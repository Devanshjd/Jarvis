"""
J.A.R.V.I.S — Just A Rather Very Intelligent System
═══════════════════════════════════════════════════════
Stark Industries Personal AI System

USAGE:
    python main.py

HOTKEYS:
    Ctrl+Shift+S  — Scan screen
    Ctrl+Shift+V  — Voice input (push-to-talk)
    Ctrl+Shift+J  — Toggle JARVIS window (optional, disabled by default)

VOICE:
    Click 🎤 or say "JARVIS" to activate voice
    /voice — toggle voice on/off
    /say <text> — make JARVIS speak

AUTOMATION:
    /open <app>    — Open an application
    /run <command> — Run a system command
    /search <query> — Web search
    /sys           — System info
    /lock          — Lock workstation
"""

import atexit
import faulthandler
import sys
import os
import threading
import traceback

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _safe_print(*args, sep=" ", end="\n", file=None, flush=False):
    """Encoding-safe print for Windows consoles with narrow code pages."""
    target = file or sys.stdout
    encoding = getattr(target, "encoding", None) or "utf-8"
    text = sep.join("" if arg is None else str(arg) for arg in args) + end
    data = text.encode(encoding, errors="replace")

    buffer = getattr(target, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        if flush:
            buffer.flush()
        return

    target.write(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))
    if flush and hasattr(target, "flush"):
        target.flush()


print = _safe_print


def _log_process_exit():
    print("[JARVIS] Python process exiting")


def _log_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        print("[JARVIS] Interrupted by keyboard")
        return
    print("[JARVIS] Unhandled exception on main thread:")
    traceback.print_exception(exc_type, exc_value, exc_traceback)


def _log_thread_exception(args):
    print(f"[JARVIS] Unhandled exception in thread {args.thread.name}:")
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)


faulthandler.enable()
atexit.register(_log_process_exit)
sys.excepthook = _log_unhandled_exception
threading.excepthook = _log_thread_exception


def check_dependencies():
    """Check and report missing dependencies."""
    required = {
        "anthropic": "anthropic",
        "PIL": "pillow",
        "keyboard": "keyboard",
        "pyautogui": "pyautogui",
    }
    optional = {
        "pyttsx3": "pyttsx3 (for JARVIS voice)",
        "speech_recognition": "SpeechRecognition (for voice input)",
        "psutil": "psutil (for system monitoring)",
        "pystray": "pystray (for optional system tray)",
    }

    missing_required = []
    missing_optional = []

    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing_required.append(package)

    for module, desc in optional.items():
        try:
            __import__(module)
        except ImportError:
            missing_optional.append(desc)

    if missing_required:
        print(f"\n⚠  Missing required packages: {', '.join(missing_required)}")
        print(f"   Run: pip install {' '.join(missing_required)}\n")

    if missing_optional:
        print(f"ℹ  Optional packages (for full features):")
        for pkg in missing_optional:
            print(f"   - {pkg}")
        print()

    return len(missing_required) == 0


def main():
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║   J.A.R.V.I.S — STARK INDUSTRIES        ║")
    print("  ║   Personal AI System v5.0                ║")
    print("  ╚══════════════════════════════════════════╝")
    print()

    deps_ok = check_dependencies()
    if not deps_ok:
        print("  Starting with limited functionality...\n")

    from ui.app import JarvisApp
    app = JarvisApp()
    app.run()


if __name__ == "__main__":
    main()
