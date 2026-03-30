"""
J.A.R.V.I.S — UI Components
Animated arc reactor, glass panels, smooth transitions.
"""

import math
import tkinter as tk
from ui.themes import COLORS, FONTS


class ArcReactor:
    """Animated arc reactor with pulsing glow effect."""

    def __init__(self, parent, size=50):
        self.canvas = tk.Canvas(
            parent, width=size, height=size,
            bg=COLORS["bg2"], highlightthickness=0,
        )
        self.size = size
        self.cx = size // 2
        self.cy = size // 2
        self._angle = 0
        self._pulse = 0
        self._pulse_dir = 1
        self._animate()

    def pack(self, **kwargs):
        self.canvas.pack(**kwargs)

    def _animate(self):
        c = self.canvas
        cx, cy = self.cx, self.cy
        c.delete("all")

        # Pulse effect
        self._pulse += 0.03 * self._pulse_dir
        if self._pulse > 1:
            self._pulse_dir = -1
        elif self._pulse < 0:
            self._pulse_dir = 1

        r = self.size // 2 - 3
        glow_alpha = int(30 + 25 * self._pulse)

        # Outer glow ring
        glow_color = f"#{0:02x}{int(180 + 40*self._pulse):02x}{int(220 + 35*self._pulse):02x}"
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=glow_color, width=2)

        # Inner rings
        for i, (radius_frac, width) in enumerate([(0.7, 1.5), (0.45, 1)]):
            ir = int(r * radius_frac)
            c.create_oval(cx-ir, cy-ir, cx+ir, cy+ir,
                         outline=COLORS["primary_dim"], width=width)

        # Core — pulsing
        cr = int(r * 0.2 + 2 * self._pulse)
        core_brightness = int(200 + 55 * self._pulse)
        core_color = f"#00{core_brightness:02x}ff"
        c.create_oval(cx-cr, cy-cr, cx+cr, cy+cr,
                     fill=core_color, outline="", width=0)

        # Rotating beams (3 of them)
        for offset in [0, 120, 240]:
            angle = math.radians(self._angle + offset)
            x1 = cx + int(r * 0.3) * math.cos(angle)
            y1 = cy + int(r * 0.3) * math.sin(angle)
            x2 = cx + int(r * 0.85) * math.cos(angle)
            y2 = cy + int(r * 0.85) * math.sin(angle)
            c.create_line(x1, y1, x2, y2, fill=COLORS["primary_dim"], width=1)

        self._angle = (self._angle + 2) % 360
        c.after(40, self._animate)


class GlassCard:
    """A frosted-glass style card container."""

    def __init__(self, parent, title=None, accent_color=None):
        self.accent = accent_color or COLORS["primary"]
        self.frame = tk.Frame(parent, bg=COLORS["card"])

        if title:
            # Minimal header with accent line
            header = tk.Frame(self.frame, bg=COLORS["card"])
            header.pack(fill=tk.X, padx=16, pady=(12, 0))

            # Small accent dot
            tk.Label(
                header, text="●", font=("Segoe UI", 6),
                fg=self.accent, bg=COLORS["card"],
            ).pack(side=tk.LEFT, padx=(0, 6))

            tk.Label(
                header, text=title.upper(),
                font=FONTS["label_md"], fg=COLORS["text_dim"],
                bg=COLORS["card"],
            ).pack(side=tk.LEFT)

        # Content area
        self.content = tk.Frame(self.frame, bg=COLORS["card"])
        self.content.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

    def pack(self, **kwargs):
        # Add subtle spacing between cards
        if "pady" not in kwargs:
            kwargs["pady"] = (0, 6)
        self.frame.pack(**kwargs)

    def grid(self, **kwargs):
        self.frame.grid(**kwargs)


class AnimatedButton(tk.Canvas):
    """Button with hover glow animation."""

    def __init__(self, parent, text, command=None,
                 color="primary", width=None, height=36):
        self.fg = COLORS.get(color, COLORS["primary"])
        self.bg = COLORS["bg3"]
        self.hover_bg = COLORS["card_hover"]
        self._command = command
        self._text = text
        self._hovering = False

        super().__init__(
            parent, height=height,
            bg=self.bg, highlightthickness=0,
            cursor="hand2",
        )
        if width:
            self.config(width=width)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        bg = self.hover_bg if self._hovering else self.bg

        # Rounded rectangle background
        r = 6
        self.create_rounded_rect(2, 2, w-2, h-2, r, fill=bg, outline=self.fg if self._hovering else COLORS["border"])

        # Text
        self.create_text(w//2, h//2, text=self._text,
                        font=FONTS["btn"], fill=self.fg)

    def create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        self.create_polygon(
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1,
            smooth=True, **kwargs,
        )

    def _on_enter(self, e):
        self._hovering = True
        self._draw()

    def _on_leave(self, e):
        self._hovering = False
        self._draw()

    def _on_click(self, e):
        if self._command:
            self._command()


class StatusDot(tk.Frame):
    """Animated pulsing status indicator."""

    def __init__(self, parent, text="ONLINE", color="green"):
        super().__init__(parent, bg=COLORS["bg2"])
        self.color = COLORS.get(color, color)
        self.dot = tk.Label(self, text="●", font=("Segoe UI", 7),
                           fg=self.color, bg=COLORS["bg2"])
        self.dot.pack(side=tk.LEFT, padx=(0, 4))
        self.label = tk.Label(self, text=text, font=FONTS["label"],
                             fg=self.color, bg=COLORS["bg2"])
        self.label.pack(side=tk.LEFT)
        self._pulse_dot()

    def _pulse_dot(self):
        # Subtle pulse between dim and bright
        import time
        phase = (math.sin(time.time() * 2) + 1) / 2
        r = int(16 + 239 * phase) if self.color == COLORS["green"] else 200
        g = int(185 + 70 * phase) if self.color == COLORS["green"] else 200
        b = int(129 + 50 * phase) if self.color == COLORS["green"] else 200

        if self.color == COLORS["green"]:
            self.dot.config(fg=f"#{r:02x}{g:02x}{b:02x}")
        self.after(100, self._pulse_dot)
