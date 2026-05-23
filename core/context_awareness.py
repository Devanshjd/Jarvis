"""
J.A.R.V.I.S — Context Awareness Module

Knows what window is currently focused, which apps are running, and can
bring a target window to the foreground before keyboard/mouse input.

The "Calculator typing into Claude Code" bug we caught happened because
JARVIS had no awareness that Claude Code was actually focused. This module
fixes that. Every agent step that types or clicks should first call:

    ctx = ContextAwareness()
    ok = ctx.ensure_focus("Calculator")
    if not ok:
        # Either bail out or report uncertainty — DON'T silently type
        # into the wrong window.

Uses Windows API (win32gui) — fast, no LLM calls, deterministic.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("jarvis.context")

try:
    import win32gui
    import win32process
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    logger.warning("pywin32 not available — context awareness disabled")


# ─── Heuristic mapping: app name → window title substrings ────────────────
# When the agent says "Calculator", we look for windows whose title contains
# any of these. Used both for focus-checking and for bringing apps forward.
_APP_TITLE_HINTS: dict[str, list[str]] = {
    "calculator": ["Calculator"],
    "calc":       ["Calculator"],
    "notepad":    ["Notepad", "- Notepad"],
    "wordpad":    ["WordPad"],
    "chrome":     ["Google Chrome", "Chrome"],
    "firefox":    ["Firefox", "Mozilla"],
    "edge":       ["Microsoft Edge", "Edge"],
    "explorer":   ["File Explorer", "Explorer", "This PC"],
    "file explorer": ["File Explorer", "Explorer", "This PC"],
    "paint":      ["Paint", "Untitled - Paint"],
    "spotify":    ["Spotify"],
    "vlc":        ["VLC", "VLC media player"],
    "vscode":     ["Visual Studio Code", "- Code"],
    "vs code":    ["Visual Studio Code", "- Code"],
    "code":       ["Visual Studio Code", "- Code"],
    "whatsapp":   ["WhatsApp"],
    "telegram":   ["Telegram"],
    "discord":    ["Discord"],
    "terminal":   ["Terminal", "Windows Terminal"],
    "powershell": ["PowerShell", "Windows PowerShell"],
    "cmd":        ["Command Prompt", "cmd.exe"],
    "task manager": ["Task Manager"],
    "settings":   ["Settings"],
    "outlook":    ["Outlook"],
    "word":       ["Word", "- Word"],
    "excel":      ["Excel", "- Excel"],
    "powerpoint": ["PowerPoint", "- PowerPoint"],
}


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    visible: bool
    foreground: bool

    def __repr__(self) -> str:
        return f"Window(title={self.title!r}, pid={self.pid}, fg={self.foreground})"


class ContextAwareness:
    """Tracks window state and brings apps to focus when needed."""

    def __init__(self):
        self.available = HAS_WIN32

    # ─── Read-only queries ────────────────────────────────────────────────

    def get_foreground_window(self) -> Optional[WindowInfo]:
        """Return the currently-focused window, or None if unavailable."""
        if not self.available:
            return None
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            return self._window_info(hwnd, foreground=True)
        except Exception as e:
            logger.warning("get_foreground_window failed: %s", e)
            return None

    def list_visible_windows(self) -> list[WindowInfo]:
        """Return all visible top-level windows."""
        if not self.available:
            return []
        results: list[WindowInfo] = []
        try:
            fg_hwnd = win32gui.GetForegroundWindow()

            def callback(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:  # Skip nameless windows
                        info = self._window_info(hwnd, foreground=(hwnd == fg_hwnd))
                        if info:
                            results.append(info)
                return True

            win32gui.EnumWindows(callback, None)
        except Exception as e:
            logger.warning("list_visible_windows failed: %s", e)
        return results

    def find_window(self, app_name: str) -> Optional[WindowInfo]:
        """Find the most likely window for the given app name.

        Resolves app_name through _APP_TITLE_HINTS to known title patterns,
        then searches visible windows for a match. Returns the first match
        (or the foreground one if multiple match).
        """
        if not self.available:
            return None
        normalized = (app_name or "").strip().lower()
        if not normalized:
            return None

        hints = _APP_TITLE_HINTS.get(normalized, [app_name])
        windows = self.list_visible_windows()

        # Score each window: substring match + prefer foreground
        scored: list[tuple[int, WindowInfo]] = []
        for w in windows:
            title_lower = w.title.lower()
            for hint in hints:
                if hint.lower() in title_lower:
                    score = 10
                    if w.foreground:
                        score += 5
                    if title_lower == hint.lower():
                        score += 3
                    scored.append((score, w))
                    break

        if not scored:
            return None
        scored.sort(key=lambda t: -t[0])
        return scored[0][1]

    def is_focused(self, app_name: str) -> bool:
        """Check if the named app is currently the foreground window."""
        fg = self.get_foreground_window()
        if not fg:
            return False
        normalized = (app_name or "").strip().lower()
        hints = _APP_TITLE_HINTS.get(normalized, [app_name])
        title_lower = fg.title.lower()
        return any(h.lower() in title_lower for h in hints)

    # ─── State-changing actions ───────────────────────────────────────────

    def bring_to_front(self, app_name: str, wait_ms: int = 400) -> bool:
        """Bring the named app's window to the foreground.

        Returns True if the window was found and successfully focused.
        Waits wait_ms after to let the focus change settle.
        """
        if not self.available:
            return False
        win = self.find_window(app_name)
        if not win:
            logger.info("bring_to_front: no window found for %r", app_name)
            return False
        try:
            # Restore if minimized
            try:
                placement = win32gui.GetWindowPlacement(win.hwnd)
                if placement and placement[1] == win32con.SW_SHOWMINIMIZED:
                    win32gui.ShowWindow(win.hwnd, win32con.SW_RESTORE)
            except Exception:
                pass

            # The Alt-key trick is required on Win10/11 because
            # SetForegroundWindow has to be called from a foreground thread.
            # Pressing-and-releasing Alt creates a brief synthetic foreground
            # context that lets SetForegroundWindow succeed.
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # Press Alt down then up (VK_MENU = 0x12)
                user32.keybd_event(0x12, 0, 0, 0)
                user32.keybd_event(0x12, 0, 0x0002, 0)
            except Exception:
                pass

            win32gui.SetForegroundWindow(win.hwnd)
            time.sleep(wait_ms / 1000.0)

            # Confirm it actually worked
            fg = win32gui.GetForegroundWindow()
            if fg == win.hwnd:
                logger.info("bring_to_front: focused %r (hwnd=%d)", win.title, win.hwnd)
                return True
            logger.warning(
                "bring_to_front: tried to focus %r but foreground is %r",
                win.title, win32gui.GetWindowText(fg) if fg else "(none)",
            )
            return False
        except Exception as e:
            logger.warning("bring_to_front error for %r: %s", app_name, e)
            return False

    def ensure_focus(self, app_name: str) -> bool:
        """Ensure the named app is focused. Idempotent.

        - If already focused → True (no-op)
        - If found but not focused → bring it forward
        - If not found at all → False (caller should open it first)
        """
        if self.is_focused(app_name):
            return True
        return self.bring_to_front(app_name)

    # ─── Internal helpers ─────────────────────────────────────────────────

    def _window_info(self, hwnd: int, foreground: bool = False) -> Optional[WindowInfo]:
        try:
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            visible = bool(win32gui.IsWindowVisible(hwnd))
            return WindowInfo(hwnd=hwnd, title=title, pid=pid, visible=visible, foreground=foreground)
        except Exception:
            return None


# Module-level singleton for convenience
_singleton: Optional[ContextAwareness] = None


def get_context() -> ContextAwareness:
    global _singleton
    if _singleton is None:
        _singleton = ContextAwareness()
    return _singleton
