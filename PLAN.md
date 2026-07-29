# PLAN.md — Shared coordination board (Claude ⇄ Codex)

> The blackboard between the two agents. **Read the bottom log before starting;
> add an entry when you finish.** Full project context is in `AGENTS.md`.

## Lanes (do not edit outside your lane without a note here)

| Agent | Owns | Don't touch |
|---|---|---|
| **Codex** | `desktop/` — Electron/React UI, views, persona indicators | `core/`, `web/` |
| **Claude** | `core/*.py`, `web/server.py`, `training/` | `desktop/` internals |

Shared/coordinate-first: `AGENTS.md`, `PLAN.md`, top-level configs, `requirements.txt`.

## Rules of the road
- `git pull --rebase` before you start. Small commits, push often.
- Run the smoke test / `npm run typecheck` before committing. Report failures honestly.
- Additive or feature-flagged; never break the running app.

## Current state (as of 2026-07-27)
- **Phases 1–3 of the multi-agent architecture are built, integrated, and tested.**
  Team scaffold, real tools (Bandit/CVSS/CWE), Obsidian vault + semantic recall,
  EDITH's gated improve loop, escalation ladder + scrubber, model scheduler,
  live `/api/team/*` endpoints, and a crew indicator in the UI status bar.
- All committed & pushed to `origin/main`.
- **Next: Phase 4 — Stormbreaker edge** (glasses camera in → team → HUD out over
  the split-compute bridge). Plus, if wanted, the deep orchestrator hook (team
  drives 100% of live chat) — a careful, feature-flagged step.

## Suggested first task for Codex (UI lane)
The backend already exposes `GET /api/team/status` and `POST /api/team/route`.
The UI only shows a minimal "CREW: N SPECIALISTS" line so far. A good self-
contained UI task: a small **crew panel/view** that shows each agent (JARVIS/
ULTRON/FRIDAY/VISION/EDITH), whether it's bound, and — after a `/api/team/route`
call — the last routed agent + the blackboard trail. Pure `desktop/`, no backend
changes needed.

---

## Activity contract — for the stateful orb (Codex, this is your dependency)

`GET /api/status` now returns a stable `activity` object. Poll it (the UI already
polls `/api/status`) and drive the orb from it. **Source of truth for the state
colors + active-agent label + tool-running + error.**

```jsonc
"activity": {
  "state": "idle | listening | thinking | tool_running | speaking | error",
  "active_agent": "JARVIS | ULTRON | FRIDAY | VISION | EDITH" | null,
  "label": "Running a security analysis" | null,   // human-readable, safe to show
  "tool":  "security" | "screen_analyze" | ... | null,
  "run_id": "8-hex" | null,                          // changes each new activity
  "since": "ISO-8601 UTC" | null,
  "error": "message" | null                          // set only when state=error
}
```

**Backend-owned states (trust these — driven by real lifecycle events):**
`thinking` (turn processing), `tool_running` (executor + crew specialists, with
`active_agent`/`label`), `speaking` (Piper TTS via the runtime), `error`, `idle`.
Verified live: `idle → tool_running(JARVIS·"Running get_fact") → speaking → idle`.

**Renderer-owned states (backend can't see these — YOU set them, don't fake from
backend):** `listening` comes from the actual microphone in the renderer (the
Gemini voice loop owns the mic). Gemini-voice *speaking* is also renderer-known.
So: OR the backend `activity.state` with the renderer's own mic/voice state —
mic active ⇒ `listening`, Gemini speaking ⇒ `speaking` — otherwise use the
backend state. Never show `listening`/`speaking` unless a real mic/TTS event
backs it (honesty rule).

**Suggested orb mapping:** idle=calm amber dim · listening=amber pulse ·
thinking=amber spin · tool_running=per-agent color (ULTRON red / FRIDAY cyan /
VISION violet / EDITH green) + show `label` · speaking=bright amber waveform ·
error=red + show `error`. Use `run_id` to animate transitions.

## Health + chat contract (truthfulness — Codex, wire the pills to THIS)

`GET /api/status` now also returns real service health from live probes (cached
~8 s). Use it to show honest pills — never a hard-coded "READY".

```jsonc
"provider": { ..., "reachable": true|false, "error": "…"|absent },  // false ⇒ LOCAL BRAIN OFFLINE
"health": {
  "ollama":          { "reachable": bool, "active_model": str|null, "models": int, "error": str|null },
  "gemini_live":     { "configured": bool, "connected": null, "error": null },   // connected is YOURS (renderer WS)
  "vision":          { "available": bool, "active_model": "moondream"|null, "ocr": bool, "active_source": null, "error": str|null },
  "memory_embedder": { "available": bool, "healthy": bool|null, "model": "nomic-embed-text", "error": str|null }, // healthy=null ⇒ warming
  "stt":             { "available": bool, "engine": "faster-whisper", "healthy": bool, "error": str|null },
  "tts":             { "available": bool, "engine": "piper"|"pyttsx3"|null, "healthy": bool, "error": str|null },
  "gesture":         { "available": null, "kind": "external process (py3.11 + mediapipe)", "healthy": null } // backend can't see it
}
```
Rules: `provider.reachable=false` ⇒ show **LOCAL BRAIN OFFLINE** (don't show a
model as ready). `gemini_live.connected` is **null from the backend** — YOU set
it from the renderer's real WS state; show **GEMINI CONFIGURED** (not "READY")
until your WS connects, and **VOICE DISCONNECTED** on drop. `vision.available=false`
⇒ **VISION UNAVAILABLE**. `healthy=null` on the embedder means "warming", not a
failure — don't flash red. Verified live: probes correctly reported Ollama
**offline** during an outage, then flipped healthy when it came back.

**Chat contract (`POST /api/chat`) — no more double replies.** Each response now
carries a `kind`:
- `kind:"ok"` — `reply` is the real answer (render it).
- `kind:"timeout"` — `reply:""`, `still_working:true`. Do **not** render a bubble;
  show a "still working…" state and let the real reply arrive once via
  `/api/history`. (The old bug: a generic answer then a late real one.)
- `kind:"empty"` — a rare honest "couldn't produce a response; rephrase?".

## Issues & pain points we hit (read this to save yourself hours)

These are real problems from building the crew — most bite when running or
testing against the backend, which you'll do a lot from the `desktop/` lane.

**Running the backend correctly**
- `python` is ambiguous on this box: some shells resolve it to **Python 3.11**
  (the gesture-only env — NO fastapi/uvicorn → `ModuleNotFoundError: uvicorn`).
  The real env is **3.13**. Launch with `python3.13` (the WindowsApps alias) or
  let the Electron app spawn it. If the backend "won't start", this is usually why.
- **No hot-reload.** `uvicorn.run` has no reload — after any Python change you
  must **restart** the backend. A stale backend silently serves old code.
- **The Electron app owns its own backend** (spawns `web_main.py`, now with
  `JARVIS_TEAM=1`). If you also run a backend by hand you'll get a port clash on
  8765, and killing one disconnects the app.

**Hardware reality (8 GB VRAM)**
- Loading **Foundation-Sec-8B (ULTRON, ~8.5 GB)** while gemma is resident can
  **OOM and crash the backend** — it already took the app down once. It's also
  **slow: 45–130 s** per answer. So: never block the UI waiting on it; the
  `activity` contract's `tool_running` state is there so the orb shows progress
  instead of freezing. Treat ULTRON as "call the analyst, expect a wait".
- Everyday chat is gemma3:4b and fast (1–16 s). Keep the snappy path snappy.

**Windows quirks**
- Console is **cp1252** — printing emoji/box-glyphs throws `UnicodeEncodeError`.
  Wrap stdout in UTF-8 or stick to ASCII in any CLI you add.
- `START_JARVIS.bat` used to point at a missing `main.py` (fixed → `web_main.py`).

**Camera (directly relevant to your orb/gesture work)**
- **Single-camera-owner rule.** The dashboard vision, the Gemini voice loop, and
  Face ID all want the one webcam; only one may hold it at a time or you get a
  black frame. `CameraFeed.tsx` must stay the sole owner — route the orb's
  gesture/preview through it, don't open a second `getUserMedia`.

**Honesty bugs are easy to ship — the whole team's #1 rule**
- We shipped (and Codex caught) a VISION agent that reported `verified` on an
  empty model reply, and one that swallowed screen-capture errors silently.
  **Never show a state/success without a real event behind it.** The orb must
  reflect the *actual* `activity.state`, show `activity.error` on error, and only
  show `listening`/`speaking` when the real mic/TTS is active. If you don't know,
  show "uncertain", not a confident lie.

**Routing was phrase-sensitive** (mostly fixed) — small wording changes flipped
which agent handled a request. If a crew action doesn't fire, it's often the
intent regex, not the dispatch.

**"Bigger model" is a dead end here** (measured): 12B == 4B on our tasks, 27B
won't load, a general 7B scored worse. The crew wins by *specialization + tools*,
not size — so the roadmap is polish/trust, not more/bigger models.

## Handoff log (newest at bottom; append, don't overwrite)

- `2026-07-27 · Claude` — Phases 1–3 done + model store moved to D: + full test
  sweep green (7/7 models, 7/7 modules, 7/7 integration). Wrote `AGENTS.md` +
  this file to onboard Codex. Backend lane is mine; `desktop/` is open for Codex.
- `2026-07-27 · Claude` — Built the backend **activity contract** (above) in
  `core/activity_state.py`, wired to real events (_core_mode, executor,
  crew dispatch, process_text try/finally) and exposed in `/api/status.activity`.
  Verified live. **Codex: the orb dependency is ready — wire `Sphere.tsx` to it,
  set `listening` from the renderer mic, reuse `CameraFeed.tsx`.**
- `2026-07-27 · Claude` — Added the **"Issues & pain points" section above** so
  Codex has the war stories (python 3.11-vs-3.13 backend launch, 8GB VRAM OOM +
  slow ULTRON, no hot-reload, single-camera-owner, cp1252, the honesty bugs, and
  why "bigger model" is a dead end). Read it before running/testing the backend.
- `2026-07-27 · Claude` — **Truthfulness/stability pass done** (my 6 backend
  items). `/api/status` now has real `health` + a truthful `provider.reachable`;
  `/api/chat` returns one terminal result with `kind` (no fake-then-late reply);
  crew self-knowledge always names the real 5; embedder health repaired to not
  false-red on cold load. `core/health.py` new. Tests: `training/
  test_backend_truthfulness.py` 5/5. Contract documented above. **Codex: wire the
  status pills + transcript to it (see the contract section).**
- `2026-07-28 · Codex` — Wired the truthful `/api/status.activity` contract into
  the Electron dashboard. The existing orb now uses backend agent/state colours,
  a lightweight scan-ring/wireframe upgrade, and real renderer mic/playback
  overrides; no second camera owner or CDN gesture dependency was added. Desktop
  typecheck and production build pass.
