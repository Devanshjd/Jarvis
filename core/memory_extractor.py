"""
J.A.R.V.I.S — Automatic Memory Extractor

Runs after each conversation turn, uses the local LLM to pull out durable
facts (entities, attributes, relationships) and stores them in the
knowledge graph. This is the "learn from every conversation automatically"
loop — the thing vierisid/jarvis has that we didn't.

Before: JARVIS only remembered what you EXPLICITLY told it to remember.
After:  JARVIS extracts facts from every exchange and remembers what
        matters, then injects it back into future prompts via the
        knowledge graph (already wired in orchestrator + project_context).

Design principles:
  - Only extract DURABLE facts (identity, preferences, ongoing projects,
    relationships) — not ephemeral chatter ("what time is it")
  - Deduplicate — don't re-store the same fact every turn
  - Run in the background — never block the response
  - Local LLM only (Ollama) — no cloud, matches privacy posture
  - Fail silent — memory extraction must never break the conversation
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("jarvis.memory_extractor")


# Phrases in a user message that signal there's probably nothing worth
# remembering — skip extraction to save cycles.
_SKIP_PATTERNS = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|ok|okay|yes|no|sure|cool|nice|"
    r"what time|what's the time|good morning|good night|bye)\s*[.!?]*\s*$",
    re.IGNORECASE,
)

# Entity types the extractor is allowed to create (keeps the graph clean).
_ALLOWED_TYPES = {
    "person", "preference", "project", "goal", "tool", "location",
    "organization", "event", "skill", "fact", "device", "account",
    "credential_ref", "contact", "schedule",
}


class MemoryExtractor:
    """Extracts durable facts from conversation turns into the knowledge graph."""

    def __init__(self, jarvis=None, knowledge_graph=None):
        self.jarvis = jarvis
        self._kg = knowledge_graph
        self._recent_hashes: set[int] = set()   # dedup within a session
        self._lock = threading.Lock()
        self._extractions = 0
        self._facts_stored = 0

    # ─── Public API ──────────────────────────────────────────────────────

    def extract_async(self, user_text: str, assistant_text: str) -> None:
        """Fire-and-forget extraction in a background thread.

        Call this after every completed conversation turn. Never blocks
        the caller. Never raises.
        """
        if not self._should_extract(user_text, assistant_text):
            return
        t = threading.Thread(
            target=self._extract_and_store,
            args=(user_text, assistant_text),
            daemon=True,
        )
        t.start()

    def get_stats(self) -> dict[str, int]:
        return {
            "extractions_run": self._extractions,
            "facts_stored": self._facts_stored,
            "dedup_cache_size": len(self._recent_hashes),
        }

    # ─── Internal ────────────────────────────────────────────────────────

    def _kg_ref(self):
        """Resolve the knowledge graph lazily."""
        if self._kg is not None:
            return self._kg
        if self.jarvis is not None:
            kg = getattr(self.jarvis, "knowledge_graph", None)
            if kg:
                self._kg = kg
                return kg
        try:
            from core.knowledge_graph import KnowledgeGraph
            self._kg = KnowledgeGraph()
            return self._kg
        except Exception:
            return None

    def _should_extract(self, user_text: str, assistant_text: str) -> bool:
        """Decide if this turn is worth extracting from."""
        if not user_text or len(user_text.strip()) < 8:
            return False
        if _SKIP_PATTERNS.match(user_text.strip()):
            return False
        # Skip if the assistant errored / refused (nothing durable there)
        low = (assistant_text or "").lower()
        if any(p in low[:60] for p in ("i'm here, sir", "could you please rephrase",
                                        "error", "failed", "i cannot", "i can't")):
            return False
        return True

    def _extract_and_store(self, user_text: str, assistant_text: str) -> None:
        """Do the actual extraction + KG write. Runs in a background thread."""
        try:
            facts = self._llm_extract(user_text, assistant_text)
            if not facts:
                return

            kg = self._kg_ref()
            if not kg:
                return

            self._extractions += 1
            for f in facts:
                self._store_fact(kg, f)
        except Exception as e:
            logger.debug("Memory extraction failed (non-fatal): %s", e)

    def _llm_extract(self, user_text: str, assistant_text: str) -> list[dict]:
        """Ask the local LLM to extract durable facts as structured triples."""
        try:
            import requests
            from pathlib import Path

            # Use a small/fast text model — memory extraction doesn't need vision
            model = "llama3.2:latest"
            try:
                cfg = json.loads((Path.home() / ".jarvis_config.json").read_text(encoding="utf-8"))
                # Prefer a small fast model if configured, else the main one
                model = (cfg.get("ollama") or {}).get("model") or model
            except Exception:
                pass

            system = (
                "You extract DURABLE facts worth remembering long-term from a "
                "conversation. Output ONLY a JSON array. Each item has exactly "
                "these 4 fields, ALL non-empty:\n"
                '  {"entity": "<who/what>", "type": "<category>", '
                '"predicate": "<short relation>", "value": "<the actual fact>"}\n\n'
                "The 'value' field MUST contain the actual information — never "
                "leave it empty. Put the fact content in 'value', a short "
                "relation word in 'predicate'.\n\n"
                "GOOD examples:\n"
                '  {"entity": "Dev", "type": "person", "predicate": "building", "value": "Stormbreaker AI goggles"}\n'
                '  {"entity": "Dev", "type": "preference", "predicate": "compute_device", "value": "Mi 11X phone"}\n'
                '  {"entity": "Dev", "type": "goal", "predicate": "monthly_budget", "value": "100 pounds"}\n\n'
                "BAD (value empty — never do this):\n"
                '  {"entity": "Mi 11X", "predicate": "used as compute", "value": ""}\n\n'
                "Types must be one of: person, preference, project, goal, tool, "
                "location, organization, event, skill, fact, device, account, "
                "contact, schedule.\n\n"
                "Do NOT extract greetings, time queries, one-off questions, or "
                "ephemeral chatter. If nothing durable, output []. Be conservative."
            )

            prompt = (
                f"User said: {user_text[:800]}\n"
                f"JARVIS replied: {assistant_text[:800]}\n\n"
                "Extract durable facts as a JSON array with non-empty values "
                "(or [] if none):"
            )

            r = requests.post(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "keep_alive": "5m",
                    "options": {"temperature": 0.1, "num_predict": 400},
                },
                timeout=30,
            )
            if r.status_code != 200:
                return []
            content = (r.json().get("message", {}).get("content") or "").strip()
            return self._parse_facts(content)
        except Exception as e:
            logger.debug("LLM extract call failed: %s", e)
            return []

    def _parse_facts(self, content: str) -> list[dict]:
        """Parse the LLM's JSON array of facts, tolerating markdown fences."""
        if not content:
            return []
        # Strip markdown fences
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.rstrip().endswith("```"):
                content = content.rstrip()[:-3]
            content = content.strip()
        # Extract the array
        try:
            if content.startswith("{"):
                # Single object — wrap
                data = [json.loads(content)]
            else:
                start = content.find("[")
                end = content.rfind("]")
                if start < 0 or end <= start:
                    return []
                data = json.loads(content[start:end + 1])
        except Exception:
            return []

        facts = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            entity = str(item.get("entity", "")).strip()
            etype = str(item.get("type", "fact")).strip().lower()
            predicate = str(item.get("predicate", "")).strip()
            value = str(item.get("value", "")).strip()
            # Tolerant salvage: small models often put the content in
            # 'predicate' and leave 'value' empty. If so, swap them.
            if entity and not value and predicate:
                value = predicate
                predicate = "note"
            if not entity or not value:
                continue
            if etype not in _ALLOWED_TYPES:
                etype = "fact"
            facts.append({
                "entity": entity[:100],
                "type": etype,
                "predicate": (predicate or "is")[:60],
                "value": value[:300],
            })
        return facts[:10]  # cap per turn

    def _store_fact(self, kg, fact: dict) -> None:
        """Write one fact to the knowledge graph, with dedup."""
        # Dedup key
        key = hash((fact["entity"].lower(), fact["predicate"].lower(),
                    fact["value"].lower()))
        with self._lock:
            if key in self._recent_hashes:
                return
            self._recent_hashes.add(key)
            # Cap dedup cache
            if len(self._recent_hashes) > 500:
                self._recent_hashes = set(list(self._recent_hashes)[-250:])

        try:
            # add_entity with the fact as an attribute
            kg.add_entity(
                fact["entity"],
                fact["type"],
                {fact["predicate"]: fact["value"]},
            )
            self._facts_stored += 1
            logger.info("Learned: %s (%s) — %s: %s",
                        fact["entity"], fact["type"],
                        fact["predicate"], fact["value"][:60])
        except Exception as e:
            logger.debug("KG store failed: %s", e)


# Module-level singleton
_extractor: Optional[MemoryExtractor] = None


def get_extractor(jarvis=None) -> MemoryExtractor:
    global _extractor
    if _extractor is None:
        _extractor = MemoryExtractor(jarvis=jarvis)
    elif jarvis is not None and _extractor.jarvis is None:
        _extractor.jarvis = jarvis
    return _extractor
