"""
J.A.R.V.I.S — Voice Control  (backend speech: cancellable, chunked, honest, timed)

The reliability half of voice that lives on the backend. Today Piper synthesises a
whole reply to one WAV and `winsound` plays the blob — you can't cut it off, and
the first word waits on the last. This fixes both:

  · CHUNKED: speak sentence-by-sentence, so the first word starts as soon as the
    first sentence is synthesised (lower time-to-first-audio), and
  · CANCELLABLE: a `stop()` (the "stop/wait" backend hook) sets a cancel flag the
    loop checks between sentences AND purges the current sound — so "stop" halts
    speech immediately, not at the end of the paragraph.

Honesty: the `speaking` activity state is driven by REAL playback here (set when a
chunk actually plays, cleared the instant it stops/cancels) — never a guess. And
per-turn timing is recorded so we can measure latency instead of hand-waving.

Engine calls (synthesise / play / interrupt) are injected, so the control logic is
testable with no audio device and works whatever the TTS engine is.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Callable, Optional

_SENT_RE = re.compile(r"[^.!?\n]+[.!?]?", re.S)


def split_sentences(text: str) -> list[str]:
    """Break text into speakable chunks (sentences). Deterministic."""
    text = (text or "").strip()
    if not text:
        return []
    return [s.strip() for s in _SENT_RE.findall(text) if s.strip()]


# ── default engine hooks (real Piper/winsound; safe no-ops when unavailable) ──
def _default_play(wav: bytes) -> None:
    try:
        import winsound
        winsound.PlaySound(wav, winsound.SND_MEMORY)   # blocks until this chunk ends
    except Exception:
        pass


def _default_interrupt() -> None:
    try:
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)   # stop whatever is playing NOW
    except Exception:
        pass


class SpeechController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cancel = threading.Event()        # halts SPEECH
        self._gen_abort = threading.Event()     # halts in-flight GENERATION
        self._speaking = False
        self._generating = False
        self._active_stream = None       # live HTTP stream, so stop() can close it
        self._last_timing: dict = {}

    def mark_generating(self, on: bool) -> None:
        with self._lock:
            self._generating = bool(on)

    def register_stream(self, resp) -> None:
        """Hand the live generation stream to the controller so stop() can close
        it — making WAIT immediate even while blocked waiting on the first token
        (the between-chunks flag alone can't interrupt that wait)."""
        with self._lock:
            self._active_stream = resp

    def is_generating(self) -> bool:
        with self._lock:
            return self._generating

    # ── turn lifecycle (a voice turn = generate → speak) ─────────────────
    def begin_turn(self) -> None:
        """Start a fresh voice turn — clear any prior cancel so a new WAIT only
        affects THIS turn."""
        self._cancel.clear()
        self._gen_abort.clear()

    def generation_aborted(self) -> bool:
        """The streaming generation loop checks this between chunks so WAIT stops
        the model thinking, not just the speaking."""
        return self._gen_abort.is_set()

    # ── truthful state ───────────────────────────────────────────────────
    def is_speaking(self) -> bool:
        with self._lock:
            return self._speaking

    def last_timing(self) -> dict:
        with self._lock:
            return dict(self._last_timing)

    def _activity(self, method: str, *args) -> None:
        try:
            from core.activity_state import get_activity
            getattr(get_activity(), method)(*args)
        except Exception:
            pass

    # ── speak (chunked + cancellable) ────────────────────────────────────
    def speak(self, text: str, synth: Callable[[str], bytes],
              play: Optional[Callable[[bytes], None]] = None,
              background: bool = False, label: str = "Speaking") -> dict:
        """Speak `text` sentence-by-sentence. `synth(sentence) -> wav bytes`.
        background=True returns immediately and speaks on a daemon thread (so an
        API call doesn't block and `stop()` can interrupt it)."""
        sentences = split_sentences(text)
        if not sentences:
            return {"spoken": [], "cancelled": False, "timing": {"chunks": 0}}
        play = play or _default_play
        if background:
            threading.Thread(target=self._run, args=(sentences, synth, play, label),
                             daemon=True).start()
            return {"started": True, "sentences": len(sentences)}
        return self._run(sentences, synth, play, label)

    def _run(self, sentences: list[str], synth: Callable[[str], bytes],
             play: Callable[[bytes], None], label: str) -> dict:
        self._cancel.clear()
        with self._lock:
            self._speaking = True
        self._activity("speaking", label)
        t0 = time.time()
        first_ms: Optional[int] = None
        spoken: list[str] = []
        cancelled = False
        try:
            for sentence in sentences:
                if self._cancel.is_set():
                    cancelled = True
                    break
                audio = synth(sentence)
                if first_ms is None:
                    first_ms = int((time.time() - t0) * 1000)
                if self._cancel.is_set():        # cancelled during synthesis
                    cancelled = True
                    break
                play(audio)                      # blocks for this chunk only
                spoken.append(sentence)
        finally:
            with self._lock:
                self._speaking = False
                self._last_timing = {
                    "chunks": len(spoken),
                    "first_audio_ms": first_ms,
                    "total_ms": int((time.time() - t0) * 1000),
                    "cancelled": cancelled,
                }
            self._activity("idle")
        return {"spoken": spoken, "cancelled": cancelled, "timing": self.last_timing()}

    # ── stop / cancel (the "stop / wait" backend hook) ───────────────────
    def stop(self, interrupt: Optional[Callable[[], None]] = None) -> dict:
        """The WAIT hook. Halt the WHOLE turn: abort in-flight generation AND
        speech (cancel flag + purge the sound playing now). Reports which stages
        were actually live so the UI can say 'stopped speech' vs 'stopped the
        whole turn' honestly."""
        was_speaking = self.is_speaking()
        was_generating = self.is_generating()
        self._gen_abort.set()
        self._cancel.set()
        # Close the live generation stream NOW so a first-token wait unblocks
        # immediately (not just at the next chunk boundary).
        with self._lock:
            stream = self._active_stream
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
        (interrupt or _default_interrupt)()
        with self._lock:
            self._speaking = False
        if was_speaking or was_generating:
            self._activity("idle")
        # scope tells the UI what actually stopped, honestly.
        scope = "speech" if was_speaking else ("thinking" if was_generating else "idle")
        return {"stopped": True, "was_speaking": was_speaking,
                "was_generating": was_generating, "scope": scope}


def stream_chat(model: str, system: str, user: str,
                abort_check: Callable[[], bool],
                options: Optional[dict] = None, timeout: int = 90,
                register: Optional[Callable[[object], None]] = None) -> dict:
    """Stream a reply from local Ollama, checking abort_check() between chunks —
    so a WAIT stops the model mid-thought. Breaking the loop closes the stream,
    which disconnects the client and makes Ollama stop generating server-side.
    `register(resp)` (optional) hands the live response to the controller so a
    concurrent stop() can close it immediately (unblocks a first-token wait).
    Returns {text, aborted, error?} (text is whatever was produced before abort)."""
    import requests
    pieces: list[str] = []
    aborted = False
    err = None
    try:
        with requests.post(
            "http://127.0.0.1:11434/api/chat",
            json={"model": model, "stream": True, "keep_alive": "5m",
                  "options": options or {},
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            stream=True, timeout=timeout) as r:
            if register:
                register(r)
            for line in r.iter_lines():
                if abort_check():
                    aborted = True
                    break
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                piece = (obj.get("message") or {}).get("content") or ""
                if piece:
                    pieces.append(piece)
                if obj.get("done"):
                    break
    except Exception as exc:
        # A close() from stop() surfaces here as a read error — that IS the abort.
        if abort_check():
            aborted = True
        else:
            err = str(exc)[:150]
    finally:
        if register:
            register(None)
    out = {"text": "".join(pieces).strip(), "aborted": aborted}
    if err:
        out["error"] = err
    return out


_controller: Optional[SpeechController] = None
_lock = threading.Lock()


def get_speech() -> SpeechController:
    global _controller
    with _lock:
        if _controller is None:
            _controller = SpeechController()
        return _controller
