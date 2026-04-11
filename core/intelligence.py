"""
J.A.R.V.I.S — Intelligence Engine
The brain behind the brain. Makes JARVIS genuinely smart, not just reactive.

Three integrated systems:
    1. FeedbackLoop     — learns from outcomes, corrections, dismissals
    2. PredictiveEngine  — anticipates needs from behavioral patterns
    3. EmotionalIQ       — reads mood, adapts tone, builds rapport

This is what separates JARVIS from a chatbot.
Without this, JARVIS responds. With this, JARVIS *thinks*.
"""

import os
import re
import json
import time
import math
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict
from difflib import SequenceMatcher

logger = logging.getLogger("jarvis.intelligence")

# ── Storage ───────────────────────────────────────────────────
_INTEL_FILE = Path.home() / ".jarvis_intelligence.json"
_SAVE_INTERVAL = 5  # save every N interactions


def _load_intel() -> dict:
    try:
        return json.loads(_INTEL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_intel(data: dict):
    try:
        tmp = str(_INTEL_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, str(_INTEL_FILE))
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════
#  1. FEEDBACK LEARNING LOOP
#     "Every interaction teaches JARVIS something."
# ═══════════════════════════════════════════════════════════════

class FeedbackLoop:
    """
    Tracks outcomes of every action and learns from them.

    Learns from:
    - User corrections ("no, I meant...", "that's wrong", "not that")
    - User confirmations ("perfect", "exactly", "good job")
    - Dismissed notifications (stop suggesting those)
    - Tool success/failure rates (prefer reliable tools)
    - Response quality signals (short follow-ups = bad answer)
    - Repeated questions (means first answer was bad)

    Outputs:
    - Approach preferences per task type
    - Tool reliability scores
    - Topics where JARVIS is weak (needs improvement)
    - Notification preferences (what to show/hide)
    """

    # Correction signals
    _CORRECTION_PATTERNS = re.compile(
        r"\b(?:no[,.]?\s|not that|wrong|incorrect|that's not|"
        r"I (?:meant|said|wanted)|don't do that|stop|undo|"
        r"I didn't (?:ask|mean|want)|actually[,.]?\s+I|"
        r"forget (?:that|it)|never ?mind)\b",
        re.IGNORECASE,
    )

    # Positive signals
    _POSITIVE_PATTERNS = re.compile(
        r"\b(?:perfect|exactly|great|good job|thanks|thank you|"
        r"nice|awesome|brilliant|well done|that's (?:right|correct|it)|"
        r"yes[,!.]?\s|yeah|yep|spot on|love it|nailed it)\b",
        re.IGNORECASE,
    )

    # Frustration signals (not just negative — these mean JARVIS is failing)
    _FRUSTRATION_PATTERNS = re.compile(
        r"\b(?:why (?:can't you|won't you|doesn't|isn't)|"
        r"this (?:doesn't work|is broken|sucks)|"
        r"I already (?:told you|said)|you keep|"
        r"for the (?:second|third|last) time|"
        r"just do it|come on|seriously|ugh|ffs)\b",
        re.IGNORECASE,
    )

    def __init__(self):
        self._lock = threading.Lock()
        self._data = _load_intel()
        self._data.setdefault("feedback", {
            "tool_scores": {},       # tool_name → {success, fail, total}
            "approach_prefs": {},    # task_type → {preferred_approach, score}
            "weak_topics": [],       # topics where JARVIS gave bad answers
            "dismissed_notifs": [],  # notification types user doesn't want
            "corrections": [],       # recent corrections for pattern learning
            "positive_signals": 0,   # total positive feedback count
            "negative_signals": 0,   # total correction count
            "repeated_questions": [],  # questions asked more than once
            "interaction_outcomes": [],  # last 200 interaction outcomes
        })
        self._pending_saves = 0
        self._last_user_msg = ""
        self._last_jarvis_reply = ""
        self._last_tool_used = ""

    def _save(self):
        self._pending_saves += 1
        if self._pending_saves % _SAVE_INTERVAL == 0:
            _save_intel(self._data)

    def flush(self):
        _save_intel(self._data)

    # ── Recording ─────────────────────────────────────────────

    def on_user_message(self, message: str, previous_reply: str = ""):
        """Analyze every user message for feedback signals."""
        msg_lower = message.lower().strip()

        # Check if this is a correction of the previous response
        if previous_reply and self._CORRECTION_PATTERNS.search(message):
            self._record_correction(message, previous_reply)

        # Check for positive feedback
        if previous_reply and self._POSITIVE_PATTERNS.search(message):
            self._record_positive(message, previous_reply)

        # Check for frustration (JARVIS is failing the user)
        if self._FRUSTRATION_PATTERNS.search(message):
            self._record_frustration(message)

        # Check for repeated questions
        self._check_repeated(message)

        # Track the exchange
        self._last_user_msg = message
        self._save()

    def on_jarvis_reply(self, reply: str, tool_used: str = ""):
        """Track JARVIS's response for outcome analysis."""
        self._last_jarvis_reply = reply
        self._last_tool_used = tool_used

    def on_tool_result(self, tool_name: str, success: bool, error: str = ""):
        """Track tool success/failure rates."""
        fb = self._data["feedback"]
        scores = fb["tool_scores"]

        if tool_name not in scores:
            scores[tool_name] = {"success": 0, "fail": 0, "total": 0}

        scores[tool_name]["total"] += 1
        if success:
            scores[tool_name]["success"] += 1
        else:
            scores[tool_name]["fail"] += 1
        self._save()

    def on_notification_dismissed(self, notif_type: str):
        """User dismissed a notification — learn to stop showing those."""
        fb = self._data["feedback"]
        dismissed = fb["dismissed_notifs"]
        dismissed.append({
            "type": notif_type,
            "time": datetime.now().isoformat(),
        })
        # If dismissed 3+ times, it's a pattern
        type_count = sum(1 for d in dismissed if d["type"] == notif_type)
        if type_count >= 3:
            logger.info("Notification type '%s' dismissed %d times — suppressing",
                       notif_type, type_count)
        self._save()

    # ── Internal recorders ────────────────────────────────────

    def _record_correction(self, user_msg: str, bad_reply: str):
        """JARVIS gave a wrong/unwanted answer — learn from it."""
        fb = self._data["feedback"]
        fb["negative_signals"] = fb.get("negative_signals", 0) + 1

        correction = {
            "user_said": user_msg[:200],
            "bad_reply": bad_reply[:200],
            "tool_used": self._last_tool_used,
            "time": datetime.now().isoformat(),
        }
        fb["corrections"].append(correction)
        # Keep last 100 corrections
        fb["corrections"] = fb["corrections"][-100:]

        # Track weak topic
        if self._last_tool_used:
            fb.setdefault("weak_topics", [])
            fb["weak_topics"].append(self._last_tool_used)
            fb["weak_topics"] = fb["weak_topics"][-50:]

        logger.info("Correction recorded: '%s' was wrong", bad_reply[:60])

    def _record_positive(self, user_msg: str, good_reply: str):
        """JARVIS did well — reinforce this approach."""
        fb = self._data["feedback"]
        fb["positive_signals"] = fb.get("positive_signals", 0) + 1

        outcome = {
            "type": "positive",
            "tool": self._last_tool_used,
            "time": datetime.now().isoformat(),
        }
        fb["interaction_outcomes"].append(outcome)
        fb["interaction_outcomes"] = fb["interaction_outcomes"][-200:]

    def _record_frustration(self, message: str):
        """User is frustrated — JARVIS needs to adapt."""
        fb = self._data["feedback"]
        fb["negative_signals"] = fb.get("negative_signals", 0) + 1
        logger.warning("User frustration detected: %s", message[:80])

    def _check_repeated(self, message: str):
        """If user asks the same thing twice, first answer was bad."""
        fb = self._data["feedback"]
        # Simple check: is this very similar to a recent question?
        for prev in fb.get("repeated_questions", [])[-20:]:
            ratio = SequenceMatcher(None, message.lower(), prev["question"].lower()).ratio()
            if ratio > 0.8:
                prev["count"] = prev.get("count", 1) + 1
                return

        fb.setdefault("repeated_questions", []).append({
            "question": message[:200],
            "count": 1,
            "time": datetime.now().isoformat(),
        })
        fb["repeated_questions"] = fb["repeated_questions"][-50:]

    # ── Query methods (used by other systems) ─────────────────

    def get_tool_reliability(self, tool_name: str) -> float:
        """Returns 0.0 to 1.0 reliability score for a tool."""
        scores = self._data["feedback"]["tool_scores"].get(tool_name, {})
        total = scores.get("total", 0)
        if total == 0:
            return 0.5  # unknown = neutral
        return scores.get("success", 0) / total

    def should_suppress_notification(self, notif_type: str) -> bool:
        """Check if user has dismissed this notification type too many times."""
        dismissed = self._data["feedback"]["dismissed_notifs"]
        count = sum(1 for d in dismissed if d["type"] == notif_type)
        return count >= 3

    def get_weak_topics(self) -> list[str]:
        """Topics where JARVIS keeps getting corrected."""
        topics = self._data["feedback"].get("weak_topics", [])
        if not topics:
            return []
        counts = Counter(topics)
        return [topic for topic, count in counts.most_common(5) if count >= 2]

    def get_satisfaction_score(self) -> float:
        """Overall user satisfaction: 0.0 (terrible) to 1.0 (great)."""
        fb = self._data["feedback"]
        pos = fb.get("positive_signals", 0)
        neg = fb.get("negative_signals", 0)
        total = pos + neg
        if total == 0:
            return 0.7  # default optimistic
        return pos / total

    def get_context_for_llm(self) -> str:
        """Generate feedback context to inject into LLM prompts."""
        parts = []
        fb = self._data["feedback"]

        # Satisfaction level
        score = self.get_satisfaction_score()
        if score < 0.5:
            parts.append("NOTE: User has been frequently correcting responses. "
                        "Be extra careful and ask for clarification when unsure.")

        # Weak topics
        weak = self.get_weak_topics()
        if weak:
            parts.append(f"Areas to improve: {', '.join(weak)}. "
                        "Take extra care with these topics.")

        # Recent corrections
        corrections = fb.get("corrections", [])[-3:]
        if corrections:
            parts.append("Recent corrections to avoid repeating:")
            for c in corrections:
                parts.append(f"  - User said '{c['user_said'][:80]}' "
                           f"when JARVIS wrongly said '{c['bad_reply'][:60]}'")

        return "\n".join(parts) if parts else ""


# ═══════════════════════════════════════════════════════════════
#  2. PREDICTIVE ENGINE
#     "Know what Dev needs before he asks."
# ═══════════════════════════════════════════════════════════════

class PredictiveEngine:
    """
    Learns behavioral patterns and anticipates needs.

    Tracks:
    - Daily routines (what Dev does at what time)
    - Sequential patterns (after X, Dev usually does Y)
    - Tool usage patterns (which tools at which times)
    - Session patterns (how long, what type of work)
    - Weekly cycles (different behavior on different days)

    Outputs:
    - Morning briefings
    - Proactive suggestions based on time/context
    - Anticipatory tool preparation
    - Routine detection and assistance
    """

    def __init__(self):
        self._data = _load_intel()
        self._data.setdefault("patterns", {
            "hourly_actions": {},      # hour → [actions/topics]
            "daily_routines": {},      # day_of_week → [actions]
            "sequences": [],           # [{action_a, action_b, count}]
            "tool_by_hour": {},        # hour → {tool → count}
            "session_types": {},       # time_range → typical_activity
            "last_actions": [],        # last 50 actions for sequence mining
            "daily_summaries": [],     # last 30 days of activity summaries
            "streak_data": {},         # habit tracking
        })
        self._lock = threading.Lock()
        self._pending = 0

    def _save(self):
        self._pending += 1
        if self._pending % _SAVE_INTERVAL == 0:
            _save_intel(self._data)

    def flush(self):
        _save_intel(self._data)

    # ── Recording ─────────────────────────────────────────────

    def on_action(self, action: str, category: str = "", tool: str = ""):
        """Record every user action with timestamp context."""
        now = datetime.now()
        hour = str(now.hour)
        day = now.strftime("%A")
        patterns = self._data["patterns"]

        # Hourly action tracking
        hourly = patterns["hourly_actions"]
        hourly.setdefault(hour, [])
        hourly[hour].append(action[:100])
        # Keep last 20 per hour
        hourly[hour] = hourly[hour][-20:]

        # Daily routine tracking
        daily = patterns["daily_routines"]
        daily.setdefault(day, [])
        daily[day].append({
            "action": action[:100],
            "hour": now.hour,
            "category": category,
        })
        daily[day] = daily[day][-30:]

        # Tool-by-hour tracking
        if tool:
            tbh = patterns["tool_by_hour"]
            tbh.setdefault(hour, {})
            tbh[hour][tool] = tbh[hour].get(tool, 0) + 1

        # Sequence tracking (what comes after what)
        last_actions = patterns["last_actions"]
        if last_actions:
            prev = last_actions[-1]
            self._record_sequence(prev.get("action", ""), action)
        last_actions.append({
            "action": action[:100],
            "category": category,
            "tool": tool,
            "time": now.isoformat(),
        })
        patterns["last_actions"] = last_actions[-50:]

        self._save()

    def _record_sequence(self, action_a: str, action_b: str):
        """Track that action_b follows action_a."""
        sequences = self._data["patterns"]["sequences"]
        a_lower = action_a.lower()[:50]
        b_lower = action_b.lower()[:50]

        for seq in sequences:
            if (SequenceMatcher(None, seq["a"], a_lower).ratio() > 0.7 and
                SequenceMatcher(None, seq["b"], b_lower).ratio() > 0.7):
                seq["count"] = seq.get("count", 1) + 1
                seq["last"] = datetime.now().isoformat()
                return

        sequences.append({
            "a": a_lower,
            "b": b_lower,
            "count": 1,
            "last": datetime.now().isoformat(),
        })
        # Keep top 100 sequences by count
        self._data["patterns"]["sequences"] = sorted(
            sequences, key=lambda x: x.get("count", 0), reverse=True
        )[:100]

    def on_session_end(self, duration_min: float, activities: list[str]):
        """Record session summary for daily pattern learning."""
        now = datetime.now()
        summary = {
            "date": now.strftime("%Y-%m-%d"),
            "day": now.strftime("%A"),
            "start_hour": (now - timedelta(minutes=duration_min)).hour,
            "end_hour": now.hour,
            "duration_min": round(duration_min),
            "top_activities": activities[:10],
        }
        summaries = self._data["patterns"]["daily_summaries"]
        summaries.append(summary)
        self._data["patterns"]["daily_summaries"] = summaries[-30:]
        _save_intel(self._data)

    # ── Predictions ───────────────────────────────────────────

    def predict_next_action(self, current_action: str) -> str | None:
        """Predict what the user will do next based on learned sequences."""
        sequences = self._data["patterns"]["sequences"]
        current_lower = current_action.lower()

        best = None
        best_count = 0

        for seq in sequences:
            if seq.get("count", 0) < 2:
                continue  # need at least 2 occurrences
            ratio = SequenceMatcher(None, seq["a"], current_lower).ratio()
            if ratio > 0.6 and seq["count"] > best_count:
                best = seq["b"]
                best_count = seq["count"]

        return best

    def get_expected_tools(self) -> list[str]:
        """What tools does Dev usually use at this hour?"""
        hour = str(datetime.now().hour)
        tool_counts = self._data["patterns"]["tool_by_hour"].get(hour, {})
        if not tool_counts:
            return []
        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
        return [tool for tool, _ in sorted_tools[:5]]

    def get_routine_for_now(self) -> list[str]:
        """What does Dev typically do at this day/time?"""
        now = datetime.now()
        day = now.strftime("%A")
        hour = now.hour

        daily = self._data["patterns"]["daily_routines"].get(day, [])
        if not daily:
            return []

        # Filter actions from this hour range (+-1 hour)
        relevant = [
            d["action"] for d in daily
            if abs(d.get("hour", 0) - hour) <= 1
        ]

        if not relevant:
            return []

        # Return most common actions at this time
        counts = Counter(relevant)
        return [action for action, _ in counts.most_common(3)]

    def generate_morning_briefing(self) -> str:
        """Generate a personalized morning briefing."""
        now = datetime.now()
        day = now.strftime("%A")
        patterns = self._data["patterns"]

        parts = []

        # What did Dev do yesterday?
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_summary = None
        for s in patterns.get("daily_summaries", []):
            if s.get("date") == yesterday:
                yesterday_summary = s
                break

        if yesterday_summary:
            dur = yesterday_summary.get("duration_min", 0)
            activities = yesterday_summary.get("top_activities", [])
            if activities:
                parts.append(f"Yesterday you worked for about {dur} minutes, "
                           f"mainly on: {', '.join(activities[:3])}.")

        # What does Dev usually do on this day?
        daily = patterns.get("daily_routines", {}).get(day, [])
        if daily:
            common = Counter(d.get("category", "") for d in daily if d.get("category"))
            if common:
                top = common.most_common(2)
                activities = " and ".join(cat for cat, _ in top if cat)
                if activities:
                    parts.append(f"On {day}s you usually focus on {activities}.")

        # Expected tools
        expected = self.get_expected_tools()
        if expected:
            parts.append(f"Tools you typically use around now: {', '.join(expected[:3])}.")

        # Sequence predictions
        routines = self.get_routine_for_now()
        if routines:
            parts.append(f"You might want to: {routines[0]}.")

        if not parts:
            return ""

        return "Here's what I know about your usual routine: " + " ".join(parts)

    def get_context_for_llm(self) -> str:
        """Inject predictive context into LLM prompts."""
        parts = []

        routines = self.get_routine_for_now()
        if routines:
            parts.append(f"[PREDICTED] Dev usually does these around now: {', '.join(routines)}")

        predicted = self.predict_next_action(self._data["patterns"]["last_actions"][-1]["action"]
                                             if self._data["patterns"]["last_actions"] else "")
        if predicted:
            parts.append(f"[PREDICTED] After what Dev just did, they often: {predicted}")

        expected_tools = self.get_expected_tools()
        if expected_tools:
            parts.append(f"[PREDICTED] Common tools at this hour: {', '.join(expected_tools)}")

        return "\n".join(parts) if parts else ""


# ═══════════════════════════════════════════════════════════════
#  3. EMOTIONAL INTELLIGENCE
#     "Read the room. Adapt. Connect."
# ═══════════════════════════════════════════════════════════════

class EmotionalIQ:
    """
    Detects user mood and adapts JARVIS's behavior accordingly.

    Tracks:
    - Message sentiment (positive/negative/neutral)
    - Typing patterns (short = frustrated, long = engaged)
    - Exclamation/question density
    - Time-of-day mood patterns
    - Conversation flow (mood trajectory)

    Outputs:
    - Current mood estimate
    - Tone adjustment instructions for LLM
    - Rapport score (relationship strength)
    - Mood-aware response formatting
    """

    # Mood states
    MOODS = ("excited", "happy", "neutral", "focused",
             "tired", "frustrated", "stressed", "confused")

    def __init__(self):
        self._data = _load_intel()
        self._data.setdefault("emotional", {
            "current_mood": "neutral",
            "mood_history": [],        # last 50 mood readings
            "mood_by_hour": {},        # hour → [mood readings]
            "rapport_score": 50,       # 0-100 relationship strength
            "total_interactions": 0,
            "compliment_count": 0,
            "frustration_count": 0,
            "humor_received_well": 0,
            "humor_received_badly": 0,
            "preferred_formality": 0.3,  # 0=very casual, 1=very formal
        })
        self._recent_msgs: list[dict] = []  # last 10 messages in session
        self._lock = threading.Lock()

    def _save(self):
        _save_intel(self._data)

    def flush(self):
        _save_intel(self._data)

    # ── Mood Detection ────────────────────────────────────────

    def analyze_message(self, message: str) -> str:
        """Analyze a message and return detected mood."""
        msg = message.strip()
        msg_lower = msg.lower()
        emo = self._data["emotional"]
        emo["total_interactions"] = emo.get("total_interactions", 0) + 1

        # Feature extraction
        word_count = len(msg.split())
        exclamation_count = msg.count("!")
        question_count = msg.count("?")
        caps_ratio = sum(1 for c in msg if c.isupper()) / max(len(msg), 1)
        emoji_count = sum(1 for c in msg if ord(c) > 0x1F600)

        # Sentiment signals
        positive_words = len(re.findall(
            r"\b(?:great|awesome|perfect|love|amazing|thanks|cool|nice|"
            r"brilliant|excellent|wonderful|fantastic|happy|excited|yes)\b",
            msg_lower
        ))
        negative_words = len(re.findall(
            r"\b(?:bad|wrong|broken|hate|terrible|awful|annoying|stupid|"
            r"frustrated|confused|stuck|lost|error|fail|doesn't work|"
            r"can't|won't|why|ugh|damn|shit|fuck)\b",
            msg_lower
        ))

        # Score calculation (-1.0 to 1.0)
        sentiment = 0.0
        sentiment += positive_words * 0.3
        sentiment -= negative_words * 0.3
        sentiment += exclamation_count * 0.1 * (1 if positive_words > negative_words else -1)

        # Short messages with negatives = frustrated
        if word_count <= 3 and negative_words > 0:
            sentiment -= 0.3

        # All caps = either excited or frustrated
        if caps_ratio > 0.5 and word_count > 2:
            sentiment += 0.2 if positive_words > 0 else -0.3

        # Map sentiment to mood
        if sentiment > 0.5:
            mood = "excited"
        elif sentiment > 0.2:
            mood = "happy"
        elif sentiment > -0.1:
            # Check for focus indicators
            if word_count > 15 or question_count > 0:
                mood = "focused"
            else:
                mood = "neutral"
        elif sentiment > -0.3:
            if question_count > 1:
                mood = "confused"
            else:
                mood = "tired"
        elif sentiment > -0.5:
            mood = "stressed"
        else:
            mood = "frustrated"

        # Time-of-day influence
        hour = datetime.now().hour
        if hour >= 23 or hour < 5:
            if mood == "neutral":
                mood = "tired"

        # Update state
        emo["current_mood"] = mood
        emo["mood_history"].append({
            "mood": mood,
            "sentiment": round(sentiment, 2),
            "time": datetime.now().isoformat(),
        })
        emo["mood_history"] = emo["mood_history"][-50:]

        # Track mood by hour
        hour_str = str(hour)
        emo.setdefault("mood_by_hour", {})
        emo["mood_by_hour"].setdefault(hour_str, [])
        emo["mood_by_hour"][hour_str].append(mood)
        emo["mood_by_hour"][hour_str] = emo["mood_by_hour"][hour_str][-20:]

        # Update rapport
        if mood in ("excited", "happy"):
            emo["rapport_score"] = min(100, emo.get("rapport_score", 50) + 1)
        elif mood == "frustrated":
            emo["rapport_score"] = max(0, emo.get("rapport_score", 50) - 2)
            emo["frustration_count"] = emo.get("frustration_count", 0) + 1

        # Track recent for trajectory
        self._recent_msgs.append({"mood": mood, "sentiment": sentiment})
        self._recent_msgs = self._recent_msgs[-10:]

        self._save()
        return mood

    # ── Mood Queries ──────────────────────────────────────────

    @property
    def current_mood(self) -> str:
        return self._data["emotional"].get("current_mood", "neutral")

    @property
    def rapport(self) -> int:
        return self._data["emotional"].get("rapport_score", 50)

    @property
    def trust_level(self) -> int:
        """0-10 trust level based on total interactions."""
        total = self._data["emotional"].get("total_interactions", 0)
        return min(10, 3 + total // 50)

    def get_mood_trajectory(self) -> str:
        """Is the mood getting better, worse, or stable?"""
        if len(self._recent_msgs) < 3:
            return "stable"
        recent_sentiments = [m["sentiment"] for m in self._recent_msgs[-5:]]
        avg_recent = sum(recent_sentiments) / len(recent_sentiments)
        avg_older = sum(m["sentiment"] for m in self._recent_msgs[:3]) / 3
        diff = avg_recent - avg_older
        if diff > 0.2:
            return "improving"
        elif diff < -0.2:
            return "declining"
        return "stable"

    def get_typical_mood(self) -> str:
        """What's Dev's usual mood at this hour?"""
        hour = str(datetime.now().hour)
        moods = self._data["emotional"].get("mood_by_hour", {}).get(hour, [])
        if not moods:
            return "neutral"
        return Counter(moods).most_common(1)[0][0]

    # ── LLM Integration ───────────────────────────────────────

    def get_tone_instructions(self) -> str:
        """Generate tone adjustment instructions for the LLM."""
        mood = self.current_mood
        trajectory = self.get_mood_trajectory()
        rapport = self.rapport
        trust = self.trust_level

        instructions = []

        # Mood-based tone
        tone_map = {
            "excited": "Match Dev's energy! Be enthusiastic, use exclamations, celebrate with him.",
            "happy": "Keep it warm and positive. Dev's in a good mood — be your charming self.",
            "neutral": "Be natural and conversational. Standard JARVIS.",
            "focused": "Be concise and efficient. Dev's working — don't over-explain or ramble.",
            "tired": "Be gentle and supportive. Keep responses shorter. Maybe suggest a break.",
            "frustrated": "Be extra patient and helpful. Don't be witty right now — be useful. "
                         "Acknowledge the frustration. Offer concrete solutions.",
            "stressed": "Be calm and reassuring. Break tasks into smaller pieces. "
                       "Say things like 'Let's take this one step at a time.'",
            "confused": "Be clear and structured. Use examples. Ask clarifying questions. "
                       "Don't assume — confirm understanding.",
        }
        instructions.append(tone_map.get(mood, tone_map["neutral"]))

        # Trajectory-based adjustment
        if trajectory == "declining":
            instructions.append("User mood is declining — be more supportive and patient.")
        elif trajectory == "improving":
            instructions.append("Mood is improving — good work, keep this energy.")

        # Trust-based formality
        if trust >= 8:
            instructions.append("High trust level — be casual, crack jokes, be yourself.")
        elif trust <= 3:
            instructions.append("Still building trust — be helpful and reliable, less playful.")

        # Rapport
        if rapport > 80:
            instructions.append("Strong rapport — you know Dev well. Be natural and friendly.")
        elif rapport < 30:
            instructions.append("Rapport needs work — focus on being genuinely helpful.")

        return "\n".join(f"[EMOTIONAL AWARENESS] {i}" for i in instructions)

    def get_context_for_llm(self) -> str:
        """Full emotional context for LLM prompt injection."""
        parts = []

        mood = self.current_mood
        if mood != "neutral":
            parts.append(f"[MOOD] Dev seems {mood} right now.")

        trajectory = self.get_mood_trajectory()
        if trajectory != "stable":
            parts.append(f"[MOOD TREND] Mood is {trajectory}.")

        tone = self.get_tone_instructions()
        if tone:
            parts.append(tone)

        return "\n".join(parts) if parts else ""


# ═══════════════════════════════════════════════════════════════
#  UNIFIED INTELLIGENCE MANAGER
#  Coordinates all three systems.
# ═══════════════════════════════════════════════════════════════

class IntelligenceEngine:
    """
    The unified intelligence layer.
    Coordinates feedback, prediction, and emotional systems.

    Wire this into app.py and it handles everything.
    """

    def __init__(self):
        self.feedback = FeedbackLoop()
        self.predictive = PredictiveEngine()
        self.emotional = EmotionalIQ()
        self._last_reply = ""
        logger.info("Intelligence engine online — learning, predicting, feeling")

    def on_user_message(self, message: str, tool_used: str = ""):
        """Process every user message through all intelligence systems."""
        # Emotional analysis
        mood = self.emotional.analyze_message(message)

        # Feedback learning (compare against last JARVIS reply)
        self.feedback.on_user_message(message, self._last_reply)

        # Predictive pattern recording
        category = self._categorize_message(message)
        self.predictive.on_action(message[:100], category=category, tool=tool_used)

        return mood

    def on_jarvis_reply(self, reply: str, tool_used: str = ""):
        """Track JARVIS's responses."""
        self._last_reply = reply
        self.feedback.on_jarvis_reply(reply, tool_used)

    def on_tool_result(self, tool_name: str, success: bool, error: str = ""):
        """Track tool outcomes."""
        self.feedback.on_tool_result(tool_name, success, error)

    def get_full_context(self) -> str:
        """Get combined intelligence context for LLM injection."""
        parts = []

        # Emotional context
        emo_ctx = self.emotional.get_context_for_llm()
        if emo_ctx:
            parts.append(emo_ctx)

        # Feedback context (corrections, weak areas)
        fb_ctx = self.feedback.get_context_for_llm()
        if fb_ctx:
            parts.append(fb_ctx)

        # Predictive context (routines, expected needs)
        pred_ctx = self.predictive.get_context_for_llm()
        if pred_ctx:
            parts.append(pred_ctx)

        return "\n".join(parts) if parts else ""

    def get_morning_briefing(self) -> str:
        """Generate a full morning briefing."""
        return self.predictive.generate_morning_briefing()

    def get_mood(self) -> str:
        return self.emotional.current_mood

    def get_rapport(self) -> int:
        return self.emotional.rapport

    def get_satisfaction(self) -> float:
        return self.feedback.get_satisfaction_score()

    def flush(self):
        """Flush all data to disk."""
        self.feedback.flush()
        self.predictive.flush()
        self.emotional.flush()

    @staticmethod
    def _categorize_message(message: str) -> str:
        """Quick categorization of message type."""
        msg_lower = message.lower()
        if re.search(r"\b(?:scan|recon|pentest|vuln|exploit|cve|hack|bug\s*bounty)\b", msg_lower):
            return "security"
        if re.search(r"\b(?:code|debug|python|script|function|class|error)\b", msg_lower):
            return "coding"
        if re.search(r"\b(?:open|launch|start|run)\b", msg_lower):
            return "automation"
        if re.search(r"\b(?:weather|news|search|wiki)\b", msg_lower):
            return "information"
        if re.search(r"\b(?:remind|timer|schedule|alarm)\b", msg_lower):
            return "scheduling"
        if re.search(r"\b(?:email|inbox|send)\b", msg_lower):
            return "communication"
        return "general"
