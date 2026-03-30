"""
J.A.R.V.I.S — Memory System
Persistent memory bank for storing and recalling operator information.
"""

from core.config import save_config


class MemoryBank:
    """Manages JARVIS's persistent memory bank."""

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
