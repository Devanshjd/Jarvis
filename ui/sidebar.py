"""
J.A.R.V.I.S — Sidebar
Clean collapsible sidebar with minimal controls.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox
from ui.themes import COLORS, FONTS
from ui.components import GlassCard
from core.brain import MODES


class Sidebar:
    """Single clean sidebar that slides out from the right."""

    def __init__(self, parent, app):
        self.app = app
        self.expanded_width = 332
        self.collapsed_width = 72
        self.current_width = self.expanded_width
        self.frame = tk.Frame(parent, bg=COLORS["bg"], width=self.current_width)
        self.frame.pack_propagate(False)
        self.is_visible = True
        self.is_expanded = True
        self._animating = False
        self._toggle_callback = None

        self._build()

    def _build(self):
        self.expanded_container = tk.Frame(self.frame, bg=COLORS["bg"])
        self.expanded_container.pack(fill=tk.BOTH, expand=True, padx=(10, 12), pady=10)
        self.collapsed_container = tk.Frame(self.frame, bg=COLORS["bg"])

        header = tk.Frame(self.expanded_container, bg=COLORS["bg"])
        header.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            header,
            text="OPERATOR STACK",
            font=FONTS["label"],
            fg=COLORS["text_dim"],
            bg=COLORS["bg"],
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Modes, live stats, tasks, memory, and files",
            font=FONTS["msg_xs"],
            fg=COLORS["text_muted"],
            bg=COLORS["bg"],
        ).pack(anchor="w", pady=(3, 0))

        self._build_modes(self.expanded_container)
        self._build_quick_stats(self.expanded_container)
        self._build_tasks(self.expanded_container)
        self._build_memory(self.expanded_container)
        self._build_files(self.expanded_container)
        self._build_compact()

    def _build_compact(self):
        rail = tk.Frame(
            self.collapsed_container,
            bg=COLORS["border_soft"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["border"],
        )
        rail.pack(fill=tk.BOTH, expand=True, padx=(8, 10), pady=10)

        inner = tk.Frame(rail, bg=COLORS["card"])
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        tk.Label(
            inner,
            text="STACK",
            font=FONTS["label"],
            fg=COLORS["text_dim"],
            bg=COLORS["card"],
        ).pack(anchor="n", pady=(14, 6))

        self.compact_mode_var = tk.StringVar(value="GEN")
        tk.Label(
            inner,
            textvariable=self.compact_mode_var,
            font=FONTS["btn"],
            fg=COLORS["primary"],
            bg=COLORS["card"],
        ).pack(anchor="n", pady=4)

        self.compact_status_var = tk.StringVar(value="LIVE")
        tk.Label(
            inner,
            textvariable=self.compact_status_var,
            font=FONTS["label"],
            fg=COLORS["text_dim"],
            bg=COLORS["card"],
        ).pack(anchor="n", pady=4)

        self.compact_task_var = tk.StringVar(value="T 0")
        tk.Label(
            inner,
            textvariable=self.compact_task_var,
            font=FONTS["mono_xs"],
            fg=COLORS["accent"],
            bg=COLORS["card"],
        ).pack(anchor="n", pady=(18, 4))

        self.compact_voice_var = tk.StringVar(value="V OFF")
        tk.Label(
            inner,
            textvariable=self.compact_voice_var,
            font=FONTS["mono_xs"],
            fg=COLORS["text_muted"],
            bg=COLORS["card"],
        ).pack(anchor="n", pady=4)

    def _build_modes(self, parent):
        card = GlassCard(parent, "Mode")
        card.pack(fill=tk.X)

        self.mode_var = tk.StringVar(value="General")
        self.mode_buttons = {}

        for mode in MODES:
            btn = tk.Radiobutton(
                card.content, text=f"  {mode}",
                variable=self.mode_var, value=mode,
                font=FONTS["label_md"],
                fg=COLORS["text_dim"], bg=COLORS["panel"],
                selectcolor=COLORS["panel_alt"],
                activeforeground=COLORS["primary"],
                activebackground=COLORS["panel"],
                anchor="w", padx=10, pady=5,
                cursor="hand2", relief=tk.FLAT,
                command=lambda m=mode: self.app.set_mode(m),
            )
            btn.pack(fill=tk.X, pady=2)
            self.mode_buttons[mode] = btn

    def _build_quick_stats(self, parent):
        card = GlassCard(parent, "Status")
        card.pack(fill=tk.X)

        self.stat_vars = {}
        stats = [("msgs", "Messages"), ("mems", "Memories"),
                 ("tasks", "Tasks"), ("voice", "Voice")]

        for key, label in stats:
            row = tk.Frame(card.content, bg=COLORS["panel"])
            row.pack(fill=tk.X, pady=2)

            tk.Label(row, text=label, font=FONTS["label_md"],
                     fg=COLORS["text_dim"], bg=COLORS["panel"],
                     anchor="w").pack(side=tk.LEFT, padx=(4, 0))

            v = tk.StringVar(value="OFF" if key == "voice" else "0")
            self.stat_vars[key] = v

            tk.Label(row, textvariable=v, font=FONTS["stat_sm"],
                     fg=COLORS["primary"], bg=COLORS["panel"],
                     anchor="e").pack(side=tk.RIGHT, padx=(0, 4))

        # Session timer
        self.time_var = tk.StringVar(value="00:00")
        tk.Label(card.content, textvariable=self.time_var,
                 font=FONTS["mono_sm"], fg=COLORS["text_dim"],
                 bg=COLORS["card"]).pack(pady=(6, 0), anchor="w")

    def _build_tasks(self, parent):
        card = GlassCard(parent, "Tasks", COLORS["accent"])
        card.pack(fill=tk.X)

        self.task_list = tk.Listbox(
            card.content, bg=COLORS["panel"], fg=COLORS["text"],
            font=FONTS["msg_sm"], bd=0, height=5,
            highlightthickness=0, selectbackground=COLORS["card_hover"],
            activestyle="none", relief=tk.FLAT,
        )
        self.task_list.pack(fill=tk.X, pady=(0, 6))
        self.task_list.bind("<Double-Button-1>", lambda e: self.app.toggle_task())

        # Add task — clean inline input
        add_frame = tk.Frame(card.content, bg=COLORS["panel"])
        add_frame.pack(fill=tk.X)

        self.task_input = tk.Entry(
            add_frame, bg=COLORS["panel"], fg=COLORS["text"],
            font=FONTS["msg_sm"], bd=0,
            insertbackground=COLORS["primary"],
        )
        self.task_input.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=4)
        self.task_input.insert(0, "Add task...")
        self.task_input.config(fg=COLORS["text_dim"])
        self.task_input.bind("<FocusIn>", lambda e: self._task_focus_in())
        self.task_input.bind("<FocusOut>", lambda e: self._task_focus_out())
        self.task_input.bind("<Return>", lambda e: self.app.add_task())

        tk.Button(
            add_frame, text="+", font=("Segoe UI", 12),
            fg=COLORS["accent"], bg=COLORS["panel"], bd=0,
            cursor="hand2", relief=tk.FLAT,
            activeforeground=COLORS["gold"], activebackground=COLORS["panel"],
            command=self.app.add_task,
        ).pack(side=tk.RIGHT, padx=4)

    def _task_focus_in(self):
        if self.task_input.get() == "Add task...":
            self.task_input.delete(0, tk.END)
            self.task_input.config(fg=COLORS["text"])

    def _task_focus_out(self):
        if not self.task_input.get().strip():
            self.task_input.insert(0, "Add task...")
            self.task_input.config(fg=COLORS["text_dim"])

    def _build_memory(self, parent):
        card = GlassCard(parent, "Memory", COLORS["purple"])
        card.pack(fill=tk.X)

        self.mem_list = tk.Listbox(
            card.content, bg=COLORS["panel"], fg=COLORS["primary_dim"],
            font=FONTS["msg_xs"], bd=0, height=3,
            highlightthickness=0, selectbackground=COLORS["card_hover"],
            activestyle="none", relief=tk.FLAT,
        )
        self.mem_list.pack(fill=tk.X, pady=(0, 4))

        tk.Button(
            card.content, text="Clear Memory", font=FONTS["label"],
            fg=COLORS["red"], bg=COLORS["card"], bd=0,
            cursor="hand2", relief=tk.FLAT,
            activeforeground=COLORS["red"], activebackground=COLORS["card"],
            command=self.app.clear_memory,
        ).pack(anchor="w")

    def _build_files(self, parent):
        card = GlassCard(parent, "Files", COLORS["green"])
        card.pack(fill=tk.X)

        btn_frame = tk.Frame(card.content, bg=COLORS["card"])
        btn_frame.pack(fill=tk.X)

        for label, cmd in [("Open File", self.app.open_file),
                           ("Analyze", self.app.analyze_file)]:
            btn = tk.Button(
                btn_frame, text=label, font=FONTS["btn"],
                fg=COLORS["green"], bg=COLORS["panel"], bd=0,
                cursor="hand2", relief=tk.FLAT, padx=12, pady=4,
                activeforeground=COLORS["primary"],
                activebackground=COLORS["panel"],
                command=cmd,
            )
            btn.pack(side=tk.LEFT, padx=(0, 4), pady=2)

        self.file_status = tk.Label(
            card.content, text="No file loaded", font=FONTS["label"],
            fg=COLORS["text_dim"], bg=COLORS["card"],
        )
        self.file_status.pack(anchor="w", pady=(4, 0))

    # ── Public API ────────────────────────────────────────────

    def refresh_tasks(self, tasks: list):
        self.task_list.delete(0, tk.END)
        for t in tasks:
            prefix = "✓  " if t["done"] else "○  "
            self.task_list.insert(tk.END, prefix + t["text"])
            if t["done"]:
                self.task_list.itemconfig(tk.END, fg=COLORS["text_dim"])

    def get_selected_task_index(self):
        sel = self.task_list.curselection()
        return sel[0] if sel else None

    def get_task_input(self) -> str:
        text = self.task_input.get().strip()
        return "" if text == "Add task..." else text

    def clear_task_input(self):
        self.task_input.delete(0, tk.END)

    def refresh_memories(self, memories: list):
        self.mem_list.delete(0, tk.END)
        for m in memories:
            self.mem_list.insert(tk.END, f"  {m[:40]}{'...' if len(m) > 40 else ''}")

    def update_stats(self, **kwargs):
        for key, value in kwargs.items():
            if key == "time":
                self.time_var.set(str(value))
            elif key in self.stat_vars:
                self.stat_vars[key].set(str(value))
        tasks = self.stat_vars.get("tasks")
        voice = self.stat_vars.get("voice")
        if tasks is not None:
            self.compact_task_var.set(f"T {tasks.get()}")
        if voice is not None:
            self.compact_voice_var.set(f"V {voice.get()}")

    def set_file_status(self, text: str, color: str = "text_dim"):
        self.file_status.config(text=text, fg=COLORS.get(color, color))

    def set_mode_display(self, mode: str):
        short = (mode or "GEN")[:3].upper()
        self.compact_mode_var.set(short)
        if hasattr(self, "mode_var"):
            self.mode_var.set(mode)

    def set_compact_status(self, text: str):
        self.compact_status_var.set(text[:8].upper())

    def _show_expanded(self, expanded: bool):
        expanded_manager = self.expanded_container.winfo_manager()
        compact_manager = self.collapsed_container.winfo_manager()
        if expanded:
            if compact_manager:
                self.collapsed_container.pack_forget()
            if not expanded_manager:
                self.expanded_container.pack(fill=tk.BOTH, expand=True, padx=(10, 12), pady=10)
        else:
            if expanded_manager:
                self.expanded_container.pack_forget()
            if not compact_manager:
                self.collapsed_container.pack(fill=tk.BOTH, expand=True)

    def _finish_toggle(self, expanded: bool):
        self.is_expanded = expanded
        self.is_visible = expanded
        self._animating = False
        self._show_expanded(expanded)
        self.frame.config(width=self.expanded_width if expanded else self.collapsed_width)
        if self._toggle_callback:
            callback = self._toggle_callback
            self._toggle_callback = None
            callback(expanded)

    def _animate_toggle(self, target_width: int, expand: bool):
        delta = target_width - self.current_width
        if abs(delta) <= 8:
            self.current_width = target_width
            self._finish_toggle(expand)
            return

        step = max(10, abs(delta) // 4)
        self.current_width += step if delta > 0 else -step
        midpoint = (self.expanded_width + self.collapsed_width) // 2
        self._show_expanded(self.current_width > midpoint)
        self.frame.config(width=self.current_width)
        self.frame.after(14, lambda: self._animate_toggle(target_width, expand))

    def toggle(self, callback=None):
        """Collapse into a telemetry rail or expand back out."""
        if self._animating:
            return

        expand = not self.is_expanded
        target_width = self.expanded_width if expand else self.collapsed_width
        self._toggle_callback = callback
        self._animating = True
        self._animate_toggle(target_width, expand)

    def grid(self, **kwargs):
        self.frame.grid(**kwargs)
