"""
J.A.R.V.I.S — Memory System
4-layer memory architecture for movie-style JARVIS:

Layer 1: Identity Memory (persistent)
    Who Dev is, how he speaks, what he likes.

Layer 2: Preference Memory (persistent)
    Preferred browser, favorite apps, work hours, habits.

Layer 3: Session Memory (session-scoped)
    What is happening right now — current conversation, task state.

Layer 4: Task Memory (persistent)
    What was being worked on, pending steps, unfinished actions.

This is what makes JARVIS feel personal. Without memory, it's just a chatbot.
"""

import time
import json
from collections import deque
from datetime import datetime
from core.config import save_config


# ═══════════════════════════════════════════════════════════
#  Layer 1: Identity Memory
# ═══════════════════════════════════════════════════════════

class IdentityMemory:
    """
    Who the user is. Persistent across all sessions.
    This layer is what makes JARVIS say "I know you, Dev."
    """

    def __init__(self, config: dict):
        self.config = config
        if "identity" not in self.config:
            self.config["identity"] = {
                "name": "Dev",
                "full_name": "Devansh",
                "age": 23,
                "location": "Hertfordshire, UK",
                "origin": "Gujarat, India",
                "occupation": "BSc Cyber Security student",
                "university": "University of Hertfordshire",
                "interests": [],
                "relationships": {},
                "personality_notes": [],
            }

    @property
    def data(self) -> dict:
        return self.config.get("identity", {})

    def update(self, key: str, value):
        """Update an identity field."""
        identity = self.data
        identity[key] = value
        self.config["identity"] = identity
        save_config(self.config)

    def add_note(self, note: str):
        """Add a personality/identity note."""
        identity = self.data
        notes = identity.get("personality_notes", [])
        if note not in notes:
            notes.append(note)
            if len(notes) > 50:
                notes = notes[-50:]
            identity["personality_notes"] = notes
            self.config["identity"] = identity
            save_config(self.config)

    def get_context_string(self) -> str:
        """Format identity for LLM context."""
        d = self.data
        parts = [f"[IDENTITY] {d.get('name', 'User')}"]
        if d.get("occupation"):
            parts.append(f"Role: {d['occupation']}")
        if d.get("location"):
            parts.append(f"Based in: {d['location']}")
        if d.get("interests"):
            parts.append(f"Interests: {', '.join(d['interests'][:5])}")
        notes = d.get("personality_notes", [])
        if notes:
            parts.append(f"Notes: {'; '.join(notes[-5:])}")
        return " | ".join(parts)


# ═══════════════════════════════════════════════════════════
#  Layer 2: Preference Memory
# ═══════════════════════════════════════════════════════════

class PreferenceMemory:
    """
    How the user likes things done. Persistent.
    "Open my usual setup" → knows what that means.
    """

    def __init__(self, config: dict):
        self.config = config
        if "preferences" not in self.config:
            self.config["preferences"] = {
                "work_apps": [],         # Apps opened for "work setup"
                "browser": "chrome",
                "code_editor": "vscode",
                "work_hours": {"start": 9, "end": 22},
                "response_style": "concise",  # concise, detailed, casual
                "favorite_commands": [],
                "custom": {},            # Key-value for anything
            }

    @property
    def data(self) -> dict:
        return self.config.get("preferences", {})

    def set(self, key: str, value):
        """Set a preference."""
        prefs = self.data
        prefs[key] = value
        self.config["preferences"] = prefs
        save_config(self.config)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def add_work_app(self, app: str):
        """Learn which apps are part of the work setup."""
        prefs = self.data
        apps = prefs.get("work_apps", [])
        if app.lower() not in [a.lower() for a in apps]:
            apps.append(app)
            prefs["work_apps"] = apps
            self.config["preferences"] = prefs
            save_config(self.config)

    def get_context_string(self) -> str:
        d = self.data
        parts = ["[PREFERENCES]"]
        if d.get("work_apps"):
            parts.append(f"Work apps: {', '.join(d['work_apps'][:5])}")
        if d.get("response_style"):
            parts.append(f"Response style: {d['response_style']}")
        custom = d.get("custom", {})
        if custom:
            items = [f"{k}: {v}" for k, v in list(custom.items())[:5]]
            parts.append(f"Custom: {'; '.join(items)}")
        return " | ".join(parts) if len(parts) > 1 else ""


# ═══════════════════════════════════════════════════════════
#  Layer 3: Session Memory (enhanced short-term)
# ═══════════════════════════════════════════════════════════

class SessionMemory:
    """
    What is happening RIGHT NOW. Session-scoped.
    Tracks conversation flow, active task, emotional state.
    """

    MAX_TURNS = 12

    def __init__(self):
        self._turns: deque[dict] = deque(maxlen=self.MAX_TURNS * 2)
        self._tool_results: list[dict] = []
        self._active_topic: str = ""
        self._active_task: str = ""
        self._mood: str = "neutral"
        self._interrupted: bool = False
        self._session_facts: list[str] = []  # Things learned this session
        self._start_time = time.time()

    def add_user(self, text: str):
        self._turns.append({"role": "user", "content": text, "ts": time.time()})

    def add_assistant(self, text: str):
        self._turns.append({"role": "assistant", "content": text, "ts": time.time()})

    def add_tool_result(self, tool_name: str, output: str, success: bool):
        self._tool_results.append({
            "tool": tool_name, "output": output[:500],
            "success": success, "ts": time.time(),
        })

    def set_topic(self, topic: str):
        self._active_topic = topic

    def set_task(self, task: str):
        self._active_task = task

    def set_mood(self, mood: str):
        self._mood = mood

    def add_fact(self, fact: str):
        """Something learned during this session."""
        if fact not in self._session_facts:
            self._session_facts.append(fact)

    @property
    def recent_messages(self) -> list[dict]:
        return list(self._turns)

    def get_recent(self) -> list[dict]:
        """Alias for orchestrator compatibility."""
        return list(self._turns)

    @property
    def last_user_message(self) -> str:
        for msg in reversed(self._turns):
            if msg["role"] == "user":
                return msg["content"]
        return ""

    @property
    def last_assistant_message(self) -> str:
        for msg in reversed(self._turns):
            if msg["role"] == "assistant":
                return msg["content"]
        return ""

    def get_context_string(self) -> str:
        """Rich session context for LLM."""
        parts = []

        if self._active_topic:
            parts.append(f"[TOPIC] {self._active_topic}")
        if self._active_task:
            parts.append(f"[ACTIVE TASK] {self._active_task}")
        if self._mood != "neutral":
            parts.append(f"[MOOD] User seems {self._mood}")

        if self._tool_results:
            tool_lines = []
            for tr in self._tool_results[-3:]:
                status = "OK" if tr["success"] else "FAIL"
                tool_lines.append(f"  [{status}] {tr['tool']}: {tr['output'][:200]}")
            parts.append("[RECENT TOOLS]\n" + "\n".join(tool_lines))

        if self._session_facts:
            parts.append("[SESSION FACTS] " + "; ".join(self._session_facts[-5:]))

        return "\n".join(parts)

    def clear(self):
        self._turns.clear()
        self._tool_results.clear()
        self._active_topic = ""
        self._active_task = ""
        self._mood = "neutral"
        self._session_facts.clear()

    def clear_tool_results(self):
        self._tool_results.clear()


# ═══════════════════════════════════════════════════════════
#  Layer 4: Task Memory
# ═══════════════════════════════════════════════════════════

class TaskMemory:
    """
    Persistent task tracking.
    "Continue what I was doing" → recalls the last work context.
    """

    def __init__(self, config: dict):
        self.config = config
        if "task_memory" not in self.config:
            self.config["task_memory"] = {
                "last_context": "",
                "last_files": [],
                "last_topic": "",
                "pending_actions": [],
                "work_sessions": [],
            }

    @property
    def data(self) -> dict:
        return self.config.get("task_memory", {})

    def save_context(self, context: str, topic: str = "", files: list = None):
        """Save current work context for later resumption."""
        d = self.data
        d["last_context"] = context[:500]
        d["last_topic"] = topic
        d["last_files"] = (files or [])[:10]
        d["last_saved"] = datetime.now().isoformat()
        self.config["task_memory"] = d
        save_config(self.config)

    def add_pending(self, action: str):
        """Add a pending action that JARVIS should follow up on."""
        d = self.data
        pending = d.get("pending_actions", [])
        pending.append({
            "action": action,
            "created": datetime.now().isoformat(),
            "done": False,
        })
        # Keep last 20
        d["pending_actions"] = pending[-20:]
        self.config["task_memory"] = d
        save_config(self.config)

    def complete_pending(self, index: int):
        d = self.data
        pending = d.get("pending_actions", [])
        if 0 <= index < len(pending):
            pending[index]["done"] = True
            d["pending_actions"] = pending
            self.config["task_memory"] = d
            save_config(self.config)

    def get_resume_context(self) -> str:
        """What to say when user says 'continue' or 'where were we'."""
        d = self.data
        if not d.get("last_context"):
            return "No previous work context saved."

        parts = []
        if d.get("last_topic"):
            parts.append(f"Last topic: {d['last_topic']}")
        if d.get("last_context"):
            parts.append(f"Context: {d['last_context']}")
        if d.get("last_files"):
            parts.append(f"Files: {', '.join(d['last_files'][:5])}")
        if d.get("last_saved"):
            parts.append(f"Saved: {d['last_saved']}")

        pending = [p for p in d.get("pending_actions", []) if not p.get("done")]
        if pending:
            parts.append(f"Pending: {'; '.join(p['action'] for p in pending[:3])}")

        return " | ".join(parts)

    def get_context_string(self) -> str:
        d = self.data
        pending = [p for p in d.get("pending_actions", []) if not p.get("done")]
        if not pending and not d.get("last_context"):
            return ""
        parts = ["[TASK MEMORY]"]
        if d.get("last_topic"):
            parts.append(f"Last: {d['last_topic']}")
        if pending:
            parts.append(f"Pending: {'; '.join(p['action'] for p in pending[:3])}")
        return " | ".join(parts)


# ═══════════════════════════════════════════════════════════
#  Unified Memory System
# ═══════════════════════════════════════════════════════════

class MemorySystem:
    """
    Unified 4-layer memory. Single interface for all memory operations.
    """

    def __init__(self, config: dict):
        self.identity = IdentityMemory(config)
        self.preferences = PreferenceMemory(config)
        self.session = SessionMemory()
        self.tasks = TaskMemory(config)
        self.config = config

    def get_full_context(self) -> str:
        """Combined memory context for LLM system prompt."""
        parts = []

        ctx = self.identity.get_context_string()
        if ctx:
            parts.append(ctx)

        ctx = self.preferences.get_context_string()
        if ctx:
            parts.append(ctx)

        ctx = self.session.get_context_string()
        if ctx:
            parts.append(ctx)

        ctx = self.tasks.get_context_string()
        if ctx:
            parts.append(ctx)

        # Legacy memories (operator-provided facts)
        mems = self.config.get("memories", [])
        if mems:
            lines = [f"{i+1}. {m}" for i, m in enumerate(mems)]
            parts.append("[OPERATOR MEMORIES]\n" + "\n".join(lines))

        return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════
#  Legacy MemoryBank (backward compatibility)
# ═══════════════════════════════════════════════════════════

class MemoryBank:
    """Manages JARVIS's persistent (long-term) memory bank."""

    MAX_MEMORIES = 100

    def __init__(self, config: dict):
        self.config = config

    @property
    def memories(self) -> list:
        return self.config.get("memories", [])

    def add(self, text: str) -> bool:
        text = text.strip().strip("\"'")
        if not text:
            return False
        if text.lower() in [m.lower() for m in self.memories]:
            return False

        mems = self.memories
        mems.append(text)
        if len(mems) > self.MAX_MEMORIES:
            mems.pop(0)

        self.config["memories"] = mems
        save_config(self.config)
        return True

    def remove(self, index: int) -> bool:
        mems = self.memories
        if 0 <= index < len(mems):
            mems.pop(index)
            self.config["memories"] = mems
            save_config(self.config)
            return True
        return False

    def clear(self):
        self.config["memories"] = []
        save_config(self.config)

    def search(self, query: str) -> list:
        query_lower = query.lower()
        return [(i, m) for i, m in enumerate(self.memories) if query_lower in m.lower()]

    def get_context_string(self) -> str:
        mems = self.memories
        if not mems:
            return ""
        lines = [f"{i+1}. {m}" for i, m in enumerate(mems)]
        return "[OPERATOR MEMORIES]\n" + "\n".join(lines)

    def __len__(self):
        return len(self.memories)


# ═══════════════════════════════════════════════════════════
#  Legacy ShortTermMemory (backward compatibility)
# ═══════════════════════════════════════════════════════════

class ShortTermMemory:
    """Backward-compatible wrapper around SessionMemory."""

    MAX_TURNS = 8

    def __init__(self):
        self._session = SessionMemory()

    def add_user(self, text: str):
        self._session.add_user(text)

    def add_assistant(self, text: str):
        self._session.add_assistant(text)

    def add_tool_result(self, tool_name: str, output: str, success: bool):
        self._session.add_tool_result(tool_name, output, success)

    def clear_tool_results(self):
        self._session.clear_tool_results()

    @property
    def recent_messages(self) -> list[dict]:
        return self._session.recent_messages

    def get_recent(self) -> list[dict]:
        return self._session.get_recent()

    def get_context_string(self) -> str:
        return self._session.get_context_string()

    def clear(self):
        self._session.clear()


class ShortTermMemory:
    """
    Session-scoped context buffer for the agent.
    Keeps the last N exchanges (user + assistant pairs) plus
    any tool results from the current turn.
    """

    MAX_TURNS = 8  # keep last 8 user/assistant pairs

    def __init__(self):
        self._turns: deque[dict] = deque(maxlen=self.MAX_TURNS * 2)
        self._tool_results: list[dict] = []

    def add_user(self, text: str):
        self._turns.append({"role": "user", "content": text})

    def add_assistant(self, text: str):
        self._turns.append({"role": "assistant", "content": text})

    def add_tool_result(self, tool_name: str, output: str, success: bool):
        self._tool_results.append({
            "tool": tool_name,
            "output": output[:500],
            "success": success,
        })

    def clear_tool_results(self):
        self._tool_results.clear()

    @property
    def recent_messages(self) -> list[dict]:
        return list(self._turns)

    def get_recent(self) -> list[dict]:
        """Return recent messages (alias for orchestrator compatibility)."""
        return list(self._turns)

    def get_context_string(self) -> str:
        """Format short-term context for the planner."""
        parts = []

        if self._tool_results:
            tool_lines = []
            for tr in self._tool_results[-3:]:
                status = "OK" if tr["success"] else "FAIL"
                tool_lines.append(f"  [{status}] {tr['tool']}: {tr['output'][:200]}")
            parts.append("[RECENT TOOL RESULTS]\n" + "\n".join(tool_lines))

        return "\n\n".join(parts)

    def clear(self):
        self._turns.clear()
        self._tool_results.clear()
