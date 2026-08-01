"""
Voice-control tests — cancellable, chunked, truthful backend speech.

No audio device is touched: the synth/play hooks are injected. What's proven:
  · text is spoken sentence-by-sentence, in order,
  · `is_speaking()` is true only while a chunk is actually playing,
  · stop() interrupts mid-reply (the "stop/wait" hook) — the rest is not played,
  · a fresh speak() starts clean (a prior stop doesn't poison it),
  · per-turn timing (chunks, time-to-first-audio) is recorded.

Run:  python training/test_voice_control.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.voice_control import SpeechController, split_sentences

_NULL = lambda: None                                   # a no-op interrupt (no winsound)


def test_split_sentences() -> None:
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert split_sentences("   ") == []


def test_speaks_all_chunks_in_order() -> None:
    c = SpeechController()
    played: list[str] = []
    r = c.speak("One. Two. Three.", synth=lambda s: s.encode(),
                play=lambda w: played.append(w.decode()))
    assert r["cancelled"] is False
    assert played == ["One.", "Two.", "Three."], played
    assert r["timing"]["chunks"] == 3 and r["timing"]["first_audio_ms"] is not None
    assert c.is_speaking() is False, "must settle to not-speaking when done"


def test_is_speaking_only_while_playing() -> None:
    c = SpeechController()
    assert c.is_speaking() is False
    seen: list[bool] = []
    c.speak("Hi there. Again.", synth=lambda s: b"x",
            play=lambda w: seen.append(c.is_speaking()))
    assert seen and all(seen), "is_speaking must be true during playback"
    assert c.is_speaking() is False


def test_stop_interrupts_mid_reply() -> None:
    c = SpeechController()
    played: list[bytes] = []

    def play(w):
        played.append(w)
        if len(played) == 1:                           # user says "stop" on chunk 1
            c.stop(interrupt=_NULL)

    r = c.speak("A. B. C. D.", synth=lambda s: s.encode(), play=play)
    assert r["cancelled"] is True, "stop() must mark the turn cancelled"
    assert len(played) == 1, "the rest of the reply must not play"
    assert c.is_speaking() is False
    assert r["timing"]["cancelled"] is True


def test_stop_when_idle_is_honest() -> None:
    c = SpeechController()
    r = c.stop(interrupt=_NULL)
    assert r["was_speaking"] is False, "nothing was playing — say so"


def test_fresh_speak_clears_prior_cancel() -> None:
    c = SpeechController()
    c.stop(interrupt=_NULL)                             # sets the cancel flag
    played: list[int] = []
    r = c.speak("One. Two.", synth=lambda s: b"x", play=lambda w: played.append(1))
    assert r["cancelled"] is False and len(played) == 2, "a new turn must start fresh"


def test_empty_text_is_a_noop() -> None:
    c = SpeechController()
    r = c.speak("   ", synth=lambda s: b"x", play=lambda w: None)
    assert r["spoken"] == [] and r["cancelled"] is False


def test_stop_scope_is_reported_honestly() -> None:
    c = SpeechController()
    # idle → nothing was live
    assert c.stop(interrupt=_NULL)["scope"] == "idle"
    # mid-generation → WAIT stops the THINKING
    c.begin_turn()
    c.mark_generating(True)
    r = c.stop(interrupt=_NULL)
    assert r["scope"] == "thinking" and r["was_generating"] is True
    # mid-speech → WAIT stops the SPEECH (tested via the play hook)
    c2 = SpeechController()
    scopes: list[str] = []
    c2.speak("A. B.", synth=lambda s: b"x",
             play=lambda w: scopes.append(c2.stop(interrupt=_NULL)["scope"]))
    assert scopes and scopes[0] == "speech"


def test_stop_closes_the_registered_stream() -> None:
    c = SpeechController()

    class _Stream:
        def __init__(self): self.closed = False
        def close(self): self.closed = True

    s = _Stream()
    c.begin_turn()
    c.mark_generating(True)
    c.register_stream(s)
    c.stop(interrupt=_NULL)
    assert s.closed is True, "stop() must close the live stream (unblocks first-token wait)"


def test_stream_chat_assembles_then_aborts() -> None:
    from core import voice_control
    import requests as _rq

    class _Resp:
        def __init__(self, lines): self.lines = lines
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_lines(self):
            for ln in self.lines:
                yield ln

    lines = [b'{"message":{"content":"Hello "}}',
             b'{"message":{"content":"world."}}',
             b'{"done":true}']
    orig = _rq.post
    _rq.post = lambda *a, **k: _Resp(lines)
    try:
        full = voice_control.stream_chat("m", "sys", "hi", abort_check=lambda: False)
        assert full["aborted"] is False and full["text"] == "Hello world."

        calls = {"n": 0}
        def abort():                       # abort after the first chunk is consumed
            calls["n"] += 1
            return calls["n"] > 1
        cut = voice_control.stream_chat("m", "sys", "hi", abort_check=abort)
        assert cut["aborted"] is True, "must stop streaming when abort fires"
        assert cut["text"] == "Hello", "returns whatever was produced before abort"
    finally:
        _rq.post = orig


def main() -> None:
    tests = [
        ("split into sentences", test_split_sentences),
        ("speaks all chunks in order", test_speaks_all_chunks_in_order),
        ("is_speaking only while playing", test_is_speaking_only_while_playing),
        ("stop interrupts mid-reply", test_stop_interrupts_mid_reply),
        ("stop when idle is honest", test_stop_when_idle_is_honest),
        ("fresh speak clears prior cancel", test_fresh_speak_clears_prior_cancel),
        ("empty text is a no-op", test_empty_text_is_a_noop),
        ("stop scope reported honestly", test_stop_scope_is_reported_honestly),
        ("stop closes the registered stream", test_stop_closes_the_registered_stream),
        ("stream_chat assembles then aborts", test_stream_chat_assembles_then_aborts),
    ]
    print("=" * 64)
    print(" VOICE-CONTROL TESTS")
    print("=" * 64)
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as exc:
            import traceback
            print(f"  [FAIL] {name} -> {exc}")
            traceback.print_exc()
    print(f"\n  {passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    main()
