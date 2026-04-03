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
    r"no |nah |nope|forget it|skip|ignore)\b",
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
_TOOL_PATTERNS = [
    (re.compile(r"\b(?:open|launch|start|run)\s+(\w[\w\s]*)", re.I), "open_app"),
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
    (re.compile(r"\b(?:search|google|look\s*up)\b", re.I), "web_search"),
    # Cybersecurity
    (re.compile(r"\b(?:url|link)\s*scan\b", re.I), "url_scan"),
    (re.compile(r"\bfile\s*scan\b", re.I), "file_scan"),
    (re.compile(r"\bsecurity\s*audit\b", re.I), "security_audit"),
    (re.compile(r"\bphishing\b", re.I), "phishing_detect"),
    (re.compile(r"\bport\s*scan\b", re.I), "port_scan"),
    (re.compile(r"\bwifi\s*scan\b", re.I), "wifi_scan"),
    (re.compile(r"\bnet(?:work)?\s*scan\b", re.I), "net_scan"),
    # Email
    (re.compile(r"\b(?:check|read)\s*(?:my\s+)?(?:inbox|email|mail)\b", re.I), "check_inbox"),
    (re.compile(r"\bsend\s*(?:an?\s+)?(?:email|mail)\b", re.I), "send_email"),
    # Smart home
    (re.compile(r"\blights?\b", re.I), "control_lights"),
    (re.compile(r"\bthermostat\b", re.I), "set_thermostat"),
    (re.compile(r"\bscene\b", re.I), "activate_scene"),
    (re.compile(r"\bdevices?\b", re.I), "list_devices"),
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

        # ── Negation / cancellation — always treat as conversational ─
        if _NEGATION_RE.search(msg_lower):
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

        # ── Conversational follow-up ─────────────────────────────
        if context and len(context) >= 1:
            if _FOLLOWUP_PATTERNS.search(msg_lower):
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

        task_type = self.classify(text, context)
        priority  = self._determine_priority(text, task_type)

        task = Task(
            priority=int(priority),
            text=text,
            task_type=task_type,
            on_reply=on_reply,
            on_error=on_error,
        )

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
                if optimal == "local_pipeline":
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
            result = PipelineResult(
                success=False, reply=f"I encountered an error: {e}",
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
            reply = (
                "I am J.A.R.V.I.S — Just A Rather Very Intelligent System. "
                "I can help you with tasks, answer questions, control your system, "
                "and much more."
            )
            return PipelineResult(success=True, reply=reply, pipeline="local_pipeline")

        return PipelineResult(success=False, reply="", pipeline="local_pipeline")

    # ── Tool Pipeline ────────────────────────────────────────────

    def _tool_pipeline(self, task: Task) -> PipelineResult:
        """
        Route to a tool: detect which tool, build args, check safety,
        execute via Executor, and format response.
        """
        msg = task.text.strip()
        msg_lower = msg.lower().strip()

        # Detect the tool from patterns
        tool_name = None
        match_obj = None
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
        tool_args = self._build_tool_args(tool_name, msg, match_obj)

        # Safety check
        from core.safety import needs_confirmation, describe_risk
        if needs_confirmation(tool_name, tool_args):
            risk_msg = describe_risk(tool_name, tool_args)
            # Request confirmation through UI
            confirmed = self._request_confirmation_sync(risk_msg)
            if not confirmed:
                return PipelineResult(
                    success=True,
                    reply="Understood, sir. Action cancelled.",
                    pipeline="tool_pipeline",
                )

        # Execute
        result = self.executor.execute(tool_name, tool_args)

        if result.success:
            reply = result.output or f"Done — {tool_name} executed successfully."
        else:
            reply = f"There was an issue: {result.error}"

        return PipelineResult(
            success=result.success, reply=reply, pipeline="tool_pipeline",
        )

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
            m = re.search(r"(?:search|google|look\s*up)\s+(?:for\s+)?(.+)", msg_lower)
            query = m.group(1).strip() if m else text
            return {"query": query}

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

        # Default: pass text as generic arg
        return {}

    def _request_confirmation_sync(self, risk_msg: str) -> bool:
        """
        Request user confirmation synchronously.
        Uses the UI thread if available, otherwise assumes yes.
        """
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
        if mem_context:
            full_system += f"\n\n{mem_context}"
        if stm_context:
            full_system += f"\n\n{stm_context}"
        if learner_context:
            full_system += f"\n\n{learner_context}"
        if notes:
            full_system += f"\n\n[CURRENT NOTES]\n{notes}"

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
        except Exception:
            pass

        try:
            reply_text, latency = self.brain._chat_with_fallback(
                messages=self.brain.history,
                system_prompt=full_system,
                max_tokens=self.brain.config.get("max_tokens", 2048),
            )

            # Try to parse as an AgentPlan (may contain a tool call)
            plan = parse_plan(reply_text)

            if plan.needs_tool and plan.tool_name:
                # Execute the tool from the plan
                tool_result = self.executor.execute(plan.tool_name, plan.tool_args)
                reply = plan.spoken_reply
                if tool_result.success and tool_result.output:
                    if tool_result.output not in reply:
                        reply += f"\n\n{tool_result.output}"
                elif not tool_result.success:
                    reply += f"\n\nHowever, there was an issue: {tool_result.error}"
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
        if success and result and task_type not in (TaskType.CONVERSATIONAL,):
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
