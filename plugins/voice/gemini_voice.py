"""
J.A.R.V.I.S - Gemini Live voice engine.

This module owns a single Gemini Live session end-to-end:
- one microphone capture path
- one audio playback path
- one async websocket session
- direct Gemini tool calling into the JARVIS executor

Unlike the old experimental version, this engine does not mix ad-hoc event
loops and thread-local run_until_complete calls. The live session runs on one
asyncio loop in one background thread, while audio capture/playback stay in
simple worker threads.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Any

try:
    import pyaudio

    HAS_PYAUDIO = True
except ImportError:
    pyaudio = None
    HAS_PYAUDIO = False

try:
    from google import genai
    from google.genai import types

    HAS_GENAI = True
except ImportError:
    genai = None
    types = None
    HAS_GENAI = False

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 1024
FORMAT_PA = pyaudio.paInt16 if HAS_PYAUDIO else None

LEGACY_LIVE_MODELS = {
    "gemini-2.0-flash-live": "gemini-3.1-flash-live-preview",
    "gemini-2.0-flash-live-preview": "gemini-3.1-flash-live-preview",
    "gemini-live-2.0-flash": "gemini-3.1-flash-live-preview",
}

LEGACY_VOICE_NAMES = {
    "en-default": "Kore",
    "default": "Kore",
}

logger = logging.getLogger("jarvis.voice.gemini")


class GeminiVoiceEngine:
    """
    Proper Gemini Live session owner for JARVIS voice.

    The model remains the live conversational interface while tools are routed
    into the existing JARVIS executor, so the voice layer can act without
    competing with the classic STT/TTS pipeline.
    """

    def __init__(self, api_key: str, jarvis=None, model: str = "gemini-3.1-flash-live-preview"):
        self.api_key = api_key
        self.jarvis = jarvis
        self.model = self._resolve_model(model)

        self.on_transcript = None
        self.on_response = None
        self.on_state_change = None

        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = None
        self._session = None

        self._audio = None
        self._input_stream = None
        self._output_stream = None
        self._capture_thread: threading.Thread | None = None
        self._playback_thread: threading.Thread | None = None

        self._session_ready = threading.Event()
        self._stop_event = threading.Event()
        self._playback_queue: queue.Queue[bytes | None] = queue.Queue()
        self._input_queue: asyncio.Queue[bytes | None] | None = None

        self._speaking_lock = threading.Lock()
        self._pending_output_chunks = 0
        self._turn_audio_complete = False
        self._suppress_output_callback = False
        self._last_output_text = ""
        self._last_input_text = ""

        self.is_speaking = False
        self._mic_pause_until = 0.0
        self._state = "idle"

    def is_available(self) -> bool:
        return HAS_GENAI and HAS_PYAUDIO and bool(self.api_key)

    def uses_native_audio(self) -> bool:
        return True

    def start(self) -> bool:
        """Start the live engine and keep one session alive in the background."""
        if not self.is_available():
            missing = []
            if not HAS_GENAI:
                missing.append("google-genai")
            if not HAS_PYAUDIO:
                missing.append("pyaudio")
            if not self.api_key:
                missing.append("Gemini API key")
            logger.warning("Cannot start Gemini Live voice: missing %s", ", ".join(missing))
            return False

        if self._running:
            return True

        self._running = True
        self._stop_event.clear()
        self._session_ready.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            daemon=True,
            name="jarvis-gemini-live",
        )
        self._thread.start()

        ready = self._session_ready.wait(timeout=15.0)
        if not ready:
            logger.warning("Gemini Live session did not become ready in time.")
        return ready

    def stop(self):
        """Stop the live session and all audio workers."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()
        self._session_ready.clear()

        if self._loop and self._loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)
                future.result(timeout=5)
            except Exception:
                pass

        self._playback_queue.put(None)

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2)
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=2)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        self._thread = None
        self._capture_thread = None
        self._playback_thread = None
        self._notify_state("idle")

    def set_listening(self, on: bool):
        """Compatibility wrapper used by the existing voice plugin."""
        if on:
            self.start()
        else:
            self.stop()

    def speak_text(self, text: str) -> bool:
        """
        Ask Gemini to speak a prepared reply.

        This is used when text interactions outside the live voice turn still
        need spoken output while the native Gemini session is active.
        """
        clean = (text or "").strip()
        if not clean:
            return False
        if not self.start():
            return False

        prompt = (
            "Speak the following JARVIS reply naturally and clearly. "
            "Do not add any introduction, explanation, or extra words.\n\n"
            f"{clean}"
        )
        self._suppress_output_callback = True
        return self._send_text(prompt)

    @property
    def active(self) -> bool:
        return self._running and self._session is not None and self._session_ready.is_set()

    def _thread_main(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run())
        except Exception:
            logger.exception("Gemini Live engine crashed")
        finally:
            try:
                self._loop.run_until_complete(self._async_cleanup())
            except Exception:
                pass
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    async def _run(self):
        self._client = genai.Client(api_key=self.api_key)
        self._input_queue = asyncio.Queue(maxsize=24)
        self._start_playback_thread()

        while self._running and not self._stop_event.is_set():
            try:
                self._notify_state("connecting")
                async with self._client.aio.live.connect(
                    model=self.model,
                    config=self._build_connect_config(),
                ) as session:
                    self._session = session
                    self._session_ready.set()
                    self._start_capture_thread()
                    self._notify_state("listening")

                    send_task = asyncio.create_task(self._send_audio_loop(session))
                    receive_task = asyncio.create_task(self._receive_loop(session))
                    done, pending = await asyncio.wait(
                        {send_task, receive_task},
                        return_when=asyncio.FIRST_EXCEPTION,
                    )

                    for task in pending:
                        task.cancel()
                    for task in done:
                        exc = task.exception()
                        if exc:
                            raise exc
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._running:
                    logger.warning("Gemini Live session error: %s", exc)
                    self._notify_state("error")
                    await asyncio.sleep(2.0)
            finally:
                self._session = None
                self._session_ready.clear()
                self._stop_capture_stream()
                await self._drain_input_queue()

        self._running = False

    async def _async_stop(self):
        self._running = False
        self._stop_event.set()
        await self._async_cleanup()

    async def _async_cleanup(self):
        session = self._session
        self._session = None
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
        self._stop_capture_stream()
        self._stop_playback_stream()
        await self._drain_input_queue()
        self._session_ready.clear()

    async def _drain_input_queue(self):
        if self._input_queue is None:
            return
        try:
            while True:
                self._input_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    def _start_capture_thread(self):
        if self._capture_thread and self._capture_thread.is_alive():
            return
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="jarvis-gemini-mic",
        )
        self._capture_thread.start()

    def _start_playback_thread(self):
        if self._playback_thread and self._playback_thread.is_alive():
            return
        self._playback_thread = threading.Thread(
            target=self._playback_loop,
            daemon=True,
            name="jarvis-gemini-audio",
        )
        self._playback_thread.start()

    def _ensure_audio(self):
        if self._audio is None and HAS_PYAUDIO:
            self._audio = pyaudio.PyAudio()

    def _capture_loop(self):
        try:
            self._ensure_audio()
            self._input_stream = self._audio.open(
                format=FORMAT_PA,
                channels=CHANNELS,
                rate=INPUT_SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )

            while self._running and not self._stop_event.is_set():
                if not self._session_ready.is_set() or self._loop is None or self._input_queue is None:
                    time.sleep(0.05)
                    continue
                if self.is_speaking or time.time() < self._mic_pause_until:
                    time.sleep(0.02)
                    continue

                data = self._input_stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if not data:
                    continue

                def _push(chunk=data):
                    if self._input_queue is None:
                        return
                    if self._input_queue.full():
                        try:
                            self._input_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    try:
                        self._input_queue.put_nowait(chunk)
                    except asyncio.QueueFull:
                        pass

                self._loop.call_soon_threadsafe(_push)
        except Exception as exc:
            if self._running:
                logger.warning("Gemini mic capture error: %s", exc)
        finally:
            self._stop_capture_stream()

    def _playback_loop(self):
        try:
            self._ensure_audio()
            self._output_stream = self._audio.open(
                format=FORMAT_PA,
                channels=CHANNELS,
                rate=OUTPUT_SAMPLE_RATE,
                output=True,
                frames_per_buffer=CHUNK_SIZE,
            )

            while self._running or not self._playback_queue.empty():
                chunk = self._playback_queue.get()
                if chunk is None:
                    break
                if not chunk:
                    continue
                self._output_stream.write(chunk)
                self._mark_output_chunk_played()
        except Exception as exc:
            if self._running:
                logger.warning("Gemini playback error: %s", exc)
        finally:
            self._stop_playback_stream()

    async def _send_audio_loop(self, session):
        while self._running and not self._stop_event.is_set():
            if self._input_queue is None:
                await asyncio.sleep(0.05)
                continue

            chunk = await self._input_queue.get()
            if chunk is None:
                break

            await session.send_realtime_input(
                audio=types.Blob(
                    data=chunk,
                    mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}",
                )
            )

    async def _receive_loop(self, session):
        async for message in session.receive():
            if not self._running or self._stop_event.is_set():
                break

            server_content = getattr(message, "server_content", None)
            if server_content:
                self._handle_server_content(server_content)

            tool_call = getattr(message, "tool_call", None)
            if tool_call and getattr(tool_call, "function_calls", None):
                self._notify_state("acting")
                responses = await asyncio.to_thread(
                    self._execute_function_calls,
                    list(tool_call.function_calls),
                )
                if responses:
                    await session.send_tool_response(function_responses=responses)
                self._notify_state("thinking")

    def _handle_server_content(self, server_content):
        transcript = getattr(server_content, "input_transcription", None)
        if transcript and getattr(transcript, "text", None):
            text = transcript.text.strip()
            if text:
                self._last_input_text = text
                if self.on_transcript:
                    self.on_transcript(text, bool(getattr(transcript, "finished", False)))

        output_transcript = getattr(server_content, "output_transcription", None)
        if output_transcript and getattr(output_transcript, "text", None):
            text = output_transcript.text.strip()
            if text:
                self._last_output_text = text

        model_turn = getattr(server_content, "model_turn", None)
        if model_turn and getattr(model_turn, "parts", None):
            for part in model_turn.parts:
                inline = getattr(part, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    self._mark_output_chunk_enqueued()
                    self._playback_queue.put(inline.data)
                elif getattr(part, "text", None):
                    self._last_output_text = part.text.strip()

        if getattr(server_content, "turn_complete", False) or getattr(server_content, "generation_complete", False):
            self._turn_audio_complete = True
            self._finalize_output_turn()

    def _execute_function_calls(self, function_calls: list[Any]) -> list[Any]:
        responses = []
        for call in function_calls:
            name = getattr(call, "name", "") or ""
            args = dict(getattr(call, "args", None) or {})
            call_id = getattr(call, "id", None) or f"jarvis_call_{int(time.time() * 1000)}"

            payload = self._run_tool(name, args)
            response = types.FunctionResponse(
                id=call_id,
                name=name,
                response=payload,
            )
            responses.append(response)
        return responses

    def _run_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if not self.jarvis or not hasattr(self.jarvis, "orchestrator"):
                return {
                    "success": False,
                    "error": "JARVIS runtime is not attached.",
                }

            executor = self.jarvis.orchestrator.executor
            result = executor.execute(name, args)
            payload: dict[str, Any] = {
                "success": bool(result.success),
                "output": result.output or "",
                "error": result.error or "",
            }
            if result.data:
                payload["data"] = result.data
            return payload
        except Exception as exc:
            logger.exception("Gemini tool execution failed for %s", name)
            return {
                "success": False,
                "error": str(exc),
            }

    def _build_connect_config(self):
        voice_cfg = getattr(self.jarvis, "config", {}).get("voice", {}) if self.jarvis else {}
        raw_voice_name = str(voice_cfg.get("gemini_voice_name", "Kore")).strip()
        voice_name = LEGACY_VOICE_NAMES.get(raw_voice_name, raw_voice_name or "Kore")

        system = self._build_system_instruction()
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name,
                    )
                )
            ),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    prefix_padding_ms=160,
                    silence_duration_ms=640,
                ),
                activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
                turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(
                    target_tokens=8192,
                )
            ),
            system_instruction=system,
            tools=self._build_tool_declarations(),
        )
        return config

    def _build_tool_declarations(self):
        try:
            from core.tool_schemas import TOOL_SCHEMAS

            declarations = []
            for schema in TOOL_SCHEMAS:
                declarations.append(
                    types.FunctionDeclaration(
                        name=schema["name"],
                        description=schema["description"],
                        parameters_json_schema=schema["input_schema"],
                    )
                )
            return [types.Tool(function_declarations=declarations)]
        except Exception as exc:
            logger.warning("Gemini tool declaration build failed: %s", exc)
            return None

    def _build_system_instruction(self) -> str:
        instruction = (
            "You are J.A.R.V.I.S, Dev's live desktop operator in a Gemini Live voice session. "
            "Respond with short, natural spoken answers. Do not use markdown, bullets, JSON, or code fences. "
            "Use the provided tools for actionable requests instead of only explaining what you would do. "
            "If you need missing details, ask a short direct question. "
            "Before state-changing actions like sending messages, typing, clicking, opening sensitive sites, "
            "running commands, logging in, or modifying files, ask for confirmation unless the user has already "
            "clearly confirmed in the current exchange. "
            "Keep the tone confident, calm, and helpful."
        )

        if self.jarvis:
            context_parts: list[str] = []
            try:
                from core.context_injector import ContextInjector

                injected = ContextInjector(self.jarvis).build_context()
                if injected:
                    context_parts.append(injected)
            except Exception:
                pass

            try:
                summary = self.jarvis.state_registry.describe_for_user()
                if summary:
                    context_parts.append(summary)
            except Exception:
                pass

            if context_parts:
                joined = "\n\n".join(part.strip() for part in context_parts if part and part.strip())
                instruction = f"{instruction}\n\n{joined[:4000]}"

        return instruction

    def _send_text(self, text: str) -> bool:
        if not text or not self._loop or not self.active:
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._session.send_realtime_input(text=text),
                self._loop,
            )
            future.result(timeout=10)
            return True
        except Exception as exc:
            logger.warning("Gemini text submit failed: %s", exc)
            return False

    def _mark_output_chunk_enqueued(self):
        with self._speaking_lock:
            self._pending_output_chunks += 1
            self._turn_audio_complete = False
            self.is_speaking = True
            self._mic_pause_until = time.time() + 0.6
        self._notify_state("speaking")

    def _mark_output_chunk_played(self):
        with self._speaking_lock:
            if self._pending_output_chunks > 0:
                self._pending_output_chunks -= 1
            self._mic_pause_until = time.time() + 0.45
            should_finish = self._turn_audio_complete and self._pending_output_chunks == 0
        if should_finish:
            self._finalize_output_turn()

    def _finalize_output_turn(self):
        callback_text = self._last_output_text.strip()
        should_callback = bool(callback_text) and not self._suppress_output_callback
        with self._speaking_lock:
            if self._pending_output_chunks > 0:
                return
            self.is_speaking = False
            self._turn_audio_complete = False
            self._mic_pause_until = time.time() + 0.25
        self._notify_state("listening" if self._running else "idle")

        if should_callback and self.on_response:
            self.on_response(callback_text)
        self._suppress_output_callback = False
        self._last_output_text = ""

    def _notify_state(self, state: str):
        if state == self._state:
            return
        self._state = state
        if self.on_state_change:
            try:
                self.on_state_change(state)
            except Exception:
                logger.debug("Gemini state callback failed", exc_info=True)

    def _stop_capture_stream(self):
        stream = self._input_stream
        self._input_stream = None
        if stream is not None:
            try:
                stream.stop_stream()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    def _stop_playback_stream(self):
        stream = self._output_stream
        self._output_stream = None
        if stream is not None:
            try:
                stream.stop_stream()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        if self._audio is not None:
            try:
                self._audio.terminate()
            except Exception:
                pass
            self._audio = None

    @staticmethod
    def _resolve_model(model_name: str) -> str:
        raw = (model_name or "").strip()
        if not raw:
            return "gemini-3.1-flash-live-preview"
        return LEGACY_LIVE_MODELS.get(raw, raw)


def create_gemini_voice(jarvis) -> GeminiVoiceEngine | None:
    """Create a Gemini Live engine from JARVIS config."""
    if not HAS_GENAI or not HAS_PYAUDIO:
        return None

    config = getattr(jarvis, "config", {})
    gemini_cfg = config.get("gemini", {})
    api_key = gemini_cfg.get("api_key", "")
    if not api_key:
        return None

    return GeminiVoiceEngine(
        api_key=api_key,
        jarvis=jarvis,
        model=gemini_cfg.get("live_model", "gemini-3.1-flash-live-preview"),
    )
