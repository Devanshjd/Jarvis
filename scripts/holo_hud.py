"""
JARVIS Holo-HUD — a gesture-driven radial launcher (Iron-Man style).

Adapted from Concept-Bytes' HoloMat (MIT) — https://github.com/Concept-Bytes/Holomat
— but rebuilt to fit JARVIS: Stormbreaker amber theme, driven by the SAME
MediaPipe pinch gesture as scripts/gesture_mouse.py, and wired to the JARVIS
backend at :8765 instead of standalone pygame games.

What it does:
    · Full-screen radial HUD: a center hub + 8 action rings.
    · Your hand (webcam) moves a reticle; PINCH (thumb+index) selects.
    · Hover the hub to toggle the ring open/closed; pinch a ring to fire its
      JARVIS action (POSTed to the backend, same contract as the wake gesture).

Why it's built this way (forward-compatible):
    Input → CoordinateMapper → HUD. Today the mapper is IDENTITY (webcam→screen).
    Swap in HomographyMapper('M.npy') later and the SAME HUD drives a projector
    table or goggles — only the mapper changes, nothing else.

Runs on Python 3.11 (MediaPipe), like the rest of the gesture stack:
    & "$env:LOCALAPPDATA\\Programs\\Python\\Python311\\python.exe" scripts\\holo_hud.py

Needs: mediapipe, opencv-python, pygame  (pip install pygame if missing)
Press Q or ESC to quit.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request

import cv2
import mediapipe as mp


def _open_camera():
    """Open the camera from JARVIS_CAM env var: a device index ("0", "1") or a
    URL for a phone stream (IP Webcam: http://<phone-ip>:8080/video). Defaults
    to the built-in webcam."""
    src = os.environ.get("JARVIS_CAM", "0").strip()
    if src.isdigit():
        cap = cv2.VideoCapture(int(src), cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(int(src))
        return cap
    return cv2.VideoCapture(src)   # phone URL / RTSP / MJPEG

try:
    import pygame
    from pygame import mixer
except ImportError:
    sys.exit("pygame is not installed. Run:  py -3.11 -m pip install pygame")

# ─── JARVIS backend (same endpoint the wake gesture already uses) ────────────
BACKEND = "http://127.0.0.1:8765/api/gesture/action"

# ─── The 8 rings: label + the action string sent to the backend ──────────────
# Map these to real JARVIS commands in your :8765 handler. Labels show on-HUD.
ACTIONS = [
    ("Voice",   "wake_voice"),
    ("Earn",    "open_earn"),
    ("Bounty",  "bounty_status"),
    ("Hunt",    "bounty_hunt"),
    ("Memory",  "recall_memory"),
    ("Oracle",  "code_oracle"),
    ("Face ID", "faceid_status"),
    ("Sleep",   "sleep"),
]

# ─── Stormbreaker amber tactical palette (matches the JARVIS re-skin) ─────────
BG        = (8, 9, 12)
AMBER     = (255, 176, 0)
AMBER_DIM = (120, 82, 0)
AMBER_HOT = (255, 214, 122)
INK       = (18, 20, 26)
WHITE     = (240, 240, 245)

# ─── Interaction tuning ──────────────────────────────────────────────────────
FRAME_MARGIN = 0.15      # ignore the outer 15% of the frame (edges are jittery)
SMOOTH = 0.35            # reticle smoothing (0=instant, 1=frozen)
PINCH_THRESH = 0.45      # thumb-tip↔index-tip distance / hand-span → pinch
SELECT_COOLDOWN = 0.9    # seconds between selections
TOGGLE_COOLDOWN = 1.0    # seconds between hub open/close


class CoordinateMapper:
    """Maps a normalized (0..1) hand point to HUD pixels.

    IDENTITY today (webcam → screen). For a projector table or goggles, subclass
    with a homography load (np.load('M.npy') + cv2.perspectiveTransform) — the
    HUD never needs to know which mapper it's using."""

    def __init__(self, width: int, height: int, margin: float = FRAME_MARGIN):
        self.w, self.h, self.m = width, height, margin

    def to_screen(self, nx: float, ny: float) -> tuple[int, int]:
        # de-margin, then clamp into the usable frame
        sx = (nx - self.m) / (1 - 2 * self.m)
        sy = (ny - self.m) / (1 - 2 * self.m)
        return (int(min(max(sx, 0), 1) * self.w),
                int(min(max(sy, 0), 1) * self.h))


class Ring:
    def __init__(self, label, action, home, target, radius, is_hub=False):
        self.label, self.action = label, action
        self.home, self.target = home, target       # collapsed vs expanded pos
        self.pos = list(home)
        self.radius = radius
        self.is_hub = is_hub
        self.visible = is_hub
        self.hover = 0.0                             # 0..1 hover glow

    def update_pos(self, t: float):
        # t: 0 collapsed → 1 expanded (eased)
        e = t * t * (3 - 2 * t)                      # smoothstep
        self.pos[0] = self.home[0] + (self.target[0] - self.home[0]) * e
        self.pos[1] = self.home[1] + (self.target[1] - self.home[1]) * e

    def contains(self, p) -> bool:
        return math.hypot(p[0] - self.pos[0], p[1] - self.pos[1]) <= self.radius

    def draw(self, screen, font):
        if not self.visible and not self.is_hub:
            return
        r = int(self.radius * (1 + 0.12 * self.hover))
        glow = int(60 + 120 * self.hover)
        # outer glow
        pygame.draw.circle(screen, AMBER_DIM, self.pos, r + 6, 2)
        pygame.draw.circle(screen, INK, self.pos, r)
        pygame.draw.circle(screen, (glow, int(glow * 0.6), 0), self.pos, r, 3)
        col = AMBER_HOT if self.hover > 0.5 else AMBER
        label = "JARVIS" if self.is_hub else self.label
        surf = font.render(label, True, col)
        screen.blit(surf, surf.get_rect(center=self.pos))


def build_rings(cx, cy):
    hub = Ring("JARVIS", "hub", (cx, cy), (cx, cy), 90, is_hub=True)
    rings = [hub]
    n = len(ACTIONS)
    dist = min(cx, cy) * 0.62
    for i, (label, action) in enumerate(ACTIONS):
        a = math.radians(360 / n * i - 90)
        tx, ty = cx + int(dist * math.cos(a)), cy + int(dist * math.sin(a))
        rings.append(Ring(label, action, (cx, cy), (tx, ty), 62))
    return rings


def send_action(action: str):
    """Fire a HUD action at the JARVIS backend (same contract as the wake
    gesture). Backend down? Print and carry on — never crash the HUD."""
    try:
        data = json.dumps({"source": "holo_hud", "action": action}).encode()
        req = urllib.request.Request(BACKEND, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2).read()
        print(f"[holo] → backend: {action}")
    except Exception:
        print(f"[holo] (backend offline) would fire: {action}")


def main():
    pygame.init()
    try:
        mixer.init()
    except Exception:
        pass
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("JARVIS Holo-HUD")
    W, H = screen.get_size()
    font = pygame.font.Font(None, 34)
    small = pygame.font.Font(None, 26)
    cx, cy = W // 2, H // 2

    mapper = CoordinateMapper(W, H)
    rings = build_rings(cx, cy)
    hub = rings[0]
    expanded = False
    expand_t = 0.0
    last_toggle = last_select = 0.0
    reticle = [cx, cy]

    hands = mp.solutions.hands.Hands(
        static_image_mode=False, max_num_hands=1,
        min_detection_confidence=0.6, min_tracking_confidence=0.5)
    cap = _open_camera()
    if not cap.isOpened():
        sys.exit("Could not open the camera. Set JARVIS_CAM to a device index or "
                 "phone URL (e.g. http://192.168.1.42:8080/video).")

    def dist(a, b):
        return math.hypot(a.x - b.x, a.y - b.y)

    clock = pygame.time.Clock()
    running = True
    print("Holo-HUD live. Point to aim, PINCH to select. Hub = open/close. Q/ESC to quit.")
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN and e.key in (pygame.K_q, pygame.K_ESCAPE):
                running = False

        ok, frame = cap.read()
        pinch = False
        finger = None
        if ok:
            frame = cv2.flip(frame, 1)
            res = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0].landmark
                span = dist(lm[0], lm[9]) + 1e-6
                pinch = dist(lm[4], lm[8]) / span < PINCH_THRESH
                finger = mapper.to_screen(lm[8].x, lm[8].y)

        # smooth the reticle toward the finger
        if finger:
            reticle[0] += (finger[0] - reticle[0]) * SMOOTH
            reticle[1] += (finger[1] - reticle[1]) * SMOOTH
        rp = (int(reticle[0]), int(reticle[1]))

        # animate expand/collapse
        expand_t += (0.14 if expanded else -0.14)
        expand_t = max(0.0, min(1.0, expand_t))
        for r in rings[1:]:
            r.visible = expand_t > 0.01
            r.update_pos(expand_t)

        now = time.time()
        # hover + selection
        for r in rings:
            hit = (r.visible or r.is_hub) and r.contains(rp) and finger is not None
            r.hover += ((1.0 if hit else 0.0) - r.hover) * 0.25
            if hit and pinch:
                if r.is_hub and now - last_toggle > TOGGLE_COOLDOWN:
                    expanded = not expanded
                    last_toggle = now
                    _play(mixer, "home")
                elif not r.is_hub and expanded and now - last_select > SELECT_COOLDOWN:
                    send_action(r.action)
                    last_select = now
                    _play(mixer, "confirmation")

        # ── render ──
        screen.fill(BG)
        _grid(screen, W, H)
        for r in rings:
            r.draw(screen, font)
        # reticle
        col = AMBER_HOT if pinch else AMBER
        pygame.draw.circle(screen, col, rp, 16, 2)
        pygame.draw.circle(screen, col, rp, 3)
        status = "PINCH" if pinch else ("TRACKING" if finger else "no hand")
        screen.blit(small.render(f"JARVIS · {status}", True, AMBER_DIM), (24, 20))
        pygame.display.flip()
        clock.tick(60)

    cap.release()
    pygame.quit()


def _grid(screen, W, H, step=64):
    for x in range(0, W, step):
        pygame.draw.line(screen, (14, 15, 20), (x, 0), (x, H))
    for y in range(0, H, step):
        pygame.draw.line(screen, (14, 15, 20), (0, y), (W, y))


def _play(mixer, name):
    try:
        mixer.music.load(f"./scripts/holo_audio/{name}.wav")
        mixer.music.play()
    except Exception:
        pass  # audio optional


if __name__ == "__main__":
    main()
