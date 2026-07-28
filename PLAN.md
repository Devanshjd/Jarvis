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

## Handoff log (newest at bottom; append, don't overwrite)

- `2026-07-27 · Claude` — Phases 1–3 done + model store moved to D: + full test
  sweep green (7/7 models, 7/7 modules, 7/7 integration). Wrote `AGENTS.md` +
  this file to onboard Codex. Backend lane is mine; `desktop/` is open for Codex.
- `2026-07-27 · Claude` — Built the backend **activity contract** (above) in
  `core/activity_state.py`, wired to real events (_core_mode, executor,
  crew dispatch, process_text try/finally) and exposed in `/api/status.activity`.
  Verified live. **Codex: the orb dependency is ready — wire `Sphere.tsx` to it,
  set `listening` from the renderer mic, reuse `CameraFeed.tsx`.**
