"""
J.A.R.V.I.S — Face Recognition (Face ID)

Lets JARVIS recognize its owner by face — 100% local, no cloud, using
OpenCV's built-in LBPH recognizer (no dlib/face_recognition needed).

Enroll once (capture ~30 face samples), then JARVIS knows you: greets you
by name, personalizes, and can gate sensitive actions to your face
(the security angle for the military path — "only Dev can authorize this").

Design:
  - Haar cascade for face DETECTION (built into OpenCV)
  - LBPH recognizer for face IDENTIFICATION (trains in seconds, runs fast)
  - Model + labels persisted to ~/.jarvis/faceid/
  - Confidence-thresholded: unknown faces are reported as unknown, never
    misattributed (important — a false "yes that's Dev" would defeat the
    security purpose)

Usage:
    from core.face_id import FaceID
    fid = FaceID()
    fid.enroll("Dev", num_samples=30)      # capture from webcam
    who, confidence = fid.recognize_frame(jpeg_bytes)   # -> ("Dev", 0.82)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.faceid")

FACEID_DIR = Path.home() / ".jarvis" / "faceid"
MODEL_PATH = FACEID_DIR / "lbph_model.yml"
LABELS_PATH = FACEID_DIR / "labels.json"

# LBPH confidence is a DISTANCE — lower = better match. Below this = recognized.
RECOGNIZE_THRESHOLD = 70.0


class FaceID:
    """Local face enrollment + recognition using OpenCV LBPH."""

    def __init__(self):
        FACEID_DIR.mkdir(parents=True, exist_ok=True)
        self._recognizer = None
        self._labels: dict[int, str] = {}
        self._detector = None
        self._load()

    # ─── Setup ────────────────────────────────────────────────────────────

    def _get_detector(self):
        if self._detector is not None:
            return self._detector
        import cv2
        # Haar cascade ships with OpenCV
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._detector = cv2.CascadeClassifier(cascade_path)
        return self._detector

    def _load(self):
        """Load a trained model + labels if they exist."""
        try:
            import cv2
            if MODEL_PATH.exists() and LABELS_PATH.exists():
                self._recognizer = cv2.face.LBPHFaceRecognizer_create()
                self._recognizer.read(str(MODEL_PATH))
                self._labels = {
                    int(k): v for k, v in
                    json.loads(LABELS_PATH.read_text(encoding="utf-8")).items()
                }
                logger.info("FaceID model loaded — enrolled: %s",
                            list(self._labels.values()))
        except Exception as e:
            logger.warning("FaceID load failed: %s", e)

    def is_enrolled(self) -> bool:
        return self._recognizer is not None and bool(self._labels)

    def enrolled_names(self) -> list[str]:
        return list(self._labels.values())

    # ─── Face detection helper ────────────────────────────────────────────

    def _detect_faces(self, gray):
        detector = self._get_detector()
        faces = detector.detectMultiScale(gray, scaleFactor=1.1,
                                          minNeighbors=5, minSize=(80, 80))
        return faces

    # ─── Enrollment ───────────────────────────────────────────────────────

    def enroll(self, name: str, num_samples: int = 30, camera_id: int = 0) -> dict:
        """Capture face samples from the webcam and train the recognizer.

        Adds `name` to the enrolled set (or re-trains including it). Returns
        {success, samples_captured, names}.
        """
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            return {"success": False, "error": "Could not open camera"}

        # Assign a label id
        existing_ids = list(self._labels.keys())
        # Reuse id if re-enrolling the same name
        label_id = next((i for i, n in self._labels.items() if n == name), None)
        if label_id is None:
            label_id = (max(existing_ids) + 1) if existing_ids else 0

        samples, labels = self._load_existing_training_data()
        captured = 0
        logger.info("Enrolling %r — look at the camera, move your head slightly", name)
        deadline = time.time() + 30  # 30s max

        while captured < num_samples and time.time() < deadline:
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._detect_faces(gray)
            for (x, y, w, h) in faces:
                face_roi = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
                samples.append(face_roi)
                labels.append(label_id)
                captured += 1
                if captured >= num_samples:
                    break
            time.sleep(0.05)

        cap.release()

        if captured < 5:
            return {"success": False, "error": f"Only captured {captured} faces — need better lighting/framing"}

        # Train
        self._labels[label_id] = name
        self._recognizer = cv2.face.LBPHFaceRecognizer_create()
        self._recognizer.train(samples, np.array(labels))
        self._recognizer.write(str(MODEL_PATH))
        LABELS_PATH.write_text(
            json.dumps({str(k): v for k, v in self._labels.items()}, ensure_ascii=False),
            encoding="utf-8")
        # Persist raw samples for future re-training
        self._save_training_data(samples, labels)

        logger.info("Enrolled %r with %d samples", name, captured)
        return {"success": True, "samples_captured": captured,
                "names": list(self._labels.values())}

    def _training_data_path(self) -> Path:
        return FACEID_DIR / "training_data.npz"

    def _load_existing_training_data(self):
        import numpy as np
        p = self._training_data_path()
        if p.exists():
            try:
                data = np.load(p, allow_pickle=True)
                return list(data["samples"]), list(data["labels"])
            except Exception:
                pass
        return [], []

    def _save_training_data(self, samples, labels):
        import numpy as np
        try:
            np.savez_compressed(self._training_data_path(),
                                samples=np.array(samples), labels=np.array(labels))
        except Exception as e:
            logger.debug("Could not persist training data: %s", e)

    # ─── Recognition ──────────────────────────────────────────────────────

    def recognize_frame(self, jpeg_bytes: bytes) -> tuple[Optional[str], float]:
        """Recognize the (largest) face in a JPEG frame.

        Returns (name, confidence 0-1) or (None, 0.0) if no face / unknown.
        confidence is normalized: 1.0 = perfect match, 0.0 = no match.
        """
        if not self.is_enrolled():
            return None, 0.0
        try:
            import cv2
            import numpy as np
            arr = np.frombuffer(jpeg_bytes, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return None, 0.0
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._detect_faces(gray)
            if len(faces) == 0:
                return None, 0.0
            # Use the largest face
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            face_roi = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
            label_id, distance = self._recognizer.predict(face_roi)
            if distance <= RECOGNIZE_THRESHOLD:
                name = self._labels.get(label_id, "unknown")
                # Normalize distance to a 0-1 confidence
                conf = max(0.0, 1.0 - distance / 100.0)
                return name, round(conf, 2)
            return None, 0.0   # face detected but not recognized
        except Exception as e:
            logger.warning("recognize_frame failed: %s", e)
            return None, 0.0

    def recognize_webcam(self, camera_id: int = 0) -> tuple[Optional[str], float]:
        """Grab one frame from the webcam and recognize."""
        try:
            import cv2
            cap = cv2.VideoCapture(camera_id)
            if not cap.isOpened():
                return None, 0.0
            ok, frame = cap.read()
            cap.release()
            if not ok:
                return None, 0.0
            _, buf = cv2.imencode(".jpg", frame)
            return self.recognize_frame(buf.tobytes())
        except Exception:
            return None, 0.0


# Module-level singleton
_faceid: Optional[FaceID] = None


def get_faceid() -> FaceID:
    global _faceid
    if _faceid is None:
        _faceid = FaceID()
    return _faceid
