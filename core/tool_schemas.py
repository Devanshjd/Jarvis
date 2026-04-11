"""
J.A.R.V.I.S — Tool Schema Registry
Structured tool declarations for AI-driven tool selection.

Instead of 150+ regex patterns trying to guess which tool to use,
we declare tools as structured schemas and let the AI model pick
the right one with proper arguments extracted from natural language.

This is the IRIS-AI pattern: tools as function declarations that the
AI model can call directly. Much more reliable than regex for:
- "tell Meet I'm coming on WhatsApp"
- "can you send a text"
- "message him saying I'll be late"

The AI understands intent, not pattern matching.
"""

# ═══════════════════════════════════════════════════════════
# Tool schemas in Claude tool_use format
# ═══════════════════════════════════════════════════════════

TOOL_SCHEMAS = [
    # ── Messaging ──────────────────────────────────────────
    {
        "name": "send_msg",
        "description": (
            "Send a text message to someone via a messaging app. "
            "Use when user wants to text, message, DM, or tell someone something "
            "on WhatsApp, Telegram, Instagram, or Discord. "
            "Examples: 'text Meet on WhatsApp that I am coming', "
            "'tell Aryan I'll be late', 'send a WhatsApp to Meet', "
            "'message him saying hello', 'DM John on Discord hey bro'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact": {
                    "type": "string",
                    "description": "Name of the person to message. Ask if not provided.",
                },
                "platform": {
                    "type": "string",
                    "enum": ["whatsapp", "telegram", "instagram", "discord"],
                    "description": "Messaging platform. Default to whatsapp if not specified.",
                },
                "message": {
                    "type": "string",
                    "description": "The message text to send. Ask if not provided.",
                },
            },
            "required": ["contact", "platform", "message"],
        },
    },

    # ── App Control ────────────────────────────────────────
    {
        "name": "open_app",
        "description": (
            "Open or launch an application on the computer. "
            "Examples: 'open Chrome', 'launch WhatsApp', 'start VS Code', "
            "'open the calculator', 'run Spotify'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app": {
                    "type": "string",
                    "description": "Name of the application to open.",
                },
            },
            "required": ["app"],
        },
    },

    # ── Web Search ─────────────────────────────────────────
    {
        "name": "web_search",
        "description": (
            "Search the web for information. "
            "Examples: 'search for Python tutorials', 'Google how to fix CORS', "
            "'look up latest CVEs', 'find React documentation', "
            "'search YouTube for cooking videos', 'search on GitHub for FastAPI'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "platform": {
                    "type": "string",
                    "enum": ["google", "youtube", "github", "stackoverflow", "reddit", "spotify"],
                    "description": "Search platform. Default to google.",
                },
            },
            "required": ["query"],
        },
    },

    # ── Weather ────────────────────────────────────────────
    {
        "name": "get_weather",
        "description": (
            "Get current weather for a city. "
            "Examples: 'what's the weather', 'is it going to rain', "
            "'weather in London', 'how's the weather outside'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name. Default to user's location if not specified.",
                },
            },
            "required": [],
        },
    },

    # ── System Status ──────────────────────────────────────
    {
        "name": "system_status",
        "description": (
            "Get system health info — CPU, RAM, battery, disk usage. "
            "Examples: 'how's my system', 'check CPU usage', "
            "'system health', 'how much RAM am I using'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ── Screen Interaction ─────────────────────────────────
    {
        "name": "screen_find",
        "description": (
            "Find a UI element on screen using AI vision. "
            "Examples: 'find the send button', 'where is the search bar', "
            "'locate the message input box'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Description of the UI element to find.",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "screen_click",
        "description": (
            "Click on a UI element on screen using AI vision. "
            "Examples: 'click the send button', 'click on Meet's chat', "
            "'press the call button'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Description of the UI element to click.",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "screen_type",
        "description": (
            "Type text into a UI element on screen. "
            "Examples: 'type hello in the message box', "
            "'type Meet in the search bar'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Description of the UI element to type into.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type.",
                },
            },
            "required": ["description", "text"],
        },
    },

    # ── Mouse & Keyboard ──────────────────────────────────
    {
        "name": "type_text",
        "description": (
            "Type text at the current cursor position. "
            "Examples: 'type hello world', 'type my email address'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to type at cursor.",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "key_press",
        "description": (
            "Press a keyboard key or shortcut. "
            "Examples: 'press Enter', 'press Ctrl+C', 'hit Escape', 'press Tab'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key or shortcut to press (e.g. 'enter', 'ctrl+c', 'escape').",
                },
            },
            "required": ["key"],
        },
    },

    # ── Screenshot / Screen Scan ───────────────────────────
    {
        "name": "take_screenshot",
        "description": (
            "Take a screenshot of the current screen. "
            "Examples: 'take a screenshot', 'capture my screen', 'screenshot'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "screen_scan",
        "description": (
            "Scan and analyze the current screen content with AI vision. "
            "Examples: 'what's on my screen', 'scan my screen', "
            "'can you see this', 'look at my screen'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Specific question about what's on screen.",
                },
            },
            "required": [],
        },
    },

    # ── Reminders & Timers ─────────────────────────────────
    {
        "name": "set_reminder",
        "description": (
            "Set a reminder for later. "
            "Examples: 'remind me to call Mom in 30 minutes', "
            "'set a reminder for the meeting at 3pm'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "What to remind about.",
                },
                "time": {
                    "type": "string",
                    "description": "When to remind (e.g. '30m', '2h', '3pm').",
                },
            },
            "required": ["message", "time"],
        },
    },
    {
        "name": "set_timer",
        "description": (
            "Set a countdown timer. "
            "Examples: 'set a timer for 5 minutes', 'timer 10 minutes'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "duration": {
                    "type": "string",
                    "description": "Timer duration (e.g. '5m', '1h', '30s').",
                },
            },
            "required": ["duration"],
        },
    },

    # ── Volume ─────────────────────────────────────────────
    {
        "name": "set_volume",
        "description": (
            "Set system volume level. "
            "Examples: 'set volume to 50', 'turn volume up', 'mute'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Volume level 0-100.",
                },
            },
            "required": ["level"],
        },
    },

    # ── Cybersecurity ──────────────────────────────────────
    {
        "name": "url_scan",
        "description": "Scan a URL for security issues, phishing indicators, and threats.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to scan."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "port_scan",
        "description": "Scan a host for open ports and running services.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Hostname or IP to scan."},
            },
            "required": ["host"],
        },
    },
    {
        "name": "recon",
        "description": "Run full reconnaissance on a domain — WHOIS, DNS, subdomains, tech stack.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain."},
            },
            "required": ["domain"],
        },
    },

    # ── File Operations ────────────────────────────────────
    {
        "name": "read_file",
        "description": "Read the contents of a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file (create or overwrite).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write."},
                "content": {"type": "string", "description": "Content to write."},
            },
            "required": ["path", "content"],
        },
    },

    # ── Web Research ───────────────────────────────────────
    {
        "name": "web_research",
        "description": (
            "Deep web research on a topic — searches, reads, and synthesizes. "
            "Examples: 'research the latest in AI security', "
            "'look up OWASP top 10 changes for 2025'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Research topic or question."},
            },
            "required": ["query"],
        },
    },
]


def get_tool_names() -> list[str]:
    """Get list of all registered tool names."""
    return [t["name"] for t in TOOL_SCHEMAS]


def get_schema_for_tool(name: str) -> dict | None:
    """Get schema for a specific tool."""
    for t in TOOL_SCHEMAS:
        if t["name"] == name:
            return t
    return None


def get_tools_summary() -> str:
    """Get a compact summary of available tools for system prompt injection."""
    lines = []
    for t in TOOL_SCHEMAS:
        params = list(t["input_schema"].get("properties", {}).keys())
        params_str = f"({', '.join(params)})" if params else "()"
        lines.append(f"  - {t['name']}{params_str}: {t['description'][:80]}")
    return "[AVAILABLE TOOLS]\n" + "\n".join(lines)
