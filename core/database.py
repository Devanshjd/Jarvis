"""
J.A.R.V.I.S — Unified Memory Database
Single SQLite database replacing all scattered JSON files.

Tables:
  conversations  — full-text searchable conversation history (unlimited)
  memories       — operator-provided facts with FTS search
  episodes       — task execution history (procedural memory)
  procedures     — aggregated tool usage stats
  kv_store       — key-value for identity, preferences, learner, intelligence, task_memory

Migration: auto-imports existing JSON files on first run, then they become read-only backups.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


DB_PATH = Path.home() / ".jarvis_memory.db"

# ═══════════════════════════════════════════════════════════
#  Thread-safe connection pool
# ═══════════════════════════════════════════════════════════

_local = threading.local()
_db_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return _local.conn


def _ensure_schema():
    """Create all tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        -- Training data: learned tool interactions
        CREATE TABLE IF NOT EXISTS training_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_input TEXT NOT NULL,
            tool_used TEXT NOT NULL,
            tool_params TEXT DEFAULT '{}',
            response TEXT DEFAULT '',
            success INTEGER DEFAULT 1,
            source TEXT DEFAULT 'manual',
            example_type TEXT DEFAULT 'direct',
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Evolution log: diagnostics, self-updates, system events
        CREATE TABLE IF NOT EXISTS evolution_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Test results: smoke test / integration test outcomes
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PASS',
            error TEXT DEFAULT '',
            suite TEXT DEFAULT 'smoke',
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Conversations: full chat history with FTS
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL,
            tool_used TEXT DEFAULT '',
            source TEXT DEFAULT 'text',
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Memories: explicit "remember this" facts
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL UNIQUE,
            category TEXT DEFAULT 'general',
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Episodes: task execution log (procedural memory)
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT DEFAULT '',
            goal TEXT NOT NULL,
            tool TEXT NOT NULL,
            args TEXT DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'completed',
            step TEXT DEFAULT '',
            attempts INTEGER DEFAULT 1,
            result TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Procedures: aggregated tool stats
        CREATE TABLE IF NOT EXISTS procedures (
            tool_name TEXT PRIMARY KEY,
            successes INTEGER DEFAULT 0,
            failures INTEGER DEFAULT 0,
            cancelled INTEGER DEFAULT 0,
            attempt_total INTEGER DEFAULT 0,
            attempt_samples INTEGER DEFAULT 0,
            arg_counts TEXT DEFAULT '{}',
            sample_goals TEXT DEFAULT '[]',
            recent_results TEXT DEFAULT '[]',
            last_status TEXT DEFAULT '',
            last_used TEXT DEFAULT ''
        );

        -- Key-Value store for structured data blobs
        -- namespace: identity, preferences, task_memory, learner, intelligence_feedback,
        --            intelligence_patterns, intelligence_emotional
        CREATE TABLE IF NOT EXISTS kv_store (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (namespace, key)
        );

        -- Tool execution outcomes for reliability tracking and learning
        CREATE TABLE IF NOT EXISTS tool_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            execution_mode TEXT DEFAULT 'direct',
            success INTEGER NOT NULL DEFAULT 0,
            latency_ms REAL DEFAULT 0,
            error_class TEXT DEFAULT '',
            timestamp TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_tool_outcomes_name
            ON tool_outcomes(tool_name);
        CREATE INDEX IF NOT EXISTS idx_tool_outcomes_ts
            ON tool_outcomes(timestamp);
    """)

    # FTS tables for search (created separately — can't use IF NOT EXISTS with virtual)
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts
            USING fts5(user_text, assistant_text, content=conversations, content_rowid=id)
        """)
    except sqlite3.OperationalError:
        pass  # Already exists

    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(content, content=memories, content_rowid=id)
        """)
    except sqlite3.OperationalError:
        pass

    conn.commit()


# ═══════════════════════════════════════════════════════════
#  Database API
# ═══════════════════════════════════════════════════════════

class JarvisDB:
    """Unified database interface for all JARVIS memory systems."""

    _initialized = False
    _migrated = False

    def __init__(self):
        if not JarvisDB._initialized:
            _ensure_schema()
            JarvisDB._initialized = True
            if not JarvisDB._migrated:
                self._migrate_json_files()
                JarvisDB._migrated = True

    # ─── Conversations ────────────────────────────────────

    def save_conversation(self, user_text: str, assistant_text: str,
                          tool_used: str = "", source: str = "text") -> int:
        """Save a conversation exchange. Returns the row ID."""
        conn = _get_conn()
        with _db_lock:
            cur = conn.execute(
                "INSERT INTO conversations (user_text, assistant_text, tool_used, source) VALUES (?, ?, ?, ?)",
                (user_text[:2000], assistant_text[:2000], tool_used, source)
            )
            conn.commit()

            # Update FTS index
            try:
                conn.execute(
                    "INSERT INTO conversations_fts (rowid, user_text, assistant_text) VALUES (?, ?, ?)",
                    (cur.lastrowid, user_text[:2000], assistant_text[:2000])
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass

            return cur.lastrowid

    def search_conversations(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search across all conversations."""
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT c.id, c.user_text, c.assistant_text, c.tool_used, c.source, c.created_at
                   FROM conversations_fts f
                   JOIN conversations c ON c.id = f.rowid
                   WHERE conversations_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit)
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            # Fallback to LIKE search if FTS fails
            rows = conn.execute(
                """SELECT id, user_text, assistant_text, tool_used, source, created_at
                   FROM conversations
                   WHERE user_text LIKE ? OR assistant_text LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_conversations(self, limit: int = 15) -> list[dict]:
        """Get most recent conversations."""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, user_text, assistant_text, tool_used, source, created_at FROM conversations ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_conversation_count(self) -> int:
        conn = _get_conn()
        return conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]

    def get_conversations_context(self, max_exchanges: int = 15) -> str:
        """Format recent conversations for LLM context injection."""
        recent = self.get_recent_conversations(max_exchanges)
        if not recent:
            return ""
        lines = ["[CONVERSATION MEMORY — past exchanges from previous sessions]"]
        for c in recent:
            ts = c["created_at"][:16].replace("T", " ") if c.get("created_at") else ""
            lines.append(f"  [{ts}] User: {c['user_text']}")
            lines.append(f"  [{ts}] JARVIS: {c['assistant_text']}")
        lines.append("[END CONVERSATION MEMORY]")
        return "\n".join(lines)

    # ─── Memories ─────────────────────────────────────────

    def save_memory(self, content: str, category: str = "general") -> bool:
        """Save an explicit memory. Returns False if duplicate."""
        conn = _get_conn()
        try:
            with _db_lock:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO memories (content, category) VALUES (?, ?)",
                    (content.strip(), category)
                )
                conn.commit()
                if cur.lastrowid:
                    try:
                        conn.execute(
                            "INSERT INTO memories_fts (rowid, content) VALUES (?, ?)",
                            (cur.lastrowid, content.strip())
                        )
                        conn.commit()
                    except sqlite3.OperationalError:
                        pass
                return cur.rowcount > 0
        except sqlite3.IntegrityError:
            return False

    def search_memories(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search memories."""
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT m.id, m.content, m.category, m.created_at
                   FROM memories_fts f
                   JOIN memories m ON m.id = f.rowid
                   WHERE memories_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, limit)
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            rows = conn.execute(
                "SELECT id, content, category, created_at FROM memories WHERE content LIKE ? LIMIT ?",
                (f"%{query}%", limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_memories(self, limit: int = 100) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, content, category, created_at FROM memories ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def remove_memory(self, memory_id: int) -> bool:
        conn = _get_conn()
        with _db_lock:
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return True

    def get_memory_count(self) -> int:
        conn = _get_conn()
        return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def get_memories_context(self) -> str:
        """Format memories for LLM context injection."""
        mems = self.get_all_memories(30)
        if not mems:
            return ""
        lines = ["[OPERATOR MEMORIES — things you were told to remember]"]
        for m in mems:
            lines.append(f"  • {m['content']}")
        lines.append("[END OPERATOR MEMORIES]")
        return "\n".join(lines)

    # ─── Episodes (Task Brain) ────────────────────────────

    def record_episode(self, *, goal: str, tool: str, args: dict | None = None,
                       status: str = "completed", result: str = "",
                       attempts: int = 1, step: str = "",
                       session_id: str = "") -> int:
        """Record a task execution episode."""
        conn = _get_conn()
        safe_args = json.dumps(self._sanitize_args(args or {}))
        with _db_lock:
            cur = conn.execute(
                """INSERT INTO episodes (session_id, goal, tool, args, status, step, attempts, result)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, goal[:300], tool, safe_args, status, step, attempts, result[:500])
            )
            conn.commit()

            # Update procedure stats
            self._update_procedure(tool, status, goal, result, attempts, args)

            return cur.lastrowid

    def get_recent_episodes(self, limit: int = 10) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM episodes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_episodes_for_tool(self, tool: str, limit: int = 10) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM episodes WHERE tool = ? ORDER BY id DESC LIMIT ?",
            (tool, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_episode_count(self) -> int:
        conn = _get_conn()
        return conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]

    def get_episode_stats(self) -> dict:
        conn = _get_conn()
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as successes,
                   SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failures,
                   SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) as cancelled
            FROM episodes
        """).fetchone()
        return dict(row)

    # ─── Procedures ───────────────────────────────────────

    def _update_procedure(self, tool: str, status: str, goal: str,
                          result: str, attempts: int, args: dict | None):
        """Update aggregated procedure stats for a tool."""
        conn = _get_conn()
        existing = conn.execute(
            "SELECT * FROM procedures WHERE tool_name = ?", (tool,)
        ).fetchone()

        if existing:
            data = dict(existing)
            if status == "completed":
                data["successes"] += 1
            elif status == "failed":
                data["failures"] += 1
            elif status == "cancelled":
                data["cancelled"] += 1

            data["attempt_total"] += attempts
            data["attempt_samples"] += 1
            data["last_status"] = status
            data["last_used"] = datetime.now().isoformat()

            # Update sample goals (keep last 10)
            goals = json.loads(data["sample_goals"])
            if goal and goal not in goals:
                goals.append(goal[:120])
                goals = goals[-10:]

            # Update recent results (keep last 10)
            results = json.loads(data["recent_results"])
            if result:
                results.append(result[:120])
                results = results[-10:]

            # Update arg counts
            arg_counts = json.loads(data["arg_counts"])
            if args:
                for k in args:
                    arg_counts[k] = arg_counts.get(k, 0) + 1

            conn.execute(
                """UPDATE procedures SET successes=?, failures=?, cancelled=?,
                   attempt_total=?, attempt_samples=?, arg_counts=?,
                   sample_goals=?, recent_results=?, last_status=?, last_used=?
                   WHERE tool_name=?""",
                (data["successes"], data["failures"], data["cancelled"],
                 data["attempt_total"], data["attempt_samples"],
                 json.dumps(arg_counts), json.dumps(goals), json.dumps(results),
                 data["last_status"], data["last_used"], tool)
            )
        else:
            s = 1 if status == "completed" else 0
            f = 1 if status == "failed" else 0
            c = 1 if status == "cancelled" else 0
            arg_counts = {}
            if args:
                arg_counts = {k: 1 for k in args}
            conn.execute(
                """INSERT INTO procedures (tool_name, successes, failures, cancelled,
                   attempt_total, attempt_samples, arg_counts, sample_goals,
                   recent_results, last_status, last_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tool, s, f, c, attempts, 1, json.dumps(arg_counts),
                 json.dumps([goal[:120]] if goal else []),
                 json.dumps([result[:120]] if result else []),
                 status, datetime.now().isoformat())
            )
        conn.commit()

    def get_procedure(self, tool: str) -> dict | None:
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM procedures WHERE tool_name = ?", (tool,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_procedures(self, min_uses: int = 2) -> list[dict]:
        conn = _get_conn()
        rows = conn.execute(
            """SELECT * FROM procedures
               WHERE (successes + failures + cancelled) >= ?
               ORDER BY last_used DESC""",
            (min_uses,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Key-Value Store ──────────────────────────────────

    def kv_set(self, namespace: str, key: str, value: Any):
        """Store a value in the KV store (auto-serializes to JSON)."""
        conn = _get_conn()
        v = json.dumps(value) if not isinstance(value, str) else value
        with _db_lock:
            conn.execute(
                """INSERT INTO kv_store (namespace, key, value, updated_at)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(namespace, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (namespace, key, v)
            )
            conn.commit()

    def kv_get(self, namespace: str, key: str, default: Any = None) -> Any:
        """Get a value from the KV store (auto-deserializes from JSON)."""
        conn = _get_conn()
        row = conn.execute(
            "SELECT value FROM kv_store WHERE namespace = ? AND key = ?",
            (namespace, key)
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return row[0]

    def kv_get_all(self, namespace: str) -> dict:
        """Get all key-value pairs in a namespace."""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT key, value FROM kv_store WHERE namespace = ?", (namespace,)
        ).fetchall()
        result = {}
        for r in rows:
            try:
                result[r[0]] = json.loads(r[1])
            except (json.JSONDecodeError, TypeError):
                result[r[0]] = r[1]
        return result

    def kv_delete(self, namespace: str, key: str):
        conn = _get_conn()
        with _db_lock:
            conn.execute(
                "DELETE FROM kv_store WHERE namespace = ? AND key = ?",
                (namespace, key)
            )
            conn.commit()

    # ─── Full Context for LLM ─────────────────────────────

    def get_full_memory_context(self) -> str:
        """
        Bundle ALL persistent memory into a single context block.
        Used for Gemini Live session injection.
        """
        sections = []

        # Identity
        identity = self.kv_get_all("identity")
        if identity:
            parts = [f"[IDENTITY] {identity.get('name', 'User')}"]
            for k in ["full_name", "age", "location", "occupation", "university", "origin"]:
                if identity.get(k):
                    parts.append(f"  {k}: {identity[k]}")
            interests = identity.get("interests", [])
            if interests:
                parts.append(f"  interests: {', '.join(interests)}")
            notes = identity.get("personality_notes", [])
            if notes:
                parts.append(f"  notes: {'; '.join(notes[-5:])}")
            sections.append("\n".join(parts))

        # Preferences
        prefs = self.kv_get_all("preferences")
        if prefs:
            parts = ["[PREFERENCES]"]
            for k, v in prefs.items():
                if v and k != "custom":
                    parts.append(f"  {k}: {v}")
            custom = prefs.get("custom", {})
            if isinstance(custom, dict):
                for k, v in custom.items():
                    parts.append(f"  {k}: {v}")
            sections.append("\n".join(parts))

        # Task memory
        task_mem = self.kv_get_all("task_memory")
        if task_mem:
            parts = ["[TASK CONTEXT]"]
            if task_mem.get("last_context"):
                parts.append(f"  Last working on: {task_mem['last_context']}")
            if task_mem.get("last_topic"):
                parts.append(f"  Last topic: {task_mem['last_topic']}")
            pending = task_mem.get("pending_actions", [])
            if isinstance(pending, list) and pending:
                undone = [a for a in pending if isinstance(a, dict) and not a.get("done")]
                if undone:
                    parts.append(f"  Pending actions ({len(undone)}):")
                    for a in undone[:5]:
                        parts.append(f"    - {a.get('action', '?')}")
            sections.append("\n".join(parts))

        # Learner profile
        learner = self.kv_get_all("learner")
        if learner:
            parts = ["[OPERATOR PROFILE]"]
            if learner.get("total_messages"):
                parts.append(f"  Total messages: {learner['total_messages']}")
            if learner.get("total_sessions"):
                parts.append(f"  Total sessions: {learner['total_sessions']}")
            topics = learner.get("topics", {})
            if isinstance(topics, dict) and topics:
                top = sorted(topics.items(), key=lambda x: -x[1])[:8]
                parts.append(f"  Top topics: {', '.join(t[0] for t in top)}")
            active_hours = learner.get("active_hours", {})
            if isinstance(active_hours, dict) and active_hours:
                peak = sorted(active_hours.items(), key=lambda x: -x[1])[:3]
                parts.append(f"  Peak hours: {', '.join(f'{h[0]}:00' for h in peak)}")
            prefs_l = learner.get("preferences", {})
            if isinstance(prefs_l, dict) and prefs_l:
                for k, v in list(prefs_l.items())[:5]:
                    parts.append(f"  {k}: {v}")
            sections.append("\n".join(parts))

        # Conversation memory
        conv_ctx = self.get_conversations_context(15)
        if conv_ctx:
            sections.append(conv_ctx)

        # Operator memories
        mem_ctx = self.get_memories_context()
        if mem_ctx:
            sections.append(mem_ctx)

        # Procedure knowledge
        procs = self.get_all_procedures(min_uses=3)
        if procs:
            parts = ["[TOOL EXPERIENCE — tools you've used and their reliability]"]
            for p in procs[:10]:
                total = p["successes"] + p["failures"] + p["cancelled"]
                rate = round(p["successes"] / total * 100) if total > 0 else 0
                parts.append(f"  {p['tool_name']}: {total} uses, {rate}% success")
            sections.append("\n".join(parts))

        return "\n\n".join(s for s in sections if s.strip())

    # ─── Training Data ────────────────────────────────────

    def save_training_example(self, user_input: str, tool_used: str,
                              tool_params: dict | None = None, response: str = "",
                              success: bool = True, source: str = "live",
                              example_type: str = "direct") -> int:
        """Save a training example from a live interaction."""
        conn = _get_conn()
        with _db_lock:
            cur = conn.execute(
                """INSERT INTO training_examples
                   (user_input, tool_used, tool_params, response, success, source, example_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_input[:500], tool_used, json.dumps(tool_params or {}),
                 response[:500], 1 if success else 0, source, example_type)
            )
            conn.commit()
            return cur.lastrowid

    def get_training_examples(self, tool: str | None = None, limit: int = 50) -> list[dict]:
        """Get training examples, optionally filtered by tool."""
        conn = _get_conn()
        if tool:
            rows = conn.execute(
                "SELECT * FROM training_examples WHERE tool_used = ? ORDER BY id DESC LIMIT ?",
                (tool, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM training_examples ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_training_stats(self) -> dict:
        """Get training data statistics by tool and source."""
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM training_examples").fetchone()[0]
        by_tool = conn.execute(
            """SELECT tool_used, COUNT(*) as count, SUM(success) as successes
               FROM training_examples GROUP BY tool_used ORDER BY count DESC"""
        ).fetchall()
        by_source = conn.execute(
            "SELECT source, COUNT(*) as count FROM training_examples GROUP BY source"
        ).fetchall()
        tools_covered = conn.execute(
            "SELECT COUNT(DISTINCT tool_used) FROM training_examples"
        ).fetchone()[0]
        return {
            "total_examples": total,
            "tools_covered": tools_covered,
            "by_tool": [dict(r) for r in by_tool],
            "by_source": [dict(r) for r in by_source],
        }

    def export_training_jsonl(self, output_path: str | None = None) -> str:
        """Export all training examples as JSONL for fine-tuning."""
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM training_examples ORDER BY id").fetchall()
        if not output_path:
            output_path = str(Path.home() / ".jarvis_training_export.jsonl")
        with open(output_path, "w", encoding="utf-8") as f:
            for r in rows:
                entry = {
                    "user_input": r["user_input"],
                    "tool_used": r["tool_used"],
                    "response": r["response"],
                    "success": bool(r["success"]),
                    "source": r["source"],
                    "type": r["example_type"],
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return output_path

    def log_evolution_event(self, action: str, data: dict) -> int:
        """Log a system evolution event (diagnostics, updates, etc.)."""
        conn = _get_conn()
        with _db_lock:
            cur = conn.execute(
                "INSERT INTO evolution_log (action, data) VALUES (?, ?)",
                (action, json.dumps(data))
            )
            conn.commit()
            return cur.lastrowid

    def save_test_result(self, test_name: str, status: str,
                         error: str = "", suite: str = "smoke") -> int:
        """Save a test result."""
        conn = _get_conn()
        with _db_lock:
            cur = conn.execute(
                "INSERT INTO test_results (test_name, status, error, suite) VALUES (?, ?, ?, ?)",
                (test_name, status, error, suite)
            )
            conn.commit()
            return cur.lastrowid

    def get_test_summary(self) -> dict:
        """Get the latest test run summary."""
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM test_results").fetchone()[0]
        passed = conn.execute("SELECT COUNT(*) FROM test_results WHERE status = 'PASS'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM test_results WHERE status = 'FAIL'").fetchone()[0]
        return {"total": total, "passed": passed, "failed": failed, "skipped": total - passed - failed}

    # ─── Stats ────────────────────────────────────────────

    def get_stats(self) -> dict:
        conn = _get_conn()
        return {
            "conversations": conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            "memories": conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
            "episodes": conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0],
            "procedures": conn.execute("SELECT COUNT(*) FROM procedures").fetchone()[0],
            "training_examples": conn.execute("SELECT COUNT(*) FROM training_examples").fetchone()[0],
            "evolution_events": conn.execute("SELECT COUNT(*) FROM evolution_log").fetchone()[0],
            "test_results": conn.execute("SELECT COUNT(*) FROM test_results").fetchone()[0],
            "kv_entries": conn.execute("SELECT COUNT(*) FROM kv_store").fetchone()[0],
            "db_size_kb": round(os.path.getsize(DB_PATH) / 1024, 1) if DB_PATH.exists() else 0,
        }

    # ─── Migration from JSON files ────────────────────────

    def _migrate_json_files(self):
        """One-time migration from JSON files to SQLite."""
        conn = _get_conn()

        # Check if already migrated
        try:
            count = conn.execute("SELECT COUNT(*) FROM kv_store WHERE namespace='_meta' AND key='migrated'").fetchone()[0]
            if count > 0:
                return
        except sqlite3.OperationalError:
            pass  # kv_store table might not exist yet on first run

        print("[JarvisDB] First run — migrating JSON files to SQLite...")
        migrated = []

        # 1. Migrate config.json (identity, preferences, task_memory, memories, learned)
        config_path = Path.home() / ".jarvis_config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))

                # Identity
                identity = config.get("identity", {})
                if identity:
                    for k, v in identity.items():
                        self.kv_set("identity", k, v)
                    migrated.append(f"identity ({len(identity)} fields)")

                # Preferences
                prefs = config.get("preferences", {})
                if prefs:
                    for k, v in prefs.items():
                        self.kv_set("preferences", k, v)
                    migrated.append(f"preferences ({len(prefs)} fields)")

                # Task memory
                task_mem = config.get("task_memory", {})
                if task_mem:
                    for k, v in task_mem.items():
                        self.kv_set("task_memory", k, v)
                    migrated.append(f"task_memory ({len(task_mem)} fields)")

                # Memories (MemoryBank)
                memories = config.get("memories", [])
                if memories:
                    for m in memories:
                        content = m if isinstance(m, str) else str(m)
                        self.save_memory(content)
                    migrated.append(f"memories ({len(memories)} items)")

                # Learner
                learned = config.get("learned", {})
                if learned:
                    for k, v in learned.items():
                        self.kv_set("learner", k, v)
                    migrated.append(f"learner ({len(learned)} fields)")

            except Exception as e:
                print(f"[JarvisDB] ⚠️ Config migration error: {e}")

        # 2. Migrate conversations
        conv_path = Path.home() / ".jarvis_conversations.json"
        if conv_path.exists():
            try:
                convos = json.loads(conv_path.read_text(encoding="utf-8"))
                for c in convos:
                    user = c.get("user", "")
                    assistant = c.get("assistant", "")
                    if user and assistant:
                        conn.execute(
                            "INSERT INTO conversations (user_text, assistant_text, source, created_at) VALUES (?, ?, 'text', ?)",
                            (user, assistant, c.get("timestamp", datetime.now().isoformat()))
                        )
                conn.commit()
                # Rebuild FTS
                try:
                    conn.execute("INSERT INTO conversations_fts (conversations_fts) VALUES ('rebuild')")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
                migrated.append(f"conversations ({len(convos)} exchanges)")
            except Exception as e:
                print(f"[JarvisDB] ⚠️ Conversation migration error: {e}")

        # 3. Migrate task brain
        tb_path = Path.home() / ".jarvis_task_brain.json"
        if tb_path.exists():
            try:
                tb = json.loads(tb_path.read_text(encoding="utf-8"))

                # Episodes
                episodes = tb.get("episodes", [])
                for ep in episodes:
                    conn.execute(
                        """INSERT INTO episodes (session_id, goal, tool, args, status, step, attempts, result, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (ep.get("session_id", ""), ep.get("goal", ""), ep.get("tool", "unknown"),
                         json.dumps(ep.get("args", {})), ep.get("status", "completed"),
                         ep.get("step", ""), ep.get("attempts", 1), ep.get("result", ""),
                         ep.get("time", datetime.now().isoformat()))
                    )

                # Procedures
                procs = tb.get("procedures", {})
                for tool_name, p in procs.items():
                    at = p.get("attempt_total", 0)
                    asamp = p.get("attempt_samples", 0)
                    conn.execute(
                        """INSERT OR REPLACE INTO procedures
                           (tool_name, successes, failures, cancelled, attempt_total, attempt_samples,
                            arg_counts, sample_goals, recent_results, last_status, last_used)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (tool_name, p.get("successes", 0), p.get("failures", 0),
                         p.get("cancelled", 0), at, asamp,
                         json.dumps(p.get("arg_counts", {})),
                         json.dumps(p.get("sample_goals", [])),
                         json.dumps(p.get("recent_results", [])),
                         p.get("last_status", ""), p.get("last_used", ""))
                    )

                conn.commit()
                migrated.append(f"task_brain ({len(episodes)} episodes, {len(procs)} procedures)")
            except Exception as e:
                print(f"[JarvisDB] ⚠️ TaskBrain migration error: {e}")

        # 4. Migrate intelligence
        intel_path = Path.home() / ".jarvis_intelligence.json"
        if intel_path.exists():
            try:
                intel = json.loads(intel_path.read_text(encoding="utf-8"))
                for section in ["feedback", "patterns", "emotional"]:
                    data = intel.get(section, {})
                    if data:
                        for k, v in data.items():
                            self.kv_set(f"intelligence_{section}", k, v)
                migrated.append("intelligence")
            except Exception as e:
                print(f"[JarvisDB] ⚠️ Intelligence migration error: {e}")

        # 5. Migrate training data (learning_log.jsonl)
        project_root = Path(__file__).resolve().parent.parent
        learning_log = project_root / "training" / "learning_log.jsonl"
        if learning_log.exists():
            try:
                count = 0
                with open(learning_log, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        conn.execute(
                            """INSERT INTO training_examples
                               (user_input, tool_used, tool_params, response, success, source, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (entry.get("user_input", ""), entry.get("tool_used", ""),
                             json.dumps(entry.get("tool_params", {})),
                             entry.get("response", ""),
                             1 if entry.get("success", True) else 0,
                             entry.get("source", "manual"),
                             entry.get("timestamp", datetime.now().isoformat()))
                        )
                        count += 1
                conn.commit()
                migrated.append(f"learning_log ({count} examples)")
            except Exception as e:
                print(f"[JarvisDB] ⚠️ Learning log migration error: {e}")

        # 6. Migrate tool routing SFT dataset
        sft_path = project_root / "training" / "datasets" / "jarvis_tool_routing" / "jarvis_tool_routing_raw.jsonl"
        if sft_path.exists():
            try:
                count = 0
                with open(sft_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        conn.execute(
                            """INSERT INTO training_examples
                               (user_input, tool_used, tool_params, response, success, source, example_type, created_at)
                               VALUES (?, ?, '{}', ?, 1, 'tool_routing', ?, ?)""",
                            (entry.get("instruction", ""),
                             entry.get("tool_name", ""),
                             entry.get("output", ""),
                             entry.get("type", "direct"),
                             datetime.now().isoformat())
                        )
                        count += 1
                conn.commit()
                migrated.append(f"tool_routing ({count} examples)")
            except Exception as e:
                print(f"[JarvisDB] ⚠️ Tool routing migration error: {e}")

        # 7. Migrate evolution logs
        evo_dir = project_root / "training" / "evolution_logs"
        if evo_dir.exists():
            try:
                count = 0
                for evo_file in sorted(evo_dir.glob("*.jsonl")):
                    with open(evo_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            entry = json.loads(line)
                            conn.execute(
                                "INSERT INTO evolution_log (action, data, created_at) VALUES (?, ?, ?)",
                                (entry.get("action", "unknown"),
                                 json.dumps(entry),
                                 entry.get("timestamp", datetime.now().isoformat()))
                            )
                            count += 1
                conn.commit()
                migrated.append(f"evolution_logs ({count} events)")
            except Exception as e:
                print(f"[JarvisDB] ⚠️ Evolution log migration error: {e}")

        # 8. Migrate test results
        test_report = project_root / "training" / "test_report.json"
        if test_report.exists():
            try:
                report = json.loads(test_report.read_text(encoding="utf-8"))
                results = report.get("results", [])
                ts = report.get("timestamp", datetime.now().isoformat())
                for r in results:
                    conn.execute(
                        "INSERT INTO test_results (test_name, status, error, suite, created_at) VALUES (?, ?, ?, 'smoke', ?)",
                        (r.get("name", "unknown"), r.get("status", "SKIP"),
                         r.get("error", ""), ts)
                    )
                conn.commit()
                migrated.append(f"test_results ({len(results)} tests)")
            except Exception as e:
                print(f"[JarvisDB] ⚠️ Test report migration error: {e}")

        # Mark as migrated
        self.kv_set("_meta", "migrated", True)
        self.kv_set("_meta", "migrated_at", datetime.now().isoformat())
        self.kv_set("_meta", "migrated_from", migrated)

        if migrated:
            print(f"[JarvisDB] ✅ Migration complete: {', '.join(migrated)}")
        else:
            print("[JarvisDB] No existing data to migrate (fresh install)")

    # ─── Tool Outcomes ────────────────────────────────────

    def record_tool_outcome(
        self,
        tool_name: str,
        execution_mode: str = "direct",
        success: bool = True,
        latency_ms: float = 0.0,
        error_class: str = "",
    ) -> int:
        """Record a tool execution outcome for reliability tracking.

        Returns the row ID.
        """
        conn = _get_conn()
        with _db_lock:
            cur = conn.execute(
                "INSERT INTO tool_outcomes (tool_name, execution_mode, success, latency_ms, error_class) "
                "VALUES (?, ?, ?, ?, ?)",
                (tool_name, execution_mode, int(success), latency_ms, error_class),
            )
            conn.commit()
            return cur.lastrowid

    def get_tool_reliability(self, tool_name: str, days: int = 7) -> dict:
        """Get reliability stats for a tool over the last N days.

        Returns:
            {
                "tool_name": str,
                "total": int,
                "successes": int,
                "failures": int,
                "reliability": float,     # 0.0 - 1.0
                "avg_latency_ms": float,
                "common_errors": list[str],
            }
        """
        conn = _get_conn()
        row = conn.execute(
            """SELECT
                   COUNT(*) as total,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                   SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
                   AVG(latency_ms) as avg_latency
               FROM tool_outcomes
               WHERE tool_name = ?
                 AND timestamp >= datetime('now', ?)""",
            (tool_name, f"-{days} days"),
        ).fetchone()

        total = row["total"] if row["total"] else 0
        successes = row["successes"] if row["successes"] else 0
        failures = row["failures"] if row["failures"] else 0
        avg_latency = row["avg_latency"] if row["avg_latency"] else 0.0

        # Get most common error classes
        error_rows = conn.execute(
            """SELECT error_class, COUNT(*) as cnt
               FROM tool_outcomes
               WHERE tool_name = ? AND success = 0 AND error_class != ''
                 AND timestamp >= datetime('now', ?)
               GROUP BY error_class
               ORDER BY cnt DESC
               LIMIT 5""",
            (tool_name, f"-{days} days"),
        ).fetchall()

        return {
            "tool_name": tool_name,
            "total": total,
            "successes": successes,
            "failures": failures,
            "reliability": successes / total if total > 0 else 1.0,
            "avg_latency_ms": round(avg_latency, 1),
            "common_errors": [r["error_class"] for r in error_rows],
        }

    def get_all_tool_reliability(self, days: int = 7) -> list[dict]:
        """Get reliability stats for ALL tools that have been used recently."""
        conn = _get_conn()
        rows = conn.execute(
            """SELECT
                   tool_name,
                   COUNT(*) as total,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                   SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
                   AVG(latency_ms) as avg_latency
               FROM tool_outcomes
               WHERE timestamp >= datetime('now', ?)
               GROUP BY tool_name
               ORDER BY total DESC""",
            (f"-{days} days",),
        ).fetchall()

        return [
            {
                "tool_name": r["tool_name"],
                "total": r["total"],
                "successes": r["successes"] or 0,
                "failures": r["failures"] or 0,
                "reliability": (r["successes"] or 0) / r["total"] if r["total"] else 1.0,
                "avg_latency_ms": round(r["avg_latency"] or 0, 1),
            }
            for r in rows
        ]

    def get_tool_mode_stats(self, tool_name: str, days: int = 7) -> dict[str, dict]:
        """Get per-mode success rates for a tool (for ExecutionRouter).

        Returns: {"direct": {"total": 5, "successes": 4, ...}, "screen": {...}}
        """
        conn = _get_conn()
        rows = conn.execute(
            """SELECT
                   execution_mode,
                   COUNT(*) as total,
                   SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                   AVG(latency_ms) as avg_latency
               FROM tool_outcomes
               WHERE tool_name = ?
                 AND timestamp >= datetime('now', ?)
               GROUP BY execution_mode""",
            (tool_name, f"-{days} days"),
        ).fetchall()

        return {
            r["execution_mode"]: {
                "total": r["total"],
                "successes": r["successes"] or 0,
                "reliability": (r["successes"] or 0) / r["total"] if r["total"] else 1.0,
                "avg_latency_ms": round(r["avg_latency"] or 0, 1),
            }
            for r in rows
        }

    # ─── Helpers ──────────────────────────────────────────

    @staticmethod
    def _sanitize_args(args: dict) -> dict:
        """Remove sensitive values from tool args before storing."""
        sensitive = {"password", "key", "token", "secret", "api_key", "apiKey", "pin"}
        return {
            k: "[REDACTED]" if k.lower() in sensitive else v
            for k, v in args.items()
        }


# Singleton instance
_db_instance: JarvisDB | None = None


def get_db() -> JarvisDB:
    """Get the singleton JarvisDB instance (thread-safe)."""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            # Double-checked locking — re-check inside the lock
            if _db_instance is None:
                _db_instance = JarvisDB()
    return _db_instance
