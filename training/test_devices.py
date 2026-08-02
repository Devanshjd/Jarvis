"""
Device-pairing tests — reach the brain from a phone, safely.

The load-bearing one is SCOPE: a paired phone token may reach chat/status/voice
and nothing else — never desktop control, terminal, self-modify, or device
management. Plus the pairing lifecycle (one-time code, TTL) and revocation.

Run:  python training/test_devices.py
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.devices import DeviceRegistry, device_scope_allows, remote_enabled


def _reg(d) -> DeviceRegistry:
    return DeviceRegistry(Path(d) / "devices.json")


def test_remote_off_by_default() -> None:
    os.environ.pop("JARVIS_REMOTE", None)
    assert remote_enabled() is False
    os.environ["JARVIS_REMOTE"] = "1"
    assert remote_enabled() is True
    os.environ.pop("JARVIS_REMOTE", None)


def test_pairing_lifecycle_and_one_time_code() -> None:
    with tempfile.TemporaryDirectory() as d:
        reg = _reg(d)
        code = reg.start_pairing()["code"]
        assert len(code) == 6 and code.isdigit()
        paired = reg.complete_pairing(code, "Pixel")
        assert paired and paired["device_id"] and paired["device_token"]
        assert paired["scope"] == "phone"
        # the token authenticates back to the device
        dev = reg.authenticate(paired["device_token"])
        assert dev and dev["name"] == "Pixel" and dev["enabled"] is True
        # the code is single-use
        assert reg.complete_pairing(code, "again") is None, "code must not be reusable"


def test_pair_start_returns_a_real_future_expiry() -> None:
    from datetime import datetime, timezone
    with tempfile.TemporaryDirectory() as d:
        started = _reg(d).start_pairing()
        exp = datetime.fromisoformat(started["expires_at"])
        now = datetime.now(timezone.utc)
        delta = (exp - now).total_seconds()
        assert 60 < delta <= 300 + 5, f"expires_at must be ~5 min in the FUTURE, got {delta}s"
        assert started["ttl_seconds"] == 300


def test_wrong_and_expired_codes_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        reg = _reg(d)
        code = reg.start_pairing()["code"]
        wrong = "000000" if code != "000000" else "111111"
        assert reg.complete_pairing(wrong, "x") is None, "a wrong code is rejected"
        # force expiry
        reg.start_pairing()
        reg._pending["expiry"] = time.time() - 1
        assert reg.complete_pairing(reg._pending["code"], "x") is None, "expired code rejected"


def test_brute_force_burns_the_code() -> None:
    with tempfile.TemporaryDirectory() as d:
        reg = _reg(d)
        code = reg.start_pairing()["code"]
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):                                   # _MAX_CODE_FAILS
            assert reg.complete_pairing(wrong, "x", source="atk") is None
        # the code is BURNED — even the CORRECT code no longer works
        assert reg.complete_pairing(code, "x", source="atk") is None, \
            "5 wrong guesses must burn the code (brute-force defence)"
        # a fresh code still pairs (this source isn't cooled down yet)
        code2 = reg.start_pairing()["code"]
        assert reg.complete_pairing(code2, "phone", source="atk"), "a new code pairs"


def test_source_cooldown_after_repeated_failures() -> None:
    with tempfile.TemporaryDirectory() as d:
        reg = _reg(d)
        for _ in range(8):                                   # _MAX_SOURCE_FAILS
            reg._note_fail("bot")
        assert reg._throttled("bot") is True
        code = reg.start_pairing()["code"]
        assert reg.complete_pairing(code, "x", source="bot") is None, \
            "a cooled-down source can't pair even with a valid code"
        # a different source is unaffected by the bot's lockout
        assert reg.complete_pairing(code, "phone", source="clean") is not None, \
            "the lockout is per-source, not global"


def test_phone_scope_allows_only_safe_endpoints() -> None:
    phone = {"scope": "phone"}
    for ok in ("/api/chat", "/api/status", "/api/history", "/api/token/health",
               "/api/voice/stop", "/api/voice/local", "/api/tts/speak",
               "/api/stt/transcribe", "/api/proactive/status"):
        assert device_scope_allows(phone, ok) is True, f"phone should reach {ok}"
    for bad in ("/api/desktop/step", "/api/terminal", "/api/self_modify/apply",
                "/api/edith/approve", "/api/agent/execute", "/api/files/read",
                "/api/security/scan", "/api/proactive/consent", "/api/proactive/voice",
                "/api/persona/remember", "/api/devices", "/api/devices/revoke"):
        assert device_scope_allows(phone, bad) is False, f"phone must NOT reach {bad}"


def test_non_phone_scope_is_denied_everything() -> None:
    assert device_scope_allows({"scope": "desktop"}, "/api/chat") is False
    assert device_scope_allows(None, "/api/chat") is False


def test_revocation_kills_the_token() -> None:
    with tempfile.TemporaryDirectory() as d:
        reg = _reg(d)
        code = reg.start_pairing()["code"]
        paired = reg.complete_pairing(code, "phone")
        tok, did = paired["device_token"], paired["device_id"]
        assert reg.authenticate(tok) is not None
        assert reg.revoke(did) is True
        assert reg.authenticate(tok) is None, "a revoked token must not authenticate"


def test_unknown_token_never_authenticates() -> None:
    with tempfile.TemporaryDirectory() as d:
        reg = _reg(d)
        assert reg.authenticate("not-a-real-token") is None
        assert reg.authenticate("") is None


def main() -> None:
    tests = [
        ("remote off by default", test_remote_off_by_default),
        ("pairing lifecycle + one-time code", test_pairing_lifecycle_and_one_time_code),
        ("pair/start returns a real future expiry", test_pair_start_returns_a_real_future_expiry),
        ("wrong/expired codes rejected", test_wrong_and_expired_codes_are_rejected),
        ("brute-force burns the code", test_brute_force_burns_the_code),
        ("source cooldown after repeated failures", test_source_cooldown_after_repeated_failures),
        ("phone scope allows only safe endpoints", test_phone_scope_allows_only_safe_endpoints),
        ("non-phone scope denied everything", test_non_phone_scope_is_denied_everything),
        ("revocation kills the token", test_revocation_kills_the_token),
        ("unknown token never authenticates", test_unknown_token_never_authenticates),
    ]
    print("=" * 64)
    print(" DEVICE-PAIRING TESTS")
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
