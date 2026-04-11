"""
J.A.R.V.I.S — Autonomous Thinking Engine
The cognitive core. JARVIS reasons locally without any API calls.

This engine gives JARVIS its own thought process:
    - Internal monologue (structured reasoning chains)
    - Deductive reasoning (derive conclusions from known facts)
    - Goal tracking (persistent goals with priorities)
    - Local NLP (understand text without ML or API)
    - Context assembly (rich context for both local and API-assisted answers)

Philosophy:
    JARVIS should THINK before it speaks. Even when it needs an API,
    it should first reason about what it knows, what it doesn't,
    and how to frame the question. This makes every response smarter.

Dependencies: standard library + core.knowledge_graph only.
Thread-safe: all mutable state is protected by locks.
"""

import os
import re
import json
import time
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger("jarvis.thinking")

# ── Persistent storage ───────────────────────────────────────
_GOALS_FILE = Path.home() / ".jarvis_goals.json"
_RULES_FILE = Path.home() / ".jarvis_rules_meta.json"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict):
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, str(path))
    except OSError as e:
        logger.error("Failed to save %s: %s", path, e)


# ═════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═════════════════════════════════════════════════════════════════

@dataclass
class ParsedInput:
    """Result of local NLP parsing."""
    intent: str = "unknown"             # ask, command, inform, greet, confirm, deny, followup
    entities: dict = field(default_factory=dict)   # {type: [values]}
    question_type: str = "unknown"      # factual, procedural, analytical, creative, conversational
    topic: str = ""                     # main subject
    sentiment: str = "neutral"          # positive, negative, neutral
    urgency: str = "normal"             # low, normal, high, critical
    raw_text: str = ""


@dataclass
class Thought:
    """A single thought in JARVIS's internal monologue."""
    content: str
    thought_type: str = "observation"   # observation, deduction, question, plan, insight, concern
    confidence: float = 0.8
    timestamp: float = field(default_factory=time.time)

    def __str__(self):
        return f"[{self.thought_type}] {self.content}"


@dataclass
class ThoughtResult:
    """Complete result of the thinking process."""
    can_answer: bool = False
    answer: Optional[str] = None
    confidence: float = 0.0
    thoughts: list = field(default_factory=list)      # list[str] — internal monologue
    suggested_tools: list = field(default_factory=list)
    knowledge_used: list = field(default_factory=list)
    needs_api: bool = True
    api_context: str = ""
    parsed_input: Optional[ParsedInput] = None


@dataclass
class Goal:
    """A tracked goal with priority and status."""
    id: str
    description: str
    priority: int = 5                   # 1 (highest) to 10 (lowest)
    status: str = "active"              # active, completed, abandoned
    created_at: str = ""
    completed_at: str = ""
    parent_goal: str = ""               # for sub-goals
    context: str = ""                   # what triggered this goal
    progress_notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "parent_goal": self.parent_goal,
            "context": self.context,
            "progress_notes": self.progress_notes,
        }

    @staticmethod
    def from_dict(d: dict) -> "Goal":
        return Goal(
            id=d.get("id", ""),
            description=d.get("description", ""),
            priority=d.get("priority", 5),
            status=d.get("status", "active"),
            created_at=d.get("created_at", ""),
            completed_at=d.get("completed_at", ""),
            parent_goal=d.get("parent_goal", ""),
            context=d.get("context", ""),
            progress_notes=d.get("progress_notes", []),
        )


# ═════════════════════════════════════════════════════════════════
#  LOCAL NLP — Understand text without API
# ═════════════════════════════════════════════════════════════════

class LocalNLP:
    """
    Lightweight text understanding using regex, keywords, and heuristics.
    No ML models, no API calls. Fast and reliable for structured inputs.
    """

    # ── Entity patterns ──────────────────────────────────────────

    _ENTITY_PATTERNS = {
        "domain": re.compile(
            r"\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:com|org|net|io|co|uk|edu|gov|dev|app|"
            r"xyz|info|biz|me|us|ca|de|fr|jp|au|in|ru|br|nl|se|no|fi|ch|at|"
            r"co\.uk|co\.in|com\.au|com\.br|ac\.uk|org\.uk)[a-zA-Z.]*)\b"
        ),
        "ip": re.compile(
            r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"
        ),
        "ip_cidr": re.compile(
            r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})\b"
        ),
        "port": re.compile(
            r"\bport\s+(\d{1,5})\b|\b(?:on|at)\s+(?:port\s+)?:?(\d{1,5})\b",
            re.IGNORECASE,
        ),
        "cve": re.compile(
            r"\b(CVE-\d{4}-\d{4,})\b", re.IGNORECASE
        ),
        "file_path": re.compile(
            r'(?:[A-Za-z]:\\[\w\\. -]+|/(?:home|tmp|var|etc|usr|opt|root)/[\w/. -]+|'
            r'~/[\w/. -]+)'
        ),
        "url": re.compile(
            r"(https?://[^\s<>\"']+)"
        ),
        "email": re.compile(
            r"\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b"
        ),
        "technology": re.compile(
            r"\b(Apache|Nginx|IIS|Node\.?js|Python|Django|Flask|React|Angular|Vue|"
            r"PHP|Laravel|WordPress|Drupal|Joomla|MySQL|PostgreSQL|MongoDB|Redis|"
            r"Docker|Kubernetes|AWS|Azure|GCP|Linux|Windows|Ubuntu|Debian|CentOS|"
            r"Kali|Burp\s*Suite|Nmap|Metasploit|Wireshark|John|Hashcat|"
            r"SQLMap|Nikto|Gobuster|Dirbuster|Ffuf|Amass|Subfinder|"
            r"Nuclei|OWASP|ZAP|Nessus|OpenVAS|Shodan|Censys)\b",
            re.IGNORECASE,
        ),
        "http_method": re.compile(
            r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b"
        ),
        "hash": re.compile(
            r"\b([a-fA-F0-9]{32})\b|\b([a-fA-F0-9]{40})\b|\b([a-fA-F0-9]{64})\b"
        ),
    }

    # ── Intent patterns ──────────────────────────────────────────

    _INTENT_PATTERNS = [
        # Commands / directives
        (re.compile(
            r"^(?:scan|run|open|launch|start|stop|kill|close|find|search|"
            r"show|list|check|test|execute|deploy|install|update|remove|"
            r"delete|create|make|build|set|configure|enable|disable)\b",
            re.IGNORECASE,
        ), "command"),
        # Questions
        (re.compile(
            r"^(?:what|who|where|when|why|how|which|is|are|do|does|did|"
            r"can|could|would|should|will|shall|have|has|had)\b",
            re.IGNORECASE,
        ), "ask"),
        # Informing / telling
        (re.compile(
            r"^(?:I\s+(?:found|noticed|saw|think|believe|want|need|have|got)|"
            r"there\s+(?:is|are)|the\s+\w+\s+(?:is|are|has|have)|"
            r"it\s+(?:seems|looks|appears))",
            re.IGNORECASE,
        ), "inform"),
        # Greetings
        (re.compile(
            r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening|night)|"
            r"yo|sup|what'?s\s+up|howdy|greetings|jarvis)\b",
            re.IGNORECASE,
        ), "greet"),
        # Confirmations
        (re.compile(
            r"^(?:yes|yeah|yep|yup|sure|ok|okay|right|correct|exactly|"
            r"affirmative|do\s+it|go\s+ahead|proceed)\b",
            re.IGNORECASE,
        ), "confirm"),
        # Denials
        (re.compile(
            r"^(?:no|nope|nah|don't|stop|cancel|abort|never\s*mind|"
            r"forget\s+it|wrong|incorrect)\b",
            re.IGNORECASE,
        ), "deny"),
    ]

    # ── Question classification ──────────────────────────────────

    _QUESTION_TYPES = {
        "factual": re.compile(
            r"\b(?:what\s+is|who\s+is|where\s+is|when\s+(?:was|is|did)|"
            r"how\s+many|how\s+much|which\s+(?:one|port|version)|"
            r"what\s+(?:port|version|ip|domain|service|os)|"
            r"tell\s+me\s+about|what\s+do\s+(?:you|we)\s+know)\b",
            re.IGNORECASE,
        ),
        "procedural": re.compile(
            r"\b(?:how\s+(?:do|can|to|should)|steps?\s+to|"
            r"guide\s+(?:me|for)|tutorial|walk\s*through|"
            r"explain\s+how|show\s+me\s+how|what\s+are\s+the\s+steps)\b",
            re.IGNORECASE,
        ),
        "analytical": re.compile(
            r"\b(?:why\s+(?:is|does|did|would|should)|"
            r"what\s+(?:caused|if|would\s+happen)|"
            r"compare|analyze|assess|evaluate|"
            r"is\s+(?:it|this|that)\s+(?:safe|secure|vulnerable|risky)|"
            r"should\s+(?:I|we)|pros?\s+and\s+cons?|"
            r"what\s+do\s+you\s+think|risk|impact)\b",
            re.IGNORECASE,
        ),
        "creative": re.compile(
            r"\b(?:write|generate|create|compose|draft|design|"
            r"suggest|recommend|come\s+up\s+with|brainstorm|"
            r"make\s+(?:a|me)|give\s+me\s+(?:a|an)\s+(?:idea|example|name))\b",
            re.IGNORECASE,
        ),
        "conversational": re.compile(
            r"\b(?:how\s+are\s+you|what'?s\s+up|thank|sorry|"
            r"good\s+(?:morning|night|evening)|bye|see\s+you|"
            r"tell\s+me\s+a\s+joke|are\s+you\s+(?:there|alive|real)|"
            r"who\s+(?:are|made)\s+you|what\s+(?:can|do)\s+you\s+do)\b",
            re.IGNORECASE,
        ),
    }

    # ── Topic detection keywords ─────────────────────────────────

    _TOPIC_KEYWORDS = {
        "security": [
            "scan", "recon", "pentest", "penetration", "vulnerability", "vuln",
            "exploit", "cve", "hack", "attack", "payload", "injection", "xss",
            "sqli", "rce", "lfi", "rfi", "ssrf", "csrf", "idor", "brute",
            "password", "credential", "privilege", "escalat", "lateral",
            "port", "nmap", "burp", "metasploit", "kali", "ctf",
            "bug bounty", "security", "firewall", "ids", "ips",
            "malware", "phishing", "ransomware", "forensic",
        ],
        "networking": [
            "ip", "dns", "dhcp", "subnet", "gateway", "router", "switch",
            "tcp", "udp", "http", "https", "ssl", "tls", "vpn", "proxy",
            "socket", "packet", "bandwidth", "latency", "traceroute", "ping",
        ],
        "coding": [
            "code", "script", "function", "class", "variable", "debug",
            "error", "exception", "traceback", "compile", "runtime", "syntax",
            "python", "javascript", "java", "bash", "api", "library",
            "framework", "git", "github", "repository", "commit", "branch",
        ],
        "system": [
            "cpu", "ram", "memory", "disk", "process", "service", "driver",
            "boot", "shutdown", "restart", "update", "install", "uninstall",
            "registry", "task manager", "performance", "temperature",
        ],
        "web": [
            "website", "webpage", "browser", "chrome", "firefox",
            "html", "css", "javascript", "react", "angular", "vue",
            "frontend", "backend", "server", "hosting", "deploy",
            "domain", "subdomain", "certificate", "header",
        ],
        "personal": [
            "remind", "remember", "schedule", "alarm", "timer", "calendar",
            "todo", "task", "note", "bookmark", "favorite", "preference",
            "name", "age", "birthday", "like", "dislike", "hobby",
        ],
        "file_management": [
            "file", "folder", "directory", "copy", "move", "rename",
            "delete", "create", "open", "save", "download", "upload",
            "zip", "extract", "compress", "backup",
        ],
    }

    # ── Urgency signals ──────────────────────────────────────────

    _URGENCY_HIGH = re.compile(
        r"\b(?:urgent|emergency|asap|immediately|right\s+now|critical|"
        r"hurry|quick(?:ly)?|fast|important|help|broken|down|"
        r"not\s+working|crashed|hacked|compromised|breach|incident)\b",
        re.IGNORECASE,
    )

    _URGENCY_LOW = re.compile(
        r"\b(?:when\s+you\s+(?:get\s+a\s+chance|have\s+time|can)|"
        r"no\s+rush|whenever|eventually|some\s*time|later|low\s+priority|"
        r"just\s+curious|wondering|btw|by\s+the\s+way)\b",
        re.IGNORECASE,
    )

    def understand(self, text: str) -> ParsedInput:
        """Full NLP parse of user input."""
        result = ParsedInput(raw_text=text)
        text_stripped = text.strip()

        if not text_stripped:
            return result

        # 1. Intent
        result.intent = self._detect_intent(text_stripped)

        # 2. Entities
        result.entities = self.extract_entities(text_stripped)

        # 3. Question type
        result.question_type = self.classify_question(text_stripped)

        # 4. Topic
        result.topic = self.detect_topic(text_stripped)

        # 5. Sentiment
        result.sentiment = self._detect_sentiment(text_stripped)

        # 6. Urgency
        result.urgency = self._detect_urgency(text_stripped)

        return result

    def extract_entities(self, text: str) -> dict:
        """Extract all recognizable entities from text."""
        entities = {}
        for entity_type, pattern in self._ENTITY_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                # Flatten tuples from patterns with multiple groups
                values = []
                for m in matches:
                    if isinstance(m, tuple):
                        values.extend(v for v in m if v)
                    elif m:
                        values.append(m)
                if values:
                    entities[entity_type] = list(set(values))
        return entities

    def classify_question(self, text: str) -> str:
        """Classify the type of question being asked."""
        for qtype, pattern in self._QUESTION_TYPES.items():
            if pattern.search(text):
                return qtype
        return "unknown"

    def detect_topic(self, text: str) -> str:
        """Detect the main topic of the message."""
        text_lower = text.lower()
        topic_scores = {}

        for topic, keywords in self._TOPIC_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                topic_scores[topic] = score

        if not topic_scores:
            return "general"

        return max(topic_scores, key=topic_scores.get)

    def is_answerable_locally(self, text: str) -> bool:
        """Can JARVIS answer this without calling an API?"""
        text_lower = text.lower().strip()

        # Greetings — always local
        if self._detect_intent(text) == "greet":
            return True

        # Time/date questions
        if re.search(r"\b(?:what\s+time|what\s+day|what\s+date|what'?s\s+the\s+(?:time|date|day))\b", text_lower):
            return True

        # Knowledge graph queries (about entities JARVIS knows)
        if re.search(r"\b(?:what\s+do\s+(?:you|we)\s+know|tell\s+me\s+about|"
                     r"what\s+(?:ports?|vulns?|vulnerabilities|subdomains?|facts?|info)\s+"
                     r"(?:are|is|do|did|have|has|were|was)\s+(?:open|found|known|on|about))\b",
                     text_lower):
            return True

        # Status questions
        if re.search(r"\b(?:what\s+(?:should|can)\s+(?:I|we)\s+do\s+next|"
                     r"what'?s\s+(?:the|our)\s+(?:status|progress|plan|next\s+step))\b",
                     text_lower):
            return True

        # Confirmations / denials
        if self._detect_intent(text) in ("confirm", "deny"):
            return True

        # Meta-questions about JARVIS
        if re.search(r"\b(?:who\s+are\s+you|what\s+(?:can|do)\s+you\s+do|"
                     r"how\s+are\s+you|are\s+you\s+(?:there|alive|online))\b",
                     text_lower):
            return True

        # Reminders and notes
        if re.search(r"\b(?:remind|remember|note|save)\b", text_lower):
            return True

        return False

    def _detect_intent(self, text: str) -> str:
        """Detect user intent from text."""
        for pattern, intent in self._INTENT_PATTERNS:
            if pattern.search(text):
                return intent
        # Fallback: if it ends with ?, it's a question
        if text.rstrip().endswith("?"):
            return "ask"
        return "unknown"

    def _detect_sentiment(self, text: str) -> str:
        """Quick sentiment detection."""
        text_lower = text.lower()
        pos = len(re.findall(
            r"\b(?:great|awesome|perfect|love|amazing|thanks|cool|nice|good|"
            r"brilliant|excellent|happy|excited|yes|please|appreciate)\b",
            text_lower
        ))
        neg = len(re.findall(
            r"\b(?:bad|wrong|broken|hate|terrible|awful|annoying|stupid|"
            r"frustrated|confused|stuck|error|fail|sucks|damn|shit|ugh|"
            r"doesn't\s+work|can't|won't)\b",
            text_lower
        ))
        if pos > neg:
            return "positive"
        elif neg > pos:
            return "negative"
        return "neutral"

    def _detect_urgency(self, text: str) -> str:
        """Detect urgency level."""
        if self._URGENCY_HIGH.search(text):
            return "high" if "!" not in text else "critical"
        if self._URGENCY_LOW.search(text):
            return "low"
        return "normal"


# ═════════════════════════════════════════════════════════════════
#  GOAL TRACKER
# ═════════════════════════════════════════════════════════════════

class GoalTracker:
    """
    Tracks what JARVIS is trying to accomplish.
    Goals persist between sessions in ~/.jarvis_goals.json.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._goals: dict[str, Goal] = {}
        self._next_id = 1
        self._load()

    def _load(self):
        """Load goals from disk."""
        data = _load_json(_GOALS_FILE)
        goals_list = data.get("goals", [])
        self._next_id = data.get("next_id", 1)
        for g in goals_list:
            goal = Goal.from_dict(g)
            self._goals[goal.id] = goal

    def _save(self):
        """Persist goals to disk."""
        data = {
            "goals": [g.to_dict() for g in self._goals.values()],
            "next_id": self._next_id,
        }
        _save_json(_GOALS_FILE, data)

    def add_goal(self, description: str, priority: int = 5,
                 context: str = "", parent: str = "") -> str:
        """Add a new goal. Returns goal ID."""
        with self._lock:
            goal_id = f"goal_{self._next_id}"
            self._next_id += 1
            goal = Goal(
                id=goal_id,
                description=description,
                priority=max(1, min(10, priority)),
                created_at=datetime.now().isoformat(),
                context=context,
                parent_goal=parent,
            )
            self._goals[goal_id] = goal
            self._save()
            logger.info("New goal: [%s] %s (priority %d)", goal_id, description, priority)
            return goal_id

    def complete_goal(self, goal_id: str) -> bool:
        """Mark a goal as completed."""
        with self._lock:
            goal = self._goals.get(goal_id)
            if not goal:
                return False
            goal.status = "completed"
            goal.completed_at = datetime.now().isoformat()
            self._save()
            logger.info("Goal completed: [%s] %s", goal_id, goal.description)
            return True

    def abandon_goal(self, goal_id: str, reason: str = "") -> bool:
        """Abandon a goal."""
        with self._lock:
            goal = self._goals.get(goal_id)
            if not goal:
                return False
            goal.status = "abandoned"
            goal.completed_at = datetime.now().isoformat()
            if reason:
                goal.progress_notes.append(f"Abandoned: {reason}")
            self._save()
            return True

    def add_progress(self, goal_id: str, note: str):
        """Add a progress note to a goal."""
        with self._lock:
            goal = self._goals.get(goal_id)
            if goal:
                goal.progress_notes.append(f"[{datetime.now().strftime('%H:%M')}] {note}")
                # Keep last 20 notes per goal
                goal.progress_notes = goal.progress_notes[-20:]
                self._save()

    def get_active_goals(self) -> list[Goal]:
        """Get all active goals sorted by priority."""
        with self._lock:
            active = [g for g in self._goals.values() if g.status == "active"]
            return sorted(active, key=lambda g: g.priority)

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a specific goal."""
        return self._goals.get(goal_id)

    def find_goals(self, keyword: str) -> list[Goal]:
        """Search goals by keyword."""
        keyword_lower = keyword.lower()
        return [
            g for g in self._goals.values()
            if keyword_lower in g.description.lower() or keyword_lower in g.context.lower()
        ]

    def suggest_next_action(self) -> Optional[str]:
        """Based on active goals, suggest what to do next."""
        active = self.get_active_goals()
        if not active:
            return None

        top_goal = active[0]
        notes = top_goal.progress_notes

        if not notes:
            return f"Start working on: {top_goal.description}"
        else:
            last_note = notes[-1]
            return f"Continue with '{top_goal.description}' — last progress: {last_note}"

    def auto_generate_goal(self, text: str, topic: str) -> Optional[str]:
        """Automatically generate a goal from context if appropriate."""
        text_lower = text.lower()

        # Pentest / recon triggers
        if re.search(r"\b(?:pentest|pen\s+test|penetration\s+test|security\s+(?:test|audit|assessment))\b", text_lower):
            entities = LocalNLP._ENTITY_PATTERNS["domain"].findall(text)
            target = entities[0] if entities else "the target"
            # Don't duplicate existing goals
            existing = self.find_goals(target)
            if not existing:
                return self.add_goal(
                    f"Complete penetration test on {target}",
                    priority=3,
                    context=text[:200],
                )

        # Bug bounty triggers
        if re.search(r"\b(?:bug\s*bounty|bounty\s*program)\b", text_lower):
            entities = LocalNLP._ENTITY_PATTERNS["domain"].findall(text)
            target = entities[0] if entities else "the target"
            existing = self.find_goals("bug bounty")
            if not existing:
                return self.add_goal(
                    f"Bug bounty hunting on {target}",
                    priority=3,
                    context=text[:200],
                )

        # Project / build triggers
        if re.search(r"\b(?:build|create|develop|make)\s+(?:a|an|the)\s+(\w[\w\s]{2,30})\b", text_lower):
            match = re.search(r"\b(?:build|create|develop|make)\s+(?:a|an|the)\s+(\w[\w\s]{2,30})\b", text_lower)
            if match:
                project = match.group(1).strip()
                existing = self.find_goals(project)
                if not existing:
                    return self.add_goal(
                        f"Build {project}",
                        priority=5,
                        context=text[:200],
                    )

        return None

    def cleanup_stale(self, days: int = 14):
        """Abandon goals that haven't had progress in N days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._lock:
            for goal in list(self._goals.values()):
                if goal.status != "active":
                    continue
                # Check last activity
                last_activity = goal.created_at
                if goal.progress_notes:
                    last_activity = goal.progress_notes[-1]
                # Simple date check (not perfect but good enough)
                if last_activity < cutoff:
                    goal.status = "abandoned"
                    goal.progress_notes.append(f"Auto-abandoned: no activity for {days} days")
            self._save()

    def get_context_string(self) -> str:
        """Format active goals for context injection."""
        active = self.get_active_goals()
        if not active:
            return ""
        lines = ["[ACTIVE GOALS]"]
        for g in active[:5]:
            status = f"P{g.priority}"
            progress = f" — {g.progress_notes[-1]}" if g.progress_notes else ""
            lines.append(f"  [{status}] {g.description}{progress}")
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════
#  DEDUCTIVE REASONING ENGINE
# ═════════════════════════════════════════════════════════════════

class DeductiveReasoner:
    """
    Given a set of facts, derive new conclusions using rules.
    Rules are (condition, conclusion) pairs — extensible and learnable.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._rules: list[tuple[Callable, Callable, str, float]] = []
        # Each rule: (condition_func, conclusion_func, rule_name, confidence)
        self._rule_stats = _load_json(_RULES_FILE)  # {rule_name: {applied, correct, wrong}}
        self._register_builtin_rules()

    def _register_builtin_rules(self):
        """Register all built-in deduction rules."""

        # ── Security rules ───────────────────────────────────────

        self.add_rule(
            "web_server_detection",
            condition=lambda facts: any(
                "port_80" in f or "port_443" in f or "port_8080" in f or "port_8443" in f
                for f in facts
            ),
            conclusion=lambda facts: "This entity is likely a web server (HTTP/HTTPS ports open).",
            confidence=0.9,
        )

        self.add_rule(
            "high_risk_public_vuln",
            condition=lambda facts: (
                any("vulnerable_to" in f for f in facts) and
                any("public" in f or "internet" in f or "external" in f for f in facts)
            ),
            conclusion=lambda facts: "HIGH RISK: Public-facing asset with known vulnerability. Prioritize remediation.",
            confidence=0.95,
        )

        self.add_rule(
            "cve_version_match",
            condition=lambda facts: (
                any("cve" in f.lower() for f in facts) and
                any("version" in f.lower() for f in facts)
            ),
            conclusion=lambda facts: "CVE found with version information — verify if this version is affected.",
            confidence=0.85,
        )

        self.add_rule(
            "missing_security_headers",
            condition=lambda facts: any(
                "missing_hsts" in f or "missing_csp" in f or
                "missing_x_frame" in f or "missing_xcto" in f
                for f in facts
            ),
            conclusion=lambda facts: "Security headers are missing — this is a misconfiguration that should be reported.",
            confidence=0.9,
        )

        self.add_rule(
            "ssl_issues",
            condition=lambda facts: any(
                "ssl_expired" in f or "ssl_weak" in f or "ssl_self_signed" in f
                for f in facts
            ),
            conclusion=lambda facts: "SSL/TLS issues detected — certificate problems indicate poor security hygiene.",
            confidence=0.9,
        )

        self.add_rule(
            "attack_surface_assessment",
            condition=lambda facts: sum(1 for f in facts if "port_" in f) >= 5,
            conclusion=lambda facts: (
                f"Large attack surface: {sum(1 for f in facts if 'port_' in f)} open ports detected. "
                "Consider prioritizing service enumeration and vulnerability scanning on each."
            ),
            confidence=0.85,
        )

        self.add_rule(
            "subdomain_not_scanned",
            condition=lambda facts: (
                any("has_subdomain" in f for f in facts) and
                any("subdomain" in f and "not_scanned" in f for f in facts)
            ),
            conclusion=lambda facts: "Discovered subdomains that haven't been scanned yet — recommend scanning them.",
            confidence=0.8,
        )

        self.add_rule(
            "database_exposure",
            condition=lambda facts: any(
                "port_3306" in f or "port_5432" in f or "port_27017" in f or
                "port_6379" in f or "port_1433" in f
                for f in facts
            ),
            conclusion=lambda facts: "Database port exposed — check if authentication is required and if it's internet-facing.",
            confidence=0.9,
        )

        self.add_rule(
            "ssh_open",
            condition=lambda facts: any("port_22" in f for f in facts),
            conclusion=lambda facts: "SSH is open — check for password auth, key-based only is recommended. Check for default credentials.",
            confidence=0.8,
        )

        self.add_rule(
            "admin_panel_exposed",
            condition=lambda facts: any(
                "/admin" in f or "/wp-admin" in f or "/phpmyadmin" in f or
                "/manager" in f or "/console" in f or "/dashboard" in f
                for f in facts
            ),
            conclusion=lambda facts: "Administrative panel exposed — this should be restricted or behind authentication.",
            confidence=0.85,
        )

        # ── Behavioral rules ────────────────────────────────────

        self.add_rule(
            "user_confused",
            condition=lambda facts: any("repeated_question" in f for f in facts),
            conclusion=lambda facts: "User has asked this question before — try a different explanation approach.",
            confidence=0.7,
        )

        self.add_rule(
            "late_night_work",
            condition=lambda facts: any("late_hour" in f for f in facts) and any("working" in f for f in facts),
            conclusion=lambda facts: "It's late and the user is still working — consider suggesting a break.",
            confidence=0.6,
        )

        self.add_rule(
            "error_on_screen",
            condition=lambda facts: any("screen_error" in f for f in facts),
            conclusion=lambda facts: "Error detected on screen — try to identify the error type and suggest a fix.",
            confidence=0.7,
        )

        self.add_rule(
            "scan_complete_next_step",
            condition=lambda facts: (
                any("scan_completed" in f for f in facts) and
                not any("vulnerability_scan" in f for f in facts)
            ),
            conclusion=lambda facts: "Reconnaissance scan completed — suggest vulnerability scanning on discovered services.",
            confidence=0.75,
        )

    def add_rule(self, name: str, condition: Callable, conclusion: Callable,
                 confidence: float = 0.8):
        """Add a deduction rule."""
        self._rules.append((condition, conclusion, name, confidence))
        if name not in self._rule_stats:
            self._rule_stats[name] = {"applied": 0, "correct": 0, "wrong": 0}

    def deduce(self, facts: list[str]) -> list[dict]:
        """
        Given a set of facts (strings), apply all rules and return new conclusions.
        Returns list of {conclusion, rule, confidence}.
        """
        conclusions = []
        with self._lock:
            for condition_fn, conclusion_fn, rule_name, base_confidence in self._rules:
                try:
                    if condition_fn(facts):
                        conclusion_text = conclusion_fn(facts)
                        # Adjust confidence based on historical accuracy
                        adjusted_confidence = self._adjusted_confidence(rule_name, base_confidence)
                        conclusions.append({
                            "conclusion": conclusion_text,
                            "rule": rule_name,
                            "confidence": adjusted_confidence,
                        })
                        # Track application
                        stats = self._rule_stats.get(rule_name, {})
                        stats["applied"] = stats.get("applied", 0) + 1
                        self._rule_stats[rule_name] = stats
                except Exception as e:
                    logger.debug("Rule '%s' raised error: %s", rule_name, e)

        return conclusions

    def record_outcome(self, rule_name: str, correct: bool):
        """Record whether a deduction was correct — adjusts future confidence."""
        with self._lock:
            if rule_name not in self._rule_stats:
                self._rule_stats[rule_name] = {"applied": 0, "correct": 0, "wrong": 0}
            stats = self._rule_stats[rule_name]
            if correct:
                stats["correct"] = stats.get("correct", 0) + 1
            else:
                stats["wrong"] = stats.get("wrong", 0) + 1
                logger.info("Rule '%s' was wrong — lowering confidence", rule_name)
            _save_json(_RULES_FILE, self._rule_stats)

    def _adjusted_confidence(self, rule_name: str, base: float) -> float:
        """Adjust rule confidence based on past accuracy."""
        stats = self._rule_stats.get(rule_name, {})
        correct = stats.get("correct", 0)
        wrong = stats.get("wrong", 0)
        total = correct + wrong
        if total < 3:
            return base  # not enough data yet
        accuracy = correct / total
        # Blend base confidence with observed accuracy
        return round(base * 0.4 + accuracy * 0.6, 3)

    def get_rule_stats(self) -> dict:
        """Get stats for all rules."""
        return dict(self._rule_stats)


# ═════════════════════════════════════════════════════════════════
#  CONTEXT BUILDER
# ═════════════════════════════════════════════════════════════════

class ContextBuilder:
    """
    Assembles all available context for reasoning.
    Used both for local thinking and for enriching API calls.
    """

    def __init__(self, jarvis):
        self._jarvis = jarvis

    def build_context(self, text: str, parsed: Optional[ParsedInput] = None) -> str:
        """
        Build rich context from all available sources.
        This context makes both local reasoning and API calls much smarter.
        """
        sections = []

        # 1. Knowledge graph context — what do we know about mentioned entities?
        kg_context = self._get_knowledge_context(text, parsed)
        if kg_context:
            sections.append(kg_context)

        # 2. Conversation history
        conv_context = self._get_conversation_context()
        if conv_context:
            sections.append(conv_context)

        # 3. Screen / environment context
        screen_context = self._get_screen_context()
        if screen_context:
            sections.append(screen_context)

        # 4. Time context
        time_context = self._get_time_context()
        sections.append(time_context)

        # 5. Active goals
        goal_context = self._get_goal_context()
        if goal_context:
            sections.append(goal_context)

        # 6. User identity/mood
        user_context = self._get_user_context()
        if user_context:
            sections.append(user_context)

        return "\n\n".join(sections)

    def _get_knowledge_context(self, text: str, parsed: Optional[ParsedInput] = None) -> str:
        """Query knowledge graph for mentioned entities."""
        kg = self._get_kg()
        if not kg:
            return ""

        parts = []
        entities_to_query = []

        # Extract entities from parsed input
        if parsed and parsed.entities:
            for etype, values in parsed.entities.items():
                entities_to_query.extend(values)

        # Also do a general topic query
        if parsed and parsed.topic and parsed.topic != "general":
            entities_to_query.append(parsed.topic)

        # Search for each entity in knowledge graph
        seen = set()
        for entity in entities_to_query[:5]:  # limit to prevent slowness
            if entity.lower() in seen:
                continue
            seen.add(entity.lower())

            data = kg.query_everything(entity)
            if data.get("entity"):
                ent = data["entity"]
                lines = [f"[KNOWLEDGE: {ent['name']}] type={ent['type']}"]
                facts = ent.get("facts", {})
                for pred, val in list(facts.items())[:10]:
                    lines.append(f"  {pred}: {val}")
                for rel in data.get("relationships", [])[:5]:
                    if rel.get("direction") == "out":
                        lines.append(f"  {rel['predicate']} -> {rel['target']}")
                    else:
                        lines.append(f"  {rel.get('source', '?')} -> {rel['predicate']}")
                parts.append("\n".join(lines))
            else:
                # Try searching
                results = kg.search_entities(entity, limit=3)
                if results:
                    matches = ", ".join(f"{r['name']}({r['type']})" for r in results)
                    parts.append(f"[SEARCH '{entity}'] Possible matches: {matches}")

        return "\n".join(parts) if parts else ""

    def _get_conversation_context(self) -> str:
        """Get recent conversation history."""
        try:
            memory = getattr(self._jarvis, "memory", None)
            if memory:
                # Try MemorySystem
                session = getattr(memory, "session", None)
                if session:
                    msgs = session.recent_messages
                    if msgs:
                        lines = ["[RECENT CONVERSATION]"]
                        for msg in msgs[-6:]:
                            role = msg.get("role", "?")
                            content = msg.get("content", "")[:150]
                            lines.append(f"  {role}: {content}")
                        return "\n".join(lines)

            # Fallback: try short_term
            stm = getattr(self._jarvis, "short_term", None)
            if stm:
                msgs = stm.get_recent()
                if msgs:
                    lines = ["[RECENT CONVERSATION]"]
                    for msg in msgs[-6:]:
                        role = msg.get("role", "?")
                        content = msg.get("content", "")[:150]
                        lines.append(f"  {role}: {content}")
                    return "\n".join(lines)
        except Exception:
            pass
        return ""

    def _get_screen_context(self) -> str:
        """Get current screen/environment context."""
        try:
            awareness = getattr(self._jarvis, "awareness", None)
            if awareness:
                state = getattr(awareness, "get_state", None)
                if state:
                    s = state()
                    if s:
                        parts = ["[SCREEN CONTEXT]"]
                        if hasattr(s, "active_window") and s.active_window:
                            parts.append(f"  Active window: {s.active_window}")
                        if hasattr(s, "recent_text") and s.recent_text:
                            parts.append(f"  Screen text: {s.recent_text[:200]}")
                        return "\n".join(parts)
        except Exception:
            pass
        return ""

    def _get_time_context(self) -> str:
        """Get time/date context."""
        now = datetime.now()
        hour = now.hour
        if hour < 6:
            period = "very late at night"
        elif hour < 9:
            period = "early morning"
        elif hour < 12:
            period = "morning"
        elif hour < 14:
            period = "around noon"
        elif hour < 17:
            period = "afternoon"
        elif hour < 20:
            period = "evening"
        elif hour < 23:
            period = "night"
        else:
            period = "late night"

        return (
            f"[TIME] {now.strftime('%A, %B %d, %Y — %H:%M')} ({period})"
        )

    def _get_goal_context(self) -> str:
        """Get active goals context."""
        try:
            thinking = getattr(self._jarvis, "thinking_engine", None)
            if thinking:
                return thinking.goals.get_context_string()
        except Exception:
            pass
        return ""

    def _get_user_context(self) -> str:
        """Get user identity and mood context."""
        parts = []
        try:
            memory = getattr(self._jarvis, "memory", None)
            if memory:
                identity = getattr(memory, "identity", None)
                if identity:
                    parts.append(identity.get_context_string())

            intel = getattr(self._jarvis, "intelligence", None)
            if intel:
                mood = intel.get_mood()
                if mood and mood != "neutral":
                    parts.append(f"[USER MOOD] {mood}")
        except Exception:
            pass
        return "\n".join(parts) if parts else ""

    def _get_kg(self):
        """Safely get KnowledgeGraph reference."""
        try:
            return getattr(self._jarvis, "knowledge_graph", None) or \
                   getattr(self._jarvis, "kg", None)
        except Exception:
            return None


# ═════════════════════════════════════════════════════════════════
#  THINKING ENGINE — The Main Brain
# ═════════════════════════════════════════════════════════════════

class ThinkingEngine:
    """
    JARVIS's autonomous thinking engine.
    Reasons locally, tracks goals, understands context, and decides
    whether it can answer without an API call.

    Usage:
        engine = ThinkingEngine(jarvis_app)
        result = engine.think("what ports are open on example.com?")
        if result.can_answer:
            print(result.answer)
        else:
            # Use result.api_context to enrich the API call
            api_response = call_api(text, context=result.api_context)
    """

    def __init__(self, jarvis=None):
        self._jarvis = jarvis
        self._lock = threading.Lock()

        # Sub-systems
        self.nlp = LocalNLP()
        self.goals = GoalTracker()
        self.reasoner = DeductiveReasoner()
        self.context_builder = ContextBuilder(jarvis) if jarvis else None

        # Internal state
        self._recent_thoughts: list[Thought] = []       # rolling buffer
        self._reflection_log: list[str] = []             # insights
        self._interaction_count = 0
        self._last_topics: list[str] = []                # for pattern detection

        logger.info("Thinking engine initialized — JARVIS can think now")

    # ─────────────────────────────────────────────────────────────
    #  MAIN ENTRY POINT
    # ─────────────────────────────────────────────────────────────

    def think(self, text: str, context: str = None) -> ThoughtResult:
        """
        The main thinking method. Given user input, JARVIS:
        1. Parses the input (NLP)
        2. Generates internal monologue
        3. Queries knowledge graph
        4. Applies deductive reasoning
        5. Decides if it can answer locally
        6. Builds rich context for API if needed

        Returns ThoughtResult with answer or enriched context.
        """
        result = ThoughtResult()

        with self._lock:
            self._interaction_count += 1

        # Step 1: Parse input
        parsed = self.nlp.understand(text)
        result.parsed_input = parsed

        # Step 2: Internal monologue
        thoughts = self._internal_monologue(text, parsed)
        result.thoughts = [str(t) for t in thoughts]

        # Step 3: Try to answer locally
        local_answer = self._try_local_answer(text, parsed)
        if local_answer:
            result.can_answer = True
            result.answer = local_answer["answer"]
            result.confidence = local_answer["confidence"]
            result.knowledge_used = local_answer.get("knowledge_used", [])
            result.needs_api = False
            self._add_thought(Thought(
                content=f"I can answer this locally with {result.confidence:.0%} confidence.",
                thought_type="deduction",
                confidence=result.confidence,
            ))
        else:
            result.needs_api = True
            self._add_thought(Thought(
                content="I need API assistance for this one. Let me build context.",
                thought_type="observation",
            ))

        # Step 4: Deductive reasoning on available facts
        facts = self._gather_facts(text, parsed)
        if facts:
            deductions = self.reasoner.deduce(facts)
            for d in deductions:
                result.thoughts.append(f"[deduction] {d['conclusion']}")
                self._add_thought(Thought(
                    content=d["conclusion"],
                    thought_type="deduction",
                    confidence=d["confidence"],
                ))

        # Step 5: Suggest tools that might help
        result.suggested_tools = self._suggest_tools(parsed)

        # Step 6: Build enriched context for API call
        if result.needs_api and self.context_builder:
            api_context_parts = []

            # Knowledge context
            built_context = self.context_builder.build_context(text, parsed)
            if built_context:
                api_context_parts.append(built_context)

            # Add our deductions
            if result.thoughts:
                api_context_parts.append(
                    "[JARVIS ANALYSIS]\n" +
                    "\n".join(f"  - {t}" for t in result.thoughts[:8])
                )

            # Add goal context
            goal_ctx = self.goals.get_context_string()
            if goal_ctx:
                api_context_parts.append(goal_ctx)

            result.api_context = "\n\n".join(api_context_parts)
        elif result.needs_api:
            # No context builder, still provide what we can
            result.api_context = "\n".join(f"- {t}" for t in result.thoughts[:5])

        # Step 7: Auto-generate goals from context
        self.goals.auto_generate_goal(text, parsed.topic)

        # Track topic
        if parsed.topic and parsed.topic != "general":
            self._last_topics.append(parsed.topic)
            self._last_topics = self._last_topics[-20:]

        return result

    def reason(self, question: str) -> Optional[str]:
        """
        Try to answer a question using only local knowledge.
        Returns the answer string or None if it can't answer.
        """
        result = self.think(question)
        if result.can_answer:
            return result.answer
        return None

    # ─────────────────────────────────────────────────────────────
    #  INTERNAL MONOLOGUE
    # ─────────────────────────────────────────────────────────────

    def _internal_monologue(self, text: str, parsed: ParsedInput) -> list[Thought]:
        """
        Generate JARVIS's internal thought chain.
        This is the "thinking out loud" process.
        """
        thoughts = []

        # What did the user say?
        thoughts.append(Thought(
            content=f"User's message: intent={parsed.intent}, topic={parsed.topic}, "
                    f"question_type={parsed.question_type}, urgency={parsed.urgency}",
            thought_type="observation",
        ))

        # What entities are mentioned?
        if parsed.entities:
            entity_summary = ", ".join(
                f"{k}: {v}" for k, v in list(parsed.entities.items())[:5]
            )
            thoughts.append(Thought(
                content=f"Entities detected: {entity_summary}",
                thought_type="observation",
            ))

        # What do I know about these entities?
        kg = self._get_kg()
        if kg and parsed.entities:
            for etype, values in list(parsed.entities.items())[:3]:
                for val in values[:2]:
                    entity_data = kg.get_entity(val)
                    if entity_data:
                        fact_count = len(entity_data.get("facts", {}))
                        thoughts.append(Thought(
                            content=f"I know about '{val}' — {fact_count} facts stored, "
                                    f"type: {entity_data.get('type', 'unknown')}",
                            thought_type="observation",
                            confidence=0.9,
                        ))
                    else:
                        thoughts.append(Thought(
                            content=f"'{val}' is new to me — no existing knowledge.",
                            thought_type="observation",
                            confidence=0.5,
                        ))

        # Can I answer this locally?
        if self.nlp.is_answerable_locally(text):
            thoughts.append(Thought(
                content="This looks like something I can handle locally.",
                thought_type="deduction",
                confidence=0.8,
            ))
        else:
            thoughts.append(Thought(
                content="This likely needs an API call, but let me gather context first.",
                thought_type="plan",
                confidence=0.7,
            ))

        # Urgency assessment
        if parsed.urgency in ("high", "critical"):
            thoughts.append(Thought(
                content=f"This is {parsed.urgency} urgency — prioritize fast response.",
                thought_type="concern",
                confidence=0.85,
            ))

        # Mood awareness
        if parsed.sentiment == "negative":
            thoughts.append(Thought(
                content="User seems frustrated or unhappy — be extra helpful and clear.",
                thought_type="concern",
                confidence=0.7,
            ))

        # Goal relevance
        active_goals = self.goals.get_active_goals()
        if active_goals:
            for goal in active_goals[:2]:
                if any(word in goal.description.lower()
                       for word in text.lower().split()
                       if len(word) > 3):
                    thoughts.append(Thought(
                        content=f"This relates to active goal: '{goal.description}'",
                        thought_type="observation",
                        confidence=0.7,
                    ))

        # Pattern detection: same topic repeatedly
        if parsed.topic in self._last_topics[-5:]:
            topic_count = self._last_topics[-10:].count(parsed.topic)
            if topic_count >= 3:
                thoughts.append(Thought(
                    content=f"User has been focused on '{parsed.topic}' for a while — "
                            "they're deep in this work.",
                    thought_type="insight",
                    confidence=0.7,
                ))

        return thoughts

    # ─────────────────────────────────────────────────────────────
    #  LOCAL ANSWERING
    # ─────────────────────────────────────────────────────────────

    def _try_local_answer(self, text: str, parsed: ParsedInput) -> Optional[dict]:
        """
        Try to answer the question using only local knowledge.
        Returns {answer, confidence, knowledge_used} or None.
        """
        text_lower = text.lower().strip()

        # ── Greetings ────────────────────────────────────────────
        # Only answer greetings if it's a PURE greeting (short, no task words)
        # "Jarvis you didn't send the text" should NOT trigger a greeting
        task_words = {"open", "send", "text", "search", "scan", "check", "find",
                      "click", "type", "call", "why", "how", "what", "didn't",
                      "not", "wrong", "fix", "try", "help", "can", "do", "navigate"}
        text_words = set(text_lower.split())
        has_task_intent = bool(text_words & task_words)

        if parsed.intent == "greet" and len(text_lower.split()) <= 4 and not has_task_intent:
            hour = datetime.now().hour
            if hour < 12:
                greeting = "Good morning"
            elif hour < 17:
                greeting = "Good afternoon"
            elif hour < 21:
                greeting = "Good evening"
            else:
                greeting = "Good evening"

            user_name = self._get_user_name()
            return {
                "answer": f"{greeting}, {user_name}. How can I help you?",
                "confidence": 1.0,
                "knowledge_used": ["time_of_day", "user_identity"],
            }

        # ── Time/date questions ──────────────────────────────────
        if re.search(r"\b(?:what\s+(?:time|day|date)|what'?s\s+the\s+(?:time|date|day))\b", text_lower):
            now = datetime.now()
            if "time" in text_lower:
                answer = f"It's {now.strftime('%H:%M')} right now."
            elif "day" in text_lower:
                answer = f"Today is {now.strftime('%A, %B %d, %Y')}."
            else:
                answer = f"It's {now.strftime('%A, %B %d, %Y at %H:%M')}."
            return {
                "answer": answer,
                "confidence": 1.0,
                "knowledge_used": ["system_clock"],
            }

        # ── Meta questions about JARVIS ──────────────────────────
        if re.search(r"\b(?:who\s+are\s+you|what\s+are\s+you)\b", text_lower):
            return {
                "answer": "I'm JARVIS — Just A Rather Very Intelligent System. "
                          "I'm your personal AI assistant, built to help with cybersecurity, "
                          "automation, and anything else you need.",
                "confidence": 1.0,
                "knowledge_used": ["self_identity"],
            }

        if re.search(r"\b(?:how\s+are\s+you|are\s+you\s+(?:ok|okay|alright|there|alive|online))\b", text_lower):
            return {
                "answer": "All systems operational. Ready to assist.",
                "confidence": 1.0,
                "knowledge_used": ["self_status"],
            }

        if re.search(r"\b(?:what\s+(?:can|do)\s+you\s+do)\b", text_lower):
            return {
                "answer": (
                    "I can help with a lot. Security reconnaissance, port scanning, "
                    "vulnerability analysis, code assistance, file management, web research, "
                    "screen awareness, task tracking, and general conversation. "
                    "I also learn from our interactions and track goals. What do you need?"
                ),
                "confidence": 1.0,
                "knowledge_used": ["self_capabilities"],
            }

        # ── Knowledge graph queries ──────────────────────────────
        kg = self._get_kg()
        if kg:
            # "What do you know about X?"
            know_match = re.search(
                r"(?:what\s+do\s+(?:you|we)\s+know\s+about|"
                r"tell\s+me\s+(?:about|everything\s+about)|"
                r"info\s+(?:on|about)|information\s+(?:on|about))\s+(.+?)[\?.]?\s*$",
                text_lower
            )
            if know_match:
                topic = know_match.group(1).strip()
                return self._answer_from_knowledge(kg, topic)

            # "What ports are open on X?"
            port_match = re.search(
                r"what\s+ports?\s+(?:are|is)\s+open\s+(?:on|for)\s+(.+?)[\?.]?\s*$",
                text_lower
            )
            if port_match:
                target = port_match.group(1).strip()
                return self._answer_ports(kg, target)

            # "What vulnerabilities did we find?"
            if re.search(r"(?:what|which)\s+(?:vulns?|vulnerabilities)\s+(?:did\s+we\s+find|were\s+found|are\s+(?:there|known))", text_lower):
                return self._answer_vulnerabilities(kg, parsed)

            # "What subdomains of X?"
            sub_match = re.search(
                r"(?:what|which|list)\s+subdomains?\s+(?:of|for|on)\s+(.+?)[\?.]?\s*$",
                text_lower
            )
            if sub_match:
                target = sub_match.group(1).strip()
                return self._answer_subdomains(kg, target)

        # ── Goal queries ─────────────────────────────────────────
        if re.search(r"\b(?:what\s+should\s+(?:I|we)\s+do\s+next|next\s+step|what'?s\s+next)\b", text_lower):
            suggestion = self.goals.suggest_next_action()
            if suggestion:
                return {
                    "answer": suggestion,
                    "confidence": 0.75,
                    "knowledge_used": ["goal_tracker"],
                }

        if re.search(r"\b(?:what\s+(?:are|is)\s+(?:my|our|the)\s+goals?|show\s+goals?|active\s+goals?)\b", text_lower):
            active = self.goals.get_active_goals()
            if active:
                lines = [f"You have {len(active)} active goal(s):"]
                for g in active:
                    lines.append(f"  [{g.id}] (P{g.priority}) {g.description}")
                    if g.progress_notes:
                        lines.append(f"    Last: {g.progress_notes[-1]}")
                return {
                    "answer": "\n".join(lines),
                    "confidence": 0.95,
                    "knowledge_used": ["goal_tracker"],
                }
            else:
                return {
                    "answer": "No active goals at the moment. Want to set one?",
                    "confidence": 0.95,
                    "knowledge_used": ["goal_tracker"],
                }

        # ── Status/progress queries ──────────────────────────────
        if re.search(r"\b(?:status|progress|where\s+(?:are|were)\s+we|where\s+did\s+we\s+leave\s+off)\b", text_lower):
            return self._answer_status()

        # ── Security assessment queries ──────────────────────────
        if kg and re.search(r"\b(?:is\s+(?:it|this|that)\s+(?:safe|secure)|security\s+(?:status|assessment))\b", text_lower):
            # Try to find the target entity
            entities = parsed.entities.get("domain", []) or parsed.entities.get("ip", [])
            if entities:
                return self._answer_security_assessment(kg, entities[0])

        return None

    # ── Knowledge-based answer helpers ───────────────────────────

    def _answer_from_knowledge(self, kg, topic: str) -> Optional[dict]:
        """Answer 'what do you know about X' from knowledge graph."""
        data = kg.query_everything(topic)

        if not data.get("entity") and not data.get("facts"):
            # Try searching
            results = kg.search_entities(topic, limit=3)
            if results:
                matches = ", ".join(f"{r['name']} ({r['type']})" for r in results)
                return {
                    "answer": f"I don't have direct info on '{topic}', but I found related entities: {matches}. "
                              "Would you like details on any of these?",
                    "confidence": 0.5,
                    "knowledge_used": ["knowledge_graph_search"],
                }
            return None

        lines = [f"Here's what I know about {topic}:"]
        knowledge_used = []

        if data["entity"]:
            ent = data["entity"]
            lines.append(f"  Type: {ent.get('type', 'unknown')}")
            facts = ent.get("facts", {})
            if facts:
                for pred, val in list(facts.items())[:15]:
                    lines.append(f"  {pred}: {val}")
                    knowledge_used.append(f"fact:{pred}")

        if data["relationships"]:
            lines.append("  Relationships:")
            for rel in data["relationships"][:8]:
                if rel.get("direction") == "out":
                    lines.append(f"    {rel['predicate']} -> {rel['target']}")
                else:
                    lines.append(f"    {rel.get('source', '?')} -> {rel['predicate']}")
                knowledge_used.append(f"rel:{rel['predicate']}")

        if data["timeline"]:
            lines.append(f"  Recent events: {len(data['timeline'])} recorded")
            for event in data["timeline"][:3]:
                lines.append(f"    [{event.get('event_type', '?')}] {event.get('description', '')[:80]}")

        return {
            "answer": "\n".join(lines),
            "confidence": 0.9,
            "knowledge_used": knowledge_used or ["knowledge_graph"],
        }

    def _answer_ports(self, kg, target: str) -> Optional[dict]:
        """Answer 'what ports are open on X'."""
        facts = kg.get_facts(target)
        if not facts:
            return None

        port_facts = [f for f in facts if f.get("predicate", "").startswith("port_")]
        if not port_facts:
            return {
                "answer": f"I don't have port scan data for '{target}'. Want me to scan it?",
                "confidence": 0.7,
                "knowledge_used": ["knowledge_graph_miss"],
            }

        lines = [f"Open ports on {target}:"]
        for pf in port_facts:
            port_num = pf["predicate"].replace("port_", "")
            service = pf.get("value", "unknown")
            lines.append(f"  Port {port_num}: {service}")

        return {
            "answer": "\n".join(lines),
            "confidence": 0.9,
            "knowledge_used": [f"fact:{pf['predicate']}" for pf in port_facts],
        }

    def _answer_vulnerabilities(self, kg, parsed: ParsedInput) -> Optional[dict]:
        """Answer 'what vulnerabilities did we find'."""
        # Search for all entities with vulnerability facts
        kg_obj = kg
        try:
            with kg_obj._conn() as conn:
                rows = conn.execute("""
                    SELECT e.name, f.predicate, f.value, f.confidence
                    FROM facts f
                    JOIN entities e ON f.entity_id = e.id
                    WHERE f.predicate LIKE '%vuln%' OR f.predicate LIKE '%cve%'
                       OR f.value LIKE '%vuln%' OR f.value LIKE '%xss%'
                       OR f.value LIKE '%sqli%' OR f.value LIKE '%rce%'
                    ORDER BY f.confidence DESC
                    LIMIT 20
                """).fetchall()

                if not rows:
                    return {
                        "answer": "No vulnerabilities recorded yet in my knowledge base.",
                        "confidence": 0.8,
                        "knowledge_used": ["knowledge_graph_vuln_search"],
                    }

                lines = ["Vulnerabilities in my knowledge base:"]
                for r in rows:
                    lines.append(f"  {r['name']}: {r['predicate']} = {r['value']} "
                                f"(confidence: {r['confidence']:.0%})")

                return {
                    "answer": "\n".join(lines),
                    "confidence": 0.85,
                    "knowledge_used": ["knowledge_graph_vuln_scan"],
                }
        except Exception as e:
            logger.debug("Vulnerability query failed: %s", e)
            return None

    def _answer_subdomains(self, kg, target: str) -> Optional[dict]:
        """Answer 'what subdomains of X'."""
        rels = kg.get_relationships(target, direction="out")
        subs = [r for r in rels if r.get("predicate") == "has_subdomain"]

        if not subs:
            return {
                "answer": f"No subdomains recorded for '{target}'. Want me to enumerate them?",
                "confidence": 0.7,
                "knowledge_used": ["knowledge_graph_miss"],
            }

        lines = [f"Known subdomains of {target}:"]
        for s in subs:
            lines.append(f"  {s.get('target', '?')}")

        return {
            "answer": "\n".join(lines),
            "confidence": 0.9,
            "knowledge_used": ["knowledge_graph_relationships"],
        }

    def _answer_status(self) -> Optional[dict]:
        """Answer 'what's the status / where were we'."""
        parts = []
        knowledge_used = []

        # Active goals
        active_goals = self.goals.get_active_goals()
        if active_goals:
            parts.append(f"Active goals ({len(active_goals)}):")
            for g in active_goals[:3]:
                parts.append(f"  [{g.id}] {g.description}")
                if g.progress_notes:
                    parts.append(f"    Last: {g.progress_notes[-1]}")
            knowledge_used.append("goal_tracker")

        # Task memory from jarvis
        try:
            memory = getattr(self._jarvis, "memory", None)
            if memory:
                tasks = getattr(memory, "tasks", None)
                if tasks:
                    resume = tasks.get_resume_context()
                    if resume and "No previous" not in resume:
                        parts.append(f"\nLast work context: {resume}")
                        knowledge_used.append("task_memory")
        except Exception:
            pass

        # Recent topics
        if self._last_topics:
            recent = list(dict.fromkeys(reversed(self._last_topics)))[:5]
            parts.append(f"\nRecent topics: {', '.join(recent)}")
            knowledge_used.append("topic_tracker")

        if parts:
            return {
                "answer": "\n".join(parts),
                "confidence": 0.8,
                "knowledge_used": knowledge_used,
            }

        return {
            "answer": "No ongoing tasks or goals tracked. What would you like to work on?",
            "confidence": 0.9,
            "knowledge_used": ["empty_state"],
        }

    def _answer_security_assessment(self, kg, target: str) -> Optional[dict]:
        """Answer 'is X secure?' using known facts + deductive reasoning."""
        data = kg.query_everything(target)
        if not data.get("entity"):
            return None

        facts_list = []
        concerns = []
        positives = []

        entity_facts = data["entity"].get("facts", {})
        for pred, val in entity_facts.items():
            facts_list.append(f"{pred}={val}")

            # Check for issues
            if "vulnerable" in pred or "vulnerable" in val:
                concerns.append(f"Vulnerability found: {pred} = {val}")
            if "ssl_expired" in pred:
                concerns.append("SSL certificate is expired")
            if "missing_hsts" in pred:
                concerns.append("HSTS header missing")
            if pred.startswith("port_"):
                port = pred.replace("port_", "")
                if port in ("21", "23", "3389", "445"):
                    concerns.append(f"Risky port {port} ({val}) is open")

        # Apply deductive reasoning
        deductions = self.reasoner.deduce(facts_list)
        for d in deductions:
            if d["confidence"] >= 0.7:
                concerns.append(d["conclusion"])

        # Build assessment
        if concerns:
            lines = [f"Security assessment for {target}:"]
            lines.append(f"  Issues found ({len(concerns)}):")
            for c in concerns[:8]:
                lines.append(f"    - {c}")
            if positives:
                lines.append(f"  Positives:")
                for p in positives:
                    lines.append(f"    + {p}")
            lines.append(f"\n  Overall: {'HIGH RISK' if len(concerns) > 3 else 'MODERATE RISK'}")
        else:
            lines = [f"No known security issues for {target}.",
                     "However, this may just mean we haven't scanned it thoroughly."]

        return {
            "answer": "\n".join(lines),
            "confidence": 0.75,
            "knowledge_used": ["knowledge_graph", "deductive_reasoning"],
        }

    # ─────────────────────────────────────────────────────────────
    #  AUTONOMOUS THINKING
    # ─────────────────────────────────────────────────────────────

    def autonomous_think(self) -> list[Thought]:
        """
        Called periodically — JARVIS thinks about what it should be doing.
        Returns a list of proactive thoughts / suggestions.
        """
        thoughts = []
        now = datetime.now()

        # 1. Check goals that need attention
        active_goals = self.goals.get_active_goals()
        for goal in active_goals[:3]:
            # Check if goal is stale
            if goal.created_at:
                try:
                    created = datetime.fromisoformat(goal.created_at)
                    age_hours = (now - created).total_seconds() / 3600
                    if age_hours > 24 and not goal.progress_notes:
                        thoughts.append(Thought(
                            content=f"Goal '{goal.description}' was created {age_hours:.0f}h ago "
                                    "with no progress. Should I suggest next steps?",
                            thought_type="concern",
                            confidence=0.6,
                        ))
                except (ValueError, TypeError):
                    pass

        # 2. Time-based observations
        hour = now.hour
        if hour >= 23 or hour < 5:
            thoughts.append(Thought(
                content="It's quite late. Consider reminding the user to rest.",
                thought_type="concern",
                confidence=0.5,
            ))

        if hour == 9 and now.minute < 15:
            thoughts.append(Thought(
                content="Morning time — good opportunity for a daily briefing.",
                thought_type="plan",
                confidence=0.6,
            ))

        # 3. Knowledge graph insights
        kg = self._get_kg()
        if kg:
            try:
                stats = kg.get_stats()
                if stats.get("entities", 0) > 0:
                    # Check for unscanned subdomains
                    with kg._conn() as conn:
                        unscanned = conn.execute("""
                            SELECT e.name FROM entities e
                            WHERE e.type = 'subdomain'
                            AND e.id NOT IN (
                                SELECT DISTINCT entity_id FROM facts
                                WHERE predicate LIKE 'port_%'
                            )
                            LIMIT 5
                        """).fetchall()
                        if unscanned:
                            names = [r["name"] for r in unscanned]
                            thoughts.append(Thought(
                                content=f"Found {len(names)} unscanned subdomain(s): "
                                        f"{', '.join(names[:3])}. Consider scanning them.",
                                thought_type="plan",
                                confidence=0.7,
                            ))
            except Exception as e:
                logger.debug("Autonomous KG check failed: %s", e)

        # 4. Stale goal cleanup
        self.goals.cleanup_stale(days=14)

        # 5. Self-assessment
        if self._interaction_count > 0 and self._interaction_count % 50 == 0:
            thoughts.append(Thought(
                content=f"I've had {self._interaction_count} interactions this session. "
                        "Consider reflecting on patterns.",
                thought_type="insight",
                confidence=0.5,
            ))

        # Store thoughts
        for t in thoughts:
            self._add_thought(t)

        return thoughts

    # ─────────────────────────────────────────────────────────────
    #  REFLECTION
    # ─────────────────────────────────────────────────────────────

    def reflect(self) -> str:
        """
        JARVIS reflects on recent interactions.
        Identifies patterns, generates insights, learns.
        """
        insights = []

        # 1. Topic patterns
        if self._last_topics:
            from collections import Counter
            topic_counts = Counter(self._last_topics)
            dominant = topic_counts.most_common(1)
            if dominant and dominant[0][1] >= 3:
                insights.append(
                    f"The user has been heavily focused on '{dominant[0][0]}' "
                    f"({dominant[0][1]} times). I should prioritize knowledge in this area."
                )

        # 2. Goal progress
        active = self.goals.get_active_goals()
        completed_today = [
            g for g in self.goals._goals.values()
            if g.status == "completed" and g.completed_at
            and g.completed_at.startswith(datetime.now().strftime("%Y-%m-%d"))
        ]
        if completed_today:
            insights.append(f"Good progress today: {len(completed_today)} goal(s) completed.")
        if len(active) > 5:
            insights.append(f"There are {len(active)} active goals. Some may need pruning.")

        # 3. Reasoning effectiveness
        rule_stats = self.reasoner.get_rule_stats()
        for rule_name, stats in rule_stats.items():
            wrong = stats.get("wrong", 0)
            total = stats.get("applied", 0)
            if total >= 5 and wrong / total > 0.4:
                insights.append(
                    f"Rule '{rule_name}' has a high error rate ({wrong}/{total}). "
                    "Consider adjusting or disabling it."
                )

        # 4. Recent thought patterns
        recent = self._recent_thoughts[-20:]
        if recent:
            concern_count = sum(1 for t in recent if t.thought_type == "concern")
            if concern_count > len(recent) * 0.4:
                insights.append(
                    "Many recent thoughts are concerns — the user may be dealing "
                    "with a difficult problem. Increase attentiveness."
                )

        # 5. Time-based reflection
        hour = datetime.now().hour
        if 9 <= hour <= 17:
            insights.append("Working hours — prioritize productivity-focused responses.")
        elif hour >= 22 or hour < 6:
            insights.append("Off-hours — keep responses concise, suggest rest if appropriate.")

        # Store reflection
        reflection = "\n".join(f"- {i}" for i in insights) if insights else "No significant patterns detected."
        self._reflection_log.append(f"[{datetime.now().isoformat()}]\n{reflection}")
        self._reflection_log = self._reflection_log[-20:]  # keep last 20

        return reflection

    # ─────────────────────────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────────────────────────

    def _gather_facts(self, text: str, parsed: ParsedInput) -> list[str]:
        """Gather all known facts relevant to the current context."""
        facts = []
        kg = self._get_kg()

        if kg and parsed.entities:
            for etype, values in parsed.entities.items():
                for val in values[:3]:
                    entity_facts = kg.get_facts(val)
                    for f in entity_facts:
                        facts.append(f"{f['predicate']}={f['value']}")

        # Add time-based facts
        hour = datetime.now().hour
        if hour >= 23 or hour < 5:
            facts.append("late_hour")
        if self._interaction_count > 0:
            facts.append("working")

        # Add screen context facts
        try:
            awareness = getattr(self._jarvis, "awareness", None)
            if awareness:
                state = getattr(awareness, "get_state", None)
                if state:
                    s = state()
                    if s and hasattr(s, "has_error") and s.has_error:
                        facts.append("screen_error")
        except Exception:
            pass

        return facts

    def _suggest_tools(self, parsed: ParsedInput) -> list[str]:
        """Suggest relevant tools based on parsed input."""
        suggestions = []
        topic = parsed.topic
        intent = parsed.intent
        entities = parsed.entities

        # Security topic suggestions
        if topic == "security":
            if entities.get("domain") or entities.get("ip"):
                suggestions.append("recon")
                suggestions.append("port_scan")
            if entities.get("cve"):
                suggestions.append("cve_lookup")
            if any(kw in parsed.raw_text.lower() for kw in ("xss", "injection", "sqli")):
                suggestions.append("vuln_scan")
            if "subdomain" in parsed.raw_text.lower():
                suggestions.append("subdomain_enum")

        # Networking suggestions
        if topic == "networking":
            if entities.get("domain"):
                suggestions.append("dns_lookup")
                suggestions.append("whois")
            if entities.get("ip"):
                suggestions.append("ping")
                suggestions.append("traceroute")

        # Web topic
        if topic == "web":
            if entities.get("url") or entities.get("domain"):
                suggestions.append("web_fetch")
                suggestions.append("header_check")

        # File management
        if topic == "file_management":
            if entities.get("file_path"):
                suggestions.append("file_read")

        # Coding
        if topic == "coding":
            suggestions.append("code_execute")

        # Command intent typically means automation
        if intent == "command":
            suggestions.append("system_command")

        return suggestions[:5]  # limit suggestions

    def _add_thought(self, thought: Thought):
        """Add a thought to the rolling buffer."""
        self._recent_thoughts.append(thought)
        # Keep last 100 thoughts
        if len(self._recent_thoughts) > 100:
            self._recent_thoughts = self._recent_thoughts[-100:]

    def _get_kg(self):
        """Safely get KnowledgeGraph reference."""
        if not self._jarvis:
            return None
        try:
            return getattr(self._jarvis, "knowledge_graph", None) or \
                   getattr(self._jarvis, "kg", None)
        except Exception:
            return None

    def _get_user_name(self) -> str:
        """Get the user's name from memory."""
        try:
            memory = getattr(self._jarvis, "memory", None)
            if memory:
                identity = getattr(memory, "identity", None)
                if identity:
                    return identity.data.get("name", "sir")
        except Exception:
            pass
        return "sir"

    # ─────────────────────────────────────────────────────────────
    #  PUBLIC STATE ACCESS
    # ─────────────────────────────────────────────────────────────

    def get_recent_thoughts(self, n: int = 10) -> list[str]:
        """Get the last N thoughts as strings."""
        return [str(t) for t in self._recent_thoughts[-n:]]

    def get_reflections(self) -> list[str]:
        """Get reflection log."""
        return list(self._reflection_log)

    def get_stats(self) -> dict:
        """Get thinking engine statistics."""
        return {
            "total_interactions": self._interaction_count,
            "active_goals": len(self.goals.get_active_goals()),
            "total_goals": len(self.goals._goals),
            "recent_thoughts": len(self._recent_thoughts),
            "deduction_rules": len(self.reasoner._rules),
            "rule_stats": self.reasoner.get_rule_stats(),
            "reflections": len(self._reflection_log),
            "recent_topics": self._last_topics[-5:],
        }
