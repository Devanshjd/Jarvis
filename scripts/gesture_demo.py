"""
Live gesture demo — wave your hand at the webcam and watch JARVIS read it.

Run with Python 3.11 (MediaPipe works there, not 3.13):
    C:\\Users\\Devansh\\AppData\\Local\\Programs\\Python\\Python311\\python.exe scripts\\gesture_demo.py

Shows a webcam window with the detected gesture + mapped JARVIS action.
Gestures: open palm, fist, point, pinch, thumbs up, peace. Press Q to quit.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
from core.gesture_control import get_gestures, GESTURE_ACTIONS  # noqa: E402


def main():
    g = get_gestures()
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open the webcam.")
        return

    print("Live gesture demo — press Q in the window to quit.")
    last = ("", 0.0)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)  # mirror
        ok2, buf = cv2.imencode(".jpg", frame)
        gesture, conf = g.recognize_frame(buf.tobytes()) if ok2 else (None, 0.0)

        label = gesture or "—"
        action = GESTURE_ACTIONS.get(gesture or "", "")
        colour = (32, 176, 255) if gesture else (120, 120, 120)  # BGR amber-ish
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 70), (12, 12, 12), -1)
        cv2.putText(frame, f"GESTURE: {label.upper()}", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2)
        cv2.putText(frame, f"-> JARVIS: {action}", (20, 58),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        if gesture and gesture != last[0]:
            print(f"  {gesture:12s} -> {action}")
            last = (gesture, time.time())

        cv2.imshow("JARVIS — Gesture Control (press Q to quit)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
