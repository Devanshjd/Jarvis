"""
J.A.R.V.I.S Desktop App — Stark Industries
============================================
Screen reading, system tray, hotkeys, file editing, real-time suggestions.

SETUP (run once):
    pip install anthropic pillow pystray keyboard pyautogui tkinter customtkinter

USAGE:
    python jarvis_desktop.py
    
HOTKEYS:
    Ctrl+Shift+J  — Open/close JARVIS window
    Ctrl+Shift+S  — Scan current screen and get suggestions
    Ctrl+Shift+V  — Voice input (if mic available)
"""

import os, sys, json, time, threading, base64, io, subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime

# ── Optional imports (graceful fallback) ──────────────────────────
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    print("Install: pip install anthropic")

try:
    from PIL import ImageGrab, Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Install: pip install pillow")

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

try:
    import pystray
    from pystray import MenuItem as item
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

# ── Config ─────────────────────────────────────────────────────────
CONFIG_FILE = os.path.expanduser("~/.jarvis_config.json")
COLORS = {
    "bg":       "#000a14",
    "bg2":      "#001020",
    "bg3":      "#001830",
    "panel":    "#001428",
    "blue":     "#00d4ff",
    "blue2":    "#0099cc",
    "blue3":    "#7dd3fc",
    "accent":   "#ff6b00",
    "gold":     "#ffd700",
    "red":      "#ff2244",
    "green":    "#00ff88",
    "text":     "#c8eeff",
    "muted":    "#2a5060",
    "border":   "#004466",
}
FONT_MONO  = ("Courier New", 10)
FONT_TITLE = ("Courier New", 18, "bold")
FONT_SUB   = ("Courier New", 9)
FONT_MSG   = ("Segoe UI", 11)
FONT_LABEL = ("Courier New", 8)

MODES = {
    "General":   "You are J.A.R.V.I.S — Tony Stark's AI. Intelligent, precise, witty, quietly confident with British sophistication. Help with anything. Occasionally call user 'sir'.",
    "Code/Dev":  "You are J.A.R.V.I.S in Developer Mode — elite software architect. Write complete working code in any language. Be thorough. Occasionally call user 'sir'.",
    "Research":  "You are J.A.R.V.I.S in Research Mode — world-class analyst. Synthesize info deeply, structured analysis, cite facts. Occasionally call user 'sir'.",
    "Projects":  "You are J.A.R.V.I.S in Project Mode — expert project manager and co-founder. Roadmaps, architecture, execution. Occasionally call user 'sir'.",
    "Analysis":  "You are J.A.R.V.I.S in Analysis Mode. Rigorous pros/cons, risk assessment, scenario planning. Occasionally call user 'sir'.",
    "Screen":    "You are J.A.R.V.I.S analyzing what is currently visible on the operator's screen. Describe what you see, identify the active application, understand what they are working on, and proactively suggest how you can help them. Be specific and practical. Call user 'sir'.",
    "File Edit": "You are J.A.R.V.I.S in File Edit Mode. The operator will show you file contents. Help read, analyze, edit, improve, or rewrite the content. Return full edited versions when asked. Occasionally call user 'sir'.",
    "Advisor":   "You are J.A.R.V.I.S in Life Advisor Mode. Trusted, wise, empathetic. Help with personal decisions, career, goals. Honest but kind. Occasionally call user 'sir'.",
}

# ── Config I/O ─────────────────────────────────────────────────────
def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except:
        return {"api_key": "", "memories": [], "tasks": []}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# ══════════════════════════════════════════════════════════════════
# JARVIS APP
# ══════════════════════════════════════════════════════════════════
class JarvisApp:
    def __init__(self):
        self.cfg = load_config()
        self.history = []
        self.mode = "General"
        self.scanning = False
        self.scan_thread = None
        self.last_scan_time = 0
        self.attached_file = None
        self.msg_count = 0
        self.session_start = time.time()

        self.root = tk.Tk()
        self.root.title("J.A.R.V.I.S — Stark Industries")
        self.root.configure(bg=COLORS["bg"])
        self.root.geometry("1200x750")
        self.root.minsize(900, 600)

        # Icon
        try:
            self.root.iconbitmap(default="")
        except:
            pass

        self._build_ui()
        self._setup_hotkeys()
        self._tick()

        # Boot message
        self.root.after(500, self._boot_message)

    # ── UI BUILD ──────────────────────────────────────────────────
    def _build_ui(self):
        # Title bar
        self._make_titlebar()
        # Main 3-col layout
        main = tk.Frame(self.root, bg=COLORS["bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # LEFT
        left = tk.Frame(main, bg=COLORS["bg"], width=210)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        left.pack_propagate(False)
        self._build_left(left)

        # CENTER
        center = tk.Frame(main, bg=COLORS["bg"])
        center.grid(row=0, column=1, sticky="nsew", padx=5)
        self._build_center(center)

        # RIGHT
        right = tk.Frame(main, bg=COLORS["bg"], width=220)
        right.grid(row=0, column=2, sticky="nsew", padx=(5,0))
        right.pack_propagate(False)
        self._build_right(right)

        # Status bar
        self._make_statusbar()

    def _make_titlebar(self):
        bar = tk.Frame(self.root, bg=COLORS["bg2"], height=52)
        bar.pack(fill=tk.X, padx=6, pady=(6,4))
        bar.pack_propagate(False)

        # Left: arc + title
        lf = tk.Frame(bar, bg=COLORS["bg2"])
        lf.pack(side=tk.LEFT, padx=12, fill=tk.Y)

        arc_canvas = tk.Canvas(lf, width=44, height=44, bg=COLORS["bg2"], highlightthickness=0)
        arc_canvas.pack(side=tk.LEFT, padx=(0,10))
        self._draw_arc(arc_canvas)

        tf = tk.Frame(lf, bg=COLORS["bg2"])
        tf.pack(side=tk.LEFT, fill=tk.Y, pady=4)
        tk.Label(tf, text="J.A.R.V.I.S", font=("Courier New",16,"bold"),
                 fg=COLORS["blue"], bg=COLORS["bg2"]).pack(anchor="w")
        tk.Label(tf, text="STARK INDUSTRIES  ·  PERSONAL AI SYSTEM", font=FONT_LABEL,
                 fg=COLORS["muted"], bg=COLORS["bg2"]).pack(anchor="w")

        # Right: stats + controls
        rf = tk.Frame(bar, bg=COLORS["bg2"])
        rf.pack(side=tk.RIGHT, padx=12, fill=tk.Y)

        # Online badge
        online_f = tk.Frame(rf, bg=COLORS["bg2"])
        online_f.pack(side=tk.RIGHT, padx=(8,0), pady=12)
        tk.Label(online_f, text="●", font=("Courier New",9), fg=COLORS["green"], bg=COLORS["bg2"]).pack(side=tk.LEFT)
        tk.Label(online_f, text=" ONLINE", font=FONT_LABEL, fg=COLORS["green"], bg=COLORS["bg2"]).pack(side=tk.LEFT)

        self.voice_btn = tk.Button(rf, text="VOICE OFF", font=FONT_LABEL,
                                   fg=COLORS["muted"], bg=COLORS["bg2"],
                                   activeforeground=COLORS["blue"],
                                   activebackground=COLORS["bg2"],
                                   bd=1, relief=tk.FLAT,
                                   command=self._toggle_voice, cursor="hand2")
        self.voice_btn.pack(side=tk.RIGHT, padx=4, pady=14)

        self.clk_label = tk.Label(rf, text="00:00:00", font=("Courier New",11),
                                   fg=COLORS["blue2"], bg=COLORS["bg2"])
        self.clk_label.pack(side=tk.RIGHT, padx=12)

        # Stat numbers
        for var_name, label in [("msg_var","MSGS"), ("mode_var","MODE"), ("mem_var","MEM")]:
            sf = tk.Frame(rf, bg=COLORS["bg2"])
            sf.pack(side=tk.RIGHT, padx=8, pady=4)
            v = tk.StringVar(value="0" if label != "MODE" else "GEN")
            setattr(self, var_name, v)
            tk.Label(sf, textvariable=v, font=("Courier New",13,"bold"),
                     fg=COLORS["blue"], bg=COLORS["bg2"]).pack()
            tk.Label(sf, text=label, font=FONT_LABEL, fg=COLORS["muted"], bg=COLORS["bg2"]).pack()

    def _draw_arc(self, canvas):
        """Animate arc reactor on canvas"""
        self._arc_angle = 0
        def animate():
            canvas.delete("all")
            cx, cy, r = 22, 22, 18
            # Outer ring
            canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                              outline=COLORS["blue"], width=2)
            # Middle ring
            canvas.create_oval(cx-12, cy-12, cx+12, cy+12,
                              outline=COLORS["blue2"], width=1)
            # Core
            canvas.create_oval(cx-5, cy-5, cx+5, cy+5,
                              fill=COLORS["blue"], outline=COLORS["blue3"], width=1)
            # Rotating tick
            import math
            angle = math.radians(self._arc_angle)
            tx = cx + 16 * math.cos(angle)
            ty = cy + 16 * math.sin(angle)
            canvas.create_line(cx, cy, tx, ty, fill=COLORS["blue3"], width=1)
            self._arc_angle = (self._arc_angle + 3) % 360
            canvas.after(50, animate)
        animate()

    def _panel(self, parent, title, color=None):
        """Create a HUD panel with title"""
        color = color or COLORS["blue"]
        f = tk.Frame(parent, bg=COLORS["panel"],
                     highlightbackground=COLORS["border"],
                     highlightthickness=1)
        # Header
        hdr = tk.Frame(f, bg=COLORS["bg3"])
        hdr.pack(fill=tk.X)
        tk.Frame(hdr, bg=color, width=3).pack(side=tk.LEFT, fill=tk.Y)
        tk.Label(hdr, text=f"  {title}", font=FONT_LABEL,
                 fg=color, bg=COLORS["bg3"],
                 padx=6, pady=5).pack(side=tk.LEFT)
        return f

    # ── LEFT PANEL ────────────────────────────────────────────────
    def _build_left(self, parent):
        # Modes
        mp = self._panel(parent, "OPERATIONAL MODES")
        mp.pack(fill=tk.X, pady=(0,5))
        self.mode_var_sel = tk.StringVar(value="General")
        for m in MODES:
            rb = tk.Radiobutton(mp, text=f"  {m}", variable=self.mode_var_sel,
                                value=m, font=("Courier New",9),
                                fg=COLORS["text"], bg=COLORS["panel"],
                                selectcolor=COLORS["bg3"],
                                activeforeground=COLORS["blue"],
                                activebackground=COLORS["panel"],
                                cursor="hand2",
                                command=lambda m=m: self._set_mode(m))
            rb.pack(anchor="w", padx=6, pady=1)

        # Stats
        sp = self._panel(parent, "SYSTEM STATS")
        sp.pack(fill=tk.X, pady=(0,5))
        self.stat_frame = tk.Frame(sp, bg=COLORS["panel"])
        self.stat_frame.pack(fill=tk.X, padx=6, pady=6)
        self._stats_vars = {}
        for key, label in [("msgs","MESSAGES"),("mems","MEMORIES"),("tasks","TASKS"),("time","SESSION")]:
            row = tk.Frame(self.stat_frame, bg=COLORS["panel"])
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, font=FONT_LABEL, fg=COLORS["muted"], bg=COLORS["panel"], width=10, anchor="w").pack(side=tk.LEFT)
            v = tk.StringVar(value="0" if key != "time" else "00:00")
            self._stats_vars[key] = v
            tk.Label(row, textvariable=v, font=("Courier New",10,"bold"), fg=COLORS["blue"], bg=COLORS["panel"]).pack(side=tk.RIGHT)

        # Memory
        memp = self._panel(parent, "MEMORY BANK")
        memp.pack(fill=tk.BOTH, expand=True, pady=(0,5))
        self.mem_list = tk.Listbox(memp, bg=COLORS["bg3"], fg=COLORS["blue3"],
                                   font=("Segoe UI",9), bd=0, highlightthickness=0,
                                   selectbackground=COLORS["bg2"],
                                   activestyle="none")
        self.mem_list.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        mem_btns = tk.Frame(memp, bg=COLORS["panel"])
        mem_btns.pack(fill=tk.X, padx=4, pady=(0,4))
        tk.Button(mem_btns, text="CLEAR MEM", font=FONT_LABEL,
                  fg=COLORS["red"], bg=COLORS["bg3"], bd=0, cursor="hand2",
                  activeforeground=COLORS["red"], activebackground=COLORS["bg3"],
                  command=self._clear_memory).pack(side=tk.LEFT)
        self._refresh_memories()

    # ── CENTER ────────────────────────────────────────────────────
    def _build_center(self, parent):
        # Chat panel
        chat_frame = self._panel(parent, "COMMUNICATION INTERFACE")
        chat_frame.pack(fill=tk.BOTH, expand=True)
        self.mode_label = tk.Label(chat_frame, textvariable=tk.StringVar(value="MODE: GENERAL"),
                                   font=FONT_LABEL, fg=COLORS["muted"], bg=COLORS["bg3"])
        # Inject into header
        for w in chat_frame.winfo_children():
            if isinstance(w, tk.Frame):
                self.mode_label = tk.Label(w, text="MODE: GENERAL", font=FONT_LABEL,
                                           fg=COLORS["muted"], bg=COLORS["bg3"])
                self.mode_label.pack(side=tk.RIGHT, padx=6)
                break

        # Chat display
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, bg=COLORS["bg"], fg=COLORS["text"],
            font=FONT_MSG, bd=0, padx=12, pady=8,
            wrap=tk.WORD, state=tk.DISABLED,
            highlightthickness=0,
            insertbackground=COLORS["blue"]
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0,1))
        # Tag styles
        self.chat_display.tag_config("user_lbl",  foreground=COLORS["accent"],  font=("Courier New",8,"bold"))
        self.chat_display.tag_config("user_msg",  foreground="#ffd8b0",         font=FONT_MSG)
        self.chat_display.tag_config("jar_lbl",   foreground=COLORS["blue"],    font=("Courier New",8,"bold"))
        self.chat_display.tag_config("jar_msg",   foreground=COLORS["text"],    font=FONT_MSG)
        self.chat_display.tag_config("sys_msg",   foreground=COLORS["muted"],   font=("Courier New",9))
        self.chat_display.tag_config("thinking",  foreground=COLORS["blue2"],   font=("Courier New",9))

        # Quick commands
        qf = tk.Frame(parent, bg=COLORS["bg"])
        qf.pack(fill=tk.X, pady=4)
        cmds = ["/plan day", "/code", "/research", "/analyze", "/debug", "/write", "/memory", "/clear"]
        for cmd in cmds:
            tk.Button(qf, text=cmd, font=FONT_LABEL,
                      fg=COLORS["muted"], bg=COLORS["bg"],
                      activeforeground=COLORS["blue"],
                      activebackground=COLORS["bg"],
                      bd=1, relief=tk.FLAT, cursor="hand2", padx=6, pady=3,
                      command=lambda c=cmd: self._quick_cmd(c)).pack(side=tk.LEFT, padx=2)

        # Screen scan button
        scan_f = tk.Frame(parent, bg=COLORS["bg"])
        scan_f.pack(fill=tk.X, pady=(0,4))
        self.scan_btn = tk.Button(scan_f, text="⬡  SCAN SCREEN  →  JARVIS ANALYZES WHAT YOU'RE WORKING ON",
                                   font=FONT_LABEL,
                                   fg=COLORS["green"], bg=COLORS["bg3"],
                                   activeforeground=COLORS["green"],
                                   activebackground=COLORS["bg3"],
                                   bd=1, relief=tk.FLAT, cursor="hand2",
                                   padx=8, pady=5,
                                   command=self._scan_screen)
        self.scan_btn.pack(fill=tk.X)

        # Input area
        inp_frame = tk.Frame(parent, bg=COLORS["bg3"],
                             highlightbackground=COLORS["border"],
                             highlightthickness=1)
        inp_frame.pack(fill=tk.X)
        tk.Label(inp_frame, text="▶", font=("Courier New",12,"bold"),
                 fg=COLORS["blue"], bg=COLORS["bg3"]).pack(side=tk.LEFT, padx=8)
        self.inp = tk.Text(inp_frame, bg=COLORS["bg3"], fg=COLORS["text"],
                           font=FONT_MSG, bd=0, height=2, padx=6, pady=8,
                           wrap=tk.WORD, insertbackground=COLORS["blue"],
                           highlightthickness=0)
        self.inp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inp.insert("1.0", "State your command, sir...")
        self.inp.config(fg=COLORS["muted"])
        self.inp.bind("<FocusIn>", self._inp_focus_in)
        self.inp.bind("<FocusOut>", self._inp_focus_out)
        self.inp.bind("<Return>", self._on_enter)
        self.inp.bind("<Shift-Return>", lambda e: None)

        btn_col = tk.Frame(inp_frame, bg=COLORS["bg3"])
        btn_col.pack(side=tk.RIGHT, padx=6, pady=6)
        self.mic_btn = tk.Button(btn_col, text="🎤", font=("Segoe UI",11),
                                  fg=COLORS["blue"], bg=COLORS["bg3"],
                                  activeforeground=COLORS["blue"],
                                  activebackground=COLORS["bg3"],
                                  bd=0, cursor="hand2",
                                  command=self._toggle_mic)
        self.mic_btn.pack(pady=(0,4))
        self.send_btn = tk.Button(btn_col, text="FIRE", font=("Courier New",9,"bold"),
                                   fg=COLORS["blue"], bg=COLORS["bg2"],
                                   activeforeground=COLORS["blue3"],
                                   activebackground=COLORS["bg"],
                                   bd=1, relief=tk.FLAT, padx=8, pady=4,
                                   cursor="hand2",
                                   command=self._send)
        self.send_btn.pack()

    # ── RIGHT PANEL ───────────────────────────────────────────────
    def _build_right(self, parent):
        # Tasks
        tp = self._panel(parent, "MISSION TASKS", COLORS["accent"])
        tp.pack(fill=tk.X, pady=(0,5))
        self.task_list = tk.Listbox(tp, bg=COLORS["bg3"], fg=COLORS["text"],
                                     font=("Segoe UI",10), bd=0, height=8,
                                     highlightthickness=0, selectbackground=COLORS["bg2"],
                                     activestyle="none")
        self.task_list.pack(fill=tk.X, padx=4, pady=4)
        self.task_list.bind("<Double-Button-1>", self._toggle_task)
        task_add = tk.Frame(tp, bg=COLORS["panel"])
        task_add.pack(fill=tk.X, padx=4, pady=(0,4))
        self.task_inp = tk.Entry(task_add, bg=COLORS["bg3"], fg=COLORS["text"],
                                  font=("Segoe UI",10), bd=0, insertbackground=COLORS["blue"])
        self.task_inp.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0,4))
        self.task_inp.bind("<Return>", lambda e: self._add_task())
        tk.Button(task_add, text="ADD", font=FONT_LABEL,
                  fg=COLORS["accent"], bg=COLORS["bg3"], bd=0, cursor="hand2",
                  activeforeground=COLORS["gold"],
                  activebackground=COLORS["bg3"],
                  command=self._add_task).pack(side=tk.RIGHT)
        tk.Button(tp, text="Ask JARVIS to prioritize →", font=FONT_LABEL,
                  fg=COLORS["muted"], bg=COLORS["panel"], bd=0, cursor="hand2",
                  activeforeground=COLORS["blue"],
                  activebackground=COLORS["panel"],
                  command=lambda: self._quick_cmd("/prioritize tasks")).pack(anchor="w", padx=6, pady=(0,4))
        self._refresh_tasks()

        # Notes
        np2 = self._panel(parent, "INTEL NOTES", COLORS["gold"])
        np2.pack(fill=tk.BOTH, expand=True, pady=(0,5))
        note_toolbar = tk.Frame(np2, bg=COLORS["bg3"])
        note_toolbar.pack(fill=tk.X)
        for label, cmd in [("SAVE", self._save_note), ("ASK JARVIS ↗", self._note_to_jarvis), ("EXPORT", self._export_note)]:
            tk.Button(note_toolbar, text=label, font=FONT_LABEL,
                      fg=COLORS["muted"], bg=COLORS["bg3"], bd=0, cursor="hand2",
                      activeforeground=COLORS["gold"],
                      activebackground=COLORS["bg3"],
                      padx=8, pady=3,
                      command=cmd).pack(side=tk.LEFT)
        self.notepad = tk.Text(np2, bg=COLORS["bg3"], fg=COLORS["text"],
                               font=("Segoe UI",10), bd=0, padx=8, pady=6,
                               wrap=tk.WORD, insertbackground=COLORS["blue"],
                               highlightthickness=0)
        self.notepad.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0,1))
        self.notepad.bind("<Control-s>", lambda e: self._save_note())
        note_content = self.cfg.get("notes", "")
        if note_content:
            self.notepad.insert("1.0", note_content)

        # File panel
        fp = self._panel(parent, "FILE OPERATIONS", COLORS["green"])
        fp.pack(fill=tk.X)
        file_btns = tk.Frame(fp, bg=COLORS["panel"])
        file_btns.pack(fill=tk.X, padx=6, pady=6)
        for label, cmd in [
            ("OPEN FILE", self._open_file),
            ("ANALYZE FILE", self._analyze_file),
            ("SCREENSHOT", self._scan_screen),
        ]:
            tk.Button(file_btns, text=label, font=FONT_LABEL,
                      fg=COLORS["green"], bg=COLORS["bg3"],
                      activeforeground=COLORS["blue"],
                      activebackground=COLORS["bg3"],
                      bd=1, relief=tk.FLAT, cursor="hand2",
                      padx=6, pady=4,
                      command=cmd).pack(fill=tk.X, pady=1)
        self.file_status = tk.Label(fp, text="No file loaded", font=FONT_LABEL,
                                     fg=COLORS["muted"], bg=COLORS["panel"],
                                     wraplength=200, justify=tk.LEFT)
        self.file_status.pack(padx=6, pady=(0,6), anchor="w")

    def _make_statusbar(self):
        sb = tk.Frame(self.root, bg=COLORS["bg2"], height=26)
        sb.pack(fill=tk.X, padx=6, pady=(0,4))
        items = [
            ("STARK INDUSTRIES AI DIVISION", COLORS["muted"]),
            ("ALL SYSTEMS NOMINAL", COLORS["green"]),
            ("MODEL: claude-opus-4-5", COLORS["muted"]),
            ("BUILD: v4.0-DESKTOP", COLORS["muted"]),
        ]
        for text, color in items:
            tk.Label(sb, text=f"  ●  {text}", font=FONT_LABEL,
                     fg=color, bg=COLORS["bg2"]).pack(side=tk.LEFT)
        self.sb_time = tk.Label(sb, text="00:00:00", font=FONT_LABEL,
                                 fg=COLORS["blue2"], bg=COLORS["bg2"])
        self.sb_time.pack(side=tk.RIGHT, padx=8)

    # ── CHAT ──────────────────────────────────────────────────────
    def _add_chat(self, role, text):
        self.chat_display.config(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M")
        if role == "user":
            self.chat_display.insert(tk.END, f"\n[{ts}] OPERATOR\n", "user_lbl")
            self.chat_display.insert(tk.END, f"{text}\n", "user_msg")
        elif role == "assistant":
            self.chat_display.insert(tk.END, f"\n[{ts}] J.A.R.V.I.S\n", "jar_lbl")
            self.chat_display.insert(tk.END, f"{text}\n", "jar_msg")
        elif role == "system":
            self.chat_display.insert(tk.END, f"\n  — {text} —\n", "sys_msg")
        elif role == "thinking":
            self.chat_display.insert(tk.END, f"\n  ◌  {text}\n", "thinking")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def _remove_last_thinking(self):
        self.chat_display.config(state=tk.NORMAL)
        content = self.chat_display.get("1.0", tk.END)
        idx = content.rfind("  ◌  ")
        if idx != -1:
            # Find line start
            line_start = content.rfind("\n", 0, idx)
            line_end = content.find("\n", idx)
            if line_end != -1:
                # Convert char index to tk index
                start_line = content[:line_start].count("\n") + 1
                end_line = content[:line_end].count("\n") + 2
                self.chat_display.delete(f"{start_line}.0", f"{end_line}.0")
        self.chat_display.config(state=tk.DISABLED)

    # ── SEND ──────────────────────────────────────────────────────
    def _send(self):
        text = self.inp.get("1.0", tk.END).strip()
        placeholder = "State your command, sir..."
        if not text or text == placeholder:
            return
        self.inp.delete("1.0", tk.END)
        self._process_send(text)

    def _process_send(self, text):
        # Memory command
        import re
        mr = re.match(r"remember\s+(?:that\s+)?(.+)", text, re.IGNORECASE)
        if mr:
            self._add_memory(mr.group(1))
            self._add_chat("user", text)
            self._add_chat("assistant", f'Committed to memory, sir: "{mr.group(1)}"')
            return

        self._add_chat("user", text)
        self.msg_count += 1
        self._update_stats()
        self.history.append({"role": "user", "content": text})
        if len(self.history) > 30:
            self.history = self.history[-28:]

        self.send_btn.config(state=tk.DISABLED)
        self._add_chat("thinking", "Processing query...")
        threading.Thread(target=self._call_api, args=(text,), daemon=True).start()

    def _call_api(self, text):
        if not HAS_ANTHROPIC:
            self.root.after(0, lambda: self._api_done("Install anthropic: pip install anthropic"))
            return
        if not self.cfg.get("api_key"):
            self.root.after(0, lambda: self._api_done("No API key configured. Go to Settings and add your Anthropic API key."))
            return
        try:
            client = anthropic.Anthropic(api_key=self.cfg["api_key"])
            sys_prompt = MODES[self.mode]
            mems = self.cfg.get("memories", [])
            if mems:
                sys_prompt += f"\n\n[OPERATOR MEMORIES]\n" + "\n".join(f"{i+1}. {m}" for i,m in enumerate(mems))
            notes = self.notepad.get("1.0", tk.END).strip()
            if notes:
                sys_prompt += f"\n\n[CURRENT NOTES]\n{notes}"

            t0 = time.time()
            msg = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=2048,
                system=sys_prompt,
                messages=self.history
            )
            lat = int((time.time()-t0)*1000)
            reply = msg.content[0].text
            self.history.append({"role": "assistant", "content": reply})
            self.msg_count += 1
            self.root.after(0, lambda r=reply, l=lat: self._api_done(r, l))
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._api_done(f"Error, sir: {err}"))

    def _api_done(self, reply, lat=None):
        self._remove_last_thinking()
        self._add_chat("assistant", reply)
        self._update_stats()
        self.send_btn.config(state=tk.NORMAL)
        if lat:
            # Update latency in status bar
            pass

    # ── SCREEN SCAN ───────────────────────────────────────────────
    def _scan_screen(self):
        if not HAS_PIL:
            self._add_chat("system", "Install Pillow for screen scanning: pip install pillow")
            return
        if not self.cfg.get("api_key"):
            self._add_chat("system", "API key required. Check Settings.")
            return

        self.scan_btn.config(text="SCANNING...", fg=COLORS["gold"])
        self._add_chat("system", "Capturing screen — analyzing what you're working on, sir...")
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        try:
            # Minimize briefly to capture actual desktop
            self.root.after(0, self.root.iconify)
            time.sleep(0.8)

            screenshot = ImageGrab.grab()
            self.root.after(0, self.root.deiconify)

            # Resize for API
            max_size = (1280, 720)
            screenshot.thumbnail(max_size, Image.LANCZOS)

            # Convert to base64
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            # Send to Claude with vision
            client = anthropic.Anthropic(api_key=self.cfg["api_key"])
            sys_prompt = MODES["Screen"]
            mems = self.cfg.get("memories", [])
            if mems:
                sys_prompt += f"\n\n[OPERATOR MEMORIES]\n" + "\n".join(f"{i+1}. {m}" for i,m in enumerate(mems))

            msg = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=1500,
                system=sys_prompt,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": "Analyze what is on my screen. What am I working on? What can you help me with right now?"
                        }
                    ]
                }]
            )
            reply = msg.content[0].text
            self.history.append({"role": "assistant", "content": reply})
            self.root.after(0, lambda r=reply: self._scan_done(r))
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._scan_done(f"Scan error: {err}"))

    def _scan_done(self, reply):
        self.scan_btn.config(text="⬡  SCAN SCREEN  →  JARVIS ANALYZES WHAT YOU'RE WORKING ON",
                              fg=COLORS["green"])
        self._add_chat("assistant", reply)
        self.msg_count += 1
        self._update_stats()

    # ── FILE OPERATIONS ───────────────────────────────────────────
    def _open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("All files","*.*"),("Text","*.txt"),("Python","*.py"),
                       ("JavaScript","*.js"),("HTML","*.html"),("JSON","*.json"),
                       ("Markdown","*.md"),("CSV","*.csv")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.attached_file = {"path": path, "content": content, "name": os.path.basename(path)}
            size_kb = len(content) // 1024
            self.file_status.config(text=f"✓ {os.path.basename(path)} ({size_kb}KB)", fg=COLORS["green"])
            self._add_chat("system", f"File loaded: {os.path.basename(path)} — ready to analyze or edit")
        except Exception as e:
            self.file_status.config(text=f"Error: {e}", fg=COLORS["red"])

    def _analyze_file(self):
        if not self.attached_file:
            self._open_file()
            if not self.attached_file:
                return
        text = f"[File: {self.attached_file['name']}]\n\n{self.attached_file['content'][:8000]}\n\n---\nAnalyze this file. What is it? What does it do? What improvements would you suggest?"
        self._process_send(text)

    # ── NOTES ─────────────────────────────────────────────────────
    def _save_note(self):
        self.cfg["notes"] = self.notepad.get("1.0", tk.END).strip()
        save_config(self.cfg)
        self._add_chat("system", "Intel notes saved")

    def _note_to_jarvis(self):
        notes = self.notepad.get("1.0", tk.END).strip()
        if notes:
            self._process_send(f"Review and improve these notes:\n\n{notes}")

    def _export_note(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                             filetypes=[("Text","*.txt"),("Markdown","*.md")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.notepad.get("1.0", tk.END))
            self._add_chat("system", f"Notes exported to {os.path.basename(path)}")

    # ── TASKS ─────────────────────────────────────────────────────
    def _add_task(self):
        text = self.task_inp.get().strip()
        if not text:
            return
        tasks = self.cfg.get("tasks", [])
        tasks.append({"text": text, "done": False})
        self.cfg["tasks"] = tasks
        save_config(self.cfg)
        self.task_inp.delete(0, tk.END)
        self._refresh_tasks()
        self._update_stats()

    def _toggle_task(self, event=None):
        sel = self.task_list.curselection()
        if not sel:
            return
        idx = sel[0]
        tasks = self.cfg.get("tasks", [])
        if idx < len(tasks):
            tasks[idx]["done"] = not tasks[idx]["done"]
            self.cfg["tasks"] = tasks
            save_config(self.cfg)
            self._refresh_tasks()

    def _refresh_tasks(self):
        self.task_list.delete(0, tk.END)
        for t in self.cfg.get("tasks", []):
            prefix = "✓ " if t["done"] else "○ "
            self.task_list.insert(tk.END, prefix + t["text"])
            if t["done"]:
                self.task_list.itemconfig(tk.END, fg=COLORS["muted"])

    # ── MEMORY ────────────────────────────────────────────────────
    def _add_memory(self, text):
        text = text.strip().strip('"\'')
        mems = self.cfg.get("memories", [])
        if text and text.lower() not in [m.lower() for m in mems]:
            mems.append(text)
            if len(mems) > 60:
                mems.pop(0)
            self.cfg["memories"] = mems
            save_config(self.cfg)
            self._refresh_memories()
            self._update_stats()

    def _refresh_memories(self):
        self.mem_list.delete(0, tk.END)
        for m in self.cfg.get("memories", []):
            self.mem_list.insert(tk.END, f"  {m[:35]}{'...' if len(m)>35 else ''}")

    def _clear_memory(self):
        if messagebox.askyesno("Clear Memory", "Wipe all memories?"):
            self.cfg["memories"] = []
            save_config(self.cfg)
            self._refresh_memories()
            self._update_stats()
            self._add_chat("system", "Memory bank wiped")

    # ── MODE ──────────────────────────────────────────────────────
    def _set_mode(self, m):
        self.mode = m
        self.mode_label.config(text=f"MODE: {m.upper()}")
        labels = {"General":"GEN","Code/Dev":"DEV","Research":"RES","Projects":"PRJ",
                  "Analysis":"ANA","Screen":"SCR","File Edit":"FIL","Advisor":"ADV"}
        self.mode_var.set(labels.get(m, m[:3].upper()))
        self._add_chat("system", f"Mode → {m.upper()}")

    # ── VOICE ─────────────────────────────────────────────────────
    def _toggle_voice(self):
        self._add_chat("system", "Voice output toggle — use system TTS if available")

    def _toggle_mic(self):
        self._add_chat("system", "Voice input: speak after clicking mic (Chrome-based recognition not available in desktop app — use hotkey Ctrl+Shift+V on Windows)")

    # ── QUICK CMDS ────────────────────────────────────────────────
    def _quick_cmd(self, cmd):
        cmd_map = {
            "/plan day":   "Plan my day and help me prioritize my tasks",
            "/code":       "Help me write code for: ",
            "/research":   "Research and summarize: ",
            "/analyze":    "Analyze this: ",
            "/debug":      "Debug this error: ",
            "/write":      "Help me write: ",
            "/memory":     "What do you remember about me?",
            "/clear":      None,
            "/prioritize tasks": f"Prioritize and give me an action plan for these tasks:\n{chr(10).join(t['text'] for t in self.cfg.get('tasks',[]))}"
        }
        if cmd == "/clear":
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.history = []
            self._add_chat("system", "Chat cleared — memory and tasks retained")
            return
        text = cmd_map.get(cmd, cmd)
        if text:
            self.inp.delete("1.0", tk.END)
            self.inp.insert("1.0", text)
            self.inp.config(fg=COLORS["text"])
            self.inp.focus_set()

    # ── INPUT HELPERS ─────────────────────────────────────────────
    def _inp_focus_in(self, event):
        if self.inp.get("1.0", tk.END).strip() == "State your command, sir...":
            self.inp.delete("1.0", tk.END)
            self.inp.config(fg=COLORS["text"])

    def _inp_focus_out(self, event):
        if not self.inp.get("1.0", tk.END).strip():
            self.inp.insert("1.0", "State your command, sir...")
            self.inp.config(fg=COLORS["muted"])

    def _on_enter(self, event):
        if not event.state & 0x1:  # No shift
            self._send()
            return "break"

    # ── HOTKEYS ───────────────────────────────────────────────────
    def _setup_hotkeys(self):
        if not HAS_KEYBOARD:
            return
        try:
            keyboard.add_hotkey("ctrl+shift+j", self._toggle_window)
            keyboard.add_hotkey("ctrl+shift+s", self._scan_screen)
        except Exception:
            pass

    def _toggle_window(self):
        if self.root.state() == "iconic":
            self.root.after(0, self.root.deiconify)
        else:
            self.root.after(0, self.root.iconify)

    # ── STATS / TICK ──────────────────────────────────────────────
    def _update_stats(self):
        mems = len(self.cfg.get("memories", []))
        tasks = len(self.cfg.get("tasks", []))
        self._stats_vars["msgs"].set(str(self.msg_count))
        self._stats_vars["mems"].set(str(mems))
        self._stats_vars["tasks"].set(str(tasks))
        self.msg_var.set(str(self.msg_count))
        self.mem_var.set(str(mems))

    def _tick(self):
        now = datetime.now()
        ts = now.strftime("%H:%M:%S")
        self.clk_label.config(text=ts)
        self.sb_time.config(text=ts)
        elapsed = int(time.time() - self.session_start)
        m, s = divmod(elapsed, 60)
        self._stats_vars["time"].set(f"{m:02d}:{s:02d}")
        self.root.after(1000, self._tick)

    def _boot_message(self):
        key = self.cfg.get("api_key", "")
        if not key:
            self._add_chat("assistant",
                "JARVIS online. Welcome, sir.\n\n"
                "⚠  API KEY REQUIRED\n\n"
                "To activate AI systems:\n"
                "1. Get a free key at console.anthropic.com\n"
                "2. Open jarvis_desktop.py in a text editor\n"
                "3. Find load_config() and add your key, OR\n"
                "4. Edit ~/.jarvis_config.json and set api_key\n\n"
                "All other features (tasks, notes, memory) work without a key."
            )
        else:
            mems = self.cfg.get("memories", [])
            mem_note = f"\nMemory bank: {len(mems)} records loaded." if mems else ""
            self._add_chat("assistant",
                f"JARVIS online. All systems nominal.{mem_note}\n\n"
                "Ready to assist. Select a mode, scan your screen, open a file, or state your command.\n\n"
                "Hotkeys:\n"
                "  Ctrl+Shift+J — toggle window\n"
                "  Ctrl+Shift+S — scan screen\n"
                "  Double-click task — toggle done"
            )

    def run(self):
        # Settings for clean close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self._save_note()
        if HAS_KEYBOARD:
            try:
                keyboard.unhook_all()
            except:
                pass
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════
# SETTINGS DIALOG (first run / API key)
# ══════════════════════════════════════════════════════════════════
def show_settings(cfg):
    """Show settings window to configure API key"""
    win = tk.Toplevel()
    win.title("JARVIS — Settings")
    win.configure(bg=COLORS["bg"])
    win.geometry("500x300")
    win.resizable(False, False)

    tk.Label(win, text="J.A.R.V.I.S CONFIGURATION", font=("Courier New",13,"bold"),
             fg=COLORS["blue"], bg=COLORS["bg"]).pack(pady=20)

    tk.Label(win, text="Anthropic API Key:", font=FONT_MONO,
             fg=COLORS["text"], bg=COLORS["bg"]).pack(anchor="w", padx=30)
    key_var = tk.StringVar(value=cfg.get("api_key",""))
    key_entry = tk.Entry(win, textvariable=key_var, width=50, show="*",
                          font=FONT_MONO, bg=COLORS["bg3"], fg=COLORS["text"],
                          insertbackground=COLORS["blue"], bd=1)
    key_entry.pack(padx=30, pady=6, ipady=4, fill=tk.X)

    tk.Label(win, text="Get your key at: console.anthropic.com", font=FONT_LABEL,
             fg=COLORS["muted"], bg=COLORS["bg"]).pack(anchor="w", padx=30)

    def save():
        cfg["api_key"] = key_var.get().strip()
        save_config(cfg)
        win.destroy()

    tk.Button(win, text="SAVE & INITIALIZE", font=("Courier New",10,"bold"),
              fg=COLORS["blue"], bg=COLORS["bg2"], bd=1, relief=tk.FLAT,
              padx=20, pady=8, cursor="hand2", command=save).pack(pady=20)


# ══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    cfg = load_config()

    # Check deps
    missing = []
    if not HAS_ANTHROPIC: missing.append("anthropic")
    if not HAS_PIL: missing.append("pillow")
    if not HAS_KEYBOARD: missing.append("keyboard")

    if missing:
        print(f"\n⚠  Missing packages: {', '.join(missing)}")
        print(f"Run: pip install {' '.join(missing)}\n")
        print("Starting with limited functionality...\n")

    app = JarvisApp()

    # Show settings on first run
    if not cfg.get("api_key"):
        app.root.after(600, lambda: show_settings(cfg))

    app.run()
