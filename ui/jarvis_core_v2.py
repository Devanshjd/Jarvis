"""
J.A.R.V.I.S -- Cinematic AI Core V2
Living particle-sphere with volumetric glow, energy network,
inner structure, turbulent motion, and escaped energy drift.

NOT a dashboard widget. NOT neon circles. NOT a HUD overlay.
This is a living artificial intelligence presence.

Visual layers (back to front):
    1. Volumetric glow bloom (soft radial light)
    2. Inner nucleus (bright dense core)
    3. Mid-shell structure (visible through outer surface)
    4. Energy network lines (front-facing mesh connections)
    5. Outer sphere surface (main particle shell)
    6. Drift particles (escaped energy beyond the boundary)

Motion system:
    - Multi-frequency turbulence (not simple rotation)
    - Sphere breathing (irregular, organic)
    - Voice-reactive surface displacement
    - Random energy surges
    - Mode-dependent behavior (spin speed, turbulence, pulse)
"""

import math
import random
import time
import tkinter as tk

# Hot-path references
_sin = math.sin
_cos = math.cos
_tau = math.tau
_sqrt = math.sqrt
_pi = math.pi
_abs = abs


class JarvisCoreV2(tk.Canvas):

    PALETTES = {
        "idle": {
            "bg":      "#020408",
            "glow1":   "#040c14",   # outer bloom
            "glow2":   "#061420",   # mid bloom
            "glow3":   "#0a2030",   # inner bloom
            "edge":    "#06222e",   # far particles
            "dim":     "#0c3a50",   # mid-far
            "mid":     "#1678a0",   # mid-near
            "bright":  "#30c8f0",   # near particles
            "core":    "#70e8ff",   # brightest / nucleus
            "line":    "#0e4e68",   # energy connections
            "line_b":  "#1890b8",   # bright connections
        },
        "listening": {
            "bg":      "#020804",
            "glow1":   "#041408",
            "glow2":   "#06200e",
            "glow3":   "#0a3018",
            "edge":    "#062e18",
            "dim":     "#0c5030",
            "mid":     "#16a068",
            "bright":  "#30f0a0",
            "core":    "#70ffc8",
            "line":    "#0e6840",
            "line_b":  "#18b878",
        },
        "thinking": {
            "bg":      "#040208",
            "glow1":   "#080414",
            "glow2":   "#0e0820",
            "glow3":   "#180e30",
            "edge":    "#1a1040",
            "dim":     "#2e1c60",
            "mid":     "#5838b0",
            "bright":  "#9068f0",
            "core":    "#c0a0ff",
            "line":    "#382080",
            "line_b":  "#6848c0",
        },
        "speaking": {
            "bg":      "#080402",
            "glow1":   "#140a04",
            "glow2":   "#201008",
            "glow3":   "#301a0e",
            "edge":    "#2e1a08",
            "dim":     "#503010",
            "mid":     "#a06818",
            "bright":  "#f0a030",
            "core":    "#ffd070",
            "line":    "#684810",
            "line_b":  "#b87820",
        },
        "alert": {
            "bg":      "#080202",
            "glow1":   "#140404",
            "glow2":   "#200808",
            "glow3":   "#301010",
            "edge":    "#2e0808",
            "dim":     "#501414",
            "mid":     "#a02828",
            "bright":  "#f04040",
            "core":    "#ff7070",
            "line":    "#681010",
            "line_b":  "#b82020",
        },
    }

    def __init__(self, parent, width=520, height=420):
        super().__init__(
            parent, width=width, height=height,
            bg=self.PALETTES["idle"]["bg"],
            highlightthickness=0, bd=0,
        )

        self.w = width
        self.h = height
        self.cx = width / 2
        self.cy = height / 2

        self.mode = "idle"
        self.phase = 0.0
        self._time_base = time.monotonic()

        self.voice_level = 0.0
        self.target_voice_level = 0.0

        # Sphere radii
        R = min(width, height) * 0.33
        self.sphere_r = R
        self.mid_r = R * 0.48
        self.nucleus_r = R * 0.18

        self._running = True
        self._frame_ms = 33  # ~30 fps

        # Particle layers
        self.outer = []       # main sphere surface
        self.mid_shell = []   # inner visible structure
        self.nucleus = []     # dense bright center
        self.drifters = []    # escaped energy particles

        # Connection index pairs (outer shell)
        self.connections = []

        self._build_all()
        self.after(self._frame_ms, self._tick)

    # ==================================================================
    # Public API (same interface as before — drop-in replacement)
    # ==================================================================

    def stop(self):
        self._running = False

    def set_mode(self, mode: str):
        if mode in self.PALETTES:
            self.mode = mode

    def set_voice_level(self, level: float):
        self.target_voice_level = max(0.0, min(1.0, float(level)))

    def set_idle(self):
        self.set_mode("idle")

    def set_listening(self, on=True):
        self.set_mode("listening" if on else "idle")

    def set_thinking(self, on=True):
        self.set_mode("thinking" if on else "idle")

    def set_speaking(self, on=True):
        if on:
            self.set_mode("speaking")
            self.target_voice_level = max(self.target_voice_level, 0.45)
        else:
            self.set_mode("idle")
            self.target_voice_level = 0.0

    def set_alert(self, on=True):
        self.set_mode("alert" if on else "idle")

    def pulse_once(self):
        self.target_voice_level = min(1.0, self.target_voice_level + 0.5)

    # ==================================================================
    # Particle construction
    # ==================================================================

    def _fib_sphere(self, n):
        """Fibonacci-spiral sphere distribution — even coverage, no pole clumping."""
        golden = _pi * (3.0 - _sqrt(5.0))
        pts = []
        for i in range(n):
            y = 1.0 - (i / max(n - 1, 1)) * 2.0
            r = _sqrt(max(0.0, 1.0 - y * y))
            a = golden * i

            nx = _cos(a) * r
            ny = y
            nz = _sin(a) * r

            # Organic jitter
            j = 0.035
            nx += random.uniform(-j, j)
            ny += random.uniform(-j, j)
            nz += random.uniform(-j, j)
            ln = _sqrt(nx*nx + ny*ny + nz*nz) or 1.0
            nx /= ln; ny /= ln; nz /= ln

            pts.append((nx, ny, nz))
        return pts

    def _build_all(self):
        # ── Outer sphere: 460 particles ──
        self.outer = []
        for nx, ny, nz in self._fib_sphere(460):
            self.outer.append({
                "nx": nx, "ny": ny, "nz": nz,
                "dv": random.uniform(0.92, 1.0),    # depth variance
                "sz": random.uniform(1.0, 2.1),      # base size
                "po": random.uniform(0, _tau),        # phase offset
                "ws": random.uniform(0.4, 1.3),       # wobble speed
                "wa": random.uniform(0.008, 0.022),    # wobble amplitude
                "tf": random.uniform(0.5, 2.0),       # turbulence frequency
            })

        # ── Mid shell: 70 particles (inner structure) ──
        self.mid_shell = []
        for nx, ny, nz in self._fib_sphere(70):
            self.mid_shell.append({
                "nx": nx, "ny": ny, "nz": nz,
                "dv": random.uniform(0.85, 1.0),
                "sz": random.uniform(1.4, 2.6),
                "po": random.uniform(0, _tau),
                "ws": random.uniform(0.2, 0.8),
                "wa": random.uniform(0.01, 0.03),
                "tf": random.uniform(0.3, 1.5),
            })

        # ── Nucleus: 25 dense bright particles ──
        self.nucleus = []
        for nx, ny, nz in self._fib_sphere(25):
            self.nucleus.append({
                "nx": nx, "ny": ny, "nz": nz,
                "dv": random.uniform(0.6, 1.0),
                "sz": random.uniform(2.0, 3.8),
                "po": random.uniform(0, _tau),
                "ws": random.uniform(0.15, 0.6),
                "wa": random.uniform(0.02, 0.05),
                "tf": random.uniform(0.2, 1.0),
            })

        # ── Drift particles: 35 escaped energy wisps ──
        self.drifters = []
        for _ in range(35):
            angle = random.uniform(0, _tau)
            elev = random.uniform(-0.6, 0.6)
            self.drifters.append({
                "angle": angle,
                "elev": elev,
                "dist": random.uniform(1.05, 1.45),  # beyond sphere surface
                "speed": random.uniform(-0.006, 0.006),
                "drift_y": random.uniform(-0.002, 0.002),
                "sz": random.uniform(0.8, 2.0),
                "po": random.uniform(0, _tau),
                "life": random.uniform(0.5, 1.0),
            })

        # ── Energy connections (outer shell neighbors) ──
        self._build_connections()

    def _build_connections(self):
        self.connections = []
        pts = self.outer
        n = len(pts)
        thresh_sq = 0.072  # ~0.268 distance on unit sphere

        for i in range(n):
            a = pts[i]
            for j in range(i + 1, min(i + 28, n)):
                b = pts[j]
                dx = a["nx"] - b["nx"]
                dy = a["ny"] - b["ny"]
                dz = a["nz"] - b["nz"]
                if dx*dx + dy*dy + dz*dz < thresh_sq:
                    self.connections.append((i, j))

        # Wrap-around
        for i in range(min(18, n)):
            a = pts[i]
            for j in range(max(0, n - 18), n):
                if i >= j:
                    continue
                b = pts[j]
                dx = a["nx"] - b["nx"]
                dy = a["ny"] - b["ny"]
                dz = a["nz"] - b["nz"]
                if dx*dx + dy*dy + dz*dz < thresh_sq:
                    self.connections.append((i, j))

    # ==================================================================
    # Transform: 3D → 2D with turbulence
    # ==================================================================

    def _transform(self, particles, radius):
        """
        Project particles with organic turbulence and voice reactivity.
        Returns indexed list: result[i] = (depth, sx, sy, size)
        """
        t = self.phase
        v = self.voice_level

        # Mode-dependent dynamics
        mode = self.mode
        spin = {"idle": 0.35, "listening": 0.50, "thinking": 0.90,
                "speaking": 0.55, "alert": 0.70}.get(mode, 0.35)
        turb_scale = {"idle": 1.0, "listening": 1.2, "thinking": 2.0,
                      "speaking": 1.5, "alert": 1.6}.get(mode, 1.0)

        # Rotation angles (not constant — has its own wobble for organic feel)
        rot_y = t * spin + _sin(t * 0.13) * 0.1
        rot_x = _sin(t * 0.09) * 0.12 + _cos(t * 0.17) * 0.06

        cry = _cos(rot_y); sry = _sin(rot_y)
        crx = _cos(rot_x); srx = _sin(rot_x)

        # Breathing — irregular, not a clean sine
        breath = (1.0
                  + _sin(t * 1.6) * 0.012
                  + _sin(t * 2.7) * 0.008
                  + _sin(t * 0.7) * 0.006)

        # Voice vibration
        vpulse = 1.0 + v * 0.14 * _sin(t * 9.0)
        scale = radius * breath * vpulse

        do_voice_wave = v > 0.03
        result = []

        for p in particles:
            # Turbulence: multi-frequency displacement
            po = p["po"]
            tf = p["tf"]
            turb_x = _sin(t * p["ws"] + po) * p["wa"] * turb_scale
            turb_y = _cos(t * tf * 0.8 + po * 1.3) * p["wa"] * turb_scale * 0.7
            turb_z = _sin(t * tf * 0.6 + po * 0.7) * p["wa"] * turb_scale * 0.5

            dv = p["dv"]
            px = (p["nx"] + turb_x) * dv
            py = (p["ny"] + turb_y) * dv
            pz = (p["nz"] + turb_z) * dv

            # Voice: surface wave displacement
            if do_voice_wave:
                wave = 1.0 + v * 0.10 * _sin(
                    p["nx"] * 4.0 + p["ny"] * 3.0 + t * 7.0 + po
                )
                px *= wave; py *= wave; pz *= wave

            # Rotate Y
            rx = px * cry + pz * sry
            rz = -px * sry + pz * cry
            # Rotate X
            ry = py * crx - rz * srx
            rz2 = py * srx + rz * crx

            depth = (rz2 + 1.0) * 0.5  # 0=far 1=near
            sx = self.cx + rx * scale
            sy = self.cy + ry * scale
            size = p["sz"] * (0.35 + depth * 0.85) + v * 0.25

            result.append((depth, sx, sy, size))

        return result

    # ==================================================================
    # Main animation tick
    # ==================================================================

    def _tick(self):
        if not self._running:
            return

        self.phase += 0.028

        # Smooth voice
        self.voice_level += (self.target_voice_level - self.voice_level) * 0.18
        self.target_voice_level *= 0.90
        if self.target_voice_level < 0.01:
            self.target_voice_level = 0.0

        pal = self.PALETTES[self.mode]
        self.configure(bg=pal["bg"])
        self.delete("all")

        # ── Layer 1: Volumetric glow bloom ──
        self._draw_glow(pal)

        # ── Project all shells ──
        nuc_proj = self._transform(self.nucleus, self.nucleus_r)
        mid_proj = self._transform(self.mid_shell, self.mid_r)
        out_proj = self._transform(self.outer, self.sphere_r)

        # ── Layer 2: Nucleus (always behind everything) ──
        self._draw_layer(sorted(nuc_proj, key=lambda t: t[0]),
                         pal["mid"], pal["bright"], pal["core"], pal["core"])

        # ── Layer 3: Mid-shell structure ──
        self._draw_layer(sorted(mid_proj, key=lambda t: t[0]),
                         pal["edge"], pal["dim"], pal["mid"], pal["bright"])

        # ── Layer 4: Energy connection lines ──
        self._draw_lines(out_proj, pal)

        # ── Layer 5: Outer sphere surface ──
        self._draw_layer(sorted(out_proj, key=lambda t: t[0]),
                         pal["edge"], pal["dim"], pal["mid"], pal["bright"])

        # ── Layer 6: Drift particles ──
        self._draw_drifters(pal)

        # ── Subtle state text ──
        self._draw_state(pal)

        self.after(self._frame_ms, self._tick)

    # ==================================================================
    # Drawing layers
    # ==================================================================

    def _draw_glow(self, pal):
        """
        Volumetric bloom — multiple soft concentric ovals
        that create the illusion of emitted light.
        """
        R = self.sphere_r
        v = self.voice_level

        # Glow pulses with breathing + voice
        pulse = _sin(self.phase * 1.6) * 4 + v * 18

        layers = [
            (R * 2.2 + pulse, pal["glow1"], "gray12"),
            (R * 1.8 + pulse, pal["glow1"], "gray12"),
            (R * 1.5 + pulse * 0.7, pal["glow2"], "gray25"),
            (R * 1.3 + pulse * 0.5, pal["glow2"], "gray25"),
            (R * 1.15 + pulse * 0.3, pal["glow3"], "gray50"),
            (R * 1.05, pal["glow3"], "gray50"),
        ]

        for r, color, stipple in layers:
            self.create_oval(
                self.cx - r, self.cy - r,
                self.cx + r, self.cy + r,
                fill=color, outline="", stipple=stipple,
            )

    def _draw_layer(self, sorted_pts, c_edge, c_dim, c_mid, c_bright):
        """Draw a depth-sorted particle layer with 4-tier coloring."""
        for depth, sx, sy, size in sorted_pts:
            if depth < 0.22:
                c = c_edge
            elif depth < 0.42:
                c = c_dim
            elif depth < 0.68:
                c = c_mid
            else:
                c = c_bright

            self.create_oval(
                sx - size, sy - size,
                sx + size, sy + size,
                fill=c, outline="",
            )

    def _draw_lines(self, indexed, pal):
        """
        Energy network connections between outer-shell particles.
        Only draw front-facing lines (both endpoints depth > 0.28).
        """
        line_dim = pal["line"]
        line_bright = pal["line_b"]
        n = len(indexed)

        for i, j in self.connections:
            if i >= n or j >= n:
                continue

            da, xa, ya, _ = indexed[i]
            db, xb, yb, _ = indexed[j]

            # Cull back-facing lines
            if da < 0.28 or db < 0.28:
                continue

            avg = (da + db) * 0.5
            c = line_bright if avg > 0.58 else line_dim

            self.create_line(xa, ya, xb, yb, fill=c, width=1)

    def _draw_drifters(self, pal):
        """
        Escaped energy wisps — particles that float just beyond
        the sphere boundary, giving it that energy-field feel.
        """
        R = self.sphere_r
        t = self.phase
        v = self.voice_level

        for p in self.drifters:
            p["angle"] += p["speed"] + v * 0.004
            p["elev"] += p["drift_y"]

            # Clamp elevation
            if _abs(p["elev"]) > 0.8:
                p["drift_y"] *= -1

            # Voice pushes drifters outward
            dist = p["dist"] + v * 0.15
            dist += _sin(t * 0.8 + p["po"]) * 0.03

            # Recycle if too far
            if dist > 1.6:
                p["dist"] = random.uniform(1.05, 1.15)
                p["angle"] = random.uniform(0, _tau)
                dist = p["dist"]

            # 2D position (simplified — no full 3D rotation for drifters)
            r = R * dist
            x = self.cx + _cos(p["angle"]) * r * _cos(p["elev"])
            y = self.cy + _sin(p["elev"]) * r * 0.6 + _sin(p["angle"]) * r * 0.4

            # Fade based on distance
            far = (dist - 1.0) / 0.6  # 0 at surface, 1 at max
            size = p["sz"] * (1.0 - far * 0.4) * (1.0 + v * 0.5)

            # Color: bright near surface, dim far away
            c = pal["mid"] if far < 0.4 else pal["dim"]

            self.create_oval(
                x - size, y - size,
                x + size, y + size,
                fill=c, outline="",
            )

    def _draw_state(self, pal):
        """Very subtle state indicator below the sphere."""
        y = self.cy + self.sphere_r + 22
        # Only show state text, nothing else
        state_text = {
            "idle": "",
            "listening": "Listening...",
            "thinking": "Thinking...",
            "speaking": "",
            "alert": "Alert",
        }.get(self.mode, "")

        if state_text:
            self.create_text(
                self.cx, y,
                text=state_text,
                fill=pal["dim"],
                font=("Segoe UI", 9),
            )
