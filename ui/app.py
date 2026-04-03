"""
J.A.R.V.I.S — Main Application
Clean, minimal UI with smooth animations.
"""

import os
import re
import io
import time
import base64
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

from core.config import load_config, save_config
from core.memory import MemoryBank, MemorySystem
from core.brain import Brain, MODES, MODE_LABELS
from core.plugin_manager import PluginManager
from core.agent import Agent
from core.learner import UserLearner
from core.cognitive import CognitiveCore
from core.orchestrator import TaskOrchestrator
from core.presence import PresenceEngine
from core.awareness import AwarenessEngine
from core.proactive import ProactiveEngine
from core.intent import IntentEngine
from core.modes import ModeAutoSwitcher
from core.self_modify import SelfModificationEngine
from core.resilient import ResilientExecutor
from ui.themes import COLORS, FONTS
from ui.components import ArcReactor, StatusDot
from ui.chat import ChatDisplay, ChatInput
from ui.sidebar import Sidebar

try:
    from PIL import ImageGrab, Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import keyboard as kb_module
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False


class JarvisApp:
    """Main JARVIS application — clean and animated."""

    def __init__(self):
        # ── Core ──
        self.config = load_config()
        self.memory = MemoryBank(self.config)
        self.mem = MemorySystem(self.config)   # 4-layer memory
        self.brain = Brain(self.config)
        self.plugin_manager = PluginManager(self)

        # ── Agent + Learner + Cognitive Core + Orchestrator ──
        self.agent = Agent(self)
        self.agent_mode = True
        self.learner = UserLearner(self.config)
        self.learner.on_session_start()
        self.cognitive = CognitiveCore(self.config)
        self.orchestrator = TaskOrchestrator(self)

        # ── Movie JARVIS Engines ──
        self.presence = PresenceEngine(self)
        self.awareness = AwarenessEngine(self)
        self.proactive = ProactiveEngine(self)
        self.intent_engine = IntentEngine()
        self.mode_switcher = ModeAutoSwitcher(self)
        self.self_modify = SelfModificationEngine(self)
        self.resilient = ResilientExecutor(self)

        # ── State ──
        self.attached_file = None
        self.session_start = time.time()
        self.voice_enabled = False
        self._processing = False   # For interruption support

        # ── Window ──
        self.root = tk.Tk()
        self.root.title("J.A.R.V.I.S — Stark Industries")
        self.root.configure(bg=COLORS["bg"])
        self.root.geometry("1100x700")
        self.root.minsize(800, 500)

        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        self._build_ui()
        self._setup_hotkeys()
        self._load_plugins()
        self._start_engines()
        self._tick()
        self.root.after(300, self._boot_animation)

    # ══════════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════════

    def _build_ui(self):
        # Top bar — minimal
        self._build_topbar()

        # Main content area
        body = tk.Frame(self.root, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Chat area (takes most space)
        chat_area = tk.Frame(body, bg=COLORS["bg"])
        chat_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_chat(chat_area)

        # Sidebar — clean right panel
        self.sidebar = Sidebar(body, self)
        self.sidebar.frame.pack(side=tk.RIGHT, fill=tk.Y)

        # Status bar — minimal
        self._build_statusbar()

        # Load data
        self._refresh_all()

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=COLORS["bg2"], height=56)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        # Left: Arc reactor + title
        left = tk.Frame(bar, bg=COLORS["bg2"])
        left.pack(side=tk.LEFT, padx=16, fill=tk.Y)

        self.arc = ArcReactor(left, 40)
        self.arc.pack(side=tk.LEFT, padx=(0, 12), pady=8)

        title_block = tk.Frame(left, bg=COLORS["bg2"])
        title_block.pack(side=tk.LEFT, fill=tk.Y, pady=8)

        tk.Label(
            title_block, text="J.A.R.V.I.S",
            font=("Segoe UI Semibold", 16), fg=COLORS["primary"],
            bg=COLORS["bg2"],
        ).pack(anchor="w")
        self.subtitle = tk.Label(
            title_block, text="Personal AI System",
            font=FONTS["label"], fg=COLORS["text_dim"],
            bg=COLORS["bg2"],
        )
        self.subtitle.pack(anchor="w")

        # Right: controls
        right = tk.Frame(bar, bg=COLORS["bg2"])
        right.pack(side=tk.RIGHT, padx=16, fill=tk.Y)

        # Online status
        self.status_dot = StatusDot(right, "ONLINE", "green")
        self.status_dot.pack(side=tk.RIGHT, padx=(12, 0), pady=18)

        # Voice toggle — clean icon button
        self.voice_btn = tk.Button(
            right, text="🎤 Off", font=FONTS["btn"],
            fg=COLORS["text_dim"], bg=COLORS["bg2"],
            activeforeground=COLORS["primary"],
            activebackground=COLORS["bg2"],
            bd=0, relief=tk.FLAT, cursor="hand2",
            command=self.toggle_voice,
        )
        self.voice_btn.pack(side=tk.RIGHT, padx=8, pady=16)
        self.voice_btn.bind("<Enter>",
            lambda e: self.voice_btn.config(fg=COLORS["primary"]))
        self.voice_btn.bind("<Leave>",
            lambda e: self.voice_btn.config(
                fg=COLORS["green"] if self.voice_enabled else COLORS["text_dim"]))

        # Sidebar toggle
        self.sidebar_btn = tk.Button(
            right, text="☰", font=("Segoe UI", 14),
            fg=COLORS["text_dim"], bg=COLORS["bg2"],
            activeforeground=COLORS["primary"],
            activebackground=COLORS["bg2"],
            bd=0, relief=tk.FLAT, cursor="hand2",
            command=lambda: self.sidebar.toggle(),
        )
        self.sidebar_btn.pack(side=tk.RIGHT, padx=4, pady=14)
        self.sidebar_btn.bind("<Enter>",
            lambda e: self.sidebar_btn.config(fg=COLORS["primary"]))
        self.sidebar_btn.bind("<Leave>",
            lambda e: self.sidebar_btn.config(fg=COLORS["text_dim"]))

        # Clock
        self.clock_label = tk.Label(
            right, text="00:00", font=FONTS["clock"],
            fg=COLORS["text_dim"], bg=COLORS["bg2"],
        )
        self.clock_label.pack(side=tk.RIGHT, padx=12, pady=16)

        # Mode display
        self.mode_label = tk.Label(
            right, text="GENERAL", font=FONTS["btn"],
            fg=COLORS["primary_dim"], bg=COLORS["bg2"],
        )
        self.mode_label.pack(side=tk.RIGHT, padx=8, pady=18)

    def _build_chat(self, parent):
        # Chat display
        self.chat = ChatDisplay(parent)
        self.chat.pack(fill=tk.BOTH, expand=True)

        # Quick commands — subtle bar
        cmd_bar = tk.Frame(parent, bg=COLORS["bg"], height=32)
        cmd_bar.pack(fill=tk.X, padx=16, pady=(4, 0))

        cmds = ["/weather", "/news", "/crypto", "/wiki",
                "/status", "/remind", "/find", "/scan",
                "/improve", "/clear"]
        for cmd in cmds:
            btn = tk.Button(
                cmd_bar, text=cmd, font=FONTS["label_md"],
                fg=COLORS["text_muted"], bg=COLORS["bg"],
                activeforeground=COLORS["primary"],
                activebackground=COLORS["bg"],
                bd=0, relief=tk.FLAT, cursor="hand2",
                padx=6, pady=2,
                command=lambda c=cmd: self._handle_quick_cmd(c),
            )
            btn.pack(side=tk.LEFT, padx=1)
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg=COLORS["primary_dim"]))
            btn.bind("<Leave>", lambda e, b=btn: b.config(fg=COLORS["text_muted"]))

        # Scan screen button — subtle
        self.scan_btn = tk.Button(
            cmd_bar, text="📸 Scan Screen", font=FONTS["label_md"],
            fg=COLORS["text_muted"], bg=COLORS["bg"],
            activeforeground=COLORS["green"],
            activebackground=COLORS["bg"],
            bd=0, relief=tk.FLAT, cursor="hand2",
            padx=8, pady=2,
            command=self.scan_screen,
        )
        self.scan_btn.pack(side=tk.RIGHT, padx=4)
        self.scan_btn.bind("<Enter>",
            lambda e: self.scan_btn.config(fg=COLORS["green"]))
        self.scan_btn.bind("<Leave>",
            lambda e: self.scan_btn.config(fg=COLORS["text_muted"]))

        # Chat input
        self.chat_input = ChatInput(parent, self.send_message, self.toggle_listening)
        self.chat_input.pack(fill=tk.X, padx=16, pady=(6, 12))

    def _build_statusbar(self):
        sb = tk.Frame(self.root, bg=COLORS["bg2"], height=24)
        sb.pack(fill=tk.X)
        sb.pack_propagate(False)

        # Left items
        for text, color_key in [("STARK INDUSTRIES", "text_dim"),
                                 ("ALL SYSTEMS NOMINAL", "green")]:
            tk.Label(
                sb, text=f"  {text}", font=FONTS["label"],
                fg=COLORS.get(color_key), bg=COLORS["bg2"],
            ).pack(side=tk.LEFT, padx=2)

        # Provider + Model display
        info = self.brain.get_provider_info()
        model_name = info["model"].split("-20")[0] if "-20" in info["model"] else info["model"]
        provider_text = f"{info['name']} · {model_name}"
        if info.get("local"):
            provider_text += " (local)"

        self.provider_label = tk.Label(
            sb, text=f"  ●  {provider_text}", font=FONTS["label"],
            fg=COLORS["primary_dim"], bg=COLORS["bg2"],
        )
        self.provider_label.pack(side=tk.LEFT, padx=2)

        # Right: session time
        self.session_label = tk.Label(
            sb, text="Session: 00:00", font=FONTS["label"],
            fg=COLORS["text_dim"], bg=COLORS["bg2"],
        )
        self.session_label.pack(side=tk.RIGHT, padx=8)

    # ══════════════════════════════════════════════════════════════
    # ENGINE STARTUP
    # ══════════════════════════════════════════════════════════════

    def _start_engines(self):
        """Start all movie-JARVIS engines."""
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

    def _on_proactive_notification(self, notification: dict):
        """Handle a proactive notification from the awareness/proactive engines."""
        msg_type = notification.get("type", "info")
        icon = notification.get("icon", "")
        message = notification.get("message", "")

        def _show():
            if msg_type == "alert":
                self.chat.add_message("system", f"{icon}  ALERT: {message}")
                # Speak alerts if voice is on
                voice = self.plugin_manager.plugins.get("voice")
                if voice and self.voice_enabled:
                    voice.speak(message)
            elif msg_type == "warning":
                self.chat.add_message("system", f"{icon}  {message}")
            elif msg_type == "suggestion":
                self.chat.add_message("system", f"{icon}  {message}")
            else:
                self.chat.add_message("system", f"{icon}  {message}")

        self.root.after(0, _show)

    # ══════════════════════════════════════════════════════════════
    # BOOT ANIMATION
    # ══════════════════════════════════════════════════════════════

    def _boot_animation(self):
        """Cinematic boot sequence — movie JARVIS style."""
        msgs = [
            ("system", "Initializing J.A.R.V.I.S..."),
            ("system", "Neural core online"),
        ]

        # Engines status
        engine_count = 0
        for name in ["presence", "awareness", "proactive"]:
            if hasattr(self, name):
                engine_count += 1
        msgs.append(("system", f"Awareness engines: {engine_count} active"))

        # Plugin count (not listing all names — too noisy)
        plugin_count = len(self.plugin_manager.plugins)
        if plugin_count:
            msgs.append(("system", f"Subsystems loaded: {plugin_count}"))

        # Memory status
        mems = len(self.memory)
        cog_stats = self.cognitive.get_stats()
        knowledge = cog_stats.get("total_knowledge", 0)
        if mems or knowledge:
            msgs.append(("system",
                f"Memory bank: {mems} records · Knowledge: {knowledge} entries"))

        # Provider status
        info = self.brain.get_provider_info()
        available = info.get("name", "Unknown")
        msgs.append(("system", f"AI provider: {available}"))

        # Resilient engine
        if hasattr(self, "resilient"):
            err_stats = self.resilient.get_error_stats()
            known = err_stats.get("known_fixes", 0)
            if known:
                msgs.append(("system", f"Resilient engine: {known} known fixes loaded"))
            else:
                msgs.append(("system", "Resilient engine: online"))

        msgs.append(("system", "All systems nominal"))

        def show_msg(index=0):
            if index < len(msgs):
                role, text = msgs[index]
                self.chat.add_message(role, text)
                self.root.after(350, lambda: show_msg(index + 1))
            else:
                self.root.after(400, self._show_greeting)

        show_msg()

    def _show_greeting(self):
        # Check if ANY provider is available (not just Anthropic)
        has_provider = False
        try:
            if self.brain.provider.is_available():
                has_provider = True
            elif self.brain.fallback_enabled:
                fallbacks = self.brain._get_fallback_providers()
                has_provider = len(fallbacks) > 0
        except Exception:
            pass

        if not has_provider:
            self.chat.add_message("assistant",
                "Welcome, sir. No AI provider configured yet.\n"
                "Free options: Gemini (aistudio.google.dev) or Groq (console.groq.com).\n"
                "Add your key to ~/.jarvis_config.json"
            )
        else:
            # Smart contextual greeting from presence engine
            greeting = self.presence.get_boot_greeting()
            self.chat.add_message("assistant", greeting)

    # ══════════════════════════════════════════════════════════════
    # PLUGINS
    # ══════════════════════════════════════════════════════════════

    def _load_plugins(self):
        try:
            from plugins.voice.voice_plugin import VoicePlugin
            self.plugin_manager.load_plugin(VoicePlugin)
        except Exception as e:
            print(f"Voice plugin: {e}")

        try:
            from plugins.automation.auto_plugin import AutomationPlugin
            self.plugin_manager.load_plugin(AutomationPlugin)
        except Exception as e:
            print(f"Automation plugin: {e}")

        try:
            from plugins.web_intel.web_plugin import WebIntelPlugin
            self.plugin_manager.load_plugin(WebIntelPlugin)
        except Exception as e:
            print(f"Web Intel plugin: {e}")

        try:
            from plugins.cyber.cyber_plugin import CyberPlugin
            self.plugin_manager.load_plugin(CyberPlugin)
        except Exception as e:
            print(f"Cyber plugin: {e}")

        try:
            from plugins.code_assist.code_plugin import CodeAssistPlugin
            self.plugin_manager.load_plugin(CodeAssistPlugin)
        except Exception as e:
            print(f"Code Assist plugin: {e}")

        try:
            from plugins.scheduler.scheduler_plugin import SchedulerPlugin
            self.plugin_manager.load_plugin(SchedulerPlugin)
        except Exception as e:
            print(f"Scheduler plugin: {e}")

        try:
            from plugins.file_manager.file_manager_plugin import FileManagerPlugin
            self.plugin_manager.load_plugin(FileManagerPlugin)
        except Exception as e:
            print(f"File Manager plugin: {e}")

        try:
            from plugins.smart_home.smart_home_plugin import SmartHomePlugin
            self.plugin_manager.load_plugin(SmartHomePlugin)
        except Exception as e:
            print(f"Smart Home plugin: {e}")

        try:
            from plugins.email.email_plugin import EmailPlugin
            self.plugin_manager.load_plugin(EmailPlugin)
        except Exception as e:
            print(f"Email plugin: {e}")

        try:
            from plugins.self_improve.self_improve_plugin import SelfImprovePlugin
            self.plugin_manager.load_plugin(SelfImprovePlugin)
        except Exception as e:
            print(f"Self-improve plugin: {e}")

    # ══════════════════════════════════════════════════════════════
    # MESSAGING
    # ══════════════════════════════════════════════════════════════

    def send_message(self, text: str):
        text = self.plugin_manager.process_message(text)

        # Plugin handled it entirely
        if text == "__handled__":
            return

        # ── Track interaction with presence engine ──
        welcome_back = self.presence.on_interaction(text)
        self.learner.on_message(text)

        # Commands — always handle directly
        if text.startswith("/"):
            parts = text.split(None, 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            self.learner.on_command(cmd)
            if self.plugin_manager.handle_command(cmd, args):
                return
            self._handle_quick_cmd(cmd)
            return

        # ── Parse intent — understand what they MEAN ──
        intent = self.intent_engine.parse(text)

        # Handle interruptions immediately
        if intent.action == "interrupt":
            self._handle_interrupt()
            return

        # Check for explicit mode switch
        mode_switch = self.mode_switcher.check_explicit_switch(text)
        if mode_switch:
            msg = self.mode_switcher.switch(mode_switch, manual=True)
            self.chat.add_message("system", msg)
            return

        # Auto-suggest mode based on intent
        suggested_mode = self.mode_switcher.suggest_mode(
            intent=intent,
            window_category=self.awareness.active_window.app_category,
        )
        if suggested_mode:
            msg = self.mode_switcher.switch(suggested_mode)
            self.chat.add_message("system", msg)

        # Show user message in chat
        self.chat.add_message("user", text)
        self.brain.add_user_message(text)
        self.brain.msg_count += 1
        self._update_stats()

        # Show welcome back if returning from idle
        if welcome_back:
            self.chat.add_message("system", welcome_back)

        # Update session memory
        self.mem.session.add_user(text)
        self.mem.session.set_mood(intent.mood)

        self.chat_input.set_enabled(False)
        self._processing = True
        self.chat.add_message("thinking", "Processing...")

        if self.agent_mode:
            # ── Smart Pipeline ── intent → cognitive → orchestrator → learn
            # Extract knowledge from user message
            self.cognitive.extract_knowledge(text, "")

            # Instant responses for greetings (no AI needed)
            if intent.category == "greeting" and intent.confidence > 0.7:
                greeting = self.presence.get_time_greeting() + " How can I help?"
                self.root.after(0, lambda: self._on_reply(greeting, 0))
                return

            # System status — local only
            if intent.category == "system" and intent.action == "status":
                status = self.awareness.get_system_status()
                self.root.after(0, lambda: self._on_reply(status, 0))
                return

            # Try local reasoning first (zero API cost)
            local_answer = self.cognitive.local_reason(text)
            if local_answer:
                self.root.after(0, lambda: self._on_reply(local_answer, 0))
                return

            # Try cache lookup (returns dict with "answer" key or None)
            cached = self.cognitive.cache_lookup(text)
            if cached:
                cached_answer = cached.get("answer", str(cached)) if isinstance(cached, dict) else str(cached)
                self.root.after(0, lambda: self._on_reply(cached_answer, 0))
                return

            # Track as unhandled (no fast-path hit)
            try:
                si = self.plugin_manager.get_plugin("self_improve")
                if si:
                    si.track_unhandled(text)
            except Exception:
                pass

            # Full orchestrator pipeline
            self.orchestrator.execute(
                text,
                on_reply=lambda r, l: self.root.after(0, self._on_reply, r, l),
                on_error=lambda e: self.root.after(0, self._on_error, e),
            )
        else:
            # ── Legacy mode ── direct LLM chat (fallback)
            system_prompt = self.brain.build_system_prompt(
                memory_context=self.memory.get_context_string(),
                notes=self._get_notes(),
            )
            self.brain.chat(
                system_prompt,
                callback=lambda r, l: self.root.after(0, self._on_reply, r, l),
                error_callback=lambda e: self.root.after(0, self._on_error, e),
            )

    @staticmethod
    def _normalize_reply(reply) -> str:
        """Ensure reply is always a plain string — never a dict or None."""
        if isinstance(reply, str):
            return reply
        if isinstance(reply, dict):
            # cache_lookup returns {"question":..., "answer":...}
            # planner returns {"spoken_reply":..., ...}
            for key in ("answer", "spoken_reply", "message", "content", "text", "reply"):
                val = reply.get(key)
                if isinstance(val, str) and val.strip():
                    return val
            return str(reply)
        if reply is None:
            return ""
        return str(reply)

    def _on_reply(self, reply, latency: int = 0):
        self._processing = False
        reply = self._normalize_reply(reply)

        self.chat.remove_last_thinking()
        self.chat.add_message("assistant", reply)
        self.chat_input.set_enabled(True)
        self._update_stats()

        # Update subtitle to show active state
        self.subtitle.config(text="At your service")

        # Feed into 4-layer memory
        self.mem.session.add_assistant(reply)

        # Feed response back to cognitive core for learning
        try:
            user_msg = self.brain.history[-2]["content"] if len(self.brain.history) >= 2 else ""
            self.cognitive.cache_store(user_msg, reply)
            self.cognitive.extract_knowledge(user_msg, reply)
        except Exception:
            pass

        # Self-improvement tracking: slow queries
        try:
            si = self.plugin_manager.get_plugin("self_improve")
            if si and latency:
                si.track_slow(
                    self.brain.history[-2]["content"] if len(self.brain.history) >= 2 else "?",
                    latency,
                )
        except Exception:
            pass

        # Speak the response if voice is on
        self.plugin_manager.on_response(reply)

    def _on_error(self, error: str):
        self._processing = False
        self.chat.remove_last_thinking()
        self.chat.add_message("assistant", f"Ran into an issue, sir. {error}")
        self.chat_input.set_enabled(True)

        # Self-improvement tracking: failures
        try:
            si = self.plugin_manager.get_plugin("self_improve")
            if si:
                query = self.brain.history[-1]["content"] if self.brain.history else "?"
                si.track_failure(query, str(error))
        except Exception:
            pass

    def _handle_interrupt(self):
        """Handle 'stop', 'wait', 'cancel' — movie JARVIS style."""
        self._processing = False
        self.chat.remove_last_thinking()
        self.chat_input.set_enabled(True)
        self.chat.add_message("assistant", "Understood. Standing by.")

        # Stop voice if speaking
        voice = self.plugin_manager.plugins.get("voice")
        if voice and hasattr(voice, 'stop_speaking'):
            voice.stop_speaking()

    # ══════════════════════════════════════════════════════════════
    # COMMANDS
    # ══════════════════════════════════════════════════════════════

    def _handle_quick_cmd(self, cmd: str):
        # Provider switching: /provider ollama
        if cmd.startswith("/provider"):
            parts = cmd.split(None, 1)
            if len(parts) > 1:
                result = self.brain.switch_provider(parts[1])
                from core.config import save_config
                save_config(self.config)
                self.chat.add_message("system", result)
                self._update_provider_display()
            else:
                # Show full provider dashboard
                result = self.brain.switch_provider("status")
                self.chat.add_message("assistant", result)
            return

        cmd_map = {
            "/plan day": "Plan my day and help me prioritize my tasks",
            "/code": "Help me write code for: ",
            "/research": "Research and summarize: ",
            "/analyze": "Analyze this: ",
            "/debug": "Debug this error: ",
            "/write": "Help me write: ",
            "/memory": "What do you remember about me?",
            "/clear": None,
            "/voice": None,
            "/prioritize tasks": "Prioritize these tasks:\n"
                + "\n".join(t["text"] for t in self.config.get("tasks", [])),
        }
        if cmd == "/clear":
            self.chat.clear()
            self.brain.clear_history()
            self.agent.short_term.clear()
            self.chat.add_message("system", "Chat cleared")
            return
        if cmd == "/voice":
            self.toggle_voice()
            return
        if cmd == "/agent":
            self.agent_mode = not self.agent_mode
            status = "ON — AI agent loop active" if self.agent_mode else "OFF — direct LLM chat"
            self.chat.add_message("system", f"Agent mode: {status}")
            return
        if cmd == "/status":
            # Movie JARVIS system status
            sys_status = self.awareness.get_system_status()
            session = self.presence.get_session_summary()
            cog_stats = self.cognitive.get_stats()
            self.chat.add_message("assistant",
                f"System Status\n"
                f"{'=' * 40}\n"
                f"{sys_status}\n\n"
                f"Session: {session['duration']} · {session['interactions']} interactions\n"
                f"State: {session['state']}\n"
                f"Knowledge: {cog_stats.get('total_knowledge', 0)} entries · "
                f"Cache: {cog_stats.get('cache_entries', 0)} ({cog_stats.get('hit_rate', 0):.0f}% hit rate)\n"
                f"Mode: {self.mode_switcher.current_mode}"
            )
            return

        if cmd == "/scan":
            self.scan_screen()
            return

        if cmd == "/brain":
            stats = self.cognitive.get_stats()
            knowledge = self.cognitive.export_knowledge()
            self.chat.add_message("assistant",
                f"Cognitive Core Status\n"
                f"{'=' * 40}\n"
                f"Knowledge entries: {stats.get('total_knowledge', 0)}\n"
                f"Cache entries: {stats.get('cache_entries', 0)}\n"
                f"Cache hits: {stats.get('cache_hits', 0)}\n"
                f"Cache misses: {stats.get('cache_misses', 0)}\n"
                f"Hit rate: {stats.get('hit_rate', 0):.1f}%\n"
                f"Skills learned: {stats.get('total_skills', 0)}\n"
                f"Interactions: {stats.get('interactions', 0)}\n"
                f"\n{knowledge[:1500] if knowledge else 'No knowledge learned yet.'}"
            )
            return
        if cmd == "/forget":
            parts = cmd.split(None, 1)
            if len(parts) > 1:
                count = self.cognitive.forget(parts[1])
                self.chat.add_message("system", f"Forgot {count} entries about '{parts[1]}'")
            else:
                self.chat.add_message("system", "Usage: /forget <topic>")
            return

        # Route plugin commands through plugin manager
        if self.plugin_manager.handle_command(cmd, ""):
            return

        text = cmd_map.get(cmd, cmd)
        if text:
            self.chat_input.set_text(text)

    # ══════════════════════════════════════════════════════════════
    # MODE
    # ══════════════════════════════════════════════════════════════

    def set_mode(self, mode: str):
        msg = self.mode_switcher.switch(mode, manual=True)
        self.chat.add_message("system", msg)

    # ══════════════════════════════════════════════════════════════
    # VOICE
    # ══════════════════════════════════════════════════════════════

    def toggle_voice(self):
        voice_plugin = self.plugin_manager.plugins.get("voice")
        if voice_plugin:
            self.voice_enabled = not self.voice_enabled
            if self.voice_enabled:
                voice_plugin.enable()
                self.voice_btn.config(text="🎤 On", fg=COLORS["green"])
                self.chat.add_message("system", "Voice activated")
                self.sidebar.update_stats(voice="ON")
            else:
                voice_plugin.disable()
                self.voice_btn.config(text="🎤 Off", fg=COLORS["text_dim"])
                self.chat.add_message("system", "Voice deactivated")
                self.sidebar.update_stats(voice="OFF")
        else:
            self.chat.add_message("system",
                "Voice not available. Install: pip install pyttsx3 SpeechRecognition pyaudio")

    def toggle_listening(self):
        """Push-to-talk: Ctrl+Shift+V or mic button. Pauses wake loop to avoid mic conflict."""
        voice_plugin = self.plugin_manager.plugins.get("voice")
        if not voice_plugin:
            self.chat.add_message("system", "Voice plugin not loaded")
            return

        # Auto-enable TTS so response is spoken back
        if not self.voice_enabled:
            self.voice_enabled = True
            voice_plugin.is_enabled = True
            self.voice_btn.config(text="🎤 On", fg=COLORS["green"])

        # Pause wake word loop so it doesn't steal the mic
        was_wake_active = voice_plugin.wake_word_active
        if was_wake_active:
            voice_plugin.wake_word_active = False
            import time
            time.sleep(0.3)  # Let current listen cycle finish

        self.chat.add_message("voice", "Listening... (speak now)")
        voice_plugin.speak("Listening.")

        def _on_done(text):
            self.root.after(0, lambda: self._on_voice_input(text))
            # Resume wake loop after processing
            if was_wake_active:
                voice_plugin._start_wake_word()

        def _on_fail(err):
            self.root.after(0, lambda: self.chat.add_message("system", f"Voice: {err}"))
            # Resume wake loop even on failure
            if was_wake_active:
                voice_plugin._start_wake_word()

        voice_plugin.listen_once(
            callback=_on_done,
            error_callback=_on_fail,
            timeout=10,
            phrase_limit=20,
        )

    def _on_voice_input(self, text: str):
        self.chat.add_message("voice", f'Heard: "{text}"')
        self.send_message(text)

    # ══════════════════════════════════════════════════════════════
    # SCREEN SCAN
    # ══════════════════════════════════════════════════════════════

    def scan_screen(self):
        if not HAS_PIL:
            self.chat.add_message("system", "Install: pip install pillow")
            return
        if not self.brain.api_key:
            self.chat.add_message("system", "API key required")
            return

        self.scan_btn.config(text="📸 Scanning...", fg=COLORS["gold"])
        self.chat.add_message("system", "Capturing screen...")

        import threading
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        try:
            self.root.after(0, self.root.iconify)
            time.sleep(0.8)
            screenshot = ImageGrab.grab()
            self.root.after(0, self.root.deiconify)

            screenshot.thumbnail((1280, 720), Image.LANCZOS)
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            from core.brain import MODES
            screen_prompt = MODES["Screen"]
            mem_ctx = self.memory.get_context_string()
            if mem_ctx:
                screen_prompt += f"\n\n{mem_ctx}"

            self.brain.chat_with_image(
                screen_prompt, img_b64,
                "Analyze my screen. What am I working on? How can you help?",
                callback=lambda r, l: self.root.after(0, self._scan_done, r),
                error_callback=lambda e: self.root.after(0, self._scan_done, f"Error: {e}"),
            )
        except Exception as e:
            self.root.after(0, self._scan_done, f"Error: {e}")

    def _scan_done(self, reply: str):
        self.scan_btn.config(text="📸 Scan Screen", fg=COLORS["text_muted"])
        self.chat.add_message("assistant", reply)
        self.brain.msg_count += 1
        self._update_stats()

    # ══════════════════════════════════════════════════════════════
    # FILE OPS
    # ══════════════════════════════════════════════════════════════

    def open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("All", "*.*"), ("Text", "*.txt"), ("Python", "*.py"),
                       ("JS", "*.js"), ("HTML", "*.html"), ("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.attached_file = {
                "path": path, "content": content,
                "name": os.path.basename(path),
            }
            self.sidebar.set_file_status(
                f"✓ {os.path.basename(path)}", "green")
            self.chat.add_message("system",
                f"Loaded: {os.path.basename(path)}")
        except Exception as e:
            self.sidebar.set_file_status(f"Error: {e}", "red")

    def analyze_file(self):
        if not self.attached_file:
            self.open_file()
            if not self.attached_file:
                return
        self.send_message(
            f"[File: {self.attached_file['name']}]\n\n"
            f"{self.attached_file['content'][:8000]}\n\n---\n"
            "Analyze this file."
        )

    # ══════════════════════════════════════════════════════════════
    # TASKS
    # ══════════════════════════════════════════════════════════════

    def add_task(self):
        text = self.sidebar.get_task_input()
        if not text:
            return
        tasks = self.config.get("tasks", [])
        tasks.append({"text": text, "done": False})
        self.config["tasks"] = tasks
        save_config(self.config)
        self.sidebar.clear_task_input()
        self._refresh_all()

    def toggle_task(self):
        idx = self.sidebar.get_selected_task_index()
        if idx is None:
            return
        tasks = self.config.get("tasks", [])
        if idx < len(tasks):
            tasks[idx]["done"] = not tasks[idx]["done"]
            self.config["tasks"] = tasks
            save_config(self.config)
            self._refresh_all()

    # ══════════════════════════════════════════════════════════════
    # MEMORY
    # ══════════════════════════════════════════════════════════════

    def clear_memory(self):
        if messagebox.askyesno("Clear Memory", "Wipe all memories?"):
            self.memory.clear()
            self._refresh_all()
            self.chat.add_message("system", "Memory cleared")

    # ══════════════════════════════════════════════════════════════
    # NOTES (from sidebar, if we add notepad later)
    # ══════════════════════════════════════════════════════════════

    def _get_notes(self) -> str:
        return self.config.get("notes", "")

    def save_notes(self):
        save_config(self.config)

    def notes_to_jarvis(self):
        notes = self._get_notes()
        if notes:
            self.send_message(f"Review these notes:\n\n{notes}")

    def export_notes(self):
        pass  # Simplified — can add later

    # ══════════════════════════════════════════════════════════════
    # SETTINGS
    # ══════════════════════════════════════════════════════════════

    def show_settings(self):
        win = tk.Toplevel(self.root)
        win.title("JARVIS — Settings")
        win.configure(bg=COLORS["bg"])
        win.geometry("450x280")
        win.resizable(False, False)

        tk.Label(win, text="Settings", font=FONTS["title_md"],
                 fg=COLORS["primary"], bg=COLORS["bg"]).pack(pady=(24, 16))

        # API Key
        tk.Label(win, text="Anthropic API Key", font=FONTS["btn"],
                 fg=COLORS["text_dim"], bg=COLORS["bg"]).pack(anchor="w", padx=32)

        key_var = tk.StringVar(value=self.config.get("api_key", ""))
        key_entry = tk.Entry(
            win, textvariable=key_var, width=50, show="●",
            font=FONTS["mono_sm"], bg=COLORS["card"], fg=COLORS["text"],
            insertbackground=COLORS["primary"], bd=0,
            highlightthickness=1, highlightcolor=COLORS["primary_dim"],
            highlightbackground=COLORS["border"],
        )
        key_entry.pack(padx=32, pady=8, ipady=6, fill=tk.X)

        tk.Label(win, text="Get key at console.anthropic.com",
                 font=FONTS["label"], fg=COLORS["text_dim"],
                 bg=COLORS["bg"]).pack(anchor="w", padx=32)

        def save():
            self.config["api_key"] = key_var.get().strip()
            save_config(self.config)
            win.destroy()
            self.chat.add_message("system", "Settings saved")

        tk.Button(
            win, text="Save", font=FONTS["btn_lg"],
            fg=COLORS["primary"], bg=COLORS["card"],
            activeforeground=COLORS["white"],
            activebackground=COLORS["card"],
            bd=0, relief=tk.FLAT, padx=24, pady=8,
            cursor="hand2", command=save,
        ).pack(pady=20)

    # ══════════════════════════════════════════════════════════════
    # STATS & TICK
    # ══════════════════════════════════════════════════════════════

    def _update_provider_display(self):
        """Update status bar with current provider info."""
        info = self.brain.get_provider_info()
        model_name = info["model"].split("-20")[0] if "-20" in info["model"] else info["model"]
        text = f"  ●  {info['name']} · {model_name}"
        if info.get("local"):
            text += " (local)"
        self.provider_label.config(text=text)

    def _refresh_all(self):
        self.sidebar.refresh_memories(self.memory.memories)
        self.sidebar.refresh_tasks(self.config.get("tasks", []))
        self._update_stats()

    def _update_stats(self):
        self.sidebar.update_stats(
            msgs=self.brain.msg_count,
            mems=len(self.memory),
            tasks=len(self.config.get("tasks", [])),
        )

    def _tick(self):
        now = datetime.now()
        self.clock_label.config(text=now.strftime("%H:%M"))

        elapsed = int(time.time() - self.session_start)
        m, s = divmod(elapsed, 60)
        h, m = divmod(m, 60)
        if h:
            self.session_label.config(text=f"Session: {h}:{m:02d}:{s:02d}")
        else:
            self.session_label.config(text=f"Session: {m:02d}:{s:02d}")
        self.sidebar.update_stats(time=f"{m:02d}:{s:02d}")

        # Update presence state in subtitle
        try:
            state_text = self.presence.get_status_text()
            if not self._processing:
                health = self.awareness.system_health
                if health.cpu_percent > 0:
                    self.subtitle.config(
                        text=f"{state_text} · {health.status_text}")
                else:
                    self.subtitle.config(text=state_text)

                # Update status dot color based on system health
                alert = health.alert_level
                if alert == "red":
                    self.status_dot.label.config(text="WARNING")
                    self.status_dot.color = COLORS["red"]
                elif alert == "yellow":
                    self.status_dot.label.config(text="ELEVATED")
                    self.status_dot.color = COLORS["gold"]
                else:
                    self.status_dot.label.config(text="ONLINE")
                    self.status_dot.color = COLORS["green"]
        except Exception:
            pass

        self.root.after(1000, self._tick)

    # ══════════════════════════════════════════════════════════════
    # HOTKEYS
    # ══════════════════════════════════════════════════════════════

    def _setup_hotkeys(self):
        if not HAS_KEYBOARD:
            return
        try:
            kb_module.add_hotkey("ctrl+shift+j", self._toggle_window)
            kb_module.add_hotkey("ctrl+shift+s", self.scan_screen)
            kb_module.add_hotkey("ctrl+shift+v", self.toggle_listening)
        except Exception:
            pass

    def _toggle_window(self):
        if self.root.state() == "iconic":
            self.root.after(0, self.root.deiconify)
        else:
            self.root.after(0, self.root.iconify)

    # ══════════════════════════════════════════════════════════════
    # RUN
    # ══════════════════════════════════════════════════════════════

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        # Save work context for "continue where I left off"
        try:
            last_msg = self.mem.session.last_user_message
            if last_msg:
                self.mem.tasks.save_context(
                    context=last_msg,
                    topic=self.mem.session._active_topic,
                )
        except Exception:
            pass

        self.save_notes()

        # Shutdown engines
        try:
            self.presence.stop()
            self.awareness.stop()
            self.proactive.stop()
        except Exception:
            pass

        for name in list(self.plugin_manager.plugins.keys()):
            self.plugin_manager.unload_plugin(name)
        if HAS_KEYBOARD:
            try:
                kb_module.unhook_all()
            except Exception:
                pass
        self.root.destroy()
