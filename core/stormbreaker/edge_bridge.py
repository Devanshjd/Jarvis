"""
J.A.R.V.I.S — Stormbreaker Edge Bridge

WebSocket server that runs on the JARVIS Desktop (PC) and accepts
connections from wearable edge nodes (Mi 11X phone, Pi Zero, future
custom goggles). Receives camera frames + audio + gesture events,
runs them through JARVIS's AI pipeline, and ships TTS audio + commands
back to the wearable.

Architecture:
    Wearable                          JARVIS Desktop
    ────────                          ──────────────
    [camera] ──── JPEG frames ───►   [edge_bridge]
    [mic]    ──── audio chunks ──►        │
    [gesture]──── events ───────►          ▼
                                     vision pipeline
                                     (Ollama, OCR, etc.)
                                          │
    [speaker]◄─── TTS audio ──────         ▼
    [HUD]    ◄─── overlay data ───   response payload

Port: 8766 (NOT 8765 — leaves JARVIS REST API alone)
Auth: HMAC-SHA256 on every message envelope, shared secret stored in
      ~/.jarvis_config.json under stormbreaker.edge_secret
Logging: structured, integrates with JARVIS logging
Heartbeat: ping every 5s, drop connection after 15s silence
Rate limit: at most 2 vision-LLM calls per second per connection
            (frames arriving faster are queued and dropped if backlog > 3)

Run:    python -m core.stormbreaker.edge_bridge
Stop:   Ctrl+C (graceful shutdown drains in-flight requests)

This is the FIXED version. The earlier voice-session file with the same
purpose had broken markdown wrapping, port collision with JARVIS REST,
deprecated APIs, and zero auth. This one is production-shaped.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

# ─── Configuration ────────────────────────────────────────────────────────

PORT = 8766                              # Stormbreaker port — distinct from JARVIS 8765
JARVIS_REST_BASE = "http://127.0.0.1:8765"
HEARTBEAT_INTERVAL = 5.0                 # seconds between pings
CONNECTION_TIMEOUT = 45.0                # disconnect if no message for this long
                                          # (generous: a single gemma3:4b frame analysis
                                          # can take 10-12s; 45s absorbs a few slow frames
                                          # queued behind heartbeats without false-killing)
MIN_FRAME_PROCESS_INTERVAL = 0.5         # max 2 vision LLM calls/sec/connection
MAX_FRAME_BACKLOG = 3                    # drop frames if queue grows past this
MAX_MESSAGE_BYTES = 20 * 1024 * 1024     # 20 MB cap — accommodates 48MP phone cameras at full JPEG quality
                                          # (Mi 11X / similar can produce 5-8 MB frames; iPhone Pro models up to 12 MB)

CONFIG_FILE = Path.home() / ".jarvis_config.json"

logger = logging.getLogger("jarvis.stormbreaker.edge_bridge")


# ─── Shared secret management ─────────────────────────────────────────────

def get_or_create_secret() -> str:
    """Read shared HMAC secret from JARVIS config, create if missing.

    Persisting it in ~/.jarvis_config.json under stormbreaker.edge_secret
    means the same secret is reused across restarts. The phone client gets
    a copy of this secret during setup (printed once, then stored on phone).
    """
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not read config: %s — using empty", e)

    sb = cfg.setdefault("stormbreaker", {})
    secret = sb.get("edge_secret")
    if not secret or not isinstance(secret, str) or len(secret) < 32:
        secret = secrets.token_urlsafe(48)
        sb["edge_secret"] = secret
        try:
            CONFIG_FILE.write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Generated new edge_secret (saved to %s)", CONFIG_FILE)
        except Exception as e:
            logger.error("Could not persist edge_secret: %s", e)
    return secret


# ─── Message protocol ─────────────────────────────────────────────────────

def sign_message(secret: str, payload: bytes) -> str:
    """HMAC-SHA256 of payload — hex-encoded."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    expected = sign_message(secret, payload)
    return hmac.compare_digest(expected, signature)


@dataclass
class IncomingMessage:
    type: str               # "auth" / "frame" / "audio" / "gesture" / "heartbeat" / "status"
    timestamp: float
    data: dict = field(default_factory=dict)
    binary: bytes = b""
    raw_payload: bytes = b""

    @classmethod
    def parse(cls, raw: str | bytes) -> "IncomingMessage":
        """Parse an envelope: {sig, payload: {type, ts, data, binary_b64}}."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        envelope = json.loads(raw)
        sig = envelope.get("sig", "")
        payload_str = envelope.get("payload", "")
        payload_bytes = payload_str.encode("utf-8")
        payload = json.loads(payload_str) if payload_str else {}
        binary = b""
        if payload.get("binary_b64"):
            binary = base64.b64decode(payload["binary_b64"])
        return cls(
            type=payload.get("type", ""),
            timestamp=float(payload.get("ts", time.time())),
            data=payload.get("data") or {},
            binary=binary,
            raw_payload=payload_bytes,
        ), sig


def build_outgoing(
    secret: str,
    msg_type: str,
    data: Optional[dict] = None,
    binary: bytes = b"",
) -> str:
    """Build a signed envelope to send to the wearable."""
    payload = {
        "type": msg_type,
        "ts": time.time(),
        "data": data or {},
    }
    if binary:
        payload["binary_b64"] = base64.b64encode(binary).decode()
    payload_str = json.dumps(payload, ensure_ascii=False)
    sig = sign_message(secret, payload_str.encode("utf-8"))
    envelope = json.dumps({"sig": sig, "payload": payload_str}, ensure_ascii=False)
    return envelope


# ─── JARVIS service integration ───────────────────────────────────────────

def analyze_frame_locally(jpeg_bytes: bytes, prompt: str = "") -> dict:
    """Send a single frame to JARVIS's local vision endpoint.

    JARVIS's /api/screen/analyze takes a screenshot from the host. For
    edge-frame analysis we call Ollama directly with the wearable's frame.
    """
    try:
        # Encode for Ollama
        img_b64 = base64.b64encode(jpeg_bytes).decode()

        # Pick vision-capable model via JARVIS's status endpoint
        try:
            status = requests.get(f"{JARVIS_REST_BASE}/api/vision/status", timeout=3).json()
            model = status.get("active_vision_model") or "gemma3:4b"
        except Exception:
            model = "gemma3:4b"

        question = prompt.strip() or (
            "Briefly describe what is visible in this image. "
            "Focus on the main subject. Under 50 words."
        )

        r = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": model,
                "prompt": question,
                "images": [img_b64],
                "stream": False,
                "keep_alive": "30s",
                "options": {"temperature": 0.3, "num_predict": 150},
            },
            timeout=30,
        )
        if r.status_code == 200:
            text = (r.json().get("response") or "").strip()
            return {"success": True, "text": text, "model": model}
        return {"success": False, "error": f"Ollama HTTP {r.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Analyze failed: {e}"}


# Track whether the JARVIS backend TTS endpoint is reachable so we don't
# spam warnings + waste time on every frame when it's down.
_tts_backend_down_until = 0.0


def transcribe_audio(audio_bytes: bytes) -> str:
    """Send audio to JARVIS's local Whisper STT endpoint. Returns text."""
    try:
        b64 = base64.b64encode(audio_bytes).decode()
        r = requests.post(
            f"{JARVIS_REST_BASE}/api/stt/transcribe",
            json={"audio_base64": b64, "language": "en"},
            timeout=30,
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("success"):
                return (d.get("text") or "").strip()
    except Exception as e:
        logger.warning("STT failed: %s", e)
    return ""


def answer_visual_question(jpeg_bytes: bytes, question: str) -> dict:
    """Answer a specific question about an image using local vision LLM.

    Unlike analyze_frame_locally (which gives a generic description), this
    answers the USER'S question — 'what color is the car?', 'read the sign',
    'is anyone in the room?'. The interactive goggles experience.
    """
    prompt = question.strip() or "Describe what you see."
    # Frame the prompt so the model answers directly + concisely (spoken aloud)
    framed = (
        f"Answer this question about the image directly and concisely, "
        f"in one or two spoken sentences: {prompt}"
    )
    return analyze_frame_locally(jpeg_bytes, framed)


def synthesize_speech(text: str) -> bytes:
    """Call JARVIS's /api/tts/speak to get WAV bytes of synthesized speech.

    If the JARVIS backend (web_main.py, port 8765) isn't running, we back
    off for 30s rather than retrying + logging on every single frame.
    """
    global _tts_backend_down_until
    if time.time() < _tts_backend_down_until:
        return b""  # backend known-down, skip fast

    try:
        r = requests.post(
            f"{JARVIS_REST_BASE}/api/tts/speak",
            json={"text": text[:500], "play": False},  # don't play on host
            timeout=15,
        )
        if r.status_code != 200:
            return b""
        d = r.json()
        if d.get("success") and d.get("audio_base64"):
            return base64.b64decode(d["audio_base64"])
        return b""
    except requests.exceptions.ConnectionError:
        # Backend not running — back off, log once
        if time.time() >= _tts_backend_down_until:
            logger.warning(
                "TTS backend (JARVIS web_main.py on :8765) not running — "
                "audio disabled. Frames still analyzed. Start it with: "
                "python web_main.py"
            )
        _tts_backend_down_until = time.time() + 30.0
        return b""
    except Exception as e:
        logger.warning("TTS synth failed: %s", e)
        return b""


# ─── Per-connection state ────────────────────────────────────────────────

@dataclass
class EdgeConnection:
    websocket: Any                     # WebSocketServerProtocol
    secret: str
    authenticated: bool = False
    last_message_at: float = field(default_factory=time.time)
    last_frame_processed_at: float = 0.0
    pending_frames: int = 0
    client_id: str = ""

    def remote(self) -> str:
        try:
            return f"{self.websocket.remote_address[0]}:{self.websocket.remote_address[1]}"
        except Exception:
            return "(unknown)"


# ─── Main message handler ────────────────────────────────────────────────

async def handle_message(conn: EdgeConnection, raw: str | bytes) -> None:
    """Parse, verify, dispatch a single incoming message."""
    try:
        msg, sig = IncomingMessage.parse(raw)
    except Exception as e:
        logger.warning("Bad message from %s: %s", conn.remote(), e)
        await send_error(conn, "malformed_envelope", str(e))
        return

    if not verify_signature(conn.secret, msg.raw_payload, sig):
        logger.warning("HMAC mismatch from %s — dropping", conn.remote())
        await send_error(conn, "bad_signature", "HMAC verification failed")
        return

    conn.last_message_at = time.time()

    # ── auth must come first ─────────────────────────────────────────
    if msg.type == "auth":
        client_id = msg.data.get("client_id", "unknown")
        conn.client_id = client_id
        conn.authenticated = True
        logger.info("Edge client authenticated: client_id=%r from %s",
                    client_id, conn.remote())
        await send_ack(conn, "auth", {"server_version": "stormbreaker-edge/0.1"})
        return

    if not conn.authenticated:
        await send_error(conn, "not_authenticated", "send auth message first")
        return

    # ── heartbeat ────────────────────────────────────────────────────
    if msg.type == "heartbeat":
        await send_ack(conn, "heartbeat", {"server_ts": time.time()})
        return

    # ── frame from camera ────────────────────────────────────────────
    if msg.type == "frame":
        await handle_frame(conn, msg)
        return

    # ── gesture event ────────────────────────────────────────────────
    if msg.type == "gesture":
        gesture = msg.data.get("name", "")
        logger.info("Gesture from %s: %s", conn.client_id, gesture)
        await send_ack(conn, "gesture", {"received": gesture})
        # TODO v1: trigger JARVIS skill based on gesture
        return

    # ── audio chunk (standalone STT) ─────────────────────────────────
    if msg.type == "audio":
        # Transcribe and send back the text
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, transcribe_audio, msg.binary)
        await send_message(conn, "transcript", {"text": text})
        return

    # ── interactive query: frame + spoken question → answer ──────────
    # This is the real goggles experience: user asks a question (audio),
    # a frame is attached, we transcribe -> answer about the image -> speak.
    if msg.type == "query":
        await handle_query(conn, msg)
        return

    # ── status update ────────────────────────────────────────────────
    if msg.type == "status":
        logger.info("Edge status from %s: %s", conn.client_id, msg.data)
        await send_ack(conn, "status", {})
        return

    logger.warning("Unknown message type from %s: %r", conn.client_id, msg.type)
    await send_error(conn, "unknown_type", f"unhandled type: {msg.type}")


async def handle_frame(conn: EdgeConnection, msg: IncomingMessage) -> None:
    """Process a camera frame: rate-limit, analyze with vision LLM, ship TTS back."""
    now = time.time()
    elapsed = now - conn.last_frame_processed_at
    if elapsed < MIN_FRAME_PROCESS_INTERVAL:
        # Drop frame — arriving too fast
        await send_ack(conn, "frame", {"dropped": True, "reason": "rate_limit"})
        return

    if conn.pending_frames >= MAX_FRAME_BACKLOG:
        await send_ack(conn, "frame", {"dropped": True, "reason": "backlog_full"})
        return

    if not msg.binary or len(msg.binary) < 200:
        await send_error(conn, "bad_frame", "frame binary too small")
        return

    conn.pending_frames += 1
    conn.last_frame_processed_at = now

    prompt = msg.data.get("prompt", "")
    speak_result = bool(msg.data.get("speak", True))

    # Run analysis in a thread so we don't block the event loop
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None, analyze_frame_locally, msg.binary, prompt,
        )
    finally:
        conn.pending_frames -= 1

    if not result.get("success"):
        await send_error(conn, "analyze_failed", result.get("error", "unknown"))
        return

    text = result.get("text", "")
    logger.info("Frame analyzed (model=%s, %d chars): %s",
                result.get("model"), len(text), text[:80])

    # Send the text result back
    await send_message(conn, "analysis", {
        "text": text,
        "model": result.get("model"),
        "latency_ms": int((time.time() - now) * 1000),
    })

    # Optionally synthesize speech and ship audio back
    if speak_result and text:
        wav_bytes = await loop.run_in_executor(None, synthesize_speech, text)
        if wav_bytes:
            await send_message(conn, "tts_audio", {"format": "wav"}, binary=wav_bytes)


async def handle_query(conn: EdgeConnection, msg: IncomingMessage) -> None:
    """Interactive Q&A: user's spoken question + a camera frame → answer.

    The message carries:
      - binary: the JPEG frame (what the user is looking at)
      - data.audio_b64: base64 audio of the spoken question (optional)
      - data.question: text question (optional — if voice not used)

    Flow: transcribe audio (if present) → answer the question about the
    image via vision LLM → synthesize speech → ship text + audio back.
    """
    loop = asyncio.get_running_loop()

    jpeg = msg.binary
    if not jpeg or len(jpeg) < 200:
        await send_error(conn, "bad_query", "no frame attached to query")
        return

    # Get the question — from attached audio or from text field
    question = (msg.data.get("question") or "").strip()
    audio_b64 = msg.data.get("audio_b64", "")
    if audio_b64 and not question:
        try:
            audio_bytes = base64.b64decode(audio_b64)
            question = await loop.run_in_executor(None, transcribe_audio, audio_bytes)
            logger.info("Query transcribed: %r", question)
        except Exception as e:
            logger.warning("Query audio decode failed: %s", e)

    if not question:
        question = "What am I looking at?"

    # Answer the question about the image
    t0 = time.time()
    result = await loop.run_in_executor(
        None, answer_visual_question, jpeg, question,
    )
    if not result.get("success"):
        await send_error(conn, "query_failed", result.get("error", "unknown"))
        return

    answer = result.get("text", "")
    logger.info("Query answered (%dms): Q=%r A=%r",
                int((time.time() - t0) * 1000), question[:40], answer[:80])

    # Ship the answer back — both text and speech
    await send_message(conn, "answer", {
        "question": question,
        "text": answer,
        "latency_ms": int((time.time() - t0) * 1000),
    })
    wav_bytes = await loop.run_in_executor(None, synthesize_speech, answer)
    if wav_bytes:
        await send_message(conn, "tts_audio", {"format": "wav"}, binary=wav_bytes)


# ─── Outgoing helpers ────────────────────────────────────────────────────

async def send_message(
    conn: EdgeConnection,
    msg_type: str,
    data: Optional[dict] = None,
    binary: bytes = b"",
) -> None:
    try:
        envelope = build_outgoing(conn.secret, msg_type, data or {}, binary)
        await conn.websocket.send(envelope)
    except ConnectionClosed:
        pass
    except Exception as e:
        logger.warning("send_message failed: %s", e)


async def send_ack(conn: EdgeConnection, msg_type: str, data: Optional[dict] = None) -> None:
    await send_message(conn, "ack", {"of": msg_type, **(data or {})})


async def send_error(conn: EdgeConnection, code: str, message: str) -> None:
    await send_message(conn, "error", {"code": code, "message": message})


# ─── Connection lifecycle ────────────────────────────────────────────────

async def heartbeat_watchdog(conn: EdgeConnection) -> None:
    """Send periodic pings; close connection if peer stops responding."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if time.time() - conn.last_message_at > CONNECTION_TIMEOUT:
                logger.info("Closing dead connection from %s (no msg in %.1fs)",
                            conn.remote(), CONNECTION_TIMEOUT)
                try:
                    await conn.websocket.close(code=1001, reason="timeout")
                except Exception:
                    pass
                return
            if conn.authenticated:
                await send_message(conn, "ping", {"server_ts": time.time()})
    except asyncio.CancelledError:
        pass


async def handle_connection(websocket) -> None:
    """Per-client handler. Spawns a watchdog and processes messages."""
    secret = get_or_create_secret()
    conn = EdgeConnection(websocket=websocket, secret=secret)
    logger.info("Edge connection opened from %s", conn.remote())

    watchdog = asyncio.create_task(heartbeat_watchdog(conn))
    try:
        async for raw in websocket:
            try:
                await handle_message(conn, raw)
            except Exception as e:
                logger.exception("Error handling message: %s", e)
                await send_error(conn, "internal", str(e)[:200])
    except (ConnectionClosedOK, ConnectionClosedError):
        pass
    except Exception as e:
        logger.exception("Connection handler crashed: %s", e)
    finally:
        watchdog.cancel()
        try:
            await watchdog
        except Exception:
            pass
        logger.info("Edge connection closed from %s (client=%r)",
                    conn.remote(), conn.client_id)


# ─── Server entry point ──────────────────────────────────────────────────

async def serve(host: str = "0.0.0.0", port: int = PORT) -> None:
    secret = get_or_create_secret()
    logger.info("Stormbreaker edge_bridge starting on ws://%s:%d", host, port)
    logger.info("Shared secret loaded (first 8 chars: %s...)", secret[:8])
    logger.info("Phone client must use the same secret — see setup guide")

    stop_event = asyncio.Event()

    def _request_stop() -> None:
        logger.info("Shutdown requested — closing server")
        stop_event.set()

    # Graceful shutdown on Ctrl+C
    try:
        loop = asyncio.get_running_loop()
        for sig_name in ("SIGINT", "SIGTERM"):
            if hasattr(signal, sig_name):
                try:
                    loop.add_signal_handler(getattr(signal, sig_name), _request_stop)
                except NotImplementedError:
                    pass  # Windows doesn't always support signal handlers
    except Exception:
        pass

    async with websockets.serve(
        handle_connection, host, port,
        max_size=MAX_MESSAGE_BYTES,
        ping_interval=30,    # bumped from 20 — slow AI inference can block client briefly
        ping_timeout=60,     # bumped from 20 — give Pi-class clients headroom during heavy work
    ) as server:
        logger.info("Stormbreaker edge_bridge READY — waiting for edge clients")
        await stop_event.wait()
        logger.info("Stopping server...")
        server.close()
        await server.wait_closed()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
