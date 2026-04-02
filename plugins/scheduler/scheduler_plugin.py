"""
J.A.R.V.I.S — Scheduler Plugin
Reminders, timers, alarms, and recurring tasks.

Commands:
    /remind <time> <message>   — Set a reminder (e.g., "/remind 5m drink water")
    /timer <duration>          — Set a countdown timer (e.g., "/timer 10m")
    /alarm <time>              — Set an alarm for a specific time (e.g., "/alarm 07:00")
    /reminders                 — List all active reminders
    /cancelreminder <id>       — Cancel a reminder by ID
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta

from core.plugin_manager import PluginBase

# Config file path (next to the plugin)
CONFIG_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_FILE = os.path.join(CONFIG_DIR, "reminders.json")


def _beep():
    """Play a notification sound (Windows beep fallback)."""
    try:
        import winsound
        # Three short beeps for attention
        for _ in range(3):
            winsound.Beep(1000, 300)
            time.sleep(0.15)
    except Exception:
        pass  # Non-Windows or no sound device


def _parse_relative_duration(text: str) -> int | None:
    """
    Parse a relative duration string into total seconds.
    Supports: "30s", "5m", "2h", "1h30m", "1h30m15s", etc.
    Returns None if the string doesn't match.
    """
    text = text.strip().lower()
    pattern = r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"
    match = re.match(pattern, text)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    total = hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def _parse_absolute_time(text: str) -> datetime | None:
    """
    Parse an absolute time string into a datetime (today or tomorrow).
    Supports: "14:30", "2:30pm", "2:30 PM", "07:00", "9am", etc.
    """
    text = text.strip().lower().replace(" ", "")
    now = datetime.now()

    # Try 24-hour format: "14:30", "07:00"
    match = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

    # Try 12-hour format: "2:30pm", "9am", "12:00am"
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?(am|pm)$", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3)
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

    return None


def _parse_recurring(text: str) -> tuple[str | None, int | str | None]:
    """
    Parse recurring pattern from text.
    Returns (recur_type, recur_value) or (None, None).
      recur_type: "interval" or "daily"
      recur_value: seconds (int) for interval, "HH:MM" (str) for daily
    """
    text = text.strip().lower()

    # "every 30m", "every 2h", "every 1h30m"
    match = re.match(r"^every\s+(\d+[hms](?:\d+[ms])?)$", text)
    if match:
        secs = _parse_relative_duration(match.group(1))
        if secs:
            return ("interval", secs)

    # "every day at 9am", "every day at 14:30"
    match = re.match(r"^every\s+day\s+at\s+(.+)$", text)
    if match:
        dt = _parse_absolute_time(match.group(1))
        if dt:
            time_str = dt.strftime("%H:%M")
            return ("daily", time_str)

    return (None, None)


def _format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m{s}s" if s else f"{m}m"
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    parts = [f"{h}h"]
    if m:
        parts.append(f"{m}m")
    if s:
        parts.append(f"{s}s")
    return "".join(parts)


class SchedulerPlugin(PluginBase):
    name = "scheduler"
    description = "Reminders, timers, alarms, and recurring tasks"
    version = "1.0"

    def activate(self):
        self._next_id = 1
        self._reminders = []  # list of reminder dicts
        self._running = True
        self._lock = threading.Lock()

        # Load persisted reminders
        self._load_config()

        # Start background checker thread
        self._thread = threading.Thread(target=self._checker_loop, daemon=True)
        self._thread.start()

    def deactivate(self):
        self._running = False

    # ══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ══════════════════════════════════════════════════════════════

    def _load_config(self):
        """Load reminders from JSON file."""
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._reminders = data.get("reminders", [])
            self._next_id = data.get("next_id", 1)
            # Remove any reminders that have already expired (non-recurring)
            now_ts = time.time()
            self._reminders = [
                r for r in self._reminders
                if r.get("fire_at", 0) > now_ts or r.get("recur_type")
            ]
            # Reschedule daily recurring reminders whose fire_at has passed
            for r in self._reminders:
                if r.get("recur_type") == "daily" and r.get("fire_at", 0) <= now_ts:
                    dt = _parse_absolute_time(r["recur_value"])
                    if dt:
                        r["fire_at"] = dt.timestamp()
        except Exception:
            self._reminders = []

    def _save_config(self):
        """Persist reminders to JSON file."""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            data = {
                "next_id": self._next_id,
                "reminders": self._reminders,
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════
    # BACKGROUND CHECKER
    # ══════════════════════════════════════════════════════════════

    def _checker_loop(self):
        """Background loop — checks every 30 seconds for fired reminders."""
        while self._running:
            time.sleep(30)
            if not self._running:
                break
            self._check_reminders()

    def _check_reminders(self):
        """Fire any reminders whose time has come."""
        now_ts = time.time()
        fired = []
        with self._lock:
            remaining = []
            for r in self._reminders:
                if r.get("fire_at", 0) <= now_ts:
                    fired.append(r)
                    # Reschedule recurring reminders
                    if r.get("recur_type") == "interval":
                        new_r = dict(r)
                        new_r["fire_at"] = now_ts + r["recur_value"]
                        remaining.append(new_r)
                    elif r.get("recur_type") == "daily":
                        new_r = dict(r)
                        dt = _parse_absolute_time(r["recur_value"])
                        if dt:
                            new_r["fire_at"] = dt.timestamp()
                        remaining.append(new_r)
                    # Non-recurring: don't keep
                else:
                    remaining.append(r)
            self._reminders = remaining
            self._save_config()

        # Notify on main thread
        for r in fired:
            self._fire_reminder(r)

    def _fire_reminder(self, reminder: dict):
        """Display the reminder notification and play a sound."""
        kind = reminder.get("kind", "reminder")
        message = reminder.get("message", "")
        rid = reminder.get("id", "?")
        recur_label = ""
        if reminder.get("recur_type"):
            recur_label = " (recurring)"

        if kind == "timer":
            text = f"Timer #{rid} is up!{recur_label}"
        elif kind == "alarm":
            text = f"Alarm #{rid}! {message}{recur_label}"
        else:
            text = f"Reminder #{rid}: {message}{recur_label}"

        # UI update from background thread — schedule on main thread
        def _notify():
            self.jarvis.chat.add_message("system",
                f"[ALERT] {text}")

        self.jarvis.root.after(0, _notify)

        # Play sound in background
        threading.Thread(target=_beep, daemon=True).start()

    # ══════════════════════════════════════════════════════════════
    # COMMANDS
    # ══════════════════════════════════════════════════════════════

    def on_command(self, command: str, args: str) -> bool:
        if command == "/remind":
            self._cmd_remind(args)
            return True
        if command == "/timer":
            self._cmd_timer(args)
            return True
        if command == "/alarm":
            self._cmd_alarm(args)
            return True
        if command == "/reminders":
            self._cmd_list()
            return True
        if command == "/cancelreminder":
            self._cmd_cancel(args)
            return True
        return False

    def _cmd_remind(self, args: str):
        """Parse: /remind <time> <message>"""
        if not args.strip():
            self.jarvis.chat.add_message("system",
                "Usage: /remind <time> <message>\n"
                "Examples: /remind 5m drink water | /remind 14:30 meeting | /remind every 30m stretch")
            return

        parts = args.strip().split(None, 1)

        # Check for "every ..." recurring syntax
        if args.strip().lower().startswith("every "):
            self._parse_recurring_remind(args.strip())
            return

        time_str = parts[0]
        message = parts[1] if len(parts) > 1 else "Reminder!"

        # Try relative duration
        secs = _parse_relative_duration(time_str)
        if secs:
            fire_at = time.time() + secs
            self._add_reminder("reminder", message, fire_at)
            self.jarvis.chat.add_message("assistant",
                f"Reminder set for {_format_duration(secs)} from now: \"{message}\"")
            return

        # Try absolute time
        dt = _parse_absolute_time(time_str)
        if dt:
            fire_at = dt.timestamp()
            self._add_reminder("reminder", message, fire_at)
            self.jarvis.chat.add_message("assistant",
                f"Reminder set for {dt.strftime('%H:%M')}: \"{message}\"")
            return

        self.jarvis.chat.add_message("system",
            f"Could not parse time: \"{time_str}\". Use formats like 5m, 2h, 1h30m, 14:30, 2:30pm")

    def _parse_recurring_remind(self, text: str):
        """Handle 'every ...' recurring reminders."""
        # "every 30m stretch" or "every day at 9am check email"
        # Try to split into recurring part and message
        # Pattern: "every <interval> <message>" or "every day at <time> <message>"
        match = re.match(
            r"^(every\s+day\s+at\s+\S+|every\s+\S+)\s*(.*)?$",
            text, re.IGNORECASE,
        )
        if not match:
            self.jarvis.chat.add_message("system",
                "Could not parse recurring pattern. Examples: every 30m, every day at 9am")
            return

        recur_part = match.group(1).strip()
        message = (match.group(2) or "").strip() or "Recurring reminder"
        recur_type, recur_value = _parse_recurring(recur_part)

        if not recur_type:
            self.jarvis.chat.add_message("system",
                "Could not parse recurring pattern. Examples: every 30m, every day at 9am")
            return

        if recur_type == "interval":
            fire_at = time.time() + recur_value
            self._add_reminder("reminder", message, fire_at,
                               recur_type="interval", recur_value=recur_value)
            self.jarvis.chat.add_message("assistant",
                f"Recurring reminder set every {_format_duration(recur_value)}: \"{message}\"")
        elif recur_type == "daily":
            dt = _parse_absolute_time(recur_value)
            if dt:
                fire_at = dt.timestamp()
                self._add_reminder("reminder", message, fire_at,
                                   recur_type="daily", recur_value=recur_value)
                self.jarvis.chat.add_message("assistant",
                    f"Daily reminder set for {recur_value}: \"{message}\"")

    def _cmd_timer(self, args: str):
        """Parse: /timer <duration>"""
        if not args.strip():
            self.jarvis.chat.add_message("system",
                "Usage: /timer <duration>\nExamples: /timer 10m | /timer 1h30m | /timer 30s")
            return

        secs = _parse_relative_duration(args.strip())
        if not secs:
            self.jarvis.chat.add_message("system",
                f"Could not parse duration: \"{args.strip()}\". Use formats like 10m, 1h30m, 30s")
            return

        fire_at = time.time() + secs
        self._add_reminder("timer", f"Timer ({_format_duration(secs)})", fire_at)
        self.jarvis.chat.add_message("assistant",
            f"Timer set for {_format_duration(secs)}.")

    def _cmd_alarm(self, args: str):
        """Parse: /alarm <time>"""
        if not args.strip():
            self.jarvis.chat.add_message("system",
                "Usage: /alarm <time>\nExamples: /alarm 07:00 | /alarm 2:30pm")
            return

        parts = args.strip().split(None, 1)
        time_str = parts[0]
        message = parts[1] if len(parts) > 1 else "Alarm!"

        # Check for recurring: "every day at ..."
        if args.strip().lower().startswith("every"):
            self._parse_recurring_remind(args.strip())
            return

        dt = _parse_absolute_time(time_str)
        if not dt:
            self.jarvis.chat.add_message("system",
                f"Could not parse time: \"{time_str}\". Use formats like 07:00, 2:30pm, 9am")
            return

        fire_at = dt.timestamp()
        self._add_reminder("alarm", message, fire_at)
        self.jarvis.chat.add_message("assistant",
            f"Alarm set for {dt.strftime('%H:%M')} ({dt.strftime('%A')}): \"{message}\"")

    def _cmd_list(self):
        """List all active reminders."""
        with self._lock:
            reminders = list(self._reminders)

        if not reminders:
            self.jarvis.chat.add_message("assistant", "No active reminders, sir.")
            return

        lines = ["Active Reminders", "────────────────"]
        for r in sorted(reminders, key=lambda x: x.get("fire_at", 0)):
            rid = r.get("id", "?")
            kind = r.get("kind", "reminder").title()
            message = r.get("message", "")
            fire_at = r.get("fire_at", 0)
            fire_dt = datetime.fromtimestamp(fire_at)
            remaining = fire_at - time.time()

            recur_info = ""
            if r.get("recur_type") == "interval":
                recur_info = f" [every {_format_duration(r['recur_value'])}]"
            elif r.get("recur_type") == "daily":
                recur_info = f" [daily at {r['recur_value']}]"

            if remaining > 0:
                time_label = f"{fire_dt.strftime('%H:%M')} (in {_format_duration(int(remaining))})"
            else:
                time_label = f"{fire_dt.strftime('%H:%M')} (overdue)"

            lines.append(f"  #{rid} [{kind}] {time_label} — {message}{recur_info}")

        self.jarvis.chat.add_message("assistant", "\n".join(lines))

    def _cmd_cancel(self, args: str):
        """Cancel a reminder by ID."""
        if not args.strip():
            self.jarvis.chat.add_message("system", "Usage: /cancelreminder <id>")
            return

        try:
            target_id = int(args.strip().lstrip("#"))
        except ValueError:
            self.jarvis.chat.add_message("system", "Invalid ID. Use /reminders to see active IDs.")
            return

        with self._lock:
            before = len(self._reminders)
            self._reminders = [r for r in self._reminders if r.get("id") != target_id]
            after = len(self._reminders)
            self._save_config()

        if after < before:
            self.jarvis.chat.add_message("assistant", f"Reminder #{target_id} cancelled, sir.")
        else:
            self.jarvis.chat.add_message("system",
                f"No reminder with ID #{target_id} found. Use /reminders to see active IDs.")

    # ══════════════════════════════════════════════════════════════
    # NATURAL LANGUAGE
    # ══════════════════════════════════════════════════════════════

    def on_message(self, message: str) -> str | None:
        """Intercept natural language reminder/timer/alarm requests."""
        msg_lower = message.lower().strip()

        # "remind me to <message> in <time>" or "remind me in <time> to <message>"
        match = re.search(
            r"remind\s+me\s+to\s+(.+?)\s+in\s+(\d+[hms](?:\d+[ms])?)",
            msg_lower,
        )
        if match:
            msg = match.group(1).strip()
            secs = _parse_relative_duration(match.group(2))
            if secs:
                fire_at = time.time() + secs
                self._add_reminder("reminder", msg, fire_at)
                self.jarvis.chat.add_message("assistant",
                    f"Reminder set for {_format_duration(secs)} from now: \"{msg}\"")
                return "__handled__"

        match = re.search(
            r"remind\s+me\s+in\s+(\d+[hms](?:\d+[ms])?)\s+to\s+(.+)",
            msg_lower,
        )
        if match:
            secs = _parse_relative_duration(match.group(1))
            msg = match.group(2).strip()
            if secs:
                fire_at = time.time() + secs
                self._add_reminder("reminder", msg, fire_at)
                self.jarvis.chat.add_message("assistant",
                    f"Reminder set for {_format_duration(secs)} from now: \"{msg}\"")
                return "__handled__"

        # "remind me at <time> to <message>"
        match = re.search(
            r"remind\s+me\s+at\s+(\S+)\s+to\s+(.+)",
            msg_lower,
        )
        if match:
            dt = _parse_absolute_time(match.group(1))
            msg = match.group(2).strip()
            if dt:
                fire_at = dt.timestamp()
                self._add_reminder("reminder", msg, fire_at)
                self.jarvis.chat.add_message("assistant",
                    f"Reminder set for {dt.strftime('%H:%M')}: \"{msg}\"")
                return "__handled__"

        # "remind me to <message> at <time>"
        match = re.search(
            r"remind\s+me\s+to\s+(.+?)\s+at\s+(\S+)",
            msg_lower,
        )
        if match:
            msg = match.group(1).strip()
            dt = _parse_absolute_time(match.group(2))
            if dt:
                fire_at = dt.timestamp()
                self._add_reminder("reminder", msg, fire_at)
                self.jarvis.chat.add_message("assistant",
                    f"Reminder set for {dt.strftime('%H:%M')}: \"{msg}\"")
                return "__handled__"

        # "set a timer for <duration>"
        match = re.search(
            r"set\s+(?:a\s+)?timer\s+(?:for\s+)?(\d+[hms](?:\d+[ms])?)",
            msg_lower,
        )
        if match:
            secs = _parse_relative_duration(match.group(1))
            if secs:
                fire_at = time.time() + secs
                self._add_reminder("timer", f"Timer ({_format_duration(secs)})", fire_at)
                self.jarvis.chat.add_message("assistant",
                    f"Timer set for {_format_duration(secs)}.")
                return "__handled__"

        # "wake me up at <time>"
        match = re.search(
            r"wake\s+me\s+(?:up\s+)?at\s+(\S+)",
            msg_lower,
        )
        if match:
            dt = _parse_absolute_time(match.group(1))
            if dt:
                fire_at = dt.timestamp()
                self._add_reminder("alarm", "Wake up!", fire_at)
                self.jarvis.chat.add_message("assistant",
                    f"Alarm set for {dt.strftime('%H:%M')}. I'll wake you up, sir.")
                return "__handled__"

        # "every day at <time> <message>" or "every <interval> <message>"
        match = re.match(
            r"(?:set\s+)?(?:a\s+)?(?:recurring\s+)?(?:reminder\s+)?(every\s+.+)",
            msg_lower,
        )
        if match:
            recur_text = match.group(1).strip()
            # Try to extract message after the recurring part
            rmatch = re.match(
                r"^(every\s+day\s+at\s+\S+|every\s+\S+)\s+(.*)?$",
                recur_text, re.IGNORECASE,
            )
            if rmatch:
                recur_part = rmatch.group(1).strip()
                msg = (rmatch.group(2) or "").strip() or "Recurring reminder"
                recur_type, recur_value = _parse_recurring(recur_part)
                if recur_type:
                    if recur_type == "interval":
                        fire_at = time.time() + recur_value
                        self._add_reminder("reminder", msg, fire_at,
                                           recur_type="interval", recur_value=recur_value)
                        self.jarvis.chat.add_message("assistant",
                            f"Recurring reminder set every {_format_duration(recur_value)}: \"{msg}\"")
                    elif recur_type == "daily":
                        dt = _parse_absolute_time(recur_value)
                        if dt:
                            fire_at = dt.timestamp()
                            self._add_reminder("reminder", msg, fire_at,
                                               recur_type="daily", recur_value=recur_value)
                            self.jarvis.chat.add_message("assistant",
                                f"Daily reminder set for {recur_value}: \"{msg}\"")
                    return "__handled__"

        return None  # Pass through to AI

    # ══════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════

    def _add_reminder(self, kind: str, message: str, fire_at: float,
                      recur_type: str = None, recur_value=None):
        """Add a reminder to the list and persist."""
        with self._lock:
            reminder = {
                "id": self._next_id,
                "kind": kind,
                "message": message,
                "fire_at": fire_at,
                "created_at": time.time(),
            }
            if recur_type:
                reminder["recur_type"] = recur_type
                reminder["recur_value"] = recur_value
            self._reminders.append(reminder)
            self._next_id += 1
            self._save_config()

    def get_status(self) -> dict:
        with self._lock:
            count = len(self._reminders)
        return {
            "name": self.name,
            "active": True,
            "active_reminders": count,
        }
