"""
Desktop-control safety tests — the gates on JARVIS driving keyboard/mouse.

These NEVER move the real mouse or type for real: the primitive `_do` and the
window-title probe are stubbed. What they prove is the safety model:
  · OFF by default — refuses until enabled,
  · a session must be scoped to one app (no unscoped control),
  · credentials / financial / CAPTCHA actions are hard-blocked even when approved,
  · typing FAILS CLOSED when the active window isn't the approved app,
  · an allowed action runs, is verified, and is audited,
  · Stop ends the session immediately.

Run:  python training/test_desktop_control.py
"""
from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.desktop_control as dc
from core.desktop_control import DesktopController


def _fresh(tmp: Path, *, enabled=True, scope="notepad",
           title="Untitled - Notepad") -> DesktopController:
    """A controller wired for a hermetic test: audit to a temp file, primitives
    stubbed so nothing real happens, and (optionally) an active scoped session."""
    dc._AUDIT = tmp / "audit.jsonl"                       # don't touch the real log
    c = DesktopController()
    c._enabled = enabled
    c._do = lambda action: {"stub": True, "action": action["action"]}  # no real input
    c._snapshot_title = lambda: title
    c._focused_is_password = lambda: False
    if enabled and scope:
        c.start_session("do a thing", scope, ttl=120)
    return c


def test_off_by_default_refuses() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _fresh(Path(d), enabled=False, scope=None)
        assert "error" in c.start_session("x", "notepad"), "disabled must refuse a session"
        assert c.execute({"action": "type_text", "text": "hi"}).get("refused"), \
            "disabled must refuse actions"


def test_session_must_be_app_scoped() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _fresh(Path(d), scope=None)          # enabled, no session yet
        assert "error" in c.start_session("type notes", ""), \
            "an unscoped session must be refused"
        assert "session" in c.start_session("type notes", "notepad"), \
            "a scoped session is allowed"


def test_propose_is_deterministic() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _fresh(Path(d))
        p = c.propose("Open Notepad and type: JARVIS desktop-control test")
        kinds = [a["action"] for a in p["actions"]]
        assert kinds == ["open_app", "focus", "type_text"], kinds
        assert p["actions"][-1]["text"].startswith("JARVIS desktop-control test")
        assert c.propose("open calc")["actions"][0]["action"] == "open_app"
        assert c.propose("do something vague")["actions"] == []   # nothing to run


def test_credentials_are_hard_blocked() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _fresh(Path(d))
        called = {"n": 0}
        c._do = lambda a: called.__setitem__("n", called["n"] + 1) or {"stub": True}
        for text in ("my password is hunter2", "the OTP is 448291", "card number 4111..."):
            r = c.execute({"action": "type_text", "text": text})
            assert r.get("blocked"), (text, r)
        assert called["n"] == 0, "a blocked action must never reach the primitive"


def test_financial_and_captcha_blocked() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _fresh(Path(d))
        assert c.execute({"action": "click", "target": "Buy now"}).get("blocked")
        assert c.execute({"action": "click", "target": "confirm order"}).get("blocked")
        assert c.execute({"action": "click", "target": "I'm not a robot"}).get("blocked")


def test_typing_fails_closed_outside_scope() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _fresh(Path(d), title="Google Chrome")        # scope is notepad
        assert c.execute({"action": "type_text", "text": "hi"}).get("refused"), \
            "typing into the wrong window must be refused"
        c._snapshot_title = lambda: ""                     # can't confirm window
        assert c.execute({"action": "type_text", "text": "hi"}).get("refused"), \
            "unknown active window must fail closed"


def test_allowed_action_runs_and_is_audited() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        c = _fresh(tmp)                                    # active Notepad window
        r = c.execute({"action": "type_text", "text": "hello world"})
        assert r["ok"] is True and r["result"]["stub"] is True, r
        assert r["verify"]["after_window"] == "Untitled - Notepad"
        assert c.status()["recent"], "the action must be recorded"
        assert (tmp / "audit.jsonl").exists(), "an audit line must be written"


def test_unknown_action_refused() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _fresh(Path(d))
        assert c.execute({"action": "rm_rf_everything"}).get("refused")


def test_stop_ends_session() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _fresh(Path(d))
        assert c.stop()["stopped"] is True
        assert c.execute({"action": "observe"}).get("refused"), \
            "after Stop, actions must be refused"


def test_raw_input_gate_closes_the_hole() -> None:
    # The legacy executor input tools now defer to THIS: no armed session ⇒ no
    # raw keyboard/mouse, regardless of any voice session.
    with tempfile.TemporaryDirectory() as d:
        dc._AUDIT = Path(d) / "audit.jsonl"
        c = DesktopController()
        c._enabled = False
        assert c.raw_input_allowed() is False, "disabled ⇒ no raw input"
        c._enabled = True
        assert c.raw_input_allowed() is False, "enabled but no session ⇒ still no raw input"
        c.start_session("type a note", "notepad", ttl=120)
        assert c.raw_input_allowed() is True, "armed scoped session ⇒ raw input allowed"


# ── browser coordinator gates (fake driver — no real Chromium) ────────────
class _FakeBrowser:
    def __init__(self) -> None:
        self.url = "https://jobs.example.com/"
        self.calls: list = []

    def current(self): return {"url": self.url, "title": "Example"}
    def navigate(self, url): self.url = url; self.calls.append(("navigate", url)); return {"url": url}
    def extract(self): self.calls.append(("extract",)); return {"url": self.url, "elements": []}
    def click(self, sel): self.calls.append(("click", sel)); return {"clicked": sel}
    def fill(self, sel, text): self.calls.append(("fill", sel, text)); return {"filled": sel}
    def select(self, sel, val): return {"selected": val}
    def upload(self, sel, path): return {"uploaded": path}
    def screenshot(self): return {"b64": "x"}
    def close(self): self.calls.append(("close",))


def _browser_controller(tmp: Path, origins=("https://jobs.example.com",)) -> DesktopController:
    dc._AUDIT = tmp / "audit.jsonl"
    c = DesktopController()
    c._enabled = True
    c.start_session("apply to jobs", app_scope="", ttl=120, origins=list(origins))
    c._browser = _FakeBrowser()          # inject so no real Chromium launches
    return c


def test_browser_navigate_enforces_allowlist() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _browser_controller(Path(d))
        off = c.execute({"action": "navigate", "url": "https://evil.example.net/x"})
        assert off.get("refused"), off
        assert c._browser.calls == [], "an off-allowlist origin must never reach the driver"
        ok = c.execute({"action": "navigate", "url": "https://jobs.example.com/search"})
        assert ok["ok"] is True, ok


def test_browser_extract_is_read_only_and_allowed() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _browser_controller(Path(d))
        r = c.execute({"action": "extract"})
        assert r["ok"] and "elements" in r["result"], r


def test_browser_submission_needs_explicit_confirm() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _browser_controller(Path(d))
        blocked = c.execute({"action": "click_dom", "selector": "button#submit", "submit": True})
        assert blocked.get("blocked"), "a submission must be refused without confirm"
        ok = c.execute({"action": "click_dom", "selector": "button#submit",
                        "submit": True, "confirm": True})
        assert ok["ok"] is True, ok


def test_browser_credential_text_blocked() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _browser_controller(Path(d))
        r = c.execute({"action": "fill", "selector": "#pw", "text": "my password is x"})
        assert r.get("blocked"), r


def test_browser_actions_need_a_session_allowlist() -> None:
    with tempfile.TemporaryDirectory() as d:
        dc._AUDIT = Path(d) / "audit.jsonl"
        c = DesktopController()
        c._enabled = True
        c.start_session("type notes", "notepad", ttl=120)      # native-only, no origins
        r = c.execute({"action": "navigate", "url": "https://jobs.example.com"})
        assert r.get("refused"), "a native-only session can't drive the browser"


def main() -> None:
    tests = [
        ("off by default refuses", test_off_by_default_refuses),
        ("session must be app-scoped", test_session_must_be_app_scoped),
        ("propose is deterministic", test_propose_is_deterministic),
        ("credentials hard-blocked", test_credentials_are_hard_blocked),
        ("financial + CAPTCHA blocked", test_financial_and_captcha_blocked),
        ("typing fails closed outside scope", test_typing_fails_closed_outside_scope),
        ("allowed action runs + audited", test_allowed_action_runs_and_is_audited),
        ("unknown action refused", test_unknown_action_refused),
        ("stop ends session", test_stop_ends_session),
        ("raw-input gate closes the hole", test_raw_input_gate_closes_the_hole),
        ("browser navigate enforces allowlist", test_browser_navigate_enforces_allowlist),
        ("browser extract read-only allowed", test_browser_extract_is_read_only_and_allowed),
        ("browser submission needs confirm", test_browser_submission_needs_explicit_confirm),
        ("browser credential text blocked", test_browser_credential_text_blocked),
        ("browser needs session allowlist", test_browser_actions_need_a_session_allowlist),
    ]
    print("=" * 64)
    print(" DESKTOP-CONTROL SAFETY TESTS")
    print("=" * 64)
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as exc:
            import traceback
            print(f"  [FAIL] {name} -> {exc}")
            traceback.print_exc()
    print(f"\n  {passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    main()
