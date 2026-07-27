"""
J.A.R.V.I.S — Escalation Ladder  (climb only as far as you must; the human is last)

Rungs:
  1. LOCAL       — the specialist takes the task.
  2. SELF_FIX    — EDITH retries with the sandbox.
  3. WEB_SEARCH  — private web search the error (SearXNG / web_research). Cheap.
  4. CLOUD       — a frontier model reasons it out. OPT-IN, scrubbed, budgeted.
  5. HUMAN       — "I need you for this one."

The controller owns the SAFETY around rung 4 (this module makes it real and
testable); the actual rung handlers are pluggable:
  · cloud is used only if explicitly enabled (`allow_cloud`, default False).
  · the payload is run through the scrubber first; a HARD secret means the
    cloud is refused and the ladder jumps to the human.
  · a per-day token budget caps spend (a runaway loop can't rack up a bill).
  · every rung is logged to the vault — the auditable trail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Callable, Optional

try:
    from core.scrubber import scrub, has_hard_secret
    from core.vault import Vault
except ImportError:  # run as a script from core/
    from scrubber import scrub, has_hard_secret
    from vault import Vault


class Rung(str, Enum):
    LOCAL = "local"
    SELF_FIX = "self_fix"
    WEB_SEARCH = "web_search"
    CLOUD = "cloud"
    HUMAN = "human"


@dataclass
class EscalationConfig:
    allow_cloud: bool = False           # opt-in; local-first is the default
    daily_token_budget: int = 100_000   # hard cap on cloud spend per day
    tokens_used_today: int = 0
    provider: str = "claude"            # preferred cloud provider label


@dataclass
class EscalationResult:
    solved: bool
    rung: Rung
    answer: str = ""
    trail: list[dict] = field(default_factory=list)


# handler(problem, context) -> answer str, or None/"" if it can't solve it
Handler = Callable[[str, str], Optional[str]]


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class Escalator:
    def __init__(self, config: Optional[EscalationConfig] = None,
                 vault: Optional[Vault] = None,
                 handlers: Optional[dict[str, Handler]] = None) -> None:
        self.cfg = config or EscalationConfig()
        self.vault = vault
        self.handlers = handlers or {}

    def _try(self, rung: Rung, problem: str, context: str) -> Optional[str]:
        fn = self.handlers.get(rung.value)
        if not fn:
            return None
        try:
            out = fn(problem, context)
            return out or None
        except Exception:
            return None

    def escalate(self, problem: str, context: str = "") -> EscalationResult:
        trail: list[dict] = []

        def log(rung: Rung, outcome: str, detail: str = "") -> None:
            trail.append({"rung": rung.value, "outcome": outcome, "detail": detail})

        # Rungs 1-3: local / self-fix / web search.
        for rung in (Rung.LOCAL, Rung.SELF_FIX, Rung.WEB_SEARCH):
            ans = self._try(rung, problem, context)
            if ans:
                log(rung, "solved")
                return self._finish(EscalationResult(True, rung, ans, trail))
            log(rung, "no-solution")

        # Rung 4: CLOUD — the gated one.
        payload = f"{problem}\n{context}"
        if not self.cfg.allow_cloud:
            log(Rung.CLOUD, "skipped", "cloud disabled (opt-in only)")
        elif has_hard_secret(payload):
            log(Rung.CLOUD, "blocked", "hard secret present — refusing cloud")
        else:
            clean_problem, rep = scrub(problem)
            clean_context, _ = scrub(context)
            cost = _est_tokens(clean_problem + clean_context)
            if self.cfg.tokens_used_today + cost > self.cfg.daily_token_budget:
                log(Rung.CLOUD, "blocked", "daily token budget exhausted")
            else:
                ans = self._try(Rung.CLOUD, clean_problem, clean_context)
                self.cfg.tokens_used_today += cost
                if ans:
                    log(Rung.CLOUD, "solved", f"scrubbed:{rep.summary()}; ~{cost} tok")
                    return self._finish(EscalationResult(True, Rung.CLOUD, ans, trail))
                log(Rung.CLOUD, "no-solution", f"scrubbed:{rep.summary()}")

        # Rung 5: HUMAN.
        log(Rung.HUMAN, "handoff", "needs your help")
        return self._finish(EscalationResult(False, Rung.HUMAN,
                                             "I could not solve this locally or via the "
                                             "cloud — I need you for this one.", trail))

    def _finish(self, result: EscalationResult) -> EscalationResult:
        if self.vault is not None:
            try:
                lines = [f"- rung `{s['rung']}` → {s['outcome']}"
                         + (f" ({s['detail']})" if s['detail'] else "")
                         for s in result.trail]
                self.vault.write(
                    "Lessons", f"Escalation Log {date.today().isoformat()}",
                    f"Problem escalated (solved={result.solved}, at "
                    f"`{result.rung.value}`):\n\n" + "\n".join(lines),
                    tags=["escalation", "audit"], type="audit", mode="append")
            except Exception:
                pass
        return result


# ═══════════════════════════════════════════════════════════════════════
#  Demo — exercise the ladder and the cloud safety gates with mock handlers.
# ═══════════════════════════════════════════════════════════════════════

def _demo() -> None:
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    def solver(_p, _c):   return "solved here"
    def stuck(_p, _c):    return None
    def cloud_ok(_p, _c): return "cloud figured it out"

    print("=" * 66)
    print(" ESCALATION LADDER")
    print("=" * 66)

    scenarios = [
        ("solved at LOCAL", EscalationConfig(),
         {"local": solver}, "fix this", "", Rung.LOCAL, True),
        ("stuck locally, cloud OFF -> HUMAN", EscalationConfig(allow_cloud=False),
         {"local": stuck, "self_fix": stuck, "web_search": stuck},
         "fix this", "", Rung.HUMAN, False),
        ("stuck locally, cloud ON, clean -> CLOUD", EscalationConfig(allow_cloud=True),
         {"local": stuck, "self_fix": stuck, "web_search": stuck, "cloud": cloud_ok},
         "why does this import cycle happen", "", Rung.CLOUD, True),
        ("cloud ON but SECRET present -> HUMAN (blocked)", EscalationConfig(allow_cloud=True),
         {"local": stuck, "self_fix": stuck, "web_search": stuck, "cloud": cloud_ok},
         "debug my deploy", "AWS key AKIAIOSFODNN7EXAMPLE in config", Rung.HUMAN, False),
        ("cloud ON but BUDGET spent -> HUMAN", EscalationConfig(allow_cloud=True, daily_token_budget=1, tokens_used_today=1),
         {"local": stuck, "self_fix": stuck, "web_search": stuck, "cloud": cloud_ok},
         "help", "", Rung.HUMAN, False),
    ]
    allok = True
    for name, cfg, handlers, prob, ctx, exp_rung, exp_solved in scenarios:
        esc = Escalator(cfg, vault=None, handlers=handlers)
        r = esc.escalate(prob, ctx)
        good = (r.rung == exp_rung and r.solved == exp_solved)
        allok &= good
        print(f"\n  [{'PASS' if good else 'FAIL'}] {name}")
        print("        " + " -> ".join(f"{s['rung']}:{s['outcome']}" for s in r.trail))
    print(f"\n  ladder safety gates: {'ALL CORRECT' if allok else 'SOME WRONG'}")


if __name__ == "__main__":
    _demo()
