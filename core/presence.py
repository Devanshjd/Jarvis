"""
J.A.R.V.I.S — Presence Engine
Always-on background service with system tray, idle awareness,
and instant responsiveness.

Movie JARVIS is never "launched" — it's already there.
This engine creates that feeling.
"""

import os
import sys
import time
import json
import threading
import logging
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger("jarvis.presence")


class PresenceState(Enum):
    """JARVIS's current state of being."""
    BOOTING     = "booting"
    ACTIVE      = "active"       # User is actively interacting
    LISTENING   = "listening"    # Waiting, alert, ready
    WATCHING    = "watching"     # Monitoring in background
    SLEEPING    = "sleeping"     # Low-power mode (late night)


class PresenceEngine:
    """
    Makes JARVIS feel alive and present.

    Responsibilities:
    - Track user activity (last interaction, idle time)
    - System tray icon with quick actions
    - Time-of-day awareness (greetings, sleep mode)
    - Session continuity (remember what was happening)
    - Startup/shutdown rituals
    """

    def __init__(self, app):
        self.app = app
        self.config = app.config
        self.state = PresenceState.BOOTING
        self._last_interaction = time.time()
        self._last_message = ""
        self._idle_threshold = 300      # 5 min = idle
        self._sleep_threshold = 1800    # 30 min = sleep
        self._session_start = time.time()
        self._interaction_count = 0
        self._tray_icon = None
        self._tray_thread = None
        self._monitor_thread = None
        self._running = True

        # Time-of-day awareness
        self._greeted_today = False
        self._last_check_hour = -1

    def start(self):
        """Boot the presence engine."""
        self.state = PresenceState.LISTENING

        # Start idle monitor
        self._monitor_thread = threading.Thread(
            target=self._idle_monitor_loop,
            daemon=True, name="jarvis-presence",
        )
        self._monitor_thread.start()

        # Start system tray
        if self.config.get("presence", {}).get("enable_tray", False):
            print("[JARVIS] System tray enabled")
            self._start_tray()
        else:
            print("[JARVIS] System tray disabled")
            logger.info("System tray disabled by config")

        logger.info("Presence engine online")

    def stop(self):
        """Shutdown presence."""
        self._running = False
        self._destroy_tray()

    # ══════════════════════════════════════════════════════════
    # USER ACTIVITY TRACKING
    # ══════════════════════════════════════════════════════════

    def on_interaction(self, text: str = ""):
        """Called whenever the user interacts with JARVIS."""
        self._last_interaction = time.time()
        self._last_message = text
        self._interaction_count += 1

        was_sleeping = self.state == PresenceState.SLEEPING
        was_watching = self.state == PresenceState.WATCHING
        self.state = PresenceState.ACTIVE

        # Welcome back if was idle
        if was_sleeping:
            return self._welcome_back("sleeping")
        elif was_watching:
            return self._welcome_back("watching")
        return None

    @property
    def idle_seconds(self) -> float:
        return time.time() - self._last_interaction

    @property
    def is_idle(self) -> bool:
        return self.idle_seconds > self._idle_threshold

    @property
    def session_duration(self) -> float:
        return time.time() - self._session_start

    # ══════════════════════════════════════════════════════════
    # TIME-OF-DAY AWARENESS
    # ══════════════════════════════════════════════════════════

    def get_time_greeting(self) -> str:
        """Context-aware greeting based on time of day."""
        hour = datetime.now().hour

        if 5 <= hour < 12:
            return "Good morning, Dev."
        elif 12 <= hour < 17:
            return "Good afternoon, Dev."
        elif 17 <= hour < 21:
            return "Good evening, Dev."
        else:
            return "Burning the midnight oil, Dev?"

    def get_contextual_greeting(self) -> str:
        """Smart greeting that considers time, day, and session history."""
        hour = datetime.now().hour
        day = datetime.now().strftime("%A")
        greeting = self.get_time_greeting()

        # Add context
        additions = []

        # Weekend awareness
        if day in ("Saturday", "Sunday"):
            additions.append("Weekend mode — take it easy, sir.")

        # Late night concern
        if hour >= 23 or hour < 4:
            additions.append("It's getting late. Shall I dim the interface?")

        # Early morning
        if 5 <= hour < 7:
            additions.append("Early start today. I'll have everything ready.")

        # Check for pending tasks
        tasks = self.config.get("tasks", [])
        pending = [t for t in tasks if not t.get("done")]
        if pending:
            additions.append(f"You have {len(pending)} pending task{'s' if len(pending) > 1 else ''}.")

        if additions:
            return f"{greeting} {additions[0]}"
        return f"{greeting} All systems are online."

    def get_boot_greeting(self) -> str:
        """The first thing JARVIS says when starting up."""
        hour = datetime.now().hour

        # Check if this is a restart (session data exists)
        learned = self.config.get("learned", {})
        total_sessions = learned.get("total_sessions", 0)

        if total_sessions <= 1:
            # First ever boot
            return (
                "J.A.R.V.I.S is online. All systems nominal.\n\n"
                "I'm ready when you are, Dev. Just speak naturally — "
                "I understand intent, not commands."
            )

        greeting = self.get_time_greeting()

        # Build contextual additions
        parts = [greeting]

        # Pending tasks
        tasks = self.config.get("tasks", [])
        pending = [t for t in tasks if not t.get("done")]
        if pending:
            if len(pending) == 1:
                parts.append("You have 1 pending task.")
            else:
                parts.append(f"You have {len(pending)} pending tasks.")

        # Late night awareness
        if hour >= 23 or hour < 5:
            parts.append("Running in night mode.")

        parts.append("All systems are online.")

        return " ".join(parts)

    # ══════════════════════════════════════════════════════════
    # IDLE MONITORING
    # ══════════════════════════════════════════════════════════

    def _idle_monitor_loop(self):
        """Background loop that tracks idle state and transitions."""
        while self._running:
            try:
                self._check_state_transition()
                self._check_time_events()
            except Exception as e:
                logger.error("Presence monitor error: %s", e)
            time.sleep(10)  # Check every 10 seconds

    def _check_state_transition(self):
        """Transition between presence states based on idle time."""
        idle = self.idle_seconds

        if self.state == PresenceState.ACTIVE:
            if idle > self._idle_threshold:
                self.state = PresenceState.WATCHING
                logger.info("State: ACTIVE → WATCHING (idle %.0fs)", idle)
                self._notify_state_change("watching")

        elif self.state == PresenceState.WATCHING:
            if idle > self._sleep_threshold:
                self.state = PresenceState.SLEEPING
                logger.info("State: WATCHING → SLEEPING (idle %.0fs)", idle)
                self._notify_state_change("sleeping")

        elif self.state == PresenceState.LISTENING:
            if idle > self._idle_threshold:
                self.state = PresenceState.WATCHING

    def _check_time_events(self):
        """Check for time-based events (hourly, daily)."""
        hour = datetime.now().hour
        if hour == self._last_check_hour:
            return
        self._last_check_hour = hour

        # Reset daily greeting flag at 5 AM
        if hour == 5:
            self._greeted_today = False

    def _notify_state_change(self, new_state: str):
        """Notify UI of state change (update status indicators)."""
        try:
            if hasattr(self.app, 'root'):
                if new_state == "watching":
                    self.app.root.after(0, self._update_presence_ui, "watching")
                elif new_state == "sleeping":
                    self.app.root.after(0, self._update_presence_ui, "sleeping")
        except Exception:
            pass

    def _update_presence_ui(self, state: str):
        """Update UI elements to reflect presence state."""
        try:
            if state == "watching":
                if hasattr(self.app, 'subtitle'):
                    self.app.subtitle.config(text="Standing by...")
            elif state == "sleeping":
                if hasattr(self.app, 'subtitle'):
                    self.app.subtitle.config(text="Night watch mode")
            elif state == "active":
                if hasattr(self.app, 'subtitle'):
                    self.app.subtitle.config(text="At your service")
        except Exception:
            pass

    def _welcome_back(self, from_state: str) -> str:
        """Generate a welcome-back message after idle."""
        idle_mins = int(self.idle_seconds / 60)

        if from_state == "sleeping":
            return f"Welcome back, Dev. I've been on standby for {idle_mins} minutes."
        elif from_state == "watching":
            return "I'm here, sir."
        return None

    # ══════════════════════════════════════════════════════════
    # SYSTEM TRAY
    # ══════════════════════════════════════════════════════════

    def _start_tray(self):
        """Create system tray icon for background presence."""
        if not self.config.get("presence", {}).get("enable_tray", False):
            logger.info("Tray start skipped (disabled)")
            return
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            logger.info("System tray unavailable (pystray/PIL not installed)")
            return

        def _create_icon():
            # Create a simple arc reactor icon
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            # Outer ring
            draw.ellipse([4, 4, 60, 60], outline=(0, 212, 255, 255), width=3)
            # Inner ring
            draw.ellipse([16, 16, 48, 48], outline=(0, 153, 187, 200), width=2)
            # Core
            draw.ellipse([26, 26, 38, 38], fill=(0, 212, 255, 255))
            return img

        def _on_show(icon, item):
            self.app.root.after(0, self.app.root.deiconify)
            self.app.root.after(0, self.app.root.lift)

        def _on_quit(icon, item):
            icon.stop()
            self.app.root.after(0, self.app._on_close)

        def _on_scan(icon, item):
            self.app.root.after(0, self.app.scan_screen)

        def _on_voice(icon, item):
            self.app.root.after(0, self.app.toggle_listening)

        try:
            menu = pystray.Menu(
                pystray.MenuItem("Show JARVIS", _on_show, default=True),
                pystray.MenuItem("Voice Input", _on_voice),
                pystray.MenuItem("Scan Screen", _on_scan),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", _on_quit),
            )

            self._tray_icon = pystray.Icon(
                "JARVIS", _create_icon(), "J.A.R.V.I.S", menu,
            )

            self._tray_thread = threading.Thread(
                target=self._tray_icon.run,
                daemon=True, name="jarvis-tray",
            )
            self._tray_thread.start()
            logger.info("System tray active")
        except Exception as e:
            logger.error("Tray icon failed: %s", e)

    def _destroy_tray(self):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════
    # SESSION INFO
    # ══════════════════════════════════════════════════════════

    def get_session_summary(self) -> dict:
        """Current session stats."""
        elapsed = self.session_duration
        h, rem = divmod(int(elapsed), 3600)
        m, s = divmod(rem, 60)
        return {
            "state": self.state.value,
            "duration": f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}",
            "interactions": self._interaction_count,
            "idle_seconds": int(self.idle_seconds),
            "time_of_day": self.get_time_greeting(),
        }

    def get_status_text(self) -> str:
        """One-line status for UI."""
        state_labels = {
            PresenceState.BOOTING: "INITIALIZING",
            PresenceState.ACTIVE: "ACTIVE",
            PresenceState.LISTENING: "LISTENING",
            PresenceState.WATCHING: "STANDING BY",
            PresenceState.SLEEPING: "NIGHT WATCH",
        }
        return state_labels.get(self.state, "ONLINE")
