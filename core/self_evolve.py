"""
J.A.R.V.I.S -- Self-Evolution Engine
Analyzes prompts, templates, feedback, and performance to IMPROVE ITSELF over time.

"The difference between intelligence and wisdom is that wisdom improves itself." -- JARVIS

When the user pastes a prompt or describes a capability, JARVIS extracts useful
patterns and evolves. This is local analysis -- regex and pattern matching, no
external API calls. All changes are reversible and persisted to disk.

Capabilities:
    - Analyze external prompts for useful techniques, rules, and knowledge
    - Evolve JARVIS's own system prompt based on learned insights
    - Learn from each interaction (what worked, what didn't)
    - Track performance to identify weak and strong areas
    - Suggest self-improvements based on accumulated data
    - Extract specialist definitions from pasted role-prompts
"""

import re
import os
import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from collections import Counter
from pathlib import Path

logger = logging.getLogger("jarvis.self_evolve")

EVOLUTION_FILE = os.path.join(os.path.expanduser("~"), ".jarvis_evolution.json")

# ══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ══════════════════════════════════════════════════════════════════════════════


@dataclass
class EvolutionResult:
    """Result of analyzing a prompt or interaction for evolutionary insights."""
    techniques_found: list[str] = field(default_factory=list)
    useful_rules: list[str] = field(default_factory=list)
    new_knowledge: list[str] = field(default_factory=list)
    specialist_definition: Optional[dict] = None
    identity_improvements: list[str] = field(default_factory=list)
    summary: str = ""

    def is_empty(self) -> bool:
        return (
            not self.techniques_found
            and not self.useful_rules
            and not self.new_knowledge
            and self.specialist_definition is None
            and not self.identity_improvements
        )

    def to_dict(self) -> dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════════════
# Prompt Analyzer -- extracts patterns from external prompts
# ══════════════════════════════════════════════════════════════════════════════


class PromptAnalyzer:
    """
    Analyzes external prompts/templates to extract useful techniques,
    behavioral rules, domain knowledge, and role definitions.

    All analysis is local -- regex and heuristic-based, no API calls.
    """

    # Pattern categories with their detection regexes
    ROLE_PATTERNS = [
        re.compile(r"(?:you are|act as|behave as|assume the role of|you're)\s+(?:a |an )?(.+?)(?:\.|,|\n|$)", re.IGNORECASE),
        re.compile(r"(?:as a|role:\s*)(.+?)(?:\.|,|\n|$)", re.IGNORECASE),
    ]

    RULE_PATTERNS = [
        re.compile(r"(?:always|must|should|never|do not|don'?t|make sure|ensure)\s+(.+?)(?:\.|$)", re.IGNORECASE | re.MULTILINE),
    ]

    PROCEDURAL_PATTERNS = [
        re.compile(r"(?:step\s*\d+[:.]\s*)(.+?)(?:\n|$)", re.IGNORECASE | re.MULTILINE),
        re.compile(r"(?:first|then|next|after that|finally)[,:]?\s+(.+?)(?:\.|$)", re.IGNORECASE | re.MULTILINE),
    ]

    FEWSHOT_PATTERNS = [
        re.compile(r"(?:example|for instance|e\.g\.|such as|sample)[:\s]+(.+?)(?:\n\n|$)", re.IGNORECASE | re.DOTALL),
    ]

    FORMAT_PATTERNS = [
        re.compile(r"(?:format|output|respond|reply|answer)\s+(?:your |the )?(?:response|output|answer|reply)\s+(?:as|in|using|with)\s+(.+?)(?:\.|$)", re.IGNORECASE | re.MULTILINE),
        re.compile(r"(?:use the following format|format:\s*)(.+?)(?:\n\n|$)", re.IGNORECASE | re.DOTALL),
    ]

    REASONING_PATTERNS = [
        re.compile(r"(?:think about|consider|reason through|analyze|evaluate|reflect on)\s+(.+?)(?:\.|$)", re.IGNORECASE | re.MULTILINE),
        re.compile(r"(?:before (?:answering|responding|replying)|first (?:check|verify|consider|think))\s*[,:]?\s*(.+?)(?:\.|$)", re.IGNORECASE | re.MULTILINE),
    ]

    PREPROCESS_PATTERNS = [
        re.compile(r"(?:before (?:you |answering|responding))\s*[,:]?\s*(.+?)(?:\.|$)", re.IGNORECASE | re.MULTILINE),
        re.compile(r"(?:first (?:check|verify|confirm|ensure|validate))\s+(.+?)(?:\.|$)", re.IGNORECASE | re.MULTILINE),
    ]

    # Technique detection keywords
    TECHNIQUE_SIGNATURES = {
        "chain-of-thought": [
            r"(?:think|reason|let'?s think)\s+(?:step[- ]by[- ]step|through)",
            r"show\s+(?:your|the)\s+(?:reasoning|thinking|work)",
            r"chain[- ]of[- ]thought",
        ],
        "few-shot": [
            r"(?:example|for instance|e\.g\.):",
            r"(?:input|user|question):\s*.*\n\s*(?:output|assistant|answer):",
        ],
        "role-playing": [
            r"(?:you are|act as|behave as|assume the role)",
        ],
        "constraints": [
            r"(?:always|never|must not|do not|don'?t|cannot)",
            r"(?:limit|restrict|constrain|bound)",
        ],
        "format-instructions": [
            r"(?:format|output|respond).*(?:as|in|using|with)",
            r"(?:json|markdown|bullet|numbered|table|csv)",
        ],
        "system-prompt": [
            r"(?:system|instructions?):",
            r"(?:you are an? (?:AI|assistant|system))",
        ],
        "self-consistency": [
            r"(?:verify|double[- ]check|validate|confirm).*(?:your|the)\s+(?:answer|response)",
        ],
        "tree-of-thought": [
            r"(?:consider|explore)\s+(?:multiple|different|various)\s+(?:approaches|paths|options)",
        ],
        "emotional-prompting": [
            r"(?:this is (?:very |really )?important)",
            r"(?:take (?:your |a )?deep breath)",
        ],
        "meta-prompting": [
            r"(?:improve|optimize|refine)\s+(?:this|your|the)\s+(?:prompt|response|output)",
        ],
    }

    # Domain knowledge keywords (topic -> indicators)
    DOMAIN_INDICATORS = {
        "cybersecurity": ["owasp", "cve", "cvss", "vulnerability", "exploit", "pentest",
                         "nmap", "burp", "injection", "xss", "csrf", "authentication",
                         "authorization", "firewall", "ids", "ips", "siem", "malware"],
        "web-development": ["html", "css", "javascript", "react", "vue", "angular",
                           "api", "rest", "graphql", "frontend", "backend", "fullstack"],
        "devops": ["docker", "kubernetes", "ci/cd", "terraform", "ansible", "jenkins",
                  "pipeline", "deploy", "container", "orchestration"],
        "machine-learning": ["model", "training", "dataset", "neural", "tensorflow",
                            "pytorch", "accuracy", "loss", "epoch", "gradient"],
        "system-admin": ["linux", "windows", "server", "network", "dns", "ssh",
                        "firewall", "monitoring", "backup", "user management"],
        "data-science": ["pandas", "numpy", "visualization", "analysis", "statistics",
                        "correlation", "regression", "clustering", "feature"],
        "coding": ["algorithm", "data structure", "function", "class", "debug",
                  "refactor", "test", "optimize", "complexity", "design pattern"],
    }

    # Tool / capability references
    TOOL_PATTERNS = [
        re.compile(r"(?:use|using|with|via|through)\s+(\w+(?:\s+\w+)?)\s+(?:tool|command|utility|program|script)", re.IGNORECASE),
        re.compile(r"(?:run|execute|invoke|call)\s+(\w+(?:\.\w+)?)", re.IGNORECASE),
    ]

    def analyze(self, text: str) -> dict:
        """
        Analyze a prompt/template and extract everything useful.

        Returns dict with:
            techniques, useful_patterns, knowledge, instructions,
            role, tools_mentioned
        """
        result = {
            "techniques": [],
            "useful_patterns": [],
            "knowledge": [],
            "instructions": [],
            "role": None,
            "tools_mentioned": [],
        }

        if not text or len(text.strip()) < 10:
            return result

        text = text.strip()

        # --- Extract role ---
        for pattern in self.ROLE_PATTERNS:
            match = pattern.search(text)
            if match:
                role = match.group(1).strip().rstrip(".,;:")
                if len(role) > 3 and len(role) < 200:
                    result["role"] = role
                    break

        # --- Detect techniques ---
        for technique, signatures in self.TECHNIQUE_SIGNATURES.items():
            for sig in signatures:
                if re.search(sig, text, re.IGNORECASE):
                    result["techniques"].append(technique)
                    break

        # --- Extract behavioral rules ---
        for pattern in self.RULE_PATTERNS:
            for match in pattern.finditer(text):
                rule = match.group(0).strip().rstrip(".,;:")
                if 10 < len(rule) < 300:
                    result["instructions"].append(rule)

        # --- Extract procedural knowledge ---
        procedures = []
        for pattern in self.PROCEDURAL_PATTERNS:
            for match in pattern.finditer(text):
                step = match.group(0).strip()
                if len(step) > 5:
                    procedures.append(step)
        if procedures:
            result["useful_patterns"].append(
                f"Procedural: {' -> '.join(procedures[:10])}"
            )

        # --- Extract format instructions ---
        for pattern in self.FORMAT_PATTERNS:
            match = pattern.search(text)
            if match:
                fmt = match.group(0).strip().rstrip(".,;:")
                if len(fmt) > 10:
                    result["useful_patterns"].append(f"Format: {fmt[:200]}")

        # --- Extract reasoning/preprocessing rules ---
        for pattern in self.REASONING_PATTERNS:
            for match in pattern.finditer(text):
                instruction = match.group(0).strip().rstrip(".,;:")
                if len(instruction) > 10:
                    result["useful_patterns"].append(f"Reasoning: {instruction[:200]}")

        for pattern in self.PREPROCESS_PATTERNS:
            for match in pattern.finditer(text):
                precheck = match.group(0).strip().rstrip(".,;:")
                if len(precheck) > 10:
                    result["useful_patterns"].append(f"Pre-check: {precheck[:200]}")

        # --- Extract domain knowledge ---
        text_lower = text.lower()
        for domain, indicators in self.DOMAIN_INDICATORS.items():
            matches = [ind for ind in indicators if ind in text_lower]
            if len(matches) >= 2:
                result["knowledge"].append(f"{domain}: {', '.join(matches)}")

        # --- Extract tool references ---
        for pattern in self.TOOL_PATTERNS:
            for match in pattern.finditer(text):
                tool = match.group(1).strip()
                if 2 < len(tool) < 50 and tool.lower() not in ("the", "a", "an", "this", "that"):
                    result["tools_mentioned"].append(tool)

        # --- Extract few-shot examples ---
        for pattern in self.FEWSHOT_PATTERNS:
            match = pattern.search(text)
            if match:
                example = match.group(0).strip()[:300]
                result["useful_patterns"].append(f"Example pattern: {example}")

        # Deduplicate
        result["techniques"] = list(dict.fromkeys(result["techniques"]))
        result["instructions"] = list(dict.fromkeys(result["instructions"]))
        result["useful_patterns"] = list(dict.fromkeys(result["useful_patterns"]))
        result["knowledge"] = list(dict.fromkeys(result["knowledge"]))
        result["tools_mentioned"] = list(dict.fromkeys(result["tools_mentioned"]))

        return result


# ══════════════════════════════════════════════════════════════════════════════
# Evolution Store -- persists all learned improvements
# ══════════════════════════════════════════════════════════════════════════════


class EvolutionStore:
    """
    Persists JARVIS's evolutionary state to disk.
    All changes are versioned and reversible.
    Thread-safe via lock.
    """

    DEFAULT_STATE = {
        "version": 1,
        "evolved_rules": [],
        "learned_techniques": [],
        "domain_knowledge": [],
        "specialist_templates": [],
        "performance_log": [],
        "identity_additions": [],
        "total_evolutions": 0,
        "last_evolved": None,
        "evolution_history": [],  # for rollback
    }

    def __init__(self, filepath: str = EVOLUTION_FILE):
        self._filepath = filepath
        self._lock = threading.Lock()
        self._state = self._load()

    def _load(self) -> dict:
        """Load evolution state from disk."""
        try:
            if os.path.exists(self._filepath):
                with open(self._filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Merge with defaults for any missing keys
                for key, default in self.DEFAULT_STATE.items():
                    if key not in data:
                        data[key] = default if not isinstance(default, list) else []
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to load evolution state: %s — starting fresh", e)
        return json.loads(json.dumps(self.DEFAULT_STATE))

    def _save(self):
        """Persist evolution state to disk. Must be called under lock."""
        try:
            os.makedirs(os.path.dirname(self._filepath) or ".", exist_ok=True)
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error("Failed to save evolution state: %s", e)

    # --- Accessors ---

    @property
    def state(self) -> dict:
        with self._lock:
            return self._state.copy()

    def get(self, key: str, default=None):
        with self._lock:
            return self._state.get(key, default)

    # --- Mutators (all thread-safe) ---

    def add_rule(self, rule: str, source: str = "prompt_analysis"):
        """Add a learned behavioral rule."""
        with self._lock:
            entry = {
                "rule": rule,
                "source": source,
                "added": datetime.now().isoformat(),
                "active": True,
            }
            # Avoid duplicates (by normalized rule text)
            existing = {r["rule"].lower().strip() for r in self._state["evolved_rules"]}
            if rule.lower().strip() not in existing:
                self._state["evolved_rules"].append(entry)
                self._record_evolution("add_rule", rule)
                self._save()
                return True
            return False

    def add_technique(self, technique: str, description: str = ""):
        """Record a learned prompt technique."""
        with self._lock:
            existing = {t["name"].lower() for t in self._state["learned_techniques"]}
            if technique.lower() not in existing:
                self._state["learned_techniques"].append({
                    "name": technique,
                    "description": description,
                    "learned": datetime.now().isoformat(),
                })
                self._record_evolution("add_technique", technique)
                self._save()
                return True
            return False

    def add_knowledge(self, domain: str, details: str):
        """Record domain knowledge."""
        with self._lock:
            self._state["domain_knowledge"].append({
                "domain": domain,
                "details": details,
                "added": datetime.now().isoformat(),
            })
            # Keep last 200 entries
            if len(self._state["domain_knowledge"]) > 200:
                self._state["domain_knowledge"] = self._state["domain_knowledge"][-200:]
            self._record_evolution("add_knowledge", f"{domain}: {details}")
            self._save()

    def add_specialist(self, specialist: dict):
        """Store a specialist template extracted from a prompt."""
        with self._lock:
            existing = {s["name"].lower() for s in self._state["specialist_templates"]}
            name = specialist.get("name", "unknown").lower()
            if name not in existing:
                specialist["extracted"] = datetime.now().isoformat()
                self._state["specialist_templates"].append(specialist)
                self._record_evolution("add_specialist", name)
                self._save()
                return True
            return False

    def add_identity(self, addition: str):
        """Add a system prompt identity addition."""
        with self._lock:
            existing = {a["text"].lower().strip() for a in self._state["identity_additions"]}
            if addition.lower().strip() not in existing:
                self._state["identity_additions"].append({
                    "text": addition,
                    "added": datetime.now().isoformat(),
                    "active": True,
                })
                self._record_evolution("add_identity", addition)
                self._save()
                return True
            return False

    def add_performance_entry(self, entry: dict):
        """Log a performance record (success or failure)."""
        with self._lock:
            entry["timestamp"] = datetime.now().isoformat()
            self._state["performance_log"].append(entry)
            # Keep last 500
            if len(self._state["performance_log"]) > 500:
                self._state["performance_log"] = self._state["performance_log"][-500:]
            self._save()

    def deactivate_rule(self, index: int) -> bool:
        """Deactivate a rule by index (reversible)."""
        with self._lock:
            rules = self._state["evolved_rules"]
            if 0 <= index < len(rules):
                rules[index]["active"] = False
                self._record_evolution("deactivate_rule", rules[index]["rule"])
                self._save()
                return True
            return False

    def deactivate_identity(self, index: int) -> bool:
        """Deactivate an identity addition by index (reversible)."""
        with self._lock:
            additions = self._state["identity_additions"]
            if 0 <= index < len(additions):
                additions[index]["active"] = False
                self._record_evolution("deactivate_identity", additions[index]["text"])
                self._save()
                return True
            return False

    def _record_evolution(self, action: str, detail: str):
        """Internal: record an evolution event for history/rollback."""
        self._state["total_evolutions"] = self._state.get("total_evolutions", 0) + 1
        self._state["last_evolved"] = datetime.now().isoformat()
        self._state["evolution_history"].append({
            "action": action,
            "detail": detail[:300],
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 200 history entries
        if len(self._state["evolution_history"]) > 200:
            self._state["evolution_history"] = self._state["evolution_history"][-200:]

    def rollback_last(self) -> Optional[dict]:
        """Undo the last evolution. Returns the undone entry or None."""
        with self._lock:
            history = self._state.get("evolution_history", [])
            if not history:
                return None

            last = history.pop()
            action = last["action"]
            detail = last["detail"]

            # Reverse the action
            if action == "add_rule":
                self._state["evolved_rules"] = [
                    r for r in self._state["evolved_rules"]
                    if r["rule"][:300] != detail
                ]
            elif action == "add_technique":
                self._state["learned_techniques"] = [
                    t for t in self._state["learned_techniques"]
                    if t["name"] != detail
                ]
            elif action == "add_specialist":
                self._state["specialist_templates"] = [
                    s for s in self._state["specialist_templates"]
                    if s.get("name", "").lower() != detail.lower()
                ]
            elif action == "add_identity":
                self._state["identity_additions"] = [
                    a for a in self._state["identity_additions"]
                    if a["text"][:300] != detail
                ]
            elif action == "deactivate_rule":
                for r in self._state["evolved_rules"]:
                    if r["rule"][:300] == detail:
                        r["active"] = True
                        break
            elif action == "deactivate_identity":
                for a in self._state["identity_additions"]:
                    if a["text"][:300] == detail:
                        a["active"] = True
                        break

            self._save()
            return last


# ══════════════════════════════════════════════════════════════════════════════
# Performance Tracker -- what works and what doesn't
# ══════════════════════════════════════════════════════════════════════════════


class PerformanceTracker:
    """
    Tracks JARVIS's successes and failures across queries, tools, and topics.
    Identifies weak areas and suggests targeted training.
    """

    def __init__(self, store: EvolutionStore):
        self._store = store

    def record_success(self, query: str, approach: str):
        """Record a successful interaction."""
        self._store.add_performance_entry({
            "type": "success",
            "query": query[:300],
            "approach": approach[:200],
        })

    def record_failure(self, query: str, approach: str, reason: str):
        """Record a failed interaction."""
        self._store.add_performance_entry({
            "type": "failure",
            "query": query[:300],
            "approach": approach[:200],
            "reason": reason[:300],
        })

    def _get_log(self) -> list[dict]:
        return self._store.get("performance_log", [])

    def get_weak_areas(self) -> list[str]:
        """Identify topics/tools where JARVIS fails often."""
        log = self._get_log()
        failures = [e for e in log if e.get("type") == "failure"]
        if not failures:
            return []

        # Extract keywords from failed queries
        failure_words = []
        for f in failures:
            words = f.get("query", "").lower().split()
            failure_words.extend(w for w in words if len(w) > 3 and w.isalpha())

        # Also count failure reasons
        reasons = Counter(f.get("reason", "unknown")[:50] for f in failures)

        # Count word frequency in failures
        word_counts = Counter(failure_words)

        # Build weak areas from most common failure words
        weak = []
        for word, count in word_counts.most_common(10):
            if count >= 2:
                weak.append(f"{word} (failed {count}x)")

        for reason, count in reasons.most_common(5):
            if count >= 2:
                weak.append(f"Reason: {reason} ({count}x)")

        return weak

    def get_strong_areas(self) -> list[str]:
        """Identify topics/tools where JARVIS succeeds consistently."""
        log = self._get_log()
        successes = [e for e in log if e.get("type") == "success"]
        if not successes:
            return []

        # Extract approaches that work
        approach_counts = Counter(s.get("approach", "unknown") for s in successes)
        strong = []
        for approach, count in approach_counts.most_common(10):
            if count >= 2:
                strong.append(f"{approach} ({count} successes)")

        return strong

    def suggest_training(self) -> list[str]:
        """Suggest what JARVIS should focus on improving."""
        suggestions = []

        weak = self.get_weak_areas()
        strong = self.get_strong_areas()

        log = self._get_log()
        total = len(log)
        failures = sum(1 for e in log if e.get("type") == "failure")
        successes = total - failures

        if total == 0:
            return ["Not enough data yet. Keep interacting to build performance history."]

        success_rate = (successes / total) * 100 if total > 0 else 0

        if success_rate < 50:
            suggestions.append(
                f"Overall success rate is low ({success_rate:.0f}%) -- "
                f"consider reviewing common failure patterns."
            )

        if weak:
            suggestions.append(f"Weak areas to improve: {', '.join(weak[:5])}")

        if strong:
            suggestions.append(f"Strong areas (keep leveraging): {', '.join(strong[:3])}")

        # Check for recurring failure reasons
        failure_reasons = [e.get("reason", "") for e in log if e.get("type") == "failure"]
        reason_counts = Counter(r[:50] for r in failure_reasons if r)
        for reason, count in reason_counts.most_common(3):
            if count >= 3:
                suggestions.append(
                    f"Recurring failure: \"{reason}\" ({count}x) -- needs a dedicated fix."
                )

        if not suggestions:
            suggestions.append(
                f"Performance looks solid ({success_rate:.0f}% success rate). "
                f"Keep evolving through prompt analysis and feedback."
            )

        return suggestions


# ══════════════════════════════════════════════════════════════════════════════
# Self Evolver -- the main engine
# ══════════════════════════════════════════════════════════════════════════════


class SelfEvolver:
    """
    JARVIS's Self-Evolution Engine.

    Coordinates prompt analysis, performance tracking, identity evolution,
    and specialist extraction. Persists all learning to disk.

    Usage:
        evolver = SelfEvolver(jarvis_app)

        # When user pastes a prompt:
        result = evolver.analyze_prompt(text)

        # After each interaction:
        evolver.learn_from_interaction(user_msg, reply, feedback)

        # Get evolved prompt additions:
        additions = evolver.get_evolved_prompt()

        # Self-improvement suggestions:
        suggestions = evolver.suggest_improvements()
    """

    # Minimum usefulness score (0-1) to adopt an extraction
    USEFULNESS_THRESHOLD = 0.3

    # How many interactions before automatic self-review
    REVIEW_INTERVAL = 25

    def __init__(self, jarvis=None):
        self.jarvis = jarvis
        self._analyzer = PromptAnalyzer()
        self._store = EvolutionStore()
        self._tracker = PerformanceTracker(self._store)
        self._interaction_count = 0
        self._lock = threading.Lock()

        logger.info(
            "Self-Evolution Engine initialized -- %d rules, %d techniques, %d evolutions",
            len(self._store.get("evolved_rules", [])),
            len(self._store.get("learned_techniques", [])),
            self._store.get("total_evolutions", 0),
        )

    # ══════════════════════════════════════════════════════════════
    # PROMPT ANALYSIS
    # ══════════════════════════════════════════════════════════════

    def analyze_prompt(self, text: str) -> EvolutionResult:
        """
        Analyze a prompt/template pasted by the user.
        Extracts useful patterns, techniques, and knowledge, then
        selectively adopts high-value elements.

        Returns an EvolutionResult summarizing what was extracted.
        """
        result = EvolutionResult()

        if not text or len(text.strip()) < 20:
            result.summary = "Text too short to analyze meaningfully."
            return result

        analysis = self._analyzer.analyze(text)

        # --- Score and adopt techniques ---
        for technique in analysis.get("techniques", []):
            score = self._score_technique(technique)
            if score >= self.USEFULNESS_THRESHOLD:
                added = self._store.add_technique(technique, f"score={score:.2f}")
                if added:
                    result.techniques_found.append(technique)

        # --- Score and adopt behavioral rules ---
        for instruction in analysis.get("instructions", []):
            score = self._score_rule(instruction)
            if score >= self.USEFULNESS_THRESHOLD:
                added = self._store.add_rule(instruction, source="prompt_analysis")
                if added:
                    result.useful_rules.append(instruction)

        # --- Store domain knowledge ---
        for knowledge in analysis.get("knowledge", []):
            parts = knowledge.split(":", 1)
            domain = parts[0].strip() if len(parts) > 1 else "general"
            details = parts[1].strip() if len(parts) > 1 else knowledge
            self._store.add_knowledge(domain, details)
            result.new_knowledge.append(knowledge)

        # --- Extract specialist if role is defined ---
        role = analysis.get("role")
        if role:
            specialist = self.create_specialist_from_prompt(text)
            if specialist:
                result.specialist_definition = specialist

        # --- Extract identity improvements ---
        useful_patterns = analysis.get("useful_patterns", [])
        for pattern in useful_patterns:
            if pattern.startswith("Pre-check:") or pattern.startswith("Reasoning:"):
                # These are high-value identity improvements
                added = self._store.add_identity(pattern)
                if added:
                    result.identity_improvements.append(pattern)

        # --- Build summary ---
        parts = []
        if result.techniques_found:
            parts.append(f"Techniques adopted: {', '.join(result.techniques_found)}")
        if result.useful_rules:
            parts.append(f"New rules: {len(result.useful_rules)}")
        if result.new_knowledge:
            parts.append(f"Knowledge areas: {len(result.new_knowledge)}")
        if result.specialist_definition:
            parts.append(f"Specialist extracted: {result.specialist_definition.get('name', 'unknown')}")
        if result.identity_improvements:
            parts.append(f"Identity improvements: {len(result.identity_improvements)}")

        if parts:
            result.summary = "Analyzed prompt and extracted: " + "; ".join(parts) + "."
        else:
            result.summary = "Analyzed prompt but found no new patterns to adopt."

        logger.info("Prompt analysis: %s", result.summary)
        return result

    # ══════════════════════════════════════════════════════════════
    # IDENTITY EVOLUTION
    # ══════════════════════════════════════════════════════════════

    def evolve_identity(self, insights: list[str]):
        """
        Update JARVIS's own system prompt/identity based on learned insights.
        Each insight is evaluated before adoption.
        """
        adopted = 0
        for insight in insights:
            if not insight or len(insight.strip()) < 5:
                continue
            score = self._score_identity_addition(insight)
            if score >= self.USEFULNESS_THRESHOLD:
                if self._store.add_identity(insight):
                    adopted += 1

        if adopted:
            logger.info("Identity evolved: %d new additions adopted", adopted)
        return adopted

    # ══════════════════════════════════════════════════════════════
    # INTERACTION LEARNING
    # ══════════════════════════════════════════════════════════════

    def learn_from_interaction(
        self,
        user_msg: str,
        jarvis_reply: str,
        feedback: Optional[str] = None,
    ):
        """
        Learn from a single interaction.

        Args:
            user_msg: What the user asked
            jarvis_reply: How JARVIS responded
            feedback: Optional user feedback ("good", "bad", "wrong", etc.)
        """
        with self._lock:
            self._interaction_count += 1

        # Classify feedback
        positive_signals = {"good", "great", "perfect", "thanks", "correct", "yes", "awesome", "nice"}
        negative_signals = {"bad", "wrong", "no", "incorrect", "fix", "fail", "error", "ugh"}

        is_positive = False
        is_negative = False

        if feedback:
            feedback_lower = feedback.lower().strip()
            if any(sig in feedback_lower for sig in positive_signals):
                is_positive = True
            if any(sig in feedback_lower for sig in negative_signals):
                is_negative = True

        # Determine approach from reply content
        approach = self._classify_approach(jarvis_reply)

        if is_positive:
            self._tracker.record_success(user_msg, approach)
        elif is_negative:
            reason = feedback if feedback else "negative feedback"
            self._tracker.record_failure(user_msg, approach, reason)

        # Auto-review after N interactions
        if self._interaction_count % self.REVIEW_INTERVAL == 0:
            self._auto_review()

    def _classify_approach(self, reply: str) -> str:
        """Classify the approach used in a reply."""
        reply_lower = reply.lower()

        if any(w in reply_lower for w in ["scan", "nmap", "vulnerability", "exploit"]):
            return "security_tools"
        if any(w in reply_lower for w in ["```", "def ", "class ", "import "]):
            return "code_generation"
        if any(w in reply_lower for w in ["file", "created", "saved", "written"]):
            return "file_operations"
        if any(w in reply_lower for w in ["searched", "found", "results for"]):
            return "search"
        if any(w in reply_lower for w in ["opened", "launched", "started"]):
            return "app_launch"
        if len(reply) > 500:
            return "detailed_explanation"

        return "general_response"

    def _auto_review(self):
        """Automatic self-review triggered every REVIEW_INTERVAL interactions."""
        suggestions = self._tracker.suggest_training()
        if suggestions:
            logger.info(
                "Auto-review after %d interactions: %s",
                self._interaction_count,
                "; ".join(suggestions[:3]),
            )

    # ══════════════════════════════════════════════════════════════
    # EVOLVED PROMPT GENERATION
    # ══════════════════════════════════════════════════════════════

    def get_evolved_prompt(self) -> str:
        """
        Return the current evolved system prompt additions.
        These should be appended to JARVIS's base system prompt.
        """
        parts = []
        state = self._store.state

        # Active evolved rules
        active_rules = [
            r["rule"] for r in state.get("evolved_rules", [])
            if r.get("active", True)
        ]
        if active_rules:
            parts.append("[EVOLVED BEHAVIORAL RULES]")
            for rule in active_rules[-20:]:  # Last 20 active rules
                parts.append(f"- {rule}")

        # Active identity additions
        active_identity = [
            a["text"] for a in state.get("identity_additions", [])
            if a.get("active", True)
        ]
        if active_identity:
            parts.append("\n[EVOLVED IDENTITY]")
            for addition in active_identity[-10:]:
                parts.append(f"- {addition}")

        # Learned techniques (as context)
        techniques = state.get("learned_techniques", [])
        if techniques:
            parts.append("\n[LEARNED TECHNIQUES]")
            names = [t["name"] for t in techniques[-15:]]
            parts.append(f"Known techniques: {', '.join(names)}")

        # Domain knowledge summary
        knowledge = state.get("domain_knowledge", [])
        if knowledge:
            domains = list({k["domain"] for k in knowledge})
            parts.append(f"\n[DOMAIN EXPERTISE]")
            parts.append(f"Knowledge areas: {', '.join(domains)}")

        return "\n".join(parts) if parts else ""

    # ══════════════════════════════════════════════════════════════
    # EVOLUTION STATS
    # ══════════════════════════════════════════════════════════════

    def get_evolution_stats(self) -> dict:
        """Return statistics about how much JARVIS has evolved."""
        state = self._store.state

        total_rules = len(state.get("evolved_rules", []))
        active_rules = sum(
            1 for r in state.get("evolved_rules", []) if r.get("active", True)
        )

        total_identity = len(state.get("identity_additions", []))
        active_identity = sum(
            1 for a in state.get("identity_additions", []) if a.get("active", True)
        )

        perf_log = state.get("performance_log", [])
        successes = sum(1 for e in perf_log if e.get("type") == "success")
        failures = sum(1 for e in perf_log if e.get("type") == "failure")

        return {
            "total_evolutions": state.get("total_evolutions", 0),
            "last_evolved": state.get("last_evolved"),
            "rules": {"total": total_rules, "active": active_rules},
            "techniques_learned": len(state.get("learned_techniques", [])),
            "domain_knowledge_entries": len(state.get("domain_knowledge", [])),
            "specialist_templates": len(state.get("specialist_templates", [])),
            "identity_additions": {"total": total_identity, "active": active_identity},
            "performance": {
                "total_logged": len(perf_log),
                "successes": successes,
                "failures": failures,
                "success_rate": f"{(successes / len(perf_log) * 100):.1f}%" if perf_log else "N/A",
            },
            "interactions_since_startup": self._interaction_count,
        }

    # ══════════════════════════════════════════════════════════════
    # SELF-IMPROVEMENT SUGGESTIONS
    # ══════════════════════════════════════════════════════════════

    def suggest_improvements(self) -> list[str]:
        """
        JARVIS identifies its own weaknesses and suggests improvements.
        Combines performance data, evolution state, and heuristics.
        """
        suggestions = []

        # Performance-based suggestions
        training = self._tracker.suggest_training()
        suggestions.extend(training)

        # Check evolution state for gaps
        state = self._store.state
        rules = state.get("evolved_rules", [])
        techniques = state.get("learned_techniques", [])
        knowledge = state.get("domain_knowledge", [])
        specialists = state.get("specialist_templates", [])

        if len(rules) == 0:
            suggestions.append(
                "No evolved rules yet. Paste prompts you find useful and I will "
                "extract behavioral rules from them."
            )

        if len(techniques) < 3:
            suggestions.append(
                "Limited prompt techniques learned. Share interesting prompt "
                "templates to expand my technique repertoire."
            )

        if len(knowledge) < 5:
            suggestions.append(
                "Domain knowledge is thin. Share domain-specific prompts "
                "(cybersecurity, coding, etc.) to deepen my expertise."
            )

        # Check for weak areas
        weak = self._tracker.get_weak_areas()
        if weak:
            suggestions.append(
                f"Identified weak areas: {', '.join(weak[:5])}. "
                f"Consider adding rules or specialists to cover these."
            )

        # Check if there are inactive (deactivated) items that could be re-evaluated
        inactive_rules = sum(1 for r in rules if not r.get("active", True))
        if inactive_rules > 0:
            suggestions.append(
                f"{inactive_rules} deactivated rule(s) -- review and reactivate "
                f"if they were disabled by mistake."
            )

        # Check if specialists could help
        if not specialists:
            suggestions.append(
                "No specialist templates extracted yet. Paste role-specific prompts "
                "(e.g., 'You are a security auditor...') and I will create specialists."
            )

        return suggestions

    # ══════════════════════════════════════════════════════════════
    # SPECIALIST EXTRACTION
    # ══════════════════════════════════════════════════════════════

    def create_specialist_from_prompt(self, text: str) -> Optional[dict]:
        """
        If user pastes a prompt that defines a role JARVIS doesn't have,
        extract it into a new Specialist definition.

        Returns a specialist dict or None if no role was found.
        """
        analysis = self._analyzer.analyze(text)
        role = analysis.get("role")

        if not role:
            return None

        # Build specialist definition
        name = self._normalize_specialist_name(role)

        specialist = {
            "name": name,
            "role": role,
            "instructions": analysis.get("instructions", [])[:20],
            "techniques": analysis.get("techniques", []),
            "tools": analysis.get("tools_mentioned", []),
            "knowledge_domains": [
                k.split(":")[0].strip()
                for k in analysis.get("knowledge", [])
            ],
            "useful_patterns": analysis.get("useful_patterns", [])[:10],
        }

        # Store the specialist
        self._store.add_specialist(specialist)

        logger.info("Specialist extracted: %s (%s)", name, role)
        return specialist

    def _normalize_specialist_name(self, role: str) -> str:
        """Convert a role description into a clean specialist name."""
        # Remove common prefixes
        role = re.sub(
            r"^(a |an |the |senior |junior |lead |expert |experienced |professional )",
            "", role.strip(), flags=re.IGNORECASE,
        )
        # Keep first 3 meaningful words
        words = [w.strip(".,;:!?") for w in role.split() if len(w) > 1][:3]
        return "_".join(w.lower() for w in words) if words else "unknown_specialist"

    # ══════════════════════════════════════════════════════════════
    # SCORING -- don't blindly adopt everything
    # ══════════════════════════════════════════════════════════════

    def _score_technique(self, technique: str) -> float:
        """
        Score the usefulness of a technique (0.0 to 1.0).
        Higher-value techniques score higher.
        """
        high_value = {
            "chain-of-thought": 0.9,
            "self-consistency": 0.85,
            "tree-of-thought": 0.8,
            "constraints": 0.7,
            "few-shot": 0.7,
            "format-instructions": 0.6,
            "role-playing": 0.5,
            "meta-prompting": 0.8,
            "emotional-prompting": 0.3,
            "system-prompt": 0.4,
        }
        return high_value.get(technique, 0.4)

    def _score_rule(self, rule: str) -> float:
        """
        Score the usefulness of a behavioral rule (0.0 to 1.0).
        Longer, more specific rules score higher.
        """
        score = 0.3  # Base score

        # Length bonus (more specific = better)
        if len(rule) > 30:
            score += 0.1
        if len(rule) > 60:
            score += 0.1

        # Actionable keywords boost
        actionable = ["verify", "check", "ensure", "validate", "confirm",
                      "analyze", "report", "document", "log", "test"]
        rule_lower = rule.lower()
        if any(w in rule_lower for w in actionable):
            score += 0.2

        # Security/safety rules get a boost (relevant to JARVIS's cybersecurity focus)
        security = ["security", "authorization", "authentication", "permission",
                    "vulnerability", "risk", "threat", "audit"]
        if any(w in rule_lower for w in security):
            score += 0.15

        # Vague rules get penalized
        vague = ["be good", "try hard", "be nice", "be helpful", "do your best"]
        if any(v in rule_lower for v in vague):
            score -= 0.3

        return min(max(score, 0.0), 1.0)

    def _score_identity_addition(self, text: str) -> float:
        """Score an identity addition (0.0 to 1.0)."""
        score = 0.3

        # Pre-checks and reasoning instructions are high value
        if text.lower().startswith(("pre-check:", "reasoning:", "before ")):
            score += 0.3

        # Specific and actionable
        if len(text) > 20:
            score += 0.1
        if any(w in text.lower() for w in ["verify", "check", "consider", "analyze"]):
            score += 0.15

        return min(max(score, 0.0), 1.0)

    # ══════════════════════════════════════════════════════════════
    # ROLLBACK / UNDO
    # ══════════════════════════════════════════════════════════════

    def undo_last_evolution(self) -> Optional[str]:
        """Undo the last evolution. Returns description of what was undone."""
        entry = self._store.rollback_last()
        if entry:
            msg = f"Undone: {entry['action']} -- {entry['detail']}"
            logger.info(msg)
            return msg
        return None

    # ══════════════════════════════════════════════════════════════
    # CONVENIENCE: access sub-components
    # ══════════════════════════════════════════════════════════════

    @property
    def analyzer(self) -> PromptAnalyzer:
        return self._analyzer

    @property
    def store(self) -> EvolutionStore:
        return self._store

    @property
    def tracker(self) -> PerformanceTracker:
        return self._tracker
