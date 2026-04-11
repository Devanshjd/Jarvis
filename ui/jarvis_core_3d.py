"""
J.A.R.V.I.S -- GPU-Accelerated 3D Core
Real volumetric energy sphere rendered with GLSL shaders on the GPU.
Includes HUD overlay with mic button, status text, and chat input.

Architecture:
    - Pygame creates the OpenGL window
    - ModernGL renders the 3D sphere via fragment shader
    - A 2D HUD overlay is rendered on top as a texture
    - Python sends uniform values (mode, time, voice level)
    - Chat messages and mic state shown in the HUD
"""

import math
import time
import threading
import struct
import collections

try:
    import pygame
    from pygame.locals import (
        DOUBLEBUF, OPENGL, QUIT, KEYDOWN, KEYUP,
        K_ESCAPE, K_RETURN, K_BACKSPACE,
        MOUSEBUTTONDOWN, VIDEORESIZE, RESIZABLE,
    )
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

try:
    import moderngl
    HAS_MODERNGL = True
except ImportError:
    HAS_MODERNGL = False


# ═══════════════════════════════════════════════════════════
# GLSL Shaders
# ═══════════════════════════════════════════════════════════

VERTEX_SHADER = """
#version 330 core
in vec2 in_pos;
out vec2 uv;
void main() {
    gl_Position = vec4(in_pos, 0.0, 1.0);
    uv = in_pos;
}
"""

FRAGMENT_SHADER = """
#version 330 core

in vec2 uv;
out vec4 fragColor;

uniform float u_time;
uniform float u_voice;
uniform float u_mode;
uniform float u_aspect;

// ── Noise ──

float hash(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise3d(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x),
            mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
        mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
            mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y),
        f.z);
}

float fbm(vec3 p) {
    float v = 0.0, a = 0.5;
    vec3 shift = vec3(100.0);
    for (int i = 0; i < 4; i++) {
        v += a * noise3d(p);
        p = p * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}

mat3 rotateY(float a) { float c=cos(a),s=sin(a); return mat3(c,0,s, 0,1,0, -s,0,c); }
mat3 rotateX(float a) { float c=cos(a),s=sin(a); return mat3(1,0,0, 0,c,-s, 0,s,c); }

vec3 getBaseColor() {
    if      (u_mode < 0.5) return vec3(0.15, 0.75, 0.95);
    else if (u_mode < 1.5) return vec3(0.15, 0.95, 0.60);
    else if (u_mode < 2.5) return vec3(0.55, 0.35, 0.95);
    else if (u_mode < 3.5) return vec3(0.95, 0.65, 0.20);
    else                   return vec3(0.95, 0.20, 0.20);
}

vec3 getCoreColor() {
    if      (u_mode < 0.5) return vec3(0.40, 0.92, 1.00);
    else if (u_mode < 1.5) return vec3(0.40, 1.00, 0.75);
    else if (u_mode < 2.5) return vec3(0.72, 0.55, 1.00);
    else if (u_mode < 3.5) return vec3(1.00, 0.82, 0.40);
    else                   return vec3(1.00, 0.40, 0.40);
}

float noisySphere(vec3 p, float radius, float t) {
    float spinSpeed = 0.3;
    if (u_mode > 1.5 && u_mode < 2.5) spinSpeed = 0.8;
    else if (u_mode > 3.5) spinSpeed = 0.6;

    mat3 rot = rotateY(t * spinSpeed) * rotateX(sin(t * 0.13) * 0.15);
    vec3 rp = rot * p;
    float disp = fbm(rp * 2.5 + t * 0.3) * 0.15;
    float voiceDisp = u_voice * 0.12 * sin(rp.x * 4.0 + rp.y * 3.0 + t * 7.0);
    float breath = sin(t * 1.6) * 0.01 + sin(t * 2.7) * 0.007;
    return length(p) - (radius + disp + voiceDisp + breath);
}

void main() {
    vec2 p = uv;
    p.x *= u_aspect;
    float t = u_time;

    vec3 baseCol = getBaseColor();
    vec3 coreCol = getCoreColor();

    float outerR = 0.75 + u_voice * 0.08;
    float innerR = 0.32;
    float nucleusR = 0.12;

    // Volumetric glow
    float distToCenter = length(p);
    float outerGlow = exp(-distToCenter * 1.8) * 0.25;
    float midGlow = exp(-distToCenter * 3.5) * 0.15;
    outerGlow *= (1.0 + u_voice * 0.8 + sin(t * 1.6) * 0.1);
    vec3 col = baseCol * outerGlow + coreCol * midGlow;

    // Raymarching
    vec3 ro = vec3(p * 1.8, -2.5);
    vec3 rd = vec3(0.0, 0.0, 1.0);
    float totalDensity = 0.0;
    vec3 totalColor = vec3(0.0);

    for (int i = 0; i < 80; i++) {
        float depth = float(i) * 0.025;
        vec3 pos = ro + rd * depth;
        float dOuter = noisySphere(pos, outerR, t);

        if (dOuter < 0.0) {
            float insideDepth = -dOuter / outerR;
            float density = smoothstep(0.0, 0.3, insideDepth) * 0.08;

            mat3 rot = rotateY(t * 0.3) * rotateX(sin(t * 0.13) * 0.15);
            vec3 rp = rot * pos;
            float turbulence = fbm(rp * 4.0 + t * 0.5);

            float dInner = abs(length(pos) - innerR) - 0.02;
            float innerShell = exp(-dInner * 40.0) * 0.4;

            float dNucleus = length(pos) - nucleusR;
            float nucleusGlow = exp(-max(dNucleus, 0.0) * 15.0) * 0.6;

            vec3 sampleColor = baseCol * (turbulence * 0.6 + 0.4);
            sampleColor += coreCol * innerShell;
            sampleColor += coreCol * nucleusGlow * 1.5;

            float edgeGlow = exp(-insideDepth * 8.0) * 0.3;
            sampleColor += baseCol * edgeGlow;

            totalDensity += density;
            totalColor += sampleColor * density;
            if (totalDensity > 0.95) break;
        }
    }

    col += totalColor;

    // Energy wisps
    float wispAngle = atan(p.y, p.x);
    if (distToCenter > outerR * 0.9 && distToCenter < outerR * 1.6) {
        float wisp = sin(wispAngle * 5.0 + t * 2.0) * 0.5 + 0.5;
        wisp *= sin(wispAngle * 13.0 - t * 3.0) * 0.5 + 0.5;
        wisp *= exp(-(distToCenter - outerR) * 5.0) * 0.12 * (1.0 + u_voice * 2.0);
        col += baseCol * wisp;
    }

    // Surface network lines
    float surfaceDist = abs(distToCenter - outerR);
    if (surfaceDist < 0.08) {
        mat3 rot = rotateY(t * 0.3);
        vec3 surfPos = rot * vec3(p, sqrt(max(0.0, outerR*outerR - dot(p,p))));
        float grid = fbm(surfPos * 8.0);
        float lines = smoothstep(0.45, 0.5, grid) * 0.3 * exp(-surfaceDist * 30.0);
        col += coreCol * lines;
    }

    col = col / (col + 0.8);
    float vig = 1.0 - dot(uv * 0.5, uv * 0.5) * 0.3;
    col *= vig;

    fragColor = vec4(col, 1.0);
}
"""

# HUD overlay shader — renders a 2D texture on top of the 3D scene
HUD_VERTEX = """
#version 330 core
in vec2 in_pos;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    gl_Position = vec4(in_pos, 0.0, 1.0);
    v_uv = in_uv;
}
"""

HUD_FRAGMENT = """
#version 330 core
in vec2 v_uv;
out vec4 fragColor;
uniform sampler2D u_hud_tex;
void main() {
    fragColor = texture(u_hud_tex, v_uv);
}
"""


# ═══════════════════════════════════════════════════════════
# JarvisCore3D
# ═══════════════════════════════════════════════════════════

class JarvisCore3D:
    """
    GPU-rendered JARVIS core with integrated HUD overlay.
    Mic button, status text, and chat display built in.
    """

    MODE_MAP = {
        "idle": 0.0,
        "listening": 1.0,
        "thinking": 2.0,
        "speaking": 3.0,
        "alert": 4.0,
    }

    def __init__(self, width=900, height=700, title="J.A.R.V.I.S"):
        self.width = width
        self.height = height
        self.title = title

        self.mode = "idle"
        self.voice_level = 0.0
        self.target_voice_level = 0.0

        self._running = False
        self._thread = None
        self._jarvis = None  # reference to JarvisApp (set by app.py)

        # Chat state
        self.chat_lines = collections.deque(maxlen=8)
        self.input_text = ""
        self.input_active = False
        self.mic_on = False
        self.status_text = ""

        # GL objects
        self._ctx = None
        self._prog = None
        self._vao = None
        self._hud_prog = None
        self._hud_vao = None
        self._hud_tex = None

    # ── Public API ──

    def set_mode(self, mode: str):
        if mode in self.MODE_MAP:
            self.mode = mode
            if mode == "listening":
                self.status_text = "Listening..."
            elif mode == "thinking":
                self.status_text = "Thinking..."
            elif mode == "speaking":
                self.status_text = ""
            elif mode == "alert":
                self.status_text = "Alert"
            else:
                self.status_text = ""

    def set_voice_level(self, level: float):
        self.target_voice_level = max(0.0, min(1.0, float(level)))

    def set_idle(self):           self.set_mode("idle")
    def set_listening(self, on=True): self.set_mode("listening" if on else "idle")
    def set_thinking(self, on=True):  self.set_mode("thinking" if on else "idle")

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

    def stop(self):
        self._running = False

    def add_chat(self, role: str, text: str):
        """Add a chat message to the HUD overlay."""
        # Truncate long messages
        display = text[:90] + "..." if len(text) > 90 else text
        self.chat_lines.append((role, display))

    # ── Threaded start ──

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self.run, daemon=True, name="jarvis-3d")
        self._thread.start()

    # ── Main render loop ──

    def run(self):
        if not HAS_PYGAME or not HAS_MODERNGL:
            print("[JARVIS 3D] pip install pygame moderngl")
            return

        pygame.init()
        pygame.display.set_caption(self.title)
        screen = pygame.display.set_mode(
            (self.width, self.height), DOUBLEBUF | OPENGL,
        )

        self._ctx = moderngl.create_context()
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = (
            moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA,
        )

        # ── Sphere shader ──
        try:
            self._prog = self._ctx.program(
                vertex_shader=VERTEX_SHADER,
                fragment_shader=FRAGMENT_SHADER,
            )
        except Exception as e:
            print(f"[JARVIS 3D] Shader error:\n{e}")
            pygame.quit()
            return

        verts = struct.pack("8f", -1,-1, 1,-1, -1,1, 1,1)
        vbo = self._ctx.buffer(verts)
        self._vao = self._ctx.simple_vertex_array(self._prog, vbo, "in_pos")

        aspect = self.width / self.height
        if "u_aspect" in self._prog:
            self._prog["u_aspect"].value = aspect

        # ── HUD overlay shader ──
        try:
            self._hud_prog = self._ctx.program(
                vertex_shader=HUD_VERTEX,
                fragment_shader=HUD_FRAGMENT,
            )
        except Exception as e:
            print(f"[JARVIS 3D] HUD shader error: {e}")
            self._hud_prog = None

        if self._hud_prog:
            # Quad with UVs
            hud_data = struct.pack("16f",
                -1,-1, 0,0,  1,-1, 1,0,  -1,1, 0,1,  1,1, 1,1,
            )
            hud_vbo = self._ctx.buffer(hud_data)
            self._hud_vao = self._ctx.simple_vertex_array(
                self._hud_prog, hud_vbo, "in_pos", "in_uv",
            )

        # HUD surface (pygame 2D) + texture
        self._hud_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._hud_tex = self._ctx.texture(
            (self.width, self.height), 4,
        )
        self._hud_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

        # Fonts
        self._font_small = pygame.font.SysFont("Segoe UI", 14)
        self._font_med = pygame.font.SysFont("Segoe UI", 18)
        self._font_large = pygame.font.SysFont("Segoe UI Semibold", 22)
        self._font_input = pygame.font.SysFont("Consolas", 16)
        self._font_status = pygame.font.SysFont("Segoe UI", 13)

        clock = pygame.time.Clock()
        start_time = time.monotonic()
        self._running = True

        # Mic button geometry
        mic_cx = self.width // 2
        mic_cy = self.height - 55
        mic_r = 22

        print(f"[JARVIS 3D] GPU core online — {self._ctx.info['GL_RENDERER']}")

        while self._running:
            # ── Events ──
            for event in pygame.event.get():
                if event.type == QUIT:
                    self._running = False
                    break

                if event.type == MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    # Check mic button click
                    dx = mx - mic_cx
                    dy = my - mic_cy
                    if dx*dx + dy*dy <= (mic_r + 5) ** 2:
                        self._toggle_mic()
                    # Check input area click
                    elif my >= self.height - 95 and my <= self.height - 70:
                        self.input_active = True
                    else:
                        self.input_active = False

                if event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        if self.input_active:
                            self.input_active = False
                            self.input_text = ""
                        else:
                            # Don't close — just ignore ESC
                            pass
                    elif self.input_active:
                        if event.key == K_RETURN:
                            self._send_input()
                        elif event.key == K_BACKSPACE:
                            self.input_text = self.input_text[:-1]
                        else:
                            ch = event.unicode
                            if ch and ch.isprintable():
                                self.input_text += ch

            # ── Voice smoothing ──
            self.voice_level += (self.target_voice_level - self.voice_level) * 0.15
            self.target_voice_level *= 0.92
            if self.target_voice_level < 0.01:
                self.target_voice_level = 0.0

            # ── Render 3D sphere ──
            t = time.monotonic() - start_time
            if "u_time" in self._prog:
                self._prog["u_time"].value = t
            if "u_voice" in self._prog:
                self._prog["u_voice"].value = self.voice_level
            if "u_mode" in self._prog:
                self._prog["u_mode"].value = self.MODE_MAP.get(self.mode, 0.0)

            self._ctx.clear(0.008, 0.015, 0.03)
            self._vao.render(moderngl.TRIANGLE_STRIP)

            # ── Render HUD overlay ──
            if self._hud_prog and self._hud_vao:
                self._draw_hud(t)
                # Upload HUD surface to GPU texture
                raw = pygame.image.tostring(self._hud_surface, "RGBA", True)
                self._hud_tex.write(raw)
                self._hud_tex.use(0)
                self._hud_vao.render(moderngl.TRIANGLE_STRIP)

            pygame.display.flip()
            clock.tick(60)

        # Cleanup
        if self._hud_tex: self._hud_tex.release()
        if self._hud_vao: self._hud_vao.release()
        if self._vao: self._vao.release()
        if self._ctx: self._ctx.release()
        pygame.quit()
        print("[JARVIS 3D] GPU core shutdown")

    # ═══════════════════════════════════════════════════════
    # HUD Drawing (2D overlay)
    # ═══════════════════════════════════════════════════════

    def _draw_hud(self, t):
        """Draw the 2D HUD overlay on the pygame surface."""
        s = self._hud_surface
        s.fill((0, 0, 0, 0))  # transparent

        W, H = self.width, self.height
        mode_colors = {
            "idle":      (60, 210, 240),
            "listening": (60, 255, 170),
            "thinking":  (160, 120, 255),
            "speaking":  (255, 180, 70),
            "alert":     (255, 80, 80),
        }
        accent = mode_colors.get(self.mode, (60, 210, 240))
        dim = tuple(c // 3 for c in accent)

        # ── Status text (below sphere) ──
        if self.status_text:
            txt = self._font_status.render(self.status_text, True, (*accent, 180))
            s.blit(txt, (W//2 - txt.get_width()//2, H//2 + 135))

        # ── Chat messages (bottom-left area) ──
        chat_y = H - 130
        for role, text in reversed(list(self.chat_lines)):
            if chat_y < H // 2 + 160:
                break

            if role == "user":
                color = (180, 180, 180, 200)
                prefix = "You: "
            elif role == "assistant":
                color = (*accent, 220)
                prefix = ""
            elif role == "voice":
                color = (120, 255, 180, 180)
                prefix = ""
            else:
                color = (*dim, 160)
                prefix = ""

            line = prefix + text
            txt = self._font_small.render(line, True, color[:3])
            txt.set_alpha(color[3] if len(color) > 3 else 200)
            s.blit(txt, (20, chat_y))
            chat_y -= 20

        # ── Input box (bottom) ──
        input_y = H - 95
        input_h = 28
        input_w = W - 120

        # Background
        input_bg = pygame.Surface((input_w, input_h), pygame.SRCALPHA)
        input_bg.fill((10, 15, 25, 160))
        s.blit(input_bg, (15, input_y))

        # Border
        border_color = accent if self.input_active else dim
        pygame.draw.rect(s, (*border_color, 120), (15, input_y, input_w, input_h), 1)

        # Text
        if self.input_text:
            txt = self._font_input.render(self.input_text, True, (220, 220, 220))
            s.blit(txt, (22, input_y + 5))
        elif not self.input_active:
            txt = self._font_input.render("Type a message...", True, (*dim, 100))
            s.blit(txt, (22, input_y + 5))

        # Cursor blink
        if self.input_active and int(t * 2) % 2 == 0:
            cursor_x = 22 + self._font_input.size(self.input_text)[0]
            pygame.draw.line(s, (*accent, 200), (cursor_x, input_y + 4), (cursor_x, input_y + input_h - 4), 1)

        # ── Mic button (bottom center) ──
        mic_cx = W // 2
        mic_cy = H - 55
        mic_r = 22

        # Outer ring
        ring_color = (60, 255, 170) if self.mic_on else dim
        pygame.draw.circle(s, (*ring_color, 180), (mic_cx, mic_cy), mic_r + 3, 2)

        # Inner fill
        if self.mic_on:
            # Pulsing green when active
            pulse = int(abs(math.sin(t * 3)) * 40) + 30
            pygame.draw.circle(s, (20, pulse + 60, 40, 160), (mic_cx, mic_cy), mic_r)
        else:
            pygame.draw.circle(s, (15, 20, 30, 140), (mic_cx, mic_cy), mic_r)

        # Mic icon (simple shape)
        mic_color = (220, 255, 220) if self.mic_on else (100, 100, 120)
        # Mic body
        pygame.draw.rect(s, (*mic_color, 220),
                        (mic_cx - 4, mic_cy - 10, 8, 14), border_radius=4)
        # Mic base arc
        pygame.draw.arc(s, (*mic_color, 220),
                       (mic_cx - 8, mic_cy - 6, 16, 18), 3.14, 6.28, 2)
        # Mic stand
        pygame.draw.line(s, (*mic_color, 220),
                        (mic_cx, mic_cy + 10), (mic_cx, mic_cy + 14), 2)
        pygame.draw.line(s, (*mic_color, 220),
                        (mic_cx - 5, mic_cy + 14), (mic_cx + 5, mic_cy + 14), 2)

        # ── Top-left: JARVIS label ──
        title = self._font_large.render("J.A.R.V.I.S", True, (*accent, 160))
        s.blit(title, (18, 14))

        # ── Top-right: mode indicator ──
        mode_txt = self._font_status.render(self.mode.upper(), True, (*dim, 140))
        s.blit(mode_txt, (W - mode_txt.get_width() - 18, 18))

    # ═══════════════════════════════════════════════════════
    # Interaction handlers
    # ═══════════════════════════════════════════════════════

    def _toggle_mic(self):
        """Toggle microphone listening via the voice plugin."""
        self.mic_on = not self.mic_on

        if self._jarvis:
            try:
                # Trigger listening through the Tkinter app's toggle
                self._jarvis.root.after(0, self._jarvis.toggle_listening)
            except Exception as e:
                print(f"[JARVIS 3D] Mic toggle error: {e}")
        else:
            # Standalone mode — just toggle visual
            if self.mic_on:
                self.set_mode("listening")
            else:
                self.set_mode("idle")

    def _send_input(self):
        """Send typed text to JARVIS."""
        text = self.input_text.strip()
        if not text:
            return

        self.add_chat("user", text)
        self.input_text = ""
        self.input_active = False

        if self._jarvis:
            try:
                print(f"[JARVIS 3D] Sending to app: '{text}'")
                self._jarvis.root.after(0, lambda t=text: self._jarvis.send_message(t))
            except Exception as e:
                print(f"[JARVIS 3D] Send error: {e}")
                self.add_chat("system", f"Error: {e}")
        else:
            print(f"[JARVIS 3D] No app connected — message not sent: '{text}'")
            self.add_chat("system", "Not connected to JARVIS")


# ═══════════════════════════════════════════════════════════
# Standalone test
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 50)
    print("J.A.R.V.I.S — GPU Core Test")
    print("=" * 50)
    print("Click mic button | Type in input box | ESC clears input")
    print()

    core = JarvisCore3D(width=900, height=700, title="J.A.R.V.I.S — Core")
    # Add some test chat messages
    core.add_chat("system", "All systems nominal")
    core.add_chat("assistant", "Good evening, Dev. How can I help?")
    core.run()
