"""
J.A.R.V.I.S — Gesture Control (MediaPipe Hands)

Turns a camera into a gesture interface for the Stormbreaker wearable. Runs on
the PC brain over frames from any camera — the PC webcam today, the Mi 11X
camera (via the edge bridge) once the goggles are on.

Detects static hand poses from a single frame (robust, low-latency) and maps
them to JARVIS commands:

    open palm   → WAKE / STOP      (attention or halt)
    fist        → SELECT / CONFIRM
    point       → CURSOR / "this"
    pinch       → CLICK
    thumbs up   → YES / CONFIRM
    peace (2)   → MENU / MODE

100% local (MediaPipe runs on-device). No cloud.

Usage:
    from core.gesture_control import get_gestures
    g = get_gestures()
    name, conf = g.recognize_frame(jpeg_bytes)   # -> ("open_palm", 0.9)
"""
from __future__ import annotations

import logging
import math
from typing import Optional

logger = logging.getLogger("jarvis.gesture")

# Gesture → JARVIS intent (what the command means to the assistant).
GESTURE_ACTIONS = {
    "open_palm": "wake_or_stop",
    "fist": "select_confirm",
    "point": "cursor",
    "pinch": "click",
    "thumbs_up": "yes_confirm",
    "peace": "menu_mode",
}


class GestureRecognizer:
    def __init__(self):
        self._hands = None

    def _get_hands(self):
        if self._hands is not None:
            return self._hands
        import mediapipe as mp
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=True, max_num_hands=1,
            min_detection_confidence=0.6)
        return self._hands

    # ─── Landmark helpers ─────────────────────────────────────────────────
    @staticmethod
    def _dist(a, b) -> float:
        return math.hypot(a.x - b.x, a.y - b.y)

    def _fingers_up(self, lm) -> list[bool]:
        """Return [thumb, index, middle, ring, pinky] extended booleans.

        A finger is 'up' if its tip is farther from the wrist than its pip
        joint (works regardless of hand orientation). Thumb uses tip-vs-ip
        along the hand's spread.
        """
        wrist = lm[0]
        tips = [4, 8, 12, 16, 20]
        pips = [3, 6, 10, 14, 18]
        up = []
        for tip, pip in zip(tips, pips):
            up.append(self._dist(lm[tip], wrist) > self._dist(lm[pip], wrist) * 1.05)
        return up

    def _classify(self, lm) -> tuple[Optional[str], float]:
        up = self._fingers_up(lm)
        thumb, index, middle, ring, pinky = up
        n = sum(up[1:])  # non-thumb fingers up

        # Pinch — thumb tip and index tip nearly touching.
        pinch_d = self._dist(lm[4], lm[8])
        hand_span = self._dist(lm[0], lm[9]) + 1e-6
        if pinch_d < 0.35 * hand_span and middle and ring:
            return "pinch", 0.85

        if all(up):
            return "open_palm", 0.9
        if not any(up):
            return "fist", 0.9
        if index and not middle and not ring and not pinky:
            return "point", 0.85
        if thumb and not index and not middle and not ring and not pinky:
            return "thumbs_up", 0.85
        if index and middle and not ring and not pinky:
            return "peace", 0.85
        return None, 0.0

    # ─── Public API ───────────────────────────────────────────────────────
    def recognize_frame(self, jpeg_bytes: bytes) -> tuple[Optional[str], float]:
        """Detect a gesture in a JPEG frame. Returns (gesture, confidence)."""
        try:
            import cv2
            import numpy as np
            arr = np.frombuffer(jpeg_bytes, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return None, 0.0
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = self._get_hands().process(rgb)
            if not res.multi_hand_landmarks:
                return None, 0.0
            lm = res.multi_hand_landmarks[0].landmark
            return self._classify(lm)
        except Exception as e:
            logger.warning("recognize_frame failed: %s", e)
            return None, 0.0

    def recognize_webcam(self, camera_id: int = 0) -> tuple[Optional[str], float]:
        """Grab one webcam frame (warm-up + DSHOW) and detect a gesture."""
        try:
            import cv2
            import time
            cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(camera_id)
            if not cap.isOpened():
                return None, 0.0
            for _ in range(3):
                cap.read(); time.sleep(0.05)
            ok, frame = cap.read()
            cap.release()
            if not ok:
                return None, 0.0
            _, buf = cv2.imencode(".jpg", frame)
            return self.recognize_frame(buf.tobytes())
        except Exception:
            return None, 0.0

    @staticmethod
    def action_for(gesture: Optional[str]) -> Optional[str]:
        return GESTURE_ACTIONS.get(gesture or "")


_gestures: Optional[GestureRecognizer] = None


def get_gestures() -> GestureRecognizer:
    global _gestures
    if _gestures is None:
        _gestures = GestureRecognizer()
    return _gestures
