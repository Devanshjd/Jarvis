"""
J.A.R.V.I.S — Proactive Engine
Event-driven intelligence that notices, warns, suggests, and assists
BEFORE being asked.

Movie JARVIS doesn't wait. It notices.
"Sir, I'm detecting unusual network activity."
"That URL appears suspicious."
"You have a meeting in 15 minutes."

This engine makes that happen.
"""

import time
import re
import threading
import logging
from datetime import datetime
from typing import Optional, Callable
from collections import deque

logger = logging.getLogger("jarvis.proactive")


class ProactiveEngine:
    """
    Monitors awareness events and generates intelligent,
    contextual interventions.

    Rules:
    1. Never interrupt unless genuinely useful
    2. Cooldown between notifications (no spam)
    3. Severity-based filtering (user can adjust sensitivity)
    4. Learn what the user dismisses (reduce those)
    5. Short, sharp messages — movie JARVIS style
    """

    def __init__(self, app):
        self.app = app
        self._running = False
        self._notification_queue: deque[dict] = deque(maxlen=50)
        self._cooldown = {}        # event_type → last_notified timestamp
        self._cooldown_seconds = {
            "window_change": 0,      # Never notify (too frequent)
            "clipboard_url": 60,     # Max once per minute
            "clipboard_code": 120,   # Max once per 2 min
            "clipboard_error": 30,   # Errors are important
            "suspicious_url": 0,     # Always notify immediately
            "high_cpu": 300,         # Max once per 5 min
            "high_ram": 300,
            "low_battery": 600,      # Max once per 10 min
            "disk_full": 3600,       # Max once per hour
            "security_suggestion": 600,
            "work_suggestion": 1800,
            "break_reminder": 3600,
        }
        self._dismissed_types = set()  # Event types user has dismissed

        # Proactive suggestion state
        self._last_break_reminder = 0
        self._continuous_work_minutes = 0
        self._last_activity_check = time.time()

        # Callback for notifications
        self._notify_callback: Optional[Callable] = None

    def start(self, awareness_engine):
        """Start the proactive engine, listening to awareness events."""
        self._running = True
        self._awareness = awareness_engine

        # Register as event handler
        awareness_engine.on_event(self._on_awareness_event)

        # Start proactive suggestion loop
        threading.Thread(
            target=self._suggestion_loop,
            daemon=True, name="jarvis-proactive",
        ).start()

        logger.info("Proactive engine online")

    def stop(self):
        self._running = False

    def set_notify_callback(self, callback: Callable):
        """Set the callback for delivering notifications to UI."""
        self._notify_callback = callback

    # ══════════════════════════════════════════════════════════
    # EVENT HANDLING
    # ══════════════════════════════════════════════════════════

    def _on_awareness_event(self, event):
        """Process an awareness event and decide whether to notify."""
        etype = event.event_type

        # Skip silenced event types
        if etype in self._dismissed_types:
            return

        # Skip info-only events (they're logged, not notified)
        if event.severity == "info" and etype not in (
            "clipboard_error", "clipboard_code",
        ):
            return

        # Cooldown check
        if not self._can_notify(etype):
            return

        # Intelligence-based suppression (user dismissed this type too many times)
        intel = getattr(self.app, "intelligence", None)
        if intel and intel.feedback.should_suppress_notification(etype):
            return

        # Generate notification
        notification = self._generate_notification(event)
        if notification:
            self._deliver(notification)
            self._cooldown[etype] = time.time()

    def _can_notify(self, event_type: str) -> bool:
        """Check if we're past the cooldown for this event type."""
        cooldown = self._cooldown_seconds.get(event_type, 60)
        if cooldown == 0 and event_type == "window_change":
            return False  # Never notify window changes
        last = self._cooldown.get(event_type, 0)
        return (time.time() - last) > cooldown

    def _generate_notification(self, event) -> Optional[dict]:
        """Turn an awareness event into a JARVIS-style notification."""
        etype = event.event_type

        # ── Security alerts ──────────────────────────────
        if etype == "suspicious_url":
            url = event.data.get("url", "")[:60]
            return {
                "type": "alert",
                "icon": "🛡️",
                "message": f"That link looks suspicious, sir. {url}",
                "action": "scan",
                "data": event.data,
            }

        # ── System health ────────────────────────────────
        if etype == "high_cpu":
            cpu = event.data.get("cpu_percent", 0)
            return {
                "type": "warning",
                "icon": "⚡",
                "message": f"CPU at {cpu:.0f}%. Something's working hard.",
            }

        if etype == "high_ram":
            ram = event.data.get("ram_percent", 0)
            return {
                "type": "warning",
                "icon": "💾",
                "message": f"Memory at {ram:.0f}%. Consider closing some apps.",
            }

        if etype == "low_battery":
            bat = event.data.get("battery_percent", 0)
            return {
                "type": "alert",
                "icon": "🔋",
                "message": f"Battery at {bat:.0f}%. Plug in, sir.",
            }

        if etype == "disk_full":
            return {
                "type": "warning",
                "icon": "💿",
                "message": "Running low on disk space.",
            }

        # ── Helpful context ──────────────────────────────
        if etype == "clipboard_error":
            preview = event.data.get("error_preview", "")[:100]
            return {
                "type": "suggestion",
                "icon": "🔍",
                "message": "I noticed an error in your clipboard. Want me to look at it?",
                "data": event.data,
            }

        if etype == "clipboard_code":
            return {
                "type": "info",
                "icon": "📋",
                "message": "Code copied. Want me to explain or run it?",
                "data": event.data,
            }

        return None

    # ══════════════════════════════════════════════════════════
    # PROACTIVE SUGGESTIONS
    # ══════════════════════════════════════════════════════════

    def _suggestion_loop(self):
        """Background loop for time-based proactive suggestions."""
        while self._running:
            try:
                self._check_break_reminder()
                self._check_context_suggestions()
            except Exception as e:
                logger.error("Suggestion loop error: %s", e)
            time.sleep(60)  # Check every minute

    def _check_break_reminder(self):
        """Suggest breaks after long continuous work."""
        if not hasattr(self, '_awareness'):
            return

        presence = getattr(self.app, 'presence', None)
        if not presence:
            return

        # Only remind if actively using JARVIS
        if presence.idle_seconds > 300:
            self._continuous_work_minutes = 0
            return

        self._continuous_work_minutes += 1

        # Remind after 90 minutes of continuous work
        if self._continuous_work_minutes >= 90:
            if self._can_notify("break_reminder"):
                self._deliver({
                    "type": "suggestion",
                    "icon": "☕",
                    "message": "You've been at it for 90 minutes. Quick break?",
                })
                self._cooldown["break_reminder"] = time.time()
                self._continuous_work_minutes = 0

    def _check_context_suggestions(self):
        """Context-aware suggestions based on what the user is doing."""
        if not hasattr(self, '_awareness'):
            return

        win = self._awareness.active_window
        if not win.title:
            return

        category = win.app_category
        hour = datetime.now().hour

        # Late night coding warning
        if category == "coding" and (hour >= 23 or hour < 4):
            if self._can_notify("work_suggestion"):
                self._deliver({
                    "type": "suggestion",
                    "icon": "🌙",
                    "message": "Late night coding session. Don't forget to rest, sir.",
                })
                self._cooldown["work_suggestion"] = time.time()

        # Security tool awareness
        if category == "security":
            if self._can_notify("security_suggestion"):
                self._deliver({
                    "type": "info",
                    "icon": "🛡️",
                    "message": "Security tools detected. Cyber mode available — say 'enter cyber mode'.",
                })
                self._cooldown["security_suggestion"] = time.time()

    # ══════════════════════════════════════════════════════════
    # NOTIFICATION DELIVERY
    # ══════════════════════════════════════════════════════════

    def _deliver(self, notification: dict):
        """Deliver notification to UI."""
        self._notification_queue.append(notification)

        if self._notify_callback:
            try:
                self._notify_callback(notification)
            except Exception as e:
                logger.error("Notification delivery failed: %s", e)

    def dismiss_type(self, event_type: str):
        """User dismissed this type — stop showing it."""
        self._dismissed_types.add(event_type)

    def get_pending(self) -> list[dict]:
        """Get pending notifications."""
        return list(self._notification_queue)

    def clear_pending(self):
        self._notification_queue.clear()
