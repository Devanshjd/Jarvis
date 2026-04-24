"""
J.A.R.V.I.S — Persistent Agent Loop Engine

Unlike the single-turn orchestrator (one message → one reply), the AgentLoop
runs a multi-step execution cycle that keeps working until the task is
genuinely complete — like a human would.

Inspired by usejarvis.dev's model of running agents "until done" with up to
200 iterations per turn.  We cap at MAX_ITERATIONS but the key insight is:
JARVIS should keep chaining tool calls, verifying results, and adapting
until it reaches a terminal state.

Flow:
  1. User intent → ExecutionPlan (via LLM or fast-path)
  2. For each step in the plan:
     a. Choose execution mode (screen/api/direct) via ExecutionRouter
     b. Execute the step
     c. Verify the result (screenshot, API check, etc.)
     d. If failed → adapt (retry with different mode, ask for help)
     e. If succeeded → move to next step
  3. When all steps complete → synthesize final reply
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("jarvis.agent_loop")


# ═══════════════════════════════════════════════════════════════════
#  Data Types
# ═══════════════════════════════════════════════════════════════════

class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ADAPTING = "adapting"
    SKIPPED = "skipped"


class LoopStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STUCK = "stuck"          # struggle detected
    WAITING_USER = "waiting_user"


@dataclass
class ExecutionStep:
    """A single step in a multi-step execution plan."""
    description: str
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    execution_mode: str = "auto"   # auto, screen, api, direct
    status: StepStatus = StepStatus.PENDING
    result: str = ""
    error: str = ""
    attempts: int = 0
    max_attempts: int = 3
    verify_method: str = ""        # screenshot, api_check, output_check
    depends_on: list[int] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    """Multi-step execution plan for a complex task."""
    goal: str
    steps: list[ExecutionStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: LoopStatus = LoopStatus.IDLE
    current_step: int = 0
    total_iterations: int = 0
    struggle_score: float = 0.0
    progress_messages: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
#  Agent Loop Engine
# ═══════════════════════════════════════════════════════════════════

# Limits
MAX_ITERATIONS = 50        # absolute ceiling per task
MAX_STEP_ATTEMPTS = 3      # retries per individual step
STRUGGLE_THRESHOLD = 0.6   # when to flag self-struggle
STEP_TIMEOUT = 60.0        # seconds per step execution
PLAN_TIMEOUT = 300.0       # 5 min total for a plan


class AgentLoop:
    """
    Persistent agent loop that executes multi-step plans.

    Unlike the single-turn orchestrator, this keeps running until:
    - All steps succeed
    - MAX_ITERATIONS reached
    - Struggle detected and user help needed
    - Explicit cancellation
    """

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self._active_plan: Optional[ExecutionPlan] = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._on_progress: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None

    @property
    def is_running(self) -> bool:
        return self._active_plan is not None and self._active_plan.status == LoopStatus.RUNNING

    @property
    def active_plan(self) -> Optional[ExecutionPlan]:
        return self._active_plan

    def execute_plan(
        self,
        plan: ExecutionPlan,
        on_progress: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
    ) -> None:
        """
        Start executing a plan in a background thread.

        Args:
            plan: The ExecutionPlan to run.
            on_progress: Callback(step_index, message) for live updates.
            on_complete: Callback(plan) when loop finishes.
        """
        with self._lock:
            if self.is_running:
                logger.warning("Agent loop already running — cancelling previous")
                self.cancel()

            self._active_plan = plan
            self._cancel.clear()
            self._on_progress = on_progress
            self._on_complete = on_complete

        thread = threading.Thread(
            target=self._run_loop,
            args=(plan,),
            daemon=True,
            name="jarvis-agent-loop",
        )
        thread.start()

    def cancel(self):
        """Cancel the active execution loop."""
        self._cancel.set()
        if self._active_plan:
            self._active_plan.status = LoopStatus.FAILED
            self._emit_progress(-1, "Execution cancelled.")

    def _run_loop(self, plan: ExecutionPlan):
        """Main execution loop — runs until complete, stuck, or cancelled."""
        plan.status = LoopStatus.RUNNING
        deadline = time.time() + PLAN_TIMEOUT

        self._emit_progress(-1, f"Starting: {plan.goal}")

        try:
            while (
                plan.current_step < len(plan.steps)
                and plan.total_iterations < MAX_ITERATIONS
                and time.time() < deadline
                and not self._cancel.is_set()
            ):
                plan.total_iterations += 1
                step = plan.steps[plan.current_step]

                # Check dependencies
                if not self._dependencies_met(plan, step):
                    logger.info("Step %d waiting on dependencies", plan.current_step)
                    time.sleep(0.5)
                    continue

                # Execute the step
                step.status = StepStatus.RUNNING
                step.attempts += 1
                self._emit_progress(
                    plan.current_step,
                    f"Step {plan.current_step + 1}/{len(plan.steps)}: {step.description}",
                )

                success = self._execute_step(plan, step)

                if success:
                    step.status = StepStatus.SUCCEEDED
                    self._emit_progress(
                        plan.current_step,
                        f"✓ {step.description}",
                    )
                    plan.current_step += 1
                    # Reset struggle on success
                    plan.struggle_score = max(0, plan.struggle_score - 0.2)
                else:
                    # Step failed — adapt
                    plan.struggle_score += 0.3

                    if step.attempts >= step.max_attempts:
                        # Exhausted retries — try adapting
                        adapted = self._adapt_step(plan, step)
                        if not adapted:
                            step.status = StepStatus.FAILED
                            self._emit_progress(
                                plan.current_step,
                                f"✗ Failed after {step.attempts} attempts: {step.description}",
                            )
                            # Skip this step and try to continue
                            plan.current_step += 1
                    else:
                        step.status = StepStatus.ADAPTING
                        self._emit_progress(
                            plan.current_step,
                            f"Retrying ({step.attempts}/{step.max_attempts}): {step.description}",
                        )
                        # Small delay before retry
                        time.sleep(1.0)

                    # ── Active struggle intervention ──────────────
                    # Ask the struggle detector for a concrete action
                    # instead of just checking a score threshold.
                    struggle = getattr(self.jarvis, "struggle_detector", None)
                    intervention = struggle.get_intervention() if struggle else None

                    if intervention:
                        action = intervention.get("action", "")

                        if action == "abort":
                            plan.status = LoopStatus.STUCK
                            self._emit_progress(
                                plan.current_step,
                                intervention.get("message", "Aborting — too many failures."),
                            )
                            break

                        elif action == "escalate_user":
                            plan.status = LoopStatus.STUCK
                            self._emit_progress(
                                plan.current_step,
                                intervention.get("message", "I need help with this task."),
                            )
                            # Try to recover before fully giving up
                            recovered = self._recover_from_struggle(plan)
                            if not recovered:
                                break
                            plan.status = LoopStatus.RUNNING

                        elif action == "switch_mode":
                            # Force the next attempt to use a different mode
                            new_mode = intervention.get("to_mode", "api")
                            step.execution_mode = new_mode
                            self._emit_progress(
                                plan.current_step,
                                f"Switching to {new_mode} mode for next attempt.",
                            )

                    elif plan.struggle_score >= STRUGGLE_THRESHOLD:
                        # Legacy fallback if no struggle detector
                        plan.status = LoopStatus.STUCK
                        self._emit_progress(
                            plan.current_step,
                            "I'm having difficulty with this task. Let me try a different approach.",
                        )
                        recovered = self._recover_from_struggle(plan)
                        if not recovered:
                            plan.status = LoopStatus.STUCK
                            break
                        plan.status = LoopStatus.RUNNING

            # Determine final status
            if self._cancel.is_set():
                plan.status = LoopStatus.FAILED
            elif plan.status != LoopStatus.STUCK:
                all_done = all(
                    s.status in (StepStatus.SUCCEEDED, StepStatus.SKIPPED)
                    for s in plan.steps
                )
                plan.status = LoopStatus.COMPLETED if all_done else LoopStatus.FAILED

        except Exception as e:
            logger.error("Agent loop error: %s", e)
            plan.status = LoopStatus.FAILED
            self._emit_progress(-1, f"Unexpected error: {e}")

        finally:
            if self._on_complete:
                try:
                    self._on_complete(plan)
                except Exception:
                    pass
            with self._lock:
                if self._active_plan is plan:
                    self._active_plan = None

    def _execute_step(self, plan: ExecutionPlan, step: ExecutionStep) -> bool:
        """Execute a single step, verify the result, and return True if successful."""
        try:
            # Get execution mode from router
            router = getattr(self.jarvis, "execution_router", None)
            if router and step.execution_mode == "auto":
                mode = router.choose_mode(step.tool_name, step.tool_args, step.description)
                step.execution_mode = mode
                logger.info("Router chose mode '%s' for tool '%s'", mode, step.tool_name)

            # Execute based on mode
            if step.execution_mode == "screen":
                success = self._execute_screen_step(step)
            elif step.execution_mode == "direct":
                success = self._execute_direct_step(step)
            else:
                success = self._execute_api_step(step)

            # Record outcome in struggle detector + router
            struggle = getattr(self.jarvis, "struggle_detector", None)
            if struggle:
                struggle.record(
                    tool_name=step.tool_name,
                    tool_args=step.tool_args,
                    mode=step.execution_mode,
                    success=success,
                    error=step.error[:200] if step.error else "",
                )
            if router:
                router.record_outcome(step.tool_name, step.execution_mode, success)

            # Screen verification: take a screenshot after screen actions to
            # confirm the UI looks correct.
            # Auto-verify ALL screen-mode steps unless the tool schema
            # explicitly sets verify=False.
            should_verify = step.verify_method == "screenshot"
            if not should_verify and success and step.execution_mode == "screen":
                # Check schema — default to verify for screen tools
                from core.tool_schemas import get_schema_for_tool
                schema = get_schema_for_tool(step.tool_name)
                if schema and schema.get("verify", True):
                    should_verify = True

            if success and should_verify:
                # Brief delay to let UI update before taking screenshot
                time.sleep(0.5)
                verified = self._verify_with_screenshot(step)
                if not verified:
                    logger.warning("Screenshot verification failed for: %s", step.description)
                    step.error = "Action executed but screen verification suggests it may not have worked"
                    return False

            return success

        except Exception as e:
            step.error = str(e)
            logger.error("Step execution error: %s", e)
            return False

    def _verify_with_screenshot(self, step: ExecutionStep) -> bool:
        """
        Take a screenshot after a screen action and ask the vision LLM
        whether it looks like the action succeeded.
        """
        brain = getattr(self.jarvis, "brain", None)
        screen = getattr(self.jarvis, "screen_interact", None)

        if not brain or not screen:
            return True  # Can't verify — assume success

        try:
            import base64
            import io
            from PIL import ImageGrab

            screenshot = ImageGrab.grab()
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            verify_prompt = (
                f"I just performed this action: {step.description}\n"
                f"Tool: {step.tool_name}, Args: {step.tool_args}\n\n"
                f"Look at the screenshot. Did the action succeed? "
                f"Reply with ONLY 'yes' or 'no' followed by a brief reason."
            )

            reply, _ = brain.chat_with_image(
                system_prompt="You are a screen verification agent. Analyze screenshots to confirm actions succeeded.",
                image_b64=img_b64,
                prompt_text=verify_prompt,
            )

            reply_lower = (reply or "").lower().strip()
            verified = reply_lower.startswith("yes")
            logger.info("Screenshot verification: %s — %s", "passed" if verified else "failed", reply[:100])
            return verified

        except Exception as e:
            logger.warning("Screenshot verification error: %s", e)
            return True  # Can't verify — assume success

    def _execute_api_step(self, step: ExecutionStep) -> bool:
        """Execute step via the normal tool/API pipeline."""
        executor = getattr(self.jarvis, "executor", None)
        if not executor:
            # Try via agent
            agent = getattr(self.jarvis, "agent", None)
            if agent:
                executor = agent.executor
        if not executor:
            step.error = "No executor available"
            return False

        result = executor.execute(step.tool_name, step.tool_args)
        step.result = result.output or ""
        step.error = result.error or ""
        return result.success

    def _execute_screen_step(self, step: ExecutionStep) -> bool:
        """Execute step via vision-based screen control."""
        screen = getattr(self.jarvis, "screen_interact", None)
        if not screen:
            logger.warning("Screen interact not available, falling back to API")
            return self._execute_api_step(step)

        try:
            if step.tool_name in ("screen_click", "click"):
                desc = step.tool_args.get("description", step.description)
                result = screen.click(desc)
                step.result = str(result)
                return bool(result)

            elif step.tool_name in ("screen_type", "type_text"):
                text = step.tool_args.get("text", "")
                desc = step.tool_args.get("description", "")
                if desc:
                    # Click the field first, then type
                    screen.click(desc)
                    time.sleep(0.3)
                result = screen.type_text(text)
                step.result = str(result)
                return True

            elif step.tool_name in ("screen_find", "find"):
                desc = step.tool_args.get("description", step.description)
                result = screen.find(desc)
                step.result = str(result)
                return result is not None

            elif step.tool_name == "key_press":
                import pyautogui
                keys = step.tool_args.get("keys", step.tool_args.get("key", ""))
                if "+" in keys:
                    pyautogui.hotkey(*keys.split("+"))
                else:
                    pyautogui.press(keys)
                step.result = f"Pressed {keys}"
                return True

            else:
                # For non-screen tools, fall back to API
                return self._execute_api_step(step)

        except Exception as e:
            step.error = f"Screen control error: {e}"
            logger.error("Screen step failed: %s", e)
            return False

    def _execute_direct_step(self, step: ExecutionStep) -> bool:
        """Execute step via direct system commands (subprocess, file I/O)."""
        if step.tool_name == "run_command":
            import subprocess
            cmd = step.tool_args.get("command", "")
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30,
                )
                step.result = result.stdout or result.stderr
                return result.returncode == 0
            except Exception as e:
                step.error = str(e)
                return False

        # Default: fall back to API execution
        return self._execute_api_step(step)

    def _adapt_step(self, plan: ExecutionPlan, step: ExecutionStep) -> bool:
        """
        Try to adapt a failing step — switch execution mode, simplify args, etc.

        Returns True if the step was successfully adapted and re-executed.
        """
        logger.info("Adapting step: %s (current mode: %s)", step.description, step.execution_mode)

        # Strategy 1: Switch execution mode
        mode_fallback = {
            "api": "screen",
            "screen": "api",
            "direct": "api",
            "auto": "screen",
        }
        new_mode = mode_fallback.get(step.execution_mode, "api")

        if new_mode != step.execution_mode:
            step.execution_mode = new_mode
            step.attempts = 0  # Reset attempts for new mode
            self._emit_progress(
                plan.current_step,
                f"Switching to {new_mode} mode for: {step.description}",
            )
            return True  # Will be retried in the main loop

        return False

    def _recover_from_struggle(self, plan: ExecutionPlan) -> bool:
        """
        Attempt to recover when the agent is struggling.

        Strategies:
        1. Re-plan remaining steps using the AI
        2. Simplify the approach
        3. Ask the user for guidance
        """
        logger.info("Attempting struggle recovery (score: %.2f)", plan.struggle_score)

        # Strategy 1: Ask AI for a new approach
        brain = getattr(self.jarvis, "brain", None)
        if brain:
            completed = [s for s in plan.steps if s.status == StepStatus.SUCCEEDED]
            failed = [s for s in plan.steps if s.status == StepStatus.FAILED]

            context = (
                f"I'm trying to: {plan.goal}\n"
                f"Completed steps: {[s.description for s in completed]}\n"
                f"Failed steps: {[f'{s.description} (error: {s.error})' for s in failed]}\n"
                f"What's an alternative approach I should try?"
            )

            try:
                reply, _ = brain.chat(
                    [{"role": "user", "content": context}],
                    system_prompt=(
                        "You are JARVIS's internal problem solver. The agent is stuck on a task. "
                        "Suggest a simpler alternative approach. Be concise — just list the new steps."
                    ),
                )
                if reply:
                    self._emit_progress(-1, f"Reconsidering approach: {reply[:200]}")
                    plan.struggle_score = 0.3  # Partially reset
                    return True
            except Exception:
                pass

        return False

    def _dependencies_met(self, plan: ExecutionPlan, step: ExecutionStep) -> bool:
        """Check if all dependencies for a step have been completed."""
        for dep_idx in step.depends_on:
            if dep_idx < len(plan.steps):
                if plan.steps[dep_idx].status not in (StepStatus.SUCCEEDED, StepStatus.SKIPPED):
                    return False
        return True

    def _emit_progress(self, step_index: int, message: str):
        """Send a progress update."""
        if self._active_plan:
            self._active_plan.progress_messages.append(message)
        if self._on_progress:
            try:
                self._on_progress(step_index, message)
            except Exception:
                pass
        logger.info("AgentLoop progress [step %d]: %s", step_index, message)

    # ── Plan Building ───────────────────────────────────────────

    def build_plan_from_text(self, text: str) -> ExecutionPlan:
        """
        Ask the AI to decompose a complex task into an ExecutionPlan.

        For simple tasks (single tool), creates a 1-step plan.
        For complex tasks, asks the AI to decompose.
        """
        orchestrator = getattr(self.jarvis, "orchestrator", None)
        if not orchestrator:
            return ExecutionPlan(
                goal=text,
                steps=[ExecutionStep(description=text, tool_name="", execution_mode="auto")],
            )

        # Check if this is a simple single-tool task
        from core.orchestrator import TaskType
        task_type = orchestrator.classify(text)

        if task_type in (TaskType.SIMPLE, TaskType.CACHED, TaskType.CONVERSATIONAL):
            # Not worth a multi-step plan
            return ExecutionPlan(goal=text, steps=[])

        if task_type == TaskType.TOOL:
            # Single tool — still worth wrapping in a plan for verification
            tool_name, tool_args = self._detect_tool(text, orchestrator)
            return ExecutionPlan(
                goal=text,
                steps=[
                    ExecutionStep(
                        description=text,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        execution_mode="auto",
                    ),
                ],
            )

        # Complex task — ask AI to decompose
        return self._ai_decompose(text)

    def _detect_tool(self, text: str, orchestrator) -> tuple[str, dict]:
        """Detect tool name and args for a single-tool request."""
        import re
        from core.orchestrator import _TOOL_PATTERNS

        msg_lower = text.lower().strip()
        for pattern, tool_name in _TOOL_PATTERNS:
            m = pattern.search(msg_lower)
            if m:
                tool_args = orchestrator._build_tool_args(tool_name, text, m)
                return tool_name, tool_args

        # Try capability match
        cap_match = orchestrator._resolve_capability_match(text)
        if cap_match:
            return cap_match.capability.name, {}

        return "", {}

    def _ai_decompose(self, text: str) -> ExecutionPlan:
        """Use the AI to decompose a complex task into steps."""
        brain = getattr(self.jarvis, "brain", None)
        if not brain:
            return ExecutionPlan(
                goal=text,
                steps=[ExecutionStep(description=text)],
            )

        import json

        prompt = (
            f"Decompose this task into concrete execution steps: \"{text}\"\n\n"
            "Return a JSON array of steps. Each step has:\n"
            '- "description": what to do\n'
            '- "tool": tool name (or empty if it\'s a thinking/planning step)\n'
            '- "args": dict of tool arguments\n'
            '- "mode": "screen" (use mouse/keyboard), "api" (use tool API), or "auto"\n'
            '- "verify": how to verify success ("screenshot", "output_check", or "")\n\n'
            "Available tools: open_app, web_search, screen_click, screen_type, screen_find, "
            "type_text, key_press, run_command, send_msg, get_weather, scan_screen, "
            "take_screenshot, mouse_click, mouse_scroll, set_volume, remember\n\n"
            "Keep it practical — 2-8 steps max. Return ONLY the JSON array."
        )

        try:
            reply, _ = brain.chat(
                [{"role": "user", "content": prompt}],
                system_prompt="You are a task planner. Return only valid JSON arrays.",
                max_tokens=1024,
            )

            # Parse the JSON
            reply = reply.strip()
            if reply.startswith("```"):
                reply = reply.split("\n", 1)[1].rsplit("```", 1)[0]

            steps_data = json.loads(reply)
            steps = []
            for i, s in enumerate(steps_data):
                steps.append(ExecutionStep(
                    description=s.get("description", f"Step {i+1}"),
                    tool_name=s.get("tool", ""),
                    tool_args=s.get("args", {}),
                    execution_mode=s.get("mode", "auto"),
                    verify_method=s.get("verify", ""),
                ))

            return ExecutionPlan(goal=text, steps=steps)

        except Exception as e:
            logger.error("AI decomposition failed: %s", e)
            return ExecutionPlan(
                goal=text,
                steps=[ExecutionStep(description=text)],
            )

    def get_status(self) -> dict[str, Any]:
        """Return current loop status for API/UI consumption."""
        plan = self._active_plan
        if not plan:
            return {"status": "idle", "plan": None}

        return {
            "status": plan.status.value,
            "goal": plan.goal,
            "current_step": plan.current_step,
            "total_steps": len(plan.steps),
            "iterations": plan.total_iterations,
            "struggle_score": plan.struggle_score,
            "steps": [
                {
                    "description": s.description,
                    "status": s.status.value,
                    "attempts": s.attempts,
                    "result": s.result[:200] if s.result else "",
                    "error": s.error[:200] if s.error else "",
                    "mode": s.execution_mode,
                }
                for s in plan.steps
            ],
            "progress": plan.progress_messages[-10:],
        }
