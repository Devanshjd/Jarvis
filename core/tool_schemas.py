"""
J.A.R.V.I.S -- Tool Schema Registry (Single Source of Truth)

Every tool JARVIS can use is declared here -- once.  All other layers
(executor, capability_registry, Gemini voice, Electron IPC) derive
their registrations from this file.

Each schema follows Claude tool_use format with extra JARVIS metadata:
  - aliases:   old / alternate names that still route here
  - layer:     "python" | "electron" | "both"
  - category:  grouping for capability_registry
  - verify:    whether post-action screenshot verification is needed
"""

from __future__ import annotations

# =====================================================================
#  Tool schemas -- the CANONICAL registry
# =====================================================================

TOOL_SCHEMAS: list[dict] = [

    # ==================================================================
    #  MESSAGING & COMMUNICATION
    # ==================================================================
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
        "aliases": ["send_whatsapp", "send_telegram", "open_whatsapp_chat"],
        "layer": "python",
        "category": "communication",
        "verify": True,
    },
    {
        "name": "send_email",
        "description": "Send an email to someone. Examples: 'email John the report', 'send mail to boss'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Email body text."},
            },
            "required": ["to", "subject", "body"],
        },
        "aliases": [],
        "layer": "python",
        "category": "communication",
        "verify": False,
    },
    {
        "name": "check_inbox",
        "description": "Check email inbox for recent messages. Examples: 'check my email', 'any new mail?'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of recent emails to fetch. Default 5."},
            },
            "required": [],
        },
        "aliases": ["inbox"],
        "layer": "python",
        "category": "communication",
        "verify": False,
    },

    # ==================================================================
    #  APP CONTROL
    # ==================================================================
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
        "aliases": ["close_app"],
        "layer": "python",
        "category": "desktop",
        "verify": True,
    },
    {
        "name": "lock_screen",
        "description": "Lock the workstation. Examples: 'lock my computer', 'lock screen'.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "aliases": ["lock_system"],
        "layer": "python",
        "category": "desktop",
        "verify": False,
    },
    {
        "name": "set_volume",
        "description": "Set system volume level. Examples: 'set volume to 50', 'turn volume up', 'mute'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "description": "Volume level 0-100."},
            },
            "required": ["level"],
        },
        "aliases": [],
        "layer": "python",
        "category": "desktop",
        "verify": False,
    },

    # ==================================================================
    #  WEB SEARCH & INFO
    # ==================================================================
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
                "query": {"type": "string", "description": "The search query."},
                "platform": {
                    "type": "string",
                    "enum": ["google", "youtube", "github", "stackoverflow", "reddit", "spotify"],
                    "description": "Search platform. Default to google.",
                },
            },
            "required": ["query"],
        },
        "aliases": ["google_search"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
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
                "city": {"type": "string", "description": "City name. Default to user's location if not specified."},
            },
            "required": [],
        },
        "aliases": ["weather", "forecast"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_news",
        "description": "Get latest news headlines. Examples: 'what's the news', 'news about AI', 'latest headlines'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "News topic to search for."},
            },
            "required": [],
        },
        "aliases": ["news", "headlines"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_crypto",
        "description": "Get cryptocurrency price. Examples: 'bitcoin price', 'how much is ETH', 'crypto BTC'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coin": {"type": "string", "description": "Cryptocurrency name or symbol (e.g. bitcoin, ETH)."},
            },
            "required": ["coin"],
        },
        "aliases": ["crypto"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_wiki",
        "description": "Look up a topic on Wikipedia. Examples: 'wiki quantum computing', 'wikipedia AI'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to look up."},
            },
            "required": ["topic"],
        },
        "aliases": ["wikipedia"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_definition",
        "description": "Get the definition of a word. Examples: 'define ephemeral', 'what does laconic mean'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "word": {"type": "string", "description": "Word to define."},
            },
            "required": ["word"],
        },
        "aliases": ["define"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_translation",
        "description": "Translate text between languages. Examples: 'translate hello to Spanish'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to translate."},
                "langpair": {"type": "string", "description": "Language pair like 'en|es'. Default 'en|es'."},
            },
            "required": ["text"],
        },
        "aliases": ["translate", "translate_text"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_currency",
        "description": "Convert currency. Examples: '100 USD to INR', 'convert euros to dollars'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Amount to convert. Default 1."},
                "from": {"type": "string", "description": "Source currency code (e.g. USD)."},
                "to": {"type": "string", "description": "Target currency code (e.g. INR)."},
            },
            "required": ["from", "to"],
        },
        "aliases": ["currency"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_quote",
        "description": "Get an inspirational quote. Examples: 'give me a quote', 'inspire me'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": ["quote"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_joke",
        "description": "Get a random joke. Examples: 'tell me a joke', 'make me laugh'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": ["joke"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_fact",
        "description": "Get a random interesting fact. Examples: 'tell me a fact', 'random fact'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": ["fact"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_ip_info",
        "description": "Get info about an IP address. Examples: 'what's my IP', 'IP info for 8.8.8.8'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ip": {"type": "string", "description": "IP address. Empty for your own."},
            },
            "required": [],
        },
        "aliases": ["ip_info", "ip_geolocation"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "get_nasa",
        "description": "Get NASA Astronomy Picture of the Day. Examples: 'NASA picture', 'space photo'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": ["nasa"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },

    # ==================================================================
    #  SCREEN INTERACTION (AI Vision)
    # ==================================================================
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
                "description": {"type": "string", "description": "Description of the UI element to find."},
            },
            "required": ["description"],
        },
        "aliases": [],
        "layer": "python",
        "category": "screen",
        "verify": True,
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
                "description": {"type": "string", "description": "Description of the UI element to click."},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button. Default left."},
            },
            "required": ["description"],
        },
        "aliases": [],
        "layer": "python",
        "category": "screen",
        "verify": True,
    },
    {
        "name": "screen_type",
        "description": "Type text into a UI element on screen. Examples: 'type hello in the message box'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Description of the UI element to type into."},
                "text": {"type": "string", "description": "Text to type."},
            },
            "required": ["description", "text"],
        },
        "aliases": [],
        "layer": "python",
        "category": "screen",
        "verify": True,
    },
    {
        "name": "screen_read",
        "description": "Read text from a specific area on screen. Examples: 'read the error message', 'what does that say'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Description of the UI element to read."},
            },
            "required": ["description"],
        },
        "aliases": [],
        "layer": "python",
        "category": "screen",
        "verify": False,
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
                "question": {"type": "string", "description": "Specific question about what's on screen."},
            },
            "required": [],
        },
        "aliases": ["scan_screen"],
        "layer": "python",
        "category": "screen",
        "verify": False,
    },
    {
        "name": "read_screen_text",
        "description": (
            "Extract all readable text from the current screen using fast OCR (Tesseract). "
            "Use this when the user wants to READ text on screen — error messages, "
            "code, page contents — and doesn't need image reasoning. Faster (~750ms) "
            "and more accurate than vision LLM for pure text. "
            "Examples: 'read the error on my screen', 'what does the screen say', "
            "'capture the text I'm looking at', 'read this for me'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "aliases": ["ocr_screen", "screen_ocr"],
        "layer": "python",
        "category": "screen",
        "verify": False,
    },
    {
        "name": "speak_locally",
        "description": (
            "Speak text out loud using local Piper TTS — works offline, no internet "
            "needed, ~100ms latency. Use this for short confirmations or notifications "
            "when JARVIS wants to talk WITHOUT going through the Gemini Live voice "
            "channel. Examples: 'say that out loud', 'speak this', 'announce something'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to speak aloud."},
            },
            "required": ["text"],
        },
        "aliases": ["local_tts", "say_aloud"],
        "layer": "python",
        "category": "voice",
        "verify": False,
    },

    # ==================================================================
    #  MOUSE & KEYBOARD (Direct Input Control)
    # ==================================================================
    {
        "name": "mouse_click",
        "description": "Click at specific screen coordinates. Examples: 'click at 500, 300'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate."},
                "y": {"type": "integer", "description": "Y coordinate."},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button."},
                "clicks": {"type": "integer", "description": "Number of clicks. Default 1."},
            },
            "required": ["x", "y"],
        },
        "aliases": [],
        "layer": "python",
        "category": "input",
        "verify": True,
    },
    {
        "name": "mouse_move",
        "description": "Move mouse to specific coordinates. Examples: 'move mouse to 100, 200'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate."},
                "y": {"type": "integer", "description": "Y coordinate."},
                "duration": {"type": "number", "description": "Move duration in seconds. Default 0.5."},
            },
            "required": ["x", "y"],
        },
        "aliases": [],
        "layer": "python",
        "category": "input",
        "verify": False,
    },
    {
        "name": "mouse_scroll",
        "description": "Scroll the mouse wheel. Examples: 'scroll down', 'scroll up 5 clicks'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "integer", "description": "Scroll amount. Positive = up, negative = down."},
            },
            "required": ["amount"],
        },
        "aliases": [],
        "layer": "python",
        "category": "input",
        "verify": False,
    },
    {
        "name": "type_text",
        "description": "Type text at the current cursor position. Examples: 'type hello world'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type at cursor."},
                "interval": {"type": "number", "description": "Delay between keystrokes in seconds. Default 0.03."},
            },
            "required": ["text"],
        },
        "aliases": ["ghost_type"],
        "layer": "python",
        "category": "input",
        "verify": True,
    },
    {
        "name": "key_press",
        "description": "Press a keyboard key. Examples: 'press Enter', 'hit Escape', 'press Tab'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key to press (e.g. 'enter', 'escape', 'tab')."},
            },
            "required": ["key"],
        },
        "aliases": [],
        "layer": "python",
        "category": "input",
        "verify": False,
    },
    {
        "name": "key_combo",
        "description": "Press a keyboard shortcut. Examples: 'press Ctrl+C', 'Ctrl+Shift+T', 'Alt+F4'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keys": {"type": "string", "description": "Key combination (e.g. 'ctrl+c', 'alt+f4')."},
            },
            "required": ["keys"],
        },
        "aliases": [],
        "layer": "python",
        "category": "input",
        "verify": False,
    },
    {
        "name": "take_screenshot",
        "description": "Take a screenshot of the current screen. Examples: 'take a screenshot', 'capture screen'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": [],
        "layer": "python",
        "category": "screen",
        "verify": False,
    },

    # ==================================================================
    #  SYSTEM
    # ==================================================================
    {
        "name": "system_status",
        "description": (
            "Get full system health via the awareness engine -- CPU, RAM, battery, disk, active apps. "
            "Examples: 'how's my system', 'system health', 'what's running'."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": [],
        "layer": "python",
        "category": "system",
        "verify": False,
    },
    {
        "name": "system_info",
        "description": "Get basic system info -- CPU, RAM, disk. Examples: 'check CPU usage', 'how much RAM'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": [],
        "layer": "python",
        "category": "system",
        "verify": False,
    },
    {
        "name": "run_command",
        "description": "Run a terminal/shell command. Examples: 'run ipconfig', 'execute dir', 'run ping google.com'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute."},
            },
            "required": ["command"],
        },
        "aliases": ["run_terminal"],
        "layer": "python",
        "category": "system",
        "verify": False,
    },

    # ==================================================================
    #  REMINDERS & TIMERS
    # ==================================================================
    {
        "name": "set_reminder",
        "description": "Set a reminder. Examples: 'remind me to call Mom in 30 minutes', 'reminder at 3pm'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What to remind about."},
                "time": {"type": "string", "description": "When to remind (e.g. '30m', '2h', '3pm')."},
            },
            "required": ["message", "time"],
        },
        "aliases": [],
        "layer": "python",
        "category": "productivity",
        "verify": False,
    },
    {
        "name": "set_timer",
        "description": "Set a countdown timer. Examples: 'timer for 5 minutes', 'set a 10 minute timer'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "duration": {"type": "string", "description": "Timer duration (e.g. '5m', '1h', '30s')."},
            },
            "required": ["duration"],
        },
        "aliases": [],
        "layer": "python",
        "category": "productivity",
        "verify": False,
    },
    {
        "name": "list_reminders",
        "description": "List all active reminders. Examples: 'show my reminders', 'what reminders do I have'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": [],
        "layer": "python",
        "category": "productivity",
        "verify": False,
    },
    {
        "name": "remember",
        "description": "Save a fact to JARVIS memory. Examples: 'remember my WiFi password is xyz', 'remember this'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The fact or information to remember."},
            },
            "required": ["text"],
        },
        "aliases": ["vault_remember"],
        "layer": "python",
        "category": "productivity",
        "verify": False,
    },

    # ==================================================================
    #  CYBERSECURITY
    # ==================================================================
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
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "file_scan",
        "description": "Scan a file for malware or security issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to scan."},
            },
            "required": ["path"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "security_audit",
        "description": "Run a security audit on the local system. Examples: 'is my system safe', 'security check'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "phishing_detect",
        "description": "Analyze text or URL for phishing indicators. Examples: 'is this link phishing'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text or URL to analyze for phishing."},
            },
            "required": ["text"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
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
        "aliases": ["nmap_scan"],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "wifi_scan",
        "description": "Scan nearby WiFi networks. Examples: 'scan WiFi', 'what networks are nearby'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "net_scan",
        "description": "Scan the local network for connected devices.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": ["net_recon"],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "network_info",
        "description": "Get local network information -- IP, gateway, DNS, interfaces.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": ["net_info"],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "threat_lookup",
        "description": "Look up threat intelligence for an IP address.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ip": {"type": "string", "description": "IP address to look up."},
            },
            "required": ["ip"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },

    # ==================================================================
    #  PENTEST / BUG BOUNTY
    # ==================================================================
    {
        "name": "recon",
        "description": "Run full reconnaissance on a domain -- WHOIS, DNS, subdomains, tech stack.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain."},
            },
            "required": ["domain"],
        },
        "aliases": ["full_recon", "whois_lookup", "dns_lookup"],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "subdomain_enum",
        "description": "Enumerate subdomains for a target domain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain."},
            },
            "required": ["domain"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "tech_detect",
        "description": "Detect technologies used by a website.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL."},
            },
            "required": ["url"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "dir_fuzz",
        "description": "Fuzz directories on a web server to find hidden paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL."},
            },
            "required": ["url"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "google_dorks",
        "description": "Generate Google dork queries for a target domain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain."},
            },
            "required": ["domain"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "ssl_check",
        "description": "Check SSL/TLS certificate for a host.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Hostname to check."},
            },
            "required": ["host"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "cors_check",
        "description": "Check CORS misconfiguration on a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL."},
            },
            "required": ["url"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "xss_test",
        "description": "Test a URL for reflected XSS vulnerabilities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL with parameters."},
            },
            "required": ["url"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "sqli_test",
        "description": "Test a URL for SQL injection vulnerabilities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL with parameters."},
            },
            "required": ["url"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "open_redirect",
        "description": "Test for open redirect vulnerabilities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL."},
            },
            "required": ["url"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "header_audit",
        "description": "Deep audit of HTTP security headers for a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL."},
            },
            "required": ["url"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "wayback",
        "description": "Fetch historical URLs from the Wayback Machine for a domain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain."},
            },
            "required": ["domain"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "cve_search",
        "description": "Search for CVE vulnerabilities by keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Search keyword (e.g. 'apache', 'log4j')."},
            },
            "required": ["keyword"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "exploit_search",
        "description": "Search for known exploits by keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Search keyword."},
            },
            "required": ["keyword"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },

    # ==================================================================
    #  CHAIN EXECUTION
    # ==================================================================
    {
        "name": "pentest_chain",
        "description": "Run a full pentest chain on a domain -- recon, scan, test, report.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain."},
            },
            "required": ["domain"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },
    {
        "name": "quick_recon_chain",
        "description": "Run a quick reconnaissance chain on a domain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain."},
            },
            "required": ["domain"],
        },
        "aliases": [],
        "layer": "python",
        "category": "security",
        "verify": False,
    },

    # ==================================================================
    #  WEB RESEARCH
    # ==================================================================
    {
        "name": "web_research",
        "description": (
            "Deep web research on a topic -- searches, reads, and synthesizes. "
            "Examples: 'research the latest in AI security', "
            "'look up OWASP top 10 changes for 2025'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Research topic or question."},
                "depth": {"type": "string", "enum": ["quick", "deep"], "description": "Research depth. Default quick."},
            },
            "required": ["query"],
        },
        "aliases": ["research_topic"],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "research_cve",
        "description": "Research a specific CVE in detail -- description, severity, affected versions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cve_id": {"type": "string", "description": "CVE ID (e.g. CVE-2024-1234) or keyword."},
            },
            "required": ["cve_id"],
        },
        "aliases": [],
        "layer": "python",
        "category": "research",
        "verify": False,
    },
    {
        "name": "research_target",
        "description": "OSINT research on a target domain -- certificates, subdomains, intelligence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain."},
            },
            "required": ["domain"],
        },
        "aliases": [],
        "layer": "python",
        "category": "research",
        "verify": False,
    },

    # ==================================================================
    #  FILE OPERATIONS
    # ==================================================================
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
        "aliases": [],
        "layer": "electron",
        "category": "file",
        "verify": False,
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
        "aliases": [],
        "layer": "electron",
        "category": "file",
        "verify": False,
    },
    {
        "name": "find_files",
        "description": "Search for files by name pattern. Examples: 'find all .py files', 'find readme'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "File name pattern or glob (e.g. '*.py', 'readme*')."},
                "path": {"type": "string", "description": "Directory to search in. Default current dir."},
            },
            "required": ["pattern"],
        },
        "aliases": ["smart_file_search"],
        "layer": "python",
        "category": "file",
        "verify": False,
    },
    {
        "name": "organize_files",
        "description": "Auto-organize files in a folder by type. Examples: 'organize my Downloads'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Folder path to organize."},
            },
            "required": ["folder"],
        },
        "aliases": [],
        "layer": "python",
        "category": "file",
        "verify": False,
    },
    {
        "name": "disk_usage",
        "description": "Show disk usage and storage info. Examples: 'how much disk space', 'storage'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": [],
        "layer": "python",
        "category": "file",
        "verify": False,
    },
    {
        "name": "save_file",
        "description": "Save content to a new file on disk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "File name or path."},
                "content": {"type": "string", "description": "Content to save."},
            },
            "required": ["filename", "content"],
        },
        "aliases": [],
        "layer": "python",
        "category": "file",
        "verify": False,
    },

    # ==================================================================
    #  CODE & DEVELOPMENT
    # ==================================================================
    {
        "name": "run_python",
        "description": "Execute Python code. Examples: 'run this Python code', 'execute print(hello)'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute."},
            },
            "required": ["code"],
        },
        "aliases": [],
        "layer": "python",
        "category": "development",
        "verify": False,
    },
    {
        "name": "git_command",
        "description": "Run a git command. Examples: 'git status', 'git log', 'git diff'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subcmd": {"type": "string", "description": "Git subcommand and args (e.g. 'status', 'log --oneline')."},
            },
            "required": ["subcmd"],
        },
        "aliases": [],
        "layer": "python",
        "category": "development",
        "verify": False,
    },
    {
        "name": "pip_install",
        "description": "Install a Python package with pip. Examples: 'pip install requests'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package name to install."},
            },
            "required": ["package"],
        },
        "aliases": [],
        "layer": "python",
        "category": "development",
        "verify": False,
    },
    {
        "name": "build_project",
        "description": (
            "Build a project from a description using the dev agent. "
            "Examples: 'build a Flask API', 'create a React app', 'make a Discord bot'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "What to build -- a clear project description."},
                "language": {"type": "string", "description": "Programming language. Default python."},
            },
            "required": ["goal"],
        },
        "aliases": [],
        "layer": "python",
        "category": "development",
        "verify": False,
    },

    # ==================================================================
    #  SMART HOME
    # ==================================================================
    {
        "name": "control_lights",
        "description": "Control smart lights. Examples: 'turn on the lights', 'dim to 50%'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["on", "off", "dim", "brighten"], "description": "Light action."},
                "level": {"type": "string", "description": "Brightness level (for dim/brighten)."},
            },
            "required": ["action"],
        },
        "aliases": [],
        "layer": "python",
        "category": "smart_home",
        "verify": False,
    },
    {
        "name": "set_thermostat",
        "description": "Set thermostat temperature. Examples: 'set temp to 72', 'make it cooler'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "temp": {"type": "integer", "description": "Target temperature."},
            },
            "required": ["temp"],
        },
        "aliases": [],
        "layer": "python",
        "category": "smart_home",
        "verify": False,
    },
    {
        "name": "activate_scene",
        "description": "Activate a smart home scene. Examples: 'activate movie mode', 'bedtime scene'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scene": {"type": "string", "description": "Scene name to activate."},
            },
            "required": ["scene"],
        },
        "aliases": [],
        "layer": "python",
        "category": "smart_home",
        "verify": False,
    },
    {
        "name": "list_devices",
        "description": "List all smart home devices. Examples: 'what devices are connected'.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": [],
        "layer": "python",
        "category": "smart_home",
        "verify": False,
    },

    # ==================================================================
    #  SELF-MODIFICATION
    # ==================================================================
    {
        "name": "create_plugin",
        "description": "Create a new JARVIS plugin. Examples: 'create a Spotify plugin'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Plugin name."},
                "description": {"type": "string", "description": "What the plugin does."},
                "commands": {"type": "object", "description": "Command map {name: description}."},
                "code": {"type": "string", "description": "Plugin source code."},
            },
            "required": ["name"],
        },
        "aliases": ["add_feature"],
        "layer": "python",
        "category": "development",
        "verify": False,
    },
    {
        "name": "modify_file",
        "description": "Modify a file in the JARVIS project for self-improvement.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Relative path to the file."},
                "content": {"type": "string", "description": "New file content."},
                "reason": {"type": "string", "description": "Why this change is being made."},
            },
            "required": ["filepath", "content"],
        },
        "aliases": ["update_self", "repair_self"],
        "layer": "python",
        "category": "development",
        "verify": False,
    },
    {
        "name": "reload_plugin",
        "description": "Hot-reload a JARVIS plugin after modification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Plugin name to reload."},
            },
            "required": ["name"],
        },
        "aliases": [],
        "layer": "python",
        "category": "development",
        "verify": False,
    },
    {
        "name": "list_plugins",
        "description": "List all JARVIS plugins and their status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
        "aliases": ["manage_plugins"],
        "layer": "python",
        "category": "development",
        "verify": False,
    },
    {
        "name": "rollback_file",
        "description": "Rollback a file to its last backup.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "File path to rollback."},
            },
            "required": ["filepath"],
        },
        "aliases": [],
        "layer": "python",
        "category": "development",
        "verify": False,
    },

    # ==================================================================
    #  WEB AUTOMATION
    # ==================================================================
    {
        "name": "web_login",
        "description": "Automated web login via Selenium. Examples: 'log into university portal'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "site": {"type": "string", "description": "Site identifier (e.g. 'university')."},
                "url": {"type": "string", "description": "URL to navigate to."},
            },
            "required": [],
        },
        "aliases": [],
        "layer": "python",
        "category": "web_automation",
        "verify": True,
    },
    {
        "name": "web_navigate",
        "description": "Navigate to a URL in the automated browser.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to."},
            },
            "required": ["url"],
        },
        "aliases": ["browser_navigate"],
        "layer": "python",
        "category": "web_automation",
        "verify": True,
    },
    {
        "name": "web_click",
        "description": "Click an element on the current browser page by CSS selector.",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the element to click."},
            },
            "required": ["selector"],
        },
        "aliases": ["browser_click"],
        "layer": "python",
        "category": "web_automation",
        "verify": True,
    },

    # ==================================================================
    #  ELECTRON-ONLY TOOLS (execute in the desktop shell, not Python)
    # ==================================================================
    {
        "name": "snap_window",
        "description": "Snap the current window to a screen position. Examples: 'snap left', 'snap right'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "position": {"type": "string", "enum": ["left", "right", "maximize", "minimize"], "description": "Snap position."},
            },
            "required": ["position"],
        },
        "aliases": [],
        "layer": "electron",
        "category": "desktop",
        "verify": True,
    },
    {
        "name": "manage_file",
        "description": "Move, copy, rename, or delete a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["move", "copy", "rename", "delete"], "description": "File operation."},
                "source": {"type": "string", "description": "Source file path."},
                "destination": {"type": "string", "description": "Destination path (for move/copy/rename)."},
            },
            "required": ["action", "source"],
        },
        "aliases": [],
        "layer": "electron",
        "category": "file",
        "verify": False,
    },
    {
        "name": "jarvis_chat",
        "description": "Send a message to JARVIS backend for general AI processing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message text to process."},
            },
            "required": ["message"],
        },
        "aliases": [],
        "layer": "both",
        "category": "general",
        "verify": False,
    },
]


# =====================================================================
#  Lookup helpers
# =====================================================================

# Build alias -> canonical name map at import time
_ALIAS_MAP: dict[str, str] = {}
_SCHEMA_BY_NAME: dict[str, dict] = {}

def _rebuild_indexes() -> None:
    """Rebuild lookup indexes after schema list changes."""
    _ALIAS_MAP.clear()
    _SCHEMA_BY_NAME.clear()
    for schema in TOOL_SCHEMAS:
        canonical = schema["name"]
        _SCHEMA_BY_NAME[canonical] = schema
        for alias in schema.get("aliases", []):
            _ALIAS_MAP[alias] = canonical


_rebuild_indexes()


def resolve_tool_name(name: str) -> str:
    """Resolve an alias to its canonical tool name."""
    return _ALIAS_MAP.get(name, name)


def get_tool_names() -> list[str]:
    """Get list of all registered canonical tool names."""
    return [t["name"] for t in TOOL_SCHEMAS]


def get_schema_for_tool(name: str) -> dict | None:
    """Get schema for a tool by canonical name or alias."""
    resolved = resolve_tool_name(name)
    return _SCHEMA_BY_NAME.get(resolved)


def get_schemas_by_layer(layer: str) -> list[dict]:
    """Get all schemas for a specific layer ('python', 'electron', 'both')."""
    return [s for s in TOOL_SCHEMAS if s.get("layer") in (layer, "both")]


def get_schemas_by_category(category: str) -> list[dict]:
    """Get all schemas in a category."""
    return [s for s in TOOL_SCHEMAS if s.get("category") == category]


def get_tools_summary() -> str:
    """Get a compact summary of available tools for system prompt injection."""
    lines = []
    for t in TOOL_SCHEMAS:
        params = list(t["input_schema"].get("properties", {}).keys())
        params_str = f"({', '.join(params)})" if params else "()"
        desc = t["description"]
        if len(desc) > 80:
            desc = desc[:77] + "..."
        lines.append(f"  - {t['name']}{params_str}: {desc}")
    return "[AVAILABLE TOOLS]\n" + "\n".join(lines)


def get_all_names_and_aliases() -> dict[str, str]:
    """Return {name_or_alias: canonical_name} for every tool."""
    result = {}
    for schema in TOOL_SCHEMAS:
        canonical = schema["name"]
        result[canonical] = canonical
        for alias in schema.get("aliases", []):
            result[alias] = canonical
    return result
