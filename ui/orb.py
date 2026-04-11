"""
J.A.R.V.I.S — Energy Orb Visualizer
The iconic golden energy sphere from Iron Man.

Renders with numpy + PIL for realistic volumetric glow, hundreds
of particles, energy arcs, and surface sparks.  GPU-like speed
via vectorized numpy operations.
"""

import math
import random
import time
import tkinter as tk

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ── Pre-computed color arrays ────────────────────────────────
_GOLD   = np.array([255, 215, 0],   dtype=np.float32) if HAS_NUMPY else (255, 215, 0)
_ORANGE = np.array([255, 140, 0],   dtype=np.float32) if HAS_NUMPY else (255, 140, 0)
_AMBER  = np.array([255, 100, 0],   dtype=np.float32) if HAS_NUMPY else (255, 100, 0)
_WHITE  = np.array([255, 240, 220], dtype=np.float32) if HAS_NUMPY else (255, 240, 220)
_HOT    = np.array([255, 255, 240], dtype=np.float32) if HAS_NUMPY else (255, 255, 240)

_PARTICLE_COLORS = [_GOLD, _ORANGE, _WHITE] if HAS_NUMPY else []


# ═══════════════════════════════════════════════════════════════
#  Particle
# ═══════════════════════════════════════════════════════════════

class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life",
                 "size", "brightness", "color_idx")

    def __init__(self, cx, cy, speed_mult=1.0):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(0.3, 2.5) * speed_mult
        self.x = cx + random.gauss(0, 2)
        self.y = cy + random.gauss(0, 2)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = 0
        self.max_life = random.randint(15, 45)
        self.size = random.uniform(1.2, 3.5)
        self.brightness = random.uniform(0.5, 1.0)
        self.color_idx = random.randint(0, 2)

    def update(self) -> bool:
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.975
        self.vy *= 0.975
        self.life += 1
        return self.life < self.max_life

    @property
    def alpha(self) -> float:
        return max(0, (1.0 - self.life / self.max_life) * self.brightness)


# ═══════════════════════════════════════════════════════════════
#  Pre-computed distance field (the secret to speed)
# ═══════════════════════════════════════════════════════════════

def _build_distance_field(size: int):
    """
    Pre-compute a normalized distance field from center.
    dist[y, x] = distance from center / (size/2).
    This is computed ONCE and reused every frame.
    """
    half = size / 2.0
    y_coords = np.arange(size, dtype=np.float32) - half + 0.5
    x_coords = np.arange(size, dtype=np.float32) - half + 0.5
    yy, xx = np.meshgrid(y_coords, x_coords, indexing="ij")
    dist = np.sqrt(xx * xx + yy * yy)
    return dist, xx, yy


# ═══════════════════════════════════════════════════════════════
#  Energy Orb — numpy rendered
# ═══════════════════════════════════════════════════════════════

class EnergyOrb(tk.Canvas):
    """
    Realistic golden energy orb.
    Each frame is rendered as a numpy array with vectorized operations.
    """

    def __init__(self, parent, size=200, bg_color=None):
        self._size = size
        self._bg_hex = bg_color or "#0a0e17"
        self._bg_rgb = self._hex_to_rgb(self._bg_hex)

        super().__init__(
            parent, width=size, height=size,
            bg=self._bg_hex, highlightthickness=0, bd=0,
        )

        self.cx = size / 2.0
        self.cy = size / 2.0
        self.radius = size / 2.0 - 18

        # Pre-compute distance field (ONCE — this is the performance trick)
        if HAS_NUMPY:
            self._dist, self._xx, self._yy = _build_distance_field(size)

        # Animation state
        self._time = 0.0
        self._phase = 0.0
        self._angle = 0.0
        self._particles: list[Particle] = []
        self._intensity = 0.0
        self._target_intensity = 0.0
        self._vibrate = (0.0, 0.0)
        self._speaking = False
        self._thinking = False
        self._tk_img = None

        self._last_frame = time.time()

        if HAS_PIL and HAS_NUMPY:
            self._animate()
        else:
            self._draw_fallback()

    # ── Public API ───────────────────────────────────────────

    def set_speaking(self, speaking: bool):
        self._speaking = speaking
        self._target_intensity = 0.9 if speaking else 0.0

    def set_thinking(self, thinking: bool):
        self._thinking = thinking
        if thinking and not self._speaking:
            self._target_intensity = 0.4

    def pulse_once(self):
        self._intensity = min(1.0, self._intensity + 0.6)

    # ── Animation loop ───────────────────────────────────────

    def _animate(self):
        now = time.time()
        dt = min(now - self._last_frame, 0.1)
        self._last_frame = now
        self._time += dt
        self._phase += dt * 2.5

        # Smooth intensity
        diff = self._target_intensity - self._intensity
        self._intensity += diff * min(dt * 6, 0.5)
        if not self._speaking and not self._thinking:
            self._intensity = max(0, self._intensity - dt * 0.3)

        # Vibration
        if self._speaking:
            v = 1.5 + self._intensity * 3.5
            self._vibrate = (random.gauss(0, v), random.gauss(0, v))
        else:
            self._vibrate = (self._vibrate[0] * 0.8, self._vibrate[1] * 0.8)

        self._angle += (0.6 + self._intensity * 2.5) * dt * 60

        # Particles
        self._spawn_particles()
        self._particles = [p for p in self._particles if p.update()]

        # Render
        self._render_frame()
        self.after(40, self._animate)  # ~25 FPS

    def _spawn_particles(self):
        rate = 0.4 + self._intensity * 4.0
        while random.random() < rate and len(self._particles) < 150:
            rate -= 1.0
            angle = random.uniform(0, 2 * math.pi)
            spawn_r = self.radius * random.uniform(0.1, 0.85)
            px = self.cx + math.cos(angle) * spawn_r + self._vibrate[0]
            py = self.cy + math.sin(angle) * spawn_r + self._vibrate[1]
            self._particles.append(Particle(px, py, 0.6 + self._intensity * 1.8))

    # ── Numpy rendering ─────────────────────────────────────

    def _render_frame(self):
        s = self._size
        intensity = self._intensity
        pulse = (math.sin(self._phase) + 1) / 2
        vx, vy = self._vibrate

        # Start with background
        frame = np.full((s, s, 3), self._bg_rgb, dtype=np.float32)

        # Shifted distance field for vibration
        if abs(vx) > 0.5 or abs(vy) > 0.5:
            half = s / 2.0
            shifted_dist = np.sqrt(
                (self._xx - vx) ** 2 + (self._yy - vy) ** 2
            )
        else:
            shifted_dist = self._dist

        # ── Layer 1: Deep outer glow ─────────────────────────
        self._add_glow(frame, shifted_dist,
                       radius=self.radius * 2.0 + pulse * 6,
                       color=_AMBER,
                       max_alpha=0.05 + intensity * 0.07 + pulse * 0.02)

        # ── Layer 2: Mid glow ────────────────────────────────
        self._add_glow(frame, shifted_dist,
                       radius=self.radius * 1.5 + pulse * 4,
                       color=_ORANGE,
                       max_alpha=0.08 + intensity * 0.12 + pulse * 0.04)

        # ── Layer 3: Main orb body ───────────────────────────
        self._add_glow(frame, shifted_dist,
                       radius=self.radius * 1.1 + pulse * 3,
                       color=_GOLD,
                       max_alpha=0.18 + intensity * 0.18 + pulse * 0.07)

        # ── Layer 4: Inner energy ────────────────────────────
        self._add_glow(frame, shifted_dist,
                       radius=self.radius * 0.6 + pulse * 2,
                       color=_GOLD,
                       max_alpha=0.28 + intensity * 0.22 + pulse * 0.08)

        # ── Layer 5: Hot core ────────────────────────────────
        core_color = _HOT if self._speaking else _WHITE
        core_r = self.radius * 0.25 + intensity * 10 + pulse * 5
        self._add_glow(frame, shifted_dist,
                       radius=core_r,
                       color=core_color,
                       max_alpha=0.45 + intensity * 0.35 + pulse * 0.15)

        # ── Layer 6: Particles ───────────────────────────────
        self._render_particles(frame)

        # ── Layer 7: Surface sparks ──────────────────────────
        self._render_sparks(frame, shifted_dist, intensity, pulse)

        # Clamp to 0–255 and convert
        np.clip(frame, 0, 255, out=frame)
        img = Image.fromarray(frame.astype(np.uint8), "RGB")

        # Draw ring arcs and wisps with PIL (vector graphics)
        self._draw_vector_layers(img, intensity, pulse, vx, vy)

        # Slight blur for volumetric feel
        if intensity > 0.15:
            try:
                img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
            except Exception:
                pass

        self._tk_img = ImageTk.PhotoImage(img)
        self.delete("all")
        self.create_image(s // 2, s // 2, image=self._tk_img)

    def _add_glow(self, frame, dist_field, radius, color, max_alpha):
        """Vectorized radial glow — runs in ~1ms instead of ~20ms."""
        if radius < 1:
            return
        # Normalized distance: 0 at center, 1 at edge of radius
        t = np.clip(1.0 - dist_field / radius, 0, 1)
        # Smooth hermite interpolation (cubic)
        t = t * t * (3 - 2 * t)
        # Alpha mask
        alpha = (t * max_alpha)[:, :, np.newaxis]
        # Additive blending
        frame += color[np.newaxis, np.newaxis, :] * alpha

    def _render_particles(self, frame):
        """Render particles into the numpy frame."""
        s = self._size
        for p in self._particles:
            a = p.alpha
            if a < 0.03:
                continue

            color = _PARTICLE_COLORS[p.color_idx]
            sz = p.size * (0.5 + a * 0.5)

            # Bounding box
            x0 = max(0, int(p.x - sz - 1))
            x1 = min(s - 1, int(p.x + sz + 1))
            y0 = max(0, int(p.y - sz - 1))
            y1 = min(s - 1, int(p.y + sz + 1))

            if x0 >= x1 or y0 >= y1:
                continue

            # Small region — compute distances
            yy = np.arange(y0, y1 + 1, dtype=np.float32) - p.y
            xx = np.arange(x0, x1 + 1, dtype=np.float32) - p.x
            dy, dx = np.meshgrid(yy, xx, indexing="ij")
            dist = np.sqrt(dx * dx + dy * dy)

            # Soft falloff
            t = np.clip(1.0 - dist / (sz + 0.5), 0, 1)
            particle_alpha = (t * a * 0.9)[:, :, np.newaxis]

            frame[y0:y1+1, x0:x1+1] += color[np.newaxis, np.newaxis, :] * particle_alpha

    def _render_sparks(self, frame, dist_field, intensity, pulse):
        """Scatter bright pixels on orb surface."""
        s = self._size
        num = 10 + int(intensity * 20)
        cx, cy = self.cx + self._vibrate[0], self.cy + self._vibrate[1]

        for _ in range(num):
            angle = random.uniform(0, 2 * math.pi)
            d = self.radius * random.uniform(0.15, 0.95)
            sx = int(cx + math.cos(angle) * d)
            sy = int(cy + math.sin(angle) * d)

            if 0 <= sx < s and 0 <= sy < s:
                brightness = random.uniform(0.2, 0.7) + intensity * 0.3
                brightness *= (0.7 + pulse * 0.3)
                add = 160 * brightness
                frame[sy, sx, 0] = min(255, frame[sy, sx, 0] + add)
                frame[sy, sx, 1] = min(255, frame[sy, sx, 1] + add * 0.82)
                frame[sy, sx, 2] = min(255, frame[sy, sx, 2] + add * 0.25)

    def _draw_vector_layers(self, img, intensity, pulse, vx, vy):
        """Draw ring arcs and energy wisps with PIL (vector drawing)."""
        draw = ImageDraw.Draw(img)
        cx = self.cx + vx
        cy = self.cy + vy
        r = self.radius

        # Energy wisps
        num_wisps = 5 + int(intensity * 6)
        for i in range(num_wisps):
            angle_deg = (self._time * (22 + i * 11) + i * 137.508) % 360
            angle = math.radians(angle_deg)

            start_r = r * 0.06
            end_r = r * (0.45 + pulse * 0.18 + intensity * 0.22)

            x1 = cx + math.cos(angle) * start_r
            y1 = cy + math.sin(angle) * start_r
            x2 = cx + math.cos(angle) * end_r
            y2 = cy + math.sin(angle) * end_r

            wisp_a = 0.07 + intensity * 0.12 + pulse * 0.04
            color = self._alpha_color((255, 215, 0), wisp_a)
            draw.line([(x1, y1), (x2, y2)], fill=color, width=1)

        # Ring arcs
        for ring_idx in range(3):
            ring_r = r * (0.7 + ring_idx * 0.25) + pulse * 2
            base_angle = self._angle * (0.6 + ring_idx * 0.35) + ring_idx * 25
            arc_span = 20 + intensity * 25

            segments = 2 + int(intensity * 2)
            for j in range(segments):
                seg_angle = base_angle + j * (360 / max(segments, 1))
                seg_a = 0.08 + intensity * 0.22 + pulse * 0.05
                color = self._alpha_color((255, 140, 0), seg_a)

                bbox = [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r]
                try:
                    draw.arc(bbox, seg_angle, seg_angle + arc_span,
                             fill=color, width=max(1, int(1 + intensity)))
                except Exception:
                    pass

    # ── Fallback ─────────────────────────────────────────────

    def _draw_fallback(self):
        r = self.radius
        cx, cy = self.cx, self.cy
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill="#3a2500", outline="#FFB800", width=2)
        self.create_text(cx, cy, text="J.A.R.V.I.S",
                         fill="#FFD700", font=("Consolas", 9))

    # ── Utilities ────────────────────────────────────────────

    @staticmethod
    def _hex_to_rgb(h: str) -> tuple:
        h = h.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    @staticmethod
    def _alpha_color(color: tuple, alpha: float) -> tuple:
        bg = (10, 14, 23)
        a = max(0, min(1, alpha))
        return (int(color[0] * a + bg[0] * (1 - a)),
                int(color[1] * a + bg[1] * (1 - a)),
                int(color[2] * a + bg[2] * (1 - a)))


# ═══════════════════════════════════════════════════════════════
#  OrbWithLabel
# ═══════════════════════════════════════════════════════════════

class OrbWithLabel(tk.Frame):
    def __init__(self, parent, size=200, show_label=True, bg_color=None):
        bg = bg_color or "#0a0e17"
        super().__init__(parent, bg=bg)

        self.orb = EnergyOrb(self, size=size, bg_color=bg)
        self.orb.pack()

        if show_label:
            self.label = tk.Label(
                self, text="J.A.R.V.I.S",
                font=("Segoe UI Semibold", 11),
                fg="#FFD700", bg=bg,
            )
            self.label.pack(pady=(2, 0))

    def set_speaking(self, speaking: bool):
        self.orb.set_speaking(speaking)

    def set_thinking(self, thinking: bool):
        self.orb.set_thinking(thinking)

    def pulse_once(self):
        self.orb.pulse_once()


# ═══════════════════════════════════════════════════════════════
#  MiniOrb — compact top bar version
# ═══════════════════════════════════════════════════════════════

class MiniOrb(tk.Canvas):
    def __init__(self, parent, size=40, bg_color=None):
        self._bg_hex = bg_color or "#0a0e17"
        self._bg_rgb = EnergyOrb._hex_to_rgb(self._bg_hex)
        self._size = size

        super().__init__(parent, width=size, height=size,
                         bg=self._bg_hex, highlightthickness=0)

        self.cx = size / 2.0
        self.cy = size / 2.0
        self.radius = size / 2.0 - 4
        self._phase = 0.0
        self._intensity = 0.0
        self._target_intensity = 0.0
        self._speaking = False
        self._tk_img = None

        if HAS_PIL and HAS_NUMPY:
            self._dist, self._xx, self._yy = _build_distance_field(size)
            self._animate()
        else:
            self._draw_fallback()

    def set_speaking(self, speaking: bool):
        self._speaking = speaking
        self._target_intensity = 0.8 if speaking else 0.0

    def _animate(self):
        self._phase += 0.1
        diff = self._target_intensity - self._intensity
        self._intensity += diff * 0.12

        s = self._size
        pulse = (math.sin(self._phase) + 1) / 2
        intensity = self._intensity

        vx = random.gauss(0, 1.0) if self._speaking else 0
        vy = random.gauss(0, 1.0) if self._speaking else 0

        frame = np.full((s, s, 3), self._bg_rgb, dtype=np.float32)

        if abs(vx) > 0.3 or abs(vy) > 0.3:
            dist = np.sqrt((self._xx - vx)**2 + (self._yy - vy)**2)
        else:
            dist = self._dist

        r = self.radius

        # Outer glow
        t = np.clip(1.0 - dist / (r * 1.5), 0, 1)
        t = t * t * (3 - 2 * t)
        a = 0.06 + intensity * 0.1 + pulse * 0.03
        frame += _AMBER * (t * a)[:, :, np.newaxis]

        # Body
        t = np.clip(1.0 - dist / (r * 1.0), 0, 1)
        t = t * t * (3 - 2 * t)
        a = 0.18 + intensity * 0.18 + pulse * 0.06
        frame += _GOLD * (t * a)[:, :, np.newaxis]

        # Core
        core_r = r * 0.4 + intensity * 3
        t = np.clip(1.0 - dist / core_r, 0, 1)
        t = t * t * (3 - 2 * t)
        a = 0.4 + intensity * 0.3 + pulse * 0.12
        c = _WHITE if self._speaking else _GOLD
        frame += c * (t * a)[:, :, np.newaxis]

        np.clip(frame, 0, 255, out=frame)
        img = Image.fromarray(frame.astype(np.uint8), "RGB")

        # Ring arc
        draw = ImageDraw.Draw(img)
        ring_r = r * 0.85
        ang = (self._phase * 35) % 360
        ring_a = 0.12 + intensity * 0.2
        color = EnergyOrb._alpha_color((255, 140, 0), ring_a)
        cx, cy = self.cx + vx, self.cy + vy
        try:
            bbox = [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r]
            draw.arc(bbox, ang, ang + 50, fill=color, width=1)
            draw.arc(bbox, ang + 180, ang + 230, fill=color, width=1)
        except Exception:
            pass

        self._tk_img = ImageTk.PhotoImage(img)
        self.delete("all")
        self.create_image(s // 2, s // 2, image=self._tk_img)
        self.after(50, self._animate)

    def _draw_fallback(self):
        r = self.radius
        self.create_oval(self.cx - r, self.cy - r, self.cx + r, self.cy + r,
                         fill="#3a2500", outline="#FFB800", width=1)
