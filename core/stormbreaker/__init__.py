"""
J.A.R.V.I.S — Stormbreaker subsystem

Standalone subsystem that bridges wearable hardware (phone, Pi Zero, or
future custom goggles) with the main JARVIS Desktop brain over WiFi.

Modules:
    edge_bridge   — WebSocket server (runs on JARVIS Desktop / PC)
    phone_client  — Termux-side Python client (runs on Mi 11X phone)
    pi_client     — Pi-side client (v1+, when we move to Pi compute)

Architecture: split-compute. Wearable captures camera + audio + gestures
and ships them to the brain over WebSocket. Brain runs AI inference
(Ollama vision, OCR, Whisper STT, Piper TTS) and ships results back.
"""
