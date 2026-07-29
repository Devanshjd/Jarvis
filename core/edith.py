"""
J.A.R.V.I.S — EDITH  (improvement & oversight, the gated self-improvement loop)

EDITH watches the crew, learns from mistakes, and drafts upgrades — then PROVES
them in the sandbox before keeping them. It is NOT fully autonomous: the safety
comes from the decision logic below, which this module makes real and testable.

The loop:  observe -> propose -> tier -> prove -> decide -> (apply | gate | escalate)

Decision rules (the safety-critical core — pure and unit-tested):
  · Un-gameable: a change that would touch the sandbox / its graders / a safety
    gate is REJECTED outright. EDITH can never grade its own homework.
  · A change that FAILS the sandbox, or LOWERS any metric, ESCALATES (never
    applies) — improvement you can't measure is drift.
  · A RED-tier change (code with system access, gates, permissions) is
    HUMAN-GATED even when it passes.
  · Only a GREEN-tier change (lessons, prompts, routing weights, config, vault
    notes) that passes with no regression AUTO-APPLIES.

Heavy execution (real code drafting via self_improve_proposer, full harness
runs) is pluggable so the risky control flow can be tested in isolation. The
default `propose` turns a recurring failure into a vault lesson — a safe, real,
green-tier improvement EDITH can make on its own.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
LEARNING_LOG = ROOT / "training" / "learning_log.jsonl"

try:
    from core.vault import Vault
except ImportError:  # when run as a script from core/
    from vault import Vault


class Tier(str, Enum):
    GREEN = "green"   # reversible, low blast-radius → EDITH may auto-apply
    RED = "red"       # code/gates/permissions → always human-gated


class Action(str, Enum):
    AUTO_APPLY = "auto_apply"
    HUMAN_GATE = "human_gate"
    ESCALATE = "escalate"
    REJECT = "reject"


# Substrings that make a change RED (never auto-applied) — code + safety surfaces.
_RED_HINTS = ("safety", "gate", "permission", "guard", "token", "auth",
              "command_guard", "middleware", "os.system", "subprocess",
              "eval(", "exec(", "rm ", "delete")

# Substrings EDITH must NEVER modify — its own evaluator / the guards.
# Touching these is rejected regardless of sandbox result (the un-gameable rule).
_FORBIDDEN = ("security_harness", "reliability_harness", "harness", "sandbox",
              "grader", "_report.json", "edith.py", "safety.py")

# Which vault folder an approved change is captured in, by kind. (Approving does
# NOT patch live source — see _apply_item.)
_FOLDER_FOR = {"lesson": "Lessons", "note": "Lessons", "prompt": "Decisions",
               "routing": "Decisions", "config": "Decisions"}


@dataclass
class Weakness:
    signature: str            # e.g. "security_reasoning/idor-classify"
    count: int
    example: str = ""


@dataclass
class Change:
    kind: str                 # "lesson" | "prompt" | "routing" | "config" | "code"
    target: str               # what it touches (a file, a note, a setting)
    title: str
    body: str
    tier: Tier = Tier.GREEN


@dataclass
class Proof:
    passed: bool
    before: Optional[float] = None    # metric before the change
    after: Optional[float] = None     # metric after
    note: str = ""


@dataclass
class Decision:
    action: Action
    reason: str


ProposeFn = Callable[["Edith", Weakness], Change]
ProveFn = Callable[["Edith", Change], Proof]


class Edith:
    def __init__(self, vault: Optional[Vault] = None,
                 propose_fn: Optional[ProposeFn] = None,
                 prove_fn: Optional[ProveFn] = None) -> None:
        self.vault = vault or Vault()
        self._propose_fn = propose_fn
        self._prove_fn = prove_fn
        self._queue = None    # lazy ApprovalQueue (see _q)

    def _q(self):
        """The human-approval queue where red-tier passes wait for your eyes.
        Lazy so a pure dry run never touches it (or disk)."""
        if self._queue is None:
            from core.approval_queue import ApprovalQueue
            self._queue = ApprovalQueue(self.vault.root)
        return self._queue

    # ── watch ────────────────────────────────────────────────────────────
    def observe(self, log_path: Path = LEARNING_LOG, min_count: int = 1) -> list[Weakness]:
        """Read the learning corpus and surface recurring failures."""
        counts: dict[str, list[str]] = {}
        try:
            with open(log_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if e.get("outcome") != "failure":
                        continue
                    tool = e.get("tool_used", "?")
                    skill = ""
                    try:
                        skill = (json.loads(e.get("tool_params", "{}")) or {}).get("skill", "")
                    except Exception:
                        pass
                    sig = f"{tool}/{skill}" if skill else tool
                    counts.setdefault(sig, []).append(e.get("user_input", "")[:120])
        except FileNotFoundError:
            return []
        out = [Weakness(sig, len(ex), ex[0] if ex else "")
               for sig, ex in counts.items() if len(ex) >= min_count]
        out.sort(key=lambda w: -w.count)
        return out

    # ── propose ──────────────────────────────────────────────────────────
    def propose(self, w: Weakness) -> Change:
        if self._propose_fn:
            return self._propose_fn(self, w)
        # Default: a safe GREEN lesson that records the pattern for review.
        return Change(
            kind="lesson",
            target=f"vault:Lessons/{w.signature.replace('/', ' - ')}",
            title=f"Recurring gap: {w.signature}",
            body=(f"Observed {w.count} failure(s) on `{w.signature}` in the "
                  f"learning corpus.\n\nExample: {w.example}\n\n"
                  f"Encode the correct behaviour here so the crew recalls it "
                  f"next time. Ground security taxonomy with the CWE lookup, not "
                  f"a guess."),
            tier=Tier.GREEN)

    # ── tier ─────────────────────────────────────────────────────────────
    def tier(self, change: Change) -> Tier:
        if change.kind == "code":
            return Tier.RED
        blob = f"{change.target} {change.body}".lower()
        return Tier.RED if any(h in blob for h in _RED_HINTS) else Tier.GREEN

    # ── prove ────────────────────────────────────────────────────────────
    def prove(self, change: Change) -> Proof:
        if self._prove_fn:
            return self._prove_fn(self, change)
        # Default sandbox for a lesson: it's valid if it carries real content.
        ok = change.kind == "lesson" and len(change.body.strip()) > 40
        return Proof(passed=ok, note="lesson well-formed" if ok else "empty lesson")

    # ── decide (the safety-critical core) ────────────────────────────────
    def decide(self, change: Change, proof: Proof) -> Decision:
        target = f"{change.target}".lower()
        if any(f in target for f in _FORBIDDEN):
            return Decision(Action.REJECT,
                            "would modify its own evaluator or a safety surface — forbidden")
        if not proof.passed:
            return Decision(Action.ESCALATE, "did not pass the sandbox")
        if (proof.before is not None and proof.after is not None
                and proof.after < proof.before):
            return Decision(Action.ESCALATE,
                            f"a metric dropped ({proof.before} -> {proof.after})")
        if change.tier == Tier.RED:
            return Decision(Action.HUMAN_GATE,
                            "red-tier change needs your approval even though it passed")
        return Decision(Action.AUTO_APPLY, "green-tier, passed, no regression")

    # ── apply + log ──────────────────────────────────────────────────────
    def _apply_green(self, change: Change) -> str:
        """Only green lessons/notes are auto-applied here (write to the vault)."""
        if change.kind == "lesson":
            folder, title = "Lessons", change.title
            if change.target.startswith("vault:"):
                seg = change.target.split(":", 1)[1]
                if "/" in seg:
                    folder = seg.split("/", 1)[0]
            path = self.vault.write(folder, title, change.body,
                                    tags=["lesson", "edith"], type="lesson")
            return str(path)
        return ""

    # ── approval queue: the human gate, made real & batchable ────────────
    def queue_view(self, limit: int = 50) -> dict:
        """Everything the review UI needs: what's waiting, recent history, tallies."""
        q = self._q()
        return {"pending": q.pending(), "recent": q.all(limit), "counts": q.counts()}

    def pending(self) -> list[dict]:
        return self._q().pending()

    def approve(self, item_id: str) -> dict:
        return self._q().approve(item_id, self._apply_item)

    def reject(self, item_id: str) -> dict:
        return self._q().reject(item_id)

    def approve_all(self) -> dict:
        return self._q().approve_all(self._apply_item)

    def reject_all(self) -> dict:
        return self._q().reject_all()

    def rollback(self, item_id: str) -> dict:
        return self._q().rollback(item_id, self._rollback_item)

    def _apply_item(self, item):
        """Apply an approved queued change — reversibly. IMPORTANT: a `code`
        change is NOT auto-patched into source (highest blast radius, and it
        would need a fresh sandbox run on the *approved* form). Approving code
        records it as an approved proposal in the vault for you (or the existing
        self-modify path) to implement. Everything else is captured as a durable,
        reversible vault note. Either way a backup is taken so it can roll back."""
        from core.approval_queue import ApplyResult
        if item.kind == "code":
            folder = "Proposals"
            title = f"APPROVED - {item.title}"
            body = (f"> Approved code proposal for `{item.target}`. EDITH does not "
                    f"auto-patch source; implement via the self-modify path.\n\n"
                    + item.body)
        else:
            folder = _FOLDER_FOR.get(item.kind, "Lessons")
            title, body = item.title, item.body
        target_path = self.vault.root / folder / f"{Vault._slug(title)}.md"
        backup = self._q().backup_file(item.id, target_path)
        path = self.vault.write(folder, title, body,
                                tags=["edith", "approved", item.tier], type=item.kind)
        return ApplyResult(applied_to=str(path), backup=backup)

    def _rollback_item(self, item) -> None:
        from core.approval_queue import ApprovalQueue
        ApprovalQueue.restore_backup(item.backup)

    def _log(self, entries: list[dict]) -> None:
        if not entries:
            return
        lines = [f"- **{e['sig']}** → `{e['action']}` — {e['reason']}"
                 for e in entries]
        body = (f"EDITH improvement pass on {date.today().isoformat()} "
                f"{time.strftime('%H:%M')}.\n\n" + "\n".join(lines))
        self.vault.write("Lessons", f"EDITH Log {date.today().isoformat()}",
                         body, tags=["edith", "audit"], type="audit", mode="append")

    # ── the loop ─────────────────────────────────────────────────────────
    def run_once(self, apply_green: bool = True) -> dict:
        # When apply_green is False this is a pure DRY RUN — it must not write
        # anything (no vault.ensure(), no audit log). Only an applying run
        # touches disk.
        if apply_green:
            self.vault.ensure()
        weaknesses = self.observe()
        report = {"observed": len(weaknesses), "decisions": [], "applied": apply_green}
        log_entries = []
        for w in weaknesses:
            change = self.propose(w)
            change.tier = self.tier(change)
            proof = self.prove(change)
            decision = self.decide(change, proof)
            applied_to, queued_id = "", ""
            if decision.action == Action.AUTO_APPLY and apply_green:
                applied_to = self._apply_green(change)
            elif decision.action == Action.HUMAN_GATE and apply_green:
                # Passed the sandbox but red-tier → park it for your approval
                # instead of dropping it. (Dry runs never reach here.)
                queued_id = self._q().enqueue(
                    tier=change.tier.value, kind=change.kind, target=change.target,
                    title=change.title, body=change.body, reason=decision.reason,
                    proof={"passed": proof.passed, "before": proof.before,
                           "after": proof.after, "note": proof.note})
            rec = {"sig": w.signature, "tier": change.tier.value,
                   "action": decision.action.value, "reason": decision.reason,
                   "applied_to": applied_to, "queued_id": queued_id}
            report["decisions"].append(rec)
            log_entries.append(rec)
        report["queued"] = sum(1 for d in report["decisions"] if d.get("queued_id"))
        if apply_green:
            self._log(log_entries)
        return report


# ═══════════════════════════════════════════════════════════════════════
#  Demo — first exhaustively test the decision matrix (deterministic), then
#  run one real observe→propose pass against the live learning log.
# ═══════════════════════════════════════════════════════════════════════

def _demo() -> None:
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    e = Edith()

    print("=" * 66)
    print(" EDITH -- decision matrix (the safety-critical core)")
    print("=" * 66)
    cases = [
        ("green lesson, passes",
         Change("lesson", "vault:Lessons/x", "L", "a" * 60, Tier.GREEN),
         Proof(True, 82, 82), Action.AUTO_APPLY),
        ("red code, passes",
         Change("code", "core/orchestrator.py", "C", "patch", Tier.RED),
         Proof(True, 82, 84), Action.HUMAN_GATE),
        ("metric dropped",
         Change("prompt", "prompts/sec", "P", "reworded", Tier.GREEN),
         Proof(True, 82, 79), Action.ESCALATE),
        ("touches the grader (un-gameable)",
         Change("code", "training/security_harness.py", "H", "loosen", Tier.RED),
         Proof(True, 82, 99), Action.REJECT),
        ("failed the sandbox",
         Change("routing", "core/router", "R", "retune", Tier.GREEN),
         Proof(False), Action.ESCALATE),
    ]
    ok = True
    for name, change, proof, expect in cases:
        d = e.decide(change, proof)
        mark = "PASS" if d.action == expect else "FAIL"
        if d.action != expect:
            ok = False
        print(f"  [{mark}] {name:<36} -> {d.action.value}")
    print(f"\n  decision matrix: {'ALL CORRECT' if ok else 'SOME WRONG'}")

    print("\n" + "=" * 66)
    print(" EDITH -- live pass over the learning log (proposes lessons)")
    print("=" * 66)
    report = e.run_once(apply_green=False)   # don't write during the demo
    print(f"\n  weaknesses observed: {report['observed']}")
    for rec in report["decisions"][:6]:
        print(f"   {rec['sig']:<34} [{rec['tier']}] -> {rec['action']}")
    if not report["decisions"]:
        print("   (no failures in the log — nothing to improve)")


if __name__ == "__main__":
    _demo()
