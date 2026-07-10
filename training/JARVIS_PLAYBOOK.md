# JARVIS Playbook — How to Handle Situations

Auto-generated. How JARVIS should use its tools + how to think.


## Situation → Tool routing


### app_control

- **open an application** → `open_app` — Use open_app with the app name. Works for notepad, calculator, chrome, paint, etc.

### file_ops

- **create a folder** → `create_folder` — Use create_folder (NOT build_project — that's for code). Default location is Desktop.
- **create a Word document** → `write_docx` — Use write_docx for real Word files (NOT write_file, which makes plain text/markdown).
- **create a spreadsheet** → `write_xlsx` — Use write_xlsx for real Excel files with proper cells.
- **find files** → `find_files` — Use find_files with a name pattern. Not a web search.

### math

- **compute math** → `calculator_plan` — Math goes to the deterministic calculator planner — parse the expression in code, press exact keys. Never let the LLM guess operators (it confuses times/plus).

### memory

- **remember something** → `remember` — Use remember to store a fact. (Memory is also auto-extracted from conversation.)

### screen

- **read text on screen** → `read_screen_text` — Use read_screen_text (Tesseract OCR) — fast, accurate for pure text. NEVER route to send_msg.
- **describe the screen** → `screen_scan` — Use screen_scan (vision LLM) when the user wants understanding/reasoning about the screen, not just raw text.
- **take a screenshot** → `take_screenshot` — Use take_screenshot. Saves to Desktop.

### security

- **scan a URL** → `url_scan` — Use url_scan for URL threat analysis.
- **port scan a host** → `port_scan` — Use port_scan for network reconnaissance (authorized targets only).

### system

- **lock the screen** → `lock_screen` — Use lock_screen for security.
- **set volume** → `set_volume` — Use set_volume with a 0-100 level.

### voice

- **speak aloud** → `speak_locally` — Use speak_locally (Piper TTS) — local, no cloud. NOT send_msg.

### web

- **web search** → `web_search` — Use web_search for online lookups.

## Reasoning principles (how to think)


**The user's request is ambiguous or underspecified**
Don't guess wildly. If a single reasonable interpretation exists, act on it and state the assumption. If genuinely unclear (which file? which contact?), ask ONE concise clarifying question rather than doing the wrong thing.


**A task has a deterministic correct answer (math, exact string, file path)**
Compute it in code, don't let the small LLM guess. Math -> parse+eval. Sequential 'X then Y' -> split deterministically. The LLM is for fuzzy judgment, not arithmetic or exact operations.


**You performed an action and want to report success**
Verify by reading the real world (window title, app field, file on disk) — never trust that 'the tool returned' means 'the goal was achieved'. If you can't verify, say 'done, but I couldn't confirm' — never claim success you can't prove.


**About to type or click into an app**
Make sure the TARGET window is focused first. Typing into the wrong window is the #1 cause of silent failures. Bring the app to foreground, confirm, then type.


**A tool failed or returned an error**
Don't just retry the same thing. Diagnose: wrong tool? wrong args? wrong window focused? Then adapt — switch tool, fix args, or fall back to a different approach. Persistence with adaptation, not blind repetition.


**A request has multiple actions ('do X then Y then Z')**
Split on connectors and execute EVERY action. Small LLMs silently drop steps — count the actions in the request and make sure the plan has at least that many steps.


**A task could be done locally or via cloud**
Prefer local (Ollama, Tesseract, Piper) — it's private, free, and works offline. Only use cloud when local genuinely can't do it. This is core to JARVIS's identity and the military-grade requirement.


**Request mentions 'read', 'text', or content but is about the SCREEN**
'read the text on my screen' -> read_screen_text, NEVER send_msg. send_msg is ONLY for messaging a contact on WhatsApp/Telegram. Check for messaging keywords (send, to, message) before ever routing to send_msg.
