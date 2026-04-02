"""
J.A.R.V.I.S — Memory System
Dual-layer memory: long-term (persistent) + short-term (session context).

Long-term: Facts the operator tells JARVIS to remember. Saved to disk.
Short-term: Recent conversation context for the agent planner. Session-only.
"""

from collections import deque
from core.config import save_config


class MemoryBank:
    """Manages JARVIS's persistent (long-term) memory bank."""

    MAX_MEMORIES = 100

    def __init__(self, config: dict):
        self.config = config

    @property
    def memories(self) -> list:
        return self.config.get("memories", [])

    def add(self, text: str) -> bool:
        """Add a memory. Returns True if added, False if duplicate."""
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
        """Remove memory by index."""
        mems = self.memories
        if 0 <= index < len(mems):
            mems.pop(index)
            self.config["memories"] = mems
            save_config(self.config)
            return True
        return False

    def clear(self):
        """Wipe all memories."""
        self.config["memories"] = []
        save_config(self.config)

    def search(self, query: str) -> list:
        """Search memories containing query text."""
        query_lower = query.lower()
        return [(i, m) for i, m in enumerate(self.memories) if query_lower in m.lower()]

    def get_context_string(self) -> str:
        """Format memories for inclusion in AI system prompt."""
        mems = self.memories
        if not mems:
            return ""
        lines = [f"{i+1}. {m}" for i, m in enumerate(mems)]
        return "[OPERATOR MEMORIES]\n" + "\n".join(lines)

    def __len__(self):
        return len(self.memories)


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
