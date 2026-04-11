"""
J.A.R.V.I.S - Persistent State Registry
Maps the home-folder and runtime-backed stores JARVIS uses across sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from typing import Callable, Optional


@dataclass
class StateStore:
    name: str
    path: Path
    kind: str
    owner: str
    exists: bool
    summary: str
    size_bytes: int = 0

    def to_user_line(self) -> str:
        status = "present" if self.exists else "missing"
        return f"- {self.name}: {self.summary} [{self.kind}, {status}]"

    def to_prompt_line(self) -> str:
        status = "present" if self.exists else "missing"
        return f"- {self.name}: {self.summary} (owner={self.owner}, type={self.kind}, status={status})"


class StateRegistry:
    """Provides a concise view of persistent JARVIS stores."""

    def __init__(self, jarvis):
        self.jarvis = jarvis

    def list_stores(self) -> list[StateStore]:
        return [
            self._json_store(
                "config",
                Path.home() / ".jarvis_config.json",
                "settings",
                "core.config",
                self._summarize_config,
            ),
            self._json_store(
                "contacts",
                Path.home() / ".jarvis_contacts.json",
                "memory",
                "plugins.messaging",
                lambda data: f"{len(data) if isinstance(data, dict) else 0} remembered contacts",
            ),
            self._json_store(
                "conversations",
                Path.home() / ".jarvis_conversations.json",
                "memory",
                "plugins.conversation_memory",
                lambda data: f"{len(data) if isinstance(data, list) else 0} stored conversation exchanges",
            ),
            self._json_store(
                "custom_responses",
                Path.home() / ".jarvis_custom_responses.json",
                "behavior",
                "plugins.self_improve",
                lambda data: f"{len(data) if isinstance(data, dict) else 0} custom response rules",
            ),
            self._json_store(
                "error_knowledge",
                Path.home() / ".jarvis_error_knowledge.json",
                "learning",
                "core.resilient",
                self._summarize_error_knowledge,
            ),
            self._json_store(
                "evolution",
                Path.home() / ".jarvis_evolution.json",
                "learning",
                "core.self_evolve",
                self._summarize_evolution,
            ),
            self._json_store(
                "goals",
                Path.home() / ".jarvis_goals.json",
                "planning",
                "core.thinking",
                lambda data: f"{len(data.get('goals', [])) if isinstance(data, dict) else 0} long-term goals",
            ),
            self._json_store(
                "intelligence",
                Path.home() / ".jarvis_intelligence.json",
                "learning",
                "core.intelligence",
                self._summarize_intelligence,
            ),
            self._json_store(
                "task_brain",
                Path.home() / ".jarvis_task_brain.json",
                "learning",
                "core.task_brain",
                self._summarize_task_brain,
            ),
            self._json_store(
                "knowledge_json",
                Path.home() / ".jarvis_knowledge.json",
                "memory",
                "core.cognitive",
                self._summarize_knowledge_json,
            ),
            self._sqlite_store(
                "knowledge_graph",
                Path.home() / ".jarvis_knowledge.db",
                "graph",
                "core.knowledge_graph",
            ),
            self._json_store(
                "research_cache",
                Path.home() / ".jarvis_research_cache.json",
                "cache",
                "core.web_research",
                lambda data: f"{len(data) if isinstance(data, dict) else 0} cached research entries",
            ),
            self._directory_store(
                "chains",
                Path.home() / ".jarvis_chains",
                "workflow",
                "core.chain_engine",
            ),
        ]

    def describe_for_user(self) -> str:
        stores = self.list_stores()
        lines = ["JARVIS persistent state:"]
        for store in stores:
            lines.append(store.to_user_line())
        return "\n".join(lines)

    def get_prompt_context(self) -> str:
        stores = self.list_stores()
        present = [store for store in stores if store.exists]
        if not present:
            return ""

        lines = ["[PERSISTENT STATE]"]
        for store in present[:8]:
            lines.append(store.to_prompt_line())

        lines.append(
            "[STATE RULES]\n"
            "- Conversation memory, contacts, goals, intelligence, and knowledge live in different stores.\n"
            "- Prefer reading the right store conceptually instead of assuming one single memory file.\n"
            "- Be careful not to expose secrets from config or private user data unless explicitly asked."
        )
        return "\n".join(lines)

    def _json_store(
        self,
        name: str,
        path: Path,
        kind: str,
        owner: str,
        summarizer: Callable[[object], str],
    ) -> StateStore:
        if not path.exists():
            return StateStore(name, path, kind, owner, False, "not created yet", 0)
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
            summary = summarizer(data)
            size = path.stat().st_size
            return StateStore(name, path, kind, owner, True, summary, size)
        except Exception as exc:
            size = path.stat().st_size if path.exists() else 0
            return StateStore(name, path, kind, owner, True, f"present but unreadable ({type(exc).__name__})", size)

    def _sqlite_store(self, name: str, path: Path, kind: str, owner: str) -> StateStore:
        if not path.exists():
            return StateStore(name, path, kind, owner, False, "not created yet", 0)

        size = path.stat().st_size
        summary = "SQLite knowledge graph present"
        try:
            uri = f"file:{path.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=2)
            cur = conn.cursor()
            counts = []
            for table in ("entities", "facts", "relationships", "timeline"):
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    counts.append(f"{table}={cur.fetchone()[0]}")
                except Exception:
                    continue
            conn.close()
            if counts:
                summary = "knowledge graph " + ", ".join(counts)
        except Exception as exc:
            summary = f"SQLite knowledge graph present ({type(exc).__name__})"

        return StateStore(name, path, kind, owner, True, summary, size)

    def _directory_store(self, name: str, path: Path, kind: str, owner: str) -> StateStore:
        if not path.exists():
            return StateStore(name, path, kind, owner, False, "not created yet", 0)
        try:
            entries = sum(1 for _ in path.iterdir())
            return StateStore(name, path, kind, owner, True, f"{entries} workflow files/directories", 0)
        except Exception as exc:
            return StateStore(name, path, kind, owner, True, f"present but unreadable ({type(exc).__name__})", 0)

    def _summarize_config(self, data: object) -> str:
        if not isinstance(data, dict):
            return "config present"
        provider = data.get("provider", "unknown")
        model = data.get("model", "unknown")
        voice = data.get("voice", {}) if isinstance(data.get("voice"), dict) else {}
        voice_engine = voice.get("engine", "classic")
        tts_engine = voice.get("tts_engine", "auto")
        return f"provider={provider}, model={model}, voice={voice_engine}/{tts_engine}"

    def _summarize_error_knowledge(self, data: object) -> str:
        if not isinstance(data, dict):
            return "error knowledge present"
        errors = len(data.get("errors", []))
        fixes = len(data.get("fixes", []))
        patterns = len(data.get("patterns", []))
        return f"errors={errors}, fixes={fixes}, patterns={patterns}"

    def _summarize_evolution(self, data: object) -> str:
        if not isinstance(data, dict):
            return "evolution memory present"
        rules = len(data.get("evolved_rules", []))
        techniques = len(data.get("learned_techniques", []))
        total = data.get("total_evolutions", 0)
        return f"rules={rules}, techniques={techniques}, evolutions={total}"

    def _summarize_intelligence(self, data: object) -> str:
        if not isinstance(data, dict):
            return "intelligence store present"
        feedback = data.get("feedback", {}) if isinstance(data.get("feedback"), dict) else {}
        patterns = data.get("patterns", {}) if isinstance(data.get("patterns"), dict) else {}
        corrections = len(feedback.get("corrections", []))
        tools = len(feedback.get("tool_scores", {}))
        hourly = len(patterns.get("hourly_actions", {}))
        return f"tool_scores={tools}, corrections={corrections}, hourly_patterns={hourly}"

    def _summarize_task_brain(self, data: object) -> str:
        if not isinstance(data, dict):
            return "task brain present"
        episodes = len(data.get("episodes", [])) if isinstance(data.get("episodes"), list) else 0
        procedures = len(data.get("procedures", {})) if isinstance(data.get("procedures"), dict) else 0
        stats = data.get("stats", {}) if isinstance(data.get("stats"), dict) else {}
        successes = int(stats.get("successes", 0))
        failures = int(stats.get("failures", 0))
        return f"episodes={episodes}, procedures={procedures}, success={successes}, fail={failures}"

    def _summarize_knowledge_json(self, data: object) -> str:
        if not isinstance(data, dict):
            return "knowledge store present"
        cache = len(data.get("cache", {})) if isinstance(data.get("cache"), dict) else 0
        knowledge = len(data.get("knowledge", [])) if isinstance(data.get("knowledge"), list) else 0
        skills = len(data.get("skills", {})) if isinstance(data.get("skills"), dict) else 0
        return f"cache={cache}, knowledge={knowledge}, skills={skills}"
