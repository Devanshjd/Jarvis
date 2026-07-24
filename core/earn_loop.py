"""
J.A.R.V.I.S — Earn Loop

An Automaton-inspired idea engine WITH the human in the loop. JARVIS
proposes money-making ideas, tracks what each one costs and earns (INR),
and recommends killing losers — but every approval, kill, and rupee
flows through the owner. No wallet, no autonomous spending.

The loop:  propose → approve → testing → active
                          ↘ killed / parked (owner decides, JARVIS recommends)

Kill rules (recommendations only — nothing dies without the owner):
  • testing with zero revenue for KILL_AFTER_DAYS       → recommend kill
  • spend past the per-idea budget cap with ROI < 1     → recommend kill
  • active but no revenue for STALE_AFTER_DAYS          → recommend review

Usage:
    from core.earn_loop import EarnLoop
    loop = EarnLoop()
    loop.propose_ideas("cybersecurity student, India, evenings free")
    loop.approve("idea_a1b2")
    loop.log_revenue("idea_a1b2", 1500, "first freelance gig")
    print(loop.status_report())

Ledger: ~/.jarvis/earn_loop/ledger.json
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.earn_loop")

DATA_DIR = Path.home() / ".jarvis" / "earn_loop"
LEDGER_FILE = DATA_DIR / "ledger.json"

STATUSES = ("proposed", "testing", "active", "killed", "parked")
CHANNELS = ("freelance", "micro-product", "white-label", "content", "service", "other")


# ─── Config ───────────────────────────────────────────────────────────────

@dataclass
class EarnConfig:
    budget_cap_inr: float = 2000.0     # max spend per idea before ROI must be > 1
    kill_after_days: int = 14          # testing this long with ₹0 revenue → recommend kill
    stale_after_days: int = 30         # active this long with no new revenue → recommend review
    max_parallel_testing: int = 3      # focus: don't test everything at once


# ─── Idea model ───────────────────────────────────────────────────────────

@dataclass
class Idea:
    id: str
    title: str
    channel: str = "other"
    status: str = "proposed"
    created: str = ""
    status_since: str = ""
    next_action: str = ""
    kill_reason: str = ""
    # Each entry: {"ts": iso, "amount": float, "note": str}
    costs: list = field(default_factory=list)
    revenue: list = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(e["amount"] for e in self.costs)

    @property
    def total_revenue(self) -> float:
        return sum(e["amount"] for e in self.revenue)

    @property
    def profit(self) -> float:
        return self.total_revenue - self.total_cost

    def days_in_status(self) -> float:
        try:
            since = datetime.fromisoformat(self.status_since)
            return (datetime.now() - since).total_seconds() / 86400.0
        except Exception:
            return 0.0

    def days_since_last_revenue(self) -> Optional[float]:
        if not self.revenue:
            return None
        try:
            last = max(datetime.fromisoformat(e["ts"]) for e in self.revenue)
            return (datetime.now() - last).total_seconds() / 86400.0
        except Exception:
            return None


# ─── Seed ideas — fallback when no LLM is reachable ───────────────────────

SEED_IDEAS = [
    ("Freelance vulnerability assessments for local businesses", "freelance",
     "List a gig on Upwork/Fiverr; offer a fixed-price website security checkup"),
    ("Security-hardening checklists as a paid Notion/PDF product", "micro-product",
     "Write one checklist for small Indian e-commerce stores; sell on Gumroad"),
    ("White-label a phone accessory after a Meesho demand test", "white-label",
     "List 3 candidate products; the one that sells 10 units gets a branded run"),
    ("YouTube/Shorts channel: 60-second security tips in Hindi+English", "content",
     "Batch-record 10 shorts; monetization via affiliate links first"),
    ("Automated website health reports for shops (JARVIS-generated)", "service",
     "Use JARVIS to draft the report; sell as a monthly retainer to 3 shops"),
]


# ─── The engine ───────────────────────────────────────────────────────────

class EarnLoop:
    """Human-in-the-loop earn engine: propose, track, recommend kills."""

    def __init__(self, jarvis=None, config: Optional[EarnConfig] = None):
        self.jarvis = jarvis
        self.cfg = config or EarnConfig()
        self.ideas: dict[str, Idea] = {}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    # ─── Persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            raw = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
            for d in raw.get("ideas", []):
                idea = Idea(**{k: d[k] for k in d if k in Idea.__dataclass_fields__})
                self.ideas[idea.id] = idea
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("Ledger load failed: %s", e)

    def _save(self) -> None:
        payload = {"updated": datetime.now().isoformat(),
                   "ideas": [asdict(i) for i in self.ideas.values()]}
        LEDGER_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                               encoding="utf-8")

    # ─── Idea lifecycle ───────────────────────────────────────────────────

    def add_idea(self, title: str, channel: str = "other",
                 next_action: str = "") -> Idea:
        now = datetime.now().isoformat()
        idea = Idea(
            id=f"idea_{uuid.uuid4().hex[:4]}",
            title=title.strip(),
            channel=channel if channel in CHANNELS else "other",
            status="proposed",
            created=now,
            status_since=now,
            next_action=next_action,
        )
        self.ideas[idea.id] = idea
        self._save()
        return idea

    def _set_status(self, idea_id: str, status: str, reason: str = "") -> Idea:
        idea = self.ideas.get(idea_id)
        if not idea:
            raise KeyError(f"No idea with id {idea_id}")
        if status not in STATUSES:
            raise ValueError(f"Bad status {status}")
        idea.status = status
        idea.status_since = datetime.now().isoformat()
        if status == "killed":
            idea.kill_reason = reason or "owner decision"
        self._save()
        return idea

    def approve(self, idea_id: str) -> Idea:
        """Owner approves a proposed idea → it enters testing."""
        testing = [i for i in self.ideas.values() if i.status == "testing"]
        if len(testing) >= self.cfg.max_parallel_testing:
            raise RuntimeError(
                f"Already testing {len(testing)} ideas (cap "
                f"{self.cfg.max_parallel_testing}). Kill or park one first — focus wins.")
        return self._set_status(idea_id, "testing")

    def promote(self, idea_id: str) -> Idea:
        """Testing idea proved itself → active."""
        return self._set_status(idea_id, "active")

    def kill(self, idea_id: str, reason: str = "") -> Idea:
        return self._set_status(idea_id, "killed", reason)

    def park(self, idea_id: str) -> Idea:
        return self._set_status(idea_id, "parked")

    # ─── Money tracking (INR) ─────────────────────────────────────────────

    def log_cost(self, idea_id: str, amount: float, note: str = "") -> Idea:
        idea = self.ideas.get(idea_id)
        if not idea:
            raise KeyError(f"No idea with id {idea_id}")
        idea.costs.append({"ts": datetime.now().isoformat(),
                           "amount": float(amount), "note": note})
        self._save()
        return idea

    def log_revenue(self, idea_id: str, amount: float, note: str = "") -> Idea:
        idea = self.ideas.get(idea_id)
        if not idea:
            raise KeyError(f"No idea with id {idea_id}")
        idea.revenue.append({"ts": datetime.now().isoformat(),
                             "amount": float(amount), "note": note})
        self._save()
        return idea

    # ─── Idea generation ──────────────────────────────────────────────────

    def propose_ideas(self, context: str = "", count: int = 5) -> list[Idea]:
        """Generate idea candidates (LLM if available, seeds otherwise)."""
        generated = self._llm_ideas(context, count)
        if not generated:
            existing = {i.title for i in self.ideas.values()}
            generated = [(t, c, a) for t, c, a in SEED_IDEAS if t not in existing][:count]
        return [self.add_idea(title, channel, action)
                for title, channel, action in generated]

    def _llm_ideas(self, context: str, count: int) -> list[tuple[str, str, str]]:
        """Ask the local LLM for idea candidates. Empty list on any failure."""
        try:
            import requests

            model = "llama3.2:latest"
            try:
                cfg = json.loads((Path.home() / ".jarvis_config.json").read_text(encoding="utf-8"))
                model = (cfg.get("ollama") or {}).get("model") or model
            except Exception:
                pass

            system = (
                "You propose realistic side-income ideas for your owner. "
                "Output ONLY a JSON array of exactly these fields per item:\n"
                '  {"title": "<one-line idea>", "channel": "<one of: '
                + ", ".join(CHANNELS) + '>", "next_action": "<the first concrete '
                'step, doable this week, under ₹500>"}\n\n'
                "Rules: legal, honest work only; no crypto, no trading, no "
                "get-rich-quick; India-friendly (INR, UPI, Meesho/Amazon.in, "
                "Upwork/Fiverr); each idea must be testable for under ₹2000 total."
            )
            killed = [i.title for i in self.ideas.values() if i.status == "killed"][-5:]
            prompt = (
                f"Owner context: {context or 'cybersecurity student in India, evenings free'}\n"
                f"Already tried and killed: {killed or 'nothing yet'}\n"
                f"Propose {count} NEW ideas as a JSON array:"
            )
            r = requests.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "keep_alive": "5m",
                    "options": {"temperature": 0.8, "num_predict": 700},
                },
                timeout=45,
            )
            if r.status_code != 200:
                return []
            content = (r.json().get("message", {}).get("content") or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.rstrip().endswith("```"):
                    content = content.rstrip()[:-3]
            items = json.loads(content.strip())
            out = []
            for it in items[:count]:
                title = (it.get("title") or "").strip()
                if title:
                    out.append((title,
                                (it.get("channel") or "other").strip(),
                                (it.get("next_action") or "").strip()))
            return out
        except Exception as e:
            logger.debug("LLM idea generation failed (using seeds): %s", e)
            return []

    # ─── Review cycle — the heartbeat, minus the dying ────────────────────

    def review_cycle(self) -> list[dict]:
        """Apply kill rules; return recommendations. NEVER auto-kills."""
        recs = []
        for idea in self.ideas.values():
            if idea.status == "testing":
                if idea.total_revenue == 0 and idea.days_in_status() >= self.cfg.kill_after_days:
                    recs.append({"idea_id": idea.id, "action": "kill",
                                 "reason": f"₹0 revenue after {idea.days_in_status():.0f} "
                                           f"days of testing (cap {self.cfg.kill_after_days})"})
                elif idea.total_cost > self.cfg.budget_cap_inr and idea.profit < 0:
                    recs.append({"idea_id": idea.id, "action": "kill",
                                 "reason": f"₹{idea.total_cost:.0f} spent (cap "
                                           f"₹{self.cfg.budget_cap_inr:.0f}) and still ₹"
                                           f"{idea.profit:.0f} in the red"})
                elif idea.profit > 0:
                    recs.append({"idea_id": idea.id, "action": "promote",
                                 "reason": f"₹{idea.profit:.0f} profit in testing — "
                                           "double down, promote to active"})
            elif idea.status == "active":
                stale = idea.days_since_last_revenue()
                if stale is not None and stale >= self.cfg.stale_after_days:
                    recs.append({"idea_id": idea.id, "action": "review",
                                 "reason": f"no revenue in {stale:.0f} days — "
                                           "revive it or park it"})
        return recs

    # ─── Reporting ────────────────────────────────────────────────────────

    def status_report(self) -> str:
        if not self.ideas:
            return ("EARN LOOP — empty ledger.\n"
                    "Start with: /earn ideas <your context>")
        lines = ["EARN LOOP — P&L (INR)", ""]
        order = {s: n for n, s in enumerate(STATUSES)}
        for idea in sorted(self.ideas.values(), key=lambda i: order.get(i.status, 9)):
            flag = {"proposed": "○", "testing": "▶", "active": "★",
                    "killed": "✖", "parked": "…"}.get(idea.status, "?")
            lines.append(
                f"{flag} [{idea.id}] {idea.title}\n"
                f"    {idea.status.upper()} ({idea.channel}) · "
                f"in: ₹{idea.total_revenue:.0f} · out: ₹{idea.total_cost:.0f} · "
                f"net: ₹{idea.profit:+.0f}"
                + (f"\n    next: {idea.next_action}" if idea.next_action
                   and idea.status in ("proposed", "testing") else "")
                + (f"\n    killed: {idea.kill_reason}" if idea.status == "killed" else "")
            )
        total_in = sum(i.total_revenue for i in self.ideas.values())
        total_out = sum(i.total_cost for i in self.ideas.values())
        lines += ["", f"TOTAL  in: ₹{total_in:.0f}  out: ₹{total_out:.0f}  "
                      f"net: ₹{total_in - total_out:+.0f}"]
        recs = self.review_cycle()
        if recs:
            lines += ["", "RECOMMENDATIONS (your call — /earn kill|promote <id>):"]
            lines += [f"  {r['action'].upper()} {r['idea_id']} — {r['reason']}" for r in recs]
        return "\n".join(lines)
