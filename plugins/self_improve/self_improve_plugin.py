"""
J.A.R.V.I.S -- Self-Improvement Plugin
Allows JARVIS to analyze its own performance, suggest improvements,
create new quick-response patterns, and expand its own capabilities.

NOT code-level self-modification -- JARVIS learns new response patterns,
custom commands, and behavioral rules at runtime.

Commands:
    /improve           -- JARVIS analyzes its weak points and suggests fixes
    /teach <trigger> = <response>  -- Teach JARVIS a new custom response
    /customs           -- List all custom learned responses
    /unteach <trigger> -- Remove a custom response
    /performance       -- Show performance stats and bottlenecks
    /suggest           -- JARVIS proactively suggests features based on usage
"""

import re
import os
import json
import time
import threading
from datetime import datetime
from collections import Counter

from core.plugin_manager import PluginBase
from core.config import save_config

CUSTOM_RESPONSES_FILE = os.path.join(
    os.path.expanduser("~"), ".jarvis_custom_responses.json"
)


class SelfImprovePlugin(PluginBase):
    name = "self_improve"
    description = "Self-improvement -- JARVIS learns new patterns and optimizes itself"
    version = "1.0"

    def __init__(self, jarvis):
        super().__init__(jarvis)
        self._customs = self._load_customs()
        # Track failures for improvement suggestions
        self._failures = []    # list of {"query", "error", "timestamp"}
        self._slow_queries = []  # list of {"query", "latency_ms", "timestamp"}
        self._unhandled = []   # queries that fell through to generic AI

    def activate(self):
        print(f"[JARVIS] Self-improve: {len(self._customs)} custom responses loaded")

    def deactivate(self):
        self._save_customs()

    # ══════════════════════════════════════════════════════════════
    # CUSTOM RESPONSES -- Teachable patterns
    # ══════════════════════════════════════════════════════════════

    def _load_customs(self) -> dict:
        try:
            with open(CUSTOM_RESPONSES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_customs(self):
        with open(CUSTOM_RESPONSES_FILE, "w", encoding="utf-8") as f:
            json.dump(self._customs, f, indent=2, ensure_ascii=False)

    def _match_custom(self, text: str) -> str | None:
        """Check if text matches any custom taught response."""
        text_lower = text.lower().strip()
        # Exact match first
        if text_lower in self._customs:
            entry = self._customs[text_lower]
            entry["uses"] = entry.get("uses", 0) + 1
            return entry["response"]
        # Fuzzy: check if any trigger is contained in the text
        for trigger, entry in self._customs.items():
            if trigger in text_lower and len(trigger) > 3:
                entry["uses"] = entry.get("uses", 0) + 1
                return entry["response"]
        return None

    # ══════════════════════════════════════════════════════════════
    # PERFORMANCE TRACKING
    # ══════════════════════════════════════════════════════════════

    def track_failure(self, query: str, error: str):
        """Called by the app when a query fails."""
        self._failures.append({
            "query": query[:200],
            "error": str(error)[:200],
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 50
        if len(self._failures) > 50:
            self._failures = self._failures[-50:]

    def track_slow(self, query: str, latency_ms: float):
        """Called when a query takes too long."""
        if latency_ms > 5000:  # > 5 seconds
            self._slow_queries.append({
                "query": query[:200],
                "latency_ms": round(latency_ms),
                "timestamp": datetime.now().isoformat(),
            })
            if len(self._slow_queries) > 50:
                self._slow_queries = self._slow_queries[-50:]

    def track_unhandled(self, query: str):
        """Called when a query isn't handled by any fast-path or tool."""
        self._unhandled.append(query[:200])
        if len(self._unhandled) > 100:
            self._unhandled = self._unhandled[-100:]

    # ══════════════════════════════════════════════════════════════
    # COMMANDS
    # ══════════════════════════════════════════════════════════════

    def on_command(self, command: str, args: str) -> bool:
        cmd = command.lower()

        if cmd == "/teach":
            return self._handle_teach(args)

        if cmd == "/unteach":
            return self._handle_unteach(args)

        if cmd == "/customs":
            return self._handle_list_customs()

        if cmd == "/improve":
            self._analyze_and_suggest()
            return True

        if cmd == "/performance":
            self._show_performance()
            return True

        if cmd == "/suggest":
            self._proactive_suggest()
            return True

        return False

    def _handle_teach(self, args: str) -> bool:
        """Teach: /teach <trigger> = <response>"""
        if "=" not in args:
            self._msg("system",
                "Usage: /teach <trigger> = <response>\n"
                "Example: /teach good morning dev = Good morning Dev! Ready to conquer the day?")
            return True

        trigger, response = args.split("=", 1)
        trigger = trigger.strip().lower()
        response = response.strip()

        if not trigger or not response:
            self._msg("system", "Both trigger and response are required.")
            return True

        self._customs[trigger] = {
            "response": response,
            "created": datetime.now().isoformat(),
            "uses": 0,
        }
        self._save_customs()
        self._msg("assistant",
            f"Learned! When I hear \"{trigger}\", I'll respond with:\n\"{response}\"")
        return True

    def _handle_unteach(self, args: str) -> bool:
        trigger = args.strip().lower()
        if trigger in self._customs:
            del self._customs[trigger]
            self._save_customs()
            self._msg("assistant", f"Forgotten: \"{trigger}\"")
        else:
            self._msg("system", f"No custom response found for \"{trigger}\"")
        return True

    def _handle_list_customs(self) -> bool:
        if not self._customs:
            self._msg("assistant",
                "No custom responses yet. Teach me with:\n"
                "  /teach <trigger> = <response>")
            return True

        lines = ["Custom Learned Responses", "=" * 40]
        for trigger, entry in sorted(self._customs.items()):
            uses = entry.get("uses", 0)
            resp = entry["response"][:60]
            lines.append(f"\n  \"{trigger}\" -> \"{resp}{'...' if len(entry['response']) > 60 else ''}\"")
            lines.append(f"    Uses: {uses}")
        lines.append(f"\nTotal: {len(self._customs)} custom responses")
        self._msg("assistant", "\n".join(lines))
        return True

    def _analyze_and_suggest(self):
        """Analyze JARVIS's performance and suggest improvements."""
        suggestions = []

        # Analyze failures
        if self._failures:
            error_types = Counter(f["error"][:50] for f in self._failures)
            most_common = error_types.most_common(3)
            for err, count in most_common:
                suggestions.append(f"Error '{err}' occurred {count}x — may need a fix")

        # Analyze slow queries
        if self._slow_queries:
            avg_slow = sum(q["latency_ms"] for q in self._slow_queries) / len(self._slow_queries)
            suggestions.append(
                f"{len(self._slow_queries)} slow queries (avg {avg_slow:.0f}ms) — "
                f"consider caching common responses with /teach")

        # Analyze unhandled queries for patterns
        if self._unhandled:
            words = []
            for q in self._unhandled:
                words.extend(q.lower().split())
            common_words = Counter(w for w in words if len(w) > 3).most_common(5)
            if common_words:
                topics = ", ".join(w for w, _ in common_words)
                suggestions.append(
                    f"Frequently asked topics without fast-path: {topics} — "
                    f"teach me responses for these")

        # Check cognitive stats
        if hasattr(self.jarvis, "cognitive"):
            stats = self.jarvis.cognitive.get_stats()
            hit_rate = stats.get("hit_rate", 0)
            if hit_rate < 20 and stats.get("interactions", 0) > 20:
                suggestions.append(
                    f"Cache hit rate is low ({hit_rate:.0f}%) — "
                    f"use /teach to add common Q&A pairs")
            knowledge = stats.get("total_knowledge", 0)
            if knowledge < 10:
                suggestions.append(
                    "Knowledge base is small — talk to me more so I can learn about you")

        # Check learner data
        if hasattr(self.jarvis, "learner"):
            data = self.jarvis.learner.data
            hours = data.get("active_hours", {})
            if hours:
                peak = max(hours, key=lambda h: hours[h])
                suggestions.append(
                    f"You're most active at {peak}:00 — "
                    f"I could proactively greet you and suggest tasks at that time")

            apps = data.get("app_usage", {})
            if apps:
                top_app = max(apps, key=lambda a: apps[a].get("count", 0))
                suggestions.append(
                    f"You use {top_app} often — I could add a quick command for it")

        if not suggestions:
            suggestions.append("Everything looks good! Keep using me and I'll find more ways to improve.")

        lines = ["Self-Improvement Analysis", "=" * 40, ""]
        for i, s in enumerate(suggestions, 1):
            lines.append(f"  {i}. {s}")

        lines.append(f"\nTip: Use /teach to train me on responses I should know instantly.")
        self._msg("assistant", "\n".join(lines))

    def _show_performance(self):
        """Show performance dashboard."""
        lines = ["Performance Dashboard", "=" * 40]

        # Failures
        lines.append(f"\nErrors (last 50): {len(self._failures)}")
        if self._failures:
            recent = self._failures[-3:]
            for f in recent:
                lines.append(f"  - {f['query'][:40]}... -> {f['error'][:40]}")

        # Slow queries
        lines.append(f"\nSlow queries (>5s): {len(self._slow_queries)}")
        if self._slow_queries:
            avg = sum(q["latency_ms"] for q in self._slow_queries) / len(self._slow_queries)
            lines.append(f"  Average latency: {avg:.0f}ms")

        # Custom responses
        total_uses = sum(e.get("uses", 0) for e in self._customs.values())
        lines.append(f"\nCustom responses: {len(self._customs)} ({total_uses} total uses)")

        # Cognitive stats
        if hasattr(self.jarvis, "cognitive"):
            stats = self.jarvis.cognitive.get_stats()
            lines.append(f"\nCognitive Core:")
            lines.append(f"  Knowledge entries: {stats.get('total_knowledge', 0)}")
            lines.append(f"  Cache hits/misses: {stats.get('cache_hits', 0)}/{stats.get('cache_misses', 0)}")
            lines.append(f"  Hit rate: {stats.get('hit_rate', 0):.1f}%")

        # Learner stats
        if hasattr(self.jarvis, "learner"):
            lines.append(f"\n{self.jarvis.learner.get_stats_summary()}")

        self._msg("assistant", "\n".join(lines))

    def _proactive_suggest(self):
        """Suggest features based on usage patterns."""
        suggestions = []

        if hasattr(self.jarvis, "learner"):
            data = self.jarvis.learner.data
            total = data.get("total_messages", 0)

            # Suggest based on frequent words
            words = data.get("word_freq", {})
            if "code" in words or "python" in words:
                suggestions.append("You talk about code often — try /pyrun for quick Python execution")
            if "email" in words or "mail" in words:
                suggestions.append("You mention email — set up /emailsetup to check inbox via voice")
            if "security" in words or "scan" in words:
                suggestions.append("Security is your thing — try /audit for a full system security check")

            # Suggest based on apps
            apps = data.get("app_usage", {})
            if "chrome" in apps and apps["chrome"].get("count", 0) > 3:
                suggestions.append(
                    "You open Chrome a lot — teach me shortcuts:\n"
                    "  /teach check youtube = (opens YouTube in Chrome)")

            if total > 50 and not self._customs:
                suggestions.append(
                    "You've sent 50+ messages but haven't taught me anything yet!\n"
                    "Use /teach to make me respond instantly to your common questions.")

        if not suggestions:
            suggestions.append(
                "Keep using me! The more we interact, the better my suggestions get.")

        lines = ["Proactive Suggestions", "=" * 40, ""]
        for i, s in enumerate(suggestions, 1):
            lines.append(f"  {i}. {s}")
        self._msg("assistant", "\n".join(lines))

    # ══════════════════════════════════════════════════════════════
    # MESSAGE INTERCEPT — check custom responses first
    # ══════════════════════════════════════════════════════════════

    def on_message(self, message: str) -> str | None:
        """Check if this matches a taught custom response."""
        custom = self._match_custom(message)
        if custom:
            self.jarvis.chat.add_message("assistant", custom)
            # Save periodically
            if sum(e.get("uses", 0) for e in self._customs.values()) % 10 == 0:
                self._save_customs()
            return "__handled__"
        return None

    def _msg(self, role, text):
        self.jarvis.root.after(0,
            lambda: self.jarvis.chat.add_message(role, text))

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "active": True,
            "custom_responses": len(self._customs),
            "failures_tracked": len(self._failures),
        }
