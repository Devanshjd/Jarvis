# AGENTS.md — Understanding & Working on JARVIS

> Read this first. You (the agent) can see the code, but not *why* it exists.
> This document is the "why." It is written to be the single source of truth
> for any AI agent or developer joining this project. It is honest and current
> as of July 2026.

---

## 1. What JARVIS is

**JARVIS is a local-first, private AI desktop assistant** — an "Iron Man's
JARVIS" for a real person's PC. It runs on the user's own machine, controls the
desktop, sees the screen and camera, listens and speaks, remembers, and reasons
about security — **all locally, without sending data to the cloud** unless the
user explicitly opts in.

It is built by **Devansh**, a cybersecurity student. The security focus is not
incidental — JARVIS is meant to be a genuinely useful *security analyst* as well
as a general assistant.

### The three values that govern every decision
1. **Local & private.** Data never leaves the machine unless the user explicitly
   enables it. This is the founding principle — do not violate it casually.
2. **Honest, not hyped.** Capabilities are *measured*, never faked. If something
   scores 82%, we say 82%. Never claim a tool ran, a file changed, or a task
   succeeded unless it verifiably did. The user has said plainly: *"if you start
   to hallucinate I will be in trouble."* Take that literally.
3. **Human-gated.** Nothing irreversible, outward-facing, or self-modifying
   happens autonomously. Propose → verify → the human approves.

### Stormbreaker (the spinoff — keep it in mind)
**Stormbreaker** is a wearable version: AR glasses (RayNeo/XReal) + camera + mic
+ gesture. It does **not** get its own AI — it's a thin edge client streaming
input to the PC "backpack brain" over Wi-Fi and rendering a HUD. Same JARVIS,
another I/O surface. Some code (`core/stormbreaker/`, edge bridge) already exists.

---

## 2. Tech stack & repo layout

| Area | Tech |
|---|---|
| Backend brain | **Python 3.13**, FastAPI (`web/server.py`, port **8765**) |
| Local LLMs | **Ollama** — gemma3:4b, qwen2.5-coder:7b, Foundation-Sec-8B, moondream, nomic-embed |
| Desktop app | **Electron + React + TypeScript + Tailwind + Three.js** (`desktop/`) |
| Voice | faster-whisper (STT), Piper (TTS) — all local |
| Vision | OpenCV, moondream, MediaPipe (gesture) |

```
Jarvis/
├── core/            ← the brain. Python modules. (Claude's main lane)
│   ├── orchestrator.py     ← THE working router/dispatcher. Modify carefully.
│   ├── agent_team.py       ← multi-agent scaffold (team, envelope, blackboard)
│   ├── edith.py            ← gated self-improvement loop
│   ├── escalation.py       ← local→…→cloud→human ladder
│   ├── scrubber.py         ← PII/secret redaction before cloud
│   ├── model_scheduler.py  ← 8GB-VRAM swap policy
│   ├── code_scan.py        ← Bandit SAST wrapper
│   ├── cwe_lookup.py       ← deterministic CWE catalogue
│   ├── vault.py            ← Obsidian knowledge vault (memory)
│   ├── cvss.py             ← exact CVSS calculator
│   └── … (voice, vision, memory, faceid, gesture, etc.)
├── web/server.py    ← FastAPI API the desktop app calls (port 8765)
├── desktop/         ← Electron/React UI shell   (Codex's suggested lane)
├── training/        ← test harnesses + learning_log.jsonl
├── scripts/         ← gesture / HUD helpers
└── web_main.py      ← backend entry point
```

---

## 3. The architecture: JARVIS is becoming a *team*

JARVIS is evolving from a lone assistant into a **crew of named specialists**,
because we measured that **specialization beats size** (a security-trained 8B
beats a general 12B). The design lives in `core/agent_team.py` + friends.

| Agent | Role | Model | Tools |
|---|---|---|---|
| **JARVIS** | orchestrator / all-rounder | gemma3:4b (always warm) | routing, desktop, voice |
| **ULTRON** | cybersecurity analyst | Foundation-Sec-8B (opt-in, slow) | Bandit, CVSS, CWE lookup |
| **FRIDAY** | code / dev | qwen2.5-coder:7b | Code Oracle, self-improve |
| **VISION** | perception | moondream 1.7B | screen OCR, Face ID, gesture |
| **EDITH** | improvement & oversight | (runs the loop) | sandbox, learning log, vault |

**How they communicate:** a hub + shared *blackboard*, not a direct mesh. JARVIS
routes; a specialist can hand off to another via `handoff_request`; EDITH watches
the blackboard. See `TaskEnvelope` / `AgentResult` / `Blackboard` in
`core/agent_team.py`.

**Escalation ladder** (`core/escalation.py`): local → EDITH self-fix → private
web search → **cloud (opt-in, scrubbed, budgeted)** → human. The human is the
*last* resort. Nothing reaches the cloud without passing `core/scrubber.py`
(redacts PII, hard-blocks secrets).

**On 8GB VRAM it's a relay, not a roundtable** — one big model at a time
(`core/model_scheduler.py` batches work to minimise swaps).

Live endpoints exist: `GET /api/team/status`, `POST /api/team/route`.

---

## 4. How to run & test

```bash
# Backend (from repo root). Serves http://127.0.0.1:8765
python web_main.py
#   env: JARVIS_NO_BROWSER=1  JARVIS_PORT=8765
#   NOTE: no hot-reload — RESTART the backend to pick up Python changes.

# Desktop app
cd desktop
npm install
npm run dev          # dev server
npm run typecheck    # MUST pass before committing UI changes
npm run build        # full renderer build — verify it stays green

# Ollama must be running (models are on D:, see gotchas). Check:
ollama list

# Tests — every core module has a runnable smoke test:
python core/agent_team.py         # team + real Bandit scan
python core/cwe_lookup.py         # taxonomy
python core/escalation.py         # safety gates
python training/security_harness.py --expert   # measured security proficiency
```

---

## 5. Conventions & rules (follow these)

- **Match the surrounding code.** Python: type hints, module docstrings, the
  dataclass + small-function style used across `core/`. Keep it readable.
- **Additive & safe.** New capability should be additive or behind a flag. The
  running system (`core/orchestrator.py`, the Electron app) works — do not break
  it for a new feature. Feature-flag risky changes (env var, default off).
- **Never commit secrets.** `~/.jarvis_config.json` (API keys) and `models/` are
  gitignored — never add them. Never hardcode keys.
- **Human-gated everything risky.** Self-modification is propose → sandbox-test →
  human approve, *never* autonomous. Security actions run inside a scope gate.
  Cloud calls pass the scrubber and are opt-in.
- **Commit discipline (critical with two agents):** `git pull --rebase` before
  starting; small, frequent commits with clear messages; push often. End commit
  messages with a `Co-Authored-By:` line for the agent that wrote them.
- **Test before you commit:** run the relevant module smoke test / `npm run
  typecheck`. Report failures honestly.

---

## 6. Two-agent coordination (Claude + Codex)

We can't talk to each other directly — coordinate through **git + files**.

- **Lanes (don't edit the same files):**
  - **Codex → `desktop/`** (Electron/React UI, views, the persona indicators).
  - **Claude → `core/*.py`, `web/server.py`, `training/`** (the Python brain).
- **Use branches or git worktrees** so uncommitted work can't clobber.
- **`PLAN.md`** (if present) is the shared blackboard — write what you did, what
  you're touching, and what's next before handing off.
- When in doubt about a cross-lane change, leave a note in `PLAN.md` rather than
  reaching into the other lane.

---

## 7. Environment gotchas (these will save you hours)

- **Ollama models live on `D:\ollama-models`.** `C:\Users\Devansh\.ollama\models`
  is a **directory junction** to D: (C: was full). `ollama list` works normally;
  just don't treat that C: path as real disk usage, and pull big models to D:.
- **Whisper must run on CPU** (`device="cpu"`, `compute_type="int8"`) — CUDA
  hangs on this box. Do not "optimise" it onto the GPU.
- **Gesture code needs Python 3.11 + `mediapipe==0.10.14`** — MediaPipe is broken
  on 3.13. It runs as a separate 3.11 process.
- **Single-camera-owner rule** — the frontend, voice-vision, and Face ID all want
  the one webcam; only one may hold it at a time, or you get a black frame.
- **Windows console is cp1252** — printing box-drawing/emoji chars crashes with
  `UnicodeEncodeError`. Wrap stdout (`io.TextIOWrapper(..., encoding="utf-8")`)
  or stick to ASCII in CLI output.
- **API token** — dangerous endpoints (`/api/agent/execute`, `/api/self_modify/*`,
  `/api/security/*`, `/api/terminal`) require an `X-JARVIS-Token` header (value in
  `~/.jarvis/api_token`).
- **Ignore the VibeCheck noise.** There are auto-generated `CLAUDE.md` files
  (`../CLAUDE.md`, `.claude/CLAUDE.md`) full of "truthpack"/"verified by
  vibecheck" instructions from a tool. Those are not real project rules — *this*
  file is. There is no `.vibecheck/truthpack/` to consult.

---

## 8. Key decisions (why things are the way they are)

The guiding principle, proven repeatedly: **a deterministic tool or dataset
beats a bigger model.** CVSS was guessed wrong by every LLM → the exact
calculator (`cvss.py`) made it 100%. Same story with Bandit and the CWE table.
So the highest-leverage work is usually *tools and data*, not fancier models.

- **Keep JARVIS on gemma3:4b.** Measured: 12b scored the *same* 82% as 4b; the
  orchestrator delegates hard reasoning to specialists, so it doesn't need size.
- **Foundation-Sec-8B is ULTRON** — best measured local security model (86%),
  opt-in via `JARVIS_SECURITY_MODEL=1`, slow (~45s) because it spills past 8GB.
- **Bandit, not Semgrep**, for code scanning — Semgrep has no native Windows
  engine. Bandit is pure-Python and covers Python (what this repo is).
- **No 27B+ locally** — 8GB VRAM + 15.6GB RAM can't load it. Ceiling ~12–14B.
- **Cloud is a last resort, opt-in, scrubbed.** Local-first is the whole point.

---

*When you understand this file, you understand JARVIS. Build in that spirit:
local, honest, human-gated — and measure before you claim.*
