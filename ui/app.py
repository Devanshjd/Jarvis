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
from core.memory import MemoryBank
from core.brain import Brain, MODES, MODE_LABELS
from core.plugin_manager import PluginManager
from core.agent import Agent
from core.learner import UserLearner
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
        self.brain = Brain(self.config)
        self.plugin_manager = PluginManager(self)

        # ── Agent + Learner ──
        self.agent = Agent(self)
        self.agent_mode = True  # Use agent loop; set False to bypass
        self.learner = UserLearner(self.config)
        self.learner.on_session_start()

        # ── State ──
        self.attached_file = None
        self.session_start = time.time()
        self.voice_enabled = False

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
                "/portscan", "/wifi", "/mynet", "/clear", "/agent"]
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
    # BOOT ANIMATION
    # ══════════════════════════════════════════════════════════════

    def _boot_animation(self):
        """Cinematic boot sequence."""
        msgs = [
            ("system", "Initializing J.A.R.V.I.S..."),
            ("system", "Core systems online"),
        ]

        # Check plugin status
        plugins = list(self.plugin_manager.plugins.keys())
        if plugins:
            msgs.append(("system", f"Plugins loaded: {', '.join(plugins)}"))

        mems = len(self.memory)
        if mems:
            msgs.append(("system", f"Memory bank: {mems} records"))

        if self.agent_mode:
            msgs.append(("system", "Agent mode: ACTIVE — planner + executor online"))

        def show_msg(index=0):
            if index < len(msgs):
                role, text = msgs[index]
                self.chat.add_message(role, text)
                self.root.after(400, lambda: show_msg(index + 1))
            else:
                # Final greeting
                self.root.after(300, self._show_greeting)

        show_msg()

    def _show_greeting(self):
        key = self.config.get("api_key", "")
        if not key:
            self.chat.add_message("assistant",
                "Welcome, sir. API key required to activate AI.\n"
                "Go to console.anthropic.com to get your key."
            )
            self.root.after(600, self.show_settings)
        elif not key.startswith("sk-ant-"):
            self.chat.add_message("assistant",
                "Welcome, sir. Your API key appears invalid — "
                "it should start with 'sk-ant-'.\n"
                "Please update it in Settings."
            )
        else:
            self.chat.add_message("assistant",
                "All systems nominal, sir. How may I assist you today?\n\n"
                "Say \"JARVIS\" anytime — I'm always listening.\n"
                "Press Ctrl+Shift+V for push-to-talk (no wake word needed).\n"
                "Hotkeys: Ctrl+Shift+J (toggle) · Ctrl+Shift+S (scan)"
            )

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

    # ══════════════════════════════════════════════════════════════
    # MESSAGING
    # ══════════════════════════════════════════════════════════════

    def send_message(self, text: str):
        text = self.plugin_manager.process_message(text)

        # Plugin handled it entirely
        if text == "__handled__":
            return

        # Track user message for learning
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

        # Show user message in chat
        self.chat.add_message("user", text)
        self.brain.add_user_message(text)
        self.brain.msg_count += 1
        self._update_stats()

        self.chat_input.set_enabled(False)
        self.chat.add_message("thinking", "Processing...")

        if self.agent_mode:
            # ── Agent Loop ── plan → safety → execute → respond
            self.agent.process_message(
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

    def _on_reply(self, reply: str, latency: int):
        self.chat.remove_last_thinking()
        self.chat.add_message("assistant", reply)
        self.chat_input.set_enabled(True)
        self._update_stats()
        # Speak the response if voice is on
        print(f"[DEBUG] _on_reply called, voice_enabled={self.voice_enabled}")
        self.plugin_manager.on_response(reply)

    def _on_error(self, error: str):
        self.chat.remove_last_thinking()
        self.chat.add_message("assistant", f"Error, sir: {error}")
        self.chat_input.set_enabled(True)

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
                info = self.brain.get_provider_info()
                available = ", ".join(["anthropic", "ollama", "lmstudio", "openai"])
                self.chat.add_message("assistant",
                    f"Current provider: {info['name']} ({info['model']})\n"
                    f"Local: {'Yes' if info.get('local') else 'No'}\n"
                    f"Vision: {'Yes' if info.get('vision') else 'No'}\n\n"
                    f"Switch with: /provider <{available}>"
                )
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

        text = cmd_map.get(cmd, cmd)
        if text:
            self.chat_input.set_text(text)

    # ══════════════════════════════════════════════════════════════
    # MODE
    # ══════════════════════════════════════════════════════════════

    def set_mode(self, mode: str):
        self.brain.set_mode(mode)
        self.mode_label.config(text=MODE_LABELS.get(mode, mode[:3].upper()))
        self.chat.add_message("system", f"Mode → {mode}")

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
        self.save_notes()
        for name in list(self.plugin_manager.plugins.keys()):
            self.plugin_manager.unload_plugin(name)
        if HAS_KEYBOARD:
            try:
                kb_module.unhook_all()
            except Exception:
                pass
        self.root.destroy()
