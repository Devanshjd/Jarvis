"""
J.A.R.V.I.S — Stormbreaker Phone Client

Runs on the Mi 11X (or any Android phone) inside Termux. Captures
camera frames via termux-api, streams them over WebSocket to the
edge_bridge running on the JARVIS Desktop PC, plays received TTS
audio through the phone speakers/Bluetooth earbuds.

This is the wearable side of v0 — phone in your shirt pocket acting as
a body-cam relay. The PC does the heavy AI; the phone is a sensor relay.

Setup (one time):
    pkg install python termux-api ffmpeg
    pip install websockets requests

    Then on the Mi 11X:
    1. Install Termux:API from F-Droid (the companion app)
    2. Grant camera + audio + storage permissions
    3. Copy this file + config to ~/storage/shared/Stormbreaker/
    4. Run: python phone_client.py

Config file (config.json next to this script):
    {
        "server_host": "192.168.1.X",   # JARVIS Desktop IP on your LAN
        "server_port": 8766,
        "client_id": "mi11x-pocket",
        "shared_secret": "<paste from PC's ~/.jarvis_config.json>",
        "frame_interval_s": 2.0,
        "camera_id": 0,                  # 0 = rear, 1 = front
        "speak_responses": true
    }

After setup, every frame_interval_s seconds the phone captures a JPEG,
ships it to the PC, gets back an analysis text + spoken audio.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    import websockets
    from websockets.client import connect as ws_connect
    from websockets.exceptions import ConnectionClosed
except ImportError:
    print("ERROR: pip install websockets")
    sys.exit(1)

# ─── Configuration ────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "server_host": "192.168.1.100",
    "server_port": 8766,
    "client_id": "mi11x-pocket",
    "shared_secret": "REPLACE_WITH_SECRET_FROM_JARVIS_CONFIG",
    "frame_interval_s": 2.0,
    "camera_id": 0,
    "speak_responses": True,
    "frame_quality": 70,
    "reconnect_delay_s": 5.0,
    "heartbeat_interval_s": 5.0,
}

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
TEMP_FRAME_PATH = Path("/data/data/com.termux/files/usr/tmp/stormbreaker_frame.jpg")
TEMP_AUDIO_PATH = Path("/data/data/com.termux/files/usr/tmp/stormbreaker_audio.wav")

logger = logging.getLogger("stormbreaker.phone_client")


def load_config() -> dict:
    """Load config.json, create default if missing."""
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(
            json.dumps(DEFAULT_CONFIG, indent=2),
            encoding="utf-8",
        )
        logger.warning("Created default config at %s — EDIT IT before running again",
                       CONFIG_FILE)
        logger.warning("You need to set: server_host, shared_secret")
        sys.exit(1)
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    # Validate critical fields
    if cfg.get("shared_secret", "").startswith("REPLACE"):
        logger.error("shared_secret not set in config.json — copy from PC's ~/.jarvis_config.json under stormbreaker.edge_secret")
        sys.exit(1)
    if not cfg.get("server_host") or cfg["server_host"] == "192.168.1.100":
        logger.warning("server_host looks like the default — set your PC's actual LAN IP")
    return cfg


# ─── Message protocol — must match edge_bridge.py ────────────────────────

def sign_message(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def build_envelope(
    secret: str,
    msg_type: str,
    data: Optional[dict] = None,
    binary: bytes = b"",
) -> str:
    payload = {
        "type": msg_type,
        "ts": time.time(),
        "data": data or {},
    }
    if binary:
        payload["binary_b64"] = base64.b64encode(binary).decode()
    payload_str = json.dumps(payload, ensure_ascii=False)
    sig = sign_message(secret, payload_str.encode("utf-8"))
    return json.dumps({"sig": sig, "payload": payload_str}, ensure_ascii=False)


def parse_incoming(raw: str | bytes) -> dict:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    envelope = json.loads(raw)
    payload = json.loads(envelope.get("payload", "{}"))
    return payload


# ─── Termux:API wrappers — capture camera, play audio ────────────────────

def is_termux() -> bool:
    """Detect if we're running inside Termux on Android."""
    return "com.termux" in os.environ.get("PREFIX", "") or Path("/data/data/com.termux").exists()


def _downscale_jpeg(jpeg_bytes: bytes, max_dim: int = 1280, quality: int = 70) -> bytes:
    """Resize a JPEG to fit within max_dim on the longest side.

    Flagship phones (Mi 11X = 48MP, recent iPhones = 12-48MP) produce
    full-resolution JPEGs that are 5-12 MB each. That's wasteful for
    AI vision (the models downscale internally anyway) and risks hitting
    WebSocket message size limits. We resize down to 1280px max longest
    side — about 1080p, ~150-300 KB per frame, plenty for gemma3:4b.

    Falls back to the original bytes if Pillow isn't available.
    """
    try:
        from PIL import Image
        import io
    except ImportError:
        return jpeg_bytes  # Pillow not installed — send full size, rely on WS limit

    try:
        img = Image.open(io.BytesIO(jpeg_bytes))
        w, h = img.size
        max_side = max(w, h)
        if max_side <= max_dim:
            # Already small enough — re-encode at target quality to save bandwidth
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
            return buf.getvalue()
        # Resize maintaining aspect ratio
        scale = max_dim / max_side
        new_size = (int(w * scale), int(h * scale))
        img = img.convert("RGB").resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception as e:
        logger.warning("Frame downscale failed (%s) — sending original", e)
        return jpeg_bytes


def capture_frame(camera_id: int = 0, quality: int = 70) -> bytes:
    """Capture a single JPEG frame from the phone camera.

    On Termux: uses termux-camera-photo (requires Termux:API app installed).
    On non-Termux (e.g. for local testing on PC): uses cv2 if available.

    Automatically downscales large frames (1280px max longest side) to
    keep bandwidth + processing latency reasonable.

    Returns JPEG bytes, or b'' on failure.
    """
    if is_termux():
        TEMP_FRAME_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["termux-camera-photo", "-c", str(camera_id), str(TEMP_FRAME_PATH)],
                capture_output=True, timeout=10,
            )
            if result.returncode != 0:
                logger.warning("termux-camera-photo failed: %s", result.stderr.decode()[:200])
                return b""
            if not TEMP_FRAME_PATH.exists() or TEMP_FRAME_PATH.stat().st_size < 200:
                return b""
            raw = TEMP_FRAME_PATH.read_bytes()
            # Downscale to keep frames manageable (48MP phone → ~200 KB)
            return _downscale_jpeg(raw, max_dim=1280, quality=quality)
        except FileNotFoundError:
            logger.error("termux-camera-photo not installed. Run: pkg install termux-api")
            logger.error("Also install the Termux:API APK from F-Droid")
            return b""
        except subprocess.TimeoutExpired:
            logger.warning("Camera capture timed out")
            return b""

    # Non-Termux fallback (PC testing)
    try:
        import cv2
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            return b""
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return b""
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes()
    except Exception as e:
        logger.warning("cv2 fallback failed: %s", e)
        return b""


def play_audio(wav_bytes: bytes) -> bool:
    """Play WAV bytes through the phone's audio output (speakers/BT earbuds)."""
    if not wav_bytes:
        return False
    TEMP_AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMP_AUDIO_PATH.write_bytes(wav_bytes)

    if is_termux():
        try:
            # Use termux-media-player or play (sox) — try in order
            for cmd in (
                ["termux-media-player", "play", str(TEMP_AUDIO_PATH)],
                ["play", str(TEMP_AUDIO_PATH)],
                ["ffplay", "-nodisp", "-autoexit", str(TEMP_AUDIO_PATH)],
            ):
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=30)
                    if result.returncode == 0:
                        return True
                except FileNotFoundError:
                    continue
            logger.warning("No audio player found — install with: pkg install termux-api ffmpeg")
            return False
        except Exception as e:
            logger.warning("Audio playback failed: %s", e)
            return False

    # Non-Termux: try winsound on Windows
    try:
        import winsound
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
        return True
    except Exception:
        return False


# ─── Client state machine ───────────────────────────────────────────────

@dataclass
class ClientState:
    cfg: dict
    last_analysis_at: float = 0.0
    frames_sent: int = 0
    frames_dropped: int = 0
    bytes_sent: int = 0
    connected: bool = False


async def send_envelope(ws, secret: str, msg_type: str,
                         data: Optional[dict] = None, binary: bytes = b"") -> None:
    await ws.send(build_envelope(secret, msg_type, data or {}, binary))


async def authenticate(ws, cfg: dict) -> bool:
    await send_envelope(ws, cfg["shared_secret"], "auth", {
        "client_id": cfg["client_id"],
        "client_version": "stormbreaker-phone/0.1",
        "platform": "termux-android" if is_termux() else "desktop-test",
    })
    # Wait for ack
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        payload = parse_incoming(raw)
        if payload.get("type") == "ack" and payload.get("data", {}).get("of") == "auth":
            logger.info("Authenticated successfully")
            return True
        logger.error("Auth failed: %s", payload)
        return False
    except asyncio.TimeoutError:
        logger.error("Auth timeout")
        return False


async def receiver_loop(ws, cfg: dict, state: ClientState) -> None:
    """Process messages coming back from the edge_bridge."""
    speak = bool(cfg.get("speak_responses", True))
    async for raw in ws:
        try:
            payload = parse_incoming(raw)
        except Exception as e:
            logger.warning("Bad reply from server: %s", e)
            continue

        ptype = payload.get("type", "")
        data = payload.get("data", {})

        if ptype == "analysis":
            text = data.get("text", "")
            latency = data.get("latency_ms", 0)
            print(f"\n[ANALYSIS in {latency}ms] {text}\n", flush=True)
        elif ptype == "tts_audio" and speak:
            binary_b64 = payload.get("binary_b64", "")
            if binary_b64:
                wav = base64.b64decode(binary_b64)
                play_audio(wav)
        elif ptype == "ack":
            of = data.get("of", "")
            if of == "frame" and data.get("dropped"):
                state.frames_dropped += 1
                logger.debug("Server dropped frame: %s", data.get("reason"))
        elif ptype == "error":
            logger.warning("Server error: %s — %s",
                           data.get("code"), data.get("message"))
        elif ptype == "ping":
            await send_envelope(ws, cfg["shared_secret"], "heartbeat", {})


async def sender_loop(ws, cfg: dict, state: ClientState) -> None:
    """Capture frames at the configured interval and ship to server."""
    interval = float(cfg.get("frame_interval_s", 2.0))
    quality = int(cfg.get("frame_quality", 70))
    camera_id = int(cfg.get("camera_id", 0))
    secret = cfg["shared_secret"]

    while True:
        try:
            t0 = time.time()
            jpeg = await asyncio.get_running_loop().run_in_executor(
                None, capture_frame, camera_id, quality,
            )
            if not jpeg:
                logger.warning("No frame captured — skipping")
                await asyncio.sleep(interval)
                continue

            await send_envelope(ws, secret, "frame", {
                "size_bytes": len(jpeg),
                "format": "jpeg",
                "speak": bool(cfg.get("speak_responses", True)),
            }, binary=jpeg)

            state.frames_sent += 1
            state.bytes_sent += len(jpeg)
            logger.debug("Sent frame %d (%d bytes, capture %dms)",
                         state.frames_sent, len(jpeg),
                         int((time.time() - t0) * 1000))

            # Sleep the remainder of the interval
            sleep_for = max(0.05, interval - (time.time() - t0))
            await asyncio.sleep(sleep_for)
        except ConnectionClosed:
            logger.info("Connection closed during send — sender_loop exiting")
            return
        except Exception as e:
            logger.exception("Sender loop error: %s", e)
            await asyncio.sleep(interval)


async def heartbeat_loop(ws, cfg: dict) -> None:
    interval = float(cfg.get("heartbeat_interval_s", 5.0))
    secret = cfg["shared_secret"]
    while True:
        await asyncio.sleep(interval)
        try:
            await send_envelope(ws, secret, "heartbeat", {})
        except ConnectionClosed:
            return


async def run_session(cfg: dict, state: ClientState) -> None:
    """One full WebSocket session: connect, auth, run loops until disconnect."""
    uri = f"ws://{cfg['server_host']}:{cfg['server_port']}"
    logger.info("Connecting to %s ...", uri)

    async with ws_connect(uri, max_size=20 * 1024 * 1024) as ws:
        state.connected = True
        logger.info("Connected — authenticating")

        if not await authenticate(ws, cfg):
            return

        # Spawn three concurrent loops
        tasks = [
            asyncio.create_task(receiver_loop(ws, cfg, state)),
            asyncio.create_task(sender_loop(ws, cfg, state)),
            asyncio.create_task(heartbeat_loop(ws, cfg)),
        ]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in pending:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        finally:
            state.connected = False


async def main_loop() -> None:
    cfg = load_config()
    state = ClientState(cfg=cfg)
    delay = float(cfg.get("reconnect_delay_s", 5.0))

    logger.info("Stormbreaker phone client starting")
    logger.info("Client ID: %s", cfg["client_id"])
    logger.info("Server: ws://%s:%d", cfg["server_host"], cfg["server_port"])
    logger.info("Frame interval: %.1fs, speak: %s",
                cfg.get("frame_interval_s", 2.0),
                cfg.get("speak_responses", True))

    while True:
        try:
            await run_session(cfg, state)
            logger.info("Session ended. Reconnecting in %.1fs...", delay)
        except (ConnectionClosed, ConnectionRefusedError, OSError) as e:
            logger.warning("Connection problem: %s — retry in %.1fs", e, delay)
        except KeyboardInterrupt:
            logger.info("Ctrl+C — exiting")
            return
        except Exception as e:
            logger.exception("Unexpected error: %s — retry in %.1fs", e, delay)
        await asyncio.sleep(delay)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
