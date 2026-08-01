"""
Persona v1 tests — one honest personality + facts-only owner memory.

The load-bearing checks: the persona prompt always carries the never-pretend
honesty rule; owner memory stores only what it was told (no invented preferences);
and the "what I'm doing" line reflects the real activity state.

Run:  python training/test_persona.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.persona import (Preferences, default_config, load_persona_config,
                          persona_prompt, persona_status, truthful_activity_line)


def _prefs(d) -> Preferences:
    return Preferences(Path(d) / "persona.json")


def test_persona_prompt_carries_the_honesty_rule() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = persona_prompt(_prefs(d), config=default_config()).lower()
    # tone (default config → concise/dry)
    assert "calm" in p and "concise" in p, "the voice/tone guide must be present"
    # the non-negotiable honesty rule
    assert "honesty" in p, "persona must state honesty is absolute"
    for phrase in ("actually performed", "never say you", "not certain", "conscious"):
        assert phrase in p, f"missing honesty guardrail: {phrase!r}"


def test_owner_memory_is_facts_only() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Preferences(Path(d) / "persona.json")
        assert p.remember("help_style", "concise, answer first") is True
        assert p.remember("help_style", "concise, answer first") is False, "dedupe"
        assert p.remember("projects", "Stormbreaker") is True
        assert p.remember("not_a_category", "x") is False, "unknown categories rejected"
        p.save()

        p2 = Preferences(Path(d) / "persona.json")             # reload
        block = p2.as_prompt()
        assert "concise, answer first" in block and "Stormbreaker" in block
        # never contains anything it wasn't told
        assert "kubernetes" not in block.lower(), "must not invent facts"

        assert p2.forget("projects", "Stormbreaker") is True
        assert "Stormbreaker" not in p2.as_prompt()


def test_empty_memory_grounds_to_nothing() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Preferences(Path(d) / "persona.json")
        assert p.as_prompt() == "", "no facts on file ⇒ no grounding block (never fabricate)"
        # persona still works, just without an owner-facts section
        assert "JARVIS" in persona_prompt(p)


def test_owner_name_fills_cleanly() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Preferences(Path(d) / "persona.json").set_owner("Dev")
        prompt = persona_prompt(p)
        assert "Dev" in prompt
        assert "{owner" not in prompt, "no unfilled template placeholders"
        # and with no owner set, still no stray placeholders
        blank = persona_prompt(Preferences(Path(d) / "empty.json"))
        assert "{owner" not in blank and "JARVIS" in blank


def test_config_defaulting_and_status() -> None:
    with tempfile.TemporaryDirectory() as d:
        cfg_path = Path(d) / ".jarvis_config.json"

        # No file → unloaded, safe defaults.
        st = persona_status(cfg_path)
        assert st["loaded"] is False
        assert st["humour"] == "dry" and st["response_style"] == "concise"

        # A real profile with an INVALID value → that key defaults, others honoured.
        cfg_path.write_text(json.dumps({"persona": {
            "humour": "off", "response_style": "detailed",
            "proactivity": "banana",           # invalid → defaults to suggest_only
            "instructions": "Prefer bullet points."}}), encoding="utf-8")
        st2 = persona_status(cfg_path)
        assert st2["loaded"] is True
        assert st2["humour"] == "off" and st2["response_style"] == "detailed"
        assert st2["proactivity"] == "suggest_only", "invalid enum must default"
        assert "instructions" not in st2, "status must not leak the free-text instructions"

        prompt = persona_prompt(_prefs(d), config=load_persona_config(cfg_path))
        assert "No jokes" in prompt, "humour=off must change the tone line"
        assert "Thorough" in prompt, "response_style=detailed must change the style line"
        assert "Prefer bullet points." in prompt, "custom instructions must be applied"
        assert "never override the honesty rule" in prompt, "instructions can't override honesty"


def test_activity_line_reflects_real_state() -> None:
    assert truthful_activity_line({"state": "idle"}) == "Right now: idle."
    line = truthful_activity_line({"state": "tool_running", "active_agent": "ULTRON",
                                   "label": "Running a security analysis"})
    assert "tool_running" in line and "ULTRON" in line and "security analysis" in line


def main() -> None:
    tests = [
        ("persona prompt carries the honesty rule", test_persona_prompt_carries_the_honesty_rule),
        ("owner memory is facts-only", test_owner_memory_is_facts_only),
        ("empty memory grounds to nothing", test_empty_memory_grounds_to_nothing),
        ("owner name fills cleanly", test_owner_name_fills_cleanly),
        ("config defaulting + PII-free status", test_config_defaulting_and_status),
        ("activity line reflects real state", test_activity_line_reflects_real_state),
    ]
    print("=" * 64)
    print(" PERSONA v1 TESTS")
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
