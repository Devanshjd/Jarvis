"""
J.A.R.V.I.S — AI-Powered Screen Element Finder & Clicker

Uses vision-capable LLMs to find and interact with ANY element on screen.
Instead of fixed coordinates or CSS selectors, just describe what you want:
    "click the search bar", "click the play button", "type into the username field"

How it works:
    1. Take a screenshot
    2. Thumbnail it to 1280x720 (saves tokens)
    3. Send to vision LLM: "find element described as X"
    4. LLM returns pixel coordinates
    5. Scale coordinates back to actual screen size
    6. Execute the action (with permission)

Dependencies (gracefully degraded):
    - PIL / Pillow    → screenshot capture
    - pyautogui       → mouse/keyboard automation
"""

import io
import re
import json
import time
import base64
import logging
import threading
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger("jarvis.screen_interact")

# ── Optional imports ─────────────────────────────────────────

_HAS_PIL = False
_HAS_PYAUTOGUI = False

try:
    from PIL import ImageGrab, Image
    _HAS_PIL = True
except ImportError:
    logger.info("PIL not available — screenshot capture disabled")

try:
    import pyautogui
    pyautogui.FAILSAFE = True   # move mouse to corner to abort
    pyautogui.PAUSE = 0.1       # small pause between actions
    _HAS_PYAUTOGUI = True
except ImportError:
    logger.info("pyautogui not available — mouse/keyboard automation disabled")


# ── Constants ────────────────────────────────────────────────

THUMBNAIL_SIZE = (1280, 720)
LLM_TIMEOUT = 30               # seconds
ELEMENT_CACHE_TTL = 15          # seconds — how long cached locations stay valid
MAX_RETRIES = 1                 # retry once if LLM returns garbage

# UI element hints — extra context for the LLM on common patterns
ELEMENT_HINTS = {
    "search":       "Look for a text input field or search icon, usually near the top of the window.",
    "close":        "Look for an X button, usually in the top-right corner of a window or dialog.",
    "minimize":     "Look for a minus/dash button, usually in the top-right area near close.",
    "maximize":     "Look for a square/expand button, usually between minimize and close.",
    "play":         "Look for a triangle/play icon pointing right.",
    "pause":        "Look for two vertical bars (pause icon).",
    "stop":         "Look for a square stop icon.",
    "back":         "Look for a left-pointing arrow, usually top-left.",
    "forward":      "Look for a right-pointing arrow, usually near the back button.",
    "refresh":      "Look for a circular arrow icon, usually near the address bar.",
    "menu":         "Look for three horizontal lines (hamburger) or three dots, usually top-left or top-right.",
    "settings":     "Look for a gear/cog icon.",
    "submit":       "Look for a button labeled Submit, Send, Go, or OK.",
    "scroll":       "Look for a scrollbar on the right side.",
    "tab":          "Look at the tab bar, usually near the top of the window.",
    "address bar":  "Look for the URL input field at the top of the browser.",
    "notification": "Look for a bell icon, usually top-right area.",
}


# ── Prompts ──────────────────────────────────────────────────

FIND_ELEMENT_PROMPT = (
    "You are a screen element locator. The user wants to find: \"{description}\"\n\n"
    "{hint}\n"
    "Look at this screenshot and find the element. Return ONLY valid JSON:\n"
    "{{\"x\": <center_x_pixel>, \"y\": <center_y_pixel>}}\n\n"
    "If the element is not visible or doesn't exist, return:\n"
    "{{\"x\": -1, \"y\": -1}}\n\n"
    "IMPORTANT: Return raw coordinates matching the screenshot dimensions ({w}x{h}).\n"
    "No explanation, no markdown, just JSON."
)

FIND_ALL_PROMPT = (
    "You are a screen element locator. The user wants to find ALL elements matching: "
    "\"{description}\"\n\n"
    "Look at this screenshot and find every matching element. Return ONLY a JSON array:\n"
    "[{{\"x\": <center_x>, \"y\": <center_y>, \"label\": \"<brief label>\"}}, ...]\n\n"
    "If none found, return: []\n\n"
    "Coordinates must match the screenshot dimensions ({w}x{h}).\n"
    "No explanation, no markdown, just JSON array."
)

DESCRIBE_SCREEN_PROMPT = (
    "Describe everything visible on this screenshot in detail. Include:\n"
    "- What application or website is open\n"
    "- All visible text, labels, and buttons\n"
    "- The general layout (menus, sidebars, main content)\n"
    "- Any notifications, popups, or dialogs\n"
    "- What the user appears to be doing\n\n"
    "Be thorough but concise."
)

READ_ELEMENT_PROMPT = (
    "Look at this cropped screenshot region. Read and return ALL the text visible "
    "in this region, exactly as it appears. Preserve line breaks. Return only the "
    "text, nothing else."
)


# ── ScreenInteract ───────────────────────────────────────────

class ScreenInteract:
    """
    AI-powered screen element finder and clicker.

    Uses vision LLM to locate any element on screen by description,
    then performs mouse/keyboard actions at the found coordinates.
    """

    def __init__(self, jarvis):
        """
        Args:
            jarvis: Reference to the main JARVIS app for access to brain (LLM)
                    and config.
        """
        self.jarvis = jarvis
        self._lock = threading.Lock()

        # Cache: description -> {x, y, timestamp}
        self._cache: Dict[str, dict] = {}
        self._cache_lock = threading.Lock()

        logger.info(
            "ScreenInteract initialized — PIL=%s, pyautogui=%s",
            _HAS_PIL, _HAS_PYAUTOGUI,
        )

    # ─── Screenshot Capture ──────────────────────────────────

    def _capture_full(self) -> Optional["Image.Image"]:
        """Capture the full screen, return as PIL Image (or None)."""
        monitor = getattr(self.jarvis, "screen_monitor", None)
        if monitor:
            live = monitor.get_live_frame()
            if live and live.get("image") is not None:
                return live["image"]
            forced = monitor.capture_now(analyze=False)
            if forced and forced.get("image") is not None:
                return forced["image"]

        if not _HAS_PIL:
            logger.error("Cannot capture screen — PIL not installed")
            return None
        try:
            return ImageGrab.grab()
        except Exception as e:
            logger.error("Screenshot capture failed: %s", e)
            return None

    def _capture_region(self, x: int, y: int, width: int, height: int) -> Optional["Image.Image"]:
        """Capture a specific screen region."""
        monitor = getattr(self.jarvis, "screen_monitor", None)
        if monitor:
            live = monitor.get_live_frame()
            if live and live.get("image") is not None:
                img = live["image"]
                left = max(0, int(x))
                top = max(0, int(y))
                right = min(img.width, int(x + width))
                bottom = min(img.height, int(y + height))
                if right > left and bottom > top:
                    return img.crop((left, top, right, bottom))
        if not _HAS_PIL:
            return None
        try:
            bbox = (x, y, x + width, y + height)
            return ImageGrab.grab(bbox=bbox)
        except Exception as e:
            logger.error("Region capture failed: %s", e)
            return None

    def _to_thumbnail(self, img: "Image.Image") -> Tuple["Image.Image", Tuple[int, int]]:
        """
        Resize image to THUMBNAIL_SIZE for the LLM.

        Returns:
            (thumbnail, original_size) — original size needed for coordinate scaling.
        """
        original_size = img.size  # (width, height)
        thumb = img.copy()
        thumb.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
        return thumb, original_size

    def _image_to_b64(self, img: "Image.Image") -> str:
        """Convert PIL Image to base64 PNG string (in-memory, never saved to disk)."""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    # ─── Coordinate Scaling ──────────────────────────────────

    def _scale_coords(
        self, llm_x: int, llm_y: int,
        thumb_size: Tuple[int, int], original_size: Tuple[int, int]
    ) -> Tuple[int, int]:
        """
        Scale coordinates from thumbnail space back to actual screen space.

        The LLM sees a 1280x720 (or smaller) thumbnail, but the actual screen
        might be 1920x1080, 2560x1440, etc.
        """
        tw, th = thumb_size
        ow, oh = original_size

        if tw == 0 or th == 0:
            return llm_x, llm_y

        actual_x = int(llm_x * ow / tw)
        actual_y = int(llm_y * oh / th)
        return actual_x, actual_y

    def _describe_location(self, x: int, y: int) -> str:
        """Convert pixel coordinates to a human-readable screen location."""
        if not _HAS_PYAUTOGUI:
            return f"({x}, {y})"

        sw, sh = pyautogui.size()
        rel_x = x / sw
        rel_y = y / sh

        # Vertical zone
        if rel_y < 0.2:
            v = "top"
        elif rel_y > 0.8:
            v = "bottom"
        else:
            v = "middle"

        # Horizontal zone
        if rel_x < 0.25:
            h = "left"
        elif rel_x > 0.75:
            h = "right"
        else:
            h = "center"

        if v == "middle" and h == "center":
            return f"center of screen ({x}, {y})"
        return f"{v}-{h} area ({x}, {y})"

    # ─── Element Hint Matching ───────────────────────────────

    def _get_hint(self, description: str) -> str:
        """If the description matches a common UI pattern, return extra context."""
        desc_lower = description.lower()
        for keyword, hint in ELEMENT_HINTS.items():
            if keyword in desc_lower:
                return hint
        return ""

    # ─── Cache ───────────────────────────────────────────────

    def _cache_get(self, description: str) -> Optional[dict]:
        """Retrieve a cached element location if still fresh."""
        with self._cache_lock:
            entry = self._cache.get(description.lower())
            if entry and (time.time() - entry["timestamp"]) < ELEMENT_CACHE_TTL:
                logger.debug("Cache hit for '%s'", description)
                return {"x": entry["x"], "y": entry["y"]}
            return None

    def _cache_put(self, description: str, x: int, y: int):
        """Store an element location in the cache."""
        with self._cache_lock:
            self._cache[description.lower()] = {
                "x": x, "y": y,
                "timestamp": time.time(),
            }

    # ─── LLM Communication ───────────────────────────────────

    def _ask_vision_llm(self, image_b64: str, prompt: str) -> Optional[str]:
        """
        Send image + prompt to the vision LLM and return the response text.

        Uses the brain's chat_with_image method. Blocks until response arrives
        or timeout is reached.
        """
        result = {"reply": None, "error": None}
        event = threading.Event()

        def on_reply(reply, latency):
            result["reply"] = reply
            event.set()

        def on_error(error_msg):
            result["error"] = error_msg
            event.set()

        try:
            self.jarvis.brain.chat_with_image(
                system_prompt="You are a precise screen element locator. Return only what is asked.",
                image_b64=image_b64,
                prompt_text=prompt,
                callback=on_reply,
                error_callback=on_error,
            )
        except Exception as e:
            logger.error("Failed to call vision LLM: %s", e)
            return None

        event.wait(timeout=LLM_TIMEOUT)

        if result["error"]:
            logger.error("Vision LLM error: %s", result["error"])
            return None
        if result["reply"] is None:
            logger.error("Vision LLM timed out after %ds", LLM_TIMEOUT)
            return None

        return result["reply"]

    def _parse_coordinates(self, response: str) -> Optional[Tuple[int, int]]:
        """
        Extract x, y coordinates from LLM response.

        Handles various formats:
            - Raw JSON: {"x": 123, "y": 456}
            - Markdown code blocks: ```json{"x": 123, "y": 456}```
            - Extra text around the JSON
        """
        if not response:
            return None

        # Try to find JSON object in the response
        patterns = [
            r'\{\s*"x"\s*:\s*(-?\d+)\s*,\s*"y"\s*:\s*(-?\d+)\s*\}',
            r'\{\s*"X"\s*:\s*(-?\d+)\s*,\s*"Y"\s*:\s*(-?\d+)\s*\}',
            r'"x"\s*:\s*(-?\d+).*?"y"\s*:\s*(-?\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
            if match:
                x = int(match.group(1))
                y = int(match.group(2))
                return (x, y)

        logger.warning("Could not parse coordinates from LLM response: %s", response[:200])
        return None

    def _parse_coordinate_list(self, response: str) -> List[dict]:
        """Extract a list of coordinate objects from LLM response."""
        if not response:
            return []

        # Strip markdown code blocks
        cleaned = re.sub(r"```(?:json)?\s*", "", response)
        cleaned = cleaned.strip().rstrip("`")

        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                results = []
                for item in data:
                    if isinstance(item, dict) and "x" in item and "y" in item:
                        results.append({
                            "x": int(item["x"]),
                            "y": int(item["y"]),
                            "label": item.get("label", ""),
                        })
                return results
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: find all coordinate pairs
        pairs = re.findall(
            r'\{\s*"x"\s*:\s*(-?\d+)\s*,\s*"y"\s*:\s*(-?\d+)(?:\s*,\s*"label"\s*:\s*"([^"]*)")?\s*\}',
            response, re.IGNORECASE,
        )
        return [{"x": int(x), "y": int(y), "label": lbl} for x, y, lbl in pairs]

    # ─── Permission System ───────────────────────────────────

    def _ask_permission(self, description: str, x: int, y: int, action: str) -> bool:
        """
        Ask the user for permission before performing a screen action.
        Uses tkinter messagebox — blocks until user responds.

        This is NON-NEGOTIABLE. Never perform actions without permission.
        """
        try:
            import tkinter.messagebox as mb

            location = self._describe_location(x, y)
            message = (
                f"JARVIS found: \"{description}\"\n"
                f"Location: {location}\n"
                f"Action: {action}\n\n"
                f"Allow this action?"
            )

            return mb.askyesno("JARVIS — Screen Action Permission", message)

        except Exception as e:
            logger.error("Permission dialog failed: %s", e)
            return False

    # ─── Core: Find Element ──────────────────────────────────

    def find_element(self, description: str, use_cache: bool = True) -> dict:
        """
        Find a screen element by natural language description.

        Takes a screenshot, sends it to the vision LLM, and returns
        the element's pixel coordinates.

        Args:
            description: What to find, e.g. "the search bar", "play button"
            use_cache: Whether to check the cache first

        Returns:
            {found: bool, x: int, y: int, confidence: float, description: str}
        """
        # Check cache first
        if use_cache:
            cached = self._cache_get(description)
            if cached:
                return {
                    "found": True,
                    "x": cached["x"],
                    "y": cached["y"],
                    "confidence": 0.8,  # slightly lower confidence for cached
                    "description": description,
                    "cached": True,
                }

        # Capture screen
        screenshot = self._capture_full()
        if screenshot is None:
            return {
                "found": False, "x": -1, "y": -1,
                "confidence": 0.0, "description": description,
                "error": "Could not capture screenshot — PIL not available",
            }

        # Thumbnail for LLM
        thumb, original_size = self._to_thumbnail(screenshot)
        thumb_size = thumb.size
        image_b64 = self._image_to_b64(thumb)

        # Build prompt with hints
        hint = self._get_hint(description)
        prompt = FIND_ELEMENT_PROMPT.format(
            description=description,
            hint=hint,
            w=thumb_size[0],
            h=thumb_size[1],
        )

        # Ask LLM
        for attempt in range(1 + MAX_RETRIES):
            response = self._ask_vision_llm(image_b64, prompt)
            coords = self._parse_coordinates(response)

            if coords is not None:
                llm_x, llm_y = coords

                # Element not found
                if llm_x == -1 and llm_y == -1:
                    logger.info("Element not found: '%s'", description)
                    return {
                        "found": False, "x": -1, "y": -1,
                        "confidence": 0.0, "description": description,
                        "error": "Element not visible on screen",
                    }

                # Scale to actual screen coordinates
                actual_x, actual_y = self._scale_coords(
                    llm_x, llm_y, thumb_size, original_size
                )

                logger.info(
                    "Found '%s' at (%d, %d) — LLM coords (%d, %d), "
                    "thumb %s, screen %s",
                    description, actual_x, actual_y,
                    llm_x, llm_y, thumb_size, original_size,
                )

                # Cache the result
                self._cache_put(description, actual_x, actual_y)

                return {
                    "found": True,
                    "x": actual_x,
                    "y": actual_y,
                    "confidence": 0.9,
                    "description": description,
                }

            # Retry with clearer prompt
            if attempt < MAX_RETRIES:
                logger.warning(
                    "Attempt %d: Could not parse LLM response for '%s', retrying",
                    attempt + 1, description,
                )
                prompt = (
                    f"Find the UI element: \"{description}\"\n"
                    f"Return ONLY this exact JSON format, nothing else:\n"
                    f"{{\"x\": NUMBER, \"y\": NUMBER}}\n"
                    f"Use -1 for both if not found. Screenshot is {thumb_size[0]}x{thumb_size[1]}."
                )

        return {
            "found": False, "x": -1, "y": -1,
            "confidence": 0.0, "description": description,
            "error": "LLM returned unparseable response",
        }

    # ─── Actions ─────────────────────────────────────────────

    def click_element(self, description: str, button: str = "left") -> dict:
        """
        Find a screen element and click it (with user permission).

        Args:
            description: What to click, e.g. "the Start button"
            button: "left", "right", or "middle"

        Returns:
            dict with result info
        """
        if not _HAS_PYAUTOGUI:
            return {"success": False, "error": "pyautogui not installed — run: pip install pyautogui"}

        result = self.find_element(description)
        if not result["found"]:
            return {"success": False, **result}

        x, y = result["x"], result["y"]

        if not self._ask_permission(description, x, y, f"{button}-click"):
            logger.info("User denied click on '%s'", description)
            return {"success": False, "error": "Action denied by user", **result}

        try:
            pyautogui.click(x, y, button=button)
            logger.info("Clicked '%s' at (%d, %d) with %s button", description, x, y, button)
            return {"success": True, "action": f"{button}-click", **result}
        except Exception as e:
            logger.error("Click failed: %s", e)
            return {"success": False, "error": str(e), **result}

    def double_click_element(self, description: str) -> dict:
        """Find a screen element and double-click it (with permission)."""
        if not _HAS_PYAUTOGUI:
            return {"success": False, "error": "pyautogui not installed — run: pip install pyautogui"}

        result = self.find_element(description)
        if not result["found"]:
            return {"success": False, **result}

        x, y = result["x"], result["y"]

        if not self._ask_permission(description, x, y, "double-click"):
            return {"success": False, "error": "Action denied by user", **result}

        try:
            pyautogui.doubleClick(x, y)
            logger.info("Double-clicked '%s' at (%d, %d)", description, x, y)
            return {"success": True, "action": "double-click", **result}
        except Exception as e:
            logger.error("Double-click failed: %s", e)
            return {"success": False, "error": str(e), **result}

    def right_click_element(self, description: str) -> dict:
        """Find a screen element and right-click it (with permission)."""
        return self.click_element(description, button="right")

    def type_into_element(self, description: str, text: str) -> dict:
        """
        Find a text field, click it, then type text into it (with permission).

        Args:
            description: What field to type into, e.g. "the search bar"
            text: Text to type
        """
        if not _HAS_PYAUTOGUI:
            return {"success": False, "error": "pyautogui not installed — run: pip install pyautogui"}

        result = self.find_element(description)
        if not result["found"]:
            return {"success": False, **result}

        x, y = result["x"], result["y"]
        preview = text[:50] + ("..." if len(text) > 50 else "")

        if not self._ask_permission(description, x, y, f"click + type: \"{preview}\""):
            return {"success": False, "error": "Action denied by user", **result}

        try:
            pyautogui.click(x, y)
            time.sleep(0.2)  # brief pause to let the field focus
            pyautogui.typewrite(text, interval=0.02) if text.isascii() else pyautogui.write(text)
            logger.info("Typed into '%s' at (%d, %d): %s", description, x, y, preview)
            return {"success": True, "action": "type", "typed": text, **result}
        except Exception as e:
            logger.error("Type failed: %s", e)
            return {"success": False, "error": str(e), **result}

    def drag_element(self, from_desc: str, to_desc: str) -> dict:
        """
        Find two elements and drag from one to the other (with permission).

        Args:
            from_desc: Element to drag from
            to_desc: Element to drag to
        """
        if not _HAS_PYAUTOGUI:
            return {"success": False, "error": "pyautogui not installed — run: pip install pyautogui"}

        from_result = self.find_element(from_desc)
        if not from_result["found"]:
            return {"success": False, "error": f"Could not find source: {from_desc}", **from_result}

        to_result = self.find_element(to_desc)
        if not to_result["found"]:
            return {"success": False, "error": f"Could not find target: {to_desc}", **to_result}

        fx, fy = from_result["x"], from_result["y"]
        tx, ty = to_result["x"], to_result["y"]

        message = (
            f"Drag from: \"{from_desc}\" at ({fx}, {fy})\n"
            f"Drag to: \"{to_desc}\" at ({tx}, {ty})"
        )

        if not self._ask_permission(message, fx, fy, "drag"):
            return {"success": False, "error": "Action denied by user"}

        try:
            pyautogui.moveTo(fx, fy)
            time.sleep(0.1)
            pyautogui.mouseDown()
            time.sleep(0.1)
            pyautogui.moveTo(tx, ty, duration=0.5)
            pyautogui.mouseUp()
            logger.info("Dragged from (%d,%d) to (%d,%d)", fx, fy, tx, ty)
            return {
                "success": True, "action": "drag",
                "from": {"x": fx, "y": fy, "description": from_desc},
                "to": {"x": tx, "y": ty, "description": to_desc},
            }
        except Exception as e:
            logger.error("Drag failed: %s", e)
            return {"success": False, "error": str(e)}

    def read_element(self, description: str) -> str:
        """
        Find an element on screen and OCR just that region using the vision LLM.

        Args:
            description: What area to read, e.g. "the error message", "the title bar"

        Returns:
            Extracted text, or error message.
        """
        result = self.find_element(description)
        if not result["found"]:
            return f"[Could not find element: {description}]"

        x, y = result["x"], result["y"]

        # Capture a generous region around the found coordinates
        region_w, region_h = 400, 200
        rx = max(0, x - region_w // 2)
        ry = max(0, y - region_h // 2)

        region_img = self._capture_region(rx, ry, region_w, region_h)
        if region_img is None:
            return "[Could not capture screen region]"

        image_b64 = self._image_to_b64(region_img)
        response = self._ask_vision_llm(image_b64, READ_ELEMENT_PROMPT)

        if response:
            return response.strip()
        return "[Could not read element text]"

    # ─── Wait / Polling ──────────────────────────────────────

    def wait_for_element(self, description: str, timeout: int = 10) -> dict:
        """
        Repeatedly try to find an element until it appears or timeout is reached.

        Args:
            description: What to wait for
            timeout: Max seconds to wait

        Returns:
            Same as find_element, with added 'waited' field.
        """
        start = time.time()
        attempts = 0

        while (time.time() - start) < timeout:
            attempts += 1
            result = self.find_element(description, use_cache=False)
            if result["found"]:
                result["waited"] = round(time.time() - start, 1)
                result["attempts"] = attempts
                return result
            time.sleep(1.0)

        return {
            "found": False, "x": -1, "y": -1,
            "confidence": 0.0, "description": description,
            "error": f"Element not found after {timeout}s ({attempts} attempts)",
            "waited": round(time.time() - start, 1),
            "attempts": attempts,
        }

    # ─── Screen Description ──────────────────────────────────

    def get_screen_text(self) -> str:
        """
        Take a screenshot and ask the LLM to describe everything visible.

        Returns:
            Full text description of the screen contents.
        """
        screenshot = self._capture_full()
        if screenshot is None:
            return "[Could not capture screenshot]"

        thumb, _ = self._to_thumbnail(screenshot)
        image_b64 = self._image_to_b64(thumb)

        response = self._ask_vision_llm(image_b64, DESCRIBE_SCREEN_PROMPT)
        if response:
            return response.strip()
        return "[Could not describe screen]"

    def find_all_elements(self, description: str) -> List[dict]:
        """
        Find ALL elements matching a description (e.g., "all buttons", "all links").

        Returns:
            List of {found: bool, x: int, y: int, label: str} dicts,
            with coordinates scaled to actual screen size.
        """
        screenshot = self._capture_full()
        if screenshot is None:
            return []

        thumb, original_size = self._to_thumbnail(screenshot)
        thumb_size = thumb.size
        image_b64 = self._image_to_b64(thumb)

        prompt = FIND_ALL_PROMPT.format(
            description=description,
            w=thumb_size[0],
            h=thumb_size[1],
        )

        response = self._ask_vision_llm(image_b64, prompt)
        raw_items = self._parse_coordinate_list(response)

        # Scale all coordinates
        results = []
        for item in raw_items:
            if item["x"] == -1 and item["y"] == -1:
                continue
            ax, ay = self._scale_coords(item["x"], item["y"], thumb_size, original_size)
            results.append({
                "found": True,
                "x": ax,
                "y": ay,
                "label": item.get("label", ""),
                "description": description,
            })

        logger.info("Found %d elements matching '%s'", len(results), description)
        return results
