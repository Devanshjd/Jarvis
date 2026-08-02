"""
Proactive voice-routing tests — safe, narrow voice control of consent.

The load-bearing one is NEVER-SILENTLY-ENABLE: a spoken command only proposes;
the consent flips only after an explicit "yes". Plus: deterministic parsing,
negation cancels, a stale pending can't linger, and it expires.

Run:  python training/test_proactive_voice.py
"""
from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.proactive_signals import Consent
from core.proactive_voice import _pending, parse_consent_command, route_utterance


def _consent(d) -> Consent:
    _pending.clear()                       # reset the module-level pending each test
    return Consent(Path(d) / "proactive.json")


def test_parse_is_deterministic_and_narrow() -> None:
    assert parse_consent_command("turn on battery suggestions") == {"source": "battery", "state": True}
    assert parse_consent_command("disable screen error alerts") == {"source": "screen_errors", "state": False}
    assert parse_consent_command("turn off battery") == {"source": "battery", "state": False}
    # ambiguous / not a command → None (never acts on a guess)
    for junk in ("what's my battery level", "turn on the lights", "battery",
                 "enable and disable battery", ""):
        assert parse_consent_command(junk) is None, junk


def test_never_silently_enables() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d)
        r = route_utterance("turn on battery suggestions", c)
        assert r["handled"] and r["kind"] == "confirm"
        assert r["source"] == "battery" and r["state"] is True
        assert "say yes" in r["reply"].lower()
        assert c.enabled("battery") is False, "the command alone must NOT enable it"
        assert not (Path(d) / "proactive.json").exists(), "nothing written before a yes"


def test_yes_confirms_and_persists() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d)
        route_utterance("turn on battery suggestions", c)      # propose
        r = route_utterance("yes", c)                          # confirm
        assert r["kind"] == "applied" and r["source"] == "battery" and r["state"] is True
        assert c.enabled("battery") is True
        assert Consent(Path(d) / "proactive.json").enabled("battery") is True, "must persist"


def test_no_cancels_and_leaves_it_off() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d)
        route_utterance("turn on battery", c)
        r = route_utterance("nope", c)
        assert r["kind"] == "cancelled" and c.enabled("battery") is False


def test_yes_without_a_pending_is_ignored() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d)
        assert route_utterance("yes", c)["handled"] is False, "a bare yes ⇒ normal chat"


def test_unrelated_utterance_drops_the_pending() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d)
        route_utterance("turn on battery", c)                  # pending
        assert route_utterance("what time is it", c)["handled"] is False
        # the stale change must not survive to a later 'yes'
        assert route_utterance("yes", c)["handled"] is False
        assert c.enabled("battery") is False


def test_pending_expires() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d)
        route_utterance("turn on battery", c)
        _pending._at = 0.0                                     # force TTL expiry
        assert route_utterance("yes", c)["handled"] is False
        assert c.enabled("battery") is False


def main() -> None:
    tests = [
        ("parse is deterministic + narrow", test_parse_is_deterministic_and_narrow),
        ("NEVER silently enables", test_never_silently_enables),
        ("yes confirms and persists", test_yes_confirms_and_persists),
        ("no cancels, leaves it off", test_no_cancels_and_leaves_it_off),
        ("bare yes is ignored", test_yes_without_a_pending_is_ignored),
        ("unrelated utterance drops pending", test_unrelated_utterance_drops_the_pending),
        ("pending expires", test_pending_expires),
    ]
    print("=" * 64)
    print(" PROACTIVE VOICE-ROUTING TESTS")
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
