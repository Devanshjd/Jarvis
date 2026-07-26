"""
JARVIS Gesture Mouse — full hand control of the OS cursor + JARVIS wake.

Runs on Python 3.11 (MediaPipe). One unified controller — no conflicting
gestures. Testable on the desktop webcam now; when the goggles arrive only the
camera source changes.

Controls (right hand, upright):
    index up (only)                 → MOVE cursor
    index up + thumb touches index  → LEFT CLICK
    index + middle up, tips TOGETHER → DOUBLE CLICK
    fist, move hand up/down          → SCROLL
    open palm                        → WAKE JARVIS ("At your service")
    (rest your hand / drop it        → cursor naturally stops — no pause gesture)

Safety: move the real mouse to the TOP-LEFT corner to abort (failsafe).
Press Q to quit.

Run:
    & "$env:LOCALAPPDATA\\Programs\\Python\\Python311\\python.exe" scripts\\gesture_mouse.py
"""
import ctypes
import json
import math
import time
import urllib.request

import cv2
import mediapipe as mp
import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0

SCREEN_W, SCREEN_H = pyautogui.size()
FRAME_MARGIN = 0.15
SMOOTH = 0.35
CLICK_COOLDOWN = 0.6
DCLICK_COOLDOWN = 0.8
SCROLL_GAIN = 40
WAKE_URL = "http://127.0.0.1:8765/api/gesture/action"

_user32 = ctypes.windll.user32


def set_cursor(x, y):
    _user32.SetCursorPos(int(x), int(y))


def wake_jarvis():
    try:
        data = json.dumps({"gesture": "open_palm", "action": "wake_or_stop"}).encode()
        req = urllib.request.Request(WAKE_URL, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pass  # backend may be down; don't crash the controller


def main():
    hands = mp.solutions.hands.Hands(
        static_image_mode=False, max_num_hands=1,
        min_detection_confidence=0.7, min_tracking_confidence=0.6)
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

    print("Gesture mouse live. index=move, thumb-tap=click, two-fingers-together"
          "=double-click, fist=scroll, palm=wake JARVIS. Q to quit.")
    prev_x, prev_y = SCREEN_W / 2, SCREEN_H / 2
    last_click = last_dclick = last_wake = 0.0
    scroll_anchor = None

    def dist(a, b):
        return math.hypot(a.x - b.x, a.y - b.y)

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        res = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        mode = "no hand"
        if res.multi_hand_landmarks:
            lm = res.multi_hand_landmarks[0].landmark
            index_up = lm[8].y < lm[6].y
            middle_up = lm[12].y < lm[10].y
            ring_up = lm[16].y < lm[14].y
            pinky_up = lm[20].y < lm[18].y
            span = dist(lm[0], lm[9]) + 1e-6
            thumb_index = dist(lm[4], lm[8]) / span     # thumb-tip to index-tip
            index_middle = dist(lm[8], lm[12]) / span   # index-tip to middle-tip
            now = time.time()

            if index_up and middle_up and ring_up and pinky_up:
                # OPEN PALM -> wake JARVIS (debounced)
                mode = "WAKE JARVIS"
                scroll_anchor = None
                if now - last_wake > 2.5:
                    wake_jarvis()
                    last_wake = now
            elif not index_up and not middle_up and not ring_up and not pinky_up:
                # FIST -> scroll
                mode = "SCROLL"
                cy = lm[9].y
                if scroll_anchor is None:
                    scroll_anchor = cy
                elif abs(scroll_anchor - cy) > 0.02:
                    pyautogui.scroll(int((scroll_anchor - cy) * SCROLL_GAIN * 20))
                    scroll_anchor = cy
            elif index_up and middle_up and not ring_up and not pinky_up and index_middle < 0.6:
                # INDEX + MIDDLE tips together -> DOUBLE CLICK
                scroll_anchor = None
                if now - last_dclick > DCLICK_COOLDOWN:
                    pyautogui.doubleClick()
                    last_dclick = now
                    mode = "DOUBLE CLICK"
                else:
                    mode = "double(cooldown)"
            elif index_up and not middle_up:
                # POINT -> move cursor; thumb pinch -> click
                scroll_anchor = None
                nx = (lm[8].x - FRAME_MARGIN) / (1 - 2 * FRAME_MARGIN)
                ny = (lm[8].y - FRAME_MARGIN) / (1 - 2 * FRAME_MARGIN)
                tx = min(max(nx, 0), 1) * SCREEN_W
                ty = min(max(ny, 0), 1) * SCREEN_H
                cx = prev_x + (tx - prev_x) * SMOOTH
                cy = prev_y + (ty - prev_y) * SMOOTH
                set_cursor(cx, cy)
                prev_x, prev_y = cx, cy
                if thumb_index < 0.45:
                    if now - last_click > CLICK_COOLDOWN:
                        pyautogui.click()
                        last_click = now
                        mode = "CLICK"
                    else:
                        mode = "click(cooldown)"
                else:
                    mode = "MOVE"
            else:
                mode = "idle"

            ix, iy = int(lm[8].x * w), int(lm[8].y * h)
            cv2.circle(frame, (ix, iy), 10, (32, 176, 255), 2)

        cv2.rectangle(frame, (0, 0), (w, 44), (12, 12, 12), -1)
        cv2.putText(frame, f"MODE: {mode}", (16, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (32, 176, 255), 2)
        cv2.imshow("JARVIS — Gesture Mouse (Q to quit)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
