"""
J.A.R.V.I.S — Chat Interface
Clean chat with animated message entry.
"""

import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime
from ui.themes import COLORS, FONTS


class ChatDisplay:
    """Clean scrollable chat with fade-in animations."""

    def __init__(self, parent):
        self.parent = parent
        self.widget = scrolledtext.ScrolledText(
            parent, bg=COLORS["bg"], fg=COLORS["text"],
            font=FONTS["msg"], bd=0, padx=20, pady=12,
            wrap=tk.WORD, state=tk.DISABLED,
            highlightthickness=0, relief=tk.FLAT,
            insertbackground=COLORS["primary"],
            selectbackground=COLORS["primary_dim"],
        )
        # Style the scrollbar
        self.widget.vbar.config(
            bg=COLORS["bg2"], troughcolor=COLORS["bg"],
            activebackground=COLORS["primary_dim"],
            highlightthickness=0, bd=0, width=8,
        )

        # Tag styles — clean and minimal
        self.widget.tag_config("user_lbl",
            foreground=COLORS["accent"], font=("Segoe UI Semibold", 9))
        self.widget.tag_config("user_msg",
            foreground=COLORS["user_msg"], font=FONTS["msg"],
            lmargin1=12, lmargin2=12, spacing3=8)
        self.widget.tag_config("jar_lbl",
            foreground=COLORS["primary"], font=("Segoe UI Semibold", 9))
        self.widget.tag_config("jar_msg",
            foreground=COLORS["jar_msg"], font=FONTS["msg"],
            lmargin1=12, lmargin2=12, spacing3=8)
        self.widget.tag_config("sys_msg",
            foreground=COLORS["text_dim"], font=FONTS["msg_xs"],
            justify=tk.CENTER, spacing1=4, spacing3=4)
        self.widget.tag_config("thinking",
            foreground=COLORS["primary_dim"], font=FONTS["msg_sm"],
            lmargin1=12)
        self.widget.tag_config("voice_msg",
            foreground=COLORS["green"], font=FONTS["msg_sm"],
            lmargin1=12)
        self.widget.tag_config("divider",
            foreground=COLORS["border"], font=("Segoe UI", 2))

    def pack(self, **kwargs):
        self.widget.pack(**kwargs)

    def add_message(self, role: str, text: str):
        """Add a message with smooth animation."""
        self.widget.config(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M")

        if role == "user":
            self.widget.insert(tk.END, f"\n  You  ·  {ts}\n", "user_lbl")
            self._animate_text(text + "\n", "user_msg")
        elif role == "assistant":
            self.widget.insert(tk.END, f"\n  JARVIS  ·  {ts}\n", "jar_lbl")
            self._animate_text(text + "\n", "jar_msg")
        elif role == "system":
            self.widget.insert(tk.END, f"\n{text}\n", "sys_msg")
        elif role == "thinking":
            self.widget.insert(tk.END, f"\n  ◌  {text}\n", "thinking")
        elif role == "voice":
            self.widget.insert(tk.END, f"\n  🎤  {text}\n", "voice_msg")

        self.widget.config(state=tk.DISABLED)
        self.widget.see(tk.END)

    def _animate_text(self, text: str, tag: str, index: int = 0, chunk_size: int = 80):
        """Animate text appearing in chunks for a typing effect."""
        if index >= len(text):
            self.widget.config(state=tk.DISABLED)
            self.widget.see(tk.END)
            return

        end = min(index + chunk_size, len(text))
        chunk = text[index:end]

        self.widget.config(state=tk.NORMAL)
        self.widget.insert(tk.END, chunk, tag)
        self.widget.see(tk.END)

        if end < len(text):
            self.parent.after(8, lambda: self._animate_text(text, tag, end, chunk_size))
        else:
            self.widget.config(state=tk.DISABLED)

    def remove_last_thinking(self):
        self.widget.config(state=tk.NORMAL)
        content = self.widget.get("1.0", tk.END)
        idx = content.rfind("  ◌  ")
        if idx != -1:
            line_start = content.rfind("\n", 0, idx)
            line_end = content.find("\n", idx)
            if line_end != -1:
                start_line = content[:line_start].count("\n") + 1
                end_line = content[:line_end].count("\n") + 2
                self.widget.delete(f"{start_line}.0", f"{end_line}.0")
        self.widget.config(state=tk.DISABLED)

    def clear(self):
        self.widget.config(state=tk.NORMAL)
        self.widget.delete("1.0", tk.END)
        self.widget.config(state=tk.DISABLED)


class ChatInput:
    """Clean minimal chat input with rounded feel."""

    PLACEHOLDER = "Ask JARVIS anything..."

    def __init__(self, parent, on_send, on_mic=None):
        self.on_send_callback = on_send

        # Outer frame with border effect
        self.outer = tk.Frame(parent, bg=COLORS["border"], padx=1, pady=1)

        self.frame = tk.Frame(self.outer, bg=COLORS["card"])

        # Text input — clean, no arrows or symbols
        self.text = tk.Text(
            self.frame, bg=COLORS["card"], fg=COLORS["text"],
            font=FONTS["msg"], bd=0, height=2, padx=16, pady=12,
            wrap=tk.WORD, insertbackground=COLORS["primary"],
            highlightthickness=0, relief=tk.FLAT,
        )
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text.insert("1.0", self.PLACEHOLDER)
        self.text.config(fg=COLORS["text_dim"])
        self.text.bind("<FocusIn>", self._focus_in)
        self.text.bind("<FocusOut>", self._focus_out)
        self.text.bind("<Return>", self._on_enter)
        self.text.bind("<Shift-Return>", lambda e: None)

        # Button area
        btn_frame = tk.Frame(self.frame, bg=COLORS["card"])
        btn_frame.pack(side=tk.RIGHT, padx=8, pady=8)

        if on_mic:
            self.mic_btn = tk.Button(
                btn_frame, text="🎤", font=("Segoe UI", 13),
                fg=COLORS["text_dim"], bg=COLORS["card"],
                activeforeground=COLORS["primary"],
                activebackground=COLORS["card"],
                bd=0, cursor="hand2", command=on_mic,
                relief=tk.FLAT,
            )
            self.mic_btn.pack(side=tk.LEFT, padx=(0, 4))
            self.mic_btn.bind("<Enter>", lambda e: self.mic_btn.config(fg=COLORS["primary"]))
            self.mic_btn.bind("<Leave>", lambda e: self.mic_btn.config(fg=COLORS["text_dim"]))

        self.send_btn = tk.Button(
            btn_frame, text="→", font=("Segoe UI", 16),
            fg=COLORS["primary"], bg=COLORS["card"],
            activeforeground=COLORS["white"],
            activebackground=COLORS["card"],
            bd=0, cursor="hand2", command=self._send,
            relief=tk.FLAT,
        )
        self.send_btn.pack(side=tk.LEFT)
        self.send_btn.bind("<Enter>", lambda e: self.send_btn.config(fg=COLORS["white"]))
        self.send_btn.bind("<Leave>", lambda e: self.send_btn.config(fg=COLORS["primary"]))

        self.frame.pack(fill=tk.BOTH, expand=True)

    def pack(self, **kwargs):
        self.outer.pack(**kwargs)

    def get_text(self) -> str:
        text = self.text.get("1.0", tk.END).strip()
        if text == self.PLACEHOLDER:
            return ""
        return text

    def clear(self):
        self.text.delete("1.0", tk.END)

    def set_text(self, text: str):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", text)
        self.text.config(fg=COLORS["text"])
        self.text.focus_set()

    def set_enabled(self, enabled: bool):
        self.send_btn.config(state=tk.NORMAL if enabled else tk.DISABLED)

    def _send(self):
        text = self.get_text()
        if text:
            self.clear()
            self.on_send_callback(text)

    def _on_enter(self, event):
        if not event.state & 0x1:
            self._send()
            return "break"

    def _focus_in(self, event):
        if self.text.get("1.0", tk.END).strip() == self.PLACEHOLDER:
            self.text.delete("1.0", tk.END)
            self.text.config(fg=COLORS["text"])
        # Glow border on focus
        self.outer.config(bg=COLORS["primary_dim"])

    def _focus_out(self, event):
        if not self.text.get("1.0", tk.END).strip():
            self.text.insert("1.0", self.PLACEHOLDER)
            self.text.config(fg=COLORS["text_dim"])
        self.outer.config(bg=COLORS["border"])
