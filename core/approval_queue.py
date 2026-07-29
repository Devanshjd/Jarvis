"""
J.A.R.V.I.S — Approval Queue  (the human gate, made real & batchable)

EDITH's red-tier changes PASS the sandbox but still need your eyes. Instead of
dropping them (the old behaviour), EDITH parks them HERE. You then approve or
reject — one at a time, or the whole batch in one shot (the "digest"). Every
apply is backed up so it can be rolled back, and every action lands in an
append-only audit log.

This module is deliberately dumb: it persists items + their status and knows how
to back up / restore a file for rollback. It does NOT know how to *produce* a
change — EDITH supplies the apply/rollback callbacks. That keeps the risky "what
does applying actually do" logic in one place (edith.py) and this store generic
and easy to test.

State lives beside the vault (honours $JARVIS_VAULT):
  <vault>/.jarvis_approval_queue.json    — the queue (dotfile; Obsidian ignores)
  <vault>/.jarvis_approval_audit.jsonl   — append-only audit trail
  <vault>/.jarvis_backups/<id>/          — pre-change file backups (rollback)
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

# Status lifecycle: pending → (applied | rejected | failed); applied → rolled_back
PENDING = "pending"
APPLIED = "applied"
REJECTED = "rejected"
ROLLED_BACK = "rolled_back"
FAILED = "failed"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class QueueItem:
    id: str
    created_at: str
    status: str
    tier: str
    kind: str
    target: str
    title: str
    body: str
    reason: str = ""
    proof: dict = field(default_factory=dict)
    source: str = "EDITH"
    decided_at: str = ""
    applied_to: str = ""
    backup: Optional[dict] = None
    error: str = ""

    def public(self) -> dict:
        """Serialisable view for the API/UI, plus a short one-line preview."""
        d = asdict(self)
        d["preview"] = " ".join((self.body or "").split())[:160]
        return d


@dataclass
class ApplyResult:
    """What an apply callback returns: where it wrote, and how to undo it."""
    applied_to: str = ""
    backup: Optional[dict] = None


ApplyFn = Callable[[QueueItem], ApplyResult]
RollbackFn = Callable[[QueueItem], None]


class ApprovalQueue:
    def __init__(self, root: Optional[Path] = None) -> None:
        if root is None:
            try:
                from core.vault import vault_root
            except ImportError:  # run as a script from core/
                from vault import vault_root
            root = vault_root()
        self.root = Path(root)
        self.path = self.root / ".jarvis_approval_queue.json"
        self.audit_path = self.root / ".jarvis_approval_audit.jsonl"
        self.backup_dir = self.root / ".jarvis_backups"
        self._lock = threading.RLock()   # backend is multi-threaded

    # ── persistence (atomic) ─────────────────────────────────────────────
    def _load(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("items", [])
        except Exception:
            return []

    def _save(self, items: list[dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"items": items}, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)      # atomic swap

    def _audit(self, action: str, it: dict) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            rec = {"ts": _now(), "action": action, "id": it.get("id"),
                   "status": it.get("status"), "kind": it.get("kind"),
                   "target": it.get("target"), "applied_to": it.get("applied_to", ""),
                   "error": it.get("error", "")}
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception:
            pass

    @staticmethod
    def _find(items: list[dict], iid: str) -> Optional[dict]:
        return next((it for it in items if it.get("id") == iid), None)

    # ── enqueue ──────────────────────────────────────────────────────────
    def enqueue(self, *, tier: str, kind: str, target: str, title: str, body: str,
                reason: str = "", proof: Optional[dict] = None,
                source: str = "EDITH") -> str:
        """Park a gated change. Idempotent: an identical still-pending item is not
        queued twice (repeated improvement passes don't pile duplicates)."""
        with self._lock:
            items = self._load()
            for it in items:
                if (it.get("status") == PENDING and it.get("kind") == kind
                        and it.get("target") == target and it.get("title") == title):
                    return it["id"]
            iid = uuid.uuid4().hex[:8]
            it = asdict(QueueItem(id=iid, created_at=_now(), status=PENDING,
                                  tier=str(tier), kind=kind, target=target,
                                  title=title, body=body, reason=reason,
                                  proof=proof or {}, source=source))
            items.append(it)
            self._save(items)
            self._audit("enqueue", it)
            return iid

    # ── read ─────────────────────────────────────────────────────────────
    def pending(self) -> list[dict]:
        with self._lock:
            return [QueueItem(**it).public()
                    for it in self._load() if it.get("status") == PENDING]

    def all(self, limit: int = 100) -> list[dict]:
        with self._lock:
            items = self._load()
        return [QueueItem(**it).public() for it in items[-limit:]][::-1]

    def counts(self) -> dict:
        with self._lock:
            items = self._load()
        out: dict = {}
        for it in items:
            s = it.get("status", "?")
            out[s] = out.get(s, 0) + 1
        return out

    # ── decide (single) ──────────────────────────────────────────────────
    def approve(self, iid: str, apply_fn: ApplyFn) -> dict:
        with self._lock:
            items = self._load()
            it = self._find(items, iid)
            if not it:
                return {"error": f"no such item {iid}"}
            if it["status"] != PENDING:
                return {"error": f"item {iid} is '{it['status']}', not pending"}
            try:
                res = apply_fn(QueueItem(**it))
                it.update(status=APPLIED, applied_to=res.applied_to,
                          backup=res.backup, decided_at=_now(), error="")
                action = "approve"
            except Exception as exc:
                it.update(status=FAILED, error=str(exc)[:200], decided_at=_now())
                action = "approve_failed"
            self._save(items)
            self._audit(action, it)
            return QueueItem(**it).public()

    def reject(self, iid: str) -> dict:
        with self._lock:
            items = self._load()
            it = self._find(items, iid)
            if not it:
                return {"error": f"no such item {iid}"}
            if it["status"] != PENDING:
                return {"error": f"item {iid} is '{it['status']}', not pending"}
            it.update(status=REJECTED, decided_at=_now())
            self._save(items)
            self._audit("reject", it)
            return QueueItem(**it).public()

    def rollback(self, iid: str, rollback_fn: RollbackFn) -> dict:
        with self._lock:
            items = self._load()
            it = self._find(items, iid)
            if not it:
                return {"error": f"no such item {iid}"}
            if it["status"] != APPLIED:
                return {"error": f"item {iid} is '{it['status']}'; only applied items roll back"}
            try:
                rollback_fn(QueueItem(**it))
                it.update(status=ROLLED_BACK, decided_at=_now(), error="")
                action = "rollback"
            except Exception as exc:
                it.update(error=str(exc)[:200])
                action = "rollback_failed"
            self._save(items)
            self._audit(action, it)
            return QueueItem(**it).public()

    # ── decide (batch — the "digest") ────────────────────────────────────
    def approve_all(self, apply_fn: ApplyFn) -> dict:
        results = [self.approve(it["id"], apply_fn) for it in self.pending()]
        return {"count": len(results), "results": results}

    def reject_all(self) -> dict:
        results = [self.reject(it["id"]) for it in self.pending()]
        return {"count": len(results), "results": results}

    # ── rollback support: snapshot before overwrite, restore to undo ──────
    def backup_file(self, iid: str, path: Path) -> dict:
        """Snapshot a file before it's overwritten (or mark 'new' if it doesn't
        exist yet). Returns a descriptor stored on the item for rollback."""
        path = Path(path)
        if not path.exists():
            return {"kind": "new", "path": str(path)}
        dest = self.backup_dir / iid
        dest.mkdir(parents=True, exist_ok=True)
        bak = dest / path.name
        shutil.copy2(path, bak)
        return {"kind": "restore", "path": str(path), "from": str(bak)}

    @staticmethod
    def restore_backup(backup: Optional[dict]) -> None:
        if not backup:
            return
        if backup.get("kind") == "new":
            p = Path(backup["path"])
            if p.exists():
                p.unlink()
        elif backup.get("kind") == "restore":
            src, dst = Path(backup["from"]), Path(backup["path"])
            if src.exists():
                shutil.copy2(src, dst)
