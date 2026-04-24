"""
J.A.R.V.I.S — Self-Struggle Detection

Monitors JARVIS's own execution for signs of difficulty and triggers
adaptive behavior.  Unlike the existing screen_monitor (which watches
the USER), this watches JARVIS itself.

Struggle signals:
  - Repeated tool failures on the same task
  - Timeout on execution steps
  - Oscillating between modes (screen → api → screen)
  - Same tool called 3+ times with same args
  - Error rate spike in last N actions
  - No progress (same step for too long)

When struggle is detected, the system can:
  - Switch execution mode (screen → api or vice versa)
  - Simplify the approach (fewer steps)
  - Ask the user for clarification
  - Fall back to a different provider
  - Log the struggle for future learning

Inspired by usejarvis.dev's struggle detection that watches agent
behavior in real-time and adapts.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("jarvis.struggle")


@dataclass
class ActionRecord:
    """Record of a single action taken by JARVIS."""
    tool_name: str
    tool_args: dict
    execution_mode: str
    success: bool
    error: str = ""
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class StruggleState:
    """Current struggle assessment."""
    score: float = 0.0           # 0.0 = no struggle, 1.0 = completely stuck
    is_struggling: bool = False
    reason: str = ""
    suggestion: str = ""
    consecutive_failures: int = 0
    mode_switches: int = 0
    repeated_calls: int = 0


class StruggleDetector:
    """
    Monitors JARVIS's execution behavior and detects when it's struggling.

    Maintains a sliding window of recent actions and computes a struggle
    score based on failure patterns, repetition, and mode oscillation.
    """

    # Thresholds
    WINDOW_SIZE = 20               # Track last N actions
    STRUGGLE_THRESHOLD = 0.5       # Score above this = struggling
    CRITICAL_THRESHOLD = 0.8       # Score above this = severely stuck
    CONSECUTIVE_FAIL_LIMIT = 3     # 3 failures in a row = immediate struggle
    REPEAT_LIMIT = 3               # Same tool+args 3 times = stuck in loop
    MODE_SWITCH_LIMIT = 4          # 4 mode switches = oscillating
    DECAY_RATE = 0.05              # Score decays per successful action
    FAIL_WEIGHT = 0.2              # Each failure adds this to score
    REPEAT_WEIGHT = 0.15           # Each repeat adds this
    OSCILLATION_WEIGHT = 0.1       # Each mode switch adds this

    def __init__(self):
        self._history: deque[ActionRecord] = deque(maxlen=self.WINDOW_SIZE)
        self._state = StruggleState()
        self._current_goal: str = ""
        self._goal_start_time: float = 0.0

    def set_goal(self, goal: str):
        """Mark the start of a new task/goal."""
        self._current_goal = goal
        self._goal_start_time = time.time()
        # Partially reset on new goal (carry over some history)
        self._state.consecutive_failures = 0
        self._state.mode_switches = 0
        self._state.repeated_calls = 0

    def record_action(self, record: ActionRecord):
        """Record an action and update the struggle score."""
        self._history.append(record)
        self._update_state()

    def record(
        self,
        tool_name: str,
        tool_args: dict,
        mode: str,
        success: bool,
        error: str = "",
        latency_ms: float = 0.0,
    ):
        """Convenience method to record an action."""
        self.record_action(ActionRecord(
            tool_name=tool_name,
            tool_args=tool_args,
            execution_mode=mode,
            success=success,
            error=error,
            latency_ms=latency_ms,
        ))

    def _update_state(self):
        """Recompute the struggle state from recent history."""
        if not self._history:
            self._state = StruggleState()
            return

        recent = list(self._history)
        score = 0.0
        reasons = []

        # 1. Consecutive failures
        consecutive = 0
        for action in reversed(recent):
            if not action.success:
                consecutive += 1
            else:
                break
        self._state.consecutive_failures = consecutive

        if consecutive >= self.CONSECUTIVE_FAIL_LIMIT:
            score += consecutive * self.FAIL_WEIGHT
            reasons.append(f"{consecutive} consecutive failures")

        # 2. Overall failure rate in window
        total = len(recent)
        failures = sum(1 for a in recent if not a.success)
        if total >= 5:
            fail_rate = failures / total
            if fail_rate > 0.5:
                score += fail_rate * 0.3
                reasons.append(f"{fail_rate:.0%} failure rate in last {total} actions")

        # 3. Repeated calls (same tool + same args)
        from collections import Counter
        call_sigs = []
        for a in recent[-10:]:  # Check last 10
            sig = f"{a.tool_name}:{sorted(a.tool_args.items())}"
            call_sigs.append(sig)

        sig_counts = Counter(call_sigs)
        max_repeat = max(sig_counts.values()) if sig_counts else 0
        self._state.repeated_calls = max_repeat

        if max_repeat >= self.REPEAT_LIMIT:
            score += max_repeat * self.REPEAT_WEIGHT
            reasons.append(f"Same action repeated {max_repeat} times")

        # 4. Mode oscillation
        modes_used = [a.execution_mode for a in recent[-8:]]
        switches = sum(
            1 for i in range(1, len(modes_used))
            if modes_used[i] != modes_used[i-1]
        )
        self._state.mode_switches = switches

        if switches >= self.MODE_SWITCH_LIMIT:
            score += switches * self.OSCILLATION_WEIGHT
            reasons.append(f"Oscillating between modes ({switches} switches)")

        # 5. Time-based struggle (spending too long on one goal)
        if self._goal_start_time:
            elapsed = time.time() - self._goal_start_time
            if elapsed > 120:  # More than 2 minutes on same goal
                time_penalty = min(0.3, (elapsed - 120) / 300)
                score += time_penalty
                reasons.append(f"Task running for {elapsed:.0f}s")

        # 6. Decay from successes
        recent_successes = sum(1 for a in recent[-5:] if a.success)
        score -= recent_successes * self.DECAY_RATE

        # Clamp
        score = max(0.0, min(1.0, score))

        # Build state
        self._state.score = score
        self._state.is_struggling = score >= self.STRUGGLE_THRESHOLD
        self._state.reason = "; ".join(reasons) if reasons else ""
        self._state.suggestion = self._suggest_recovery()

    def _suggest_recovery(self) -> str:
        """Suggest a recovery strategy based on the current state."""
        state = self._state

        if not state.is_struggling:
            return ""

        if state.consecutive_failures >= self.CONSECUTIVE_FAIL_LIMIT:
            last_actions = list(self._history)[-3:]
            last_mode = last_actions[-1].execution_mode if last_actions else "api"
            alt_mode = "screen" if last_mode == "api" else "api"
            return f"Switch to {alt_mode} mode — current approach ({last_mode}) keeps failing"

        if state.repeated_calls >= self.REPEAT_LIMIT:
            return "Break the loop — try a completely different tool or approach"

        if state.mode_switches >= self.MODE_SWITCH_LIMIT:
            # Find the mode with best recent success
            recent = list(self._history)[-8:]
            mode_success = {}
            for a in recent:
                mode_success.setdefault(a.execution_mode, []).append(a.success)
            best_mode = max(
                mode_success.keys(),
                key=lambda m: sum(mode_success[m]) / len(mode_success[m]),
                default="api",
            )
            return f"Stop oscillating — commit to {best_mode} mode"

        if state.score >= self.CRITICAL_THRESHOLD:
            return "Ask the user for help — too many failures to continue autonomously"

        return "Retry with simplified approach"

    @property
    def score(self) -> float:
        return self._state.score

    @property
    def is_struggling(self) -> bool:
        return self._state.is_struggling

    @property
    def state(self) -> StruggleState:
        return self._state

    def get_context_for_llm(self) -> str:
        """Get struggle context to inject into LLM prompts."""
        if not self._state.is_struggling:
            return ""

        return (
            f"[SELF-AWARENESS] I am currently struggling with this task "
            f"(struggle score: {self._state.score:.2f}). "
            f"Reason: {self._state.reason}. "
            f"Suggestion: {self._state.suggestion}. "
            f"I should try a different approach rather than repeating what failed."
        )

    def get_intervention(self) -> Optional[dict]:
        """
        Get a concrete intervention action based on struggle severity.

        Returns None if no intervention needed, otherwise a dict:
          - score < 0.5  → None (no intervention)
          - score >= 0.5 → switch_mode (force a different execution mode)
          - score >= 0.7 → escalate_user (ask user for help)
          - score >= 0.9 → abort (stop trying)

        The caller (agent_loop) should act on this directly instead
        of just passing a hint to the LLM.
        """
        score = self._state.score

        if score < self.STRUGGLE_THRESHOLD:
            return None

        # Determine the mode that's been failing
        recent = list(self._history)[-5:]
        current_mode = recent[-1].execution_mode if recent else "direct"
        failed_modes = {a.execution_mode for a in recent if not a.success}

        if score >= 0.9:
            return {
                "action": "abort",
                "message": (
                    f"Unable to complete after multiple attempts. "
                    f"Reason: {self._state.reason}"
                ),
                "score": score,
            }

        if score >= 0.7:
            return {
                "action": "escalate_user",
                "message": (
                    f"I'm having trouble with this task (score: {score:.2f}). "
                    f"{self._state.reason}. "
                    f"Would you like me to try a different approach?"
                ),
                "score": score,
                "suggestion": self._state.suggestion,
            }

        # score >= 0.5 — switch mode
        alt_mode = "api" if current_mode == "screen" else "screen"
        if alt_mode in failed_modes:
            alt_mode = "direct"  # try direct if both screen and api failed

        return {
            "action": "switch_mode",
            "from_mode": current_mode,
            "to_mode": alt_mode,
            "message": f"Switching from {current_mode} to {alt_mode} mode",
            "score": score,
        }

    def reset(self):
        """Reset all state."""
        self._history.clear()
        self._state = StruggleState()
        self._current_goal = ""
        self._goal_start_time = 0.0

    def get_status(self) -> dict[str, Any]:
        """Return current state for API/UI."""
        return {
            "score": self._state.score,
            "is_struggling": self._state.is_struggling,
            "reason": self._state.reason,
            "suggestion": self._state.suggestion,
            "consecutive_failures": self._state.consecutive_failures,
            "mode_switches": self._state.mode_switches,
            "repeated_calls": self._state.repeated_calls,
            "history_size": len(self._history),
            "current_goal": self._current_goal,
        }
