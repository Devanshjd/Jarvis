"""
J.A.R.V.I.S - Task Session Manager

Tracks one active operator task so JARVIS can remember:
- what it is trying to do
- which tool it chose
- which inputs are still missing
- what step it is on
- what happened last
"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Optional


@dataclass
class TaskSession:
    session_id: str
    goal: str
    tool_name: str
    args: dict = field(default_factory=dict)
    required_args: list[str] = field(default_factory=list)
    missing_args: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    status: str = "draft"
    step: str = "created"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    attempts: int = 0
    success: Optional[bool] = None
    last_result: str = ""
    last_user_text: str = ""

    def touch(self) -> None:
        self.updated_at = time.time()

    def is_fresh(self, max_age: float = 120.0) -> bool:
        return (time.time() - self.updated_at) <= max_age

    def is_waiting(self, max_age: float = 120.0) -> bool:
        return self.status == "waiting_input" and self.is_fresh(max_age)

    def to_pending_tool(self) -> dict:
        if self.status != "waiting_input":
            return {}
        return {
            "tool": self.tool_name,
            "args": dict(self.args),
            "missing": list(self.prompts or self.missing_args),
            "time": self.updated_at,
            "session_id": self.session_id,
            "step": self.step,
        }

    def to_last_action(self) -> dict:
        return {
            "tool": self.tool_name,
            "args": dict(self.args),
            "time": self.updated_at,
            "result": self.last_result,
            "success": self.success,
            "status": self.status,
            "step": self.step,
            "attempts": self.attempts,
        }

    def describe(self) -> str:
        filled = ", ".join(f"{k}={v}" for k, v in self.args.items() if v) or "no args yet"
        waiting = ""
        if self.missing_args:
            waiting = f" | waiting for: {', '.join(self.missing_args)}"
        result = f" | last result: {self.last_result[:100]}" if self.last_result else ""
        return (
            f"{self.tool_name} [{self.status}] step={self.step} attempts={self.attempts} "
            f"| {filled}{waiting}{result}"
        )


class TaskSessionManager:
    """Single active task session plus a recent completed/failed session."""

    TERMINAL_STATES = {"completed", "failed", "cancelled"}

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self._lock = threading.Lock()
        self._counter = 0
        self._active: Optional[TaskSession] = None
        self._last: Optional[TaskSession] = None

    def start_or_update(
        self,
        *,
        goal: str,
        tool_name: str,
        args: Optional[dict] = None,
        required_args: Optional[list[str]] = None,
        user_text: str = "",
    ) -> TaskSession:
        with self._lock:
            session = self._active
            if (
                session
                and session.is_fresh()
                and session.tool_name == tool_name
                and session.status not in self.TERMINAL_STATES
            ):
                self._merge_args(session, args or {})
                if required_args is not None:
                    session.required_args = list(required_args)
                if goal:
                    session.goal = goal
                if user_text:
                    session.last_user_text = user_text
                session.touch()
                return session

            session = TaskSession(
                session_id=self._new_id(),
                goal=goal,
                tool_name=tool_name,
                args=dict(args or {}),
                required_args=list(required_args or []),
                last_user_text=user_text,
            )
            self._active = session
            return session

    def get_active_session(self, max_age: float = 120.0) -> Optional[TaskSession]:
        with self._lock:
            if self._active and self._active.is_fresh(max_age):
                return self._active
            if self._active and not self._active.is_fresh(max_age):
                self._active = None
            return None

    def get_waiting_session(self, max_age: float = 120.0) -> Optional[TaskSession]:
        session = self.get_active_session(max_age=max_age)
        if session and session.is_waiting(max_age=max_age):
            return session
        return None

    def get_recent_action(self, max_age: float = 120.0) -> Optional[TaskSession]:
        with self._lock:
            candidate = self._last
            if candidate and candidate.is_fresh(max_age):
                return candidate
            if self._active and self._active.attempts > 0 and self._active.is_fresh(max_age):
                return self._active
            return None

    def set_waiting(
        self,
        *,
        missing_args: list[str],
        prompts: list[str],
        args: Optional[dict] = None,
        result_text: str = "",
        step: str = "awaiting_input",
    ) -> Optional[TaskSession]:
        with self._lock:
            if not self._active:
                return None
            if args:
                self._merge_args(self._active, args)
            self._active.missing_args = list(missing_args)
            self._active.prompts = list(prompts)
            self._active.status = "waiting_input"
            self._active.step = step
            self._active.success = None
            if result_text:
                self._active.last_result = result_text
            self._active.touch()
            return self._active

    def mark_executing(
        self,
        *,
        args: Optional[dict] = None,
        step: str = "executing",
    ) -> Optional[TaskSession]:
        with self._lock:
            if not self._active:
                return None
            if args:
                self._merge_args(self._active, args)
            self._active.status = "executing"
            self._active.step = step
            self._active.missing_args = []
            self._active.prompts = []
            self._active.attempts += 1
            self._active.touch()
            return self._active

    def record_result(
        self,
        *,
        success: bool,
        result_text: str,
        args: Optional[dict] = None,
        step: Optional[str] = None,
        keep_active: bool = False,
    ) -> Optional[TaskSession]:
        with self._lock:
            session = self._active
            if not session:
                return None
            if args:
                self._merge_args(session, args)
            session.success = success
            session.last_result = result_text or ""
            session.status = "completed" if success else "failed"
            session.step = step or session.status
            session.touch()
            self._last = session
            if not keep_active:
                self._active = None
            return session

    def cancel_active(self, reason: str = "") -> Optional[TaskSession]:
        with self._lock:
            session = self._active
            if not session:
                return None
            session.status = "cancelled"
            session.step = "cancelled"
            session.success = False
            session.last_result = reason or "Cancelled by user."
            session.touch()
            self._last = session
            self._active = None
            return session

    def clear_active(self, tool_name: Optional[str] = None) -> None:
        with self._lock:
            if not self._active:
                return
            if tool_name and self._active.tool_name != tool_name:
                return
            self._active = None

    def describe_for_user(self) -> str:
        active = self.get_active_session()
        recent = self.get_recent_action()
        if not active and not recent:
            return "No active task session."

        lines = ["Task Session Status:"]
        if active:
            lines.append(f"- Active: {active.describe()}")
        if recent and recent is not active:
            lines.append(f"- Recent: {recent.describe()}")
        return "\n".join(lines)

    def get_prompt_context(self) -> str:
        active = self.get_active_session()
        recent = self.get_recent_action()
        lines = []
        if active:
            lines.append("[ACTIVE TASK SESSION]")
            lines.append(active.describe())
        if recent and recent is not active:
            lines.append("[RECENT TASK SESSION]")
            lines.append(recent.describe())
        return "\n".join(lines)

    def _merge_args(self, session: TaskSession, args: dict) -> None:
        for key, value in (args or {}).items():
            if value not in ("", None, [], {}):
                session.args[key] = value

    def _new_id(self) -> str:
        self._counter += 1
        return f"task-{int(time.time())}-{self._counter}"
