"""
J.A.R.V.I.S — Core Runtime Base

This module contains the core orchestration logic extracted from the legacy
Tk UI layer. It provides the JarvisRuntime base class that handles:
  - Message processing (send_message → orchestrator → reply)
  - Engine lifecycle (_start_engines, shutdown)
  - Command handling (/provider, /clear, /status, etc.)
  - Reply normalization and cognitive caching
  - Knowledge graph integration
  - Self-evolution learning

HeadlessJarvisRuntime extends this with HTTP/API-specific features.
The old ui/app.py (JarvisApp) also uses these methods via inheritance.

Architecture:
  core/runtime.py    ← brain logic (this file)
  core/headless_runtime.py ← API layer (extends runtime)
  ui/app.py          ← legacy Tk UI (extends runtime for GUI)
"""

from __future__ import annotations

import math
import re
import threading
import time
from pathlib import Path
from typing import Any

from core.config import load_config, save_config
from core.memory import MemoryBank, MemorySystem
from core.brain import Brain
from core.plugin_manager import PluginManager
from core.agent import Agent
from core.learner import UserLearner
from core.cognitive import CognitiveCore
from core.orchestrator import TaskOrchestrator, TaskType
from core.presence import PresenceEngine
from core.awareness import AwarenessEngine
from core.proactive import ProactiveEngine
from core.intent import IntentEngine
from core.modes import ModeAutoSwitcher
from core.self_modify import SelfModificationEngine
from core.resilient import ResilientExecutor
from core.intelligence import IntelligenceEngine
from core.knowledge_graph import KnowledgeGraph
from core.chain_engine import ChainEngine
from core.screen_awareness import ScreenAwareness
from core.report_engine import ReportEngine
from core.thinking import ThinkingEngine
from core.specialists import SpecialistTeam
from core.self_evolve import SelfEvolver
from core.web_research import WebResearcher
from core.screen_interact import ScreenInteract
from core.capability_registry import CapabilityRegistry
from core.state_registry import StateRegistry
from core.task_brain import TaskBrain
from core.dev_agent import DevAgent
from core.auto_repair import AutoRepairEngine
from core.agent_loop import AgentLoop
from core.execution_router import ExecutionRouter
from core.struggle_detector import StruggleDetector

try:
    from PIL import ImageGrab, Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class JarvisRuntime:
    """
    Core JARVIS runtime — pure orchestration logic, no UI framework dependency.

    This class owns:
      - All core engines (brain, orchestrator, memory, plugins, etc.)
      - Message processing pipeline (send_message → classify → orchestrate → reply)
      - Command handling (/provider, /clear, /status, etc.)
      - Reply post-processing (normalization, caching, knowledge extraction)

    Subclasses must provide:
      - self.root       — scheduler with .after(ms, callback) method
      - self.chat       — message store with add_message/remove_last_thinking
      - self.chat_input — input controller with set_enabled/get_text/clear
      - self.main_core  — core display with set_mode/set_voice_level
      - self.sidebar    — sidebar with update_stats/set_mode_display
      - self.subtitle, self.mode_label, etc. — UI state holders
    """

    def _init_engines(self):
        """Initialize all core engines. Call from subclass __init__."""
        self.config = load_config()
        self.memory = MemoryBank(self.config)
        self.mem = MemorySystem(self.config)
        self.brain = Brain(self.config)
        self.plugin_manager = PluginManager(self)

        self.agent = Agent(self)
        self.agent_mode = True
        self.learner = UserLearner(self.config)
        self.learner.on_session_start()
        self.cognitive = CognitiveCore(self.config)
        self.orchestrator = TaskOrchestrator(self)

        self.presence = PresenceEngine(self)
        self.awareness = AwarenessEngine(self)
        self.proactive = ProactiveEngine(self)
        self.intent_engine = IntentEngine()
        self.mode_switcher = ModeAutoSwitcher(self)
        self.self_modify = SelfModificationEngine(self)
        self.resilient = ResilientExecutor(self)
        self.intelligence = IntelligenceEngine()
        self.knowledge_graph = KnowledgeGraph()
        self.chain_engine = ChainEngine(self)
        self.screen_monitor = ScreenAwareness(self)
        self.report_engine = ReportEngine()
        self.thinker = ThinkingEngine(self)
        self.specialists = SpecialistTeam()
        self.evolver = SelfEvolver(self)
        self.researcher = WebResearcher(self)
        self.screen_interact = ScreenInteract(self)
        self.dev_agent = DevAgent(self)
        self.auto_repair = AutoRepairEngine(self)
        self.task_brain = TaskBrain(self)
        self.capabilities = CapabilityRegistry(self)
        self.state_registry = StateRegistry(self)

        # ── Human-like execution engines ────────────────────────
        self.execution_router = ExecutionRouter(self)
        self.struggle_detector = StruggleDetector()
        self.agent_loop = AgentLoop(self)

        self.attached_file = None
        self.session_start = time.time()
        self.voice_enabled = False
        self._processing = False
        self._active_turn: dict[str, Any] = {}

    # ─── Engine Lifecycle ───────────────────────────────────────

    def _start_engines(self):
        """Start background engines (presence, awareness, proactive, screen)."""
        self.core_3d = None  # No 3D core in headless mode

        try:
            self.presence.start()
        except Exception as e:
            print(f"Presence engine: {e}")

        try:
            self.awareness.start()
        except Exception as e:
            print(f"Awareness engine: {e}")

        try:
            self.proactive.start(self.awareness)
            self.proactive.set_notify_callback(self._on_proactive_notification)
        except Exception as e:
            print(f"Proactive engine: {e}")

        try:
            self.screen_monitor.start()
        except Exception as e:
            print(f"Screen awareness: {e}")

    def _on_proactive_notification(self, notification: dict):
        """Handle proactive engine notifications."""
        msg = notification.get("message", "")
        if msg:
            self.chat.add_message("system", f"[Proactive] {msg}")

    def shutdown(self):
        """Gracefully shut down all engines."""
        for attr in ("presence", "awareness", "proactive", "screen_monitor"):
            try:
                getattr(self, attr).stop()
            except Exception:
                pass
        try:
            voice_plugin = self.plugin_manager.get_plugin("voice")
            if voice_plugin:
                voice_plugin.disable()
        except Exception:
            pass
        try:
            self.intelligence.flush()
        except Exception:
            pass
        try:
            save_config(self.config)
        except Exception:
            pass

    # ─── Message Processing Pipeline ────────────────────────────

    def send_message(self, text: str):
        """Process one user message through the full JARVIS pipeline."""
        if not text or not text.strip():
            return

        text = self.plugin_manager.process_message(text)
        if text == "__handled__":
            return
        if not text or not text.strip():
            return

        # Track interaction
        welcome_back = self.presence.on_interaction(text)
        self.learner.on_message(text)
        self.intelligence.on_user_message(text)

        # Commands
        if text.startswith("/"):
            parts = text.split(None, 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            self.learner.on_command(cmd)
            if self.plugin_manager.handle_command(cmd, args):
                return
            self._handle_quick_cmd(text)
            return

        # Parse intent
        intent = self.intent_engine.parse(text)
        if intent.action == "interrupt":
            self._handle_interrupt()
            return

        # Mode switching
        mode_switch = self.mode_switcher.check_explicit_switch(text)
        if mode_switch:
            msg = self.mode_switcher.switch(mode_switch, manual=True)
            self.chat.add_message("system", msg)
            return

        suggested_mode = self.mode_switcher.suggest_mode(
            intent=intent,
            window_category=self.awareness.active_window.app_category,
        )
        if suggested_mode:
            self.mode_switcher.switch(suggested_mode)

        # Add to chat
        self.chat.add_message("user", text)
        if getattr(self, "core_3d", None):
            self.core_3d.add_chat("user", text)
        self.brain.add_user_message(text)
        self.brain.msg_count += 1
        self._update_stats()

        if welcome_back:
            self.chat.add_message("system", welcome_back)

        self.mem.session.add_user(text)
        self.mem.session.set_mood(intent.mood)

        self.chat_input.set_enabled(False)
        self._processing = True
        self.chat.add_message("thinking", "Processing...")
        self._core_mode("thinking")

        if self.agent_mode:
            orchestrator_context = self.brain.history[-8:] if self.brain.history else []
            request_type = self.orchestrator.classify(text, context=orchestrator_context)
            bypass_fastpaths = self.orchestrator.should_bypass_fastpaths(
                text, context=orchestrator_context
            )
            self._active_turn = {
                "text": text,
                "task_type": request_type.value,
                "bypass_fastpaths": bool(bypass_fastpaths),
                "source": "agent_mode",
                "history_needs_assistant": False,
            }
            force_orchestrator = request_type in {
                TaskType.TOOL, TaskType.MULTI_STEP, TaskType.RESEARCH,
            } or bypass_fastpaths

            self.cognitive.extract_knowledge(text, "")

            # Auto-detect prompts for evolution
            if hasattr(self, "evolver") and len(text) > 200:
                if re.search(r"(?:you are|act as|always|never|step \d|before answering)", text, re.I):
                    try:
                        evo_result = self.evolver.analyze_prompt(text)
                        if evo_result.useful_rules or evo_result.techniques_found:
                            self.root.after(0, lambda: self.chat.add_message("system",
                                f"Detected prompt — evolved: {len(evo_result.useful_rules)} rules, "
                                f"{len(evo_result.techniques_found)} techniques absorbed"))
                    except Exception:
                        pass

            # Detect correction/frustration
            _frustration_re = re.compile(
                r"\b(?:you\s+didn'?t|didn'?t\s+(?:send|type|work)|why\s+(?:are|aren'?t|can'?t|didn'?t)\s+you|"
                r"that'?s\s+not|not\s+what\s+i|try\s+again|do\s+it\s+(?:again|properly)|"
                r"you\s+(?:just|only)\s+(?:searched|opened)|but\s+(?:you|it)\s+didn'?t|"
                r"wrong\s+(?:place|box|field)|it\s+didn'?t\s+work)\b", re.I
            )
            _is_correction = bool(_frustration_re.search(text))

            # For complex multi-step tasks, use the persistent agent loop
            # This lets JARVIS keep working until the task is done
            if request_type == TaskType.MULTI_STEP and not _is_correction:
                try:
                    plan = self.agent_loop.build_plan_from_text(text)
                    if plan.steps and len(plan.steps) > 1:
                        self._active_turn["source"] = "agent_loop"
                        self.struggle_detector.set_goal(text)
                        self.agent_loop.execute_plan(
                            plan,
                            on_progress=lambda idx, msg: self.root.after(
                                0, self._on_agent_loop_progress, idx, msg
                            ),
                            on_complete=lambda p: self.root.after(
                                0, self._on_agent_loop_complete, p
                            ),
                        )
                        return
                except Exception as e:
                    import logging
                    logging.getLogger("jarvis.runtime").warning(
                        "Agent loop plan failed, falling back: %s", e
                    )
                    # Fall through to orchestrator

            if force_orchestrator:
                self._active_turn["source"] = "orchestrator"
                self.orchestrator.execute(
                    text,
                    on_reply=lambda r, l: self.root.after(0, self._on_reply, r, l),
                    on_error=lambda e: self.root.after(0, self._on_error, e),
                )
                return

            # ThinkingEngine: local reasoning
            try:
                thought = self.thinker.think(text)
                if (thought.can_answer and thought.answer and thought.confidence >= 0.6
                        and not _is_correction):
                    self._dispatch_local_reply(thought.answer, 0, request_type)
                    return
            except Exception:
                pass

            # Fallback to orchestrator
            self._active_turn["source"] = "orchestrator"
            self.orchestrator.execute(
                text,
                on_reply=lambda r, l: self.root.after(0, self._on_reply, r, l),
                on_error=lambda e: self.root.after(0, self._on_error, e),
            )

    # ─── Reply Handling ─────────────────────────────────────────

    def _dispatch_local_reply(self, reply, latency: int = 0, task_type=None):
        """Deliver a local fast-path reply."""
        turn = dict(getattr(self, "_active_turn", {}) or {})
        if task_type is not None:
            turn["task_type"] = task_type.value if hasattr(task_type, "value") else str(task_type)
        turn["source"] = "local_fastpath"
        turn["history_needs_assistant"] = True
        self._active_turn = turn
        self.root.after(0, lambda: self._on_reply(reply, latency))

    @staticmethod
    def _looks_like_task_operator_reply(reply: str) -> bool:
        """Return True for action prompts that should not be cached."""
        text = (reply or "").strip()
        if not text:
            return False
        task_like_re = re.compile(
            r"^(?:who should i|what should the message say|which app|which contact|"
            r"what do you want me to|waiting for|i searched |message sent to |"
            r"tried multiple approaches|i have the details, but|"
            r"i hit resistance while trying to|i couldn't verify|"
            r"i searched whatsapp|do you want me to retry|"
            r"could you clarify|please choose|i found \d+ matches)",
            re.IGNORECASE,
        )
        return bool(task_like_re.search(text))

    def _should_cache_cognitive_reply(self, user_msg: str, reply: str) -> bool:
        """Only cache clean conversational replies, not task traffic."""
        user_msg = (user_msg or "").strip()
        reply = (reply or "").strip()
        if not user_msg or not reply:
            return False

        turn = dict(getattr(self, "_active_turn", {}) or {})
        task_type_value = str(turn.get("task_type") or "").strip().lower()
        if task_type_value in {TaskType.TOOL.value, TaskType.MULTI_STEP.value, TaskType.RESEARCH.value}:
            return False
        if bool(turn.get("bypass_fastpaths")):
            return False
        if self.orchestrator.task_sessions.get_waiting_session():
            return False
        if self._looks_like_task_operator_reply(reply):
            return False

        try:
            context = self.brain.history[-8:-1] if len(self.brain.history) > 1 else []
            inferred_type = self.orchestrator.classify(user_msg, context=context)
            if inferred_type in {TaskType.TOOL, TaskType.MULTI_STEP, TaskType.RESEARCH}:
                return False
            if self.orchestrator.should_bypass_fastpaths(user_msg, context=context):
                return False
        except Exception:
            pass

        return True

    @staticmethod
    def _normalize_reply(reply) -> str:
        """Ensure reply is always a plain string."""
        def _strip_decorative_prefix(text: str) -> str:
            if not text:
                return text
            marker_re = re.compile(
                r"\b(it seems|excellent|you(?:'|')?re|you(?:'|')?ve|"
                r"let(?:'|')?s|right\b|absolutely|to begin|i(?:'|')?m)\b", re.I)
            fancy_prefix = re.match(
                r"^(?:[^\x00-\x7F]{1,24}|[A-Za-zÀ-ÿ]{2,24})!\s*"
                r"(?:\([^)]{1,48}\))?\s*"
                r"(?:[–—-]\s*[^\n]{0,100}?[–—-]\s*)?", text)
            if fancy_prefix:
                tail = text[fancy_prefix.end():].lstrip()
                marker_match = marker_re.search(tail)
                if marker_match:
                    return tail[marker_match.start():].lstrip(" -–—:;")
            translated_intro = re.search(
                r'That(?:\u2018|\u2019|\')?s\s+[A-Za-z]+\s+for\s+["\u201c\u201d][^"\u201c\u201d]{1,60}["\u201c\u201d]\s*[-\u2013\u2014]\s*(.+)$',
                text, re.I)
            if translated_intro:
                tail = translated_intro.group(1).lstrip()
                marker_match = marker_re.search(tail)
                if marker_match:
                    return tail[marker_match.start():].lstrip(" -–—:;")
                return tail
            if text and ord(text[0]) > 127:
                marker_match = marker_re.search(text)
                if marker_match:
                    return text[marker_match.start():].lstrip(" -–—:;")
            return text

        if isinstance(reply, str):
            text = reply.strip()
            import json as _json
            fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if fence_match:
                text = fence_match.group(1).strip()
            if text.startswith("{") and text.endswith("}"):
                try:
                    data = _json.loads(text)
                    for key in ("spoken_reply", "response", "answer", "message", "content", "text", "reply", "summary"):
                        val = data.get(key)
                        if isinstance(val, str) and val.strip():
                            text = val.strip()
                            break
                except Exception:
                    pass
            text = _strip_decorative_prefix(text)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            while lines and re.match(r"^<unused\d+>", lines[0], re.I):
                lines.pop(0)

            def _looks_like_noise_line(line: str) -> bool:
                if not line:
                    return False
                if re.match(r"^<unused\d+>", line, re.I):
                    return True
                if len(line) > 80:
                    return False
                non_ascii = sum(1 for ch in line if ord(ch) > 127)
                return (non_ascii / max(len(line), 1)) > 0.25

            if len(lines) > 1 and _looks_like_noise_line(lines[0]):
                english_tail = "\n".join(lines[1:])
                if re.search(r"[A-Za-z]{4,}", english_tail):
                    lines.pop(0)
            return "\n\n".join(lines) if lines else text

        if isinstance(reply, dict):
            for key in ("answer", "spoken_reply", "message", "content", "text", "reply", "summary"):
                val = reply.get(key)
                if isinstance(val, str) and val.strip():
                    return val
            return str(reply)
        if reply is None:
            return ""
        return str(reply)

    def _on_reply(self, reply, latency: int = 0):
        """Handle a completed reply from orchestrator or local fast-path."""
        self._processing = False
        reply = self._normalize_reply(reply)
        turn = dict(getattr(self, "_active_turn", {}) or {})
        user_msg = str(
            turn.get("text")
            or (self.brain.history[-2]["content"] if len(self.brain.history) >= 2 else "")
        ).strip()

        if turn.get("history_needs_assistant"):
            try:
                latest = self.brain.history[-1] if self.brain.history else {}
                if latest.get("role") != "assistant" or latest.get("content") != reply:
                    self.brain.add_assistant_message(reply)
                    self.brain.msg_count += 1
            except Exception:
                pass

        self.chat.remove_last_thinking()
        self.chat.add_message("assistant", reply)
        if getattr(self, "core_3d", None):
            self.core_3d.add_chat("assistant", reply)
        self.chat_input.set_enabled(True)
        self._update_stats()

        self._core_mode("speaking")
        self.animate_speaking_core(reply)
        self.subtitle.config(text="At your service")

        # Feed into memory layers
        self.mem.session.add_assistant(reply)

        try:
            if self._should_cache_cognitive_reply(user_msg, reply):
                self.cognitive.cache_store(user_msg, reply)
                self.cognitive.extract_knowledge(user_msg, reply)
        except Exception:
            pass

        try:
            self.intelligence.on_jarvis_reply(reply)
        except Exception:
            pass

        try:
            if hasattr(self, "evolver"):
                self.evolver.learn_from_interaction(user_msg, reply)
        except Exception:
            pass

        try:
            if hasattr(self, "knowledge_graph"):
                self.knowledge_graph.extract_from_text(reply, source="jarvis_reply")
                if len(self.brain.history) >= 2:
                    um = self.brain.history[-2].get("content", "")
                    if um:
                        self.knowledge_graph.extract_from_text(um, source="user_message")
        except Exception:
            pass

        try:
            si = self.plugin_manager.get_plugin("self_improve")
            if si and latency:
                si.track_slow(
                    self.brain.history[-2]["content"] if len(self.brain.history) >= 2 else "?",
                    latency,
                )
        except Exception:
            pass

        try:
            self.plugin_manager.on_response(reply)
        finally:
            self._active_turn = {}

    def _on_error(self, error: str):
        """Handle a processing error."""
        self._processing = False
        self._active_turn = {}
        self.chat.remove_last_thinking()
        err_msg = f"Ran into an issue, sir. {error}"
        self.chat.add_message("assistant", err_msg)
        if getattr(self, "core_3d", None):
            self.core_3d.add_chat("assistant", err_msg)
        self.chat_input.set_enabled(True)
        self._core_mode("alert")
        self.root.after(1800, lambda: self._core_mode("idle"))

        try:
            si = self.plugin_manager.get_plugin("self_improve")
            if si:
                query = self.brain.history[-1]["content"] if self.brain.history else "?"
                si.track_failure(query, str(error))
        except Exception:
            pass

    # ─── Agent Loop Callbacks ──────────────────────────────────

    def _on_agent_loop_progress(self, step_index: int, message: str):
        """Handle progress updates from the persistent agent loop."""
        self.chat.remove_last_thinking()
        self.chat.add_message("thinking", message)

    def _on_agent_loop_complete(self, plan):
        """Handle completion of a persistent agent loop execution."""
        from core.agent_loop import LoopStatus, StepStatus

        self._processing = False
        self.chat.remove_last_thinking()

        if plan.status == LoopStatus.COMPLETED:
            # Build a summary of what was accomplished
            succeeded = [s for s in plan.steps if s.status == StepStatus.SUCCEEDED]
            results = [s.result for s in succeeded if s.result]

            if len(succeeded) == 1:
                reply = results[0] if results else f"Done — {plan.goal}"
            elif results:
                parts = [f"**{s.description}**: {s.result}" for s in succeeded if s.result]
                reply = f"Completed: {plan.goal}\n\n" + "\n".join(parts)
            else:
                reply = f"All done, sir. {plan.goal} — completed in {len(succeeded)} steps."

            self.chat.add_message("assistant", reply)
            self._core_mode("speaking")

        elif plan.status == LoopStatus.STUCK:
            # Struggle detected — report and ask for help
            suggestion = ""
            if hasattr(self, "struggle_detector"):
                suggestion = self.struggle_detector.state.suggestion
            reply = (
                f"I'm having difficulty completing: {plan.goal}\n\n"
                f"I completed {sum(1 for s in plan.steps if s.status == StepStatus.SUCCEEDED)} "
                f"of {len(plan.steps)} steps. "
            )
            if suggestion:
                reply += f"\n\n{suggestion}"
            failed = [s for s in plan.steps if s.status == StepStatus.FAILED]
            if failed:
                reply += f"\n\nStuck on: {failed[0].description}"
                if failed[0].error:
                    reply += f" — {failed[0].error}"

            self.chat.add_message("assistant", reply)
            self._core_mode("alert")

        else:
            # Generic failure
            self.chat.add_message("assistant",
                f"I wasn't able to fully complete: {plan.goal}. "
                f"Finished {plan.total_iterations} iterations.")
            self._core_mode("alert")

        self.chat_input.set_enabled(True)
        self._active_turn = {}
        self.root.after(2000, lambda: self._core_mode("idle"))

    # ─── Core Display Sync ──────────────────────────────────────

    def _core_mode(self, mode: str):
        if hasattr(self, "main_core"):
            self.main_core.set_mode(mode)
        if getattr(self, "core_3d", None):
            self.core_3d.set_mode(mode)

    def _core_voice(self, level: float):
        if hasattr(self, "main_core"):
            self.main_core.set_voice_level(level)
        if getattr(self, "core_3d", None):
            self.core_3d.set_voice_level(level)

    def animate_speaking_core(self, text: str):
        if not hasattr(self, "main_core") and not getattr(self, "core_3d", None):
            return
        duration = max(900, min(len(text) * 38, 5000))
        steps = max(10, duration // 90)

        def step(i=0):
            if i >= steps:
                self._core_voice(0.0)
                self._core_mode("idle")
                return
            level = 0.25 + abs(math.sin(i * 0.6)) * 0.75
            self._core_voice(level)
            self.root.after(90, lambda: step(i + 1))

        step()

    def _handle_interrupt(self):
        self._processing = False
        self.chat.remove_last_thinking()
        self.chat_input.set_enabled(True)
        self.chat.add_message("assistant", "Understood. Standing by.")
        voice = self.plugin_manager.plugins.get("voice")
        if voice and hasattr(voice, "stop_speaking"):
            voice.stop_speaking()

    # ─── Command Handling ───────────────────────────────────────

    def _handle_quick_cmd(self, cmd: str):
        raw_cmd = (cmd or "").strip()
        parts = raw_cmd.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/provider":
            if args:
                result = self.brain.switch_provider(args)
                save_config(self.config)
                self.chat.add_message("system", result)
                self._update_provider_display()
            else:
                result = self.brain.switch_provider("status")
                self.chat.add_message("assistant", result)
            return

        if cmd == "/gemma":
            target = args if args else "gemma"
            if target == "fast":
                target = "gemma-fast"
            elif target == "vision":
                target = "gemma-vision"
            elif target not in ("gemma", "gemma-fast", "gemma-vision") and not target.startswith("gemma"):
                target = f"gemma:{target}"
            result = self.brain.switch_provider(target)
            save_config(self.config)
            self.chat.add_message("system", result)
            self._update_provider_display()
            return

        if cmd == "/clear":
            self.chat.clear()
            self.brain.clear_history()
            self.agent.short_term.clear()
            self.chat.add_message("system", "Chat cleared")
            return
        if cmd == "/voice":
            self.toggle_voice()
            return
        if cmd in ("/state", "/stores"):
            self.chat.add_message("assistant", self.state_registry.describe_for_user())
            return
        if cmd in ("/taskbrain", "/episodes", "/procedures"):
            self.chat.add_message("assistant", self.task_brain.describe_for_user())
            return
        if cmd.startswith("/dataset"):
            parts = cmd.split(None, 1)
            action = parts[1].strip().lower() if len(parts) > 1 else "status"
            if action in ("status", "show", "help"):
                self.chat.add_message("assistant", self.task_brain.describe_dataset_export())
            elif action == "export":
                repo_root = Path(__file__).resolve().parents[1]
                output_dir = repo_root / "training_data"
                result = self.task_brain.export_datasets(output_dir)
                self.chat.add_message("assistant",
                    "Task dataset exported\n"
                    f"- Episodes: {result['episodes']}\n"
                    f"- Planner examples: {result['planner_examples']}\n"
                    f"- Procedures: {result['procedures']}\n"
                    f"- Folder: {result['output_dir']}")
            else:
                self.chat.add_message("system", "Usage: /dataset | /dataset export")
            return
        if cmd in ("/task", "/session"):
            self.chat.add_message("assistant", self.orchestrator.task_sessions.describe_for_user())
            return
        if cmd == "/agent":
            self.agent_mode = not self.agent_mode
            status = "ON — AI agent loop active" if self.agent_mode else "OFF — direct LLM chat"
            self.chat.add_message("system", f"Agent mode: {status}")
            return
        if cmd == "/status":
            sys_status = self.awareness.get_system_status()
            session = self.presence.get_session_summary()
            cog_stats = self.cognitive.get_stats()
            self.chat.add_message("assistant",
                f"System Status\n{'=' * 40}\n{sys_status}\n\n"
                f"Session: {session['duration']} · {session['interactions']} interactions\n"
                f"State: {session['state']}\n"
                f"Knowledge: {cog_stats.get('total_knowledge', 0)} entries · "
                f"Cache: {cog_stats.get('cache_entries', 0)} ({cog_stats.get('hit_rate', 0):.0f}% hit rate)\n"
                f"Mode: {self.mode_switcher.current_mode}")
            return
        if cmd == "/scan":
            self.scan_screen()
            return

        if cmd.startswith("/evolve"):
            if hasattr(self, "evolver"):
                parts = raw_cmd.split(None, 1)
                if len(parts) > 1:
                    prompt_text = parts[1]
                    result = self.evolver.analyze_prompt(prompt_text)
                    self.chat.add_message("assistant",
                        f"Prompt Analysis Complete\n{'=' * 40}\n{result.summary}\n\n"
                        f"Techniques: {', '.join(result.techniques_found) or 'none'}\n"
                        f"Rules: {len(result.useful_rules)}\n"
                        f"Knowledge: {len(result.new_knowledge)}")
                    if result.specialist_definition and hasattr(self, "specialists"):
                        from core.specialists import Specialist
                        sd = result.specialist_definition
                        self.specialists.add_specialist(Specialist(
                            name=sd.get("name", "Custom"),
                            role=sd.get("role", "Custom specialist"),
                            identity_prompt=sd.get("identity", ""),
                            trigger_patterns=sd.get("triggers", []),
                            preferred_tools=sd.get("tools", []),
                            reasoning_rules=[],
                            knowledge_domains=sd.get("domains", []),
                        ))
                else:
                    stats = self.evolver.get_evolution_stats()
                    improvements = self.evolver.suggest_improvements()
                    self.chat.add_message("assistant",
                        f"Evolution Status\n{'=' * 40}\n"
                        f"Total: {stats.get('total_evolutions', 0)} · "
                        f"Rules: {stats.get('learned_rules', 0)} · "
                        f"Techniques: {stats.get('learned_techniques', 0)}\n"
                        f"Suggested:\n" +
                        "\n".join(f"  • {i}" for i in improvements[:5]) if improvements
                        else "  No improvements needed.")
            return

        if cmd.startswith("/research"):
            parts = raw_cmd.split(None, 1)
            if len(parts) > 1 and hasattr(self, "researcher"):
                query = parts[1].strip()
                self.chat.add_message("system", f"Researching: {query}...")
                self.chat_input.set_enabled(False)

                def _do_research():
                    try:
                        result = self.researcher.research(query, depth="deep")
                        def _show():
                            self.chat.add_message("assistant",
                                f"Research: {query}\n{'=' * 40}\n{result.summary}\n\n"
                                f"Sources: {len(result.sources)}\n"
                                + "\n".join(f"  • {s.get('title', s.get('url', '?'))}" for s in result.sources[:5]))
                            self.chat_input.set_enabled(True)
                        self.root.after(0, _show)
                    except Exception as e:
                        self.root.after(0, lambda: self.chat.add_message("system", f"Research failed: {e}"))
                        self.root.after(0, lambda: self.chat_input.set_enabled(True))

                threading.Thread(target=_do_research, daemon=True).start()
            else:
                self.chat.add_message("system", "Usage: /research <topic>")
            return

        # Default: send to orchestrator as a prompt
        prompt = cmd
        for k, v in {"/plan day": "Plan my day", "/code": "Help me write code for: ",
                      "/research": "Research: ", "/analyze": "Analyze: ",
                      "/debug": "Debug: ", "/write": "Help me write: ",
                      "/memory": "What do you remember about me?"}.items():
            if cmd.startswith(k) and v:
                prompt = v + args
                break

        if prompt != cmd:
            self.chat.add_message("user", prompt)
            self.brain.add_user_message(prompt)
            self._processing = True
            self.chat.add_message("thinking", "Processing...")
            self._core_mode("thinking")
            self.orchestrator.execute(
                prompt,
                on_reply=lambda r, l: self.root.after(0, self._on_reply, r, l),
                on_error=lambda e: self.root.after(0, self._on_error, e),
            )
        else:
            self.chat.add_message("system", f"Unknown command: {cmd}")

    # ─── Screen & Vision ────────────────────────────────────────

    def scan_screen(self):
        if not HAS_PIL:
            self.chat.add_message("system", "PIL not available for screen capture.")
            return
        self.chat.add_message("system", "Scanning screen...")
        self.chat_input.set_enabled(False)

        def _do_scan():
            try:
                screenshot = ImageGrab.grab()
                import io, base64
                buf = io.BytesIO()
                screenshot.save(buf, format="PNG")
                img_b64 = base64.b64encode(buf.getvalue()).decode()
                result = self.brain.analyze_image(img_b64, "What's on this screen? Provide a brief analysis.")
                self.root.after(0, lambda: self._scan_done(result))
            except Exception as e:
                self.root.after(0, lambda: self._scan_done(f"Scan failed: {e}"))

        threading.Thread(target=_do_scan, daemon=True).start()

    def _scan_done(self, result):
        self.chat.add_message("assistant", str(result))
        self.chat_input.set_enabled(True)

    def _has_vision_provider(self) -> bool:
        info = self.brain.get_provider_info()
        return bool(info.get("vision"))

    # ─── Utils ──────────────────────────────────────────────────

    def _format_provider_text(self):
        info = self.brain.get_provider_info()
        name = info.get("name", "Unknown")
        model = info.get("model", "unknown")
        if len(model) > 20:
            model = model[:20]
        text = f"{name} // {model}"
        if info.get("local"):
            text += " LOCAL"
        return text

    def _update_provider_display(self):
        self.provider_pill.set(value=self._format_provider_text())

    def _update_stats(self):
        task_count = len(self.config.get("tasks", []))
        self.sidebar.update_stats(
            msgs=self.brain.msg_count,
            mems=len(self.memory),
            tasks=task_count,
        )
        self.task_pill.set(value=str(task_count))

    def _get_notes(self) -> str:
        return self.config.get("notes", "")
