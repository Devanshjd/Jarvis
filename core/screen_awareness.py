"""
J.A.R.V.I.S — Continuous Screen Awareness

Periodically captures screenshots, OCRs them, and detects what the user
is doing so JARVIS can offer contextual, proactive assistance.

If the user is struggling (repeated errors, frantic window-switching,
same page refreshed over and over) JARVIS can step in and help.

Dependencies (all optional — degrades gracefully):
  - PIL / Pillow   → screenshot capture
  - pytesseract    → OCR text extraction
"""

import re
import time
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Any

logger = logging.getLogger("jarvis.screen_awareness")

# ── Optional imports ──────────────────────────────────────────

_HAS_PIL = False
_HAS_TESSERACT = False

try:
    from PIL import ImageGrab
    _HAS_PIL = True
except ImportError:
    logger.info("PIL not available — screenshot capture disabled")

try:
    import pytesseract
    _HAS_TESSERACT = True
except ImportError:
    logger.info("pytesseract not available — OCR disabled, using window-title fallback")


# ── Constants ─────────────────────────────────────────────────

THUMBNAIL_SIZE = (800, 600)

# Regex patterns that indicate something went wrong on screen
ERROR_PATTERNS = [
    re.compile(r"\berror\b", re.IGNORECASE),
    re.compile(r"\bexception\b", re.IGNORECASE),
    re.compile(r"\bfailed\b", re.IGNORECASE),
    re.compile(r"\bdenied\b", re.IGNORECASE),
    re.compile(r"\bnot found\b", re.IGNORECASE),
    re.compile(r"\btraceback\b", re.IGNORECASE),
    re.compile(r"\bfatal\b", re.IGNORECASE),
    re.compile(r"\bsegmentation fault\b", re.IGNORECASE),
    re.compile(r"\bcommand not found\b", re.IGNORECASE),
    re.compile(r"\bpermission denied\b", re.IGNORECASE),
    re.compile(r"\bsyntax error\b", re.IGNORECASE),
    re.compile(r"\bundefined\b", re.IGNORECASE),
]

DEFAULT_CAPTURE_INTERVAL = 30  # seconds
ACTIVITY_LOG_MAX = 200
RECENT_TEXT_BUFFER = 10        # keep last N OCR results for repetition check


# ── Data structures ───────────────────────────────────────────

@dataclass
class ActivityEntry:
    """Single entry in the activity log."""
    timestamp: float
    window_title: str
    detected_activity: str
    error_detected: bool = False
    text_hash: int = 0          # hash of OCR text for quick comparison


@dataclass
class ScreenState:
    """Current state derived from screen analysis."""
    current_text: str = ""
    window_title: str = ""
    error_count: int = 0
    struggle_score: int = 0     # 0-100
    last_capture_time: float = 0.0
    repeated_content_count: int = 0
    rapid_switch_count: int = 0


# ── Main class ────────────────────────────────────────────────

class ScreenAwareness:
    """
    Periodically captures the screen, extracts text via OCR, and
    tracks user activity patterns to detect when they might need help.

    Works in three tiers:
      1. Full OCR   — PIL + pytesseract available
      2. Screenshot  — PIL only (no text, but can still track window titles)
      3. Titles only — neither available, pulls from AwarenessEngine
    """

    def __init__(self, jarvis):
        """
        Parameters
        ----------
        jarvis : the main JARVIS app instance — used to read
                 awareness engine state and (optionally) push
                 proactive suggestions.
        """
        self.jarvis = jarvis
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._capture_lock = threading.Lock()

        # Configurable
        screen_cfg = getattr(getattr(jarvis, "config", {}), "get", lambda *_: {})("screen", {})
        self.capture_interval: float = float(screen_cfg.get("live_interval", DEFAULT_CAPTURE_INTERVAL))
        self.analysis_interval: float = float(screen_cfg.get("analysis_interval", 12.0))
        self.live_frame_ttl: float = float(screen_cfg.get("live_frame_ttl", max(self.capture_interval * 1.5, 5.0)))

        # State
        self.state = ScreenState()
        self.activity_log: deque[ActivityEntry] = deque(maxlen=ACTIVITY_LOG_MAX)
        self._recent_text_hashes: deque[int] = deque(maxlen=RECENT_TEXT_BUFFER)
        self._recent_windows: deque[Tuple[float, str]] = deque(maxlen=50)
        self._latest_image = None
        self._latest_capture_time = 0.0
        self._last_ocr_time = 0.0

        # Capability flags
        self._can_screenshot = _HAS_PIL
        self._can_ocr = _HAS_PIL and _HAS_TESSERACT

        tier = (
            "full OCR" if self._can_ocr
            else "screenshots only" if self._can_screenshot
            else "window-title fallback"
        )
        logger.info("ScreenAwareness initialised — tier: %s", tier)

    # ── Lifecycle ─────────────────────────────────────────────

    def start(self):
        """Start the background monitoring loop."""
        if self._running:
            logger.warning("ScreenAwareness already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="jarvis-screen-awareness",
        )
        self._thread.start()
        logger.info("ScreenAwareness started (interval=%ds)", self.capture_interval)

    def stop(self):
        """Signal the monitoring thread to stop."""
        self._running = False
        logger.info("ScreenAwareness stopping")

    # ── Background loop ───────────────────────────────────────

    def _monitor_loop(self):
        """Main loop — runs in a daemon thread."""
        while self._running:
            try:
                self._capture_and_analyze()
            except Exception:
                logger.exception("Error during screen capture/analysis")

            # Sleep in short increments so we can stop quickly
            waited = 0.0
            while waited < self.capture_interval and self._running:
                time.sleep(min(1.0, self.capture_interval - waited))
                waited += 1.0

        logger.info("ScreenAwareness monitor loop exited")

    # ── Capture & Analyse ─────────────────────────────────────

    def _capture_and_analyze(self):
        """Take a screenshot, OCR it, and update internal state."""
        now = time.time()
        window_title = self._get_window_title()
        screenshot = None

        # ---- Screenshot + OCR path ----
        if self._can_screenshot:
            try:
                screenshot = ImageGrab.grab()
                with self._lock:
                    self._latest_image = screenshot.copy()
                    self._latest_capture_time = now
            except Exception:
                logger.debug("Screenshot capture failed")

        with self._lock:
            previous_text = self.state.current_text or window_title

        ocr_text = previous_text
        should_run_ocr = (
            screenshot is not None
            and self._can_ocr
            and (not previous_text or (now - self._last_ocr_time) >= self.analysis_interval)
        )

        if should_run_ocr:
            try:
                analysis_img = screenshot.copy()
                analysis_img = analysis_img.resize(THUMBNAIL_SIZE)
                ocr_text = pytesseract.image_to_string(analysis_img) or previous_text
                self._last_ocr_time = now
            except Exception:
                logger.debug("OCR failed on this frame, keeping previous text")

        # If we got no OCR text, use the window title as the "text"
        if not ocr_text:
            ocr_text = window_title

        # ---- Detect errors in text ----
        errors_found = sum(1 for p in ERROR_PATTERNS if p.search(ocr_text))
        has_error = errors_found > 0

        # ---- Detect activity category ----
        activity = self._classify_activity(window_title, ocr_text)

        # ---- Track repetition ----
        text_hash = hash(ocr_text.strip()[:500])  # hash first 500 chars
        self._recent_text_hashes.append(text_hash)

        # ---- Track window switching ----
        self._recent_windows.append((now, window_title))

        # ---- Build log entry ----
        entry = ActivityEntry(
            timestamp=now,
            window_title=window_title,
            detected_activity=activity,
            error_detected=has_error,
            text_hash=text_hash,
        )
        self.activity_log.append(entry)

        # ---- Update state under lock ----
        with self._lock:
            self.state.current_text = ocr_text
            self.state.window_title = window_title
            self.state.last_capture_time = now
            if has_error:
                self.state.error_count += errors_found
            self.state.repeated_content_count = self._count_repeated_content()
            self.state.rapid_switch_count = self._count_rapid_switches()
            self.state.struggle_score = self._detect_struggle()

    def get_live_frame(self, max_age: Optional[float] = None) -> Optional[dict]:
        """
        Return the latest cached screenshot if it is still fresh enough.

        The returned image is a copy so callers can crop/resize safely.
        """
        ttl = self.live_frame_ttl if max_age is None else max_age
        with self._lock:
            if self._latest_image is None or not self._latest_capture_time:
                return None
            age = time.time() - self._latest_capture_time
            if age > ttl:
                return None
            return {
                "image": self._latest_image.copy(),
                "captured_at": self._latest_capture_time,
                "window_title": self.state.window_title,
                "text": self.state.current_text,
                "age": age,
            }

    def capture_now(self, analyze: bool = False) -> Optional[dict]:
        """
        Capture a fresh screen frame immediately.

        This is used as a fast path for tools that need a current image without
        waiting for the background loop.
        """
        if not self._can_screenshot:
            return None

        with self._capture_lock:
            try:
                screenshot = ImageGrab.grab()
                now = time.time()
                window_title = self._get_window_title()
                with self._lock:
                    self._latest_image = screenshot.copy()
                    self._latest_capture_time = now
                    self.state.window_title = window_title
                    self.state.last_capture_time = now
                if analyze:
                    self._capture_and_analyze()
                return self.get_live_frame(max_age=self.live_frame_ttl)
            except Exception:
                logger.exception("Immediate screen capture failed")
                return None

    # ── Struggle detection ────────────────────────────────────

    def _detect_struggle(self) -> int:
        """
        Compute a 0-100 struggle score based on recent patterns.

        Factors:
          - Errors detected in recent frames
          - Repeated identical screen content
          - Rapid window switching (confusion)
          - Same page / command repeated many times

        Returns an integer 0 (calm) to 100 (very stuck).
        """
        score = 0

        # --- Factor 1: recent errors ---
        recent = list(self.activity_log)[-10:]  # last 10 entries
        recent_error_count = sum(1 for e in recent if e.error_detected)
        score += min(recent_error_count * 8, 40)  # up to 40 points

        # --- Factor 2: repeated content (same screen 3+ times) ---
        repeated = self.state.repeated_content_count
        if repeated >= 3:
            score += min((repeated - 2) * 10, 30)  # up to 30 points

        # --- Factor 3: rapid window switching ---
        switches = self.state.rapid_switch_count
        if switches > 5:
            score += min((switches - 5) * 5, 20)  # up to 20 points

        # --- Factor 4: same error text appearing multiple captures ---
        if recent_error_count >= 3:
            score += 10  # bonus for persistent errors

        return min(score, 100)

    def _count_repeated_content(self) -> int:
        """How many of the last N frames have identical text."""
        if len(self._recent_text_hashes) < 2:
            return 0
        latest = self._recent_text_hashes[-1]
        return sum(1 for h in self._recent_text_hashes if h == latest)

    def _count_rapid_switches(self) -> int:
        """Count distinct windows in the last 30 seconds."""
        now = time.time()
        cutoff = now - 30
        recent_titles = {
            title for ts, title in self._recent_windows if ts >= cutoff and title
        }
        return len(recent_titles)

    # ── Activity classification ───────────────────────────────

    @staticmethod
    def _classify_activity(window_title: str, text: str) -> str:
        """Rough classification of what the user is doing."""
        title_lower = window_title.lower()
        text_lower = text.lower()

        if any(kw in title_lower for kw in ["code", "pycharm", "sublime", "vim", "nvim", "idea"]):
            return "coding"
        if any(kw in title_lower for kw in ["chrome", "firefox", "edge", "brave", "opera"]):
            if any(kw in text_lower for kw in ["stackoverflow", "github", "docs", "documentation"]):
                return "researching"
            return "browsing"
        if any(kw in title_lower for kw in ["terminal", "cmd", "powershell", "bash", "wt"]):
            return "terminal"
        if any(kw in title_lower for kw in ["word", "docs", "notion", "obsidian"]):
            return "writing"
        if any(kw in title_lower for kw in ["discord", "slack", "teams", "telegram", "whatsapp"]):
            return "communicating"
        if any(kw in title_lower for kw in ["explorer", "files", "finder"]):
            return "file_management"
        return "other"

    # ── Window title helper ───────────────────────────────────

    def _get_window_title(self) -> str:
        """
        Get the current active window title.

        Prefers data from the existing AwarenessEngine if available,
        otherwise returns an empty string.
        """
        try:
            awareness = getattr(self.jarvis, "awareness", None)
            if awareness is not None:
                win = getattr(awareness, "active_window", None)
                if win is not None:
                    return getattr(win, "title", "") or ""
        except Exception:
            pass
        return ""

    # ── Public query API ──────────────────────────────────────

    def get_screen_context(self) -> str:
        """
        Return a concise string describing the current screen state,
        suitable for injection into an LLM system prompt.
        """
        with self._lock:
            s = self.state

        parts: List[str] = []

        if s.window_title:
            parts.append(f"Active window: {s.window_title}")

        # Summarise the OCR text (first 300 chars)
        if s.current_text and s.current_text != s.window_title:
            preview = s.current_text[:300].replace("\n", " ").strip()
            if preview:
                parts.append(f"Screen text: {preview}")

        if s.struggle_score > 30:
            parts.append(f"Struggle score: {s.struggle_score}/100")
        if s.error_count > 0:
            parts.append(f"Errors detected on screen: {s.error_count}")

        return " | ".join(parts) if parts else "No screen context available."

    def get_activity_summary(self, minutes: int = 5) -> str:
        """
        Summarise what the user has been doing in the last *minutes*.

        Returns a human-readable paragraph.
        """
        cutoff = time.time() - (minutes * 60)
        recent = [e for e in self.activity_log if e.timestamp >= cutoff]

        if not recent:
            return f"No activity recorded in the last {minutes} minutes."

        # Aggregate activities
        activity_counts: dict[str, int] = {}
        windows_seen: set[str] = set()
        error_entries = 0

        for entry in recent:
            activity_counts[entry.detected_activity] = (
                activity_counts.get(entry.detected_activity, 0) + 1
            )
            if entry.window_title:
                windows_seen.add(entry.window_title)
            if entry.error_detected:
                error_entries += 1

        # Build summary
        lines: List[str] = []
        lines.append(
            f"In the last {minutes} min: {len(recent)} screen samples captured."
        )

        top_activities = sorted(activity_counts.items(), key=lambda x: -x[1])
        activity_str = ", ".join(f"{act} ({cnt}x)" for act, cnt in top_activities[:4])
        lines.append(f"Activities: {activity_str}.")

        if windows_seen:
            lines.append(
                f"Windows used ({len(windows_seen)}): "
                + ", ".join(sorted(windows_seen)[:6])
            )

        if error_entries:
            lines.append(
                f"Errors appeared in {error_entries}/{len(recent)} samples."
            )

        with self._lock:
            score = self.state.struggle_score
        if score > 0:
            level = (
                "low" if score < 30
                else "moderate" if score < 60
                else "high"
            )
            lines.append(f"Struggle level: {level} ({score}/100).")

        return " ".join(lines)
