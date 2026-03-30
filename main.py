"""
J.A.R.V.I.S — Just A Rather Very Intelligent System
═══════════════════════════════════════════════════════
Stark Industries Personal AI System

USAGE:
    python main.py

HOTKEYS:
    Ctrl+Shift+J  — Toggle JARVIS window
    Ctrl+Shift+S  — Scan screen
    Ctrl+Shift+V  — Voice input (push-to-talk)

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

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_dependencies():
    """Check and report missing dependencies."""
    required = {
        "anthropic": "anthropic",
        "PIL": "pillow",
        "keyboard": "keyboard",
        "pystray": "pystray",
        "pyautogui": "pyautogui",
    }
    optional = {
        "pyttsx3": "pyttsx3 (for JARVIS voice)",
        "speech_recognition": "SpeechRecognition (for voice input)",
        "psutil": "psutil (for system monitoring)",
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
