"""
J.A.R.V.I.S — Task Orchestrator
Intelligent task classification, routing, and execution pipeline.

Replaces the simple agent.process_message() flow with:
  1. Classify incoming request (no AI needed)
  2. Route to optimal pipeline (local, tool, AI, multi-step)
  3. Execute with priority queuing and parallel support
  4. Post-process: update cache, track success rates, adaptive routing

The orchestrator learns over time which pipelines work best for which
query types, and routes accordingly.
"""

import re
import time
import json
import hashlib
import threading
import logging
from enum import Enum, IntEnum
from queue import PriorityQueue
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from core.schemas import AgentPlan, ToolResult
from core.task_session import TaskSessionManager
from core.tool_schemas import get_schema_for_tool

# Optional import — cognitive core may not exist yet
try:
    from core.cognitive import CognitiveCore
except ImportError:
    CognitiveCore = None

logger = logging.getLogger("jarvis.orchestrator")


# ═══════════════════════════════════════════════════════════════════
#  Enums
# ═══════════════════════════════════════════════════════════════════

class TaskType(Enum):
    """Classification of an incoming user request."""
    SIMPLE         = "simple"          # greetings, time, date, basic facts
    CACHED         = "cached"          # answered before — serve from cache
    TOOL           = "tool"            # needs a specific tool (open app, weather…)
    REASONING      = "reasoning"       # needs AI thinking (analysis, creative, code)
    MULTI_STEP     = "multi_step"      # complex — decompose and execute sequentially
    RESEARCH       = "research"        # web search + synthesis
    CONVERSATIONAL = "conversational"  # follow-up to previous message


class Priority(IntEnum):
    """Task priority — lower number = higher priority."""
    URGENT = 0   # alarms, security alerts, errors
    HIGH   = 1   # user-initiated commands, questions
    MEDIUM = 2   # background tasks, reminders checking
    LOW    = 3   # learning, knowledge extraction, cache updates


# ═══════════════════════════════════════════════════════════════════
#  Data classes
# ═══════════════════════════════════════════════════════════════════

@dataclass(order=True)
class Task:
    """A unit of work in the priority queue."""
    priority: int
    text: str              = field(compare=False)
    task_type: TaskType    = field(compare=False, default=TaskType.SIMPLE)
    created_at: float      = field(compare=False, default_factory=time.time)
    on_reply: Any          = field(compare=False, default=None, repr=False)
    on_error: Any          = field(compare=False, default=None, repr=False)
    metadata: dict         = field(compare=False, default_factory=dict)


@dataclass
class PipelineResult:
    """Result from a pipeline execution."""
    success: bool
    reply: str
    latency_ms: float = 0.0
    task_type: TaskType = TaskType.SIMPLE
    pipeline: str = "unknown"


# ═══════════════════════════════════════════════════════════════════
#  Classification patterns
# ═══════════════════════════════════════════════════════════════════

# ── Negation / cancellation patterns ────────────────────────
_NEGATION_RE = re.compile(
    r"^(?:don'?t|do not|stop|cancel|never mind|nevermind|abort|"
    r"forget it|skip|ignore)\b|^(?:no|nah|nope)(?:[\s.!?,]*$|(?:\s+(?:thanks|thank you))?$)",
    re.IGNORECASE,
)

_DIRECT_CONTROL_RE = re.compile(
    r"\b(?:use|control|take|have|got)\b.*\b(?:mouse|keyboard)\b|"
    r"\b(?:mouse|keyboard)\b.*\b(?:use|control|access)\b|"
    r"\bi\s+give\s+you\s+permission\b|"
    r"\bdirect\s+(?:control|desktop\s+control)\b",
    re.IGNORECASE,
)

_DIRECT_CONTROL_RETRY_RE = re.compile(
    r"\b(?:try(?:\s+again|\s+now|\s+it)?|retry|go\s+ahead|do\s+it|"
    r"send\s+it|send\s+that|now\s+try|yes)\b",
    re.IGNORECASE,
)

_RETRY_CONFIRM_RE = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|sure|please|go\s+ahead|"
    r"do\s+it|continue|again|retry|try\s+(?:again|now|it)|"
    r"yes\s+try(?:\s+(?:again|now))?)\b",
    re.IGNORECASE,
)

_SECURITY_CHECK_RE = re.compile(
    r"\b(?:system\s+safe|safe\s+or\s+not|security\s+check|"
    r"check\s+(?:if\s+)?(?:my\s+)?system\b.*\bsafe|"
    r"scan\s+(?:if\s+)?(?:my\s+)?system\b.*\bsafe)\b",
    re.IGNORECASE,
)

_SEND_INTENT_RE = re.compile(
    r"\b(?:send|text|texting|message|messaging|msg|dm|tell)\b",
    re.IGNORECASE,
)

_DIRECT_CONTROL_TRAILER_RE = re.compile(
    r"(?:\s+(?:through|using|with)\s+(?:my\s+)?)"
    r"(?:keyboard(?:\s+and\s+(?:mouse|mouose))?|(?:mouse|mouose)(?:\s+and\s+keyboard)?)\b.*$",
    re.IGNORECASE,
)

# Greetings / simple
_GREETINGS = {
    "hi", "hello", "hey", "yo", "sup", "hi jarvis", "hey jarvis",
    "hello jarvis", "good morning", "good evening", "good afternoon",
    "good night", "thanks", "thank you", "bye", "goodbye", "see you",
}

_TIME_DATE_RE = re.compile(
    r"\b(?:what(?:'s| is)(?: the)? (?:time|date|day))|"
    r"\b(?:current (?:time|date))|"
    r"\b(?:today(?:'s)? date)\b",
    re.IGNORECASE,
)

_BASIC_FACTS_RE = re.compile(
    r"^(?:who (?:are you|made you|built you|created you))|"
    r"^(?:what(?:'s| is) your name)|"
    r"^(?:what can you do)",
    re.IGNORECASE,
)

# Tool triggers — maps regex to tool name
# ORDER MATTERS: more specific patterns MUST come before generic ones.
# "open trailer of spider-man in youtube" = web_search, NOT open_app.
_TOOL_PATTERNS = [
    # ── Platform-specific searches (BEFORE open_app) ──
    # "open X in/on youtube" / "play X on youtube" / "search X on youtube"
    (re.compile(r"\b(?:open|play|watch|find|search)\s+.+\b(?:in|on)\s+(?:youtube|spotify|google|github|reddit)\b", re.I), "web_search"),
    (re.compile(r"\b(?:youtube|spotify)\s+.+", re.I), "web_search"),
    (re.compile(r"\b(?:trailer|video|song|music|clip)\s+.+\b(?:in|on)\s+\w+", re.I), "web_search"),
    # ── App launching (only for actual app names, not search queries) ──
    # Negative lookahead: don't match if "in/on youtube/google/spotify" follows
    (re.compile(r"\b(?:open|launch|start|run)\s+(?!.*\b(?:in|on)\s+(?:youtube|spotify|google|github|reddit)\b)(\w[\w\s]*)", re.I), "open_app"),
    (re.compile(r"\bweather\b", re.I), "get_weather"),
    (re.compile(r"\b(?:news|headlines)\b", re.I), "get_news"),
    (re.compile(r"\b(?:crypto|bitcoin|btc|eth(?:ereum)?)\b", re.I), "get_crypto"),
    (re.compile(r"\bwiki(?:pedia)?\s+(.+)", re.I), "get_wiki"),
    (re.compile(r"\bdefine\s+(.+)", re.I), "get_definition"),
    (re.compile(r"\btranslat(?:e|ion)\b", re.I), "get_translation"),
    (re.compile(r"\b(?:convert|currency)\b.*\b(?:usd|eur|inr|gbp)\b", re.I), "get_currency"),
    (re.compile(r"\b(?:inspirational\s+)?quote\b", re.I), "get_quote"),
    (re.compile(r"\bjoke\b", re.I), "get_joke"),
    (re.compile(r"\bfact\b", re.I), "get_fact"),
    (re.compile(r"\bnasa\b", re.I), "get_nasa"),
    (re.compile(r"\b(?:system|pc|computer)\s*(?:info|status|stats|health)\b", re.I), "system_info"),
    (re.compile(r"\bscan\s*(?:the\s+)?screen\b", re.I), "scan_screen"),
    (re.compile(r"\block\s*(?:the\s+)?(?:screen|computer|pc)\b", re.I), "lock_screen"),
    (re.compile(r"\bvolume\b", re.I), "set_volume"),
    (re.compile(r"\b(?:remind(?:er)?|alarm)\b", re.I), "set_reminder"),
    (re.compile(r"\btimer\b", re.I), "set_timer"),
    (re.compile(r"\b(?:search|google|look\s*up)\s+(?:for\s+)?(?!bar\b|box\b|field\b|input\b)\w+", re.I), "web_search"),
    # Cybersecurity
    (re.compile(r"\b(?:url|link)\s*scan\b", re.I), "url_scan"),
    (re.compile(r"\bfile\s*scan\b", re.I), "file_scan"),
    (re.compile(r"\bsecurity\s*audit\b", re.I), "security_audit"),
    (_SECURITY_CHECK_RE, "security_audit"),
    (re.compile(r"\bphishing\b", re.I), "phishing_detect"),
    (re.compile(r"\bport\s*scan\b", re.I), "port_scan"),
    (re.compile(r"\bwifi\s*scan\b", re.I), "wifi_scan"),
    (re.compile(r"\bnet(?:work)?\s*scan\b", re.I), "net_scan"),
    # Email
    (re.compile(r"\b(?:check|read)\s*(?:my\s+)?(?:inbox|email|mail)\b", re.I), "check_inbox"),
    (re.compile(r"\bsend\s*(?:an?\s+)?(?:email|mail)\b", re.I), "send_email"),
    # Smart home (specific patterns to avoid false matches with security commands)
    (re.compile(r"\b(?:turn\s+(?:on|off)\s+)?lights?\b", re.I), "control_lights"),
    (re.compile(r"\bthermostat\b", re.I), "set_thermostat"),
    (re.compile(r"\b(?:home\s+)?scene\b", re.I), "activate_scene"),
    (re.compile(r"\b(?:smart\s+(?:home\s+)?|home\s+|iot\s+)devices?\b", re.I), "list_devices"),
    # Web automation
    (re.compile(r"\b(?:log\s*in|login|sign\s*in)\s*(?:to|into)\b", re.I), "web_login"),
    # Pentest / Bug bounty
    (re.compile(r"\b(?:full\s+)?recon\b", re.I), "recon"),
    (re.compile(r"\bsubdomain", re.I), "subdomain_enum"),
    (re.compile(r"\btech\s*(?:stack|detect)", re.I), "tech_detect"),
    (re.compile(r"\b(?:dir(?:ectory)?\s*(?:fuzz|brute|bust)|fuzz\s*dir)", re.I), "dir_fuzz"),
    (re.compile(r"\bdork", re.I), "google_dorks"),
    (re.compile(r"\bssl\b|\btls\b|\bcert(?:ificate)?\s*(?:check|scan|anal)", re.I), "ssl_check"),
    (re.compile(r"\bcors\b", re.I), "cors_check"),
    (re.compile(r"\bxss\b", re.I), "xss_test"),
    (re.compile(r"\bsql\s*i(?:njection)?\b", re.I), "sqli_test"),
    (re.compile(r"\bopen\s*redirect", re.I), "open_redirect"),
    (re.compile(r"\bheader\s*audit\b", re.I), "header_audit"),
    (re.compile(r"\bwayback\b", re.I), "wayback"),
    (re.compile(r"\bcve\b", re.I), "cve_search"),
    (re.compile(r"\bexploit\b", re.I), "exploit_search"),
    # Chain execution
    (re.compile(r"\b(?:full\s+)?pentest\s+chain\b", re.I), "pentest_chain"),
    (re.compile(r"\bquick\s+recon\s+chain\b", re.I), "quick_recon_chain"),
    # Web research
    (re.compile(r"\b(?:research|look\s*up|find\s+(?:out|info))\s+(?:about\s+)?(.+)", re.I), "web_research"),
    (re.compile(r"\bresearch\s+(?:cve|CVE)[- ]?\d{4}", re.I), "research_cve"),
    # Messaging — MUST be before type_text (so "text meet on whatsapp" doesn't become type_text)
    # Require platform mention OR "text/dm/msg <name>" pattern with clear messaging intent
    (re.compile(r"\b(?:send|text|msg|dm)\s+\w+\s+(?:on|via|through)\s+(?:whatsapp|telegram|instagram|discord)\b", re.I), "send_msg"),
    (re.compile(r"\b(?:whatsapp|telegram|instagram|discord)\s+\w+\s+.+", re.I), "send_msg"),
    (re.compile(r"\bsend\s+(?:a\s+)?(?:message|text|msg)\s+(?:to\s+)?\w+", re.I), "send_msg"),
    (re.compile(r"\b(?:text|dm|msg)\s+\w+\s+(?:that|saying|say)\b", re.I), "send_msg"),
    (re.compile(r"\b(?:text|dm|msg)\s+\w+\s+(?:on|via)\s+\w+\s+.+", re.I), "send_msg"),
    # More natural: "tell Meet I'm coming" / "message Meet on WhatsApp"
    (re.compile(r"\btell\s+\w+\s+(?:that\s+|i'?m\s+|to\s+|on\s+(?:whatsapp|telegram))", re.I), "send_msg"),
    (re.compile(r"\b(?:send|text)\s+(?:a\s+)?(?:whatsapp|telegram)\s+(?:to\s+)?\w+", re.I), "send_msg"),
    (re.compile(r"\bsend\s+(?:a\s+)?(?:whatsapp|telegram)\b", re.I), "send_msg"),
    (re.compile(r"\b(?:can\s+you\s+)?(?:send|text|message)\s+\w+\s+(?:saying|that)\b", re.I), "send_msg"),
    # Mouse & keyboard
    (re.compile(r"\bclick\s+(?:on\s+)?(?:the\s+)?(.+)", re.I), "mouse_click"),
    (re.compile(r"\bscroll\s+(?:down|up)", re.I), "mouse_scroll"),
    (re.compile(r"\btype\s+(?:in\s+|out\s+)?['\"]?(.+?)['\"]?\s*$", re.I), "type_text"),
    (re.compile(r"\bpress\s+(?:the\s+)?(.+)", re.I), "key_press"),
    (re.compile(r"\bscreenshot\b|\btake\s+(?:a\s+)?(?:screen\s*shot|snap)", re.I), "take_screenshot"),
    # AI screen interaction (vision-based)
    (re.compile(r"\bfind\s+(?:the\s+)?(?:button|element|field|icon|link|text|input|menu)\b", re.I), "screen_find"),
    (re.compile(r"\bclick\s+(?:on\s+)?(?:the\s+)?(?:button|element|link|icon|menu)\b", re.I), "screen_click"),
    (re.compile(r"\btype\s+(?:into|in)\s+(?:the\s+)?(?:field|input|box|search)\b", re.I), "screen_type"),
    (re.compile(r"\bread\s+(?:the\s+)?(?:screen|text|content|page)\b", re.I), "screen_read"),
    # Dev agent (build project)
    (re.compile(r"\b(?:build|create|make|generate)\s+(?:a\s+|me\s+(?:a\s+)?)?(?:project|app|application|program|tool|script|website|game)\b", re.I), "build_project"),
]

# Research triggers
_RESEARCH_RE = re.compile(
    r"\b(?:research|find out|look into|investigate|compare|analyze)\b",
    re.IGNORECASE,
)

# Reasoning triggers — needs AI thinking
_REASONING_RE = re.compile(
    r"\b(?:explain|why|how does|write|create|generate|code|summarize|"
    r"analyze|compose|draft|help me|suggest|recommend|think|plan|"
    r"review|debug|refactor|design|brainstorm|describe)\b",
    re.IGNORECASE,
)

# Multi-step detection — "and" between unrelated topics
_MULTI_STEP_RE = re.compile(
    r"(.+?)\s+(?:and\s+(?:also\s+)?|then\s+|also\s+|plus\s+)(.+)",
    re.IGNORECASE,
)

# Conversational follow-up cues
_FOLLOWUP_PATTERNS = re.compile(
    r"^(?:what about|how about|and |also |why(?:\?)?$|"
    r"can you (?:also|explain)|tell me more|go on|continue|"
    r"what else|yes|no|ok(?:ay)?|sure|exactly|right)",
    re.IGNORECASE,
)

_SEND_STATUS_RE = re.compile(
    r"\b(?:did\s+(?:you|it)\s+(?:send|sent)|was\s+it\s+sent|"
    r"did\s+that\s+send|did\s+the\s+message\s+send|is\s+it\s+sent)\b",
    re.IGNORECASE,
)

_ACTION_CORRECTION_RE = re.compile(
    r"\b(?:not\s+(?:in|on|there)|wrong\s+(?:place|chat|box|field)|"
    r"(?:in|on)\s+(?:the\s+)?(?:search|chat|text)\s*(?:bar|box|field)|"
    r"instead|i\s+(?:meant|said)|no\s+(?:in|on)|"
    r"you\s+(?:didn'?t|have\s+not|haven'?t)|"
    r"didn'?t\s+(?:send|type|click|do|work|open|write)|"
    r"that'?s\s+not\s+what|not\s+what\s+i|"
    r"why\s+(?:are\s+you\s+not|aren'?t\s+you|can'?t\s+you|didn'?t\s+you)|"
    r"you\s+(?:just|only)\s+(?:searched|opened|clicked)|"
    r"after\s+opening|"
    r"(?:not|nnot)\s+(?:writing|typing|sending)\b|"
    r"searched\s+(?:the\s+)?person|"
    r"but\s+(?:you|it)\s+didn'?t|"
    r"try\s+again|do\s+it\s+(?:again|properly)|"
    r"that\s+didn'?t\s+work|it\s+(?:didn'?t|doesn'?t)\s+work)\b",
    re.I,
)

# Urgency keywords
_URGENT_RE = re.compile(
    r"\b(?:alarm|emergency|urgent|security\s*alert|error|critical|"
    r"danger|warning|immediately|asap|now)\b",
    re.IGNORECASE,
)


# ═══════════════════════════════════════════════════════════════════
#  Task Orchestrator
# ═══════════════════════════════════════════════════════════════════

class TaskOrchestrator:
    """
    Intelligent task classifier, router, and executor for JARVIS.

    Replaces the simple process_message() with a multi-pipeline system
    that classifies requests, queues by priority, routes to the optimal
    pipeline, executes (with parallelism where possible), and learns
    from outcomes.
    """

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.brain  = jarvis.brain
        self.memory = jarvis.memory

        # Executor from the existing agent (reuse tool registry)
        from core.executor import Executor
        self.executor = Executor(jarvis)

        # Short-term memory for conversational context
        from core.memory import ShortTermMemory
        self.short_term = ShortTermMemory()

        # Priority queue for task scheduling
        self._queue: PriorityQueue = PriorityQueue()
        self._queue_lock = threading.Lock()

        # Thread pool for parallel subtask execution
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jarvis-orch")

        # ── Cognitive cache ──────────────────────────────────────
        # query_hash -> {"reply": str, "hits": int, "last_used": float}
        self._cache: dict[str, dict] = {}
        self._cache_lock = threading.Lock()
        self.CACHE_MAX = 200

        # ── Last action tracking (for follow-up corrections) ────
        self._last_action = {}  # {"tool": str, "args": dict, "reply": str, "time": float}
        # Pending tool state lets JARVIS hold onto missing slots across follow-ups.
        self._pending_tool = {}  # {"tool": str, "args": dict, "missing": list[str], "time": float}
        self.task_sessions = TaskSessionManager(jarvis)

        # ── Adaptive routing state ───────────────────────────────
        # task_type -> {pipeline_name -> {"successes": int, "failures": int, "total_latency": float}}
        self._routing_stats: dict[str, dict[str, dict]] = {}
        self._routing_lock = threading.Lock()

        # ── Success tracking ─────────────────────────────────────
        # task_type -> {"success": int, "fail": int}
        self._task_stats: dict[str, dict[str, int]] = {}

        # Background worker for the priority queue
        self._worker_running = False
        self._worker_thread: Optional[threading.Thread] = None

    # ═════════════════════════════════════════════════════════════
    #  1. Classification
    # ═════════════════════════════════════════════════════════════

    def classify(self, text: str, context: Optional[list] = None) -> TaskType:
        """
        Classify a user request into a TaskType using keyword patterns,
        regex, and conversational context.  No AI call needed.

        Args:
            text:    The raw user message.
            context: Recent conversation turns (list of dicts) for
                     detecting follow-ups.

        Returns:
            TaskType enum value.
        """
        msg = text.strip()
        msg_lower = msg.lower().strip()
        has_tool_intent = any(pattern.search(msg_lower) for pattern, _tool_name in _TOOL_PATTERNS)
        capability_match = self._resolve_capability_match(msg)

        if self.task_sessions.get_waiting_session():
            return TaskType.TOOL
        if self._looks_like_recent_action_correction(msg_lower):
            return TaskType.TOOL
        if self._looks_like_single_send_request(msg_lower):
            return TaskType.TOOL
        if capability_match:
            return TaskType.TOOL

        # ── Negation / cancellation — always treat as conversational ─
        if _NEGATION_RE.search(msg_lower) and not has_tool_intent:
            return TaskType.CONVERSATIONAL

        # ── Check cache first ────────────────────────────────────
        cache_key = self._cache_key(msg_lower)
        with self._cache_lock:
            if cache_key in self._cache:
                return TaskType.CACHED

        # ── Simple: greetings, time, date, identity ──────────────
        if msg_lower in _GREETINGS:
            return TaskType.SIMPLE
        if _TIME_DATE_RE.search(msg_lower):
            return TaskType.SIMPLE
        if _BASIC_FACTS_RE.search(msg_lower):
            return TaskType.SIMPLE
        if _DIRECT_CONTROL_RE.search(msg_lower) and not has_tool_intent and not capability_match:
            return TaskType.SIMPLE
        if self._is_recent_send_status_query(msg_lower):
            return TaskType.SIMPLE

        # ── Conversational follow-up ─────────────────────────────
        if context and len(context) >= 1:
            if _FOLLOWUP_PATTERNS.search(msg_lower) and not has_tool_intent:
                return TaskType.CONVERSATIONAL

        # ── Multi-step detection ─────────────────────────────────
        multi = _MULTI_STEP_RE.match(msg)
        if multi:
            part_a = multi.group(1).strip()
            part_b = multi.group(2).strip()
            # Only multi-step if both parts look like distinct tasks
            type_a = self._classify_single(part_a)
            type_b = self._classify_single(part_b)
            if type_a != type_b or type_a == TaskType.TOOL:
                return TaskType.MULTI_STEP

        # ── Research ─────────────────────────────────────────────
        if _RESEARCH_RE.search(msg_lower):
            return TaskType.RESEARCH

        # ── Tool ─────────────────────────────────────────────────
        if _SECURITY_CHECK_RE.search(msg_lower):
            return TaskType.TOOL

        for pattern, _tool_name in _TOOL_PATTERNS:
            if pattern.search(msg_lower):
                return TaskType.TOOL

        # ── Reasoning ────────────────────────────────────────────
        if _REASONING_RE.search(msg_lower):
            return TaskType.REASONING

        # ── Default: if short, treat as conversational; otherwise reasoning
        if len(msg.split()) <= 3 and context:
            return TaskType.CONVERSATIONAL
        return TaskType.REASONING

    def should_bypass_fastpaths(self, text: str, context: Optional[list] = None) -> bool:
        """
        Return True when the request should skip UI fast paths and go
        directly into orchestrator routing/state handling.
        """
        msg_lower = (text or "").lower().strip()
        if not msg_lower:
            return False
        if self.task_sessions.get_waiting_session():
            return True
        if self._is_recent_send_status_query(msg_lower):
            return True
        if self._looks_like_recent_action_correction(msg_lower):
            return True
        if self._looks_like_single_send_request(msg_lower):
            return True
        if self._resolve_capability_match(text):
            return True
        if _DIRECT_CONTROL_RE.search(msg_lower):
            return True
        kind = self.classify(text, context=context)
        return kind in {TaskType.TOOL, TaskType.MULTI_STEP, TaskType.RESEARCH}

    def _resolve_capability_match(self, text: str):
        capabilities = getattr(self.jarvis, "capabilities", None)
        if not capabilities or not text:
            return None
        try:
            return capabilities.resolve_request(text)
        except Exception:
            return None

    def _looks_like_recent_action_correction(self, text: str) -> bool:
        if not text:
            return False
        last = self._last_action or {}
        if not last or time.time() - float(last.get("time", 0) or 0) > 180:
            return False
        return bool(_ACTION_CORRECTION_RE.search(text.lower().strip()))

    def _prefer_operator_execution(self, task: Task) -> bool:
        metadata = getattr(task, "metadata", {}) or {}
        if metadata.get("pending_tool") or metadata.get("planned_tool"):
            return True
        if self.task_sessions.get_waiting_session():
            return True
        text_lower = (task.text or "").lower().strip()
        if self._looks_like_single_send_request(text_lower):
            return True
        if self._looks_like_recent_action_correction(text_lower):
            return True
        if _DIRECT_CONTROL_RE.search(text_lower) and self._get_recent_send_args():
            return True
        return False

    def _looks_like_single_send_request(self, msg_lower: str) -> bool:
        """Detect a single messaging request that should stay on the send_msg path."""
        if not msg_lower or not _SEND_INTENT_RE.search(msg_lower):
            return False

        platforms = ("whatsapp", "telegram", "instagram", "discord")
        has_platform = any(p in msg_lower for p in platforms)
        has_contact_shape = bool(
            re.search(
                r"\b(?:send|text|texting|message|messaging|msg|dm|tell)\b.+\b(?:to\s+)?\w+",
                msg_lower,
                re.I,
            )
        )
        has_message_shape = bool(
            re.search(r"\b(?:that|saying|say|i'?m|i\s+am|i'?ll|i\s+will)\b", msg_lower, re.I)
        )

        return (has_platform and has_contact_shape) or (has_contact_shape and has_message_shape)

    def _classify_single(self, text: str) -> TaskType:
        """Lightweight classification for a single sub-phrase (no recursion)."""
        msg = text.lower().strip()
        if msg in _GREETINGS:
            return TaskType.SIMPLE
        for pattern, _ in _TOOL_PATTERNS:
            if pattern.search(msg):
                return TaskType.TOOL
        if _REASONING_RE.search(msg):
            return TaskType.REASONING
        return TaskType.REASONING

    # ═════════════════════════════════════════════════════════════
    #  2. Priority Queue
    # ═════════════════════════════════════════════════════════════

    def _determine_priority(self, text: str, task_type: TaskType) -> Priority:
        """Determine task priority based on content and type."""
        if _URGENT_RE.search(text):
            return Priority.URGENT
        if task_type in (TaskType.SIMPLE, TaskType.CACHED):
            return Priority.HIGH
        if task_type in (TaskType.TOOL, TaskType.REASONING, TaskType.CONVERSATIONAL):
            return Priority.HIGH
        if task_type == TaskType.MULTI_STEP:
            return Priority.HIGH
        if task_type == TaskType.RESEARCH:
            return Priority.MEDIUM
        return Priority.MEDIUM

    def enqueue(self, task: Task, priority: Optional[Priority] = None) -> None:
        """
        Add a task to the priority queue.

        Args:
            task:     The Task to enqueue.
            priority: Override priority (uses task.priority if None).
        """
        if priority is not None:
            task.priority = int(priority)
        with self._queue_lock:
            self._queue.put(task)
        logger.debug("Enqueued task: type=%s priority=%s text=%.40s",
                      task.task_type.value, task.priority, task.text)

    def dequeue(self) -> Optional[Task]:
        """
        Remove and return the highest-priority task.
        Returns None if queue is empty.
        """
        with self._queue_lock:
            if self._queue.empty():
                return None
            return self._queue.get_nowait()

    def start_worker(self) -> None:
        """Start the background queue worker thread."""
        if self._worker_running:
            return
        self._worker_running = True
        self._worker_thread = threading.Thread(
            target=self._queue_worker, daemon=True, name="jarvis-orch-worker",
        )
        self._worker_thread.start()

    def stop_worker(self) -> None:
        """Stop the background queue worker."""
        self._worker_running = False

    def _queue_worker(self) -> None:
        """Background thread that processes queued tasks."""
        while self._worker_running:
            task = self.dequeue()
            if task is None:
                time.sleep(0.1)
                continue
            try:
                self._execute_task(task)
            except Exception as e:
                logger.error("Queue worker error: %s", e)
                if task.on_error:
                    self._safe_callback(task.on_error, f"Orchestrator error: {e}")

    # ═════════════════════════════════════════════════════════════
    #  3. Execution Pipelines
    # ═════════════════════════════════════════════════════════════

    def execute(self, text: str, on_reply: Callable, on_error: Callable) -> None:
        """
        Main entry point.  Classifies the request, determines priority,
        and routes to the appropriate execution pipeline.

        Args:
            text:     User message.
            on_reply: callback(reply_text: str, latency_ms: float)
            on_error: callback(error_text: str)
        """
        context = self.short_term.get_recent()
        self.short_term.add_user(text)
        msg_lower = text.lower().strip()

        waiting_session = self.task_sessions.get_waiting_session()
        if waiting_session and _NEGATION_RE.search(msg_lower):
            cancelled = self.task_sessions.cancel_active("Cancelled by user.")
            task_brain = getattr(self.jarvis, "task_brain", None)
            if cancelled and task_brain:
                try:
                    task_brain.record_task_outcome(
                        goal=cancelled.goal,
                        tool_name=cancelled.tool_name,
                        args=cancelled.args,
                        status="cancelled",
                        result_text=cancelled.last_result,
                        attempts=cancelled.attempts,
                        step=cancelled.step,
                        session_id=cancelled.session_id,
                    )
                except Exception:
                    pass
            waiting_session = None
        self._sync_task_state_compat()

        if self._is_recent_send_status_query(msg_lower):
            pending_tool = {}
        elif waiting_session and waiting_session.is_waiting():
            pending_tool = waiting_session.to_pending_tool()
        else:
            pending_tool = self._get_recent_pending_tool()
        task_type = TaskType.TOOL if pending_tool else self.classify(text, context)
        priority  = self._determine_priority(text, task_type)

        task = Task(
            priority=int(priority),
            text=text,
            task_type=task_type,
            on_reply=on_reply,
            on_error=on_error,
        )
        if pending_tool:
            task.metadata["pending_tool"] = pending_tool
            task.metadata["task_session_id"] = pending_tool.get("session_id", "")

        logger.info("Classified: '%s' -> %s (priority=%s)",
                     text[:50], task_type.value, priority.name)

        # Execute immediately in a background thread (for responsiveness)
        threading.Thread(
            target=self._execute_task, args=(task,),
            daemon=True, name="jarvis-task",
        ).start()

    def _execute_task(self, task: Task) -> None:
        """Route a task to the optimal pipeline and execute it."""
        start = time.perf_counter()
        result: Optional[PipelineResult] = None

        try:
            # Check adaptive routing for a preferred pipeline
            optimal = self.get_optimal_route(task.text)

            if task.task_type == TaskType.CACHED:
                result = self._local_pipeline(task)

            elif task.task_type == TaskType.SIMPLE:
                result = self._local_pipeline(task)

            elif task.task_type == TaskType.TOOL:
                if optimal == "local_pipeline" and not self._prefer_operator_execution(task):
                    result = self._local_pipeline(task)
                if result is None or not result.success:
                    result = self._tool_pipeline(task)

            elif task.task_type == TaskType.REASONING:
                result = self._ai_pipeline(task)

            elif task.task_type == TaskType.MULTI_STEP:
                result = self._multi_pipeline(task)

            elif task.task_type == TaskType.RESEARCH:
                result = self._ai_pipeline(task)

            elif task.task_type == TaskType.CONVERSATIONAL:
                result = self._ai_pipeline(task)

            else:
                result = self._ai_pipeline(task)

        except Exception as e:
            logger.error("Pipeline error for '%s': %s", task.text[:40], e)

            # ── Resilient recovery — don't give up ──
            resilient = getattr(self.jarvis, "resilient", None)
            if resilient:
                logger.info("Engaging resilient executor for pipeline error")
                resilient.knowledge.record_error(
                    type(e).__name__, str(e)[:200], task.text[:200],
                )

            result = PipelineResult(
                success=False, reply=f"Ran into a snag, sir. {e}",
                pipeline="error",
            )

        # Calculate latency
        elapsed_ms = (time.perf_counter() - start) * 1000
        if result:
            result.latency_ms = elapsed_ms
            result.task_type = task.task_type

        # Post-process (cache, stats, feedback)
        success = result.success if result else False
        reply = result.reply if result else "I'm sorry, I couldn't process that."
        pipeline = result.pipeline if result else "unknown"

        self.post_process(
            task_type=task.task_type,
            query=task.text,
            result=reply,
            latency=elapsed_ms,
            success=success,
            pipeline=pipeline,
        )

        # Update conversation memory
        self.short_term.add_assistant(reply)
        if hasattr(self.brain, 'add_assistant_message'):
            self.brain.add_assistant_message(reply)
        if hasattr(self.brain, 'msg_count'):
            self.brain.msg_count += 1

        # Deliver reply to UI
        if task.on_reply:
            self._safe_callback(task.on_reply, reply, elapsed_ms)

    # ── Local Pipeline ───────────────────────────────────────────

    def _is_recent_send_status_query(self, text: str) -> bool:
        """Return True when the user is asking about the latest send-message action."""
        if not text:
            return False
        last = self._last_action or {}
        if last.get("tool") != "send_msg":
            return False
        if time.time() - float(last.get("time", 0) or 0) > 180:
            return False
        return bool(_SEND_STATUS_RE.search(text.lower().strip()))

    def _format_recent_send_status(self) -> str:
        """Summarize the latest send-message result without needing an AI provider."""
        last = self._last_action or {}
        args = last.get("args") or {}
        contact = str(args.get("contact", "")).strip()
        platform = str(args.get("platform", "")).strip()
        result = str(last.get("result", "") or "").strip()

        if result:
            return result

        if last.get("success"):
            if contact and platform:
                return f"The last message was sent to {contact} via {platform}."
            if contact:
                return f"The last message was sent to {contact}."
            return "The last message send completed successfully."

        if contact and platform:
            return f"The last attempt to message {contact} via {platform} did not complete."
        return "The last message send did not complete."

    def _get_recent_send_args(self) -> dict:
        """Return the latest send-message args if they are still safe to reuse."""
        recent = self._get_recent_retryable_action("send_msg")
        return dict(recent.get("args") or {}) if recent else {}

    def _is_retry_confirmation(self, msg_lower: str, *, allow_plain_yes: bool = False) -> bool:
        """Return True when a short follow-up should trigger a retry."""
        if not msg_lower:
            return False
        if _DIRECT_CONTROL_RETRY_RE.search(msg_lower):
            return True
        if allow_plain_yes and _RETRY_CONFIRM_RE.search(msg_lower):
            return True
        return False

    def _is_retryable_tool(self, tool_name: str) -> bool:
        """Conservatively decide whether a recent tool action is safe to retry locally."""
        tool_name = str(tool_name or "").strip()
        if not tool_name:
            return False
        if tool_name == "send_msg":
            return True
        if tool_name in {"open_app", "web_login", "web_navigate", "web_click"}:
            return True

        capabilities = getattr(self.jarvis, "capabilities", None)
        capability = capabilities.get_capability(tool_name) if capabilities else None
        if not capability:
            return False
        if capability.category not in {"communication", "desktop", "screen", "input"}:
            return False
        return capability.execution_mode in {"operator", "vision", "direct"}

    def _get_recent_retryable_action(
        self,
        tool_name: str | None = None,
        *,
        max_age: float = 300.0,
    ) -> dict:
        """Return the freshest fully-specified recent action suitable for a local retry."""
        recent = self.task_sessions.get_recent_action(max_age=max_age)
        if recent and (not tool_name or recent.tool_name == tool_name):
            if self._is_retryable_tool(recent.tool_name):
                required_args = self._required_args_for_tool(recent.tool_name)
                args = dict(recent.args or {})
                if not self._missing_required_args(recent.tool_name, args, required_args):
                    return {
                        "tool": recent.tool_name,
                        "args": args,
                        "goal": recent.goal,
                        "status": recent.status,
                        "step": recent.step,
                        "time": recent.updated_at,
                    }

        last = self._last_action or {}
        last_tool = str(last.get("tool") or "").strip()
        if not last_tool or (tool_name and last_tool != tool_name):
            return {}
        if time.time() - float(last.get("time", 0) or 0) > max_age:
            return {}
        if not self._is_retryable_tool(last_tool):
            return {}

        args = dict(last.get("args") or {})
        required_args = self._required_args_for_tool(last_tool)
        if self._missing_required_args(last_tool, args, required_args):
            return {}

        return {
            "tool": last_tool,
            "args": args,
            "goal": "",
            "status": str(last.get("status") or ""),
            "step": str(last.get("step") or ""),
            "time": float(last.get("time", 0) or 0),
        }

    def _describe_tool_attempt(self, tool_name: str, tool_args: dict) -> str:
        """Human-readable label for a retryable tool action."""
        tool_name = str(tool_name or "").strip()
        tool_args = dict(tool_args or {})

        if tool_name == "send_msg":
            contact = tool_args.get("contact", "them")
            platform = tool_args.get("platform", "the app")
            return f"message {contact} on {platform}"
        if tool_name == "open_app":
            return f"open {tool_args.get('app', 'the app')}"
        if tool_name == "screen_click":
            return f"click {tool_args.get('description') or tool_args.get('element') or 'that element'}"
        if tool_name == "screen_type":
            return f"type into {tool_args.get('description') or tool_args.get('element') or 'that field'}"
        if tool_name == "screen_find":
            return f"find {tool_args.get('description') or tool_args.get('element') or 'that element'}"
        if tool_name == "screen_read":
            return f"read {tool_args.get('description') or tool_args.get('element') or 'that area'}"
        if tool_name == "web_login":
            site = tool_args.get("site") or tool_args.get("url") or "that site"
            return f"log into {site}"
        return f"run {tool_name}"

    def _build_retry_lead_text(
        self,
        tool_name: str,
        tool_args: dict,
        *,
        correction: bool = False,
        direct_control: bool = False,
    ) -> str:
        """Build a short operator-style retry lead-in."""
        action = self._describe_tool_attempt(tool_name, tool_args)
        if direct_control and tool_name == "send_msg":
            return "Understood. I'll use direct keyboard and mouse control for this action attempt."
        if correction:
            return f"I see the issue. Retrying {action} now."
        return f"Understood. Retrying {action} now."

    def _retry_recent_tool(
        self,
        goal: str,
        *,
        lead_text: str = "",
        preferred_tool: str | None = None,
        step_prefix: str = "retrying_recent",
    ) -> Optional[PipelineResult]:
        """Retry the most recent fully-specified operator-capable action."""
        recent = self._get_recent_retryable_action(preferred_tool)
        if not recent:
            return None

        tool_name = recent["tool"]
        retry_args = dict(recent.get("args") or {})
        required_args = self._required_args_for_tool(tool_name)
        step_name = f"{step_prefix}:{tool_name}"

        self.task_sessions.start_or_update(
            goal=goal or recent.get("goal") or tool_name,
            tool_name=tool_name,
            args=retry_args,
            required_args=required_args,
            user_text=goal,
        )
        self.task_sessions.mark_executing(
            args=retry_args,
            step=step_name,
        )

        result = self.executor.execute(tool_name, retry_args)
        result_text = (
            (result.output or "")[:200]
            if result.success
            else (result.error or "Retry failed.")[:200]
        )
        completed_session = self.task_sessions.record_result(
            success=result.success,
            result_text=result_text,
            args=retry_args,
            step="completed" if result.success else "failed",
            keep_active=False,
        )

        task_brain = getattr(self.jarvis, "task_brain", None)
        if completed_session and task_brain:
            try:
                task_brain.record_task_outcome(
                    goal=completed_session.goal,
                    tool_name=completed_session.tool_name,
                    args=completed_session.args,
                    status=completed_session.status,
                    result_text=completed_session.last_result,
                    attempts=completed_session.attempts,
                    step=completed_session.step,
                    session_id=completed_session.session_id,
                )
            except Exception:
                pass

        self._sync_task_state_compat()

        reply = result.output if result.success else f"{result.error or 'Retry failed.'}{self._auto_repair_note(result)}"
        if lead_text:
            reply = f"{lead_text}\n\n{reply}"
        return PipelineResult(
            success=result.success,
            reply=reply,
            pipeline="tool_pipeline",
        )

    def _retry_recent_send(self, goal: str, lead_text: str = "") -> Optional[PipelineResult]:
        """Retry the most recent send-message action without needing the AI pipeline."""
        return self._retry_recent_tool(
            goal,
            lead_text=lead_text,
            preferred_tool="send_msg",
            step_prefix="retrying_recent_send",
        )

    def _local_pipeline(self, task: Task) -> PipelineResult:
        """
        Fast path: handle locally without any API calls.
        Serves cached answers and simple requests (greetings, time, date).
        """
        msg = task.text.strip()
        msg_lower = msg.lower().strip()

        # Try cache first
        cache_key = self._cache_key(msg_lower)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached:
                cached["hits"] += 1
                cached["last_used"] = time.time()
                logger.debug("Cache hit for '%s' (hits=%d)", msg[:30], cached["hits"])
                return PipelineResult(
                    success=True, reply=cached["reply"], pipeline="local_pipeline",
                )

        # Greetings
        if msg_lower in _GREETINGS:
            reply = "Hello, sir. How can I assist you?"
            return PipelineResult(success=True, reply=reply, pipeline="local_pipeline")

        # Time
        if re.search(r"what(?:'s| is) the time", msg_lower) or msg_lower in ("time", "current time"):
            now = datetime.now().strftime("%I:%M %p")
            return PipelineResult(
                success=True, reply=f"It's {now}, sir.", pipeline="local_pipeline",
            )

        # Date
        if re.search(r"what(?:'s| is) (?:the |today(?:'s)? )?date", msg_lower) or msg_lower == "date":
            today = datetime.now().strftime("%A, %B %d, %Y")
            return PipelineResult(
                success=True, reply=f"Today is {today}, sir.", pipeline="local_pipeline",
            )

        # Identity
        if _BASIC_FACTS_RE.search(msg_lower):
            if "what can you do" in msg_lower:
                capabilities = getattr(self.jarvis, "capabilities", None)
                if capabilities:
                    reply = capabilities.describe_for_user(limit=14)
                    return PipelineResult(success=True, reply=reply, pipeline="local_pipeline")
            reply = (
                "I am J.A.R.V.I.S — Just A Rather Very Intelligent System. "
                "I can help you with tasks, answer questions, control your system, "
                "and much more."
            )
            return PipelineResult(success=True, reply=reply, pipeline="local_pipeline")

        if self._is_recent_send_status_query(msg_lower):
            return PipelineResult(
                success=True,
                reply=self._format_recent_send_status(),
                pipeline="local_pipeline",
            )

        waiting_session = self.task_sessions.get_waiting_session()
        if (
            waiting_session
            and waiting_session.step == "awaiting_retry"
            and self._is_retry_confirmation(msg_lower, allow_plain_yes=True)
        ):
            retry = self._retry_recent_tool(
                msg,
                lead_text=self._build_retry_lead_text(
                    waiting_session.tool_name,
                    waiting_session.args,
                ),
                preferred_tool=waiting_session.tool_name,
            )
            if retry:
                return retry

        if (
            getattr(self.jarvis, "direct_control_preferred", False)
            and self._get_recent_send_args()
            and _DIRECT_CONTROL_RETRY_RE.search(msg_lower)
        ):
            retry = self._retry_recent_send(
                msg,
                lead_text="Understood. I'll use direct keyboard and mouse control for this message attempt.",
            )
            if retry:
                return retry

        if _DIRECT_CONTROL_RE.search(msg_lower):
            setattr(self.jarvis, "direct_control_preferred", True)
            should_retry = bool(
                _DIRECT_CONTROL_RETRY_RE.search(msg_lower)
                or re.search(r"\b(?:send|text|message|whatsapp|telegram|instagram|discord)\b", msg_lower)
            )
            if should_retry:
                retry = self._retry_recent_send(
                    msg,
                    lead_text="Understood. I'll use direct keyboard and mouse control for this message attempt.",
                )
                if retry:
                    return retry
            return PipelineResult(
                success=True,
                reply="Understood. I'll use direct keyboard and mouse control for the next compatible desktop action.",
                pipeline="local_pipeline",
            )

        return PipelineResult(success=False, reply="", pipeline="local_pipeline")

    # ── Tool Pipeline ────────────────────────────────────────────

    def _tool_pipeline(self, task: Task) -> PipelineResult:
        """
        Route to a tool: detect which tool, build args, check safety,
        execute via Executor, and format response.
        """
        msg = task.text.strip()
        msg_lower = msg.lower().strip()

        if self._is_recent_send_status_query(msg_lower):
            self._clear_pending_tool("send_msg")
            self.task_sessions.clear_active("send_msg")
            self._sync_task_state_compat()
            return PipelineResult(
                success=True,
                reply=self._format_recent_send_status(),
                pipeline="tool_pipeline",
            )

        pending_tool = task.metadata.get("pending_tool")
        if pending_tool:
            tool_name = pending_tool.get("tool")
            pending_args = dict(pending_tool.get("args", {}))
            followup_args = self._build_tool_args(tool_name, msg, None)
            tool_args = self._merge_pending_tool_args(tool_name, pending_tool, pending_args, followup_args, msg)
            match_obj = None
        else:
            tool_name = task.metadata.get("planned_tool")
            match_obj = None

        # ── Correction / frustration detection ────────────────────
        # If user says "you didn't send", "why not understanding", "wrong place"
        # and there's a recent action, enter repair mode instead of starting over
        if self._last_action and (time.time() - self._last_action.get("time", 0) < 120):
            correction_re = re.compile(
                r"\b(?:not\s+(?:in|on|there)|wrong\s+(?:place|chat|box|field)|"
                r"(?:in|on)\s+(?:the\s+)?(?:search|chat|text)\s*(?:bar|box|field)|"
                r"instead|i\s+(?:meant|said)|no\s+(?:in|on)|"
                # ── Frustration / failure reports ──
                r"you\s+(?:didn'?t|have\s+not|haven'?t)|"
                r"didn'?t\s+(?:send|type|click|do|work|open)|"
                r"that'?s\s+not\s+what|not\s+what\s+i|"
                r"why\s+(?:are\s+you\s+not|aren'?t\s+you|can'?t\s+you|didn'?t\s+you)|"
                r"you\s+(?:just|only)\s+(?:searched|opened|clicked)|"
                r"but\s+(?:you|it)\s+didn'?t|"
                r"try\s+again|do\s+it\s+(?:again|properly)|"
                r"that\s+didn'?t\s+work|it\s+(?:didn'?t|doesn'?t)\s+work)\b", re.I
            )
            if self._looks_like_recent_action_correction(msg_lower) or correction_re.search(msg_lower):
                last = self._last_action
                if last.get("tool") == "send_msg":
                    retry_args = dict(last.get("args") or {})
                    required_retry_args = self._required_args_for_tool("send_msg")
                    retry_missing = self._missing_required_args("send_msg", retry_args, required_retry_args)
                    if not retry_missing:
                        self.task_sessions.start_or_update(
                            goal=msg,
                            tool_name="send_msg",
                            args=retry_args,
                            required_args=required_retry_args,
                            user_text=msg,
                        )
                        self.task_sessions.mark_executing(
                            args=retry_args,
                            step="retrying_after_correction",
                        )
                        retry_result = self.executor.execute("send_msg", retry_args)
                        retry_text = (
                            (retry_result.output or "")[:200]
                            if retry_result.success
                            else (retry_result.error or "Retry failed.")[:200]
                        )
                        completed_session = self.task_sessions.record_result(
                            success=retry_result.success,
                            result_text=retry_text,
                            args=retry_args,
                            step="completed" if retry_result.success else "failed",
                            keep_active=False,
                        )
                        task_brain = getattr(self.jarvis, "task_brain", None)
                        if completed_session and task_brain:
                            try:
                                task_brain.record_task_outcome(
                                    goal=completed_session.goal,
                                    tool_name=completed_session.tool_name,
                                    args=completed_session.args,
                                    status=completed_session.status,
                                    result_text=completed_session.last_result,
                                    attempts=completed_session.attempts,
                                    step=completed_session.step,
                                    session_id=completed_session.session_id,
                                )
                            except Exception:
                                pass
                        self._sync_task_state_compat()

                        contact = retry_args.get("contact", "them")
                        platform = retry_args.get("platform", "the app")
                        repair_note = self._auto_repair_note(retry_result)
                        if retry_result.success:
                            return PipelineResult(
                                success=True,
                                reply=(
                                    f"I see the issue. Retrying the message to {contact} on {platform} now.\n\n"
                                    f"{retry_result.output}"
                                ),
                                pipeline="tool_pipeline",
                            )
                        return PipelineResult(
                            success=False,
                            reply=(
                                f"I retried the message to {contact} on {platform}, but it still didn't complete.\n\n"
                                f"{retry_result.error or 'Retry failed.'}{repair_note}"
                            ),
                            pipeline="tool_pipeline",
                        )

                retry = self._retry_recent_tool(
                    msg,
                    lead_text=self._build_retry_lead_text(
                        last.get("tool", ""),
                        dict(last.get("args") or {}),
                        correction=True,
                        direct_control=bool(getattr(self.jarvis, "direct_control_preferred", False)),
                    ),
                    preferred_tool=last.get("tool", ""),
                    step_prefix="retrying_after_correction",
                )
                if retry:
                    return retry

                # This is a correction — route to AI with full repair context
                correction_context = (
                    f"[REPAIR MODE] The user is telling you the previous action FAILED. "
                    f"Do NOT greet them. Do NOT ask how you can help.\n"
                    f"Previous action: tool={last.get('tool')}, args={last.get('args')}, "
                    f"result={last.get('result', 'unknown')}.\n"
                    f"User says: \"{msg}\".\n"
                    f"You must: 1) Acknowledge what went wrong, "
                    f"2) Explain what you actually did vs what was intended, "
                    f"3) Propose the corrective action and execute it.\n"
                    f"Example: 'I see the issue. I searched for the contact but the cursor "
                    f"stayed in the search bar instead of the message box. Let me retry "
                    f"from the chat input.'"
                )
                task.metadata["correction_context"] = correction_context
                return self._ai_pipeline(task)

        # Detect the tool from patterns
        if not tool_name:
            capability_match = self._resolve_capability_match(msg)
            if capability_match:
                tool_name = capability_match.capability.name
                task.metadata.setdefault("planned_tool", tool_name)

        if not tool_name:
            for pattern, tname in _TOOL_PATTERNS:
                m = pattern.search(msg_lower)
                if m:
                    tool_name = tname
                    match_obj = m
                    break

        if not tool_name:
            # Fall through to AI pipeline
            return self._ai_pipeline(task)

        # Build tool args from the match
        if not pending_tool:
            tool_args = self._build_tool_args(tool_name, msg, match_obj)

        required_args = self._required_args_for_tool(tool_name)
        self.task_sessions.start_or_update(
            goal=msg,
            tool_name=tool_name,
            args=tool_args,
            required_args=required_args,
            user_text=msg,
        )

        missing_fields = self._missing_required_args(tool_name, tool_args, required_args)
        if missing_fields:
            prompts = self._missing_prompts_for_tool(tool_name, tool_args, missing_fields)
            self.task_sessions.set_waiting(
                missing_args=missing_fields,
                prompts=prompts,
                args=tool_args,
                result_text="Waiting for missing task details.",
            )
            self._sync_task_state_compat()
            return PipelineResult(
                success=True,
                reply=" ".join(prompts),
                pipeline="tool_pipeline",
            )

        # Safety check
        from core.safety import needs_confirmation, describe_risk
        if needs_confirmation(tool_name, tool_args):
            risk_msg = describe_risk(tool_name, tool_args)
            # Request confirmation through UI
            confirmed = self._request_confirmation_sync(risk_msg)
            if not confirmed:
                cancelled = self.task_sessions.cancel_active("Action cancelled during confirmation.")
                task_brain = getattr(self.jarvis, "task_brain", None)
                if cancelled and task_brain:
                    try:
                        task_brain.record_task_outcome(
                            goal=cancelled.goal,
                            tool_name=cancelled.tool_name,
                            args=cancelled.args,
                            status="cancelled",
                            result_text=cancelled.last_result,
                            attempts=cancelled.attempts,
                            step=cancelled.step,
                            session_id=cancelled.session_id,
                        )
                    except Exception:
                        pass
                self._sync_task_state_compat()
                return PipelineResult(
                    success=True,
                    reply="Understood, sir. Action cancelled.",
                    pipeline="tool_pipeline",
                )

        self.task_sessions.mark_executing(
            args=tool_args,
            step=f"executing:{tool_name}",
        )

        # Execute (Executor already has resilient retry built in)
        result = self.executor.execute(tool_name, tool_args)

        # Track tool outcome in intelligence engine
        intel = getattr(self.jarvis, "intelligence", None)
        if intel:
            intel.on_tool_result(tool_name, result.success,
                                result.error if not result.success else "")

        # Record in struggle detector + execution router
        struggle = getattr(self.jarvis, "struggle_detector", None)
        router = getattr(self.jarvis, "execution_router", None)
        exec_mode = "api"  # default; screen mode tracked in agent_loop
        if router:
            exec_mode = router.choose_mode(tool_name, tool_args, msg)
            router.record_outcome(tool_name, exec_mode, result.success,
                                  latency_ms=0.0)
        if struggle:
            struggle.record(
                tool_name=tool_name,
                tool_args=tool_args,
                mode=exec_mode,
                success=result.success,
                error=(result.error or "")[:200],
            )

        # Feed successful scan results into knowledge graph
        kg = getattr(self.jarvis, "knowledge_graph", None)
        if kg and result.success and result.output:
            try:
                # Extract target from tool args
                target = (tool_args.get("domain") or tool_args.get("url")
                          or tool_args.get("host") or tool_args.get("keyword") or "")
                if target:
                    kg.extract_scan_results(tool_name, target, result.output)
                # Also do general text extraction
                kg.extract_from_text(result.output, source=f"tool:{tool_name}")
            except Exception:
                pass

        # Track last action for follow-up corrections / repair mode
        result_text = (result.output or "")[:200] if result.success else (result.error or "Tool failed.")[:200]
        completed_session = self.task_sessions.record_result(
            success=result.success,
            result_text=result_text,
            args=tool_args,
            step="completed" if result.success else "failed",
            keep_active=False,
        )
        task_brain = getattr(self.jarvis, "task_brain", None)
        if completed_session and task_brain:
            try:
                task_brain.record_task_outcome(
                    goal=completed_session.goal,
                    tool_name=completed_session.tool_name,
                    args=completed_session.args,
                    status=completed_session.status,
                    result_text=completed_session.last_result,
                    attempts=completed_session.attempts,
                    step=completed_session.step,
                    session_id=completed_session.session_id,
                )
            except Exception:
                pass
        self._sync_task_state_compat()
        using_direct_control = tool_name == "send_msg" and getattr(self.jarvis, "direct_control_preferred", False)

        if result.success:
            self._clear_pending_tool(tool_name)
            reply = result.output or f"Done — {tool_name} executed successfully."
        else:
            # Record the failure for learning
            resilient = getattr(self.jarvis, "resilient", None)
            if resilient:
                resilient.knowledge.record_error(
                    "tool_failure", result.error[:200],
                    f"tool={tool_name} args={tool_args}",
                )
            # Give a helpful clarification message instead of raw error
            error_text = result.error or "Unknown tool failure."
            input_errors = ["no message", "no contact", "not specified", "not provided", "missing"]
            is_input_err = any(phrase in error_text.lower() for phrase in input_errors)
            is_ambiguous_contact = (
                tool_name == "send_msg"
                and str((result.data or {}).get("kind", "")).lower() == "ambiguous_contact"
            )

            if is_input_err or is_ambiguous_contact:
                if is_ambiguous_contact:
                    tool_args = dict(tool_args or {})
                    tool_args["contact"] = ""
                    options = list((result.data or {}).get("options") or [])
                    if options:
                        tool_args["contact_options"] = options
                    query = str((result.data or {}).get("query", "") or "").strip()
                    if query:
                        tool_args["contact_query"] = query
                    prompts = [error_text]
                    self.task_sessions.start_or_update(
                        goal=msg,
                        tool_name=tool_name,
                        args=tool_args,
                        required_args=self._required_args_for_tool(tool_name),
                        user_text=msg,
                    )
                    self.task_sessions.set_waiting(
                        missing_args=["contact"],
                        prompts=prompts,
                        args=tool_args,
                        result_text=error_text,
                        step="awaiting_contact_choice",
                    )
                    self._sync_task_state_compat()
                    reply = error_text
                    if using_direct_control and "direct keyboard and mouse control" not in reply.lower():
                        reply = f"Using direct keyboard and mouse control.\n\n{reply}"
                    return PipelineResult(
                        success=False,
                        reply=reply,
                        pipeline="tool_pipeline",
                    )

                missing_fields = self._missing_required_args(tool_name, tool_args)
                if missing_fields:
                    prompts = self._missing_prompts_for_tool(tool_name, tool_args, missing_fields)
                    self.task_sessions.start_or_update(
                        goal=msg,
                        tool_name=tool_name,
                        args=tool_args,
                        required_args=self._required_args_for_tool(tool_name),
                        user_text=msg,
                    )
                    self.task_sessions.set_waiting(
                        missing_args=missing_fields,
                        prompts=prompts,
                        args=tool_args,
                        result_text=error_text,
                    )
                    self._sync_task_state_compat()
                    reply = " ".join(prompts)
                else:
                    self.task_sessions.start_or_update(
                        goal=msg,
                        tool_name=tool_name,
                        args=tool_args,
                        required_args=self._required_args_for_tool(tool_name),
                        user_text=msg,
                    )
                    follow_up = (
                        "I have the details, but the action still failed. Do you want me to retry?"
                        if tool_name == "send_msg"
                        else "I still need a bit more detail before I can finish that. Could you clarify?"
                    )
                    self.task_sessions.set_waiting(
                        missing_args=[],
                        prompts=[follow_up],
                        args=tool_args,
                        result_text=error_text,
                        step="awaiting_retry" if tool_name == "send_msg" else "awaiting_clarification",
                    )
                    self._sync_task_state_compat()
                    reply = follow_up
            elif self._is_retryable_tool(tool_name):
                self.task_sessions.start_or_update(
                    goal=msg,
                    tool_name=tool_name,
                    args=tool_args,
                    required_args=self._required_args_for_tool(tool_name),
                    user_text=msg,
                )
                follow_up = (
                    f"I hit resistance while trying to {self._describe_tool_attempt(tool_name, tool_args)}. "
                    f"Say 'try again' and I'll rerun it directly."
                )
                self.task_sessions.set_waiting(
                    missing_args=[],
                    prompts=[follow_up],
                    args=tool_args,
                    result_text=error_text,
                    step="awaiting_retry",
                )
                self._sync_task_state_compat()
                reply = f"{follow_up}\n\n{error_text}{self._auto_repair_note(result)}"
            else:
                self._clear_pending_tool(tool_name)
                self.task_sessions.clear_active(tool_name)
                self._sync_task_state_compat()
                reply = f"Tried multiple approaches but hit a wall: {result.error}{self._auto_repair_note(result)}"

        if using_direct_control and "direct keyboard and mouse control" not in reply.lower():
            reply = f"Using direct keyboard and mouse control.\n\n{reply}"

        return PipelineResult(
            success=result.success, reply=reply, pipeline="tool_pipeline",
        )

    def _auto_repair_note(self, result: ToolResult) -> str:
        """Add a small user-facing note when a background self-repair was scheduled."""
        try:
            info = (result.data or {}).get("auto_repair", {})
        except Exception:
            return ""

        if not info or not info.get("queued"):
            return ""

        label = info.get("label", "module")
        return (
            f"\n\nI'm diagnosing the {label} in the background and will patch it automatically "
            f"if the fix passes syntax and reload checks."
        )

    def _get_recent_pending_tool(self) -> dict:
        """Return a pending tool request if it is still fresh enough to resume."""
        if not self._pending_tool:
            return {}
        if time.time() - self._pending_tool.get("time", 0) > 120:
            self._pending_tool = {}
            return {}
        return dict(self._pending_tool)

    def _clear_pending_tool(self, tool_name: Optional[str] = None) -> None:
        """Clear pending tool state, optionally only for a specific tool."""
        if not self._pending_tool:
            return
        if tool_name and self._pending_tool.get("tool") != tool_name:
            return
        self._pending_tool = {}

    def _pending_tool_for_rescue(self) -> dict:
        """Return the freshest pending tool state suitable for routing rescue."""
        waiting = self.task_sessions.get_waiting_session()
        if waiting:
            return waiting.to_pending_tool()
        return self._get_recent_pending_tool()

    def _required_args_for_tool(self, tool_name: str) -> list[str]:
        """Look up required args for a tool from the structured schema registry."""
        schema = get_schema_for_tool(tool_name or "")
        if not schema:
            return []
        input_schema = schema.get("input_schema", {})
        return list(input_schema.get("required", []) or [])

    def _tool_arg_present(self, value: Any) -> bool:
        """Treat blank strings and empty containers as missing, but allow values like 0."""
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, dict, set)):
            return bool(value)
        return True

    def _missing_required_args(self, tool_name: str, tool_args: dict, required_args: Optional[list[str]] = None) -> list[str]:
        """Return the required tool args that are still missing."""
        required = required_args if required_args is not None else self._required_args_for_tool(tool_name)
        missing = []
        for field in required:
            if not self._tool_arg_present((tool_args or {}).get(field)):
                missing.append(field)
        return missing

    def _missing_prompts_for_tool(self, tool_name: str, tool_args: dict, missing_fields: list[str]) -> list[str]:
        """Generate focused follow-up prompts for only the missing pieces."""
        if not missing_fields:
            return []

        if tool_name == "send_msg":
            prompt_map = {
                "contact": "Who should I send it to?",
                "platform": "Which app should I use: WhatsApp, Telegram, Instagram, or Discord?",
                "message": "What should the message say?",
            }
            return [prompt_map[field] for field in missing_fields if field in prompt_map]

        prompt_map = {
            "app": "Which app should I open?",
            "query": "What should I search for?",
            "description": "What should I look for on the screen?",
            "text": "What text should I type?",
            "url": "Which URL should I use?",
            "domain": "Which domain should I use?",
            "host": "Which host should I scan?",
            "path": "Which file path should I use?",
            "content": "What content should I write?",
            "to": "Who should I send it to?",
            "subject": "What should the subject be?",
            "body": "What should the message say?",
            "time": "When should I set it for?",
            "duration": "How long should I set it for?",
            "city": "Which city should I check?",
        }
        prompts = []
        for field in missing_fields:
            prompts.append(prompt_map.get(field, f"What {field.replace('_', ' ')} should I use?"))
        return prompts

    def _sync_task_state_compat(self) -> None:
        """Keep legacy pending/last-action state aligned with task sessions."""
        waiting = self.task_sessions.get_waiting_session()
        recent = self.task_sessions.get_recent_action()
        self._pending_tool = waiting.to_pending_tool() if waiting else {}
        self._last_action = recent.to_last_action() if recent else {}

    def _merge_pending_tool_args(self, tool_name: str, pending_tool: dict, pending_args: dict, followup_args: dict, text: str) -> dict:
        """Merge a new follow-up utterance into an existing pending tool request."""
        merged = dict(pending_args or {})
        for key, value in (followup_args or {}).items():
            if value:
                merged[key] = value

        if tool_name != "send_msg":
            return merged

        platforms = {"whatsapp", "telegram", "instagram", "discord"}
        filler = {
            "yes", "yeah", "yep", "yup", "ok", "okay", "please", "now",
            "send", "message", "text", "msg", "dm", "it", "him", "her",
        }
        text_clean = text.strip().lower()
        missing_lines = [str(item).lower() for item in pending_tool.get("missing", [])]
        missing_text = " ".join(missing_lines)

        affirmation_re = re.compile(
            r"^(?:yes|yeah|yep|yup|exactly|right|correct|sure|okay|ok|"
            r"yes\s+exactly|that's\s+right|that'?s\s+it)\b",
            re.I,
        )
        if affirmation_re.search(text_clean):
            return merged

        if not merged.get("platform") and "which app" in missing_text:
            token = text_clean.replace("on ", "").strip()
            if token in platforms:
                merged["platform"] = token

        contact_options = [str(item).strip() for item in (merged.get("contact_options") or []) if str(item).strip()]
        if not merged.get("contact") and contact_options:
            raw_choice = re.sub(r"^(?:to|use)\s+", "", text.strip(), flags=re.I).strip()
            if re.fullmatch(r"\d+", raw_choice):
                idx = int(raw_choice) - 1
                if 0 <= idx < len(contact_options):
                    merged["contact"] = contact_options[idx]
            if not merged.get("contact"):
                normalized_choice = re.sub(r"\s+", " ", raw_choice.strip().lower())
                for option in contact_options:
                    normalized_option = re.sub(r"\s+", " ", option.strip().lower())
                    if (
                        normalized_choice == normalized_option
                        or normalized_choice in normalized_option
                        or normalized_option in normalized_choice
                    ):
                        merged["contact"] = option
                        break
            if not merged.get("contact") and raw_choice and raw_choice.lower() not in platforms and raw_choice.lower() not in filler:
                merged["contact"] = raw_choice
            if merged.get("contact"):
                merged.pop("contact_options", None)
                merged.pop("contact_query", None)

        if not merged.get("contact") and "who should i send it to" in missing_text:
            token = re.sub(r"^(?:to\s+)?", "", text.strip(), flags=re.I).strip()
            token_lower = token.lower()
            if token and token_lower not in platforms and token_lower not in filler:
                merged["contact"] = token

        if not merged.get("message") and "what should the message say" in missing_text:
            if text_clean and text_clean not in filler and text_clean not in platforms:
                merged["message"] = text.strip()

        return merged

    def _build_tool_args(self, tool_name: str, text: str, match) -> dict:
        """Build tool arguments from the user's text and regex match."""
        msg_lower = text.lower().strip()

        if tool_name == "open_app":
            # Extract app name from "open X" / "launch X"
            m = re.search(r"\b(?:open|launch|start|run)\s+(.+)", msg_lower)
            app = m.group(1).strip() if m else ""
            return {"app": app}

        elif tool_name == "get_weather":
            m = re.search(r"weather\s+(?:in\s+)?(.+)", msg_lower)
            city = m.group(1).strip() if m else ""
            return {"city": city}

        elif tool_name == "get_news":
            m = re.search(r"news\s+(?:about\s+)?(.+)", msg_lower)
            topic = m.group(1).strip() if m else ""
            return {"topic": topic}

        elif tool_name == "get_crypto":
            m = re.search(r"(?:price\s+(?:of\s+)?|crypto\s+)(\w+)", msg_lower)
            coin = m.group(1).strip() if m else ""
            return {"coin": coin}

        elif tool_name == "get_wiki":
            m = re.search(r"wiki(?:pedia)?\s+(.+)", msg_lower)
            topic = m.group(1).strip() if m else text
            return {"topic": topic}

        elif tool_name == "get_definition":
            m = re.search(r"define\s+(.+)", msg_lower)
            word = m.group(1).strip() if m else ""
            return {"word": word}

        elif tool_name == "web_search":
            # Detect platform: "search X on youtube" / "youtube search X" / "search X in spotify"
            platform = ""
            platforms = ["youtube", "google", "github", "stackoverflow", "stack overflow",
                         "reddit", "amazon", "wikipedia", "twitter", "x", "linkedin", "spotify"]
            for p in platforms:
                if re.search(rf"\bon\s+{p}\b|\bin\s+{p}\b|{p}\s+search", msg_lower):
                    platform = p
                    break
                # Also detect "youtube X" as "search X on youtube"
                if msg_lower.startswith(p + " "):
                    platform = p
                    break

            # Extract query — strip platform name and trigger words
            # Handles: "search X", "open X in youtube", "play X on spotify", "find X"
            m = re.search(
                r"(?:search|google|look\s*up|find|open|play|watch|listen\s+to)\s+(?:for\s+)?(.+)",
                msg_lower
            )
            query = m.group(1).strip() if m else text.strip()
            # Remove "on youtube" / "in youtube" / "on google" etc from the query
            for p in platforms:
                query = re.sub(rf"\s+on\s+{p}\b", "", query, flags=re.I).strip()
                query = re.sub(rf"\s+in\s+{p}\b", "", query, flags=re.I).strip()
                query = re.sub(rf"^{p}\s+", "", query, flags=re.I).strip()
            # Also strip "can you" / "please" / "for me" noise
            query = re.sub(r"^(?:can\s+you\s+|please\s+|for\s+me\s*)", "", query, flags=re.I).strip()
            return {"query": query, "platform": platform}

        elif tool_name == "set_reminder":
            m = re.search(r"remind(?:er)?\s+(?:me\s+)?(?:in\s+)?(.+)", msg_lower)
            raw = m.group(1).strip() if m else text
            return {"time": "5m", "message": raw}

        elif tool_name == "set_timer":
            m = re.search(r"timer\s+(?:for\s+)?(.+)", msg_lower)
            duration = m.group(1).strip() if m else "5m"
            return {"duration": duration}

        elif tool_name == "set_volume":
            m = re.search(r"volume\s+(?:to\s+)?(\d+)", msg_lower)
            level = int(m.group(1)) if m else 50
            return {"level": level}

        elif tool_name in ("check_inbox",):
            return {"count": 5}

        elif tool_name == "send_email":
            return {"to": "", "subject": "", "body": text}

        elif tool_name == "url_scan":
            m = re.search(r"(?:scan|check)\s+(?:url\s+)?(?:https?://\S+)", msg_lower)
            url = m.group(0).split()[-1] if m else ""
            return {"url": url}

        elif tool_name == "port_scan":
            m = re.search(r"port\s*scan\s+(\S+)", msg_lower)
            host = m.group(1) if m else ""
            return {"host": host}

        elif tool_name == "web_login":
            # Detect what site to login to
            if re.search(r"\b(?:uni|university|studynet|herts)\b", msg_lower):
                return {"site": "university"}
            m = re.search(r"(?:https?://\S+)", text)
            url = m.group(0) if m else ""
            return {"site": "custom", "url": url}

        # ── Pentest tools ─────────────────────────────────────────
        elif tool_name in ("recon", "subdomain_enum", "google_dorks", "wayback"):
            # Extract domain from text
            m = re.search(r"(?:https?://)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)", text)
            domain = m.group(1) if m else text.split()[-1] if text.split() else ""
            return {"domain": domain}

        elif tool_name in ("tech_detect", "dir_fuzz", "cors_check", "xss_test",
                           "sqli_test", "open_redirect", "header_audit"):
            # Extract URL from text
            m = re.search(r"(https?://\S+)", text)
            url = m.group(1) if m else ""
            if not url:
                m = re.search(r"([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}\S*)", text)
                url = m.group(1) if m else ""
            return {"url": url}

        elif tool_name == "ssl_check":
            m = re.search(r"(?:https?://)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?::\d+)?)", text)
            host = m.group(1) if m else ""
            return {"host": host}

        elif tool_name == "web_research":
            m = re.search(r"(?:research|look\s*up|find\s+(?:out|info))\s+(?:about\s+)?(.+)", msg_lower)
            query = m.group(1).strip() if m else text.strip()
            depth = "deep" if re.search(r"\b(?:deep|thorough|detailed|comprehensive)\b", msg_lower) else "quick"
            return {"query": query, "depth": depth}

        elif tool_name == "research_cve":
            m = re.search(r"(CVE-\d{4}-\d+)", text, re.I)
            cve_id = m.group(1).upper() if m else text.strip()
            return {"cve_id": cve_id}

        elif tool_name == "research_target":
            m = re.search(r"(?:https?://)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,})", text)
            domain = m.group(1) if m else ""
            return {"domain": domain}

        elif tool_name in ("pentest_chain", "quick_recon_chain"):
            m = re.search(r"(?:https?://)?([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)", text)
            domain = m.group(1) if m else text.split()[-1] if text.split() else ""
            return {"domain": domain}

        elif tool_name in ("cve_search", "exploit_search"):
            # Extract keyword — everything after the trigger word
            m = re.search(r"\b(?:cve|exploit|search)\s+(.+)", msg_lower)
            keyword = m.group(1).strip() if m else text.strip()
            return {"keyword": keyword}

        elif tool_name == "mouse_click":
            # Try to extract coordinates or element description
            m = re.search(r"(\d+)\s*,\s*(\d+)", text)
            if m:
                return {"x": int(m.group(1)), "y": int(m.group(2))}
            # No coordinates — let AI figure it out or click current position
            m = re.search(r"click\s+(?:on\s+)?(?:the\s+)?(.+)", msg_lower)
            target = m.group(1).strip() if m else ""
            return {"target": target}

        elif tool_name == "mouse_scroll":
            amount = 3  # default scroll amount
            if "up" in msg_lower:
                amount = 3
            elif "down" in msg_lower:
                amount = -3
            m = re.search(r"(\d+)", text)
            if m:
                val = int(m.group(1))
                amount = val if "up" in msg_lower else -val
            return {"amount": amount}

        elif tool_name == "type_text":
            m = re.search(r"type\s+(?:in\s+|out\s+)?['\"]?(.+?)['\"]?\s*$", msg_lower)
            txt = m.group(1).strip() if m else text.strip()
            return {"text": txt}

        elif tool_name == "key_press":
            m = re.search(r"press\s+(?:the\s+)?(.+)", msg_lower)
            keys = m.group(1).strip() if m else ""
            # Detect combos: "ctrl+c", "alt+tab", "ctrl shift delete"
            if "+" in keys or re.search(r"\b(?:ctrl|alt|shift|win)\b.*\b(?:ctrl|alt|shift|win|[a-z])\b", keys):
                keys = re.sub(r"\s+", "+", keys)  # "ctrl c" → "ctrl+c"
                return {"keys": keys}
            return {"key": keys}

        elif tool_name == "take_screenshot":
            return {}

        # ── AI screen interaction ────────────────────────────────
        elif tool_name == "screen_find":
            m = re.search(r"find\s+(?:the\s+)?(.+)", msg_lower)
            element = m.group(1).strip() if m else text.strip()
            return {"description": element}

        elif tool_name == "screen_click":
            m = re.search(r"click\s+(?:on\s+)?(?:the\s+)?(.+)", msg_lower)
            element = m.group(1).strip() if m else text.strip()
            return {"description": element}

        elif tool_name == "screen_type":
            # "type hello into the search field"
            m = re.search(r"type\s+['\"]?(.+?)['\"]?\s+into\s+(?:the\s+)?(.+)", msg_lower)
            if m:
                return {"text": m.group(1).strip(), "description": m.group(2).strip()}
            m = re.search(r"type\s+(?:into|in)\s+(?:the\s+)?(.+)", msg_lower)
            element = m.group(1).strip() if m else ""
            return {"text": "", "description": element}

        elif tool_name == "screen_read":
            m = re.search(r"read\s+(?:the\s+)?(.+)", msg_lower)
            element = m.group(1).strip() if m else ""
            return {"description": element}

        # ── Dev agent ────────────────────────────────────────────
        elif tool_name == "build_project":
            m = re.search(r"(?:build|create|make|generate)\s+(?:a\s+|me\s+(?:a\s+)?)?(.+)", msg_lower)
            description = m.group(1).strip() if m else text.strip()
            return {"description": description}

        # ── Messaging ────────────────────────────────────────────
        elif tool_name == "send_msg":
            # Tolerant natural-language slot extraction
            # Handles: "text meet on whatsapp that i am coming"
            #          "tell meet i'm coming on whatsapp"
            #          "send a whatsapp to meet saying hello"
            #          "can you message meet"
            #          "whatsapp meet i am coming"
            request_text = re.sub(
                r"^(?:well\s+)?(?:yes|yeah|yep|yup|no|nah|nope)\s+"
                r"(?=(?:can\s+you|could\s+you|would\s+you|please|send|text|message|msg|dm|tell)\b)",
                "",
                msg_lower,
            ).strip()
            request_text = re.sub(r"^(?:try|please)\s+", "", request_text).strip()
            request_text = re.sub(r"\btexting\b", "text", request_text)
            request_text = re.sub(r"\bmessaging\b", "message", request_text)

            if _DIRECT_CONTROL_TRAILER_RE.search(request_text):
                setattr(self.jarvis, "direct_control_preferred", True)
                request_text = _DIRECT_CONTROL_TRAILER_RE.sub("", request_text).strip()

            platforms_list = ["whatsapp", "telegram", "instagram", "discord"]
            noise_words = {"a", "the", "on", "to", "via", "through", "message",
                           "text", "send", "tell", "msg", "dm", "can", "you",
                           "please", "now", "just", "me", "my", "saying", "say",
                           "that", "do", "this", "it", "him", "her", "i"}

            # 1. Detect platform
            platform = ""
            for p in platforms_list:
                if p in request_text:
                    platform = p
                    break
            if not platform:
                platform = "whatsapp"

            # 2. Extract message body — after "that/saying/say/i'm/i am"
            message = ""
            msg_patterns = [
                r"(?:that\s+|saying\s+|say\s+|with\s+message\s+|:\s*|message\s+is\s+)(.+)",
                r"\b(?:i'?m|i\s+am|i\s+will|i'll)\s+(.+)",  # "tell meet i'm coming"
            ]
            for pat in msg_patterns:
                m = re.search(pat, request_text)
                if m:
                    message = m.group(1).strip()
                    for p in platforms_list:
                        message = re.sub(rf"\s+on\s+{p}\s*$", "", message).strip()
                    break

            # 3. Extract contact — find the proper noun (not a noise/trigger/platform word)
            contact = ""
            # Try structured patterns first
            contact_patterns = [
                r"(?:send|text|message|msg|dm|tell)(?:\s+(?:a\s+)?(?:message|text|msg|dm))?\s+(?:to\s+)?(\w+)",
                r"(?:text|message)\s+(\w+)\s+(?:on|via|through|that|saying|say)\b",
                r"(?:whatsapp|telegram)\s+(?:to\s+)?(\w+)",
                r"(?:to|for)\s+(\w+)\s+(?:on|via|that|saying|say)\b",
            ]
            for pat in contact_patterns:
                m = re.search(pat, request_text)
                if m:
                    candidate = m.group(1).strip()
                    if candidate not in noise_words and candidate not in platforms_list:
                        contact = candidate
                        break

            # 4. If contact empty, try "<platform> <contact> <rest>"
            if not contact and platform:
                m = re.search(rf"{platform}\s+(\w+)(?:\s+(.+))?", request_text)
                if m and m.group(1) not in noise_words:
                    contact = m.group(1).strip()
                    if not message and m.group(2):
                        message = m.group(2).strip()

            # 5. If message empty, grab everything after contact+platform
            if not message and contact:
                after = rf"{re.escape(contact)}(?:\s+on\s+\w+)?\s+(.+)"
                m = re.search(after, request_text)
                if m:
                    candidate = m.group(1).strip()
                    for p in platforms_list:
                        candidate = re.sub(rf"^(?:on\s+)?{p}\s*", "", candidate).strip()
                    if candidate and candidate not in platforms_list:
                        message = candidate

            if message:
                message = _DIRECT_CONTROL_TRAILER_RE.sub("", message).strip()

            return {"platform": platform, "contact": contact, "message": message}

        # Default: pass text as generic arg
        return {}

    def _request_confirmation_sync(self, risk_msg: str) -> bool:
        """
        Request user confirmation synchronously.
        Uses the UI thread if available, otherwise assumes yes.
        """
        permission_hook = getattr(self.jarvis, "request_permission", None)
        if callable(permission_hook):
            try:
                return bool(permission_hook(risk_msg, kind="confirmation"))
            except TypeError:
                return bool(permission_hook(risk_msg))

        if not hasattr(self.jarvis, 'root') or self.jarvis.root is None:
            return True

        result_holder = [None]
        event = threading.Event()

        def _ask():
            from tkinter import messagebox
            confirmed = messagebox.askyesno(
                "JARVIS — Confirmation Required", risk_msg,
            )
            result_holder[0] = confirmed
            event.set()

        try:
            self.jarvis.root.after(0, _ask)
            event.wait(timeout=60)
            return result_holder[0] if result_holder[0] is not None else False
        except Exception:
            return False

    # ── AI Pipeline ──────────────────────────────────────────────

    def _ai_pipeline(self, task: Task) -> PipelineResult:
        """
        Send to AI provider for reasoning, conversation, or research.
        Builds context from memory + short-term and uses fallback-aware chat.
        """
        from core.planner import build_planning_messages, parse_plan, PLANNER_PROMPT
        from core.brain import MODES

        msg_lower = task.text.lower().strip()
        rescue_pending = self._pending_tool_for_rescue()
        capability_match = self._resolve_capability_match(task.text)
        should_rescue_to_tools = bool(
            rescue_pending
            or capability_match
            or self._looks_like_single_send_request(msg_lower)
            or (_DIRECT_CONTROL_RE.search(msg_lower) and self._get_recent_send_args())
        )
        if should_rescue_to_tools:
            rescue_metadata = dict(getattr(task, "metadata", {}) or {})
            if rescue_pending and "pending_tool" not in rescue_metadata:
                rescue_metadata["pending_tool"] = rescue_pending
            if capability_match and "planned_tool" not in rescue_metadata:
                rescue_metadata["planned_tool"] = capability_match.capability.name
            rescue_task = Task(
                priority=task.priority,
                text=task.text,
                task_type=TaskType.TOOL,
                created_at=task.created_at,
                on_reply=task.on_reply,
                on_error=task.on_error,
                metadata=rescue_metadata,
            )
            return self._tool_pipeline(rescue_task)

        provider_name = str(self.brain.config.get("provider", "") or "").lower()
        local_reasoner = provider_name in {"ollama", "lmstudio"}

        # Build context
        mem_context = self.memory.get_context_string() if hasattr(self.memory, 'get_context_string') else ""
        stm_context = self.short_term.get_context_string()

        notes = ""
        if hasattr(self.jarvis, 'config'):
            notes = self.jarvis.config.get("notes", "")

        learner_context = ""
        if hasattr(self.jarvis, "learner"):
            learner_context = self.jarvis.learner.get_context_string()

        identity = MODES.get(self.brain.mode, MODES.get("General", ""))
        full_system = identity + "\n\n" + PLANNER_PROMPT
        full_system += (
            "\n\n[RESPONSE RULES]\n"
            "- Reply in plain natural English.\n"
            "- Do not begin with random foreign words, translations, or decorative exclamations.\n"
            "- Do not output JSON, code fences, or raw dictionaries to the user.\n"
            "- Do not claim you fixed code, changed files, reloaded plugins, searched the web, scanned the system, or sent a message unless a tool result in this turn confirms it.\n"
            "- If you are unsure whether an action succeeded, say so plainly.\n"
            "- Keep the answer grounded, concise, and practical.\n"
        )
        if mem_context:
            full_system += f"\n\n{mem_context}"
        if stm_context:
            full_system += f"\n\n{stm_context}"
        if learner_context:
            full_system += f"\n\n{learner_context}"
        if notes:
            full_system += f"\n\n[CURRENT NOTES]\n{notes}"

        # ── Context Injection: situational awareness ──
        try:
            from core.context_injector import ContextInjector
            ctx_injector = ContextInjector(self.jarvis)
            situational_ctx = ctx_injector.build_context()
            if situational_ctx:
                full_system += f"\n\n{situational_ctx}"
        except Exception:
            pass

        # ── Runtime capabilities: what JARVIS can actually do right now ──
        try:
            capabilities = getattr(self.jarvis, "capabilities", None)
            if capabilities:
                caps_ctx = capabilities.get_prompt_context(task.text)
                if caps_ctx:
                    full_system += f"\n\n{caps_ctx}"
            else:
                from core.tool_schemas import get_tools_summary
                tools_ctx = get_tools_summary()
                if tools_ctx:
                    full_system += f"\n\n{tools_ctx}"
        except Exception:
            pass

        # ── Task brain: learned procedures from previous task outcomes ──
        try:
            task_brain = getattr(self.jarvis, "task_brain", None)
            if task_brain:
                task_brain_ctx = task_brain.get_prompt_context(task.text)
                if task_brain_ctx:
                    full_system += f"\n\n{task_brain_ctx}"
        except Exception:
            pass

        # Inject awareness context (what user is doing, clipboard)
        try:
            if hasattr(self.jarvis, 'awareness'):
                env_ctx = self.jarvis.awareness.get_current_context()
                if env_ctx:
                    full_system += f"\n\n{env_ctx}"
                clip_ctx = self.jarvis.awareness.get_clipboard_context()
                if clip_ctx:
                    full_system += f"\n{clip_ctx}"
            # Inject 4-layer memory context
            if hasattr(self.jarvis, 'mem'):
                mem4_ctx = self.jarvis.mem.get_full_context()
                if mem4_ctx:
                    full_system += f"\n\n{mem4_ctx}"
            # Inject intent context
            if hasattr(self.jarvis, 'intent_engine'):
                intent_ctx = self.jarvis.intent_engine.get_conversation_context()
                if intent_ctx:
                    full_system += f"\n\n[INTENT] {intent_ctx}"
            # Inject conversation memory from previous sessions
            if not local_reasoner and hasattr(self.jarvis, 'plugin_manager'):
                conv_mem = self.jarvis.plugin_manager.plugins.get("conversation_memory")
                if conv_mem and hasattr(conv_mem, 'get_context_for_llm'):
                    conv_ctx = conv_mem.get_context_for_llm(max_exchanges=10)
                    if conv_ctx:
                        full_system += f"\n\n{conv_ctx}"
            # Inject intelligence context (mood, feedback, predictions)
            if not local_reasoner and hasattr(self.jarvis, 'intelligence'):
                intel_ctx = self.jarvis.intelligence.get_full_context()
                if intel_ctx:
                    full_system += f"\n\n{intel_ctx}"
            # Inject knowledge graph context
            if not local_reasoner and hasattr(self.jarvis, 'knowledge_graph'):
                # Extract topic from user message for targeted knowledge retrieval
                topic = task.text.split()[0] if task.text.split() else None
                kg_ctx = self.jarvis.knowledge_graph.get_context_for_llm(topic)
                if kg_ctx:
                    full_system += f"\n\n{kg_ctx}"
            # Inject screen awareness context
            if hasattr(self.jarvis, 'screen_monitor'):
                screen_ctx = self.jarvis.screen_monitor.get_screen_context()
                if screen_ctx:
                    full_system += f"\n\n[SCREEN] {screen_ctx}"
                # If user is struggling, add a hint
                if self.jarvis.screen_monitor.struggle_score > 50:
                    full_system += (
                        "\n[NOTE] The user appears to be struggling based on screen activity "
                        "(repeated errors, rapid window switching). Be extra helpful and proactive."
                    )
            # Inject SELF-struggle awareness (JARVIS's own execution difficulty)
            if hasattr(self.jarvis, 'struggle_detector'):
                struggle_ctx = self.jarvis.struggle_detector.get_context_for_llm()
                if struggle_ctx:
                    full_system += f"\n{struggle_ctx}"
            # Inject specialist persona
            if not local_reasoner and hasattr(self.jarvis, 'specialists'):
                try:
                    specialist = self.jarvis.specialists.select_specialist(task.text)
                    if specialist.name != "Generalist":
                        prompt_add = self.jarvis.specialists.get_prompt_injection(specialist)
                        if prompt_add:
                            full_system += f"\n\n{prompt_add}"
                        logger.info("Specialist selected: %s", specialist.name)
                except Exception:
                    pass

            # Inject self-evolution learned rules
            if not local_reasoner and hasattr(self.jarvis, 'evolver'):
                try:
                    evolved = self.jarvis.evolver.get_evolved_prompt()
                    if evolved:
                        full_system += f"\n\n[EVOLVED BEHAVIORS]\n{evolved}"
                except Exception:
                    pass

            # Inject thinking engine context — JARVIS's own reasoning
            if not local_reasoner and hasattr(self.jarvis, 'thinker'):
                try:
                    thought = self.jarvis.thinker.think(task.text)
                    if thought.api_context:
                        full_system += f"\n\n[JARVIS INTERNAL REASONING]\n{thought.api_context}"
                    if thought.thoughts:
                        monologue = " → ".join(thought.thoughts[:5])
                        full_system += f"\n[THOUGHT CHAIN] {monologue}"
                    if thought.knowledge_used:
                        full_system += f"\n[KNOWN FACTS] {'; '.join(thought.knowledge_used[:10])}"
                except Exception:
                    pass
        except Exception:
            pass

        # Inject correction context if this is a follow-up correction
        correction_ctx = task.metadata.get("correction_context")
        if correction_ctx:
            full_system += f"\n\n{correction_ctx}"

        try:
            # Filter empty messages before sending to API
            clean_msgs = [m for m in self.brain.history
                          if m.get("content") and m["content"].strip()]
            if local_reasoner and len(clean_msgs) > 8:
                clean_msgs = clean_msgs[-8:]
            reply_text, latency = self.brain._chat_with_fallback(
                messages=clean_msgs,
                system_prompt=full_system,
                max_tokens=self.brain.config.get("max_tokens", 2048),
            )

            # Try to parse as an AgentPlan (may contain a tool call)
            plan = parse_plan(reply_text)

            if plan.needs_tool and plan.tool_name:
                # Execute the tool from the plan (Executor has resilient retry)
                tool_result = self.executor.execute(plan.tool_name, plan.tool_args)
                reply = plan.spoken_reply
                if tool_result.success and tool_result.output:
                    if tool_result.output not in reply:
                        reply += f"\n\n{tool_result.output}"
                elif not tool_result.success:
                    # Record failure for future learning
                    resilient = getattr(self.jarvis, "resilient", None)
                    if resilient:
                        resilient.knowledge.record_error(
                            "ai_tool_failure", tool_result.error[:200],
                            f"plan_tool={plan.tool_name}",
                        )
                    reply += f"\n\nTried my best, but: {tool_result.error}"
            else:
                reply = plan.spoken_reply or reply_text

            return PipelineResult(success=True, reply=reply, pipeline="ai_pipeline")

        except Exception as e:
            logger.error("AI pipeline error: %s", e)
            return PipelineResult(
                success=False,
                reply=f"I had trouble processing that: {e}",
                pipeline="ai_pipeline",
            )

    # ── Multi-Step Pipeline ──────────────────────────────────────

    def _multi_pipeline(self, task: Task) -> PipelineResult:
        """
        Decompose a complex request into subtasks, execute each
        (in parallel when independent), and combine results.
        """
        subtasks = self._decompose(task.text)

        if len(subtasks) <= 1:
            # Not really multi-step — just run through AI
            return self._ai_pipeline(task)

        # Check if subtasks are independent (can run in parallel)
        types = [self._classify_single(s) for s in subtasks]
        independent = all(t == TaskType.TOOL for t in types) or len(set(types)) > 1

        if independent:
            results = self.execute_parallel(subtasks)
        else:
            # Execute sequentially
            results = []
            for sub in subtasks:
                sub_task = Task(
                    priority=task.priority, text=sub,
                    task_type=self._classify_single(sub),
                )
                sub_result = self._execute_subtask(sub_task)
                results.append(sub_result)

        combined = self.combine_results(results)
        return PipelineResult(
            success=True, reply=combined, pipeline="multi_pipeline",
        )

    def _decompose(self, text: str) -> list[str]:
        """
        Split a multi-step request into individual subtasks.
        Uses 'and', 'then', 'also' as delimiters between distinct tasks.
        """
        # Split on common multi-task delimiters
        parts = re.split(
            r'\s+(?:and\s+(?:also\s+)?|then\s+|also\s+|plus\s+)',
            text, flags=re.IGNORECASE,
        )
        # Filter out empty parts and strip whitespace
        return [p.strip() for p in parts if p.strip()]

    def _execute_subtask(self, task: Task) -> str:
        """Execute a single subtask and return the reply text."""
        if task.task_type == TaskType.SIMPLE:
            result = self._local_pipeline(task)
        elif task.task_type == TaskType.TOOL:
            result = self._tool_pipeline(task)
        else:
            result = self._ai_pipeline(task)
        return result.reply if result else "Could not process subtask."

    # ═════════════════════════════════════════════════════════════
    #  4. Result Combiner
    # ═════════════════════════════════════════════════════════════

    def combine_results(self, subtask_results: list) -> str:
        """
        Intelligently combine results from multiple subtasks.
        Structures output rather than blindly concatenating.

        Args:
            subtask_results: list of reply strings from subtasks.

        Returns:
            A structured, combined response string.
        """
        if not subtask_results:
            return "No results to report."

        if len(subtask_results) == 1:
            return subtask_results[0]

        # Filter out empty or error-only results
        valid = [r for r in subtask_results if r and r.strip()]
        if not valid:
            return "I completed the tasks but there's nothing to report."

        # If all results are short (< 100 chars), combine inline
        if all(len(r) < 100 for r in valid):
            return " | ".join(valid)

        # Otherwise, structure with numbered sections
        lines = ["Here's what I found:\n"]
        for i, result in enumerate(valid, 1):
            result_clean = result.strip()
            if len(valid) == 2:
                prefix = "First" if i == 1 else "Second"
                lines.append(f"**{prefix}:** {result_clean}\n")
            else:
                lines.append(f"{i}. {result_clean}\n")
        return "\n".join(lines)

    # ═════════════════════════════════════════════════════════════
    #  5. Feedback Loop / Post-Processing
    # ═════════════════════════════════════════════════════════════

    def post_process(self, task_type: TaskType, query: str, result: str,
                     latency: float, success: bool, pipeline: str = "unknown") -> None:
        """
        After every task, feed results back for learning.

        Updates:
          - Cognitive cache (for future fast-path)
          - Task success rates per type
          - Routing stats per pipeline
          - Learner (if available)

        Args:
            task_type:  The classified TaskType.
            query:      Original user query.
            result:     The reply text.
            latency:    Execution time in ms.
            success:    Whether the task succeeded.
            pipeline:   Which pipeline handled it.
        """
        type_key = task_type.value

        # ── Update cache (only for successful results) ───────────
        if success and result and task_type in (TaskType.SIMPLE,):
            cache_key = self._cache_key(query.lower().strip())
            with self._cache_lock:
                self._cache[cache_key] = {
                    "reply": result,
                    "hits": 0,
                    "last_used": time.time(),
                }
                # Evict oldest if over limit
                if len(self._cache) > self.CACHE_MAX:
                    oldest_key = min(
                        self._cache, key=lambda k: self._cache[k]["last_used"],
                    )
                    del self._cache[oldest_key]

        # ── Update task stats ────────────────────────────────────
        if type_key not in self._task_stats:
            self._task_stats[type_key] = {"success": 0, "fail": 0}
        if success:
            self._task_stats[type_key]["success"] += 1
        else:
            self._task_stats[type_key]["fail"] += 1

        # ── Update routing stats ─────────────────────────────────
        with self._routing_lock:
            if type_key not in self._routing_stats:
                self._routing_stats[type_key] = {}
            if pipeline not in self._routing_stats[type_key]:
                self._routing_stats[type_key][pipeline] = {
                    "successes": 0, "failures": 0, "total_latency": 0.0,
                }
            stats = self._routing_stats[type_key][pipeline]
            if success:
                stats["successes"] += 1
            else:
                stats["failures"] += 1
            stats["total_latency"] += latency

        # ── Feed to learner if available ─────────────────────────
        if hasattr(self.jarvis, "learner") and hasattr(self.jarvis.learner, "learn"):
            try:
                self.jarvis.learner.learn(query, result)
            except Exception:
                pass

        logger.debug(
            "Post-process: type=%s pipeline=%s success=%s latency=%.0fms",
            type_key, pipeline, success, latency,
        )

    # ═════════════════════════════════════════════════════════════
    #  6. Parallel Execution
    # ═════════════════════════════════════════════════════════════

    def execute_parallel(self, subtasks: list[str]) -> list[str]:
        """
        Execute independent subtasks in parallel using ThreadPoolExecutor.

        Args:
            subtasks: List of subtask text strings.

        Returns:
            List of reply strings, in the same order as input.
        """
        results = [""] * len(subtasks)
        futures = {}

        for i, sub_text in enumerate(subtasks):
            sub_type = self._classify_single(sub_text)
            sub_task = Task(
                priority=int(Priority.HIGH),
                text=sub_text,
                task_type=sub_type,
            )
            future = self._pool.submit(self._execute_subtask, sub_task)
            futures[future] = i

        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result(timeout=30)
            except Exception as e:
                results[idx] = f"Subtask failed: {e}"
                logger.error("Parallel subtask %d error: %s", idx, e)

        return results

    # ═════════════════════════════════════════════════════════════
    #  7. Adaptive Routing
    # ═════════════════════════════════════════════════════════════

    def get_optimal_route(self, text: str) -> str:
        """
        Determine the optimal pipeline for a query based on historical
        success rates and latency.

        Uses accumulated stats to pick the pipeline with the best
        success rate (ties broken by lowest average latency).

        Args:
            text: The user query (used for classification).

        Returns:
            Pipeline name string (e.g., "local_pipeline", "ai_pipeline").
        """
        task_type = self._classify_single(text)
        type_key = task_type.value

        with self._routing_lock:
            pipelines = self._routing_stats.get(type_key, {})

        if not pipelines:
            # No history — return default based on task type
            return self._default_pipeline(task_type)

        # Score each pipeline: success_rate * 1000 - avg_latency
        best_pipeline = None
        best_score = -float("inf")

        for pipe_name, stats in pipelines.items():
            total = stats["successes"] + stats["failures"]
            if total == 0:
                continue
            success_rate = stats["successes"] / total
            avg_latency = stats["total_latency"] / total if total else 0

            # Weighted score: heavily favor success rate, slightly prefer speed
            score = (success_rate * 10000) - avg_latency
            if score > best_score:
                best_score = score
                best_pipeline = pipe_name

        return best_pipeline or self._default_pipeline(task_type)

    def _default_pipeline(self, task_type: TaskType) -> str:
        """Return the default pipeline name for a task type."""
        defaults = {
            TaskType.SIMPLE:         "local_pipeline",
            TaskType.CACHED:         "local_pipeline",
            TaskType.TOOL:           "tool_pipeline",
            TaskType.REASONING:      "ai_pipeline",
            TaskType.MULTI_STEP:     "multi_pipeline",
            TaskType.RESEARCH:       "ai_pipeline",
            TaskType.CONVERSATIONAL: "ai_pipeline",
        }
        return defaults.get(task_type, "ai_pipeline")

    # ═════════════════════════════════════════════════════════════
    #  Helpers
    # ═════════════════════════════════════════════════════════════

    def _cache_key(self, text: str) -> str:
        """Generate a stable cache key from query text."""
        normalized = re.sub(r'\s+', ' ', text.lower().strip())
        return hashlib.md5(normalized.encode()).hexdigest()

    def _safe_callback(self, callback: Callable, *args) -> None:
        """
        Invoke a callback on the UI thread if available,
        otherwise call directly.
        """
        if hasattr(self.jarvis, 'root') and self.jarvis.root is not None:
            try:
                self.jarvis.root.after(0, lambda: callback(*args))
            except Exception:
                callback(*args)
        else:
            callback(*args)

    def get_stats(self) -> dict:
        """Return orchestrator statistics for diagnostics."""
        with self._routing_lock:
            routing = {
                k: {p: dict(s) for p, s in v.items()}
                for k, v in self._routing_stats.items()
            }
        return {
            "task_stats": dict(self._task_stats),
            "routing_stats": routing,
            "cache_size": len(self._cache),
            "queue_size": self._queue.qsize(),
        }

    def clear_cache(self) -> None:
        """Clear the cognitive cache."""
        with self._cache_lock:
            self._cache.clear()
        logger.info("Orchestrator cache cleared.")

    def shutdown(self) -> None:
        """Gracefully shut down the orchestrator."""
        self.stop_worker()
        self._pool.shutdown(wait=False)
        logger.info("Orchestrator shut down.")
