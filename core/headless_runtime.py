"""
Headless JARVIS runtime for non-Tk frontends.

This lets us reuse the existing Python orchestration/tool stack while
hosting it behind a browser shell or other non-desktop UI surface.
"""

from __future__ import annotations

import importlib
import threading
import time
from datetime import datetime
from typing import Any

from core.config import load_config, save_config
from core.runtime import JarvisRuntime


class _ImmediateRoot:
    """Tiny stand-in for Tk root that supports .after(...) scheduling."""

    def __init__(self):
        self._state = "normal"

    def after(self, ms: int, callback=None, *args):
        if callback is None:
            return None
        delay = max(0.0, float(ms) / 1000.0)
        if delay <= 0:
            callback(*args)
            return None
        timer = threading.Timer(delay, callback, args=args)
        timer.daemon = True
        timer.start()
        return timer

    def protocol(self, *_args, **_kwargs):
        return None

    def mainloop(self):
        return None

    def destroy(self):
        return None

    def iconify(self):
        self._state = "iconic"

    def deiconify(self):
        self._state = "normal"

    def state(self):
        return self._state


class _Configurable:
    """Minimal widget-like object with a config(...) API."""

    def __init__(self, **initial):
        self.state = dict(initial)

    def config(self, **kwargs):
        self.state.update(kwargs)


class _NullPill:
    def __init__(self, label: str = "", value: str = "", accent: str = ""):
        self.label = label
        self.value = value
        self.accent = accent

    def set(self, *, value: str | None = None, accent: str | None = None):
        if value is not None:
            self.value = value
        if accent is not None:
            self.accent = accent


class _NullStatusDot:
    def __init__(self):
        self.label = _Configurable(text="ONLINE")
        self.color = "green"


class _NullCore:
    def set_mode(self, _mode: str):
        return None

    def set_voice_level(self, _level: float):
        return None

    def add_chat(self, _role: str, _text: str):
        return None


class _NullSidebar:
    def __init__(self):
        self.stats: dict[str, Any] = {}
        self.mode = "General"
        self.compact_status = "NOMINAL"
        self.file_status = ""

    def update_stats(self, **kwargs):
        self.stats.update(kwargs)

    def set_mode_display(self, mode: str):
        self.mode = mode

    def set_compact_status(self, value: str):
        self.compact_status = value

    def refresh_memories(self, _memories):
        return None

    def refresh_tasks(self, _tasks):
        return None

    def set_file_status(self, text: str, _color: str = ""):
        self.file_status = text

    def toggle(self, callback=None):
        if callback:
            callback(True)

    def get_task_input(self):
        return ""

    def clear_task_input(self):
        return None

    def get_selected_task_index(self):
        return None


class _NullChatInput:
    def __init__(self):
        self.enabled = True
        self.text = ""

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)

    def get_text(self) -> str:
        return self.text

    def clear(self):
        self.text = ""

    def set_text(self, text: str):
        self.text = text

    def append_text(self, text: str):
        if self.text:
            self.text = f"{self.text}\n\n{text}"
        else:
            self.text = text


class _MessageStore:
    """Thread-safe chat transcript store for browser and API clients."""

    def __init__(self):
        self.messages: list[dict[str, Any]] = []
        self._cond = threading.Condition()

    def _normalize(self, text: Any) -> str:
        if text is None:
            return ""
        if isinstance(text, dict):
            for key in ("answer", "spoken_reply", "message", "content", "text", "reply", "summary"):
                val = text.get(key)
                if isinstance(val, str) and val.strip():
                    return val
            return str(text)
        return str(text)

    def add_message(self, role: str, text: Any):
        entry = {
            "id": len(self.messages) + 1,
            "role": role,
            "text": self._normalize(text),
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        with self._cond:
            self.messages.append(entry)
            self._cond.notify_all()

    def remove_last_thinking(self):
        with self._cond:
            for idx in range(len(self.messages) - 1, -1, -1):
                if self.messages[idx]["role"] == "thinking":
                    self.messages.pop(idx)
                    break
            self._cond.notify_all()

    def clear(self):
        with self._cond:
            self.messages.clear()
            self._cond.notify_all()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._cond:
            return list(self.messages)

    def wait_for_growth(self, previous_len: int, timeout: float) -> bool:
        with self._cond:
            if len(self.messages) > previous_len:
                return True
            self._cond.wait(timeout=timeout)
            return len(self.messages) > previous_len


class HeadlessJarvisRuntime(JarvisRuntime):
    """
    Headless JARVIS runtime — extends JarvisRuntime with HTTP/API features.

    Provides null UI stubs (no Tk) and HTTP-friendly methods like
    process_text(), status_snapshot(), and history().
    """

    _PLUGIN_SPECS = [
        ("plugins.voice.voice_plugin", "VoicePlugin", "Voice"),
        ("plugins.automation.auto_plugin", "AutomationPlugin", "Automation"),
        ("plugins.web_intel.web_plugin", "WebIntelPlugin", "Web Intel"),
        ("plugins.cyber.cyber_plugin", "CyberPlugin", "Cyber"),
        ("plugins.code_assist.code_plugin", "CodeAssistPlugin", "Code Assist"),
        ("plugins.scheduler.scheduler_plugin", "SchedulerPlugin", "Scheduler"),
        ("plugins.file_manager.file_manager_plugin", "FileManagerPlugin", "File Manager"),
        ("plugins.smart_home.smart_home_plugin", "SmartHomePlugin", "Smart Home"),
        ("plugins.email.email_plugin", "EmailPlugin", "Email"),
        ("plugins.self_improve.self_improve_plugin", "SelfImprovePlugin", "Self Improve"),
        ("plugins.conversation_memory.conversation_memory_plugin", "ConversationMemoryPlugin", "Conversation Memory"),
        ("plugins.web_automation.web_automation_plugin", "WebAutomationPlugin", "Web Automation"),
        ("plugins.pentest.pentest_plugin", "PentestPlugin", "Pentest"),
        ("plugins.messaging.messaging_plugin", "MessagingPlugin", "Messaging"),
    ]

    def __init__(self):
        # Initialize all core engines from JarvisRuntime base
        self._init_engines()
        self._request_options: dict[str, Any] = {}
        self._request_lock = threading.Lock()

        self.root = _ImmediateRoot()
        self.chat = _MessageStore()
        self.chat_input = _NullChatInput()
        self.sidebar = _NullSidebar()
        self.main_core = _NullCore()
        self.core_3d = None
        self.subtitle = _Configurable(text="Headless operator runtime")
        self.mode_label = _Configurable(text=self.config.get("mode", "GENERAL").upper())
        self.clock_label = _Configurable(text="00:00")
        self.voice_btn = _Configurable(text="MIC OFF")
        self.sidebar_btn = _Configurable(text="STACK OPEN")
        self.scan_btn = _Configurable(text="Scan")
        self.status_dot = _NullStatusDot()
        self.system_pill = _NullPill("SYSTEM", "NOMINAL", "green")
        self.provider_pill = _NullPill("ACTIVE AI", self._format_provider_text(), "primary")
        self.mode_pill = _NullPill("MODE", self.config.get("mode", "General").upper(), "accent")
        self.voice_pill = _NullPill("VOICE", "MIC OFF", "text_dim")
        self.session_pill = _NullPill("SESSION", "00:00", "text_dim")
        self.task_pill = _NullPill("TASKS", str(len(self.config.get("tasks", []))), "accent")
        self.hero_shell = None
        self.cmd_shell = None
        self.clipboard_shell = None
        self._clipboard_preview_text = ""

        self._load_plugins()
        self.capabilities.refresh()
        self._start_engines()
        self.chat.add_message("system", "Headless JARVIS runtime online.")

    def _load_plugins(self):
        for module_name, class_name, label in self._PLUGIN_SPECS:
            try:
                module = importlib.import_module(module_name)
                plugin_class = getattr(module, class_name)
                self.plugin_manager.load_plugin(plugin_class)
            except Exception as exc:
                print(f"{label} plugin: {exc}")

    def toggle_voice(self):
        voice_plugin = self.plugin_manager.get_plugin("voice")
        if not voice_plugin:
            self.chat.add_message("system", "Voice plugin not loaded.")
            return False

        if self.voice_enabled:
            voice_plugin.disable()
            self.voice_enabled = False
            self.voice_btn.config(text="MIC OFF")
            self.voice_pill.set(value="MIC OFF", accent="text_dim")
            self.chat.add_message("system", "Voice standby.")
        else:
            ok = bool(voice_plugin.enable())
            self.voice_enabled = ok
            if ok:
                self.voice_btn.config(text="MIC ON")
                accent = "green" if getattr(voice_plugin, "uses_gemini_live", lambda: False)() else "primary"
                label = "GEMINI LIVE" if getattr(voice_plugin, "uses_gemini_live", lambda: False)() else "MIC LIVE"
                self.voice_pill.set(value=label, accent=accent)
                self.chat.add_message("system", f"{label} active.")
            else:
                self.voice_btn.config(text="MIC OFF")
                self.voice_pill.set(value="MIC OFF", accent="text_dim")
                self.chat.add_message("system", "Voice failed to start.")
        return self.voice_enabled

    def voice_snapshot(self) -> dict[str, Any]:
        voice_plugin = self.plugin_manager.get_plugin("voice")
        if not voice_plugin:
            return {
                "loaded": False,
                "active": False,
                "engine": "none",
                "live_session": False,
            }

        status = {}
        try:
            status = voice_plugin.get_status() or {}
        except Exception:
            status = {}
        return {
            "loaded": True,
            "active": bool(status.get("active", self.voice_enabled)),
            "engine": status.get("engine", "classic"),
            "tts_engine": status.get("tts_engine", "auto"),
            "wake_word_active": bool(status.get("wake_word_active")),
            "live_session": bool(status.get("live_session")),
        }

    def set_voice_enabled(self, enabled: bool | None = None) -> dict[str, Any]:
        target = self.voice_enabled if enabled is None else bool(enabled)
        if enabled is None or target != self.voice_enabled:
            current = bool(self.voice_enabled)
            if enabled is None:
                self.toggle_voice()
            elif enabled and not current:
                self.toggle_voice()
            elif not enabled and current:
                self.toggle_voice()
        snapshot = self.voice_snapshot()
        self.voice_enabled = bool(snapshot.get("active"))
        return snapshot

    def _refresh_clipboard_preview(self, force: bool = False):
        return None

    def _update_shell_chrome(self, accent):
        return None

    def paste_clipboard_to_input(self, send_now: bool = False):
        return None

    def request_permission(self, prompt: str | None = None, **_kwargs) -> bool:
        """
        Allow non-Tk shells to govern dangerous desktop actions.

        Browser/API callers can opt in per request by setting approve_desktop.
        """
        if self._request_options.get("approve_desktop"):
            return True
        if prompt:
            self.chat.add_message(
                "system",
                f"Desktop approval required. Re-send with approval enabled.\n\n{prompt}",
            )
        return False

    def process_text(self, text: str, approve_desktop: bool = False, timeout: float = 120.0) -> dict[str, Any]:
        """
        Process one user turn and wait until the runtime emits a stable reply.
        """
        with self._request_lock:
            start_index = len(self.chat.snapshot())
            self._request_options = {"approve_desktop": bool(approve_desktop)}
            try:
                self.send_message(text)
                result = self._wait_for_turn(start_index, timeout)
                result["status"] = self.status_snapshot()
                return result
            finally:
                self._request_options = {}

    def _wait_for_turn(self, start_index: int, timeout: float) -> dict[str, Any]:
        deadline = time.time() + max(1.0, timeout)
        observed_len = start_index

        while time.time() < deadline:
            snapshot = self.chat.snapshot()
            delta = snapshot[start_index:]
            visible = [m for m in delta if m["role"] != "thinking"]
            terminal = [m for m in visible if m["role"] in {"assistant", "system"}]

            if terminal and not self._processing:
                time.sleep(0.12)
                snapshot = self.chat.snapshot()
                delta = snapshot[start_index:]
                visible = [m for m in delta if m["role"] != "thinking"]
                terminal = [m for m in visible if m["role"] in {"assistant", "system"}]
                last = terminal[-1] if terminal else None
                return {
                    "reply": (last or {}).get("text", ""),
                    "messages": visible,
                    "waiting_for_input": bool(self.orchestrator.task_sessions.get_waiting_session()),
                    "processing": bool(self._processing),
                }

            remaining = max(0.05, deadline - time.time())
            self.chat.wait_for_growth(observed_len, min(0.25, remaining))
            observed_len = len(self.chat.snapshot())

        snapshot = self.chat.snapshot()
        delta = [m for m in snapshot[start_index:] if m["role"] != "thinking"]
        last = next((m for m in reversed(delta) if m["role"] in {"assistant", "system"}), None)
        return {
            "reply": (last or {}).get("text", ""),
            "messages": delta,
            "waiting_for_input": bool(self.orchestrator.task_sessions.get_waiting_session()),
            "processing": bool(self._processing),
            "timed_out": True,
        }

    def status_snapshot(self) -> dict[str, Any]:
        provider = self.brain.get_provider_info()
        waiting = self.orchestrator.task_sessions.get_waiting_session()
        voice = self.voice_snapshot()
        self.voice_enabled = bool(voice.get("active"))
        return {
            "provider": provider,
            "mode": self.mode_switcher.current_mode,
            "agent_mode": self.agent_mode,
            "voice_enabled": self.voice_enabled,
            "voice": voice,
            "messages": self.brain.msg_count,
            "memories": len(self.memory),
            "tasks": len(self.config.get("tasks", [])),
            "plugins": sorted(self.plugin_manager.plugins.keys()),
            "waiting_for_input": bool(waiting),
            "waiting_summary": self.orchestrator.task_sessions.describe_for_user() if waiting else "",
            "agent_loop": self.agent_loop.get_status(),
            "struggle": self.struggle_detector.get_status(),
        }

    def history(self, limit: int = 120) -> list[dict[str, Any]]:
        return self.chat.snapshot()[-max(1, int(limit)):]

    # shutdown() is inherited from JarvisRuntime
