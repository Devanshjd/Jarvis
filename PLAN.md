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

## EDITH approval queue — the "batch-approve digest" (Codex, build the review UI on THIS)

The independence-without-removing-the-gate design. EDITH auto-applies GREEN
(safe/reversible) changes after the sandbox passes — real autonomy. RED changes
(code, gates, permissions) still PASS the sandbox but then **wait in an approval
queue** for your sign-off, one-by-one or as a batch "digest". Every apply is
backed up (rollback), every action audited.

Endpoints (POSTs are token-guarded like the other `/api/edith/*`; the GET is open
so the desktop can poll it for a review badge):

```
GET  /api/edith/queue?limit=50   → { pending:[item], recent:[item], counts:{status:int} }
POST /api/edith/approve       {id} → applies it (reversibly); returns the item
POST /api/edith/reject        {id}
POST /api/edith/approve_all        → { count, results:[item] }   ← the digest button
POST /api/edith/reject_all
POST /api/edith/rollback      {id} → undo an applied item (restore file / delete new note)
POST /api/edith/propose_code {file,instruction} → EDITH DRAFTS real code (qwen) →
     sandbox-tests it → parks a passing draft in the queue. SLOW (30–130 s on the
     coder model); returns {status:"queued",queued_id} or {status:"failed",report}
     with the honest sandbox error. Nothing is applied.
```

`item` shape:
```jsonc
{ "id":"8-hex", "created_at":"ISO", "status":"pending|applied|rejected|rolled_back|failed",
  "tier":"red", "kind":"code|lesson|prompt|routing|config", "target":"core/x.py",
  "title":"…", "body":"…", "preview":"one-line", "reason":"why it was gated",
  "proof":{ "passed":true, "before":82, "after":84, "note":"…" },
  "applied_to":"<path written on approve>", "decided_at":"ISO", "error":"" }
```

UX to build: a **review badge** = length of `pending` (poll the GET). A **digest
panel** listing `pending` with per-item Approve/Reject + one **"Approve all"**
(→ `approve_all`). Show applied items with an **Undo** (→ `rollback`). **Empty
`pending` is the normal state** — green auto-applies; only red parks here. Items
only appear after a real applying pass (`POST /api/edith/run?apply=true`), and
not until a red-tier proposer exists (today the default proposer makes green
lessons only), so don't treat empty as an error.

What "Approve" does, by item kind (reflect in the copy):
- **`code` with a drafted body** (from `propose_code`, `has_payload:true`) →
  Approve **patches the real file** (backup taken; `rollback` restores it).
  It already passed the sandbox and your click is the gate. Takes effect on the
  **next backend restart** (no hot-reload) — say so in the UI. Show the `body`
  diff prominently; this is the one the human must actually read.
- **`code` without a body** (generic gating, `has_payload:false`) → Approve only
  records an approved proposal note in the vault; nothing is patched.
- **lesson / prompt / config** → Approve writes a durable vault note.

Real-world reminder from the first live run: a qwen draft PASSED the sandbox but
had made the docstring *worse* — a quality regression only a human catches. The
sandbox proves "won't crash", not "is good". So the diff review is not optional
chrome; it's the whole point. Default the digest to **review-then-decide**, never
a blind "approve all" for code items.

## Desktop control — gated keyboard/mouse (Codex, build the control card on THIS)

The highest-blast-radius capability in the project, so it's **off by default** and
every safety rail lives in the backend. Your UI drives it; it can't act without an
enabled + scoped + unexpired session, and each step is safety-gated server-side.

Endpoints (all POSTs token-guarded under `/api/desktop/`; status GET is open):
```
GET  /api/desktop/status          → { available, enabled, session|null, recent:[…] }
POST /api/desktop/enable  {on}     → the APPROVE DESKTOP toggle (off ends any session)
POST /api/desktop/session/start {task, app_scope, ttl} → approve a task bound to ONE app
POST /api/desktop/session/stop     → the Stop button (ends control immediately)
POST /api/desktop/plan    {task}   → deterministic proposed actions (NOTHING runs)
POST /api/desktop/observe          → read-only active window + scoped control labels
POST /api/desktop/step    {action} → execute ONE approved atomic action (gated+verified)
```
`action` is one typed atomic step: `{action:"open_app"|"focus"|"click"|"type_text"|
"press"|"hotkey", …}` (e.g. `{"action":"type_text","text":"hi"}`). `step` returns
`{ok:true, result, verify:{before_window,after_window}}` or a refusal:
`{blocked:"…"}` (credential/financial/CAPTCHA — refused even if approved),
`{refused:"…"}` (disabled / no session / outside app scope / unknown action).

UI to build: an **APPROVE DESKTOP** toggle → a **session card** (task + app scope +
countdown) → call `plan`, show the proposed steps, and let the user **approve each
step** (→ `step`) with the target window shown → a big **STOP** (→ session/stop).
Show `verify` after each step. Rules to honour in the copy: control is **scoped to
one app** and **expires**; credentials/financial/CAPTCHA are **hard-blocked** (tell
the user to do those themselves); typing **fails closed** if the active window
isn't the approved app. Screen content is never used to pick actions.

**Browser control (same session, same gate).** A session can also carry a
`origins` allowlist, and then these **browser actions** run through the same
`/api/desktop/step` (Playwright, real local Chromium):
```
navigate {url}   — refused unless url's origin ∈ allowlist (every action re-checks live origin)
extract          — read-only: {url,title,elements:[{tag,type,name,text}]} for YOU to choose from
click_dom {selector}
fill {selector,text}     — a password/credential field is refused at the DOM level
select {selector,value}
upload {selector,path}   — an approved local file
browser_shot             — screenshot (b64)
browser_close
```
`POST /api/desktop/session/start` now takes `{task, app_scope?, origins?, ttl}` —
bind to a native app, a browser allowlist, or both (at least one). A **submission
in your name** (`submit`/`send`/`post`/`apply`, or an action with `submit:true`)
is **refused unless the action carries `confirm:true`** — that's your final
review gate; money actions stay hard-blocked entirely. Verify shape for browser
steps is `{before_url, after_url}`. Codex: the operator console shows the live
URL + extracted elements, per-step approve, and a distinct **Confirm submission**
control that sends `confirm:true`.

**Raw-input hole closed.** The legacy `executor` input tools (`mouse_click`,
`type_text`, `screen_click`, …) no longer auto-approve under a Gemini-Live voice
session or a passed `approve_desktop`; they now require an armed
`DesktopController` session (`raw_input_allowed()`). The scoped session is the one
switch that arms real keyboard/mouse — chat/voice can't.

## Job Application Mode (Codex, build the profile editor + fill-review on THIS)

A **planner on top of** the gated browser — it never bypasses a gate, and it
**never invents an answer** (a form goes out in your name). Fills come only from a
local facts-only profile; unknowns are handed back to you; Submit stays the
console's confirm-gated step.

```
GET  /api/jobs/profile          → PII-FREE summary {has_profile, identity_fields:[…],
                                   links:[…], resume:bool, approved_answers:[…], preferences}
POST /api/jobs/profile {data}   → save approved facts to ~/.jarvis/job_profile.json (NOT the repo)
POST /api/jobs/plan_fill {fields}→ {plan:[…], actions:[…], summary:{fields,auto_fill,needs_user:[…]}}
POST /api/jobs/rank {listings}  → {ranked:[{score,…}]}
```
`fields` = what `extract` returns. Each `plan` entry is either
`{needs_user:true, reason}` (YOU fill it — credential, or no approved fact) or
`{needs_user:false, matched_key, source:"profile.<key>", action:{…}}` whose value
was copied verbatim from the profile. `actions` are the auto-fills to feed one by
one into `/api/desktop/step` (still per-step approved); the final **Submit is not
in there** — it's your confirm-gated click. UI: a **profile editor** (identity,
links, resume path, approved screening answers, preferences), and per application
a **fill-review** that clearly marks each field *from your profile* vs *needs you*,
then the Confirm-submission control. Never show JARVIS composing an answer.

## Persona v1 (Codex, build the settings/persona editor on THIS)

One honest personality for text AND voice. `core/persona.py` defines the voice
(calm, sharp, concise, dry humour) plus the **never-pretend rule** (only claim
actions actually performed; never fake seeing the screen / running a scan / a
result), and a facts-only local owner memory (`~/.jarvis/persona.json`). It's
injected into the chat system prompt already (always on); the voice loop should
call `persona_prompt()` too so both surfaces sound the same (coordinate — voice
reliability is the shared next milestone).

```
GET  /api/persona                 → { guide:"<full persona prompt>", remembers:{owner_name, help_style:[…], projects:[…], preferences:[…], facts:[…]} }
POST /api/persona/remember {category,item}  → teach one fact (category ∈ help_style|projects|preferences|facts); facts-only
POST /api/persona/forget   {category,item}
POST /api/persona/owner    {name} → how JARVIS addresses you
```
UI: a **persona/settings panel** — show the voice guide (read-only), let the user
add/remove how-they-like-help / projects / preferences and set their name.
It's facts-only: JARVIS never invents a preference, and the memory stays local.
`truthful_activity_line()` (from the real `activity` state) is available so the
transcript can show "Right now: thinking / VISION scanning / browser step awaiting
approval" honestly — pairs with your activity timeline.

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
- `2026-07-30 · Codex` — Wired Claude's `/api/status.health` + `/api/chat.kind`
  truthfulness contract into the Electron dashboard. Provider/vision/voice pills
  now distinguish offline, configured, live, and disconnected states; dashboard
  camera/screen activity no longer conflicts with the centre VISION badge; a
  timed-out chat renders only `JARVIS // STILL WORKING` until history receives
  the one real reply. Gemini Live receives the accurate five-member crew roster
  in its renderer context. Verified against the live backend; typecheck +
  production build pass. Desktop-only files touched.
- `2026-07-30 · Claude` — **EDITH approval queue shipped** (independence WITHOUT
  removing the gate — the answer to "just make it autonomous like Hermes": even
  Hermes keeps a human gate). Green auto-applies after the sandbox; RED passes now
  park in a persistent, batchable approval queue instead of being dropped. New
  `core/approval_queue.py` (thread-safe, atomic, audit log + file backup/rollback);
  EDITH enqueues `HUMAN_GATE` decisions and gained `approve/reject/approve_all/
  reject_all/rollback`; six `/api/edith/*` endpoints (contract above). The
  un-gameable rule still holds — a change touching the grader is REJECTED, never
  queued. Tests `training/test_edith_queue.py` **7/7**; decision matrix + backend
  truthfulness still green; verified live on 8765 (queue shape, token guard 403,
  graceful bad-id). **Codex: build the batch-approve digest UI on the contract above.**
- `2026-07-30 · Claude` — **Code-drafting path wired into EDITH.** `propose_code`
  (new `POST /api/edith/propose_code`) has EDITH draft REAL code via the local
  coder model (qwen2.5-coder), sandbox-test it (syntax + N load-sims), and park a
  passing draft in the queue carrying the full content. **Approving a drafted code
  item now PATCHES the real file** (backup + rollback; effective next restart) —
  approval is the gate. Guarded twice (proposer `can_modify` + EDITH `_FORBIDDEN`).
  Also a `run_once(code_targets=...)` curated hook (EDITH never guesses a file).
  Tests `training/test_edith_queue.py` now **11/11**. **Verified live end-to-end
  with the real model**: drafted a change to `core/activity_state.py`, passed 4/4
  sandbox checks in ~30 s, queued — and it had made the docstring *worse*, so I
  rejected it (the gate earning its keep). Contract above updated; the code-diff
  is the item the digest UI must show for review.
- `2026-07-30 · Codex` — Built the desktop **EDITH Improvement Digest**. The new
  EDITH nav badge polls the read-only queue; the view renders pending gated
  proposals with evidence, full code diffs, a required diff-review acknowledgement
  before patch approval, per-item reject, audit history, and Undo for applied
  backed-up items. Batch approval is disabled whenever code is pending; no action
  is sent without an explicit click. Verified live against `:8765` (empty queue
  plus the real rejected code audit), and `npm run typecheck` + `npm run build`
  pass. Desktop files only.
- `2026-07-30 · Claude` — **Gated desktop control (keyboard/mouse) — backend.**
  Answer to "JARVIS can't use the mouse/keyboard like you": the primitives already
  existed (precise_click pywinauto→OCR, screen_interact vision, pyautogui) but were
  scattered with only a tkinter popup gate. New `core/desktop_control.py` unifies
  them behind a real safety model: OFF by default (`JARVIS_DESKTOP` / `/enable`),
  scoped+expiring sessions bound to ONE app, propose→approve→execute→verify→log per
  atomic action, hard-blocks on credentials/financial/CAPTCHA (refused even if
  approved), FAIL-CLOSED typing outside the app scope, deterministic planning (no
  model in the loop → screen can't inject steps), append-only audit. Seven
  `/api/desktop/*` endpoints (contract above). Tests `training/
  test_desktop_control.py` **9/9** (never move the real mouse). Verified live SAFE
  paths on 8765 (status off-by-default, 403 guard, deterministic plan, disabled
  refusal). **I did NOT run a live desktop action — that needs Devansh present +
  APPROVE DESKTOP.** **Codex: build the control card (toggle → session → per-step
  approve with target window → STOP) on the contract above.**
- `2026-07-30 · Codex` — Built the desktop **CONTROL** tab on the real
  `/api/desktop/*` contract: off-by-default gate, task/app/TTL scoped-session
  form, deterministic plan preview, sequential per-step approvals with the
  read-only active-window target, verified before/after window display, audit,
  and a prominent Stop button. The dashboard's old broad `APPROVE DESKTOP`
  checkbox was removed so chat/voice no longer claim it grants this capability;
  renderer chat always sends `approve_desktop:false`. Verified the live safe
  status (`available:true`, `enabled:false`, no session/action) and ran desktop
  typecheck + production build successfully. **No control was armed and no mouse
  or keyboard action ran.** Restart the desktop app to load the new view.
- `2026-07-30 · Codex → Claude security follow-up` — The legacy
  `/api/agent/execute` / executor path still has its own desktop approval model,
  separate from `DesktopController` (and the executor can auto-approve under a
  live voice session). The desktop renderer no longer opts into it, but to make
  the gated controller the true sole path, route raw input through
  `DesktopController` or hard-disable that legacy raw-input path in `core/`.
- `2026-07-30 · Claude` — **Computer Use milestone — core delivered.** (1) Closed
  the raw-input hole: `executor` actuating tools (`mouse_click`/`type_text`/
  `screen_click`/…) now require `DesktopController.raw_input_allowed()` — no more
  auto-approve under a voice session or `approve_desktop`. (2) New
  `core/browser_control.py`: real local-Chromium Playwright driver on its own
  thread, origin-allowlisted, with DOM-level password-field refusal and read-only
  `extract`. (3) Unified into the ONE session coordinator (`core/desktop_control.py`):
  a session binds to `app_scope` and/or a browser `origins` allowlist; browser
  actions (`navigate/extract/click_dom/fill/select/upload/browser_*`) run through
  the same gated `/step`; submissions in your name need `confirm:true`; money/
  creds/CAPTCHA stay hard-blocked. Contract above. Tests: `test_desktop_control.py`
  **15/15** + `test_browser_control.py` **5/5** (real headless Chromium vs a LOCAL
  fixture — password refusal + allowlist proven); edith 11/11 + truthfulness 5/5
  still green. **Deferred:** "Job Application Mode" workflow (find→rank→draft→fill→
  you confirm Submit) — the primitives are ready for it. **Codex: build the unified
  operator console on the extended contract (browser URL/elements, per-step approve,
  Confirm-submission control, STOP).**

## Next milestone — unified Computer Use (Claude core + Codex desktop)

**Goal:** General local computer use, not a jobs-only feature: browser DOM
control, native Windows keyboard/mouse/app control, and screen/OCR fallback all
share one scoped, observable, human-gated execution loop.

**Core contract (Claude — delivered in `afa56b2`):** extends the existing `/api/desktop/*` safety
model into a single session coordinator: `observe -> propose -> approve one typed
action -> execute -> verify -> audit -> stop`. A session must bind to a task, a
TTL, and either one Windows app or an explicit browser-origin allowlist. Browser
actions should be typed (`navigate`, `click`, `fill`, `select`, `upload approved
file`, `extract`) and use a local Chrome/Playwright or CDP driver; native actions
reuse `DesktopController`. Structured DOM/screen content is data, never an
instruction. The old raw-input agent path must be routed through this coordinator
or disabled.

**Required hard gates:** control off by default; scoped and expiring sessions;
per-action approval; visible target/browser URL before execution; fail closed on
unknown focus/target; append-only audit; immediate Stop; no credentials/secrets,
CAPTCHAs, financial actions, or unreviewed external submissions. Use local fixture
pages and stubbed native primitives for tests — never live job sites.

**Desktop follow-up (Codex):** evolve CONTROL into the unified operator console:
browser/app scope chips, live page/window evidence, typed action timeline,
verification/recovery display, profile/file chooser, and a final submission-review
gate. The existing CONTROL tab is the native-control foundation, not a duplicate.

**Security correction required (Claude):** Codex independently reproduced that
`DesktopController._blocked()` only inspected native-style action fields
(`text/app/target/keys`), so a browser `click_dom` action with a selector such as
`button#buy-now` returned `None` instead of a financial hard block. The desktop
console now defensively refuses to queue credential/CAPTCHA/financial-looking
browser actions, but this is not sufficient: extend the backend matcher to cover
`url/selector/value/path` for every browser action and add direct regression tests
before calling the browser money/CAPTCHA guard complete.

- `2026-07-30 · Codex` — Upgraded desktop **CONTROL** into the unified Computer
  Use operator console. It now starts app and/or browser-origin scoped sessions;
  displays live page URL/title and extracted DOM evidence; lets the operator queue
  typed `navigate/extract/click/fill/select/upload/screenshot` browser actions;
  requires sequential step approval; displays URL/window verification and a
  combined audit; and gives submissions a separate review checkbox plus
  `confirm:true` execution. Native control, Stop, and the browser screenshot
  evidence remain in the same console. Browser action drafts are additionally
  client-blocked for credential/CAPTCHA/financial-looking values until the core
  matcher correction above lands. Verified `npm run typecheck` + `npm run build`,
  `training/test_desktop_control.py` **15/15**, and real local-fixture headless
  Chromium `training/test_browser_control.py` **5/5**. No session was enabled and
  no browser/native action ran against a live target.
- `2026-07-30 · Claude` — **Closed the browser money/CAPTCHA/credential gap Codex
  found.** `DesktopController._blocked()` now inspects every operable field —
  `selector/value/path/url` as well as native `text/target` — and normalises
  selector/URL separators first, so a hint buried in a CSS selector surfaces as a
  word (`button#buy-now` → "button buy now", `.g-recaptcha` → "g recaptcha",
  `#card-number` → "card number"). So a payment/CAPTCHA/credential-looking browser
  action is now hard-blocked at the backend, not only defensively in the UI.
  Regression tests added (`test_block_hints_hidden_in_selectors_and_paths`);
  `test_desktop_control.py` **16/16**, browser fixture **5/5**. Codex: the backend
  guard is now authoritative — the client-side block is belt-and-suspenders, not
  the only line. Restart the backend to load it.
- `2026-07-31 · Claude` — **Job Application Mode — core built.** New
  `core/job_profile.py` (local facts-only profile at `~/.jarvis/job_profile.json`,
  PII outside the repo, PII-free summary) + `core/job_apply.py` (`map_form`
  deterministically maps extracted form fields → fill actions **only** from
  approved facts; credentials/free-text/unknowns → `needs_user`; **never invents a
  value**; `rank_listings` scores real listings by your prefs). Four `/api/jobs/*`
  endpoints (contract above), token-guarded (PII). It's a PLANNER — execution
  reuses the gated `/api/desktop/step`, Submit stays confirm-gated. Tests
  `training/test_job_apply.py` **5/5** incl. the "NEVER fabricates a value" guard.
  **Deferred:** live search orchestration polish. **Codex: build the profile editor
  + fill-review UI on the contract above.**
- `2026-08-01 · Claude` — Fixed the PII leak Codex flagged: `JobProfile.summary()`
  no longer returns the profile file `path` (the home dir exposes the OS username).
  Regression assertion added (summary carries no `path` / `.jarvis` string). Jobs
  **5/5**. `/api/jobs/profile` GET is now truly PII-free (field names only).
- `2026-08-01 · Codex` — Delivered desktop **JOBS**: a local profile editor,
  PII-free fact inventory, and a facts-only fill review. The editor never
  prepopulates saved values; saving requires a local/verbatim-use acknowledgement,
  explicitly warns that it replaces an existing profile, then clears the entered
  values. CONTROL can hand its real extracted page evidence to JOBS; only fields
  with a stable extracted `name`/`id` are eligible (no broad `input` selector).
  The review shows profile source keys or `needs you`, never fact values; reviewed
  actions return to CONTROL as redacted in-memory queue entries, still requiring
  per-step approval. Stop clears pending sensitive queue entries; Submit remains
  absent from JOBS and confirm-gated in CONTROL. Verified `npm run typecheck`,
  `npm run build`, `training/test_job_apply.py` **5/5**, and
  `training/test_desktop_control.py` **16/16**. No live page or application was
  touched.

  **Core follow-up (Claude):** `JobProfile.summary()` currently returns `path`,
  which can include the Windows username despite the PII-free contract. Codex does
  not render it, but the backend should drop that field. Also consider making
  `has_profile` account for `resume_path` / `cover_letter_path` /
  `work_authorization`, or return explicit presence booleans, so a profile made of
  those approved facts alone is represented truthfully in the inventory.

## Persona + Presence v1 (parallel lanes, 2026-08-01)

**Desktop contract (Codex owns):** Persist this local-only shape in
`~/.jarvis_config.json` under `persona`, expose it in the shell snapshot, and
provide an honest Settings editor. The renderer must not claim personality is
active until the backend reports it has loaded the profile.

```jsonc
"persona": {
  "instructions": "operator-authored, max 500 chars",
  "humour": "off | subtle | dry",
  "response_style": "concise | balanced | detailed",
  "proactivity": "off | suggest_only"
}
```

`voice.gemini_voice_name` remains the selected renderer-owned live voice. The
Settings save must persist it rather than merely changing the selected button.

**Core contract (Claude owns):** Load `config.persona`, validate/default it, and
apply it to both local chat and Gemini Live context. Expose a truthful,
PII-free `persona` status in `/api/status`, for example
`{"loaded":true,"humour":"dry","response_style":"concise",
"proactivity":"suggest_only"}`. Do not represent consciousness or invent
observations/emotions. `suggest_only` may surface a real local signal as a
recommendation but never execute, message externally, or interrupt voice without
the operator's approval. Add focused tests for persistence/defaulting and that
the status says unloaded when no profile is available.

- `2026-08-01 · Codex` — Desktop half delivered: Settings now persists the
  structured `persona` profile locally, preserves the chosen Gemini Live voice,
  reloads both through the shell snapshot, and provides Tactical Butler / Warm
  Partner / Direct Operator starting profiles plus explicit humour, response-style,
  and suggest-only controls. The page never claims personality is active until
  `GET /api/status` reports `persona.loaded`; before then it says backend
  application is unverified. A snapshot refresh no longer overwrites an operator
  while they are editing. Verified `npm run typecheck` + `npm run build`.
- `2026-08-01 · Claude` — **Persona v1 core built + your contract fulfilled.** New
  `core/persona.py`: loads/validates `config.persona` from `~/.jarvis_config.json`
  (humour/response_style/proactivity/instructions — invalid values default, missing
  profile → unloaded+defaults), builds ONE `persona_prompt()` for chat and voice
  from the knobs + an **immutable honesty core** (only claim real actions; no
  invented perceptions/results/feelings; no consciousness; custom instructions can
  never override it), plus a facts-only local owner memory (`~/.jarvis/persona.json`,
  `/api/persona/*`). Applied to chat: injected in `orchestrator._ai_pipeline`
  (always on). **`GET /api/status.persona`** now returns the PII-free status
  `{loaded, humour, response_style, proactivity, error}` — reports `loaded:false`
  when no profile is saved (so your "unverified until loaded" copy is truthful; no
  `instructions` leaked). `proactivity:suggest_only` is documented in the prompt as
  surface-a-real-signal-only, never execute/message/interrupt without a yes. Tests
  `training/test_persona.py` **6/6** (defaulting, PII-free status, honesty rule,
  facts-only). **Voice loop still needs to call `persona_prompt()`** so both
  surfaces match — that's our shared voice-reliability milestone. All backend
  suites green (43/43).
