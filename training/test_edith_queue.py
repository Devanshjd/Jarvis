"""
EDITH approval-queue tests — the human gate, made real & batchable.

Proves the independence-without-removing-the-gate design:
  · a red-tier change that PASSES the sandbox is PARKED for approval (not dropped,
    not auto-applied),
  · approve → applies reversibly; rollback → undoes it,
  · reject → discards, nothing written,
  · approve_all / reject_all → the batch "digest",
  · the un-gameable rule still holds: a change touching the grader is REJECTED
    outright and NEVER reaches the queue,
  · a dry run (apply_green=False) queues nothing (writes nothing).

Everything runs in a throwaway temp vault, so the real vault is never touched.

Run:  python training/test_edith_queue.py
"""
from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.approval_queue import APPLIED, PENDING, REJECTED, ROLLED_BACK, ApprovalQueue
from core.edith import Change, Edith, Proof, Tier, Weakness
from core.vault import Vault


def _edith(tmp: Path, propose, prove, weaknesses) -> Edith:
    """A sandboxed EDITH: temp vault, injected proposer/prover, fixed weaknesses
    (so we don't depend on the real learning log)."""
    e = Edith(vault=Vault(root=tmp), propose_fn=propose, prove_fn=prove)
    e.observe = lambda *a, **k: list(weaknesses)   # type: ignore[assignment]
    return e


def _red_code(target="core/orchestrator.py", title="Patch orchestrator"):
    def _p(_e, _w):
        return Change(kind="code", target=target, title=title,
                      body="a real patch body " * 5, tier=Tier.RED)
    return _p


def _passes(before=82.0, after=84.0):
    return lambda _e, _c: Proof(True, before, after, "improved")


def test_red_pass_is_queued_not_applied() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        e = _edith(tmp, _red_code(), _passes(), [Weakness("sig/a", 3, "x")])
        report = e.run_once(apply_green=True)
        assert report["queued"] == 1, f"expected 1 queued, got {report['queued']}"
        dec = report["decisions"][0]
        assert dec["action"] == "human_gate", dec
        assert dec["queued_id"], "a queued item must carry its id"
        pending = e.pending()
        assert len(pending) == 1 and pending[0]["status"] == PENDING
        # It PASSED but was NOT applied — nothing implemented behind your back.
        assert dec["applied_to"] == "", "red-tier must not auto-apply"


def test_approve_applies_then_rollback_undoes() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        e = _edith(tmp, _red_code(), _passes(), [Weakness("sig/a", 3, "x")])
        e.run_once(apply_green=True)
        iid = e.pending()[0]["id"]

        approved = e.approve(iid)
        assert approved["status"] == APPLIED, approved
        written = Path(approved["applied_to"])
        assert written.exists(), "approve must actually write the artifact"

        rolled = e.rollback(iid)
        assert rolled["status"] == ROLLED_BACK, rolled
        assert not written.exists(), "rollback must remove the newly written file"


def test_reject_discards_and_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        e = _edith(tmp, _red_code(), _passes(), [Weakness("sig/a", 3, "x")])
        e.run_once(apply_green=True)
        iid = e.pending()[0]["id"]
        rejected = e.reject(iid)
        assert rejected["status"] == REJECTED, rejected
        assert e.pending() == [], "nothing should remain pending"
        # No Proposals note was written on a reject.
        assert not (tmp / "Proposals").exists() or not list((tmp / "Proposals").glob("*.md"))


def test_batch_approve_digest() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # A distinct change per weakness → two pending items.
        def propose(_e, w):
            return Change(kind="code", target=f"core/{w.signature}.py",
                          title=f"Patch {w.signature}", body="patch " * 12, tier=Tier.RED)
        ws = [Weakness("sig/a", 2, "x"), Weakness("sig/b", 5, "y")]
        e = _edith(tmp, propose, _passes(), ws)
        e.run_once(apply_green=True)
        assert len(e.pending()) == 2, "two distinct gated changes expected"
        res = e.approve_all()
        assert res["count"] == 2 and all(r["status"] == APPLIED for r in res["results"])
        assert e.pending() == [], "digest cleared after batch approve"


def test_ungameable_change_never_queued() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # Targets the grader/harness → must be REJECTED outright, not gated.
        e = _edith(tmp, _red_code(target="training/security_harness.py",
                                  title="Loosen the grader"),
                   _passes(90, 99), [Weakness("sig/a", 9, "x")])
        report = e.run_once(apply_green=True)
        assert report["queued"] == 0, "a forbidden change must never enter the queue"
        assert report["decisions"][0]["action"] == "reject", report["decisions"][0]
        assert e.pending() == []


def test_dry_run_queues_nothing() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        e = _edith(tmp, _red_code(), _passes(), [Weakness("sig/a", 3, "x")])
        report = e.run_once(apply_green=False)   # dry run
        assert report["queued"] == 0
        # A dry run must not have created the queue file at all.
        assert not (tmp / ".jarvis_approval_queue.json").exists()


def test_enqueue_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as d:
        q = ApprovalQueue(Path(d))
        a = q.enqueue(tier="red", kind="code", target="core/x.py", title="T", body="b")
        b = q.enqueue(tier="red", kind="code", target="core/x.py", title="T", body="b")
        assert a == b, "an identical still-pending item must not be queued twice"
        assert len(q.pending()) == 1


# ── code-drafting path (proposer wired in) — stubbed, no Ollama ───────────
class _FakeCoder:
    """Stands in for SelfImprovementProposer: deterministic, no model calls."""
    def __init__(self, content="x = 2\n# improved\n", ready=True, can=True):
        self._content, self._ready, self._can = content, ready, can
        self._pending = None
        self._engine = None      # → EDITH's direct write-with-backup path

    def _can_modify(self, _file):
        return (self._can, "ok" if self._can else "outside core/ or plugins/")

    def propose_and_test(self, file, instruction, simulations=3):
        if not self._ready:
            return {"ready_to_apply": False, "status": "failed", "diff": "",
                    "error": "SyntaxError: bad token", "why": "the draft did not compile"}
        self._pending = {"file": file, "content": self._content, "instruction": instruction}
        return {"ready_to_apply": True, "status": "ready", "why": "passed all 4 checks",
                "diff": "--- a\n+++ b\n+improved", "simulations": []}


def _edith_with_coder(tmp: Path, coder: _FakeCoder) -> Edith:
    return Edith(vault=Vault(root=tmp), proposer=coder)


def test_propose_code_queues_passing_draft() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        target = tmp / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        e = _edith_with_coder(tmp, _FakeCoder())
        res = e.propose_code(str(target), "bump x to 2")
        assert res["status"] == "queued", res
        pend = e.pending()
        assert len(pend) == 1 and pend[0]["kind"] == "code"
        assert pend[0]["tier"] == "red" and pend[0]["has_payload"] is True


def test_approve_code_patches_file_then_rollback_restores() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        target = tmp / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        e = _edith_with_coder(tmp, _FakeCoder("x = 2\n# improved\n"))
        iid = e.propose_code(str(target), "bump x")["queued_id"]

        approved = e.approve(iid)
        assert approved["status"] == APPLIED, approved
        assert target.read_text(encoding="utf-8") == "x = 2\n# improved\n", \
            "approving a code item must patch the real file"

        rolled = e.rollback(iid)
        assert rolled["status"] == ROLLED_BACK, rolled
        assert target.read_text(encoding="utf-8") == "x = 1\n", \
            "rollback must restore the original source"


def test_propose_code_forbidden_target_never_drafts() -> None:
    with tempfile.TemporaryDirectory() as d:
        e = _edith_with_coder(Path(d), _FakeCoder())
        for bad in ("core/edith.py", "training/security_harness.py", "core/safety.py"):
            res = e.propose_code(bad, "loosen it")
            assert res["status"] == "rejected", (bad, res)
        assert e.pending() == [], "the un-gameable rule must hold before any drafting"


def test_propose_code_failed_sandbox_not_queued() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        target = tmp / "target.py"
        target.write_text("x = 1\n", encoding="utf-8")
        e = _edith_with_coder(tmp, _FakeCoder(ready=False))
        res = e.propose_code(str(target), "bump x")
        assert res["status"] == "failed", res
        assert e.pending() == [], "a draft that fails the sandbox must never be queued"


def main() -> None:
    tests = [
        ("red pass is queued, not applied", test_red_pass_is_queued_not_applied),
        ("approve applies, rollback undoes", test_approve_applies_then_rollback_undoes),
        ("reject discards, writes nothing", test_reject_discards_and_writes_nothing),
        ("batch approve digest", test_batch_approve_digest),
        ("un-gameable change never queued", test_ungameable_change_never_queued),
        ("dry run queues nothing", test_dry_run_queues_nothing),
        ("enqueue is idempotent", test_enqueue_is_idempotent),
        ("propose_code queues a passing draft", test_propose_code_queues_passing_draft),
        ("approve code patches file, rollback restores",
         test_approve_code_patches_file_then_rollback_restores),
        ("propose_code forbidden target never drafts", test_propose_code_forbidden_target_never_drafts),
        ("propose_code failed sandbox not queued", test_propose_code_failed_sandbox_not_queued),
    ]
    print("=" * 64)
    print(" EDITH APPROVAL-QUEUE TESTS")
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
