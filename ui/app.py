"""
J.A.R.V.I.S — Main Application
Clean, minimal UI with smooth animations.
"""

import os
import re
import io
import math
import time
import base64
from pathlib import Path
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
from ui.themes import COLORS, FONTS
from ui.components import StatusDot, StatusPill
from ui.jarvis_core_v2 import JarvisCoreV2
from ui.chat import ChatDisplay, ChatInput
from ui.sidebar import Sidebar

# GPU 3D core — optional, falls back to V2 canvas
try:
    from ui.jarvis_core_3d import JarvisCore3D
    HAS_3D_CORE = True
except ImportError:
    HAS_3D_CORE = False

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

        # ── State ──
        self.attached_file = None
        self.session_start = time.time()
        self.voice_enabled = False
        self._processing = False   # For interruption support
        self._active_turn = {}

        # ── Window ──
        self.root = tk.Tk()
        self.root.title("J.A.R.V.I.S — Stark Industries")
        self.root.configure(bg=COLORS["bg"])
        ui_cfg = self.config.get("ui", {})
        self.root.geometry(str(ui_cfg.get("window_geometry", "1280x820")))
        self.root.minsize(
            int(ui_cfg.get("min_width", 960)),
            int(ui_cfg.get("min_height", 620)),
        )

        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        self._build_ui()
        self._setup_hotkeys()
        self._load_plugins()
        self.capabilities.refresh()
        self._start_engines()
        self._tick()
        self.root.after(300, self._boot_animation)

    # ══════════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════════

    def _build_ui(self):
        shell = tk.Frame(
            self.root,
            bg=COLORS["shell"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["border"],
        )
        shell.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self._build_topbar(shell)

        body = tk.Frame(shell, bg=COLORS["shell"])
        body.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        chat_area = tk.Frame(body, bg=COLORS["shell"])
        chat_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_chat(chat_area)

        self.sidebar = Sidebar(body, self)
        self.sidebar.frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.sidebar.set_mode_display(self.config.get("mode", "General"))

        self._build_statusbar(shell)

        self._refresh_all()

    def _build_topbar(self, parent):
        bar = tk.Frame(parent, bg=COLORS["bg2"], height=58)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        left = tk.Frame(bar, bg=COLORS["bg2"])
        left.pack(side=tk.LEFT, padx=16, fill=tk.Y)

        tk.Label(
            left, text="JARVIS OPERATOR",
            font=FONTS["title_md"], fg=COLORS["text"],
            bg=COLORS["bg2"],
        ).pack(anchor="w", pady=(9, 0))
        tk.Label(
            left, text="Desktop intelligence shell",
            font=FONTS["label"], fg=COLORS["text_dim"],
            bg=COLORS["bg2"],
        ).pack(anchor="w")

        center = tk.Frame(bar, bg=COLORS["bg2"])
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(
            center, text="JARVIS OS // OPERATOR MODE",
            font=FONTS["label_md"], fg=COLORS["text_muted"],
            bg=COLORS["bg2"],
        ).pack(expand=True)

        right = tk.Frame(bar, bg=COLORS["bg2"])
        right.pack(side=tk.RIGHT, padx=16, fill=tk.Y)

        self.status_dot = StatusDot(right, "ONLINE", "green", bg_color=COLORS["bg2"])
        self.status_dot.pack(side=tk.RIGHT, padx=(12, 0), pady=19)

        self.voice_btn = tk.Button(
            right, text="MIC OFF", font=FONTS["btn"],
            fg=COLORS["text_dim"], bg=COLORS["bg2"],
            activeforeground=COLORS["primary"],
            activebackground=COLORS["bg2"],
            bd=0, relief=tk.FLAT, cursor="hand2",
            command=self.toggle_voice,
        )
        self.voice_btn.pack(side=tk.RIGHT, padx=8, pady=18)
        self.voice_btn.bind("<Enter>",
            lambda e: self.voice_btn.config(fg=COLORS["primary"]))
        self.voice_btn.bind("<Leave>",
            lambda e: self.voice_btn.config(
                fg=COLORS["green"] if self.voice_enabled else COLORS["text_dim"]))

        self.sidebar_btn = tk.Button(
            right, text="STACK OPEN", font=FONTS["btn"],
            fg=COLORS["text_dim"], bg=COLORS["bg2"],
            activeforeground=COLORS["primary"],
            activebackground=COLORS["bg2"],
            bd=0, relief=tk.FLAT, cursor="hand2",
            command=self.toggle_sidebar,
        )
        self.sidebar_btn.pack(side=tk.RIGHT, padx=4, pady=18)
        self.sidebar_btn.bind("<Enter>",
            lambda e: self.sidebar_btn.config(fg=COLORS["primary"]))
        self.sidebar_btn.bind("<Leave>",
            lambda e: self.sidebar_btn.config(fg=COLORS["text_dim"]))

        self.clock_label = tk.Label(
            right, text="00:00", font=FONTS["clock"],
            fg=COLORS["text_dim"], bg=COLORS["bg2"],
        )
        self.clock_label.pack(side=tk.RIGHT, padx=12, pady=18)

        self.mode_label = tk.Label(
            right, text="GENERAL", font=FONTS["btn"],
            fg=COLORS["primary"], bg=COLORS["bg2"],
        )
        self.mode_label.pack(side=tk.RIGHT, padx=8, pady=18)

    def _build_chat(self, parent):
        hero_shell = tk.Frame(
            parent,
            bg=COLORS["border_soft"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["border"],
        )
        self.hero_shell = hero_shell
        hero_shell.pack(fill=tk.X, padx=(12, 8), pady=(12, 8))

        hero_panel = tk.Frame(hero_shell, bg=COLORS["card"])
        hero_panel.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        hero_header = tk.Frame(hero_panel, bg=COLORS["card"], height=34)
        hero_header.pack(fill=tk.X, padx=16, pady=(12, 0))
        hero_header.pack_propagate(False)

        tk.Label(
            hero_header, text="COGNITIVE CORE",
            font=FONTS["label"], fg=COLORS["text_dim"],
            bg=COLORS["card"],
        ).pack(side=tk.LEFT)

        self.subtitle = tk.Label(
            hero_header, text="Personal AI System",
            font=FONTS["msg_xs"], fg=COLORS["text_muted"],
            bg=COLORS["card"],
        )
        self.subtitle.pack(side=tk.RIGHT)

        core_panel = tk.Frame(hero_panel, bg=COLORS["card"])
        core_panel.pack(fill=tk.X, padx=8, pady=(6, 10))
        self.main_core = JarvisCoreV2(core_panel, width=560, height=300)
        self.main_core.pack()

        cmd_shell = tk.Frame(
            parent,
            bg=COLORS["border_soft"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["border"],
        )
        self.cmd_shell = cmd_shell
        cmd_bar = tk.Frame(cmd_shell, bg=COLORS["card"], height=34)
        cmd_bar.pack(fill=tk.X, padx=1, pady=1)

        cmds = ["/weather", "/news", "/crypto", "/wiki",
                "/status", "/remind", "/scan", "/knowledge",
                "/chain", "/report", "/clear"]
        for cmd in cmds:
            btn = tk.Button(
                cmd_bar, text=cmd, font=FONTS["label_md"],
                fg=COLORS["text_muted"], bg=COLORS["card"],
                activeforeground=COLORS["primary"],
                activebackground=COLORS["card"],
                bd=0, relief=tk.FLAT, cursor="hand2",
                padx=8, pady=5,
                command=lambda c=cmd: self._handle_quick_cmd(c),
            )
            btn.pack(side=tk.LEFT, padx=1)
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg=COLORS["primary_dim"]))
            btn.bind("<Leave>", lambda e, b=btn: b.config(fg=COLORS["text_muted"]))

        self.scan_btn = tk.Button(
            cmd_bar, text="📸 Scan Screen", font=FONTS["label_md"],
            fg=COLORS["text_muted"], bg=COLORS["card"],
            activeforeground=COLORS["green"],
            activebackground=COLORS["card"],
            bd=0, relief=tk.FLAT, cursor="hand2",
            padx=10, pady=5,
            command=self.scan_screen,
        )
        self.scan_btn.pack(side=tk.RIGHT, padx=4)
        self.scan_btn.bind("<Enter>",
            lambda e: self.scan_btn.config(fg=COLORS["green"]))
        self.scan_btn.bind("<Leave>",
            lambda e: self.scan_btn.config(fg=COLORS["text_muted"]))

        clip_shell = tk.Frame(
            parent,
            bg=COLORS["border_soft"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["border"],
        )
        self.clipboard_shell = clip_shell
        clip_bar = tk.Frame(clip_shell, bg=COLORS["card"], height=34)
        clip_bar.pack(fill=tk.X, padx=1, pady=1)
        clip_bar.pack_propagate(False)

        self.clipboard_label = tk.Label(
            clip_bar,
            text="CLIPBOARD READY",
            font=FONTS["label"],
            fg=COLORS["accent"],
            bg=COLORS["card"],
        )
        self.clipboard_label.pack(side=tk.LEFT, padx=(12, 10))

        self.clipboard_preview = tk.Label(
            clip_bar,
            text="",
            font=FONTS["msg_xs"],
            fg=COLORS["text_dim"],
            bg=COLORS["card"],
            anchor="w",
        )
        self.clipboard_preview.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.clipboard_insert_btn = tk.Button(
            clip_bar, text="INSERT", font=FONTS["btn"],
            fg=COLORS["accent"], bg=COLORS["card"],
            activeforeground=COLORS["white"],
            activebackground=COLORS["card"],
            bd=0, relief=tk.FLAT, cursor="hand2",
            command=self.paste_clipboard_to_input,
        )
        self.clipboard_insert_btn.pack(side=tk.RIGHT, padx=8, pady=4)

        self.clipboard_send_btn = tk.Button(
            clip_bar, text="SEND", font=FONTS["btn"],
            fg=COLORS["primary"], bg=COLORS["card"],
            activeforeground=COLORS["white"],
            activebackground=COLORS["card"],
            bd=0, relief=tk.FLAT, cursor="hand2",
            command=lambda: self.paste_clipboard_to_input(send_now=True),
        )
        self.clipboard_send_btn.pack(side=tk.RIGHT, padx=4, pady=4)

        self.chat_input = ChatInput(parent, self.send_message, self.toggle_listening, self.paste_clipboard_to_input)
        self.chat_input.pack(side=tk.BOTTOM, fill=tk.X, padx=(12, 8), pady=(0, 12))
        self._clipboard_preview_text = ""
        self._refresh_clipboard_preview(force=True)

        cmd_shell.pack(side=tk.BOTTOM, fill=tk.X, padx=(12, 8), pady=(0, 8))

        self.chat = ChatDisplay(parent)
        self.chat.pack(fill=tk.BOTH, expand=True, padx=(12, 8), pady=(0, 8))

    def _build_statusbar(self, parent):
        sb = tk.Frame(parent, bg=COLORS["bg2"], height=40)
        sb.pack(fill=tk.X)
        sb.pack_propagate(False)

        left = tk.Frame(sb, bg=COLORS["bg2"])
        left.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)

        right = tk.Frame(sb, bg=COLORS["bg2"])
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=5)

        self.system_pill = StatusPill(left, "SYSTEM", "NOMINAL", "green", bg_color=COLORS["bg2"])
        self.system_pill.pack(side=tk.LEFT, padx=(0, 8))

        self.provider_pill = StatusPill(left, "ACTIVE AI", self._format_provider_text(), "primary", bg_color=COLORS["bg2"])
        self.provider_pill.pack(side=tk.LEFT, padx=(0, 8))

        self.mode_pill = StatusPill(left, "MODE", self.config.get("mode", "General").upper(), "accent", bg_color=COLORS["bg2"])
        self.mode_pill.pack(side=tk.LEFT, padx=(0, 8))

        self.voice_pill = StatusPill(right, "VOICE", "MIC OFF", "text_dim", bg_color=COLORS["bg2"])
        self.voice_pill.pack(side=tk.RIGHT)

        self.session_pill = StatusPill(right, "SESSION", "00:00", "text_dim", bg_color=COLORS["bg2"])
        self.session_pill.pack(side=tk.RIGHT, padx=(0, 8))

        self.task_pill = StatusPill(right, "TASKS", str(len(self.config.get("tasks", []))), "accent", bg_color=COLORS["bg2"])
        self.task_pill.pack(side=tk.RIGHT, padx=(0, 8))

    # ══════════════════════════════════════════════════════════════
    # ENGINE STARTUP
    # ══════════════════════════════════════════════════════════════

    def _start_engines(self):
        """Start all movie-JARVIS engines."""
        # GPU 3D Core — launches in a separate window alongside Tkinter
        self.core_3d = None
        ui_cfg = self.config.get("ui", {})
        if HAS_3D_CORE and ui_cfg.get("external_core_window", False):
            try:
                self.core_3d = JarvisCore3D(
                    width=800, height=600,
                    title="J.A.R.V.I.S — Core",
                )
                self.core_3d._jarvis = self  # connect mic/input to app
                self.core_3d.start()  # runs in background thread
                print("[JARVIS] GPU 3D core launched")
            except Exception as e:
                print(f"[JARVIS] 3D core failed (using V2 fallback): {e}")
                self.core_3d = None

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
        # Core: thinking mode during boot (both V2 + 3D)
        self._core_mode("thinking")

        msgs = [
            ("system", "Initializing J.A.R.V.I.S..."),
            ("system", "Neural core online"),
        ]

        # Subsystem count — one clean line
        plugin_count = len(self.plugin_manager.plugins)
        engine_count = sum(1 for n in ["presence", "awareness", "proactive"] if hasattr(self, n))
        msgs.append(("system", f"Systems: {plugin_count} subsystems · {engine_count} engines"))

        # Memory — one clean line
        mems = len(self.memory)
        knowledge = self.cognitive.get_stats().get("total_knowledge", 0)
        mem_parts = []
        if mems:
            mem_parts.append(f"{mems} memories")
        if knowledge:
            mem_parts.append(f"{knowledge} knowledge")
        if mem_parts:
            msgs.append(("system", f"Memory: {' · '.join(mem_parts)}"))

        # Provider — one clean line
        info = self.brain.get_provider_info()
        msgs.append(("system", f"AI: {info.get('name', 'Unknown')}"))

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
                "Free cloud options: Gemini (aistudio.google.dev) or Groq (console.groq.com).\n"
                "Local option: install Ollama, pull Gemma with `ollama pull gemma3:4b`, then use `/provider gemma`.\n"
                "Add keys or local settings in ~/.jarvis_config.json"
            )
        else:
            # Smart contextual greeting from presence engine
            greeting = self.presence.get_boot_greeting()

            # Add morning briefing from intelligence engine
            try:
                if hasattr(self, 'intelligence'):
                    briefing = self.intelligence.get_morning_briefing()
                    if briefing:
                        greeting += f"\n\n{briefing}"
            except Exception:
                pass

            self.chat.add_message("assistant", greeting)

        # Core: boot done, relax to idle
        self._core_mode("idle")

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

        try:
            from plugins.conversation_memory.conversation_memory_plugin import ConversationMemoryPlugin
            self.plugin_manager.load_plugin(ConversationMemoryPlugin)
        except Exception as e:
            print(f"Conversation Memory plugin: {e}")

        try:
            from plugins.web_automation.web_automation_plugin import WebAutomationPlugin
            self.plugin_manager.load_plugin(WebAutomationPlugin)
        except Exception as e:
            print(f"Web Automation plugin: {e}")

        try:
            from plugins.pentest.pentest_plugin import PentestPlugin
            self.plugin_manager.load_plugin(PentestPlugin)
        except Exception as e:
            print(f"Pentest plugin: {e}")

        try:
            from plugins.messaging.messaging_plugin import MessagingPlugin
            self.plugin_manager.load_plugin(MessagingPlugin)
        except Exception as e:
            print(f"Messaging plugin: {e}")

    # ══════════════════════════════════════════════════════════════
    # MESSAGING
    # ══════════════════════════════════════════════════════════════

    def send_message(self, text: str):
        if not text or not text.strip():
            return  # Never process empty messages

        text = self.plugin_manager.process_message(text)

        # Plugin handled it entirely
        if text == "__handled__":
            return

        if not text or not text.strip():
            return  # Plugin returned empty

        # ── Track interaction with presence engine ──
        welcome_back = self.presence.on_interaction(text)
        self.learner.on_message(text)

        # ── Intelligence engine — mood, feedback, patterns ──
        mood = self.intelligence.on_user_message(text)

        # Commands — always handle directly
        if text.startswith("/"):
            parts = text.split(None, 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            self.learner.on_command(cmd)
            if self.plugin_manager.handle_command(cmd, args):
                return
            self._handle_quick_cmd(text)
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

        # Auto-suggest mode based on intent (silent — no chat spam)
        suggested_mode = self.mode_switcher.suggest_mode(
            intent=intent,
            window_category=self.awareness.active_window.app_category,
        )
        if suggested_mode:
            self.mode_switcher.switch(suggested_mode)
            # Mode switches are shown only in the top-bar label, not chat

        # Show user message in chat
        self.chat.add_message("user", text)
        if getattr(self, "core_3d", None):
            self.core_3d.add_chat("user", text)
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

        # Core: thinking mode (both V2 + 3D)
        self._core_mode("thinking")

        if self.agent_mode:
            orchestrator_context = self.brain.history[-8:] if self.brain.history else []
            request_type = self.orchestrator.classify(
                text,
                context=orchestrator_context,
            )
            bypass_fastpaths = self.orchestrator.should_bypass_fastpaths(
                text,
                context=orchestrator_context,
            )
            self._active_turn = {
                "text": text,
                "task_type": request_type.value,
                "bypass_fastpaths": bool(bypass_fastpaths),
                "source": "agent_mode",
                "history_needs_assistant": False,
            }
            force_orchestrator = request_type in {
                TaskType.TOOL,
                TaskType.MULTI_STEP,
                TaskType.RESEARCH,
            } or bypass_fastpaths
            # ── JARVIS THINKS FIRST ── think → reason → then API only if needed
            # Extract knowledge from user message
            self.cognitive.extract_knowledge(text, "")

            # ── Auto-detect prompts pasted for evolution ──
            if hasattr(self, 'evolver') and len(text) > 200:
                # Long text with prompt-like patterns → analyze for evolution
                import re as _re
                if _re.search(r"(?:you are|act as|always|never|step \d|before answering)", text, _re.I):
                    try:
                        evo_result = self.evolver.analyze_prompt(text)
                        if evo_result.useful_rules or evo_result.techniques_found:
                            self.root.after(0, lambda: self.chat.add_message("system",
                                f"Detected prompt — evolved: {len(evo_result.useful_rules)} rules, "
                                f"{len(evo_result.techniques_found)} techniques absorbed"))
                    except Exception:
                        pass

            # ── Detect correction/frustration — skip local fast-path ──
            import re as _re
            _frustration_re = _re.compile(
                r"\b(?:you\s+didn'?t|didn'?t\s+(?:send|type|work)|why\s+(?:are|aren'?t|can'?t|didn'?t)\s+you|"
                r"that'?s\s+not|not\s+what\s+i|try\s+again|do\s+it\s+(?:again|properly)|"
                r"you\s+(?:just|only)\s+(?:searched|opened)|but\s+(?:you|it)\s+didn'?t|"
                r"wrong\s+(?:place|box|field)|it\s+didn'?t\s+work)\b", _re.I
            )
            _is_correction = bool(_frustration_re.search(text))

            if force_orchestrator:
                self._active_turn["source"] = "orchestrator"
                self.orchestrator.execute(
                    text,
                    on_reply=lambda r, l: self.root.after(0, self._on_reply, r, l),
                    on_error=lambda e: self.root.after(0, self._on_error, e),
                )
                return

            # ── ThinkingEngine: JARVIS reasons locally before anything else ──
            # BUT skip local answers for corrections — they need full orchestrator context
            try:
                thought = self.thinker.think(text)

                # If JARVIS can answer locally — but NOT if user is correcting a failed action
                if (thought.can_answer and thought.answer and thought.confidence >= 0.6
                        and not _is_correction):
                    self._dispatch_local_reply(thought.answer, 0, request_type)
                    return
            except Exception as e:
                thought = None
                import logging
                logging.getLogger("jarvis").debug("Thinking engine: %s", e)

            # Instant responses for greetings (no AI needed)
            # BUT: only if it's a PURE greeting, not mid-conversation speech
            # "Jarvis open WhatsApp" starts with "jarvis" but isn't a greeting
            is_pure_greeting = (
                intent.category == "greeting"
                and intent.confidence > 0.7
                and len(text.split()) <= 5  # real greetings are short
                and not intent.is_followup
                and not _is_correction
                and self.brain.msg_count < 2  # first interaction of session
            )
            if is_pure_greeting:
                greeting = self.presence.get_time_greeting() + " How can I help?"
                self._dispatch_local_reply(greeting, 0, TaskType.SIMPLE)
                return

            # System status — local only
            if intent.category == "system" and intent.action == "status":
                status = self.awareness.get_system_status()
                self._dispatch_local_reply(status, 0, TaskType.SIMPLE)
                return

            # Try local reasoning first (zero API cost)
            local_answer = self.cognitive.local_reason(text)
            if local_answer:
                self._dispatch_local_reply(local_answer, 0, request_type)
                return

            # Try cache lookup (returns dict with "answer" key or None)
            cached = self.cognitive.cache_lookup(text)
            if cached:
                cached_answer = cached.get("answer", str(cached)) if isinstance(cached, dict) else str(cached)
                self._dispatch_local_reply(cached_answer, 0, request_type)
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
            self._active_turn = {
                "text": text,
                "task_type": TaskType.REASONING.value,
                "bypass_fastpaths": False,
                "source": "legacy_brain",
                "history_needs_assistant": False,
            }
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

    def _dispatch_local_reply(self, reply, latency: int = 0, task_type: TaskType | None = None):
        """Deliver a local fast-path reply while keeping turn state consistent."""
        turn = dict(getattr(self, "_active_turn", {}) or {})
        if task_type is not None:
            turn["task_type"] = task_type.value if isinstance(task_type, TaskType) else str(task_type)
        turn["source"] = "local_fastpath"
        turn["history_needs_assistant"] = True
        self._active_turn = turn
        self.root.after(0, lambda: self._on_reply(reply, latency))

    @staticmethod
    def _looks_like_task_operator_reply(reply: str) -> bool:
        """Return True for action prompts/results that should not become general chat cache."""
        text = (reply or "").strip()
        if not text:
            return False
        task_like_re = re.compile(
            r"^(?:who should i|what should the message say|which app|which contact|"
            r"what do you want me to|waiting for|i searched |message sent to |"
            r"tried multiple approaches|i have the details, but|"
            r"i hit resistance while trying to|"
            r"i couldn't verify|"
            r"i searched whatsapp|"
            r"do you want me to retry|"
            r"could you clarify|"
            r"please choose|"
            r"i found \d+ matches)",
            re.IGNORECASE,
        )
        return bool(task_like_re.search(text))

    def _should_cache_cognitive_reply(self, user_msg: str, reply: str) -> bool:
        """Only cache clean conversational replies, not operator/task traffic."""
        user_msg = (user_msg or "").strip()
        reply = (reply or "").strip()
        if not user_msg or not reply:
            return False

        turn = dict(getattr(self, "_active_turn", {}) or {})
        task_type_value = str(turn.get("task_type") or "").strip().lower()
        bypass_fastpaths = bool(turn.get("bypass_fastpaths"))
        if task_type_value in {
            TaskType.TOOL.value,
            TaskType.MULTI_STEP.value,
            TaskType.RESEARCH.value,
        }:
            return False
        if bypass_fastpaths:
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
        """Ensure reply is always a plain string — never a dict or None."""
        def _strip_decorative_prefix(text: str) -> str:
            if not text:
                return text

            marker_re = re.compile(
                r"\b(it seems|excellent|you(?:'|’)?re|you(?:'|’)?ve|"
                r"let(?:'|’)?s|right\b|absolutely|to begin|i(?:'|’)?m)\b",
                re.I,
            )
            fancy_prefix = re.match(
                r"^(?:[^\x00-\x7F]{1,24}|[A-Za-zÀ-ÿ]{2,24})!\s*"
                r"(?:\([^)]{1,48}\))?\s*"
                r"(?:[–—-]\s*[^\n]{0,100}?[–—-]\s*)?",
                text,
            )
            if fancy_prefix:
                tail = text[fancy_prefix.end():].lstrip()
                marker_match = marker_re.search(tail)
                if marker_match:
                    return tail[marker_match.start():].lstrip(" -–—:;")

            translated_intro = re.search(
                r"That(?:'|’)?s\s+[A-Za-z]+\s+for\s+[\"“][^\"”]{1,60}[\"”]\s*[-–—]\s*(.+)$",
                text,
                re.I,
            )
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
            fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if fence_match:
                text = fence_match.group(1).strip()
            if text.startswith("{") and text.endswith("}"):
                try:
                    import json
                    data = json.loads(text)
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
            # cache_lookup returns {"question":..., "answer":...}
            # planner returns {"spoken_reply":..., ...}
            for key in ("answer", "spoken_reply", "message", "content", "text", "reply", "summary"):
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

        # Core: stop thinking, enter speaking mode, then animate pulse
        self._core_mode("speaking")
        self.animate_speaking_core(reply)

        # Update subtitle to show active state
        self.subtitle.config(text="At your service")

        # Feed into 4-layer memory
        self.mem.session.add_assistant(reply)

        # Feed response back to cognitive core for learning
        try:
            if self._should_cache_cognitive_reply(user_msg, reply):
                self.cognitive.cache_store(user_msg, reply)
                self.cognitive.extract_knowledge(user_msg, reply)
        except Exception:
            pass

        # Intelligence engine — track reply for feedback learning
        try:
            self.intelligence.on_jarvis_reply(reply)
        except Exception:
            pass

        # Self-evolution — learn from every interaction
        try:
            if hasattr(self, 'evolver'):
                self.evolver.learn_from_interaction(user_msg, reply)
        except Exception:
            pass

        # Knowledge graph — extract entities from conversation
        try:
            if hasattr(self, 'knowledge_graph'):
                self.knowledge_graph.extract_from_text(reply, source="jarvis_reply")
                if len(self.brain.history) >= 2:
                    user_msg = self.brain.history[-2].get("content", "")
                    if user_msg:
                        self.knowledge_graph.extract_from_text(user_msg, source="user_message")
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

        # Speak the response if voice is on, but always clear turn state.
        try:
            self.plugin_manager.on_response(reply)
        finally:
            self._active_turn = {}

    # ── Core state sync — forwards to both V2 canvas + GPU 3D core ──

    def _core_mode(self, mode: str):
        """Set mode on all available cores."""
        if hasattr(self, "main_core"):
            self.main_core.set_mode(mode)
        if getattr(self, "core_3d", None):
            self.core_3d.set_mode(mode)

    def _core_voice(self, level: float):
        """Set voice level on all available cores."""
        if hasattr(self, "main_core"):
            self.main_core.set_voice_level(level)
        if getattr(self, "core_3d", None):
            self.core_3d.set_voice_level(level)

    def animate_speaking_core(self, text: str):
        """Simulate voice amplitude on all cores while JARVIS 'speaks'."""
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

    def _on_error(self, error: str):
        self._processing = False
        self._active_turn = {}
        self.chat.remove_last_thinking()
        err_msg = f"Ran into an issue, sir. {error}"
        self.chat.add_message("assistant", err_msg)
        if getattr(self, "core_3d", None):
            self.core_3d.add_chat("assistant", err_msg)
        self.chat_input.set_enabled(True)

        # Core: alert mode
        self._core_mode("alert")
        self.root.after(1800, lambda: self._core_mode("idle"))

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
        raw_cmd = (cmd or "").strip()
        parts = raw_cmd.split(None, 1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""

        # Provider switching: /provider ollama
        if cmd == "/provider":
            if args:
                result = self.brain.switch_provider(args)
                from core.config import save_config
                save_config(self.config)
                self.chat.add_message("system", result)
                self._update_provider_display()
            else:
                # Show full provider dashboard
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
            from core.config import save_config
            save_config(self.config)
            self.chat.add_message("system", result)
            self._update_provider_display()
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
                self.chat.add_message(
                    "assistant",
                    "Task dataset exported\n"
                    f"- Episodes: {result['episodes']}\n"
                    f"- Planner examples: {result['planner_examples']}\n"
                    f"- Procedures: {result['procedures']}\n"
                    f"- Folder: {result['output_dir']}"
                )
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

        if cmd.startswith("/evolve"):
            parts = cmd.split(None, 1)
            if hasattr(self, 'evolver'):
                if len(parts) > 1:
                    # User is pasting a prompt for JARVIS to analyze and learn from
                    prompt_text = parts[1]
                    result = self.evolver.analyze_prompt(prompt_text)
                    self.chat.add_message("assistant",
                        f"Prompt Analysis Complete\n{'=' * 40}\n"
                        f"{result.summary}\n\n"
                        f"Techniques found: {', '.join(result.techniques_found) or 'none'}\n"
                        f"Rules adopted: {len(result.useful_rules)}\n"
                        f"Knowledge extracted: {len(result.new_knowledge)}\n"
                        + (f"New specialist: {result.specialist_definition['name']}\n"
                           if result.specialist_definition else "")
                        + "\nI've integrated the useful patterns into my reasoning.")

                    # If a specialist was extracted, add it
                    if result.specialist_definition and hasattr(self, 'specialists'):
                        from core.specialists import Specialist
                        spec_def = result.specialist_definition
                        new_spec = Specialist(
                            name=spec_def.get("name", "Custom"),
                            role=spec_def.get("role", "Custom specialist"),
                            identity_prompt=spec_def.get("identity", ""),
                            trigger_patterns=spec_def.get("triggers", []),
                            preferred_tools=spec_def.get("tools", []),
                            reasoning_rules=[],
                            knowledge_domains=spec_def.get("domains", []),
                        )
                        self.specialists.add_specialist(new_spec)
                else:
                    stats = self.evolver.get_evolution_stats()
                    improvements = self.evolver.suggest_improvements()
                    self.chat.add_message("assistant",
                        f"Evolution Status\n{'=' * 40}\n"
                        f"Total evolutions: {stats.get('total_evolutions', 0)}\n"
                        f"Learned rules: {stats.get('learned_rules', 0)}\n"
                        f"Techniques: {stats.get('learned_techniques', 0)}\n"
                        f"Knowledge items: {stats.get('domain_knowledge', 0)}\n"
                        f"Success rate: {stats.get('success_rate', 0):.0%}\n\n"
                        f"Suggested improvements:\n" +
                        "\n".join(f"  • {i}" for i in improvements[:5]) if improvements
                        else "  No improvements needed right now.")
            return

        if cmd.startswith("/research"):
            parts = cmd.split(None, 1)
            if len(parts) > 1 and hasattr(self, 'researcher'):
                query = parts[1].strip()
                self.chat.add_message("system", f"Researching: {query}...")
                self.chat_input.set_enabled(False)

                def _do_research():
                    try:
                        result = self.researcher.research(query, depth="deep")
                        def _show():
                            self.chat.add_message("assistant",
                                f"Research: {query}\n{'=' * 40}\n"
                                f"{result.summary}\n\n"
                                f"Sources: {len(result.sources)}\n"
                                + "\n".join(f"  • {s.get('title', s.get('url', '?'))}" for s in result.sources[:5])
                                + (f"\n\nFacts stored in knowledge graph: {result.knowledge_stored}" if result.knowledge_stored else ""))
                            self.chat_input.set_enabled(True)
                        self.root.after(0, _show)
                    except Exception as e:
                        self.root.after(0, lambda: self.chat.add_message("system", f"Research failed: {e}"))
                        self.root.after(0, lambda: self.chat_input.set_enabled(True))

                import threading
                threading.Thread(target=_do_research, daemon=True).start()
            else:
                self.chat.add_message("system", "Usage: /research <topic>")
            return

        if cmd.startswith("/specialist"):
            parts = cmd.split(None, 1)
            if hasattr(self, 'specialists'):
                if len(parts) > 1:
                    # Test which specialist would handle this
                    test_text = parts[1]
                    spec = self.specialists.select_specialist(test_text)
                    self.chat.add_message("assistant",
                        f"For \"{test_text}\":\n"
                        f"  Selected: {spec.name}\n"
                        f"  Role: {spec.role}\n"
                        f"  Tools: {', '.join(spec.preferred_tools[:5])}")
                else:
                    specs = self.specialists.list_specialists()
                    lines = ["JARVIS Specialist Team:"]
                    for s in specs:
                        lines.append(f"  [{s.name}] — {s.role}")
                    self.chat.add_message("assistant", "\n".join(lines))
            return

        if cmd.startswith("/think"):
            parts = cmd.split(None, 1)
            if len(parts) > 1 and hasattr(self, 'thinker'):
                query = parts[1]
                thought = self.thinker.think(query)
                monologue = "\n".join(f"  → {t}" for t in thought.thoughts) if thought.thoughts else "  (no thoughts)"
                knowledge = "\n".join(f"  • {k}" for k in thought.knowledge_used) if thought.knowledge_used else "  (none)"
                tools = ", ".join(thought.suggested_tools) if thought.suggested_tools else "none"
                self.chat.add_message("assistant",
                    f"JARVIS Internal Thinking\n{'=' * 40}\n"
                    f"Can answer locally: {thought.can_answer} (confidence: {thought.confidence:.0%})\n"
                    f"Needs API: {thought.needs_api}\n\n"
                    f"Thought chain:\n{monologue}\n\n"
                    f"Knowledge used:\n{knowledge}\n\n"
                    f"Suggested tools: {tools}\n\n"
                    f"Answer: {thought.answer or '(needs API for full answer)'}")
            elif hasattr(self, 'thinker'):
                # Autonomous reflection
                reflection = self.thinker.reflect()
                self.chat.add_message("assistant", f"JARVIS Reflection\n{'=' * 40}\n{reflection}")
            return

        if cmd.startswith("/goals"):
            if hasattr(self, 'thinker'):
                parts = cmd.split(None, 1)
                if len(parts) > 1:
                    self.thinker.goals.add_goal(parts[1])
                    self.chat.add_message("system", f"Goal added: {parts[1]}")
                else:
                    goals = self.thinker.goals.get_active_goals()
                    if goals:
                        lines = ["Active Goals:"]
                        for g in goals:
                            lines.append(f"  [{g.priority}] {g.description} (since {g.created_at[:10]})")
                        self.chat.add_message("assistant", "\n".join(lines))
                    else:
                        self.chat.add_message("system", "No active goals. Add one: /goals <description>")
            return

        if cmd.startswith("/chain") or cmd.startswith("/pentest"):
            parts = cmd.split(None, 2)
            if hasattr(self, 'chain_engine'):
                if cmd.startswith("/pentest") and len(parts) >= 2:
                    domain = parts[1].strip()
                    chain = self.chain_engine.full_pentest_chain(domain)
                    self.chat.add_message("system",
                        f"Launching full pentest chain on {domain} — {len(chain.steps)} steps")

                    def _chain_progress(msg):
                        self.root.after(0, lambda m=msg: self.chat.add_message("system", m))

                    def _chain_done(chain_obj):
                        def _show():
                            self.chat.add_message("assistant",
                                f"Pentest chain complete — {chain_obj.status}\n"
                                + "\n".join(f"  {s.step_id}: {s.status}" for s in chain_obj.steps))
                        self.root.after(0, _show)

                    self.chain_engine.execute_chain(
                        chain,
                        progress_cb=_chain_progress,
                        done_cb=_chain_done,
                        background=True,
                    )

                elif cmd.startswith("/chain") and len(parts) >= 2 and parts[1] == "quick" and len(parts) >= 3:
                    domain = parts[2].strip()
                    chain = self.chain_engine.quick_recon_chain(domain)
                    self.chat.add_message("system",
                        f"Launching quick recon chain on {domain} — {len(chain.steps)} steps")
                    def _chain_progress(msg):
                        self.root.after(0, lambda m=msg: self.chat.add_message("system", m))

                    def _chain_done(chain_obj):
                        def _show():
                            self.chat.add_message("assistant",
                                f"Quick recon chain complete — {chain_obj.status}\n"
                                + "\n".join(f"  {s.step_id}: {s.status}" for s in chain_obj.steps))
                        self.root.after(0, _show)

                    self.chain_engine.execute_chain(
                        chain,
                        progress_cb=_chain_progress,
                        done_cb=_chain_done,
                        background=True,
                    )

                elif cmd == "/chain" or cmd == "/chain list":
                    templates = self.chain_engine.list_templates()
                    lines = ["Available Chain Templates:"]
                    for t in templates:
                        lines.append(f"  {t['name']}: {t['description']} ({t['steps']} steps)")
                    self.chat.add_message("assistant", "\n".join(lines))
                else:
                    self.chat.add_message("system",
                        "Usage: /pentest <domain> | /chain quick <domain> | /chain list")
            return

        if cmd.startswith("/report"):
            if hasattr(self, 'report_engine'):
                # Generate report from pentest findings
                pentest = self.plugin_manager.plugins.get("pentest")
                if pentest and hasattr(pentest, 'findings') and pentest.findings:
                    from core.report_engine import Finding
                    findings = []
                    for i, f in enumerate(pentest.findings):
                        findings.append(Finding(
                            id=f"FINDING-{i+1:03d}",
                            title=f.get("title", f.get("type", "Unknown")),
                            severity=f.get("severity", "medium"),
                            description=f.get("description", ""),
                            affected_url=f.get("url", f.get("target", "")),
                            impact=f.get("impact", ""),
                            remediation=f.get("remediation", ""),
                        ))
                    target = pentest.scope.get("target", "Unknown") if hasattr(pentest, 'scope') else "Unknown"
                    report = self.report_engine.generate_report(findings, target)
                    # Save to file
                    import os
                    report_path = os.path.join(os.path.expanduser("~"), "Desktop",
                        f"jarvis_pentest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
                    try:
                        with open(report_path, "w", encoding="utf-8") as rf:
                            rf.write(report)
                        self.chat.add_message("assistant",
                            f"Report generated with {len(findings)} findings.\nSaved to: {report_path}")
                    except Exception as e:
                        self.chat.add_message("assistant", f"Report generated but save failed: {e}\n\n{report[:2000]}")
                else:
                    self.chat.add_message("system", "No pentest findings to report. Run scans first.")
            return

        if cmd == "/knowledge" or cmd == "/kg":
            parts = cmd.split(None, 1)
            query = parts[1] if len(parts) > 1 else None
            if hasattr(self, 'knowledge_graph'):
                if query:
                    data = self.knowledge_graph.query_everything(query)
                    if data["entity"]:
                        facts_str = "\n".join(f"  {k}: {v}" for k, v in data["entity"].get("facts", {}).items())
                        rels_str = "\n".join(
                            f"  → {r['predicate']} {r.get('target', r.get('source', ''))}"
                            for r in data["relationships"]
                        )
                        self.chat.add_message("assistant",
                            f"Knowledge: {query}\n"
                            f"Type: {data['entity']['type']}\n"
                            f"Facts:\n{facts_str or '  (none)'}\n"
                            f"Relationships:\n{rels_str or '  (none)'}")
                    else:
                        self.chat.add_message("system", f"No knowledge about '{query}'")
                else:
                    stats = self.knowledge_graph.get_stats()
                    types_str = ", ".join(f"{t}: {c}" for t, c in stats.get("entity_types", {}).items())
                    self.chat.add_message("assistant",
                        f"Knowledge Graph\n{'=' * 40}\n"
                        f"Entities: {stats['entities']}\n"
                        f"Facts: {stats['facts']}\n"
                        f"Relationships: {stats['relationships']}\n"
                        f"Timeline events: {stats['timeline_events']}\n"
                        f"Types: {types_str or 'none'}")
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
        if cmd in ("/abilities", "/tools"):
            summary = self.capabilities.describe_for_user(limit=20)
            self.chat.add_message("assistant", summary)
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

    # ══════════════════════════════════════════════════════════════
    # VOICE
    # ══════════════════════════════════════════════════════════════

    def toggle_listening(self):
        """Push-to-talk: Ctrl+Shift+V or mic button. Pauses wake loop to avoid mic conflict."""
        voice_plugin = self.plugin_manager.plugins.get("voice")
        if not voice_plugin:
            self.chat.add_message("system", "Voice plugin not loaded")
            return

        if getattr(voice_plugin, "uses_gemini_live", lambda: False)():
            if not self.voice_enabled:
                self.toggle_voice()
            else:
                self.chat.add_message("system", "Gemini Live session active. Speak naturally.")
            return

        # Auto-enable TTS so response is spoken back
        if not self.voice_enabled:
            self.voice_enabled = True
            voice_plugin.is_enabled = True
            self.voice_btn.config(text="MIC ON", fg=COLORS["green"])

        # Pause wake word loop so it doesn't steal the mic
        was_wake_active = voice_plugin.wake_word_active
        if was_wake_active:
            voice_plugin.wake_word_active = False
            import time
            time.sleep(0.3)  # Let current listen cycle finish

        self.chat.add_message("voice", "Listening... (speak now)")
        voice_plugin.speak("Listening.")

        # Core: listening mode (both V2 + 3D)
        self._core_mode("listening")

        def _on_done(text):
            self.root.after(0, lambda: self._core_mode("idle"))
            self.root.after(0, lambda: self._on_voice_input(text))
            if was_wake_active:
                voice_plugin._start_wake_word()

        def _on_fail(err):
            self.root.after(0, lambda: self._core_mode("idle"))
            self.root.after(0, lambda: self.chat.add_message("system", f"Voice: {err}"))
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
        if not self._has_vision_provider():
            self.chat.add_message(
                "system",
                "No vision-capable provider available. Configure Gemini/OpenAI/Anthropic or use a local vision-capable Ollama model.",
            )
            return

        self.scan_btn.config(text="📸 Scanning...", fg=COLORS["gold"])
        self.chat.add_message("system", "Using live screen feed...")

        import threading
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        try:
            screenshot = None
            monitor = getattr(self, "screen_monitor", None)
            if monitor:
                live = monitor.get_live_frame(max_age=3.0) or monitor.capture_now(analyze=False)
                if live:
                    screenshot = live.get("image")

            if screenshot is None:
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
            try:
                live_ctx = self.screen_monitor.get_screen_context()
                if live_ctx and live_ctx != "No screen context available.":
                    screen_prompt += f"\n\n[LIVE SCREEN CONTEXT]\n{live_ctx}"
            except Exception:
                pass

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

    def _has_vision_provider(self) -> bool:
        """Check whether the active or fallback provider stack can currently handle images."""
        try:
            if self.brain.provider.supports_vision and self.brain.provider.is_available():
                return True
        except Exception:
            pass

        try:
            if self.brain.fallback_enabled:
                for _name, provider in self.brain._get_fallback_providers():
                    if provider.supports_vision and provider.is_available():
                        return True
        except Exception:
            pass

        return False

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

    def _refresh_all(self):
        self.sidebar.refresh_memories(self.memory.memories)
        self.sidebar.refresh_tasks(self.config.get("tasks", []))
        self._update_stats()

    # ══════════════════════════════════════════════════════════════
    # HOTKEYS
    # ══════════════════════════════════════════════════════════════

    def _setup_hotkeys(self):
        if not HAS_KEYBOARD:
            return
        try:
            if self.config.get("ui", {}).get("enable_global_hide_hotkey", False):
                kb_module.add_hotkey("ctrl+shift+j", self._toggle_window)
            kb_module.add_hotkey("ctrl+shift+s", self.scan_screen)
            kb_module.add_hotkey("ctrl+shift+v", self.toggle_listening)
        except Exception:
            pass

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

    def _update_shell_chrome(self, accent):
        accent_color = COLORS.get(accent, accent)
        for widget in (
            getattr(self, "hero_shell", None),
            getattr(self, "cmd_shell", None),
            getattr(self, "clipboard_shell", None),
            getattr(self.chat, "outer", None),
            getattr(self.chat_input, "outer", None),
        ):
            if widget is not None:
                widget.config(
                    bg=COLORS["border_soft"],
                    highlightbackground=accent_color,
                    highlightcolor=accent_color,
                )

    def _set_sidebar_button_label(self, expanded: bool):
        self.sidebar_btn.config(text="STACK OPEN" if expanded else "STACK RAIL")

    def _after_sidebar_toggle(self, expanded: bool):
        self._set_sidebar_button_label(expanded)

    def toggle_sidebar(self):
        self.sidebar.toggle(self._after_sidebar_toggle)

    def set_mode(self, mode: str):
        msg = self.mode_switcher.switch(mode, manual=True)
        mode_text = mode.upper()
        self.mode_label.config(text=mode_text)
        self.mode_pill.set(value=mode_text)
        self.sidebar.set_mode_display(mode)
        self.chat.add_message("system", msg)

    def toggle_voice(self):
        voice_plugin = self.plugin_manager.plugins.get("voice")
        if voice_plugin:
            self.voice_enabled = not self.voice_enabled
            if self.voice_enabled:
                voice_plugin.enable()
                self.voice_btn.config(text="MIC ON", fg=COLORS["green"])
                if getattr(voice_plugin, "uses_gemini_live", lambda: False)():
                    self.voice_pill.set(value="GEMINI LIVE", accent="green")
                    self.chat.add_message("system", "Gemini Live session active")
                else:
                    self.voice_pill.set(value="MIC LIVE", accent="green")
                    self.chat.add_message("system", "Voice activated")
                self.sidebar.update_stats(voice="ON")
            else:
                voice_plugin.disable()
                self.voice_btn.config(text="MIC OFF", fg=COLORS["text_dim"])
                self.voice_pill.set(value="MIC OFF", accent="text_dim")
                if getattr(voice_plugin, "uses_gemini_live", lambda: False)():
                    self.chat.add_message("system", "Gemini Live session closed")
                else:
                    self.chat.add_message("system", "Voice deactivated")
                self.sidebar.update_stats(voice="OFF")
        else:
            self.chat.add_message(
                "system",
                "Voice not available. Install: pip install pyttsx3 SpeechRecognition pyaudio",
            )

    def _tick(self):
        now = datetime.now()
        self.clock_label.config(text=now.strftime("%H:%M"))
        self._refresh_clipboard_preview()

        elapsed = int(time.time() - self.session_start)
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            session_text = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            session_text = f"{minutes:02d}:{seconds:02d}"
        self.session_pill.set(value=session_text)
        self.sidebar.update_stats(time=f"{minutes:02d}:{seconds:02d}")

        try:
            state_text = self.presence.get_status_text()
            accent = "border_glow"
            if not self._processing:
                health = self.awareness.system_health
                if health.cpu_percent > 0:
                    self.subtitle.config(text=f"{state_text} · {health.status_text}")
                else:
                    self.subtitle.config(text=state_text)

                alert = health.alert_level
                if alert == "red":
                    self.status_dot.label.config(text="WARNING")
                    self.status_dot.color = COLORS["red"]
                    self.system_pill.set(value="WARNING", accent="red")
                    self.sidebar.set_compact_status("WARNING")
                    accent = "red"
                elif alert == "yellow":
                    self.status_dot.label.config(text="ELEVATED")
                    self.status_dot.color = COLORS["gold"]
                    self.system_pill.set(value="ELEVATED", accent="gold")
                    self.sidebar.set_compact_status("ELEVATED")
                    accent = "gold"
                else:
                    self.status_dot.label.config(text="ONLINE")
                    self.status_dot.color = COLORS["green"]
                    self.system_pill.set(value="NOMINAL", accent="green")
                    self.sidebar.set_compact_status("NOMINAL")
                    if self._processing:
                        accent = "primary"
                    elif self.voice_enabled:
                        accent = "accent"
                    else:
                        accent = "border_glow"
            else:
                self.subtitle.config(text="Processing active")
                self.system_pill.set(value="ACTIVE", accent="primary")
                self.sidebar.set_compact_status("ACTIVE")
                accent = "primary"

            self._update_shell_chrome(accent)
        except Exception:
            pass

        self.root.after(1000, self._tick)

    def _get_clipboard_text(self):
        text = ""
        try:
            cb = getattr(self.awareness, "clipboard", None)
            if cb and getattr(cb, "content", ""):
                text = cb.content.strip()
        except Exception:
            text = ""

        if text:
            return text

        try:
            text = self.root.clipboard_get().strip()
        except Exception:
            text = ""
        return text

    def _refresh_clipboard_preview(self, force=False):
        text = self._get_clipboard_text()
        preview = " ".join(text.split())[:120] if text else ""
        if not force and preview == self._clipboard_preview_text:
            return

        self._clipboard_preview_text = preview
        if preview:
            self.clipboard_preview.config(text=preview)
            if not self.clipboard_shell.winfo_manager():
                self.clipboard_shell.pack(
                    side=tk.BOTTOM,
                    fill=tk.X,
                    padx=(12, 8),
                    pady=(0, 8),
                    before=self.chat_input.outer,
                )
        else:
            self.clipboard_preview.config(text="")
            if self.clipboard_shell.winfo_manager():
                self.clipboard_shell.pack_forget()

    def paste_clipboard_to_input(self, send_now=False):
        text = self._get_clipboard_text()
        if not text:
            self.chat.add_message("system", "Clipboard is empty or does not contain text.")
            return

        current = self.chat_input.get_text()
        if current:
            self.chat_input.append_text(text)
        else:
            self.chat_input.set_text(text)

        if send_now:
            self.send_message(self.chat_input.get_text())
            self.chat_input.clear()

    def _toggle_window(self):
        if self.root.state() == "iconic":
            print("[JARVIS] Window restore hotkey triggered")
            self.root.after(0, self.root.deiconify)
        else:
            print("[JARVIS] Window hide hotkey triggered")
            self.root.after(0, self.root.iconify)

    # ══════════════════════════════════════════════════════════════
    # RUN
    # ══════════════════════════════════════════════════════════════

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        print("[JARVIS] Main window close requested")
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

        # Shutdown GPU 3D core
        try:
            if getattr(self, "core_3d", None):
                self.core_3d.stop()
        except Exception:
            pass

        # Shutdown engines
        try:
            self.presence.stop()
            self.awareness.stop()
            self.proactive.stop()
        except Exception:
            pass

        # Flush intelligence data to disk
        try:
            if hasattr(self, 'intelligence'):
                self.intelligence.flush()
        except Exception:
            pass

        # Stop screen awareness
        try:
            if hasattr(self, 'screen_monitor'):
                self.screen_monitor.stop()
        except Exception:
            pass

        # Save evolution state
        try:
            if hasattr(self, 'evolver'):
                self.evolver.store.save()
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
