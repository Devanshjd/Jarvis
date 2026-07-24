"""
J.A.R.V.I.S — Codebase Oracle (local RAG over a repository)

Index a repo once, then ask it questions in plain English — "where is auth
handled?", "what does the recon pipeline do?" — and get an answer grounded in
the actual code, with file:line citations.

Two payoffs for Devansh:
  · Bug bounty — point it at a target's public source, ask where the risky
    surface is, jump straight to the interesting files.
  · Self-improvement — JARVIS understands its OWN code before it proposes a
    fix, so the self-modify loop drafts smarter changes.

100% local: embeddings via Ollama `nomic-embed-text`, answer via the local
code model (qwen2.5-coder if present). Nothing leaves the machine.

Store: ~/.jarvis/code_oracle/index.db  (one DB, many repos via a `repo` column)
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.code_oracle")

ORACLE_DIR = Path.home() / ".jarvis" / "code_oracle"
DB_PATH = ORACLE_DIR / "index.db"
EMBED_MODEL = "nomic-embed-text"
OLLAMA = "http://127.0.0.1:11434"

CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c",
             ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt",
             ".md", ".json", ".yaml", ".yml", ".toml", ".sh"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "out", ".venv", "venv",
             "__pycache__", ".next", ".cache", "vendor", "target",
             ".jarvis_backups", ".jarvis_sandbox"}
CHUNK_LINES = 50          # lines per chunk
CHUNK_OVERLAP = 8
MAX_FILE_KB = 400
MAX_CHUNKS = 4000         # safety cap per index run


def _embed(text: str):
    import numpy as np
    try:
        import requests
        r = requests.post(f"{OLLAMA}/api/embeddings",
                          json={"model": EMBED_MODEL, "prompt": text[:4000]}, timeout=30)
        if r.status_code != 200:
            return None
        v = r.json().get("embedding")
        if not v:
            return None
        a = np.asarray(v, dtype=np.float32)
        n = np.linalg.norm(a)
        return a / n if n > 0 else a
    except Exception:
        return None


class CodeOracle:
    def __init__(self, jarvis=None):
        self.jarvis = jarvis
        ORACLE_DIR.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS chunks ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  repo TEXT, file TEXT, start_line INTEGER, end_line INTEGER,"
            "  text TEXT, embedding BLOB)")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_repo ON chunks(repo)")
        self._db.commit()

    @staticmethod
    def _repo_key(repo_path: str) -> str:
        return hashlib.sha1(str(Path(repo_path).resolve()).encode()).hexdigest()[:12]

    # ─── Indexing ─────────────────────────────────────────────────────────
    def index_repo(self, repo_path: str) -> dict:
        root = Path(repo_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return {"success": False, "error": f"Not a directory: {root}"}
        repo = self._repo_key(str(root))

        # Clear any prior index for this repo (re-index fresh).
        self._db.execute("DELETE FROM chunks WHERE repo=?", (repo,))
        self._db.commit()

        files_indexed = 0
        chunks_added = 0
        t0 = time.time()
        for path in root.rglob("*"):
            if chunks_added >= MAX_CHUNKS:
                break
            if not path.is_file() or path.suffix.lower() not in CODE_EXTS:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            try:
                if path.stat().st_size > MAX_FILE_KB * 1024:
                    continue
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            if not lines:
                continue
            rel = str(path.relative_to(root))
            i = 0
            while i < len(lines) and chunks_added < MAX_CHUNKS:
                chunk_lines = lines[i:i + CHUNK_LINES]
                text = "\n".join(chunk_lines).strip()
                if len(text) >= 20:
                    header = f"// file: {rel} (lines {i+1}-{i+len(chunk_lines)})\n"
                    vec = _embed(header + text)
                    if vec is not None:
                        self._db.execute(
                            "INSERT INTO chunks (repo,file,start_line,end_line,text,embedding)"
                            " VALUES (?,?,?,?,?,?)",
                            (repo, rel, i + 1, i + len(chunk_lines), text, vec.tobytes()))
                        chunks_added += 1
                i += CHUNK_LINES - CHUNK_OVERLAP
            files_indexed += 1
        self._db.commit()
        return {"success": True, "repo": repo, "root": str(root),
                "files_indexed": files_indexed, "chunks": chunks_added,
                "elapsed_s": round(time.time() - t0, 1),
                "capped": chunks_added >= MAX_CHUNKS}

    # ─── Retrieval + answer ───────────────────────────────────────────────
    def _retrieve(self, repo: str, question: str, k: int) -> list[dict]:
        import numpy as np
        qv = _embed(question)
        if qv is None:
            return []
        rows = self._db.execute(
            "SELECT file,start_line,end_line,text,embedding FROM chunks WHERE repo=?",
            (repo,)).fetchall()
        if not rows:
            return []
        mat = np.stack([np.frombuffer(r[4], dtype=np.float32) for r in rows])
        scores = mat @ qv
        order = np.argsort(-scores)[:k]
        return [{"file": rows[i][0], "start": rows[i][1], "end": rows[i][2],
                 "text": rows[i][3], "score": round(float(scores[i]), 3)}
                for i in order]

    def ask(self, repo_path: str, question: str, k: int = 6) -> dict:
        repo = self._repo_key(repo_path)
        count = self._db.execute("SELECT COUNT(*) FROM chunks WHERE repo=?", (repo,)).fetchone()[0]
        if count == 0:
            return {"success": False,
                    "error": "This repo isn't indexed yet. Run index first.",
                    "answer": ""}
        hits = self._retrieve(repo, question, k)
        if not hits:
            return {"success": False, "error": "No relevant code found.", "answer": ""}

        context = "\n\n".join(
            f"// {h['file']} (lines {h['start']}-{h['end']})\n{h['text']}" for h in hits)
        model = self._code_model()
        answer = ""
        try:
            import requests
            r = requests.post(
                f"{OLLAMA}/api/chat",
                json={"model": model, "stream": False, "keep_alive": "5m",
                      "options": {"temperature": 0.2, "num_predict": 600},
                      "messages": [
                          {"role": "system", "content":
                           "You answer questions about a codebase using ONLY the provided "
                           "code excerpts. Each excerpt starts with a header comment giving its "
                           "real filename and line range — cite THAT exact filename and lines "
                           "for each claim, e.g. (recon_pipeline.py:127-134). Never write a "
                           "placeholder like file.py. If the excerpts don't contain the answer, "
                           "say so — do not invent code."},
                          {"role": "user", "content":
                           f"CODE EXCERPTS:\n{context}\n\nQUESTION: {question}\n\nAnswer with citations:"}]},
                timeout=120)
            if r.status_code == 200:
                answer = (r.json().get("message", {}).get("content") or "").strip()
        except Exception as e:
            answer = f"(local reasoning error: {e})"
        return {"success": True, "answer": answer,
                "sources": [{"file": h["file"], "lines": f"{h['start']}-{h['end']}",
                             "score": h["score"]} for h in hits]}

    def _code_model(self) -> str:
        try:
            import requests
            r = requests.get(f"{OLLAMA}/api/tags", timeout=5)
            names = {m.get("name", "") for m in r.json().get("models", [])} if r.ok else set()
            for pref in ("qwen2.5-coder:7b", "qwen2.5-coder", "gemma3:4b"):
                for n in names:
                    if n == pref or n.startswith(pref):
                        return n
        except Exception:
            pass
        return "gemma3:4b"

    def context_for(self, repo_path: str, query: str, k: int = 3) -> str:
        """Retrieval-only (no LLM): return the most relevant code chunks as a
        context string. Used by the self-modify proposer to understand related
        code before drafting a fix."""
        repo = self._repo_key(repo_path)
        hits = self._retrieve(repo, query, k)
        if not hits:
            return ""
        return "\n\n".join(
            f"// {h['file']} (lines {h['start']}-{h['end']})\n{h['text']}" for h in hits)

    def indexed_repos(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT repo, COUNT(*) FROM chunks GROUP BY repo").fetchall()
        return [{"repo": r[0], "chunks": r[1]} for r in rows]


_oracle: Optional[CodeOracle] = None


def get_oracle(jarvis=None) -> CodeOracle:
    global _oracle
    if _oracle is None:
        _oracle = CodeOracle(jarvis)
    return _oracle
