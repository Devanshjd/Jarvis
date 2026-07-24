"""
J.A.R.V.I.S — Semantic (Vector) Memory

Gives JARVIS memory that recalls by MEANING, not keywords. "What did we decide
about the Stormbreaker budget?" retrieves the right past turn even with zero
word overlap — that's the jump from keyword search to genuine recall.

100% local:
  · Embeddings via Ollama (`nomic-embed-text`) — no cloud, no API key.
  · Storage in a local SQLite DB; vectors kept as float32 blobs.
  · Search is brute-force cosine over a numpy matrix — instant for the
    thousands of memories a personal assistant accumulates.

Usage:
    from core.vector_memory import get_vector_memory
    vm = get_vector_memory()
    vm.add("Stormbreaker budget is £80-100/month", {"kind": "decision"})
    hits = vm.search("how much are we spending on the goggles", k=3)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.vector_memory")

VM_DIR = Path.home() / ".jarvis" / "vector_memory"
DB_PATH = VM_DIR / "memory.db"
EMBED_MODEL = "nomic-embed-text"
OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embeddings"


class VectorMemory:
    def __init__(self):
        VM_DIR.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS memories ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  text TEXT NOT NULL,"
            "  metadata TEXT,"
            "  embedding BLOB NOT NULL,"
            "  created REAL"
            ")"
        )
        self._db.commit()
        self._dim: Optional[int] = None

    # ─── Embedding ────────────────────────────────────────────────────────
    def embed(self, text: str):
        """Return a float32 numpy vector for `text` via local Ollama. None on
        failure (so callers degrade gracefully)."""
        import numpy as np
        try:
            import requests
            r = requests.post(OLLAMA_EMBED_URL,
                              json={"model": EMBED_MODEL, "prompt": text[:4000]},
                              timeout=30)
            if r.status_code != 200:
                return None
            vec = r.json().get("embedding")
            if not vec:
                return None
            arr = np.asarray(vec, dtype=np.float32)
            n = np.linalg.norm(arr)
            return arr / n if n > 0 else arr        # unit-normalise for cosine
        except Exception as exc:
            logger.debug("embed failed: %s", exc)
            return None

    # ─── Write ────────────────────────────────────────────────────────────
    def add(self, text: str, metadata: Optional[dict] = None) -> bool:
        text = (text or "").strip()
        if len(text) < 3:
            return False
        vec = self.embed(text)
        if vec is None:
            return False
        self._db.execute(
            "INSERT INTO memories (text, metadata, embedding, created) VALUES (?,?,?,?)",
            (text, json.dumps(metadata or {}), vec.tobytes(), time.time()),
        )
        self._db.commit()
        return True

    def remember_turn(self, user_msg: str, assistant_reply: str) -> None:
        """Store a conversation turn (best-effort). Skips trivial chit-chat."""
        u = (user_msg or "").strip()
        if len(u) < 8:
            return
        self.add(f"User asked: {u}\nJARVIS answered: {(assistant_reply or '')[:600]}",
                 {"kind": "conversation"})

    # ─── Search ───────────────────────────────────────────────────────────
    def search(self, query: str, k: int = 4, min_score: float = 0.35) -> list[dict]:
        """Return up to k memories most semantically similar to `query`."""
        import numpy as np
        qv = self.embed(query)
        if qv is None:
            return []
        rows = self._db.execute(
            "SELECT id, text, metadata, embedding FROM memories").fetchall()
        if not rows:
            return []
        mat = np.stack([np.frombuffer(r[3], dtype=np.float32) for r in rows])
        # rows are unit-normalised already, so dot product == cosine similarity.
        scores = mat @ qv
        order = np.argsort(-scores)[:k]
        out = []
        for i in order:
            score = float(scores[i])
            if score < min_score:
                continue
            rid, text, meta, _ = rows[i]
            out.append({
                "id": rid, "text": text,
                "metadata": json.loads(meta or "{}"),
                "score": round(score, 3),
            })
        return out

    def recall_context(self, query: str, k: int = 3) -> str:
        """A compact string of relevant memories to inject into a prompt."""
        hits = self.search(query, k=k)
        if not hits:
            return ""
        lines = ["Relevant things you remember:"]
        lines += [f"- {h['text'][:300]}" for h in hits]
        return "\n".join(lines)

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]


_vm: Optional[VectorMemory] = None


def get_vector_memory() -> VectorMemory:
    global _vm
    if _vm is None:
        _vm = VectorMemory()
    return _vm
