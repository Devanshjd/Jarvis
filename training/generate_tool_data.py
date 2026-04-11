# JARVIS Tool-Calling Training Data Generator
# Creates synthetic training examples for the JARVIS tool router
# Output: JSONL with (user_input → tool_call) pairs

import json
import random
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent / "datasets" / "jarvis_tool_routing"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# All 43 JARVIS Tools with Training Examples
# ═══════════════════════════════════════════════════════════════

TOOL_EXAMPLES = {
    # ─── Core File Tools ───
    "read_file": {
        "description": "Read contents of a file",
        "params": {"file_path": "string"},
        "examples": [
            ("read the file config.json", {"file_path": "config.json"}),
            ("show me what's in main.py", {"file_path": "main.py"}),
            ("open and display README.md", {"file_path": "README.md"}),
            ("cat the contents of index.ts", {"file_path": "index.ts"}),
            ("what does package.json contain", {"file_path": "package.json"}),
            ("read my notes.txt file", {"file_path": "notes.txt"}),
            ("display the log file at logs/app.log", {"file_path": "logs/app.log"}),
            ("show the CSS file styles.css", {"file_path": "styles.css"}),
        ],
    },
    "write_file": {
        "description": "Write content to a file",
        "params": {"file_name": "string", "content": "string"},
        "examples": [
            ("create a file called hello.py with print hello world", {"file_name": "hello.py", "content": "print('hello world')"}),
            ("write a todo list to tasks.txt", {"file_name": "tasks.txt", "content": "1. Complete project\n2. Review code\n3. Deploy"}),
            ("save this code to script.js: console.log('hi')", {"file_name": "script.js", "content": "console.log('hi')"}),
            ("create notes.md with meeting notes heading", {"file_name": "notes.md", "content": "# Meeting Notes\n\n"}),
            ("make a new file config.yaml with name: jarvis", {"file_name": "config.yaml", "content": "name: jarvis"}),
        ],
    },
    "manage_file": {
        "description": "Copy, move, rename, or delete a file",
        "params": {"operation": "string", "source_path": "string", "dest_path": "string"},
        "examples": [
            ("delete the file temp.txt", {"operation": "delete", "source_path": "temp.txt", "dest_path": ""}),
            ("rename report.docx to final_report.docx", {"operation": "rename", "source_path": "report.docx", "dest_path": "final_report.docx"}),
            ("copy main.py to backup/main.py", {"operation": "copy", "source_path": "main.py", "dest_path": "backup/main.py"}),
            ("move old.log to archive/old.log", {"operation": "move", "source_path": "old.log", "dest_path": "archive/old.log"}),
            ("remove the temporary file cache.db", {"operation": "delete", "source_path": "cache.db", "dest_path": ""}),
        ],
    },
    "read_directory": {
        "description": "List contents of a directory",
        "params": {"dir_path": "string"},
        "examples": [
            ("list files in the current directory", {"dir_path": "."}),
            ("show me what's in the downloads folder", {"dir_path": "~/Downloads"}),
            ("list everything in src/", {"dir_path": "src/"}),
            ("what files are in the desktop folder", {"dir_path": "~/Desktop"}),
            ("show the documents directory", {"dir_path": "~/Documents"}),
        ],
    },
    "create_folder": {
        "description": "Create a new directory",
        "params": {"folder_path": "string"},
        "examples": [
            ("create a folder called projects", {"folder_path": "projects"}),
            ("make a new directory src/components", {"folder_path": "src/components"}),
            ("create the backup folder", {"folder_path": "backup"}),
            ("make a directory called output", {"folder_path": "output"}),
        ],
    },

    # ─── App Control ───
    "open_app": {
        "description": "Open an application",
        "params": {"app_name": "string"},
        "examples": [
            ("open chrome", {"app_name": "chrome"}),
            ("launch visual studio code", {"app_name": "code"}),
            ("open notepad", {"app_name": "notepad"}),
            ("start discord", {"app_name": "discord"}),
            ("open the calculator", {"app_name": "calc"}),
            ("launch spotify", {"app_name": "spotify"}),
            ("open file explorer", {"app_name": "explorer"}),
            ("start firefox browser", {"app_name": "firefox"}),
            ("open terminal", {"app_name": "cmd"}),
            ("launch task manager", {"app_name": "taskmgr"}),
        ],
    },
    "close_app": {
        "description": "Close an application",
        "params": {"app_name": "string"},
        "examples": [
            ("close chrome", {"app_name": "chrome"}),
            ("kill notepad", {"app_name": "notepad"}),
            ("close spotify", {"app_name": "spotify"}),
            ("shut down discord", {"app_name": "discord"}),
            ("exit firefox", {"app_name": "firefox"}),
        ],
    },

    # ─── Terminal ───
    "run_terminal": {
        "description": "Run a terminal/shell command",
        "params": {"command": "string"},
        "examples": [
            ("run pip install requests", {"command": "pip install requests"}),
            ("execute dir in the terminal", {"command": "dir"}),
            ("run npm install", {"command": "npm install"}),
            ("check the IP address", {"command": "ipconfig"}),
            ("show system information", {"command": "systeminfo"}),
            ("ping google.com", {"command": "ping google.com -n 4"}),
            ("check disk usage", {"command": "wmic logicaldisk get size,freespace,caption"}),
            ("list running processes", {"command": "tasklist"}),
            ("run git status", {"command": "git status"}),
            ("run python --version", {"command": "python --version"}),
        ],
    },

    # ─── Search ───
    "google_search": {
        "description": "Search Google for information",
        "params": {"query": "string"},
        "examples": [
            ("search for python tutorials", {"query": "python tutorials"}),
            ("google how to fix blue screen error", {"query": "how to fix blue screen error"}),
            ("look up latest cybersecurity news", {"query": "latest cybersecurity news 2026"}),
            ("search what is machine learning", {"query": "what is machine learning"}),
            ("find react component best practices", {"query": "react component best practices"}),
        ],
    },
    "smart_file_search": {
        "description": "Search for files on the computer",
        "params": {"query": "string"},
        "examples": [
            ("find all python files", {"query": "*.py"}),
            ("search for files named report", {"query": "report"}),
            ("find large files on my computer", {"query": "*.zip"}),
            ("locate the config file", {"query": "config"}),
        ],
    },

    # ─── Desktop Automation ───
    "ghost_type": {
        "description": "Type text automatically using keyboard",
        "params": {"text": "string"},
        "examples": [
            ("type hello world", {"text": "hello world"}),
            ("type my email address john@gmail.com", {"text": "john@gmail.com"}),
            ("auto type this message: meeting at 3pm", {"text": "meeting at 3pm"}),
        ],
    },
    "press_shortcut": {
        "description": "Press a keyboard shortcut",
        "params": {"key": "string", "modifiers": "string[]"},
        "examples": [
            ("press ctrl+c", {"key": "c", "modifiers": ["ctrl"]}),
            ("press ctrl+v to paste", {"key": "v", "modifiers": ["ctrl"]}),
            ("press alt+tab", {"key": "tab", "modifiers": ["alt"]}),
            ("press ctrl+s to save", {"key": "s", "modifiers": ["ctrl"]}),
            ("press ctrl+z to undo", {"key": "z", "modifiers": ["ctrl"]}),
            ("take a screenshot with print screen", {"key": "printscreen", "modifiers": []}),
            ("press ctrl+shift+escape", {"key": "escape", "modifiers": ["ctrl", "shift"]}),
            ("press windows+d to show desktop", {"key": "d", "modifiers": ["win"]}),
        ],
    },
    "take_screenshot": {
        "description": "Take a screenshot of the screen",
        "params": {},
        "examples": [
            ("take a screenshot", {}),
            ("capture my screen", {}),
            ("screenshot this", {}),
            ("take a screen capture", {}),
            ("grab a screenshot for me", {}),
        ],
    },
    "set_volume": {
        "description": "Set system volume",
        "params": {"level": "number"},
        "examples": [
            ("set volume to 50", {"level": 50}),
            ("turn volume to max", {"level": 100}),
            ("mute the volume", {"level": 0}),
            ("set volume to 75 percent", {"level": 75}),
            ("lower volume to 30", {"level": 30}),
        ],
    },

    # ─── Memory ───
    "save_core_memory": {
        "description": "Save a fact to long-term memory",
        "params": {"fact": "string"},
        "examples": [
            ("remember that my birthday is March 15", {"fact": "User's birthday is March 15"}),
            ("save that the wifi password is MyPass123", {"fact": "WiFi password is MyPass123"}),
            ("remember I prefer dark mode", {"fact": "User prefers dark mode"}),
            ("note that the project deadline is Friday", {"fact": "Project deadline is Friday"}),
            ("remember my favorite color is blue", {"fact": "User's favorite color is blue"}),
            ("save that the server IP is 10.0.0.5", {"fact": "Server IP address is 10.0.0.5"}),
        ],
    },
    "retrieve_core_memory": {
        "description": "Retrieve saved memories",
        "params": {},
        "examples": [
            ("what do you remember about me", {}),
            ("show my saved memories", {}),
            ("recall everything you know", {}),
            ("what facts have I told you", {}),
            ("check your memory", {}),
        ],
    },

    # ─── Project ───
    "open_project": {
        "description": "Open a project folder in VS Code",
        "params": {"folder_path": "string"},
        "examples": [
            ("open the jarvis project", {"folder_path": "D:/my pross/Jarvis"}),
            ("open my website project in VS Code", {"folder_path": "~/projects/website"}),
            ("open the desktop folder in code", {"folder_path": "~/Desktop"}),
        ],
    },

    # ─── Window Management ───
    "snap_window": {
        "description": "Snap a window to a screen position",
        "params": {"app_name": "string", "position": "string"},
        "examples": [
            ("snap chrome to the left", {"app_name": "chrome", "position": "left"}),
            ("move VS Code to the right half", {"app_name": "code", "position": "right"}),
            ("maximize notepad", {"app_name": "notepad", "position": "maximize"}),
            ("put discord on the left side", {"app_name": "discord", "position": "left"}),
        ],
    },
    "execute_macro": {
        "description": "Execute a saved macro",
        "params": {"macro_name": "string"},
        "examples": [
            ("run the morning routine macro", {"macro_name": "morning_routine"}),
            ("execute the dev setup macro", {"macro_name": "dev_setup"}),
            ("play the gaming macro", {"macro_name": "gaming"}),
        ],
    },
    "lock_system": {
        "description": "Lock the computer",
        "params": {},
        "examples": [
            ("lock my computer", {}),
            ("lock the screen", {}),
            ("lock the system", {}),
            ("lock it", {}),
        ],
    },

    # ─── Communications ───
    "send_whatsapp": {
        "description": "Send a WhatsApp message",
        "params": {"contact": "string", "message": "string"},
        "examples": [
            ("send a WhatsApp to Mom saying I'll be late", {"contact": "Mom", "message": "I'll be late"}),
            ("message John on WhatsApp that the meeting is at 3", {"contact": "John", "message": "The meeting is at 3"}),
            ("WhatsApp Dad saying happy birthday", {"contact": "Dad", "message": "Happy birthday!"}),
        ],
    },
    "open_whatsapp_chat": {
        "description": "Open a WhatsApp chat",
        "params": {"contact": "string"},
        "examples": [
            ("open WhatsApp chat with Mom", {"contact": "Mom"}),
            ("go to John's WhatsApp", {"contact": "John"}),
        ],
    },
    "send_telegram": {
        "description": "Send a Telegram message",
        "params": {"contact": "string", "message": "string"},
        "examples": [
            ("send a Telegram to Alex saying hi", {"contact": "Alex", "message": "Hi"}),
            ("telegram my group that I'm running late", {"contact": "my group", "message": "I'm running late"}),
        ],
    },
    "send_email": {
        "description": "Send an email",
        "params": {"to": "string", "subject": "string", "body": "string"},
        "examples": [
            ("email john@company.com about the project update", {"to": "john@company.com", "subject": "Project Update", "body": "Hi John, here's the project update."}),
            ("send an email to boss@work.com saying I'm sick today", {"to": "boss@work.com", "subject": "Sick Day", "body": "Hi, I'm not feeling well and need to take the day off."}),
        ],
    },

    # ─── Cyber Arsenal ───
    "port_scan": {
        "description": "Scan ports on a target host",
        "params": {"target": "string", "ports": "string"},
        "examples": [
            ("scan ports on 192.168.1.1", {"target": "192.168.1.1", "ports": "1-1024"}),
            ("check if port 80 is open on google.com", {"target": "google.com", "ports": "80"}),
            ("scan common ports on 10.0.0.1", {"target": "10.0.0.1", "ports": "22,80,443,8080"}),
            ("scan the local network gateway", {"target": "192.168.1.1", "ports": "1-100"}),
        ],
    },
    "nmap_scan": {
        "description": "Run an nmap scan on a target",
        "params": {"target": "string", "flags": "string"},
        "examples": [
            ("nmap scan 192.168.1.0/24", {"target": "192.168.1.0/24", "flags": "-sV"}),
            ("run a stealth scan on 10.0.0.5", {"target": "10.0.0.5", "flags": "-sS"}),
            ("scan for OS detection on the target", {"target": "192.168.1.1", "flags": "-O"}),
        ],
    },
    "whois_lookup": {
        "description": "Look up WHOIS information for a domain",
        "params": {"target": "string"},
        "examples": [
            ("whois google.com", {"target": "google.com"}),
            ("look up domain info for github.com", {"target": "github.com"}),
            ("who owns example.com", {"target": "example.com"}),
        ],
    },
    "dns_lookup": {
        "description": "Look up DNS records",
        "params": {"target": "string", "record_type": "string"},
        "examples": [
            ("DNS lookup for google.com", {"target": "google.com", "record_type": "A"}),
            ("check MX records for gmail.com", {"target": "gmail.com", "record_type": "MX"}),
            ("find the nameservers for example.com", {"target": "example.com", "record_type": "NS"}),
        ],
    },
    "subdomain_enum": {
        "description": "Enumerate subdomains of a domain",
        "params": {"domain": "string"},
        "examples": [
            ("find subdomains of example.com", {"domain": "example.com"}),
            ("enumerate subdomains for target.com", {"domain": "target.com"}),
            ("subdomain scan on google.com", {"domain": "google.com"}),
        ],
    },
    "hash_identify": {
        "description": "Identify the type of a hash",
        "params": {"hash": "string"},
        "examples": [
            ("identify this hash: 5d41402abc4b2a76b9719d911017c592", {"hash": "5d41402abc4b2a76b9719d911017c592"}),
            ("what type of hash is e3b0c44298fc1c149afbf4c8996fb924", {"hash": "e3b0c44298fc1c149afbf4c8996fb924"}),
            ("identify: $2b$12$LJ3m4ysDF.kmNMGV", {"hash": "$2b$12$LJ3m4ysDF.kmNMGV"}),
        ],
    },
    "ip_geolocation": {
        "description": "Get geolocation of an IP address",
        "params": {"ip": "string"},
        "examples": [
            ("locate IP 8.8.8.8", {"ip": "8.8.8.8"}),
            ("where is the IP 1.1.1.1 located", {"ip": "1.1.1.1"}),
            ("geolocate 192.168.1.1", {"ip": "192.168.1.1"}),
            ("find the location of IP 104.26.10.78", {"ip": "104.26.10.78"}),
        ],
    },

    # ─── RAG / Knowledge Base ───
    "ingest_document": {
        "description": "Ingest a document into the knowledge base",
        "params": {"file_path": "string"},
        "examples": [
            ("ingest the file research.pdf into knowledge base", {"file_path": "research.pdf"}),
            ("add notes.md to the knowledge base", {"file_path": "notes.md"}),
            ("learn from this document report.txt", {"file_path": "report.txt"}),
            ("import manual.pdf into your brain", {"file_path": "manual.pdf"}),
        ],
    },
    "semantic_search": {
        "description": "Search the knowledge base semantically",
        "params": {"query": "string", "top_k": "number"},
        "examples": [
            ("search knowledge base for network security", {"query": "network security", "top_k": 5}),
            ("find information about python decorators", {"query": "python decorators", "top_k": 5}),
            ("what do my documents say about machine learning", {"query": "machine learning", "top_k": 5}),
        ],
    },
    "list_documents": {
        "description": "List all documents in the knowledge base",
        "params": {},
        "examples": [
            ("what documents are in the knowledge base", {}),
            ("list all ingested documents", {}),
            ("show my knowledge base", {}),
        ],
    },

    # ─── Creative Tools ───
    "generate_image": {
        "description": "Generate an AI image from a text prompt",
        "params": {"prompt": "string", "width": "number", "height": "number"},
        "examples": [
            ("generate an image of a cyberpunk city", {"prompt": "a cyberpunk city at night with neon lights", "width": 1024, "height": 1024}),
            ("create a picture of a robot assistant", {"prompt": "a friendly robot assistant in a modern office", "width": 1024, "height": 1024}),
            ("make an image of a mountain landscape", {"prompt": "beautiful mountain landscape at sunset", "width": 1024, "height": 768}),
            ("draw a cat wearing a space suit", {"prompt": "a cat wearing a space suit floating in space", "width": 1024, "height": 1024}),
        ],
    },
    "analyze_code": {
        "description": "Analyze a code file for quality and security",
        "params": {"file_path": "string"},
        "examples": [
            ("analyze the code in main.py", {"file_path": "main.py"}),
            ("check index.ts for security issues", {"file_path": "index.ts"}),
            ("review the quality of app.js", {"file_path": "app.js"}),
            ("scan server.py for vulnerabilities", {"file_path": "server.py"}),
        ],
    },
    "summarize_text": {
        "description": "Summarize text or a file",
        "params": {"input": "string"},
        "examples": [
            ("summarize the file report.md", {"input": "report.md"}),
            ("give me a summary of notes.txt", {"input": "notes.txt"}),
            ("summarize this: AI is transforming the world of technology rapidly", {"input": "AI is transforming the world of technology rapidly"}),
        ],
    },
    "translate_text": {
        "description": "Translate text between languages",
        "params": {"text": "string", "target_lang": "string", "source_lang": "string"},
        "examples": [
            ("translate hello to spanish", {"text": "hello", "target_lang": "es", "source_lang": "en"}),
            ("translate good morning to french", {"text": "good morning", "target_lang": "fr", "source_lang": "en"}),
            ("say thank you in japanese", {"text": "thank you", "target_lang": "ja", "source_lang": "en"}),
            ("translate I love programming to german", {"text": "I love programming", "target_lang": "de", "source_lang": "en"}),
            ("how do you say goodbye in hindi", {"text": "goodbye", "target_lang": "hi", "source_lang": "en"}),
            ("translate welcome to arabic", {"text": "welcome", "target_lang": "ar", "source_lang": "en"}),
        ],
    },
}

# ─── Multi-Tool Chain Examples ───
MULTI_TOOL_CHAINS = [
    {
        "user_input": "open chrome and search for python tutorials",
        "tool_calls": [
            {"tool": "open_app", "params": {"app_name": "chrome"}},
            {"tool": "google_search", "params": {"query": "python tutorials"}}
        ]
    },
    {
        "user_input": "take a screenshot and save it to desktop",
        "tool_calls": [
            {"tool": "take_screenshot", "params": {}},
        ]
    },
    {
        "user_input": "create a new folder called project and create a file main.py inside it",
        "tool_calls": [
            {"tool": "create_folder", "params": {"folder_path": "project"}},
            {"tool": "write_file", "params": {"file_name": "project/main.py", "content": "# Main project file\n"}}
        ]
    },
    {
        "user_input": "scan the network and then check who owns the suspicious IP",
        "tool_calls": [
            {"tool": "port_scan", "params": {"target": "192.168.1.0/24", "ports": "1-100"}},
        ]
    },
    {
        "user_input": "read the config file and summarize it",
        "tool_calls": [
            {"tool": "read_file", "params": {"file_path": "config.json"}},
        ]
    },
    {
        "user_input": "lock my computer and remember that I left at 5pm",
        "tool_calls": [
            {"tool": "save_core_memory", "params": {"fact": "User left at 5pm"}},
            {"tool": "lock_system", "params": {}}
        ]
    },
]

# ─── Ambiguous / Reasoning Examples ───
REASONING_EXAMPLES = [
    {"input": "I need to back up my work", "reasoning": "User wants to copy files for safety. Use manage_file with copy operation.", "tool": "manage_file", "params": {"operation": "copy", "source_path": ".", "dest_path": "backup/"}},
    {"input": "is my website up?", "reasoning": "User wants to check if a server is responding. Port scan on port 80/443.", "tool": "port_scan", "params": {"target": "localhost", "ports": "80,443"}},
    {"input": "clean up my desktop", "reasoning": "User wants to organize files. List directory first to see what's there.", "tool": "read_directory", "params": {"dir_path": "~/Desktop"}},
    {"input": "I'm going to sleep", "reasoning": "User is done for the day. Lock the system.", "tool": "lock_system", "params": {}},
    {"input": "prepare my dev environment", "reasoning": "User wants their coding setup. Open VS Code.", "tool": "open_app", "params": {"app_name": "code"}},
    {"input": "what did I tell you yesterday", "reasoning": "User asking about past information. Retrieve memories.", "tool": "retrieve_core_memory", "params": {}},
    {"input": "check if something is wrong with the server", "reasoning": "User suspects server issues. Run a port scan to check services.", "tool": "port_scan", "params": {"target": "localhost", "ports": "22,80,443,3000,5000,8080"}},
    {"input": "help me study this paper", "reasoning": "User wants to learn from a document. Ingest it into knowledge base for semantic search.", "tool": "ingest_document", "params": {"file_path": "paper.pdf"}},
]


# ═══════════════════════════════════════════════════════════════
# Data Generation
# ═══════════════════════════════════════════════════════════════

def generate_training_data():
    """Generate complete training dataset."""
    training_data = []

    # 1. Direct tool-call examples
    for tool_name, tool_info in TOOL_EXAMPLES.items():
        for user_input, params in tool_info["examples"]:
            entry = {
                "instruction": user_input,
                "output": json.dumps({"tool": tool_name, "params": params}),
                "tool_name": tool_name,
                "type": "direct"
            }
            training_data.append(entry)

            # Augment with variations
            variations = augment_input(user_input, tool_name)
            for var in variations:
                training_data.append({
                    "instruction": var,
                    "output": json.dumps({"tool": tool_name, "params": params}),
                    "tool_name": tool_name,
                    "type": "augmented"
                })

    # 2. Multi-tool chain examples
    for chain in MULTI_TOOL_CHAINS:
        training_data.append({
            "instruction": chain["user_input"],
            "output": json.dumps({"tool_chain": chain["tool_calls"]}),
            "tool_name": "multi",
            "type": "chain"
        })

    # 3. Reasoning examples
    for ex in REASONING_EXAMPLES:
        training_data.append({
            "instruction": ex["input"],
            "output": json.dumps({
                "reasoning": ex["reasoning"],
                "tool": ex["tool"],
                "params": ex["params"]
            }),
            "tool_name": ex["tool"],
            "type": "reasoning"
        })

    return training_data


def augment_input(text: str, tool_name: str) -> list:
    """Create natural language variations of an input."""
    variations = []
    prefixes = [
        "hey jarvis ", "yo ", "can you ", "please ", "I need you to ",
        "jarvis ", "hey ", "could you ", "I want to ", ""
    ]
    suffixes = [
        "", " please", " for me", " right now", " quickly",
        " asap", ""
    ]

    # Generate 3 random variations
    for _ in range(3):
        prefix = random.choice(prefixes)
        suffix = random.choice(suffixes)
        var = prefix + text.lower() + suffix
        if var != text.lower():
            variations.append(var.strip())

    return variations[:3]


def format_for_training(data: list) -> list:
    """Format data as chat-template for SFT training."""
    formatted = []

    system_prompt = (
        "You are JARVIS, an AI desktop assistant. Your job is to understand the user's request "
        "and respond with the correct tool call as JSON. Available tools: " +
        ", ".join(TOOL_EXAMPLES.keys()) +
        ". Respond ONLY with a JSON object containing 'tool' and 'params' keys."
    )

    for entry in data:
        formatted.append({
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": entry["instruction"]},
                {"role": "assistant", "content": entry["output"]}
            ]
        })

    return formatted


def save_dataset(data: list, name: str):
    """Save dataset in multiple formats."""
    # JSONL format (for training)
    jsonl_path = OUTPUT_DIR / f"{name}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # JSON format (for inspection)
    json_path = OUTPUT_DIR / f"{name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Stats
    stats = {
        "total_entries": len(data),
        "generated_at": datetime.now().isoformat(),
        "tools_covered": len(TOOL_EXAMPLES),
        "types": {}
    }
    for entry in data:
        t = entry.get("type", "formatted")
        stats["types"][t] = stats["types"].get(t, 0) + 1

    stats_path = OUTPUT_DIR / f"{name}_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)

    return jsonl_path, len(data)


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  JARVIS Tool-Routing Training Data Generator")
    print("=" * 60)

    # Generate raw data
    print("\n1. Generating tool-call examples...")
    raw_data = generate_training_data()
    path, count = save_dataset(raw_data, "jarvis_tool_routing_raw")
    print(f"   Raw data: {count} entries -> {path}")

    # Format for chat-template training
    print("\n2. Formatting for SFT training...")
    formatted = format_for_training(raw_data)
    path, count = save_dataset(formatted, "jarvis_tool_routing_sft")
    print(f"   SFT data: {count} entries -> {path}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Total: {len(raw_data)} raw + {len(formatted)} formatted entries")
    print(f"  Tools covered: {len(TOOL_EXAMPLES)}")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"{'=' * 60}\n")
