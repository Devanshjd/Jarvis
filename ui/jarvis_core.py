"""
J.A.R.V.I.S — Cinematic AI Core
Full animated HUD with rotating rings, particle sparks,
voice-reactive waveform, mode-based color shifting, and
corner bracket overlays.

Modes:
    idle      — calm cyan/blue holographic core
    listening — green active pulse
    thinking  — purple spinning analysis
    speaking  — orange glowing vibration
    alert     — red warning
"""

import math
import random
import tkinter as tk


class JarvisCore(tk.Canvas):

    MODE_COLORS = {
        "idle": {
            "primary":   "#4fdcff",
            "secondary": "#1b8fb8",
            "glow":      "#7fe8ff",
            "bg":        "#050b12",
        },
        "listening": {
            "primary":   "#5fffd2",
            "secondary": "#1ea88b",
            "glow":      "#98ffe7",
            "bg":        "#04110d",
        },
        "thinking": {
            "primary":   "#9c7bff",
            "secondary": "#5a45b8",
            "glow":      "#c4b2ff",
            "bg":        "#090612",
        },
        "speaking": {
            "primary":   "#ffb347",
            "secondary": "#cc7a00",
            "glow":      "#ffd38c",
            "bg":        "#120b03",
        },
        "alert": {
            "primary":   "#ff5b5b",
            "secondary": "#b82f2f",
            "glow":      "#ff9a9a",
            "bg":        "#140505",
        },
    }

    def __init__(self, parent, width=420, height=420):
        super().__init__(
            parent, width=width, height=height,
            bg="#050b12", highlightthickness=0, bd=0,
        )

        self.w = width
        self.h = height
        self.cx = width / 2
        self.cy = height / 2

        self.base_radius = min(width, height) * 0.155
        self.phase = 0.0
        self.rotation = 0.0
        self.mode = "idle"

        # Voice reactivity
        self.voice_level = 0.0
        self.target_voice_level = 0.0
        self.thinking_level = 0.0
        self.listening_level = 0.0
        self.alert_level = 0.0

        # Ring state
        self.ring_offsets = [0.0, 90.0, 180.0, 270.0]
        self.ring_speeds = [0.9, -0.55, 1.25, -0.35]

        # Particles
        self.particles = []
        self.max_particles = 48
        self._seed_particles()

        self._running = True
        self.after(16, self._animate)

    # ── Public API ───────────────────────────────────────────

    def set_mode(self, mode: str):
        if mode in self.MODE_COLORS:
            self.mode = mode

    def set_voice_level(self, level: float):
        self.target_voice_level = max(0.0, min(1.0, float(level)))

    def set_speaking(self, speaking: bool):
        if speaking:
            self.set_mode("speaking")
            self.target_voice_level = max(self.target_voice_level, 0.6)
        else:
            if self.mode == "speaking":
                self.set_mode("idle")
            self.target_voice_level = 0.0

    def set_listening(self, listening: bool):
        if listening:
            self.set_mode("listening")
            self.listening_level = 1.0
        else:
            if self.mode == "listening":
                self.set_mode("idle")
            self.listening_level = 0.0

    def set_thinking(self, thinking: bool):
        if thinking:
            self.set_mode("thinking")
            self.thinking_level = 1.0
        else:
            if self.mode == "thinking":
                self.set_mode("idle")
            self.thinking_level = 0.0

    def set_alert(self, alert: bool):
        if alert:
            self.set_mode("alert")
            self.alert_level = 1.0
        else:
            if self.mode == "alert":
                self.set_mode("idle")
            self.alert_level = 0.0

    def pulse_once(self):
        self.target_voice_level = min(1.0, self.target_voice_level + 0.5)

    def stop(self):
        self._running = False

    # ── Particles ────────────────────────────────────────────

    def _seed_particles(self):
        self.particles.clear()
        for _ in range(self.max_particles):
            self.particles.append(self._make_particle())

    def _make_particle(self):
        angle = random.uniform(0, math.tau)
        dist = random.uniform(self.base_radius * 0.8, self.base_radius * 2.2)
        return {
            "angle": angle,
            "dist":  dist,
            "speed": random.uniform(0.3, 1.6),
            "size":  random.uniform(1.0, 2.8),
            "life":  random.uniform(0.3, 1.0),
            "drift": random.uniform(-0.02, 0.02),
        }

    # ── Animation loop ───────────────────────────────────────

    def _animate(self):
        if not self._running:
            return

        self.phase += 0.08
        self.rotation += 0.7

        # Smooth voice level
        self.voice_level += (self.target_voice_level - self.voice_level) * 0.18
        if self.target_voice_level > 0.01:
            self.target_voice_level *= 0.92
        else:
            self.target_voice_level = 0.0

        self.delete("all")
        pal = self.MODE_COLORS[self.mode]
        self.configure(bg=pal["bg"])

        self._draw_background_vignette(pal)
        self._draw_outer_grid(pal)
        self._draw_particles(pal)
        self._draw_rings(pal)
        self._draw_core(pal)
        self._draw_center_text(pal)

        self.after(16, self._animate)

    # ── Drawing layers ───────────────────────────────────────

    def _draw_background_vignette(self, pal):
        for i in range(6, 0, -1):
            r = self.base_radius * (2.8 + i * 0.22)
            color = pal["secondary"] if i % 2 == 0 else pal["primary"]
            width = max(1, int((i / 6.0) * 2))
            self.create_oval(
                self.cx - r, self.cy - r, self.cx + r, self.cy + r,
                outline=color, width=width, stipple="gray50",
            )

    def _draw_outer_grid(self, pal):
        """Tick marks around the outer edge + corner brackets."""
        r = self.base_radius * 2.5

        # Radial ticks
        for deg in range(0, 360, 15):
            angle = math.radians(deg + self.rotation * 0.15)
            x1 = self.cx + math.cos(angle) * (r - 8)
            y1 = self.cy + math.sin(angle) * (r - 8)
            x2 = self.cx + math.cos(angle) * r
            y2 = self.cy + math.sin(angle) * r
            self.create_line(x1, y1, x2, y2, fill=pal["secondary"], width=1)

        # Corner brackets — HUD framing
        c = 44
        m = 20
        w, h = self.w, self.h
        for sx, sy in [(m, m), (w - m, m), (m, h - m), (w - m, h - m)]:
            dx = 1 if sx < w / 2 else -1
            dy = 1 if sy < h / 2 else -1
            self.create_line(sx, sy, sx + c * dx, sy, fill=pal["secondary"], width=2)
            self.create_line(sx, sy, sx, sy + c * dy, fill=pal["secondary"], width=2)

    def _draw_particles(self, pal):
        for p in self.particles:
            p["angle"] += p["drift"]
            p["dist"] += p["speed"] * (0.6 + self.voice_level * 1.7)
            p["life"] -= 0.007 + self.voice_level * 0.01

            if p["life"] <= 0 or p["dist"] > self.base_radius * 3.4:
                p.update(self._make_particle())

            x = self.cx + math.cos(p["angle"]) * p["dist"]
            y = self.cy + math.sin(p["angle"]) * p["dist"]
            s = p["size"] * (0.8 + self.voice_level * 0.7)

            self.create_oval(x - s, y - s, x + s, y + s,
                             fill=pal["glow"], outline="")

    def _draw_rings(self, pal):
        pulse = 1.0 + math.sin(self.phase * 2.2) * 0.02
        voice_boost = self.voice_level * 16
        think_boost = 10 if self.mode == "thinking" else 0
        listen_boost = 8 if self.mode == "listening" else 0
        alert_boost = 12 if self.mode == "alert" else 0

        ring_radii = [
            self.base_radius + 20 + voice_boost * 0.5,
            self.base_radius + 42 + think_boost * 0.4,
            self.base_radius + 68 + listen_boost * 0.5,
            self.base_radius + 96 + alert_boost * 0.4,
        ]

        for idx, r in enumerate(ring_radii):
            speed = self.ring_speeds[idx]
            start = self.rotation * speed + self.ring_offsets[idx]
            extent = 110 + (self.voice_level * 30 if idx < 2 else 0)

            # Primary arc
            self.create_arc(
                self.cx - r, self.cy - r, self.cx + r, self.cy + r,
                start=start, extent=extent, style=tk.ARC,
                outline=pal["primary"], width=2 if idx < 2 else 1,
            )

            # Secondary arc (opposite side)
            self.create_arc(
                self.cx - r, self.cy - r, self.cx + r, self.cy + r,
                start=start + 180, extent=extent * 0.6, style=tk.ARC,
                outline=pal["secondary"], width=1,
            )

            # Tick clusters on ring
            for j in range(6):
                a = math.radians(start + j * 18)
                x1 = self.cx + math.cos(a) * (r - 4)
                y1 = self.cy + math.sin(a) * (r - 4)
                x2 = self.cx + math.cos(a) * (r + 6)
                y2 = self.cy + math.sin(a) * (r + 6)
                self.create_line(x1, y1, x2, y2, fill=pal["glow"], width=1)

        # Voice waveform ring (visible when speaking or voice_level > 0)
        if self.mode == "speaking" or self.voice_level > 0.03:
            points = []
            wave_r = self.base_radius + 12
            for deg in range(0, 360, 8):
                a = math.radians(deg)
                wobble = math.sin(a * 6 + self.phase * 5.5) * (3 + self.voice_level * 15)
                rr = wave_r + wobble
                points.extend([
                    self.cx + math.cos(a) * rr,
                    self.cy + math.sin(a) * rr,
                ])
            if len(points) >= 4:
                self.create_line(*points, fill=pal["glow"], width=2, smooth=True)

        # Breathing ring
        breathe_r = (self.base_radius + 5) * pulse + self.voice_level * 5
        self.create_oval(
            self.cx - breathe_r, self.cy - breathe_r,
            self.cx + breathe_r, self.cy + breathe_r,
            outline=pal["secondary"], width=1,
        )

    def _draw_core(self, pal):
        base = self.base_radius
        pulse = math.sin(self.phase * 3.0) * 4
        voice_p = self.voice_level * 18
        think_spin = self.rotation * (2.6 if self.mode == "thinking" else 0.7)

        outer = base + pulse + voice_p * 0.35
        inner = base * 0.58 + voice_p * 0.22
        nucleus = base * 0.28 + voice_p * 0.14

        # Outer glow shells
        for mult, w in [(1.35, 2), (1.18, 2), (1.03, 2)]:
            r = outer * mult
            self.create_oval(
                self.cx - r, self.cy - r, self.cx + r, self.cy + r,
                outline=pal["secondary"], width=w, stipple="gray50",
            )

        # Segmented rotating arcs
        for k in range(3):
            r = outer - k * 10
            self.create_arc(
                self.cx - r, self.cy - r, self.cx + r, self.cy + r,
                start=think_spin + k * 55, extent=85, style=tk.ARC,
                outline=pal["glow"], width=3 if k == 0 else 2,
            )

        # Inner filled glow
        self.create_oval(
            self.cx - inner, self.cy - inner,
            self.cx + inner, self.cy + inner,
            fill=pal["secondary"], outline="", stipple="gray50",
        )

        # Center nucleus
        self.create_oval(
            self.cx - nucleus, self.cy - nucleus,
            self.cx + nucleus, self.cy + nucleus,
            fill=pal["primary"], outline="",
        )

        # Spinning spokes
        for deg in range(0, 360, 60):
            a = math.radians(deg + think_spin * 1.7)
            x1 = self.cx + math.cos(a) * (nucleus * 0.4)
            y1 = self.cy + math.sin(a) * (nucleus * 0.4)
            x2 = self.cx + math.cos(a) * (inner * 0.82)
            y2 = self.cy + math.sin(a) * (inner * 0.82)
            self.create_line(x1, y1, x2, y2, fill=pal["glow"], width=1)

    def _draw_center_text(self, pal):
        self.create_text(
            self.cx, self.cy - 10,
            text="J.A.R.V.I.S",
            fill=pal["glow"],
            font=("Segoe UI Semibold", max(9, int(self.base_radius * 0.22))),
        )
        self.create_text(
            self.cx, self.cy + 14,
            text=self.mode.upper(),
            fill=pal["primary"],
            font=("Consolas", max(7, int(self.base_radius * 0.14))),
        )
