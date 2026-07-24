"""
J.A.R.V.I.S — Bug Bounty Targeting

The bug-bounty channel of the earn loop. Skill-based, legal, pays through
normal channels — a good fit for a cybersecurity student. JARVIS helps with
the parts that are tedious, NOT the parts that require judgment:

  - track programs + their scope (in / out) so you never test out-of-scope
  - generate a recon checklist for a target (methodology, not exploitation)
  - draft a clean vulnerability report from your findings (you verify + submit)
  - log submissions and outcomes so you learn what pays

Hard boundaries (by design):
  - It NEVER scans, exploits, or touches a live target — it only organises
    YOUR work and drafts text. You do the actual authorised testing.
  - It only helps with programs that have an explicit bounty/VDP scope. Testing
    out of scope is illegal; the scope fields exist to keep you inside it.

Local-first: recon/report drafting use local Ollama when available, with solid
static fallbacks so it works fully offline.

Ledger: ~/.jarvis/bug_bounty/targets.json
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

BB_DIR = Path.home() / ".jarvis" / "bug_bounty"
LEDGER = BB_DIR / "targets.json"

SEVERITIES = ["info", "low", "medium", "high", "critical"]

# Static recon checklist — a legitimate, methodology-level starting point.
# Deliberately recon/mapping oriented, not exploitation payloads.
RECON_CHECKLIST = [
    "Confirm the asset is IN SCOPE for the program before touching it.",
    "Read the program policy: allowed testing, rate limits, prohibited actions.",
    "Passive recon: subdomains (crt.sh, Subfinder), tech stack (Wappalyzer), robots.txt / sitemap.",
    "Map the app: authenticated + unauthenticated surface, roles, API endpoints.",
    "Enumerate inputs: params, headers, cookies, file uploads, JSON bodies.",
    "Review auth flows: login, reset, session handling, MFA, JWT/oauth if present.",
    "Check access control: can a low-priv user reach high-priv objects/IDs (IDOR)?",
    "Look for injection surfaces: reflected/stored inputs, template rendering, search.",
    "Business logic: coupons, quantities, price fields, multi-step flows.",
    "Note anything odd; verify safely; capture clean, minimal repro steps.",
    "Write the report ONLY for confirmed, reproducible issues — no theory.",
]


@dataclass
class Submission:
    title: str
    severity: str = "medium"
    status: str = "draft"          # draft | submitted | triaged | resolved | duplicate | n/a
    reward_inr: float = 0.0
    created: float = field(default_factory=time.time)


@dataclass
class Target:
    id: str
    program: str
    platform: str = "other"        # hackerone | bugcrowd | intigriti | private | other
    scope_in: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    status: str = "recon"          # recon | testing | reporting | parked | done
    notes: str = ""
    submissions: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.time)


class BugBountyTracker:
    def __init__(self, jarvis=None):
        self.jarvis = jarvis
        BB_DIR.mkdir(parents=True, exist_ok=True)
        self.targets: dict[str, Target] = {}
        self._load()

    # ─── Persistence ──────────────────────────────────────────────────────
    def _load(self) -> None:
        if not LEDGER.exists():
            return
        try:
            raw = json.loads(LEDGER.read_text(encoding="utf-8"))
            for t in raw.get("targets", []):
                self.targets[t["id"]] = Target(**t)
        except Exception:
            pass

    def _save(self) -> None:
        LEDGER.write_text(
            json.dumps({"targets": [asdict(t) for t in self.targets.values()]},
                       indent=2, ensure_ascii=False),
            encoding="utf-8")

    # ─── Targets ──────────────────────────────────────────────────────────
    def add_target(self, program: str, platform: str = "other",
                   scope_in: Optional[list[str]] = None,
                   scope_out: Optional[list[str]] = None) -> Target:
        tid = uuid.uuid4().hex[:6]
        t = Target(id=tid, program=program.strip(), platform=platform.strip().lower() or "other",
                   scope_in=[s.strip() for s in (scope_in or []) if s.strip()],
                   scope_out=[s.strip() for s in (scope_out or []) if s.strip()])
        self.targets[tid] = t
        self._save()
        return t

    def get(self, target_id: str) -> Target:
        if target_id not in self.targets:
            raise KeyError(f"No target [{target_id}]. Add one with /bounty add <program>.")
        return self.targets[target_id]

    def set_status(self, target_id: str, status: str) -> Target:
        t = self.get(target_id)
        t.status = status
        self._save()
        return t

    def in_scope(self, target_id: str, asset: str) -> Optional[bool]:
        """True/False if the asset clearly matches scope, None if uncertain."""
        t = self.get(target_id)
        a = asset.strip().lower()
        if any(a == s.lower() or a.endswith(s.lower().lstrip("*.")) for s in t.scope_out):
            return False
        if any(a == s.lower() or a.endswith(s.lower().lstrip("*.")) for s in t.scope_in):
            return True
        return None

    def log_submission(self, target_id: str, title: str, severity: str = "medium",
                       status: str = "submitted", reward_inr: float = 0.0) -> Target:
        t = self.get(target_id)
        sev = severity.lower() if severity.lower() in SEVERITIES else "medium"
        t.submissions.append(asdict(Submission(title=title.strip(), severity=sev,
                                               status=status, reward_inr=reward_inr)))
        self._save()
        return t

    # ─── Recon checklist ──────────────────────────────────────────────────
    def recon_checklist(self, target_id: Optional[str] = None) -> list[str]:
        """A methodology checklist for a target. Local LLM if available, else
        the static legitimate checklist."""
        program = ""
        if target_id:
            program = self.get(target_id).program
        llm = self._llm_lines(
            system=(
                "You are a bug-bounty methodology assistant for an AUTHORISED tester. "
                "Output ONLY a JSON array of short recon/mapping checklist steps "
                "(methodology, NOT exploit payloads). Legal, scope-respecting."),
            prompt=f"Give a 10-step recon checklist for testing the program: {program or 'a web app'}.",
        )
        return llm or RECON_CHECKLIST

    # ─── Report drafting ──────────────────────────────────────────────────
    def draft_report(self, title: str, severity: str = "medium",
                     summary: str = "", steps: str = "", impact: str = "") -> str:
        """Draft a clean vulnerability report. LLM-polished if available, else a
        solid template. YOU verify every claim before submitting."""
        sev = severity.lower() if severity.lower() in SEVERITIES else "medium"
        llm = self._llm_text(
            system=(
                "You write concise, professional bug-bounty vulnerability reports. "
                "Use the standard sections: Title, Severity, Summary, Steps to "
                "Reproduce, Impact, Remediation. Only state what the tester provided; "
                "do NOT invent findings. Keep it factual and submission-ready."),
            prompt=(f"Title: {title}\nSeverity: {sev}\nSummary: {summary}\n"
                    f"Steps: {steps}\nImpact: {impact}\n\nWrite the report:"),
        )
        if llm:
            return llm
        # Static template fallback
        return (
            f"# {title}\n\n"
            f"**Severity:** {sev}\n\n"
            f"## Summary\n{summary or '<what the issue is, in one or two sentences>'}\n\n"
            f"## Steps to Reproduce\n{steps or '1. ...\\n2. ...\\n3. ...'}\n\n"
            f"## Impact\n{impact or '<what an attacker can actually do with this>'}\n\n"
            f"## Remediation\n<the fix — validate input / enforce access control / etc.>\n\n"
            f"---\n_Verify every step reproduces before submitting. Only report "
            f"confirmed, in-scope issues._"
        )

    # ─── Status ───────────────────────────────────────────────────────────
    def status_report(self) -> str:
        if not self.targets:
            return ("No bug-bounty targets yet. Add one:\n"
                    "  /bounty add <program> [platform]\n"
                    "Then: /bounty recon <id>  ·  /bounty report <id> <title>")
        lines = ["Bug-bounty targets:", ""]
        total_reward = 0.0
        for t in self.targets.values():
            subs = t.submissions
            paid = sum(s.get("reward_inr", 0) for s in subs)
            total_reward += paid
            lines.append(f"  [{t.id}] {t.program} ({t.platform}) — {t.status.upper()}")
            if t.scope_in:
                lines.append(f"      in-scope: {', '.join(t.scope_in[:4])}")
            if subs:
                lines.append(f"      submissions: {len(subs)}  ·  earned: ₹{paid:.0f}")
        lines += ["", f"Total earned so far: ₹{total_reward:.0f}"]
        lines += ["", "Reminder: only test IN-SCOPE assets on programs that authorise it."]
        return "\n".join(lines)

    # ─── Local LLM helpers ────────────────────────────────────────────────
    def _model(self) -> str:
        model = "llama3.2:latest"
        try:
            cfg = json.loads((Path.home() / ".jarvis_config.json").read_text(encoding="utf-8"))
            model = (cfg.get("ollama") or {}).get("model") or model
        except Exception:
            pass
        return model

    def _llm_text(self, system: str, prompt: str) -> str:
        try:
            import requests
            r = requests.post(
                "http://127.0.0.1:11434/api/chat",
                json={"model": self._model(),
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": prompt}],
                      "stream": False, "keep_alive": "5m",
                      "options": {"temperature": 0.4, "num_predict": 800}},
                timeout=60)
            if r.status_code != 200:
                return ""
            return (r.json().get("message", {}).get("content") or "").strip()
        except Exception:
            return ""

    def _llm_lines(self, system: str, prompt: str) -> list[str]:
        text = self._llm_text(system, prompt)
        if not text:
            return []
        # Try to parse a JSON array; else split lines.
        try:
            start, end = text.find("["), text.rfind("]")
            if start != -1 and end != -1:
                arr = json.loads(text[start:end + 1])
                return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
        return [ln.strip(" -*0123456789.") for ln in text.splitlines() if ln.strip()][:12]


# Module-level singleton
_tracker: Optional[BugBountyTracker] = None


def get_tracker(jarvis=None) -> BugBountyTracker:
    global _tracker
    if _tracker is None:
        _tracker = BugBountyTracker(jarvis)
    return _tracker
