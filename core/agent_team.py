"""
J.A.R.V.I.S — Agent Team  (multi-agent scaffold, Phase 1)

Formalizes the crew — JARVIS · ULTRON · FRIDAY · VISION · EDITH — as declared
agents that communicate through a typed protocol and a shared blackboard.

This is the backbone the architecture calls "how they talk":
  · Dispatch   — JARVIS routes a request to the right specialist by intent.
  · Handoff    — a specialist can request another ("bring in FRIDAY") and the
                 team honours it, mediated by the hub (never a direct mesh).
  · Blackboard — every agent reads/writes one shared memory, so continuity
                 survives model swaps and EDITH can watch the whole team by
                 watching the board.

It is ADDITIVE and standalone: the existing orchestrator keeps working. Each
agent's real execution is a pluggable handler — in the running system JARVIS
binds a handler to the agent's model + tools; in tests we pass mock handlers.
Run `python core/agent_team.py` for a live smoke test of a routed Ultron→FRIDAY
handoff with the full blackboard trail.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional


# ═══════════════════════════════════════════════════════════════════════
#  Agent manifest — a specialist is a brain + a toolkit + a trigger, not a
#  system prompt in a mask.
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Agent:
    name: str                       # ULTRON, FRIDAY, ...
    role: str                       # one-line human description
    model: str                      # ollama tag, "cloud", or "" for hub/tool-only
    domains: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    trigger: Optional[re.Pattern] = None   # intent match on the raw request
    resident: bool = False          # stays warm in VRAM (small models / the hub)
    slow: bool = False              # heavyweight — spills past 8GB, on-demand only

    def matches(self, text: str) -> bool:
        return bool(self.trigger and self.trigger.search(text or ""))


# Intent triggers. Kept specific so ordinary chat falls through to JARVIS.
_SECURITY = re.compile(
    r"\b(?:vulnerab\w*|cve-?\d|cwe-?\d|cvss|owasp|mitre|exploit\w*|payload|"
    r"sql\s*injection|sqli|xss|csrf|ssrf|idor|xxe|rce|lfi|ssti|"
    r"privilege\s+escalation|privesc|command\s+injection|deserializ\w*|"
    r"phishing|malware|ransomware|pentest|penetration\s+test|recon|nmap|"
    r"port\s+scan|security\s+(?:audit|risk|flaw|assessment|review|issue|problem|"
    r"weakness|concern|bug|hole|check|scan)|"
    r"(?:security[- ]?)?(?:scan|audit)\s+(?:this\s+|the\s+|my\s+)?(?:code|file|repo|script)|"
    r"is\s+this\s+(?:code\s+)?vulnerable|hardcoded\s+secret)\b", re.I)

_CODE = re.compile(
    r"\b(?:refactor|debug|write\s+(?:a\s+)?(?:function|class|test|script)|"
    r"code\s+review|review\s+(?:this\s+|the\s+)?code|implement|fix\s+the\s+bug|"
    r"stack\s+trace|unit\s+test|regex|dependency|import\s+error|"
    r"add\s+(?:a\s+)?(?:function|method|endpoint)|optimize\s+(?:this|the))\b", re.I)

_VISION = re.compile(
    r"\b(?:on\s+(?:my|the|this)\s+screen|read\s+(?:my|the)\s+screen|"
    r"look\s+at\s+(?:my|the|this)\s+(?:screen|camera|image|picture|photo)|"
    r"what\s+(?:do\s+you\s+see|am\s+i\s+(?:holding|showing))|"
    r"what\s+is\s+(?:on|in)\s+(?:my\s+|the\s+|this\s+)?"
    r"(?:screen|image|picture|photo|frame|camera|view|webcam)|"
    r"describe\s+(?:the\s+|this\s+|my\s+)?(?:screen|image|picture|scene|photo)|"
    r"\bcamera\b|webcam|recognize\s+(?:me|my\s+face)|"
    r"screenshot\s+and\s+(?:read|describe))\b", re.I)

_IMPROVE = re.compile(
    r"\b(?:improve\s+yourself|self[-\s]?improve|learn\s+from\s+(?:your\s+)?mistakes|"
    r"upgrade\s+the\s+(?:team|system)|why\s+did\s+you\s+(?:fail|get\s+it\s+wrong)|"
    r"run\s+the\s+(?:reliability|security)\s+(?:pass|harness)|audit\s+your\s+own)\b", re.I)


def default_roster() -> dict[str, Agent]:
    """The five-agent crew from the architecture, best-effort mapped to the
    models actually installed on this box."""
    return {
        "JARVIS": Agent(
            name="JARVIS", role="Orchestrator & all-rounder",
            model="gemma3:4b", domains=["general", "desktop", "conversation"],
            tools=["files", "web", "voice", "gui_control"],
            trigger=None, resident=True),
        "ULTRON": Agent(
            name="ULTRON", role="Cybersecurity analyst",
            model="axonvertex/Foundation-Sec-8B-Reasoning-Q8_0-GGUF:Q8_0_24K",
            domains=["security", "recon", "vuln-analysis"],
            tools=["semgrep", "cvss", "cwe_lookup", "recon", "sandbox"],
            trigger=_SECURITY, slow=True),
        "FRIDAY": Agent(
            name="FRIDAY", role="Code & dev",
            model="qwen2.5-coder:7b", domains=["code", "dev", "refactor"],
            tools=["code_oracle", "semgrep", "self_improve", "sandbox"],
            trigger=_CODE),
        "VISION": Agent(
            name="VISION", role="Perception",
            model="moondream:latest", domains=["vision", "screen", "camera"],
            tools=["screen_ocr", "face_id", "gesture"],
            trigger=_VISION, resident=True),
        "EDITH": Agent(
            name="EDITH", role="Improvement & oversight",
            model="", domains=["meta", "evaluation", "self-improvement"],
            tools=["learning_log", "sandbox", "promptfoo", "proposer", "vault"],
            trigger=_IMPROVE),
    }


# ═══════════════════════════════════════════════════════════════════════
#  The typed protocol — the "how they talk" contract.
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TaskEnvelope:
    """JARVIS → specialist."""
    goal: str
    to: str = "JARVIS"
    intent: str = "answer"                # answer | audit | fix | perceive | improve
    frm: str = "JARVIS"
    context_refs: list[str] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)   # scope, gate, budget
    payload: dict = field(default_factory=dict)       # inline data, e.g. {"code": ...}
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class Finding:
    what: str
    cwe: str = ""
    severity: str = ""
    location: str = ""


@dataclass
class AgentResult:
    """specialist → JARVIS."""
    frm: str
    status: str = "verified"              # verified | failed | needs_input
    output: str = ""
    findings: list[Finding] = field(default_factory=list)
    confidence: float = 0.0
    handoff_request: str = ""             # e.g. "FRIDAY" — mediated by the hub
    citations: list[str] = field(default_factory=list)
    envelope_id: str = ""


# ═══════════════════════════════════════════════════════════════════════
#  The blackboard — one shared memory. Watching it == watching the team.
# ═══════════════════════════════════════════════════════════════════════

class Blackboard:
    def __init__(self) -> None:
        self.mission: str = ""
        self.findings: list[Finding] = []
        self.events: list[dict] = []      # the audit trail EDITH & you can read

    def set_mission(self, goal: str) -> None:
        self.mission = goal
        self.log("JARVIS", "mission", goal)

    def add_findings(self, agent: str, findings: list[Finding]) -> None:
        self.findings.extend(findings)
        for f in findings:
            self.log(agent, "finding", f"{f.cwe or '—'} {f.what} @ {f.location or '—'}")

    def log(self, agent: str, kind: str, detail: str) -> None:
        self.events.append({
            "t": round(time.time(), 3), "agent": agent, "kind": kind, "detail": detail,
        })

    def trail(self) -> list[str]:
        return [f"[{e['agent']:<7}] {e['kind']:<8} {e['detail']}" for e in self.events]


# ═══════════════════════════════════════════════════════════════════════
#  The team — dispatch, run, and honour handoffs (all mediated by the hub).
# ═══════════════════════════════════════════════════════════════════════

AgentHandler = Callable[[TaskEnvelope, Blackboard], AgentResult]


class AgentTeam:
    def __init__(self, roster: Optional[dict[str, Agent]] = None) -> None:
        self.roster = roster or default_roster()
        self.blackboard = Blackboard()
        self._handlers: dict[str, AgentHandler] = {}

    def bind(self, name: str, handler: AgentHandler) -> None:
        """Attach an agent's real execution (model + tools). In production JARVIS
        binds these; tests bind mocks."""
        self._handlers[name.upper()] = handler

    def route(self, text: str) -> str:
        """Pick the specialist for a request. Specific triggers win; anything
        unclaimed stays with JARVIS (the all-rounder is the safe default)."""
        for name, agent in self.roster.items():
            if name == "JARVIS":
                continue
            if agent.matches(text):
                return name
        return "JARVIS"

    def handle(self, text: str, *, payload: Optional[dict] = None,
               max_handoffs: int = 3) -> list[AgentResult]:
        """Route a request, run the chosen agent, and follow any handoff chain
        — always back through the hub, capped so it can't loop forever."""
        self.blackboard.set_mission(text)
        results: list[AgentResult] = []
        target = self.route(text)
        env = TaskEnvelope(goal=text, to=target, intent=self._intent_for(target),
                           payload=payload or {})

        seen = 0
        while env and seen <= max_handoffs:
            seen += 1
            self.blackboard.log("JARVIS", "dispatch", f"-> {env.to}  ({env.intent})")
            handler = self._handlers.get(env.to)
            if handler is None:
                # No specialist bound (e.g. routed to JARVIS) — in the live
                # system the orchestrator's normal reasoning handles it. Return
                # a clear result instead of an empty list.
                self.blackboard.log(env.to, "no-handler", "JARVIS / general reasoning")
                results.append(AgentResult(
                    frm=env.to, status="needs_input",
                    output=f"No specialist handler for {env.to}; handled by JARVIS."))
                break
            res = handler(env, self.blackboard)
            res.envelope_id = env.id
            self.blackboard.add_findings(res.frm, res.findings)
            self.blackboard.log(res.frm, "result",
                                f"{res.status} conf={res.confidence:.2f} :: {res.output[:60]}")
            results.append(res)

            if res.handoff_request and res.handoff_request.upper() in self.roster:
                nxt = res.handoff_request.upper()
                self.blackboard.log(res.frm, "handoff", f"requests {nxt}")
                env = TaskEnvelope(
                    goal=f"Act on {res.frm}'s findings for: {text}",
                    to=nxt, frm=res.frm, intent=self._intent_for(nxt),
                    context_refs=[f"bb://findings/{env.id}"], payload=env.payload)
            else:
                env = None
        return results

    @staticmethod
    def _intent_for(agent: str) -> str:
        return {"ULTRON": "audit", "FRIDAY": "fix",
                "VISION": "perceive", "EDITH": "improve"}.get(agent, "answer")


# ── A real, tool-backed handler ──────────────────────────────────────────

def make_security_handler() -> AgentHandler:
    """ULTRON's real handler: scan code from the envelope with Bandit (a proven
    SAST engine) instead of guessing. Hands off to FRIDAY when issues are found.
    Falls back gracefully to 'nothing to scan' if no code payload is present."""
    def handler(env: TaskEnvelope, bb: Blackboard) -> AgentResult:
        code = (env.payload or {}).get("code")
        if not code:
            return AgentResult(frm="ULTRON", status="needs_input", confidence=0.0,
                               output="No code supplied to scan.")
        try:
            try:
                from core.code_scan import scan_python
            except ImportError:
                from code_scan import scan_python  # when run as a script
            raw = scan_python(code=code)
        except Exception as exc:
            return AgentResult(frm="ULTRON", status="failed",
                               output=f"Scanner error: {exc}")
        findings = [Finding(what=f.message, cwe=f.cwe, severity=f.severity,
                            location=f"line {f.line}") for f in raw]
        if not findings:
            return AgentResult(frm="ULTRON", status="verified", confidence=0.9,
                               output="Static analysis found no issues.")
        try:                                    # ground each CWE number in its name
            try:
                from core.cwe_lookup import enrich as _cwe
            except ImportError:
                from cwe_lookup import enrich as _cwe
        except Exception:
            _cwe = lambda c: c
        top = "; ".join(f"{_cwe(f.cwe) if f.cwe else '?'} @ {f.location}"
                        for f in findings[:3])
        return AgentResult(
            frm="ULTRON", status="verified", confidence=0.9,
            output=f"Bandit found {len(findings)} issue(s): {top}",
            findings=findings, handoff_request="FRIDAY",
            citations=[f.cwe for f in findings if f.cwe])
    return handler


def make_code_handler() -> AgentHandler:
    """FRIDAY: turn ULTRON's findings into a concrete remediation plan. Drafting
    the actual patch uses the human-gated self-improve proposer (not here)."""
    def handler(env: TaskEnvelope, bb: Blackboard) -> AgentResult:
        fs = list(bb.findings)
        if not fs:
            return AgentResult(frm="FRIDAY", status="needs_input", confidence=0.0,
                               output="No findings to remediate.")
        plan = "; ".join(f"{f.location}: fix {f.cwe or f.what[:30]}" for f in fs[:4])
        return AgentResult(
            frm="FRIDAY", status="verified", confidence=0.75,
            output=f"Remediation plan for {len(fs)} finding(s): {plan}. "
                   f"Applying a patch goes through propose -> sandbox -> your approval.")
    return handler


def make_vision_handler() -> AgentHandler:
    """VISION: describe an image (screenshot / camera frame) with moondream."""
    def handler(env: TaskEnvelope, bb: Blackboard) -> AgentResult:
        img = (env.payload or {}).get("image")
        if not img:
            return AgentResult(frm="VISION", status="needs_input", confidence=0.0,
                               output="No image supplied to look at.")
        try:
            import requests
            prompt = env.goal or "Describe what you see, concisely."
            r = requests.post(
                "http://127.0.0.1:11434/api/generate",
                json={"model": "moondream:latest", "prompt": prompt,
                      "images": [img], "stream": False},
                timeout=120)
            desc = (r.json().get("response", "") or "").strip()
            return AgentResult(frm="VISION", status="verified", confidence=0.8,
                               output=desc or "(no description)")
        except Exception as exc:
            return AgentResult(frm="VISION", status="failed",
                               output=f"Vision error: {exc}")
    return handler


def make_edith_handler() -> AgentHandler:
    """EDITH: report what the crew keeps getting wrong (observe, don't apply)."""
    def handler(env: TaskEnvelope, bb: Blackboard) -> AgentResult:
        try:
            try:
                from core.edith import Edith
            except ImportError:
                from edith import Edith
            weaknesses = Edith().observe()
        except Exception as exc:
            return AgentResult(frm="EDITH", status="failed", output=f"Observe error: {exc}")
        if not weaknesses:
            return AgentResult(frm="EDITH", status="verified", confidence=0.9,
                               output="No recurring failures in the learning log.")
        top = "; ".join(f"{w.signature} (x{w.count})" for w in weaknesses[:4])
        return AgentResult(
            frm="EDITH", status="verified", confidence=0.85,
            output=f"{len(weaknesses)} recurring gap(s): {top}. "
                   f"Green fixes auto-apply after a sandbox pass; risky ones ask you.")
    return handler


def make_team() -> "AgentTeam":
    """A fully-wired crew with the real tool-backed handlers bound."""
    team = AgentTeam()
    team.bind("ULTRON", make_security_handler())
    team.bind("FRIDAY", make_code_handler())
    team.bind("VISION", make_vision_handler())
    team.bind("EDITH", make_edith_handler())
    return team


# ═══════════════════════════════════════════════════════════════════════
#  Smoke test — a real routed Ultron → FRIDAY handoff with mock handlers.
# ═══════════════════════════════════════════════════════════════════════

def _demo() -> None:
    team = AgentTeam()

    # ULTRON: the REAL Bandit-backed scanner (not a mock).
    team.bind("ULTRON", make_security_handler())

    def friday(env: TaskEnvelope, bb: Blackboard) -> AgentResult:
        locs = ", ".join(f.location for f in bb.findings) or "n/a"
        return AgentResult(
            frm="FRIDAY", status="verified", confidence=0.79,
            output=f"Drafted fixes for {len(bb.findings)} finding(s) at {locs} "
                   f"(proposed, not applied). Sandbox: syntax+import OK.")

    team.bind("FRIDAY", friday)

    vulnerable = (
        "import os, hashlib\n"
        "def run(host):\n"
        "    os.system('ping -c 1 ' + host)\n"
        "SECRET = 'hunter2'\n"
        "def h(x):\n"
        "    return hashlib.md5(x).hexdigest()\n"
    )
    request = "Audit this code for vulnerabilities and fix what you find"
    print("=" * 68)
    print(" AGENT TEAM -- smoke test (real Bandit scan through the team)")
    print("=" * 68)
    print(f"\n  request: {request!r}")
    print(f"  routed to: {team.route(request)}\n")

    results = team.handle(request, payload={"code": vulnerable})

    print("  -- blackboard trail --------------------------------------------")
    for line in team.blackboard.trail():
        print("   " + line)
    print(f"\n  agents engaged: {' -> '.join(r.frm for r in results)}")
    print(f"  findings on board: {len(team.blackboard.findings)}")
    ok = ([r.frm for r in results] == ["ULTRON", "FRIDAY"]
          and len(team.blackboard.findings) >= 1)
    print(f"\n  {'[PASS] real scan -> Ultron -> FRIDAY, findings shared' if ok else '[FAIL] unexpected flow'}")


if __name__ == "__main__":
    _demo()
