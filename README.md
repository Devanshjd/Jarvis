# J.A.R.V.I.S — a local-first personal AI

A desktop AI assistant that runs **on your own machine**. No cloud dependency for the core, no API keys leaving your PC — voice, memory, vision, code understanding, and desktop control, all local where it counts.

Built in public by a cybersecurity student. Still rough, still evolving — but it's real and it runs.

> **Why local?** If you're going to trust an assistant with your screen, your files, and your voice, it should stay on your hardware. Privacy isn't a feature here — it's the foundation.

---

## What it does

### 🗣️ Voice — fully offline
A turn-based local voice loop: **Whisper** (speech-to-text) → **Ollama** (local LLM) → **Piper** (text-to-speech). Talk to it with your internet off. A cloud voice mode (Gemini Live) is also available for real-time streaming.

### 🧠 Semantic memory
Remembers conversations by **meaning, not keywords** — local embeddings (`nomic-embed-text`) + cosine search. Ask something related to a past chat and it recalls the right context. Wired into both text chat and voice.

### 👁️ Vision
Reads your **screen and camera** with local models (gemma3 / moondream) + OCR. Face recognition (OpenCV LBPH) greets its owner by name — 100% on-device.

### 🖱️ Desktop control
Opens apps, manages files, runs commands, types text, presses shortcuts, and drives macros — real OS automation, not just chat.

### 🔍 Code Oracle
Point it at any repository, index it, and **ask questions in plain English** — answers come back grounded in the actual code with `file:line` citations. Local RAG.

### 🛡️ Security toolkit
A scope-gated recon pipeline (`subfinder → httpx → nuclei`) with local-LLM triage, and a `/bounty` tracker for bug-bounty work. **Refuses to scan out-of-scope targets** — built to be a responsible tool.

### ✋ Gesture control
Hand gestures via **MediaPipe** map to real actions (open palm → wake voice, peace → switch view). Part of the **Stormbreaker** wearable roadmap.

### 🔧 Self-improvement (human-gated)
JARVIS can draft changes to its **own code** with a code-specialized model, test them in a sandbox with multiple simulations, and report back — but **only applies them after you approve**. No autonomous self-rewriting.

---

## Architecture

```
┌──────────────────────────────┐        ┌───────────────────────────┐
│  Electron desktop app (UI)   │  HTTP  │  Python backend (FastAPI) │
│  React · Tailwind · Three.js │◄──────►│  port 8765                │
└──────────────────────────────┘        │                           │
                                         │  Ollama (local LLMs)      │
                                         │  Whisper · Piper · OCR    │
                                         │  Vector memory · Oracle   │
                                         │  Vision · Face ID         │
                                         └───────────────────────────┘
```

Gesture detection runs as a small **Python 3.11** side-process (MediaPipe) that talks to the backend over HTTP.

---

## Tech stack

- **Frontend:** Electron, React, TypeScript, Tailwind, Three.js (react-three-fiber), Framer Motion
- **Backend:** Python, FastAPI
- **Local AI:** Ollama (gemma3, qwen2.5-coder, nomic-embed-text), faster-whisper, Piper TTS, Tesseract OCR, OpenCV, MediaPipe
- **Storage:** SQLite (knowledge graph + vector memory)

---

## Running it

**Prerequisites:** Python 3.13, Node.js, [Ollama](https://ollama.com) running locally, and a few models pulled:

```bash
ollama pull gemma3:4b
ollama pull nomic-embed-text
ollama pull qwen2.5-coder:7b   # for the self-improvement proposer
```

**Backend + desktop:**

```bash
# backend (FastAPI on :8765)
python web_main.py

# desktop app
cd desktop
npm install
npm run build
npm start
```

**Gesture service (optional, needs Python 3.11 — MediaPipe doesn't support 3.13):**

```bash
py -3.11 scripts/gesture_service.py
```

Voice models (Piper `.onnx`) and the Whisper model download on first use / from their respective sources — they're not committed to keep the repo lean.

---

## Stormbreaker — the wearable

The long-term goal: take JARVIS off the desktop and into **AR glasses**. The plan uses off-the-shelf display glasses (e.g. RayNeo Air 3s) as the HUD, a phone as the camera + compute edge, and the PC as the brain over WiFi. The entire **software** stack — vision, voice, memory, gesture — already works; what's left is hardware assembly.

---

## Status & honesty

This is a **learning-in-public project**, not a polished product. Some honest notes:
- The **core is local**; the optional real-time voice mode uses a cloud model (Gemini Live).
- The self-improvement loop is **human-gated** by design — it proposes and tests, you approve.
- The security tooling is for **authorized testing only** (bug-bounty programs with explicit scope). Scanning systems you don't have permission to test is illegal.
- Reliability is measured, not assumed — but it's a work in progress.

---

## Author

**Devansh Jamdar** — cybersecurity student (SOC / pentesting / network security). Building JARVIS and its Stormbreaker wearable spinoff in public.

*If you find this interesting, feedback is genuinely welcome.*
