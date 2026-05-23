"""
J.A.R.V.I.S — Precise Click

Clicks UI elements by description WITHOUT needing a fancy vision model.
Three tiers, tried in order:

  Tier 1: pywinauto control click — for Windows native/UWP apps that expose
          their UI tree (Calculator, Notepad, File Explorer, etc.)
          ~95% reliable when the element exists in the AutomationTree.

  Tier 2: OCR text click — Tesseract returns bounding boxes for every
          visible text region; we find the requested text and click its
          center. ~80% reliable for any element with a text label.

  Tier 3: (future) vision-LLM coordinate grounding — gemma3:4b returns
          pixel coords. ~50-60% reliable; only used when Tier 1+2 fail.

The agent's screen_click handler calls click_element(target) which tries
the tiers in order. Most "click Play / Save / Submit" requests succeed
on Tier 1 or 2 without ever needing a vision model.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("jarvis.precise_click")

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from pywinauto import Application, Desktop
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False


@dataclass
class ClickResult:
    success: bool
    method: str            # "pywinauto" / "ocr" / "vision" / "none"
    x: int = -1
    y: int = -1
    matched_text: str = ""
    error: str = ""


# ═══════════════════════════════════════════════════════════════════════
#  TIER 1 — pywinauto control click
# ═══════════════════════════════════════════════════════════════════════

def click_control_in_app(app_hint: str, label: str, button: str = "left") -> ClickResult:
    """Find a UI control in a specific app by label and click it.

    Uses pywinauto's AutomationTree — works on Windows native + UWP apps.
    `app_hint`: app name like "calculator", "notepad", "spotify"
    `label`:    button/control text like "Play", "Equals", "Save"
    """
    if not HAS_PYWINAUTO:
        return ClickResult(False, "none", error="pywinauto unavailable")

    candidates = [
        ("uia", {"title_re": f".*{re.escape(app_hint)}.*"}),
    ]
    if app_hint:
        candidates.append(("win32", {"title_re": f".*{re.escape(app_hint)}.*"}))

    for backend, kwargs in candidates:
        try:
            app = Application(backend=backend).connect(**kwargs, timeout=2)
            win = app.window(**kwargs)
            # Try several ways to locate the control
            for finder in (
                lambda: win.child_window(title=label, control_type="Button"),
                lambda: win.child_window(title_re=f"^{re.escape(label)}$"),
                lambda: win.child_window(title_re=f".*{re.escape(label)}.*"),
                lambda: win.descendants(control_type="Button"),  # fall through
            ):
                try:
                    elem = finder()
                    if isinstance(elem, list):
                        # When we got all descendants, filter by label
                        for e in elem:
                            try:
                                t = (e.window_text() or "").strip().lower()
                                if t == label.lower() or label.lower() in t:
                                    elem = e
                                    break
                            except Exception:
                                continue
                        else:
                            continue  # no descendant matched
                    if not elem:
                        continue
                    # Confirm it's visible/enabled
                    try:
                        rect = elem.rectangle()
                        if rect.width() <= 0 or rect.height() <= 0:
                            continue
                        elem.click_input(button=button)
                        cx, cy = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
                        logger.info("pywinauto clicked %r in %r at (%d,%d)", label, app_hint, cx, cy)
                        return ClickResult(True, f"pywinauto/{backend}",
                                           x=cx, y=cy, matched_text=label)
                    except Exception:
                        continue
                except Exception:
                    continue
        except Exception as e:
            logger.debug("pywinauto connect failed for %s/%s: %s", backend, app_hint, e)
            continue

    return ClickResult(False, "pywinauto", error=f"control {label!r} not found in {app_hint!r}")


# ═══════════════════════════════════════════════════════════════════════
#  TIER 2 — OCR text click
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TextHit:
    text: str
    x: int        # left
    y: int        # top
    w: int
    h: int
    confidence: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)


def find_text_on_screen(target: str, min_confidence: int = 40) -> list[TextHit]:
    """Find all occurrences of `target` text on the current screen.

    Uses Tesseract image_to_data which returns text + bbox + confidence
    for every recognized text region. Matches are case-insensitive and
    substring-tolerant (so "Play" matches a button labeled "Play Song").

    Returns hits sorted by confidence DESC.
    """
    if not (HAS_PYAUTOGUI and HAS_TESSERACT):
        return []

    target_lower = (target or "").strip().lower()
    if not target_lower:
        return []

    try:
        img = pyautogui.screenshot()
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception as e:
        logger.warning("OCR screenshot failed: %s", e)
        return []

    n = len(data["text"])
    # ── Strategy A: exact / substring match on single text regions ───────
    hits: list[TextHit] = []
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        try:
            conf = int(data["conf"][i])
        except Exception:
            conf = 0
        if conf < min_confidence:
            continue
        text_lower = text.lower()
        if target_lower == text_lower or target_lower in text_lower:
            hits.append(TextHit(
                text=text, x=int(data["left"][i]), y=int(data["top"][i]),
                w=int(data["width"][i]), h=int(data["height"][i]), confidence=conf,
            ))

    # ── Strategy B: multi-word target — join consecutive words on a line
    target_words = target_lower.split()
    if not hits and len(target_words) > 1:
        # Group by (block_num, par_num, line_num) to find words on same line
        from collections import defaultdict
        lines = defaultdict(list)
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines[key].append((i, text))

        for line_words in lines.values():
            # Get the concatenated lowercase text of this line
            joined = " ".join(t.lower() for _, t in line_words)
            if target_lower in joined:
                # Compute bounding box covering matching words
                # (find which words to include)
                start_idx = joined.find(target_lower)
                if start_idx < 0:
                    continue
                # Walk through words counting chars to find which words match
                matched_word_indices = []
                cursor = 0
                for word_pos, (i, t) in enumerate(line_words):
                    word_start = cursor
                    cursor += len(t) + 1  # +1 for space
                    word_end = cursor - 1
                    if word_end > start_idx and word_start <= start_idx + len(target_lower):
                        matched_word_indices.append(i)
                if not matched_word_indices:
                    continue
                xs = [int(data["left"][i]) for i in matched_word_indices]
                ys = [int(data["top"][i]) for i in matched_word_indices]
                rights = [int(data["left"][i]) + int(data["width"][i]) for i in matched_word_indices]
                bottoms = [int(data["top"][i]) + int(data["height"][i]) for i in matched_word_indices]
                confs = [int(data["conf"][i]) for i in matched_word_indices if int(data["conf"][i]) > 0]
                hits.append(TextHit(
                    text=" ".join(data["text"][i] for i in matched_word_indices),
                    x=min(xs), y=min(ys),
                    w=max(rights) - min(xs), h=max(bottoms) - min(ys),
                    confidence=int(sum(confs) / max(len(confs), 1)) if confs else 0,
                ))

    hits.sort(key=lambda h: -h.confidence)
    return hits


def click_text(target: str, button: str = "left", click_index: int = 0,
               double: bool = False) -> ClickResult:
    """Click on text matching `target` on the current screen.

    If multiple matches found, clicks the `click_index`-th one (0 = highest
    confidence). Returns ClickResult with success + matched text + coords.
    """
    if not HAS_PYAUTOGUI:
        return ClickResult(False, "none", error="pyautogui unavailable")

    hits = find_text_on_screen(target)
    if not hits:
        return ClickResult(False, "ocr", matched_text=target,
                           error=f"no text matching {target!r} found on screen")

    if click_index >= len(hits):
        return ClickResult(False, "ocr", matched_text=target,
                           error=f"asked for match #{click_index} but only {len(hits)} found")

    hit = hits[click_index]
    cx, cy = hit.center
    try:
        if double:
            pyautogui.doubleClick(cx, cy, button=button)
        else:
            pyautogui.click(cx, cy, button=button)
        time.sleep(0.15)
        logger.info("OCR clicked %r at (%d, %d) [conf=%d]", hit.text, cx, cy, hit.confidence)
        return ClickResult(True, "ocr", x=cx, y=cy, matched_text=hit.text)
    except Exception as e:
        return ClickResult(False, "ocr", x=cx, y=cy, matched_text=hit.text,
                           error=f"pyautogui click failed: {e}")


# ═══════════════════════════════════════════════════════════════════════
#  HYBRID — try all tiers in order
# ═══════════════════════════════════════════════════════════════════════

def click_element(
    target: str,
    app_hint: str = "",
    button: str = "left",
    double: bool = False,
) -> ClickResult:
    """Click a UI element by description, trying multiple methods in order.

    `target`:   what to click — button label, link text, icon caption
    `app_hint`: optional app name to scope pywinauto search
    `button`:   "left" / "right" / "middle"
    `double`:   True for double-click

    Tries (in order):
      1. pywinauto control click — only if app_hint given
      2. OCR text click — works for any visible text
      3. (future) vision-LLM coordinate grounding
    """
    target = (target or "").strip()
    if not target:
        return ClickResult(False, "none", error="empty target")

    # Tier 1: pywinauto (requires app hint)
    if app_hint:
        r = click_control_in_app(app_hint, target, button=button)
        if r.success:
            return r
        logger.debug("Tier 1 (pywinauto) miss for %r in %r — trying OCR", target, app_hint)

    # Tier 2: OCR text click
    r = click_text(target, button=button, double=double)
    if r.success:
        return r

    # Tier 3: future vision-LLM grounding would go here
    return ClickResult(False, "none",
                       error=f"all click methods failed for {target!r} (app_hint={app_hint!r})")
