"""
J.A.R.V.I.S — Context Injector
Automatically builds rich situational context for every AI call.

Inspired by IRIS-AI's context injection pattern: before every AI call,
inject system state, active window, time, recent actions, and environment.
This makes JARVIS situationally aware without the user having to explain context.
"""

import time
from datetime import datetime


class ContextInjector:
    """
    Builds a compact situational awareness block that gets injected
    into every AI system prompt. Keeps JARVIS aware of:
    - Current time and day context
    - System health (CPU, RAM, battery)
    - Active window / what user is doing
    - Recent actions and their outcomes
    - Current conversation state
    - Pending tasks
    """

    def __init__(self, jarvis):
        self.jarvis = jarvis

    def build_context(self) -> str:
        """Build full situational context string for system prompt injection."""
        sections = []

        # ── Time awareness ──
        sections.append(self._time_context())

        # ── System health (compact) ──
        sys_ctx = self._system_context()
        if sys_ctx:
            sections.append(sys_ctx)

        # ── Active window ──
        win_ctx = self._window_context()
        if win_ctx:
            sections.append(win_ctx)

        # ── Recent actions (what JARVIS just did) ──
        action_ctx = self._recent_actions_context()
        if action_ctx:
            sections.append(action_ctx)

        # ── Pending tasks ──
        pending_ctx = self._pending_context()
        if pending_ctx:
            sections.append(pending_ctx)

        # ── Persistent state map ──
        state_ctx = self._persistent_state_context()
        if state_ctx:
            sections.append(state_ctx)

        # ── Conversation state ──
        conv_ctx = self._conversation_state()
        if conv_ctx:
            sections.append(conv_ctx)

        if not sections:
            return ""

        return "[SITUATIONAL AWARENESS]\n" + "\n".join(sections)

    def _time_context(self) -> str:
        """Current time and day context."""
        now = datetime.now()
        day = now.strftime("%A")
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%d %B %Y")

        # Time-of-day hint
        hour = now.hour
        if hour < 6:
            period = "late night"
        elif hour < 12:
            period = "morning"
        elif hour < 17:
            period = "afternoon"
        elif hour < 21:
            period = "evening"
        else:
            period = "night"

        return f"Time: {time_str} {day} {date_str} ({period})"

    def _system_context(self) -> str:
        """Compact system health — only mention if something is notable."""
        try:
            awareness = getattr(self.jarvis, 'awareness', None)
            if not awareness:
                return ""

            h = awareness.system_health
            parts = []

            # Only mention CPU if notable
            if h.cpu_percent > 50:
                parts.append(f"CPU: {h.cpu_percent:.0f}%")

            # RAM if high
            if h.ram_percent > 75:
                parts.append(f"RAM: {h.ram_percent:.0f}%")

            # Battery if low or notable
            if h.battery_percent is not None:
                if h.battery_percent < 30 and not h.battery_plugged:
                    parts.append(f"Battery: {h.battery_percent:.0f}% (unplugged!)")

            if parts:
                return "System: " + " | ".join(parts)
            return ""
        except Exception:
            return ""

    def _window_context(self) -> str:
        """What app/window the user is currently in."""
        try:
            awareness = getattr(self.jarvis, 'awareness', None)
            if not awareness:
                return ""

            win = awareness.active_window
            if win.app_name:
                ctx = f"Active: {win.app_name}"
                if win.title and win.title != win.app_name:
                    # Truncate long titles
                    title = win.title[:60] + "..." if len(win.title) > 60 else win.title
                    ctx += f" — {title}"
                if win.app_category and win.app_category != "other":
                    ctx += f" [{win.app_category}]"
                return ctx
            return ""
        except Exception:
            return ""

    def _recent_actions_context(self) -> str:
        """What JARVIS recently did — so it doesn't lose track."""
        try:
            orchestrator = getattr(self.jarvis, 'orchestrator', None)
            if not orchestrator:
                return ""

            sessions = getattr(orchestrator, "task_sessions", None)
            if sessions:
                recent = sessions.get_recent_action()
                if recent and recent.is_fresh(120):
                    args_str = ", ".join(f"{k}={v}" for k, v in recent.args.items() if v)
                    status = (
                        "ok" if recent.success is True
                        else "failed" if recent.success is False
                        else recent.status
                    )
                    ctx = f"Last action ({int(time.time() - recent.updated_at)}s ago): {recent.tool_name}"
                    if args_str:
                        ctx += f"({args_str})"
                    ctx += f" [{status}]"
                    if recent.last_result and recent.success is False:
                        ctx += f" - {recent.last_result[:80]}"
                    return ctx

            last = getattr(orchestrator, '_last_action', {})
            if not last:
                return ""

            elapsed = time.time() - last.get("time", 0)
            if elapsed > 120:
                return ""  # too old

            tool = last.get("tool", "unknown")
            args = last.get("args", {})
            success = last.get("success", None)
            result = last.get("result", "")

            status = "✓" if success else "✗"
            args_str = ", ".join(f"{k}={v}" for k, v in args.items() if v) if args else ""

            ctx = f"Last action ({int(elapsed)}s ago): {tool}({args_str}) {status}"
            if result and not success:
                ctx += f" — {result[:80]}"
            return ctx
        except Exception:
            return ""

    def _pending_context(self) -> str:
        """Pending incomplete actions."""
        try:
            orchestrator = getattr(self.jarvis, 'orchestrator', None)
            if not orchestrator:
                return ""

            sessions = getattr(orchestrator, "task_sessions", None)
            if sessions:
                waiting = sessions.get_waiting_session()
                if waiting and waiting.is_waiting(120):
                    filled = ", ".join(f"{k}={v}" for k, v in waiting.args.items() if v)
                    ctx = f"Pending: {waiting.tool_name}"
                    if filled:
                        ctx += f"({filled})"
                    if waiting.missing_args:
                        ctx += f" - waiting for: {'; '.join(waiting.missing_args)}"
                    return ctx

            pending = getattr(orchestrator, '_pending_tool', {})
            if not pending:
                return ""

            elapsed = time.time() - pending.get("time", 0)
            if elapsed > 120:
                return ""

            tool = pending.get("tool", "")
            args = pending.get("args", {})
            missing = pending.get("missing", [])

            filled = ", ".join(f"{k}={v}" for k, v in args.items() if v)
            ctx = f"Pending: {tool}({filled})"
            if missing:
                ctx += f" — waiting for: {'; '.join(missing)}"
            return ctx
        except Exception:
            return ""

    def _conversation_state(self) -> str:
        """Voice/conversation state."""
        try:
            voice = None
            pm = getattr(self.jarvis, 'plugin_manager', None)
            if pm:
                voice = pm.get_plugin("voice")

            parts = []
            if voice:
                if getattr(voice, '_conversation_active', False):
                    parts.append("Voice conversation active")
                if getattr(voice, '_confirmation_active', False):
                    parts.append("Awaiting voice confirmation")
                if getattr(voice, 'is_speaking', False):
                    parts.append("Currently speaking")

            # Mode
            mode = getattr(self.jarvis, 'mode_switcher', None)
            if mode and mode.current_mode != "General":
                parts.append(f"Mode: {mode.current_mode}")

            if parts:
                return "State: " + " | ".join(parts)
            return ""
        except Exception:
            return ""

    def _persistent_state_context(self) -> str:
        """Compact view of long-term stores so JARVIS knows where memory lives."""
        try:
            registry = getattr(self.jarvis, "state_registry", None)
            if not registry:
                return ""
            stores = registry.list_stores()
            important = []
            for store in stores:
                if not store.exists:
                    continue
                if store.name in {"contacts", "conversations", "goals", "intelligence", "knowledge_json", "knowledge_graph"}:
                    important.append(f"{store.name}: {store.summary}")
            if important:
                return "Persistent: " + " | ".join(important[:6])
            return ""
        except Exception:
            return ""
