"""
J.A.R.V.I.S — User Learning System
Tracks operator patterns, habits, and preferences over time.

Learns:
    - Frequently used apps (and when)
    - Common command patterns
    - Time-of-day activity
    - Speech patterns & corrections
    - Preferred responses
    - Topics of interest

Data stored in config JSON — no external database needed.
"""

import time
from datetime import datetime
from collections import Counter

from core.config import save_config


class UserLearner:
    """
    Observes and learns from user behavior over time.
    Stores learned data persistently in config.
    """

    def __init__(self, config: dict):
        self.config = config
        # Initialize learning data if not present
        if "learned" not in self.config:
            self.config["learned"] = {
                "app_usage": {},         # app_name → {count, last_used, times_of_day}
                "command_freq": {},      # command → count
                "topics": {},            # topic → count
                "active_hours": {},      # hour (0-23) → message count
                "word_freq": {},         # common words → count
                "corrections": [],       # speech recognition corrections
                "preferences": {},       # key-value preferences
                "total_messages": 0,
                "total_sessions": 0,
                "first_seen": datetime.now().isoformat(),
            }
            self._save()

    @property
    def data(self) -> dict:
        return self.config.get("learned", {})

    def _save(self):
        save_config(self.config)

    # ══════════════════════════════════════════════════════════════
    # TRACKING
    # ══════════════════════════════════════════════════════════════

    def on_message(self, message: str):
        """Track a user message — called on every input."""
        d = self.data
        d["total_messages"] = d.get("total_messages", 0) + 1

        # Track active hours
        hour = str(datetime.now().hour)
        hours = d.get("active_hours", {})
        hours[hour] = hours.get(hour, 0) + 1
        d["active_hours"] = hours

        # Track word frequency (skip short words)
        words = message.lower().split()
        word_freq = d.get("word_freq", {})
        for word in words:
            if len(word) > 3 and word.isalpha():
                word_freq[word] = word_freq.get(word, 0) + 1
        # Keep top 100 words only
        if len(word_freq) > 100:
            top = dict(Counter(word_freq).most_common(100))
            d["word_freq"] = top
        else:
            d["word_freq"] = word_freq

        self.config["learned"] = d
        # Save periodically (every 10 messages)
        if d["total_messages"] % 10 == 0:
            self._save()

    def on_app_opened(self, app_name: str):
        """Track an app being opened."""
        d = self.data
        apps = d.get("app_usage", {})

        app_name = app_name.lower().strip()
        if app_name not in apps:
            apps[app_name] = {"count": 0, "times_of_day": []}

        apps[app_name]["count"] = apps[app_name].get("count", 0) + 1
        apps[app_name]["last_used"] = datetime.now().isoformat()
        # Track time of day
        hour = datetime.now().hour
        times = apps[app_name].get("times_of_day", [])
        times.append(hour)
        # Keep last 20 entries
        apps[app_name]["times_of_day"] = times[-20:]

        d["app_usage"] = apps
        self.config["learned"] = d
        self._save()

    def on_command(self, command: str):
        """Track a command usage."""
        d = self.data
        cmds = d.get("command_freq", {})
        cmds[command] = cmds.get(command, 0) + 1
        d["command_freq"] = cmds
        self.config["learned"] = d

    def on_topic(self, topic: str):
        """Track a topic of interest."""
        d = self.data
        topics = d.get("topics", {})
        topic = topic.lower().strip()
        topics[topic] = topics.get(topic, 0) + 1
        d["topics"] = topics
        self.config["learned"] = d

    def learn_preference(self, key: str, value: str):
        """Store a user preference."""
        d = self.data
        prefs = d.get("preferences", {})
        prefs[key] = value
        d["preferences"] = prefs
        self.config["learned"] = d
        self._save()

    def on_session_start(self):
        """Track a new session."""
        d = self.data
        d["total_sessions"] = d.get("total_sessions", 0) + 1
        d["last_session"] = datetime.now().isoformat()
        self.config["learned"] = d
        self._save()

    # ══════════════════════════════════════════════════════════════
    # INSIGHTS — feed into LLM context
    # ══════════════════════════════════════════════════════════════

    def get_context_string(self) -> str:
        """Generate a context block for the LLM about the user."""
        d = self.data
        if d.get("total_messages", 0) < 5:
            return ""  # Not enough data yet

        parts = ["[USER PROFILE — Learned from behavior]"]

        # App usage patterns
        apps = d.get("app_usage", {})
        if apps:
            top_apps = sorted(apps.items(), key=lambda x: x[1].get("count", 0), reverse=True)[:5]
            app_list = ", ".join(f"{name} ({info['count']}x)" for name, info in top_apps)
            parts.append(f"Frequently used apps: {app_list}")

        # Active hours
        hours = d.get("active_hours", {})
        if hours:
            sorted_hours = sorted(hours.items(), key=lambda x: int(x[1]), reverse=True)[:3]
            peak = ", ".join(f"{int(h)}:00" for h, _ in sorted_hours)
            parts.append(f"Most active hours: {peak}")

        # Topics of interest
        topics = d.get("topics", {})
        if topics:
            top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]
            topic_list = ", ".join(t for t, _ in top_topics)
            parts.append(f"Topics of interest: {topic_list}")

        # Preferences
        prefs = d.get("preferences", {})
        if prefs:
            pref_list = ", ".join(f"{k}: {v}" for k, v in prefs.items())
            parts.append(f"Preferences: {pref_list}")

        # Session stats
        total_msgs = d.get("total_messages", 0)
        total_sess = d.get("total_sessions", 0)
        parts.append(f"Usage: {total_msgs} messages across {total_sess} sessions")

        return "\n".join(parts)

    def get_suggested_apps(self) -> list[str]:
        """Return top apps the user frequently opens — for quick suggestions."""
        apps = self.data.get("app_usage", {})
        if not apps:
            return []
        sorted_apps = sorted(apps.items(), key=lambda x: x[1].get("count", 0), reverse=True)
        return [name for name, _ in sorted_apps[:5]]

    def get_peak_hours(self) -> list[int]:
        """Return the user's most active hours."""
        hours = self.data.get("active_hours", {})
        if not hours:
            return []
        sorted_hours = sorted(hours.items(), key=lambda x: int(x[1]), reverse=True)
        return [int(h) for h, _ in sorted_hours[:3]]

    def get_stats_summary(self) -> str:
        """Quick stats for the sidebar/status."""
        d = self.data
        total = d.get("total_messages", 0)
        sessions = d.get("total_sessions", 0)
        apps_used = len(d.get("app_usage", {}))
        return f"Messages: {total} | Sessions: {sessions} | Apps: {apps_used}"
