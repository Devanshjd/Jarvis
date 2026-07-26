"""
JARVIS Gesture Service — turns hand gestures into real JARVIS controls.

Runs on Python 3.11 (MediaPipe). Detects a HELD gesture, debounces it, and
POSTs it to the JARVIS backend (Python 3.13, port 8765), which reacts audibly
and performs the action. This closes the loop: gesture -> JARVIS does something.

Run:
    & "$env:LOCALAPPDATA\\Programs\\Python\\Python311\\python.exe" scripts\\gesture_service.py

Hold a gesture steady for ~half a second to fire it. Same gesture won't
re-fire until you change your hand or ~2.5s passes. Press Q to quit.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
from core.gesture_control import get_gestures, GESTURE_ACTIONS  # noqa: E402

BACKEND = "http://127.0.0.1:8765/api/gesture/action"
STABLE_FRAMES = 5        # gesture must persist this many frames before firing
COOLDOWN_S = 2.5         # don't re-fire the same gesture within this window


def send(gesture: str, action: str) -> bool:
    try:
        data = json.dumps({"gesture": gesture, "action": action}).encode()
        req = urllib.request.Request(BACKEND, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
        return True
    except Exception as e:
        print(f"  [!] could not reach JARVIS backend: {e}")
        return False


def main():
    g = get_gestures()
    import os
    _src = os.environ.get("JARVIS_CAM", "0").strip()
    if _src.isdigit():
        cap = cv2.VideoCapture(int(_src), cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(int(_src))
    else:
        cap = cv2.VideoCapture(_src)   # phone URL (IP Webcam)
    if not cap.isOpened():
        print("Could not open the camera. Set JARVIS_CAM to a device index or phone URL.")
        return

    print("Gesture service live — hold a gesture to control JARVIS. Press Q to quit.")
    stable_g, stable_n = None, 0
    last_fired, last_time = None, 0.0
    flash_until = 0.0
    flash_text = ""

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        ok2, buf = cv2.imencode(".jpg", frame)
        gesture, _ = g.recognize_frame(buf.tobytes()) if ok2 else (None, 0.0)

        if gesture == stable_g:
            stable_n += 1
        else:
            stable_g, stable_n = gesture, 1

        now = time.time()
        if gesture and stable_n == STABLE_FRAMES:
            if gesture != last_fired or (now - last_time) > COOLDOWN_S:
                action = GESTURE_ACTIONS.get(gesture, "")
                if send(gesture, action):
                    print(f"  {gesture:12s} -> JARVIS ({action})")
                    flash_text = f"SENT: {gesture} -> {action}"
                    flash_until = now + 1.2
                    last_fired, last_time = gesture, now

        # overlay
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 70), (12, 12, 12), -1)
        cv2.putText(frame, f"GESTURE: {(gesture or '-').upper()}", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (32, 176, 255) if gesture else (120, 120, 120), 2)
        if now < flash_until:
            cv2.putText(frame, flash_text, (20, 58),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 255, 120), 2)
        else:
            cv2.putText(frame, "hold a gesture steady to send", (20, 58),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

        cv2.imshow("JARVIS — Gesture Control (LIVE, press Q to quit)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
