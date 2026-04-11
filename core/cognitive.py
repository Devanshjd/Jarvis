"""
J.A.R.V.I.S — Cognitive Core (Local Intelligence Engine)
Makes JARVIS smarter over time WITHOUT depending on external AI APIs.

Systems:
    1. Response Cache      — instant answers from past Q&A (zero API cost)
    2. Task Decomposition  — break complex requests into atomic subtasks
    3. Knowledge Extraction — learn facts from every conversation turn
    4. Local Reasoning      — answer math, recall, definitions locally
    5. Self-Evaluation      — track quality, learn best provider per query type
    6. Skill Memory         — remember successful multi-step workflows
    7. Context Manager      — send only the most relevant history to the AI

All data persists in ~/.jarvis_knowledge.json (auto-created, thread-safe).
No external dependencies — stdlib only.
"""

import json
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from core.runtime_hygiene import sanitize_learning_text, should_cache_learning


# ── Storage Path ─────────────────────────────────────────────
KNOWLEDGE_FILE = os.path.join(Path.home(), ".jarvis_knowledge.json")

# ── Defaults ─────────────────────────────────────────────────
MAX_KNOWLEDGE_ENTRIES = 5000
SAVE_INTERVAL = 20          # interactions between disk writes
CACHE_SIMILARITY_THRESHOLD = 0.75
MAX_CONTEXT_MESSAGES = 10


class CognitiveCore:
    """
    Local intelligence engine that learns, caches, reasons, and
    self-improves across sessions — no external API required.
    """

    # ══════════════════════════════════════════════════════════
    # INIT / PERSISTENCE
    # ══════════════════════════════════════════════════════════

    def __init__(self, config: dict | None = None):
        """
        Args:
            config: Optional dict with overrides for thresholds, paths, etc.
        """
        self.config = config or {}
        self._lock = threading.Lock()
        self._interaction_count = 0

        # Tuning knobs (overridable via config)
        self._similarity_threshold = self.config.get(
            "similarity_threshold", CACHE_SIMILARITY_THRESHOLD
        )
        self._max_entries = self.config.get(
            "max_knowledge_entries", MAX_KNOWLEDGE_ENTRIES
        )
        self._save_interval = self.config.get(
            "save_interval", SAVE_INTERVAL
        )
        self._knowledge_file = self.config.get(
            "knowledge_file", KNOWLEDGE_FILE
        )

        # ── Internal stores ──────────────────────────────────
        self._data = self._load()

    # ── Disk I/O ─────────────────────────────────────────────

    def _empty_store(self) -> dict:
        """Return a blank knowledge store skeleton."""
        return {
            "cache": [],            # response cache entries
            "knowledge": [],        # extracted facts / triples
            "skills": [],           # remembered multi-step workflows
            "provider_scores": {},  # provider -> {query_type -> {score, count}}
            "stats": {
                "cache_hits": 0,
                "cache_misses": 0,
                "total_interactions": 0,
                "total_extractions": 0,
                "local_answers": 0,
            },
            "last_response": None,  # most recent AI response text
        }

    def _load(self) -> dict:
        """Load knowledge from disk, or create a fresh store."""
        try:
            with open(self._knowledge_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure all keys exist (forward-compat)
            template = self._empty_store()
            for key, default in template.items():
                data.setdefault(key, default)
            if isinstance(data.get("stats"), dict):
                for sk, sv in template["stats"].items():
                    data["stats"].setdefault(sk, sv)
            return data
        except (FileNotFoundError, json.JSONDecodeError):
            return self._empty_store()

    def _save(self, force: bool = False):
        """
        Write knowledge to disk.  By default only writes every
        ``_save_interval`` interactions to reduce I/O.
        """
        self._interaction_count += 1
        if not force and self._interaction_count % self._save_interval != 0:
            return
        self._write_disk()

    def _write_disk(self):
        """Unconditionally flush to disk (thread-safe)."""
        with self._lock:
            try:
                tmp = self._knowledge_file + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, default=str)
                os.replace(tmp, self._knowledge_file)
            except OSError:
                pass  # non-fatal — will retry on next save

    def flush(self):
        """Force an immediate save to disk (call on shutdown)."""
        self._write_disk()

    # ══════════════════════════════════════════════════════════
    # 1. RESPONSE CACHE
    # ══════════════════════════════════════════════════════════

    def cache_lookup(self, question: str) -> dict | None:
        """
        Check if a similar question was answered before.

        Returns the cached entry dict if found (ratio > threshold),
        otherwise None.  Increments stats accordingly.
        """
        question_lower = question.strip().lower()
        best_match = None
        best_ratio = 0.0

        for entry in self._data["cache"]:
            if not should_cache_learning(entry.get("question", ""), entry.get("answer", "")):
                continue
            ratio = SequenceMatcher(
                None, question_lower, entry["question"].lower()
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = entry

        if best_match and best_ratio >= self._similarity_threshold:
            best_match["times_used"] = best_match.get("times_used", 0) + 1
            self._data["stats"]["cache_hits"] += 1
            self._save()
            return best_match

        self._data["stats"]["cache_misses"] += 1
        return None

    def cache_store(
        self,
        question: str,
        answer: str,
        provider: str = "unknown",
        rating: float = 0.0,
    ):
        """
        Store a Q&A pair in the response cache.

        Args:
            question:  The user query.
            answer:    The AI (or local) response.
            provider:  Which backend generated the answer.
            rating:    Optional quality score (0-1).
        """
        safe_question = sanitize_learning_text(question, limit=220)
        safe_answer = sanitize_learning_text(answer, limit=700)
        if not should_cache_learning(safe_question, safe_answer):
            return

        entry = {
            "question": safe_question,
            "answer": safe_answer,
            "provider_used": provider,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "times_used": 1,
            "user_rating": rating,
        }
        with self._lock:
            self._data["cache"].append(entry)
            self._prune("cache")
        self._save()

    # ══════════════════════════════════════════════════════════
    # 2. TASK DECOMPOSITION
    # ══════════════════════════════════════════════════════════

    # Patterns that signal multi-step intent
    _MULTI_STEP_PATTERNS = [
        r"\band\s+then\b",
        r"\bafter\s+that\b",
        r"\balso\b",
        r"\bfirst\b.*\bthen\b",
        r"\bnext\b",
        r"\bfinally\b",
        r"\bfollowed\s+by\b",
        r"\bstep\s*\d",
        r"\b(?:1|2|3|4|5)\s*[\.\):]",
    ]

    @classmethod
    def decompose_task(cls, text: str) -> list[str]:
        """
        Break a complex request into ordered atomic subtasks.

        Returns a list with one or more subtask strings.  If the
        request is already atomic, the list contains just the
        original text.
        """
        text = text.strip()
        if not text:
            return []

        # Check whether it looks multi-step at all
        is_multi = any(
            re.search(p, text, re.IGNORECASE) for p in cls._MULTI_STEP_PATTERNS
        )
        if not is_multi:
            return [text]

        # Split on explicit delimiters
        subtasks: list[str] = []

        # Numbered items  ("1. do X  2. do Y")
        numbered = re.split(r"\d+\s*[\.\):]", text)
        if len(numbered) > 2:
            subtasks = [s.strip() for s in numbered if s.strip()]
            return subtasks

        # Natural-language connectors
        parts = re.split(
            r"\band\s+then\b|\bafter\s+that\b|\bthen\b|\balso\b|"
            r"\bnext\b|\bfinally\b|\bfollowed\s+by\b",
            text,
            flags=re.IGNORECASE,
        )

        # Strip leading "first" from the first chunk
        if parts:
            parts[0] = re.sub(r"^\s*first\s*,?\s*", "", parts[0], flags=re.IGNORECASE)

        subtasks = [p.strip(" ,;") for p in parts if p.strip(" ,;")]
        return subtasks if subtasks else [text]

    # ══════════════════════════════════════════════════════════
    # 3. KNOWLEDGE EXTRACTION
    # ══════════════════════════════════════════════════════════

    # Regex rules — (pattern, entity_type, relation)
    _EXTRACTION_RULES: list[tuple[str, str, str]] = [
        # Names
        (r"(?:my name is|I'm|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
         "user", "name"),
        # Preferences — like / prefer / love
        (r"I\s+(?:like|prefer|love|enjoy)\s+(.+?)(?:\.|,|$)",
         "user", "likes"),
        # Preferences — dislike / hate
        (r"I\s+(?:dislike|hate|don't like|can't stand)\s+(.+?)(?:\.|,|$)",
         "user", "dislikes"),
        # Facts — "X is Y"
        (r"^([A-Z][\w\s]{1,30})\s+is\s+(.+?)(?:\.|$)",
         "fact", "is"),
        # Definitions — "X means Y"
        (r"(\w[\w\s]{1,30})\s+means\s+(.+?)(?:\.|$)",
         "definition", "means"),
        # Skills
        (r"I\s+(?:know|use|work with|study|am learning)\s+(.+?)(?:\.|,|$)",
         "user", "skill"),
        # Location
        (r"I\s+(?:live in|am from|am in|am based in)\s+(.+?)(?:\.|,|$)",
         "user", "location"),
        # Schedule
        (r"(?:I\s+usually|every\s+day\s+I|every\s+\w+\s+I)\s+(.+?)(?:\.|$)",
         "user", "schedule"),
        # Age
        (r"I\s+am\s+(\d{1,3})\s+years?\s+old",
         "user", "age"),
        # Job / role
        (r"I\s+(?:work as|am a|am an)\s+(.+?)(?:\.|,|$)",
         "user", "role"),
    ]

    def extract_knowledge(
        self, user_msg: str, ai_response: str
    ) -> list[dict]:
        """
        Scan both user message and AI response for extractable facts.

        Returns a list of knowledge dicts:
            {entity, relation, value, confidence, source, timestamp}
        """
        extracted: list[dict] = []
        now = datetime.now(timezone.utc).isoformat()

        for text, source in [
            (user_msg, "user"),
            (ai_response, "ai"),
        ]:
            text = sanitize_learning_text(text, limit=500)
            if not text:
                continue
            for pattern, entity, relation in self._EXTRACTION_RULES:
                for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                    groups = match.groups()
                    # For two-group patterns (fact, definition) entity is g0, value is g1
                    if len(groups) >= 2 and relation in ("is", "means"):
                        value = groups[1].strip()
                        entity_name = groups[0].strip()
                    else:
                        value = groups[0].strip() if groups else match.group().strip()
                        entity_name = entity

                    if len(value) < 2 or len(value) > 200:
                        continue

                    entry = {
                        "entity": entity_name,
                        "relation": relation,
                        "value": value,
                        "confidence": 0.8 if source == "user" else 0.5,
                        "source": source,
                        "timestamp": now,
                    }

                    # Avoid exact duplicates
                    if not self._knowledge_exists(entry):
                        extracted.append(entry)

        if extracted:
            with self._lock:
                self._data["knowledge"].extend(extracted)
                self._data["stats"]["total_extractions"] += len(extracted)
                self._prune("knowledge")
            self._save()

        return extracted

    def _knowledge_exists(self, entry: dict) -> bool:
        """Check if an equivalent knowledge triple already exists."""
        for k in self._data["knowledge"]:
            if (
                k["entity"].lower() == entry["entity"].lower()
                and k["relation"] == entry["relation"]
                and k["value"].lower() == entry["value"].lower()
            ):
                return True
        return False

    # ══════════════════════════════════════════════════════════
    # 4. LOCAL REASONING ENGINE
    # ══════════════════════════════════════════════════════════

    def local_reason(self, text: str) -> str | None:
        """
        Attempt to answer the query entirely locally (no API).

        Returns the answer string, or None if an API call is needed.
        """
        text_stripped = text.strip()
        text_lower = text_stripped.lower()

        # ── Repetition ───────────────────────────────────────
        if text_lower in (
            "say that again", "repeat", "repeat that",
            "what did you say", "come again",
        ):
            last = self._data.get("last_response")
            if last:
                self._data["stats"]["local_answers"] += 1
                return last
            return None

        # ── Math evaluation ──────────────────────────────────
        math_answer = self._try_math(text_stripped)
        if math_answer is not None:
            self._data["stats"]["local_answers"] += 1
            return math_answer

        # ── Recall from knowledge base ───────────────────────
        recall_match = re.match(
            r"(?:what did I say about|when did I mention|"
            r"do you (?:remember|know) (?:about|what))\s+(.+?)[\?]?$",
            text_stripped, re.IGNORECASE,
        )
        if recall_match:
            topic = recall_match.group(1).strip()
            results = self.get_knowledge_about(topic)
            if results:
                lines = [
                    f"- {r['entity']} {r['relation']} {r['value']}"
                    for r in results[:5]
                ]
                self._data["stats"]["local_answers"] += 1
                return "Here's what I know:\n" + "\n".join(lines)

        # ── Definitions from KB ──────────────────────────────
        def_match = re.match(
            r"(?:what is|what's|define|meaning of)\s+(.+?)[\?]?$",
            text_stripped, re.IGNORECASE,
        )
        if def_match:
            topic = def_match.group(1).strip()
            results = self.get_knowledge_about(topic)
            defs = [
                r for r in results
                if r["relation"] in ("is", "means")
            ]
            if defs:
                answer = defs[0]["value"]
                self._data["stats"]["local_answers"] += 1
                return f"{defs[0]['entity']} — {answer}"

        # ── List preferences ─────────────────────────────────
        if re.search(
            r"list (?:my )?preferences|what do I like|my preferences",
            text_lower,
        ):
            prefs = [
                k for k in self._data["knowledge"]
                if k["relation"] in ("likes", "dislikes")
            ]
            if prefs:
                lines = [
                    f"- You {k['relation']} {k['value']}" for k in prefs
                ]
                self._data["stats"]["local_answers"] += 1
                return "Your preferences:\n" + "\n".join(lines)

        # ── Count queries ────────────────────────────────────
        count_match = re.match(
            r"how many (.+?) do I have",
            text_lower,
        )
        if count_match:
            thing = count_match.group(1).strip()
            matches = self.get_knowledge_about(thing)
            if matches:
                self._data["stats"]["local_answers"] += 1
                return f"I have {len(matches)} entries about {thing}."

        # ── Comparison ───────────────────────────────────────
        cmp_match = re.match(
            r"(?:which is better|compare)\s+(.+?)\s+(?:or|vs|versus)\s+(.+?)[\?]?$",
            text_stripped, re.IGNORECASE,
        )
        if cmp_match:
            a_topic = cmp_match.group(1).strip()
            b_topic = cmp_match.group(2).strip()
            a_data = self.get_knowledge_about(a_topic)
            b_data = self.get_knowledge_about(b_topic)
            if a_data and b_data:
                lines = [f"What I know about {a_topic}:"]
                lines += [f"  - {k['relation']}: {k['value']}" for k in a_data[:3]]
                lines += [f"What I know about {b_topic}:"]
                lines += [f"  - {k['relation']}: {k['value']}" for k in b_data[:3]]
                self._data["stats"]["local_answers"] += 1
                return "\n".join(lines)

        # Not answerable locally
        return None

    # ── Math helpers ─────────────────────────────────────────

    _MATH_FUNCS = {
        "sqrt": math.sqrt,
        "abs": abs,
        "round": round,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "ceil": math.ceil,
        "floor": math.floor,
        "pi": math.pi,
        "e": math.e,
    }

    def _try_math(self, text: str) -> str | None:
        """Attempt to evaluate a math expression from natural language."""
        # "what's 15% of 200" → 30
        pct_match = re.match(
            r"(?:what(?:'s| is))?\s*(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)",
            text, re.IGNORECASE,
        )
        if pct_match:
            pct = float(pct_match.group(1))
            base = float(pct_match.group(2))
            result = pct / 100 * base
            return f"{pct}% of {base} = {self._fmt_num(result)}"

        # "sqrt(144)", "2**10", "3+4*5", etc.
        # Strip leading question words
        expr = re.sub(
            r"^(?:what(?:'s| is)|calculate|compute|eval(?:uate)?|solve)\s+",
            "", text, flags=re.IGNORECASE,
        ).strip("? ")

        if not expr:
            return None

        # Only allow safe characters
        if not re.match(r"^[\d\s\+\-\*/\.\(\)\%\^a-zA-Z_,]+$", expr):
            return None

        # Replace ^ with ** and common words
        expr = expr.replace("^", "**")
        expr = re.sub(r"\bx\b", "*", expr)

        try:
            result = eval(expr, {"__builtins__": {}}, self._MATH_FUNCS)  # noqa: S307
            if isinstance(result, (int, float)):
                return f"{text.strip('? ')} = {self._fmt_num(result)}"
        except Exception:
            pass

        return None

    @staticmethod
    def _fmt_num(n: float) -> str:
        """Format a number nicely (drop trailing zeros)."""
        if isinstance(n, float) and n == int(n):
            return str(int(n))
        return f"{n:.6g}"

    # ══════════════════════════════════════════════════════════
    # 5. SELF-EVALUATION & LEARNING
    # ══════════════════════════════════════════════════════════

    def evaluate_interaction(
        self,
        user_msg: str,
        ai_response: str,
        latency: float,
        provider: str,
    ):
        """
        Score an interaction and update provider performance data.

        Heuristics (no AI needed):
            +1 if response was fast (< 2 s)
            +1 if response length is reasonable
            -1 if the user message looks like a correction/complaint
        """
        score = 0.0

        # Speed bonus
        if latency < 2.0:
            score += 1.0
        elif latency < 5.0:
            score += 0.5

        # Length sanity — very short or very long answers are suspect
        rlen = len(ai_response)
        if 20 < rlen < 3000:
            score += 1.0
        elif rlen >= 3000:
            score += 0.5

        # Detect corrections / complaints in the user message
        neg_signals = [
            "no that's wrong", "that's not right", "incorrect",
            "you're wrong", "try again", "not what I asked",
            "that's not what", "wrong answer",
        ]
        if any(sig in user_msg.lower() for sig in neg_signals):
            score -= 2.0

        # Detect positive signals
        pos_signals = ["thanks", "thank you", "perfect", "great", "awesome", "exactly"]
        if any(sig in user_msg.lower() for sig in pos_signals):
            score += 1.0

        # Classify query type
        query_type = self._classify_query(user_msg)

        # Update provider scores
        with self._lock:
            scores = self._data["provider_scores"]
            if provider not in scores:
                scores[provider] = {}
            if query_type not in scores[provider]:
                scores[provider][query_type] = {"total_score": 0.0, "count": 0}

            bucket = scores[provider][query_type]
            bucket["total_score"] += score
            bucket["count"] += 1

            self._data["stats"]["total_interactions"] += 1
            self._data["last_response"] = ai_response

        self._save()

    def get_best_provider_for(self, query_type: str = "general") -> str | None:
        """
        Return the provider name with the highest average score for
        the given query type.  Returns None if no data yet.
        """
        best_provider = None
        best_avg = float("-inf")

        for provider, types in self._data["provider_scores"].items():
            bucket = types.get(query_type)
            if bucket and bucket["count"] >= 3:
                avg = bucket["total_score"] / bucket["count"]
                if avg > best_avg:
                    best_avg = avg
                    best_provider = provider

        return best_provider

    @staticmethod
    def _classify_query(text: str) -> str:
        """Classify a user message into a broad query type."""
        text_lower = text.lower()
        if any(w in text_lower for w in ("code", "function", "debug", "error", "program", "script")):
            return "code"
        if any(w in text_lower for w in ("write", "essay", "article", "email", "draft", "letter")):
            return "writing"
        if any(w in text_lower for w in ("research", "explain", "how does", "why does", "what is")):
            return "research"
        if any(w in text_lower for w in ("math", "calculate", "equation", "solve")):
            return "math"
        if any(w in text_lower for w in ("creative", "story", "poem", "imagine", "idea")):
            return "creative"
        return "general"

    # ══════════════════════════════════════════════════════════
    # 6. SKILL MEMORY
    # ══════════════════════════════════════════════════════════

    def remember_skill(self, trigger: str, steps: list[str]):
        """
        Persist a successful multi-step workflow so it can be
        recalled later.

        Args:
            trigger: A short phrase describing when to use this skill
                     (e.g. "deploy my app").
            steps:   Ordered list of actions that accomplished the task.
        """
        with self._lock:
            # Update existing skill if trigger matches
            for skill in self._data["skills"]:
                if SequenceMatcher(
                    None, skill["trigger"].lower(), trigger.lower()
                ).ratio() > 0.8:
                    skill["steps"] = steps
                    skill["success_count"] = skill.get("success_count", 0) + 1
                    skill["last_used"] = datetime.now(timezone.utc).isoformat()
                    self._save()
                    return

            self._data["skills"].append({
                "trigger": trigger.strip(),
                "steps": steps,
                "success_count": 1,
                "last_used": datetime.now(timezone.utc).isoformat(),
            })
        self._save()

    def recall_skill(self, text: str) -> list[str] | None:
        """
        Find a previously remembered skill that matches the request.

        Returns the step list, or None if nothing matches.
        """
        text_lower = text.strip().lower()
        best_match = None
        best_ratio = 0.0

        for skill in self._data["skills"]:
            ratio = SequenceMatcher(
                None, text_lower, skill["trigger"].lower()
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = skill

        if best_match and best_ratio >= self._similarity_threshold:
            best_match["success_count"] = best_match.get("success_count", 0) + 1
            best_match["last_used"] = datetime.now(timezone.utc).isoformat()
            self._save()
            return best_match["steps"]

        return None

    # ══════════════════════════════════════════════════════════
    # 7. CONTEXT WINDOW MANAGER
    # ══════════════════════════════════════════════════════════

    def build_smart_context(
        self,
        current_query: str,
        history: list[dict],
        max_messages: int = MAX_CONTEXT_MESSAGES,
    ) -> list[dict]:
        """
        Select the most relevant messages from conversation history.

        Strategy:
            - Always include the last 3 messages (recency).
            - Score remaining messages by keyword overlap with current query.
            - Inject relevant user-profile knowledge facts.
            - Cap at *max_messages*.

        Each history entry is expected to have at least:
            {"role": "user"|"assistant", "content": str}
        """
        if not history:
            return []

        query_keywords = set(self._tokenize(current_query))

        # Always include the most recent 3 messages
        recent = history[-3:]
        older = history[:-3]

        # Score older messages by relevance
        scored: list[tuple[float, dict]] = []
        for msg in older:
            msg_keywords = set(self._tokenize(msg.get("content", "")))
            overlap = len(query_keywords & msg_keywords)
            scored.append((overlap, msg))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Budget: how many older messages we can include
        budget = max_messages - len(recent)
        top_older = [msg for _score, msg in scored[:budget] if _score > 0]

        # Prepend knowledge context as a system-style message
        knowledge_context = self._build_knowledge_preamble(current_query)

        result: list[dict] = []
        if knowledge_context:
            result.append({
                "role": "system",
                "content": knowledge_context,
            })
        # Older relevant messages first (chronological feel), then recent
        result.extend(top_older)
        result.extend(recent)

        return result[:max_messages]

    def _build_knowledge_preamble(self, query: str) -> str:
        """Build a short preamble of relevant facts for the AI."""
        relevant = self.get_knowledge_about(query)
        if not relevant:
            return ""
        lines = ["Relevant knowledge about the user:"]
        for k in relevant[:8]:
            lines.append(f"- {k['entity']} {k['relation']} {k['value']}")
        return "\n".join(lines)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple word-level tokenizer (lowercase, alpha-only, len>=3)."""
        return [
            w for w in re.findall(r"[a-zA-Z]{3,}", text.lower())
            if w not in _STOP_WORDS
        ]

    # ══════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ══════════════════════════════════════════════════════════

    def get_stats(self) -> dict:
        """
        Return learning statistics.

        Keys: total_knowledge, total_skills, cache_size, cache_hits,
              cache_misses, hit_rate, local_answers, total_interactions.
        """
        s = self._data["stats"]
        total_lookups = s["cache_hits"] + s["cache_misses"]
        hit_rate = (
            round(s["cache_hits"] / total_lookups * 100, 1)
            if total_lookups > 0
            else 0.0
        )
        return {
            "total_knowledge": len(self._data["knowledge"]),
            "total_skills": len(self._data["skills"]),
            "cache_size": len(self._data["cache"]),
            "cache_hits": s["cache_hits"],
            "cache_misses": s["cache_misses"],
            "hit_rate": f"{hit_rate}%",
            "local_answers": s["local_answers"],
            "total_interactions": s["total_interactions"],
        }

    def get_knowledge_about(self, topic: str) -> list[dict]:
        """
        Search the knowledge base for entries related to *topic*.

        Matches against entity, relation, and value fields.
        """
        topic_lower = topic.strip().lower()
        topic_words = set(topic_lower.split())
        results: list[dict] = []

        for k in self._data["knowledge"]:
            text = f"{k['entity']} {k['relation']} {k['value']}".lower()
            # Substring match or word overlap
            if topic_lower in text or topic_words & set(text.split()):
                results.append(k)

        return results

    def forget(self, topic: str) -> int:
        """
        Remove all knowledge entries related to *topic*.

        Returns the number of entries removed.
        """
        before = len(self._data["knowledge"])
        topic_lower = topic.strip().lower()

        self._data["knowledge"] = [
            k for k in self._data["knowledge"]
            if topic_lower not in f"{k['entity']} {k['relation']} {k['value']}".lower()
        ]

        removed = before - len(self._data["knowledge"])
        if removed:
            self._save(force=True)
        return removed

    def export_knowledge(self) -> str:
        """Return a human-readable summary of all learned knowledge."""
        lines: list[str] = []
        lines.append("=== JARVIS Knowledge Base ===")
        lines.append(f"Entries: {len(self._data['knowledge'])}")
        lines.append(f"Cache size: {len(self._data['cache'])}")
        lines.append(f"Skills: {len(self._data['skills'])}")
        lines.append("")

        # Group by entity
        groups: dict[str, list[dict]] = {}
        for k in self._data["knowledge"]:
            groups.setdefault(k["entity"], []).append(k)

        for entity, entries in groups.items():
            lines.append(f"[{entity}]")
            for e in entries:
                lines.append(f"  {e['relation']}: {e['value']}  (confidence={e['confidence']})")
            lines.append("")

        if self._data["skills"]:
            lines.append("[Skills]")
            for s in self._data["skills"]:
                lines.append(
                    f"  \"{s['trigger']}\" -> {len(s['steps'])} steps "
                    f"(used {s['success_count']}x)"
                )
            lines.append("")

        stats = self.get_stats()
        lines.append("[Stats]")
        for key, val in stats.items():
            lines.append(f"  {key}: {val}")

        return "\n".join(lines)

    # ── Internal helpers ─────────────────────────────────────

    def _prune(self, collection: str):
        """
        Keep collection size within ``_max_entries`` by removing
        the oldest / least-used entries.
        """
        data = self._data[collection]
        if len(data) <= self._max_entries:
            return

        if collection == "cache":
            # Remove least-used first, then oldest
            data.sort(key=lambda x: (x.get("times_used", 0), x.get("timestamp", "")))
        else:
            # Oldest first
            data.sort(key=lambda x: x.get("timestamp", ""))

        excess = len(data) - self._max_entries
        self._data[collection] = data[excess:]


# ── Stop words (minimal set to improve keyword relevance) ────
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "this", "that", "these", "those", "and", "but", "or", "nor",
    "not", "for", "with", "about", "from", "into", "through",
    "during", "before", "after", "above", "below", "between",
    "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all",
    "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "only", "own", "same", "than", "too", "very",
    "just", "because", "its", "his", "her", "their", "our", "your",
    "what", "which", "who", "whom", "you", "they", "him",
    "she", "her", "them", "myself", "yourself", "itself",
})
