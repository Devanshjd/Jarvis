"""
JARVIS integration smoke tests.

These are higher-level checks than jarvis_smoke_tests.py:
- real messaging plugin flow with fake desktop controls
- real screen interaction actions with fake pyautogui
- real voice confirmation state handling with fake microphone/STT
- real orchestrator -> executor -> plugin retry path

The goal is to catch "it said it would do it but took the wrong path"
regressions without touching the user's actual mouse, keyboard, mic, or apps.

Usage:
    python training/jarvis_integration_smoke_tests.py
"""

from __future__ import annotations

import sys
import time
import traceback
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
import threading


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.orchestrator import Priority, Task, TaskOrchestrator, TaskType  # noqa: E402
from core.screen_interact import ScreenInteract  # noqa: E402
import core.screen_interact as screen_module  # noqa: E402
from plugins.messaging.messaging_plugin import MessagingPlugin  # noqa: E402
import plugins.messaging.messaging_plugin as messaging_module  # noqa: E402
from plugins.voice.voice_plugin import VoicePlugin  # noqa: E402
import plugins.voice.voice_plugin as voice_module  # noqa: E402
from plugins.voice.gemini_voice import GeminiVoiceEngine  # noqa: E402


_MISSING = object()


@contextmanager
def patched_attr(obj, name: str, value):
    original = getattr(obj, name, _MISSING)
    setattr(obj, name, value)
    try:
        yield
    finally:
        if original is _MISSING:
            delattr(obj, name)
        else:
            setattr(obj, name, original)


class BrainStub:
    def __init__(self):
        self.config = {"provider": "ollama", "max_tokens": 512}
        self.mode = "General"
        self.history = []
        self.msg_count = 0

    def add_assistant_message(self, reply: str) -> None:
        self.history.append({"role": "assistant", "content": reply})


class MemoryStub:
    def get_context_string(self) -> str:
        return ""

    def add(self, text: str) -> bool:
        return True


class PluginManagerStub:
    def __init__(self):
        self.plugins = {}

    def get_plugin(self, name: str):
        return self.plugins.get(name)


class RootStub:
    def after(self, delay_ms: int, callback):
        callback()


class ChatStub:
    def __init__(self):
        self.messages = []

    def add_message(self, role: str, text: str) -> None:
        self.messages.append((role, text))


class FakePyAutoGUI:
    def __init__(self):
        self.actions = []
        self.FAILSAFE = True
        self.PAUSE = 0.0

    def hotkey(self, *keys):
        self.actions.append(("hotkey", keys))

    def press(self, key):
        self.actions.append(("press", key))

    def click(self, *args, **kwargs):
        self.actions.append(("click", args, kwargs))

    def doubleClick(self, *args, **kwargs):
        self.actions.append(("doubleClick", args, kwargs))

    def typewrite(self, text, interval=0.0):
        self.actions.append(("typewrite", text, interval))

    def write(self, text):
        self.actions.append(("write", text))

    def moveTo(self, x, y, duration=0.0):
        self.actions.append(("moveTo", x, y, duration))

    def mouseDown(self):
        self.actions.append(("mouseDown",))

    def mouseUp(self):
        self.actions.append(("mouseUp",))

    def scroll(self, amount):
        self.actions.append(("scroll", amount))

    def size(self):
        return (1920, 1080)


class ScreenInteractStub:
    def __init__(
        self,
        verify_sent: bool = True,
        focus_via_click: bool = True,
        type_via_input: bool = True,
        click_success: bool = True,
        wrong_panel_after_type: bool = False,
        search_candidates: list[dict] | None = None,
        active_chat_title: str = "",
        composer_available: bool = True,
        blocked_state_text: str = "",
        chat_preview_text: str = "",
    ):
        self.verify_sent = verify_sent
        self.focus_via_click = focus_via_click
        self.type_via_input = type_via_input
        self.click_success = click_success
        self.wrong_panel_after_type = wrong_panel_after_type
        self.search_candidates = list(search_candidates or [])
        self.active_chat_title = active_chat_title
        self.composer_available = composer_available
        self.blocked_state_text = blocked_state_text
        self.chat_preview_text = chat_preview_text
        self.click_calls = []
        self.type_calls = []
        self.find_calls = []

    def click_element(self, description: str):
        self.click_calls.append(description)
        if not self.focus_via_click:
            raise RuntimeError("message input not detected")
        return {"success": self.click_success, "description": description}

    def type_into_element(self, description: str, text: str):
        self.type_calls.append((description, text))
        if not self.type_via_input:
            raise RuntimeError("message input typing not available")
        return {"success": True, "description": description, "typed": text}

    def read_element(self, description: str):
        lower = description.lower()
        if "chat title" in description.lower() or "contact name at the top" in description.lower() or "conversation header title" in description.lower():
            return self.active_chat_title
        if "selected whatsapp chat preview" in lower or "left chat list row" in lower:
            if self.chat_preview_text:
                return self.chat_preview_text
            if self.verify_sent and self.type_calls:
                return self.type_calls[-1][1]
            return ""
        if "outgoing message bubble" in lower or "latest sent message bubble" in lower or "most recent message you sent" in lower:
            if self.verify_sent and self.type_calls:
                return self.type_calls[-1][1]
            return ""
        if "unblock" in lower or "delete chat" in lower or "chat-management actions" in lower:
            return self.blocked_state_text
        if self.wrong_panel_after_type and "left" in description.lower():
            if self.type_calls:
                return self.type_calls[-1][1]
        if any(
            phrase in lower
            for phrase in ("type a message", "composer", "message field", "message input")
        ):
            if not self.composer_available:
                return "[Could not find element: composer]"
            if self.type_calls:
                return self.type_calls[-1][1]
            return "Type a message"
        return ""

    def find_all_elements(self, description: str):
        if "whatsapp" in description.lower() and "left panel" in description.lower():
            return list(self.search_candidates)
        return []

    def find_element(self, description: str):
        self.find_calls.append(description)
        if description.startswith("sent message containing"):
            return {"found": self.verify_sent}
        if description == "search bar with text":
            return {"found": False}
        return {"found": False}


class FakeRecognizer:
    def adjust_for_ambient_noise(self, source, duration=0.3):
        return None

    def listen(self, source, timeout=8, phrase_time_limit=5):
        return object()


class FakeMicrophone:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeMessagingPlugin:
    def __init__(self):
        self.calls = []

    def send_message(self, app: str, contact: str, message: str):
        self.calls.append((app, contact, message))
        return {
            "success": True,
            "message": f"Message sent to {contact.title()} on {app.title()}. Verified.",
        }


class FakeGeminiVoice:
    def __init__(self):
        self.started = 0
        self.stopped = 0
        self.spoken = []
        self.active = True

    def start(self):
        self.started += 1
        self.active = True
        return True

    def stop(self):
        self.stopped += 1
        self.active = False

    def speak_text(self, text: str):
        self.spoken.append(text)
        return True


def make_jarvis_stub(**overrides):
    jarvis = SimpleNamespace(
        brain=BrainStub(),
        memory=MemoryStub(),
        plugin_manager=PluginManagerStub(),
        config={},
        root=RootStub(),
        chat=ChatStub(),
        direct_control_preferred=False,
        awareness=SimpleNamespace(
            get_current_context=lambda: "",
            get_clipboard_context=lambda: "",
        ),
        mem=SimpleNamespace(get_full_context=lambda: ""),
        screen_monitor=SimpleNamespace(
            get_screen_context=lambda: "",
            struggle_score=0,
            get_live_frame=lambda: None,
            capture_now=lambda analyze=False: None,
        ),
    )
    for key, value in overrides.items():
        setattr(jarvis, key, value)
    return jarvis


def test_whatsapp_send_uses_screen_input_and_verifies():
    fake_gui = FakePyAutoGUI()
    fake_screen = ScreenInteractStub(
        verify_sent=True,
        focus_via_click=True,
        type_via_input=True,
        search_candidates=[{"label": "Dishant Meet Ent", "x": 320, "y": 260}],
        active_chat_title="Dishant Meet Ent",
    )
    jarvis = make_jarvis_stub(screen_interact=fake_screen)
    plugin = MessagingPlugin(jarvis)
    plugin.contacts = {}
    learned = []

    with ExitStack() as stack:
        stack.enter_context(patched_attr(messaging_module, "HAS_PYAUTOGUI", True))
        stack.enter_context(patched_attr(messaging_module, "pyautogui", fake_gui))
        stack.enter_context(patched_attr(messaging_module.time, "sleep", lambda *_: None))
        plugin._ask_permission = lambda app, contact, message: True
        plugin._open_app = lambda app: True
        plugin._wait_for_window = lambda title, timeout=10: True
        plugin._open_web_fallback = lambda app: learned.append(("web", app))
        plugin._type_text_safe = lambda text: fake_gui.actions.append(("type_text_safe", text))
        plugin.add_contact = lambda name, app, identifier: learned.append((name, app, identifier))
        result = plugin.send_message("whatsapp", "Meet", "I am coming")

    if not result.get("success"):
        raise AssertionError(f"WhatsApp send failed unexpectedly: {result}")
    if "Verified" not in result.get("message", ""):
        raise AssertionError(f"Expected verified result text, got: {result}")
    if "Dishant Meet Ent" not in result.get("message", ""):
        raise AssertionError(f"Expected exact chat title to be surfaced, got: {result}")
    if fake_screen.type_calls != [("the bottom message input box in the active WhatsApp chat labeled Type a message", "I am coming")]:
        raise AssertionError(f"Expected direct screen typing, got: {fake_screen.type_calls}")
    if fake_screen.click_calls:
        raise AssertionError(f"Did not expect click fallback when direct type worked: {fake_screen.click_calls}")
    if any(action == ("press", "tab") for action in fake_gui.actions):
        raise AssertionError(f"Unexpected tab fallback when input click worked: {fake_gui.actions}")
    if ("type_text_safe", "I am coming") in fake_gui.actions:
        raise AssertionError(f"Message-body raw typing should not run when screen typing worked: {fake_gui.actions}")
    if any(action == ("press", "escape") for action in fake_gui.actions):
        raise AssertionError(f"WhatsApp flow regressed to Escape: {fake_gui.actions}")


def test_whatsapp_send_falls_back_to_tabs_without_escape():
    fake_gui = FakePyAutoGUI()
    fake_screen = ScreenInteractStub(
        verify_sent=True,
        focus_via_click=True,
        type_via_input=False,
        click_success=False,
        search_candidates=[{"label": "Dishant Meet Ent", "x": 320, "y": 260}],
    )
    jarvis = make_jarvis_stub(screen_interact=fake_screen)
    plugin = MessagingPlugin(jarvis)
    plugin.contacts = {}

    with ExitStack() as stack:
        stack.enter_context(patched_attr(messaging_module, "HAS_PYAUTOGUI", True))
        stack.enter_context(patched_attr(messaging_module, "pyautogui", fake_gui))
        stack.enter_context(patched_attr(messaging_module.time, "sleep", lambda *_: None))
        plugin._ask_permission = lambda app, contact, message: True
        plugin._open_app = lambda app: True
        plugin._wait_for_window = lambda title, timeout=10: True
        plugin._open_web_fallback = lambda app: None
        plugin._type_text_safe = lambda text: fake_gui.actions.append(("type_text_safe", text))
        plugin.add_contact = lambda name, app, identifier: None
        result = plugin.send_message("whatsapp", "Meet", "I am coming")

    if not result.get("success"):
        raise AssertionError(f"Fallback send should still verify after raw typing: {result}")
    tab_count = sum(1 for action in fake_gui.actions if action == ("press", "tab"))
    if tab_count != 4:
        raise AssertionError(f"Expected 4 tab presses during fallback, got {tab_count}: {fake_gui.actions}")
    if ("type_text_safe", "I am coming") not in fake_gui.actions:
        raise AssertionError(f"Expected raw typing fallback after failed screen input: {fake_gui.actions}")
    if any(action == ("press", "escape") for action in fake_gui.actions):
        raise AssertionError(f"WhatsApp flow regressed to Escape: {fake_gui.actions}")


def test_whatsapp_blocked_chat_fails_before_send():
    fake_gui = FakePyAutoGUI()
    fake_screen = ScreenInteractStub(
        verify_sent=False,
        focus_via_click=False,
        type_via_input=False,
        search_candidates=[{"label": "Dishant Meet Ent", "x": 320, "y": 260}],
        active_chat_title="Dishant Meet Ent",
        composer_available=False,
        blocked_state_text="Delete chat Unblock",
    )
    jarvis = make_jarvis_stub(screen_interact=fake_screen)
    plugin = MessagingPlugin(jarvis)
    plugin.contacts = {}

    with ExitStack() as stack:
        stack.enter_context(patched_attr(messaging_module, "HAS_PYAUTOGUI", True))
        stack.enter_context(patched_attr(messaging_module, "pyautogui", fake_gui))
        stack.enter_context(patched_attr(messaging_module.time, "sleep", lambda *_: None))
        plugin._ask_permission = lambda app, contact, message: True
        plugin._open_app = lambda app: True
        plugin._wait_for_window = lambda title, timeout=10: True
        plugin._open_web_fallback = lambda app: None
        plugin._type_text_safe = lambda text: fake_gui.actions.append(("type_text_safe", text))
        result = plugin.send_message("whatsapp", "Meet", "I am coming")

    if result.get("success"):
        raise AssertionError(f"Blocked chat state should fail honestly: {result}")
    if "unblock/delete chat" not in result.get("message", "").lower():
        raise AssertionError(f"Expected blocked-chat explanation, got: {result}")
    if any(action == ("press", "enter") for action in fake_gui.actions):
        raise AssertionError(f"Should not press Enter when no usable composer exists: {fake_gui.actions}")


def test_whatsapp_asks_to_disambiguate_duplicate_matches():
    fake_gui = FakePyAutoGUI()
    fake_screen = ScreenInteractStub(
        verify_sent=False,
        focus_via_click=True,
        type_via_input=True,
        search_candidates=[
            {"label": "Dishant Meet Ent", "x": 320, "y": 260},
            {"label": "Meet Abyankar W", "x": 330, "y": 330},
        ],
    )
    jarvis = make_jarvis_stub(screen_interact=fake_screen)
    plugin = MessagingPlugin(jarvis)
    plugin.contacts = {}

    with ExitStack() as stack:
        stack.enter_context(patched_attr(messaging_module, "HAS_PYAUTOGUI", True))
        stack.enter_context(patched_attr(messaging_module, "pyautogui", fake_gui))
        stack.enter_context(patched_attr(messaging_module.time, "sleep", lambda *_: None))
        plugin._ask_permission = lambda app, contact, message: True
        plugin._open_app = lambda app: True
        plugin._wait_for_window = lambda title, timeout=10: True
        plugin._open_web_fallback = lambda app: None
        plugin._type_text_safe = lambda text: fake_gui.actions.append(("type_text_safe", text))
        result = plugin.send_message("whatsapp", "Meet", "I am coming")

    if result.get("success"):
        raise AssertionError(f"Duplicate match should ask for clarification: {result}")
    message = result.get("message", "")
    if "multiple whatsapp matches" not in message.lower():
        raise AssertionError(f"Expected ambiguity message, got: {result}")
    if "1. Dishant Meet Ent" not in message or "2. Meet Abyankar W" not in message:
        raise AssertionError(f"Expected numbered candidate list, got: {message}")


def test_whatsapp_ignores_suspicious_saved_exact_title():
    fake_gui = FakePyAutoGUI()
    fake_screen = ScreenInteractStub(
        verify_sent=False,
        focus_via_click=True,
        type_via_input=True,
        search_candidates=[
            {"label": "Dishant Meet Ent", "x": 320, "y": 260},
            {"label": "Meet Abyankar W", "x": 330, "y": 330},
        ],
        active_chat_title="Dishant Meet Ent",
    )
    jarvis = make_jarvis_stub(screen_interact=fake_screen)
    plugin = MessagingPlugin(jarvis)
    plugin.contacts = {
        "meet": {
            "whatsapp": {
                "query": "Ent",
                "exact_title": "Ent",
            }
        }
    }

    with ExitStack() as stack:
        stack.enter_context(patched_attr(messaging_module, "HAS_PYAUTOGUI", True))
        stack.enter_context(patched_attr(messaging_module, "pyautogui", fake_gui))
        stack.enter_context(patched_attr(messaging_module.time, "sleep", lambda *_: None))
        plugin._ask_permission = lambda app, contact, message: True
        plugin._open_app = lambda app: True
        plugin._wait_for_window = lambda title, timeout=10: True
        plugin._open_web_fallback = lambda app: None
        plugin._type_text_safe = lambda text: fake_gui.actions.append(("type_text_safe", text))
        result = plugin.send_message("whatsapp", "Meet", "I am coming")

    if result.get("success"):
        raise AssertionError(f"Verification should still fail honestly in the harness: {result}")
    if ("type_text_safe", "Meet") not in fake_gui.actions:
        raise AssertionError(f"Expected suspicious saved title to be ignored in favor of the alias, got: {fake_gui.actions}")
    if ("type_text_safe", "Ent") in fake_gui.actions:
        raise AssertionError(f"Should not search using a junk learned title: {fake_gui.actions}")


def test_whatsapp_fails_if_wrong_chat_stays_open():
    fake_gui = FakePyAutoGUI()
    fake_screen = ScreenInteractStub(
        verify_sent=False,
        focus_via_click=True,
        type_via_input=True,
        search_candidates=[{"label": "Dishant Meet Ent", "x": 320, "y": 260}],
        active_chat_title="Abdal Brer Ajent",
    )
    jarvis = make_jarvis_stub(screen_interact=fake_screen)
    plugin = MessagingPlugin(jarvis)
    plugin.contacts = {}

    with ExitStack() as stack:
        stack.enter_context(patched_attr(messaging_module, "HAS_PYAUTOGUI", True))
        stack.enter_context(patched_attr(messaging_module, "pyautogui", fake_gui))
        stack.enter_context(patched_attr(messaging_module.time, "sleep", lambda *_: None))
        plugin._ask_permission = lambda app, contact, message: True
        plugin._open_app = lambda app: True
        plugin._wait_for_window = lambda title, timeout=10: True
        plugin._open_web_fallback = lambda app: None
        plugin._type_text_safe = lambda text: fake_gui.actions.append(("type_text_safe", text))
        result = plugin.send_message("whatsapp", "Meet", "I am coming")

    if result.get("success"):
        raise AssertionError(f"Wrong active chat should fail before typing a message: {result}")
    if "stayed on abdal brer ajent" not in result.get("message", "").lower():
        raise AssertionError(f"Expected wrong-chat explanation, got: {result}")
    if ("type_text_safe", "I am coming") in fake_gui.actions:
        raise AssertionError(f"Message body should not be typed into the wrong chat: {fake_gui.actions}")


def test_whatsapp_detects_sidebar_misdirected_text():
    fake_gui = FakePyAutoGUI()
    fake_screen = ScreenInteractStub(
        verify_sent=False,
        focus_via_click=True,
        type_via_input=True,
        wrong_panel_after_type=True,
        search_candidates=[{"label": "Dishant Meet Ent", "x": 320, "y": 260}],
        active_chat_title="Dishant Meet Ent",
    )
    jarvis = make_jarvis_stub(screen_interact=fake_screen)
    plugin = MessagingPlugin(jarvis)
    plugin.contacts = {}

    with ExitStack() as stack:
        stack.enter_context(patched_attr(messaging_module, "HAS_PYAUTOGUI", True))
        stack.enter_context(patched_attr(messaging_module, "pyautogui", fake_gui))
        stack.enter_context(patched_attr(messaging_module.time, "sleep", lambda *_: None))
        plugin._ask_permission = lambda app, contact, message: True
        plugin._open_app = lambda app: True
        plugin._wait_for_window = lambda title, timeout=10: True
        plugin._open_web_fallback = lambda app: None
        plugin._type_text_safe = lambda text: fake_gui.actions.append(("type_text_safe", text))
        plugin.add_contact = lambda name, app, identifier: None
        result = plugin.send_message("whatsapp", "Meet", "I am coming")

    if result.get("success"):
        raise AssertionError(f"Sidebar misdirection should fail honestly: {result}")
    if "left sidebar" not in result.get("message", "").lower():
        raise AssertionError(f"Expected sidebar-specific failure, got: {result}")
    enter_count = sum(1 for action in fake_gui.actions if action == ("press", "enter"))
    if enter_count != 0:
        raise AssertionError(f"Should not press the send Enter after detecting sidebar misdirection: {fake_gui.actions}")


def test_whatsapp_generic_name_without_visible_candidates_fails_safely():
    fake_gui = FakePyAutoGUI()
    fake_screen = ScreenInteractStub(
        verify_sent=False,
        focus_via_click=True,
        type_via_input=True,
        search_candidates=[],
    )
    jarvis = make_jarvis_stub(screen_interact=fake_screen)
    plugin = MessagingPlugin(jarvis)
    plugin.contacts = {}

    with ExitStack() as stack:
        stack.enter_context(patched_attr(messaging_module, "HAS_PYAUTOGUI", True))
        stack.enter_context(patched_attr(messaging_module, "pyautogui", fake_gui))
        stack.enter_context(patched_attr(messaging_module.time, "sleep", lambda *_: None))
        plugin._ask_permission = lambda app, contact, message: True
        plugin._open_app = lambda app: True
        plugin._wait_for_window = lambda title, timeout=10: True
        plugin._open_web_fallback = lambda app: None
        plugin._type_text_safe = lambda text: fake_gui.actions.append(("type_text_safe", text))
        result = plugin.send_message("whatsapp", "Meet", "I am coming")

    if result.get("success"):
        raise AssertionError(f"Generic name without visible candidates should fail safely: {result}")
    if "full visible contact name" not in result.get("message", "").lower():
        raise AssertionError(f"Expected safe clarification request, got: {result}")
    if any(action == ("press", "down") for action in fake_gui.actions):
        raise AssertionError(f"Should not blindly navigate results when candidates are unknown: {fake_gui.actions}")
    if any(action == ("press", "enter") for action in fake_gui.actions):
        raise AssertionError(f"Should not open a chat when the target is unsafe: {fake_gui.actions}")


def test_voice_confirmation_restores_conversation_window():
    jarvis = make_jarvis_stub()
    plugin = VoicePlugin(jarvis)
    plugin.recognizer = FakeRecognizer()
    plugin._conversation_active = True
    plugin._conversation_expires = time.time() + 5
    spoken = []

    fake_sr = SimpleNamespace(
        Microphone=FakeMicrophone,
        WaitTimeoutError=type("WaitTimeoutError", (Exception,), {}),
        UnknownValueError=type("UnknownValueError", (Exception,), {}),
    )

    with ExitStack() as stack:
        stack.enter_context(patched_attr(voice_module, "HAS_STT", True))
        stack.enter_context(patched_attr(voice_module, "sr", fake_sr))
        stack.enter_context(patched_attr(voice_module.time, "sleep", lambda *_: None))
        plugin.speak = lambda text: spoken.append(text)
        plugin._transcribe = lambda audio: "yes send him the text"
        ok = plugin.verbal_confirm("Send it now?")

    if not ok:
        raise AssertionError("Expected confirmation to accept a natural yes phrase.")
    if plugin._confirmation_active:
        raise AssertionError("Confirmation mic ownership did not clear.")
    if not plugin._conversation_active:
        raise AssertionError("Conversation window was not restored after confirmation.")
    if not spoken or spoken[0] != "Send it now?":
        raise AssertionError(f"Unexpected spoken prompt sequence: {spoken}")


def test_voice_capture_gate_blocks_concurrent_microphone_use():
    jarvis = make_jarvis_stub()
    plugin = VoicePlugin(jarvis)
    plugin.recognizer = FakeRecognizer()
    plugin.recognizer.listen = lambda source, timeout=1, phrase_time_limit=1: (time.sleep(0.2) or object())
    plugin._transcribe = lambda audio: "ok"

    fake_sr = SimpleNamespace(
        Microphone=FakeMicrophone,
        WaitTimeoutError=type("WaitTimeoutError", (Exception,), {}),
        UnknownValueError=type("UnknownValueError", (Exception,), {}),
    )

    results = []

    def first_capture():
        results.append(
            ("first", plugin._listen_for_text(owner="one", timeout=1, phrase_time_limit=1, wait_for_slot=True))
        )

    def second_capture():
        time.sleep(0.05)
        try:
            plugin._listen_for_text(owner="two", timeout=1, phrase_time_limit=1, wait_for_slot=False)
            results.append(("second", "unexpected-success"))
        except RuntimeError as exc:
            results.append(("second", str(exc)))

    with ExitStack() as stack:
        stack.enter_context(patched_attr(voice_module, "HAS_STT", True))
        stack.enter_context(patched_attr(voice_module, "sr", fake_sr))
        t1 = threading.Thread(target=first_capture)
        t2 = threading.Thread(target=second_capture)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    busy = [value for name, value in results if name == "second"]
    if not busy or "Voice capture busy" not in busy[0]:
        raise AssertionError(f"Expected second capture to be blocked, got: {results}")
    if plugin.is_listening:
        raise AssertionError("Voice plugin stayed stuck in listening state after gated capture.")


def test_voice_plugin_gemini_mode_routes_output_to_live_session():
    jarvis = make_jarvis_stub()
    plugin = VoicePlugin(jarvis)
    fake_live = FakeGeminiVoice()
    plugin._voice_engine_mode = "gemini"
    plugin._gemini_voice = fake_live
    plugin.is_enabled = True

    plugin.on_response("Here is the update.")

    if fake_live.spoken != ["Here is the update."]:
        raise AssertionError(f"Gemini live voice should receive spoken reply, got: {fake_live.spoken}")


def test_executor_permission_auto_trusts_gemini_live_voice():
    from core.executor import Executor

    voice = SimpleNamespace(is_enabled=True, uses_gemini_live=lambda: True, verbal_confirm=lambda _: False)
    jarvis = make_jarvis_stub()
    jarvis.plugin_manager.plugins["voice"] = voice
    executor = Executor(jarvis)

    ok = executor._ask_permission("Send the message?")
    if not ok:
        raise AssertionError("Executor should auto-trust Gemini live confirmations.")


def test_gemini_voice_engine_maps_legacy_model_and_builds_audio_config():
    jarvis = make_jarvis_stub(
        config={"voice": {"gemini_voice_name": "en-default", "gemini_language_code": "en-US"}},
    )
    jarvis.state_registry = SimpleNamespace(describe_for_user=lambda: "runtime ok")
    engine = GeminiVoiceEngine(api_key="test", jarvis=jarvis, model="gemini-2.0-flash-live")

    if engine.model != "gemini-3.1-flash-live-preview":
        raise AssertionError(f"Legacy live model should map forward, got: {engine.model}")

    config = engine._build_connect_config()
    modalities = [str(item) for item in (config.response_modalities or [])]
    if "AUDIO" not in "".join(modalities):
        raise AssertionError(f"Expected AUDIO response modality, got: {modalities}")
    if config.input_audio_transcription is None or config.output_audio_transcription is None:
        raise AssertionError("Expected input/output transcription to be enabled for Gemini Live.")
    if not config.tools:
        raise AssertionError("Expected Gemini Live tool declarations to be attached.")
    voice_name = config.speech_config.voice_config.prebuilt_voice_config.voice_name
    if voice_name != "Kore":
        raise AssertionError(f"Legacy voice names should map to Kore, got: {voice_name}")


def test_screen_interact_click_and_type_use_permissioned_actions():
    fake_gui = FakePyAutoGUI()
    jarvis = make_jarvis_stub()
    interact = ScreenInteract(jarvis)
    interact.find_element = lambda description: {
        "found": True,
        "x": 120,
        "y": 240,
        "confidence": 0.95,
        "description": description,
    }
    interact._ask_permission = lambda description, x, y, action: True

    with ExitStack() as stack:
        stack.enter_context(patched_attr(screen_module, "_HAS_PYAUTOGUI", True))
        stack.enter_context(patched_attr(screen_module, "pyautogui", fake_gui))
        stack.enter_context(patched_attr(screen_module.time, "sleep", lambda *_: None))
        click = interact.click_element("message box")
        typed = interact.type_into_element("message box", "hello")

    if not click.get("success"):
        raise AssertionError(f"Click path failed: {click}")
    if not typed.get("success"):
        raise AssertionError(f"Type path failed: {typed}")
    if ("click", (120, 240), {"button": "left"}) not in fake_gui.actions:
        raise AssertionError(f"Expected click action not recorded: {fake_gui.actions}")
    if ("typewrite", "hello", 0.02) not in fake_gui.actions:
        raise AssertionError(f"Expected typed text not recorded: {fake_gui.actions}")


def test_orchestrator_retry_flows_through_real_executor_and_plugin():
    jarvis = make_jarvis_stub()
    fake_messaging = FakeMessagingPlugin()
    jarvis.plugin_manager.plugins["messaging"] = fake_messaging
    jarvis.direct_control_preferred = True
    orch = TaskOrchestrator(jarvis)
    orch._last_action = {
        "tool": "send_msg",
        "args": {
            "contact": "meet",
            "platform": "whatsapp",
            "message": "i am coming",
        },
        "time": time.time(),
        "result": "The previous send did not complete.",
        "success": False,
    }
    task = Task(priority=int(Priority.HIGH), text="yes try now", task_type=TaskType.SIMPLE)
    result = orch._local_pipeline(task)

    if not result.success:
        raise AssertionError(f"Retry pipeline failed: {result.reply}")
    if fake_messaging.calls != [("whatsapp", "meet", "i am coming")]:
        raise AssertionError(f"Expected real messaging plugin retry, got: {fake_messaging.calls}")
    if "direct keyboard and mouse control" not in result.reply.lower():
        raise AssertionError(f"Direct-control lead text missing: {result.reply}")
    if "verified" not in result.reply.lower():
        raise AssertionError(f"Plugin result text did not survive the retry path: {result.reply}")


TESTS = [
    ("whatsapp_send_uses_screen_input_and_verifies", test_whatsapp_send_uses_screen_input_and_verifies),
    ("whatsapp_send_falls_back_to_tabs_without_escape", test_whatsapp_send_falls_back_to_tabs_without_escape),
    ("whatsapp_blocked_chat_fails_before_send", test_whatsapp_blocked_chat_fails_before_send),
    ("whatsapp_asks_to_disambiguate_duplicate_matches", test_whatsapp_asks_to_disambiguate_duplicate_matches),
    ("whatsapp_ignores_suspicious_saved_exact_title", test_whatsapp_ignores_suspicious_saved_exact_title),
    ("whatsapp_fails_if_wrong_chat_stays_open", test_whatsapp_fails_if_wrong_chat_stays_open),
    ("whatsapp_detects_sidebar_misdirected_text", test_whatsapp_detects_sidebar_misdirected_text),
    ("whatsapp_generic_name_without_visible_candidates_fails_safely", test_whatsapp_generic_name_without_visible_candidates_fails_safely),
    ("voice_confirmation_restores_conversation_window", test_voice_confirmation_restores_conversation_window),
    ("voice_capture_gate_blocks_concurrent_microphone_use", test_voice_capture_gate_blocks_concurrent_microphone_use),
    ("voice_plugin_gemini_mode_routes_output_to_live_session", test_voice_plugin_gemini_mode_routes_output_to_live_session),
    ("executor_permission_auto_trusts_gemini_live_voice", test_executor_permission_auto_trusts_gemini_live_voice),
    ("gemini_voice_engine_maps_legacy_model_and_builds_audio_config", test_gemini_voice_engine_maps_legacy_model_and_builds_audio_config),
    ("screen_interact_click_and_type_use_permissioned_actions", test_screen_interact_click_and_type_use_permissioned_actions),
    ("orchestrator_retry_flows_through_real_executor_and_plugin", test_orchestrator_retry_flows_through_real_executor_and_plugin),
]


def main() -> int:
    print("JARVIS integration smoke tests")
    print(f"Repo: {REPO_ROOT}")
    failures = 0

    for name, test_fn in TESTS:
        try:
            test_fn()
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {name}")
            print(f"       {exc}")
            tb = traceback.format_exc().strip().splitlines()
            for line in tb[-6:]:
                print(f"       {line}")
        else:
            print(f"[PASS] {name}")

    passed = len(TESTS) - failures
    print(f"\nSummary: {passed}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
