"""
J.A.R.V.I.S — Live Integration  (the switch that wires the crew into the brain)

Everything the multi-agent architecture built (vault memory, the specialists,
EDITH, the escalation ladder) is additive and safe. This module is the single
opt-in switch that makes JARVIS's MAIN chat actually use it.

    JARVIS_TEAM=1   →  on
    (unset/0)       →  off — the default experience is completely unchanged.

Every function here is defensive: if the flag is off, or anything errors, it
returns an empty/neutral result so the normal pipeline is never affected.
"""
from __future__ import annotations

import os
from typing import Optional


def team_enabled() -> bool:
    """Master switch. Also honoured by the security-specialist routing so one
    flag turns the whole crew on."""
    return os.environ.get("JARVIS_TEAM", "").strip().lower() in ("1", "true", "yes", "on")


_CREW = (
    "[YOUR CREW — you are JARVIS, orchestrator of a local multi-agent team. "
    "When asked which agents / specialists you have, name ONLY these four; you "
    "have no other agents:\n"
    "- ULTRON: cybersecurity analyst (Foundation-Sec-8B) — vuln analysis, exact "
    "CWE, CVSS, Bandit code scans.\n"
    "- FRIDAY: code & dev (qwen2.5-coder) — code review, fixes, the Code Oracle.\n"
    "- VISION: perception (moondream) — reads your screen and camera, gestures, "
    "Face ID.\n"
    "- EDITH: improvement & oversight — learns from mistakes and proposes "
    "sandbox-gated upgrades.\n"
    "You route work to them and they share a blackboard.]"
)


def crew_context() -> str:
    """JARVIS's accurate self-knowledge of its crew — so it never confabulates
    old agent names (coder/researcher/...). Always on: the crew EXISTS (reachable
    via /api/team/route) even when auto-dispatch is off, so naming them is honest.
    The JARVIS_TEAM flag only controls automatic dispatch, not self-knowledge."""
    return _CREW


def recall_context(text: str, k: int = 2) -> str:
    """Pull relevant knowledge from the Obsidian vault to ground the answer.
    Returns a context block for the system prompt, or '' (flag off / no hits /
    error). This is what makes JARVIS actually USE its memory in conversation."""
    if not team_enabled():
        return ""
    try:
        from core.vault import Vault
        return Vault().recall(text, k=k) or ""
    except Exception:
        return ""


def run_edith(apply_green: bool = False) -> dict:
    """Run one EDITH improvement pass on demand (observe → propose → decide).
    apply_green=False by default: it reports what it WOULD do without writing,
    so an API call can't spam the vault with lesson stubs."""
    try:
        from core.edith import Edith
        return Edith().run_once(apply_green=apply_green)
    except Exception as exc:
        return {"error": str(exc)}


def escalate(problem: str, context: str = "", allow_cloud: bool = False) -> dict:
    """Run a problem up the escalation ladder. Web-search rung is backed by the
    local research tool when available; cloud rung stays opt-in + scrubbed."""
    try:
        from core.escalation import Escalator, EscalationConfig

        def web_search(p: str, _c: str) -> Optional[str]:
            try:
                from core.web_research import get_researcher
                results = get_researcher().search_web(p, num_results=3) or []
                snips = [f"{r.get('title','')} — {r.get('snippet','')}".strip(" —")
                         for r in results[:3] if r.get('title') or r.get('snippet')]
                joined = " | ".join(s for s in snips if s)
                return joined[:500] if joined else None
            except Exception:
                return None

        esc = Escalator(EscalationConfig(allow_cloud=allow_cloud),
                        handlers={"web_search": web_search})
        r = esc.escalate(problem, context)
        return {"solved": r.solved, "rung": r.rung.value,
                "answer": r.answer, "trail": r.trail}
    except Exception as exc:
        return {"error": str(exc)}
