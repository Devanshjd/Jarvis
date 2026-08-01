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
        self._cancel = threading.Event()
        self._speaking = False
        self._last_timing: dict = {}

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
        """Halt speech immediately: flag cancellation (so the loop stops queuing
        chunks) and purge the sound that's playing right now."""
        was = self.is_speaking()
        self._cancel.set()
        (interrupt or _default_interrupt)()
        with self._lock:
            self._speaking = False
        if was:
            self._activity("idle")
        return {"stopped": True, "was_speaking": was}


_controller: Optional[SpeechController] = None
_lock = threading.Lock()


def get_speech() -> SpeechController:
    global _controller
    with _lock:
        if _controller is None:
            _controller = SpeechController()
        return _controller
