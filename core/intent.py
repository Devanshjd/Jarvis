"""
J.A.R.V.I.S — Intent Engine
Natural language understanding that replaces command matching.

Tony doesn't type "/weather london". He says:
"What's it like outside?"
"Is it going to rain?"
"Jarvis, I need to work."
"That site looks off."
"Something feels wrong with my system."

This engine understands INTENT, not syntax.
"""

import re
import time
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("jarvis.intent")


@dataclass
class Intent:
    """Parsed user intent."""
    action: str                     # What to do
    category: str                   # Which domain
    confidence: float = 1.0         # How sure we are (0-1)
    entities: dict = field(default_factory=dict)  # Extracted info
    raw_text: str = ""              # Original input
    requires_ai: bool = False       # Needs LLM to fulfill
    negated: bool = False           # "don't", "stop", "cancel"
    is_followup: bool = False       # Continues previous context
    mood: str = "neutral"           # urgent, casual, frustrated, curious


class IntentEngine:
    """
    Understands natural language intent without requiring exact commands.

    Flow:
    1. Detect mood and urgency
    2. Check for negation/interruption
    3. Check for follow-up context
    4. Match intent patterns (broad, fuzzy)
    5. Extract entities (names, numbers, topics)
    6. Return structured Intent

    This is NOT command matching. It's understanding.
    """

    def __init__(self):
        self._last_intent: Optional[Intent] = None
        self._conversation_topic: str = ""
        self._build_patterns()

    def _build_patterns(self):
        """Build intent recognition patterns — broad and fuzzy."""

        # Negation / interruption — HIGHEST priority
        self._negation = re.compile(
            r"\b(don'?t|do\s*not|stop|cancel|never\s*mind|forget\s*(it|that)|"
            r"no\s+wait|actually\s+no|hold\s+on|abort|scratch\s+that|"
            r"not\s+that|undo)\b", re.I
        )

        # Interruption commands
        self._interruption = re.compile(
            r"^(stop|wait|pause|hold|cancel|quiet|shut\s*up|enough|ok\s+stop)\.?$", re.I
        )

        # Follow-up signals
        self._followup = re.compile(
            r"^(what\s+about|how\s+about|and\s+what|tell\s+me\s+more|"
            r"explain|why|go\s+on|continue|elaborate|more\s+detail|"
            r"what\s+else|anything\s+else|also|then\s+what|"
            r"yes|yeah|sure|ok|do\s+it|go\s+ahead|proceed|"
            r"that|this|it|the\s+same)\b", re.I
        )

        # ── Intent patterns by category ──────────────────

        self._intent_patterns = {

            # ── GREETING ─────────────────────────────────
            ("greeting", "greet"): re.compile(
                r"^(hey|hi|hello|yo|sup|what'?s\s+up|howdy|good\s+(morning|afternoon|evening|night)|"
                r"jarvis|wake\s+up|you\s+there|are\s+you\s+(awake|there|online|up))\b", re.I
            ),

            # ── IDENTITY ────────────────────────────────
            ("identity", "self_info"): re.compile(
                r"\b(who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do|"
                r"your\s+name|about\s+yourself|capabilities|what\s+do\s+you\s+know|"
                r"introduce\s+yourself)\b", re.I
            ),

            # ── SYSTEM STATUS ────────────────────────────
            ("system", "status"): re.compile(
                r"\b(how('?s| is)\s+(my\s+)?(system|machine|computer|pc|laptop)(\s+doing)?|"
                r"system\s+(status|health|info|check)|"
                r"(check\s+)?(cpu|ram|memory)\s*(usage)?|battery|disk\s+space|"
                r"am\s+i\s+secure|"
                r"how('?s| is)\s+(everything|things|it)\s*(running|going|looking|doing)?|"
                r"diagnostics|run\s+diagnostics)\b", re.I
            ),

            # ── WEATHER ──────────────────────────────────
            ("weather", "check"): re.compile(
                r"\b(weather|temperature|forecast|rain|snow|sunny|cloudy|"
                r"cold\s+outside|hot\s+outside|what'?s?\s+it\s+like\s+outside|"
                r"do\s+i\s+need\s+(an?\s+)?(umbrella|jacket|coat)|"
                r"is\s+it\s+(going\s+to\s+)?(rain|snow|be\s+(hot|cold|warm)))\b", re.I
            ),

            # ── WEB SEARCH ───────────────────────────────
            ("search", "web"): re.compile(
                r"\b(search(\s+for)?|google|look\s*up|find\s+(info|information|out)|"
                r"what\s+is|who\s+is|when\s+(did|was|is)|where\s+(is|was|are)|"
                r"how\s+(do|does|did|to|many|much|long|far))\b", re.I
            ),

            # ── OPEN APP / WORKSPACE ─────────────────────
            ("app", "open"): re.compile(
                r"\b(open|launch|start|run|fire\s+up|boot\s+up|bring\s+up|"
                r"i\s+need\s+to\s+work|work\s+setup|start\s+working|"
                r"get\s+me\s+set\s+up|my\s+(usual|normal)\s+setup|"
                r"open\s+(what\s+i|my)\s+usually?\s+use)\b", re.I
            ),

            # ── CLOSE / STOP APP ─────────────────────────
            ("app", "close"): re.compile(
                r"\b(close|quit|exit|kill|end|terminate|shut\s+down)\s+"
                r"(the\s+)?(app|application|program|window|that|this|it)\b", re.I
            ),

            # ── SCREEN ANALYSIS ──────────────────────────
            ("screen", "analyze"): re.compile(
                r"\b(what('?s|\s+is)\s+on\s+(my\s+)?screen|"
                r"what\s+am\s+i\s+(looking\s+at|seeing|doing)|"
                r"scan\s+(my\s+)?screen|look\s+at\s+(my\s+)?screen|"
                r"read\s+(my\s+)?screen|screen\s+scan|"
                r"analyze\s+(my\s+)?screen|what'?s?\s+this|"
                r"tell\s+me\s+what\s+(i'?m|you)\s+see(ing)?)\b", re.I
            ),

            # ── CYBERSECURITY ────────────────────────────
            ("security", "check"): re.compile(
                r"\b(is\s+(this|that|it)\s+(safe|secure|suspicious|legit|malicious|phishing)|"
                r"(is\s+)?(this|that)\s+(link|url|site|website|page)\s+(safe|suspicious|legit)|"
                r"check\s+(if|whether|this|that)\s*(is\s*)?(safe|suspicious|secure)|"
                r"looks?\s+(suspicious|sketchy|off|weird|dodgy|phishy)|"
                r"scan\s+(this|that|the|it)|url\s+scan|phishing|"
                r"something\s+(feels|looks|seems)\s+(off|wrong|suspicious)|"
                r"threat|malware|virus|hack|breach|vulnerability|"
                r"port\s+scan|network\s+scan|security\s+audit|"
                r"(is\s+)?(this|that)\s+safe)\b", re.I
            ),

            # ── EMAIL ────────────────────────────────────
            ("email", "check"): re.compile(
                r"\b(check\s+(my\s+)?(email|inbox|mail)|"
                r"any\s+(new\s+)?(emails?|mail|messages?)|"
                r"read\s+(my\s+)?email|unread\s+messages?|"
                r"send\s+(an?\s+)?email|write\s+(an?\s+)?email|"
                r"compose\s+(an?\s+)?(email|message)|"
                r"reply\s+to)\b", re.I
            ),

            # ── REMINDER / SCHEDULE ──────────────────────
            ("schedule", "remind"): re.compile(
                r"\b(remind\s+me|set\s+(a\s+)?reminder|"
                r"don'?t\s+(let\s+me\s+)?forget|i\s+need\s+to\s+remember|"
                r"wake\s+me|alarm|timer|schedule|"
                r"remind\s+me\s+(about\s+this|to|in|at|tomorrow)|"
                r"note\s+to\s+self|remember\s+this|"
                r"in\s+\d+\s*(min|hour|sec|h|m|s))", re.I
            ),

            # ── CODING / DEV ────────────────────────────
            ("code", "help"): re.compile(
                r"\b(write\s+(me\s+)?a?\s*(code|script|function|program|class)|"
                r"code\s+(this|that|it)|help\s+(me\s+)?(code|program|debug)|"
                r"fix\s+(this|the|my)\s*(code|bug|error|issue)|"
                r"explain\s+(this|the)\s*code|debug\s+(this|it)|"
                r"run\s+(this|the|my)\s*(code|script|python)|"
                r"what'?s?\s+wrong\s+with\s+(this|my)\s+code|"
                r"refactor|optimize|improve\s+(this|my)\s*code)\b", re.I
            ),

            # ── FILE OPERATIONS ──────────────────────────
            ("files", "manage"): re.compile(
                r"\b(find\s+(my\s+)?files?|organize\s+(my\s+)?files?|"
                r"where\s+is\s+(my|the)\s+\w+|"
                r"disk\s+usage|storage|how\s+much\s+space|"
                r"clean\s+up|delete\s+old|sort\s+my|"
                r"move\s+(this|that|the)|copy\s+(this|that|the)|"
                r"recent\s+files?|last\s+downloaded)\b", re.I
            ),

            # ── SMART HOME ───────────────────────────────
            ("home", "control"): re.compile(
                r"\b(lights?\s+(on|off|dim|bright)|turn\s+(on|off)\s+(the\s+)?lights?|"
                r"set\s+(the\s+)?temperature|thermostat|"
                r"it'?s?\s+(too\s+)?(hot|cold|warm|dark|bright)|"
                r"dim\s+the|movie\s+mode|night\s+mode|"
                r"activate\s+(scene|mode)|devices|smart\s+home)\b", re.I
            ),

            # ── REMEMBER / MEMORY ────────────────────────
            ("memory", "store"): re.compile(
                r"\b(remember\s+(that|this|my)|"
                r"don'?t\s+forget|save\s+this|note\s+that|"
                r"keep\s+in\s+mind|store\s+this|"
                r"what\s+do\s+you\s+(remember|know)\s+about|"
                r"do\s+you\s+remember|recall)\b", re.I
            ),

            # ── CREATIVE / WRITING ───────────────────────
            ("creative", "write"): re.compile(
                r"\b(write\s+(me\s+)?a?\s*(poem|story|essay|letter|message|song|email|text)|"
                r"compose|draft\s+(a|an)|help\s+me\s+write|"
                r"something\s+(romantic|funny|creative|professional)|"
                r"love\s+(letter|message|poem)|surprise\s+(her|him))\b", re.I
            ),

            # ── NEWS / INFO ──────────────────────────────
            ("info", "news"): re.compile(
                r"\b(news|headlines|what'?s?\s+happening|"
                r"current\s+events|latest\s+on|"
                r"tell\s+me\s+about|brief\s+me|"
                r"crypto|bitcoin|stock|market)\b", re.I
            ),

            # ── MOOD / PERSONAL ──────────────────────────
            ("personal", "chat"): re.compile(
                r"\b(i'?m?\s+(bored|tired|stressed|sad|happy|excited|anxious|frustrated|angry)|"
                r"how\s+are\s+you|tell\s+me\s+a\s+joke|"
                r"make\s+me\s+(laugh|smile|feel\s+better)|"
                r"i\s+need\s+(motivation|help|advice|a\s+break)|"
                r"cheer\s+me\s+up|talk\s+to\s+me|"
                r"what\s+should\s+i\s+do)\b", re.I
            ),

            # ── CONTINUE / RESUME ────────────────────────
            ("context", "resume"): re.compile(
                r"\b(continue\s+(where|what|from)|pick\s+up\s+where|"
                r"what\s+was\s+i\s+doing|resume|get\s+back\s+to|"
                r"where\s+were\s+we|last\s+time|"
                r"what\s+were\s+we\s+(working|talking)\s+(on|about))\b", re.I
            ),
        }

        # Entity extraction patterns
        self._entity_patterns = {
            "time": re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", re.I),
            "duration": re.compile(r"\b(\d+)\s*(min(?:ute)?s?|hours?|h|m|sec(?:ond)?s?|s)\b", re.I),
            "url": re.compile(r"(https?://\S+)", re.I),
            "email": re.compile(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", re.I),
            "filepath": re.compile(r"([A-Z]:\\[\w\\. -]+|\~/[\w/. -]+|/[\w/. -]+)", re.I),
            "app_name": re.compile(
                r"\b(chrome|firefox|edge|brave|vscode|code|terminal|cmd|"
                r"notepad|calculator|spotify|discord|slack|teams|"
                r"word|excel|powerpoint|explorer|obs|telegram|whatsapp)\b", re.I
            ),
            "city": re.compile(
                r"\b(?:in|for|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
            ),
        }

    # ══════════════════════════════════════════════════════════
    # MAIN PARSE
    # ══════════════════════════════════════════════════════════

    def parse(self, text: str, context: list = None) -> Intent:
        """
        Parse natural language into structured intent.

        Args:
            text: Raw user input
            context: Recent conversation messages (for follow-up detection)

        Returns:
            Intent with action, category, entities, and metadata
        """
        text = text.strip()
        if not text:
            return Intent(action="none", category="empty", raw_text=text)

        # 1. Check for interruption
        if self._interruption.match(text):
            return Intent(
                action="interrupt", category="control",
                raw_text=text, confidence=1.0,
            )

        # 2. Detect negation
        negated = bool(self._negation.search(text))

        # 3. Detect mood
        mood = self._detect_mood(text)

        # 4. Check for follow-up
        is_followup = bool(self._followup.match(text))
        if is_followup and self._last_intent:
            # Short follow-ups inherit the previous category
            if len(text.split()) <= 4:
                intent = Intent(
                    action=self._last_intent.action,
                    category=self._last_intent.category,
                    raw_text=text,
                    is_followup=True,
                    negated=negated,
                    mood=mood,
                    requires_ai=True,
                    confidence=0.7,
                )
                return intent

        # 5. Match intent patterns
        best_match = None
        best_confidence = 0.0

        # Priority order — earlier matches win on ties
        priority_order = [
            "greeting", "identity", "system", "schedule",
            "screen", "security", "weather", "code",
            "app", "email", "files", "home", "memory",
            "creative", "info", "personal", "context", "search",
        ]

        for (category, action), pattern in self._intent_patterns.items():
            match = pattern.search(text)
            if match:
                match_len = match.end() - match.start()
                confidence = min(match_len / max(len(text), 1) + 0.5, 1.0)

                # Use match position — earlier matches in text are more likely the intent
                match_pos = match.start()

                # Priority boost for categories higher in the list
                cat_idx = priority_order.index(category) if category in priority_order else 99

                # Score = confidence + position bonus + priority bonus
                score = confidence + (1.0 - match_pos / max(len(text), 1)) * 0.1
                best_score = best_confidence + 0.1 if best_match else 0

                if best_match:
                    existing_idx = priority_order.index(best_match[0]) if best_match[0] in priority_order else 99
                    # If same confidence, prefer earlier in priority order
                    if abs(confidence - best_confidence) < 0.15 and cat_idx < existing_idx:
                        score += 0.2

                if score > best_score or best_match is None:
                    best_confidence = confidence
                    best_match = (category, action)

        # 6. Extract entities
        entities = self._extract_entities(text)

        # 7. Build intent
        if best_match:
            category, action = best_match

            # If negated, adjust the action
            if negated:
                action = f"cancel_{action}"

            intent = Intent(
                action=action,
                category=category,
                confidence=best_confidence,
                entities=entities,
                raw_text=text,
                negated=negated,
                is_followup=is_followup,
                mood=mood,
                requires_ai=category in (
                    "creative", "code", "personal", "context",
                ),
            )
        else:
            # No pattern matched — requires AI reasoning
            intent = Intent(
                action="converse",
                category="general",
                confidence=0.3,
                entities=entities,
                raw_text=text,
                negated=negated,
                is_followup=is_followup,
                mood=mood,
                requires_ai=True,
            )

        self._last_intent = intent
        return intent

    def _detect_mood(self, text: str) -> str:
        """Detect the emotional tone of the message."""
        text_lower = text.lower()

        if any(w in text_lower for w in ["urgent", "emergency", "asap", "now", "hurry", "quick"]):
            return "urgent"
        if any(w in text_lower for w in ["please", "could you", "would you", "mind"]):
            return "polite"
        if any(w in text_lower for w in ["wtf", "damn", "broken", "stupid", "hate", "ugh"]):
            return "frustrated"
        if "?" in text and any(w in text_lower for w in ["why", "how", "what", "when"]):
            return "curious"
        if any(w in text_lower for w in ["thanks", "perfect", "great", "awesome", "nice"]):
            return "positive"
        if len(text.split()) <= 3:
            return "casual"

        return "neutral"

    def _extract_entities(self, text: str) -> dict:
        """Extract structured entities from text."""
        entities = {}

        for name, pattern in self._entity_patterns.items():
            matches = pattern.findall(text)
            if matches:
                if name == "duration" and matches:
                    # Parse duration into seconds
                    num, unit = matches[0]
                    multiplier = {"s": 1, "sec": 1, "second": 1, "seconds": 1,
                                  "m": 60, "min": 60, "minute": 60, "minutes": 60,
                                  "h": 3600, "hour": 3600, "hours": 3600}
                    entities["duration_seconds"] = int(num) * multiplier.get(unit.lower().rstrip("s"), 60)
                    entities["duration_raw"] = f"{num} {unit}"
                else:
                    entities[name] = matches[0] if len(matches) == 1 else matches

        return entities

    # ══════════════════════════════════════════════════════════
    # INTENT → ROUTE MAPPING
    # ══════════════════════════════════════════════════════════

    def get_route(self, intent: Intent) -> dict:
        """
        Map an intent to execution instructions.
        Returns a dict with routing info for the orchestrator.
        """
        route = {
            "pipeline": "ai",       # default to AI
            "tool": None,
            "tool_args": {},
            "fast_response": None,  # If set, skip AI entirely
            "mode_hint": None,      # Suggest a mode switch
            "context_inject": None, # Extra context for LLM
        }

        cat = intent.category
        action = intent.action

        # ── Greetings — instant, no AI ────────────────
        if cat == "greeting":
            route["pipeline"] = "instant"
            # Fast response will be generated by presence engine
            return route

        # ── System status — local only ────────────────
        if cat == "system":
            route["pipeline"] = "local"
            route["tool"] = "system_status"
            return route

        # ── Weather ───────────────────────────────────
        if cat == "weather":
            route["pipeline"] = "tool"
            route["tool"] = "get_weather"
            route["tool_args"] = {"city": intent.entities.get("city", "")}
            return route

        # ── Screen analysis ───────────────────────────
        if cat == "screen":
            route["pipeline"] = "vision"
            route["mode_hint"] = "Screen"
            return route

        # ── Security ──────────────────────────────────
        if cat == "security":
            route["pipeline"] = "tool"
            route["mode_hint"] = "Cyber"
            url = intent.entities.get("url")
            if url:
                route["tool"] = "url_scan"
                route["tool_args"] = {"url": url}
            else:
                route["tool"] = "security_audit"
            return route

        # ── Open app ──────────────────────────────────
        if cat == "app" and action == "open":
            route["pipeline"] = "tool"
            app_name = intent.entities.get("app_name")
            if app_name:
                route["tool"] = "open_app"
                route["tool_args"] = {"app": app_name}
            else:
                route["pipeline"] = "ai"  # Let AI figure out what to open
            return route

        # ── Email ─────────────────────────────────────
        if cat == "email":
            route["pipeline"] = "tool"
            if "send" in action or "compose" in intent.raw_text.lower():
                route["tool"] = "send_email"
            else:
                route["tool"] = "check_inbox"
            return route

        # ── Schedule / Reminders ──────────────────────
        if cat == "schedule":
            route["pipeline"] = "tool"
            route["tool"] = "set_reminder"
            route["tool_args"] = {
                "duration": intent.entities.get("duration_raw", ""),
                "seconds": intent.entities.get("duration_seconds", 0),
            }
            return route

        # ── Code ──────────────────────────────────────
        if cat == "code":
            route["pipeline"] = "ai"
            route["mode_hint"] = "Code/Dev"
            return route

        # ── Files ─────────────────────────────────────
        if cat == "files":
            route["pipeline"] = "tool"
            route["tool"] = "find_files"
            return route

        # ── Smart home ────────────────────────────────
        if cat == "home":
            route["pipeline"] = "tool"
            route["tool"] = "control_lights"
            return route

        # ── News / Info ───────────────────────────────
        if cat == "info":
            route["pipeline"] = "tool"
            if any(w in intent.raw_text.lower() for w in ["crypto", "bitcoin"]):
                route["tool"] = "get_crypto"
            else:
                route["tool"] = "get_news"
            return route

        # ── Memory ────────────────────────────────────
        if cat == "memory":
            route["pipeline"] = "local"
            route["tool"] = "memory_recall"
            return route

        # ── Creative / Personal / General → AI ────────
        route["pipeline"] = "ai"
        return route

    # ══════════════════════════════════════════════════════════
    # CONTEXT
    # ══════════════════════════════════════════════════════════

    def get_conversation_context(self) -> str:
        """Get intent-aware context string for LLM."""
        if not self._last_intent:
            return ""

        parts = []
        li = self._last_intent

        if li.mood != "neutral":
            parts.append(f"User mood: {li.mood}")
        if li.is_followup:
            parts.append(f"This is a follow-up to: {li.category}/{li.action}")
        if li.negated:
            parts.append("User expressed negation — they do NOT want the mentioned action")

        return " | ".join(parts) if parts else ""
