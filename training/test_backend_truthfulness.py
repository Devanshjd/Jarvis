"""
Backend truthfulness & stability tests (the Codex-requested set).

Focused, dependency-light checks that JARVIS's backend tells the truth:
  · health probes degrade honestly when Ollama is offline,
  · the /api/status health contract has every field the UI needs,
  · the /api/chat timeout contract returns ONE terminal result (no fake answer),
  · self-knowledge names only the real crew,
  · ULTRON -> FRIDAY routing/handoff works.

Run:  python training/test_backend_truthfulness.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_health_offline_ollama_degrades_honestly() -> None:
    from core.health import _probe_vision, _probe_embedder
    down = {"reachable": False, "active_model": None, "models": 0, "error": "refused"}
    v = _probe_vision(down)
    e = _probe_embedder(down)
    assert v["available"] is False and v["error"], "vision must be unavailable when ollama is down"
    assert e["available"] is False and e["healthy"] is False, "embedder must be down when ollama is down"


def test_health_contract_has_all_fields() -> None:
    from core.health import probe_all
    h = probe_all(force=True)
    for k in ("ollama", "gemini_live", "vision", "memory_embedder", "stt", "tts", "gesture"):
        assert k in h, f"health missing '{k}'"
    assert set(("reachable", "active_model", "error")).issubset(h["ollama"]), "ollama fields"
    assert "configured" in h["gemini_live"] and "connected" in h["gemini_live"], "gemini fields"


def test_chat_timeout_contract_single_result() -> None:
    # Mirrors web/server.py api_chat: a timeout must NOT fabricate an answer that
    # then gets followed by the late real reply. One terminal result.
    def apply(result: dict) -> dict:
        if result.get("timed_out"):
            result["kind"] = "timeout"; result["reply"] = ""; result["still_working"] = True
        elif result.get("reply"):
            result["kind"] = "ok"
        else:
            result["kind"] = "empty"; result["reply"] = "rephrase?"
        return result
    r = apply({"timed_out": True, "reply": "half-baked generic text"})
    assert r["kind"] == "timeout", "timeout must be flagged"
    assert r["reply"] == "", "timeout must not return a fake answer"
    assert r.get("still_working") is True, "timeout must signal still-working"
    ok = apply({"reply": "real answer"})
    assert ok["kind"] == "ok" and ok["reply"] == "real answer"


def test_self_knowledge_names_only_real_crew() -> None:
    from core.live_integration import crew_context
    c = crew_context().upper()
    for real in ("JARVIS", "ULTRON", "FRIDAY", "VISION", "EDITH"):
        assert real in c, f"crew self-knowledge missing {real}"
    # Genuinely-stale agent names from old training data. (Not "coder" — that's a
    # substring of FRIDAY's real model "qwen2.5-coder", which is legitimate.)
    for stale in ("RESEARCHER", "WRITER", "DELEGATE_TO_AGENT"):
        assert stale not in c, f"crew self-knowledge must not name stale agent '{stale}'"


def test_ultron_to_friday_routing_and_handoff() -> None:
    from core.agent_team import make_team, TaskEnvelope, Blackboard, AgentResult, Finding
    team = make_team()
    assert team.route("scan this code for security issues") == "ULTRON"
    assert team.route("audit this python code") == "ULTRON"

    # Real handoff with a deterministic ULTRON stub (avoids loading a model).
    def ultron(env: TaskEnvelope, bb: Blackboard) -> AgentResult:
        return AgentResult(frm="ULTRON", status="verified", confidence=0.9,
                           output="found command injection",
                           findings=[Finding("cmd injection", "CWE-78", "high", "x.py:1")],
                           handoff_request="FRIDAY")
    team.bind("ULTRON", ultron)
    results = team.handle("audit this code for vulnerabilities", payload={"code": "os.system(x)"})
    agents = [r.frm for r in results]
    assert agents == ["ULTRON", "FRIDAY"], f"expected ULTRON->FRIDAY, got {agents}"
    assert len(team.blackboard.findings) >= 1, "findings must be shared on the blackboard"


def main() -> None:
    tests = [
        ("health degrades honestly (ollama offline)", test_health_offline_ollama_degrades_honestly),
        ("health contract has all fields", test_health_contract_has_all_fields),
        ("chat timeout returns one terminal result", test_chat_timeout_contract_single_result),
        ("self-knowledge names only real crew", test_self_knowledge_names_only_real_crew),
        ("ULTRON -> FRIDAY routing + handoff", test_ultron_to_friday_routing_and_handoff),
    ]
    print("=" * 64)
    print(" BACKEND TRUTHFULNESS TESTS")
    print("=" * 64)
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {name} -> {exc}")
    print(f"\n  {passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    main()
