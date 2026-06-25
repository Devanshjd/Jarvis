"""
JARVIS — Seed the knowledge graph with all Stormbreaker decisions.

Run once after each scope-lock change. Saves every architecture decision,
BOM item, constraint, and goal as a structured KG entity so JARVIS's
research / planning / chat tools can ground in our actual choices instead
of making up generic recommendations.

Usage:
    python training/seed_stormbreaker_context.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.project_context import save_decision, save_bom_item  # noqa: E402
from core.knowledge_graph import KnowledgeGraph  # noqa: E402


# ─── 1. Project goals & constraints ───────────────────────────────────────
GOALS_AND_CONSTRAINTS = [
    {
        "name": "stormbreaker_product_goal",
        "type": "goal",
        "facts": {
            "what": "AI-assisted AR goggles for daily wear + DRDO/military variant",
            "target_market": "India",
            "differentiators": "fully local AI, privacy-first, offline-capable, JARVIS-powered",
            "user_segments": "consumer accessibility (eyesight assistance), enterprise security, military/police",
            "competitors": "Ray-Ban Meta (cloud-tied), XReal Air (phone tethered), Meta Quest (Android-locked), HoloLens (enterprise only)",
            "stormbreaker_advantage": "open-source local AI, no cloud dependency, DRDO-pitchable",
        },
    },
    {
        "name": "budget_constraint",
        "type": "constraint",
        "facts": {
            "monthly_budget_gbp": "80-100",
            "v0_budget_total_gbp": "~130",
            "v1_target_budget_gbp": "~400",
            "v3_military_budget_gbp": "~2000-3000",
            "currency_note": "user in UK, building for India market",
            "implication": "every component must justify cost — no premium parts unless essential",
        },
    },
    {
        "name": "no_soldering_no_3d_printer_constraint",
        "type": "constraint",
        "facts": {
            "tools_available": "none (no soldering iron, no 3D printer)",
            "workaround": "plug-and-play modules with USB / Qwiic / STEMMA QT connectors only",
            "frame_strategy_v0": "modify cheap safety glasses with foam tape + cable clips",
            "frame_strategy_v1": "send STL files to UK 3D print service (Hubs / Treatstock)",
            "soldering_alternative": "screw-terminal breakout boards + pre-built amp modules",
        },
    },
    {
        "name": "privacy_military_grade_constraint",
        "type": "constraint",
        "facts": {
            "no_third_party_apis": "everything runs local — no Gemini cloud, no OpenAI, no Google services",
            "no_data_egress_in_secure_mode": "secure mode blocks all internet traffic",
            "approved_local_stack": "Ollama (gemma3:4b + moondream), Tesseract OCR, Piper TTS, MediaPipe Hands, Whisper.cpp",
            "drdo_pitch_target": "yes — military variant deferred to v3, special features TBD",
            "rationale": "user explicitly requested military-grade — DRDO/Indian Army cannot accept cloud-dependent products",
        },
    },
    {
        "name": "top_three_priority_features",
        "type": "constraint",
        "facts": {
            "priority_1": "gesture control — smooth and easy",
            "priority_2": "adjustable focal length — for prescription glasses wearers",
            "priority_3": "stable OS — system survives power loss, auto-recovers",
            "source": "user scope-lock answer, 2026-05-15",
        },
    },
]


# ─── 2. Locked architecture decisions ─────────────────────────────────────
ARCHITECTURE_DECISIONS = [
    {
        "name": "split_compute_architecture",
        "decision": "Pi Zero 2 W on goggles + user's Windows PC running JARVIS Desktop as the AI brain, connected over local WiFi via WebSocket",
        "rationale": "Cheapest path — uses existing PC as brain, saves £80+ on Pi 5. Glasses stay lightweight (matchbox-sized compute). Can swap PC for Pi 5 in pocket later when going mobile.",
        "phase": "v0-v1",
        "edge_node": "Raspberry Pi Zero 2 W (£15)",
        "brain_node": "user's Windows PC, JARVIS Desktop (Electron + Python)",
        "link": "local WiFi WebSocket, JPEG frames at 5 fps + audio + gesture events",
        "latency_target_ms": "50",
        "bandwidth_target_mbps": "5-10",
    },
    {
        "name": "stormbreaker_os_strategy",
        "decision": "Raspberry Pi OS Lite 64-bit + overlayroot + auto-boot to JARVIS service + custom branded shell = 'Stormbreaker OS'",
        "rationale": "Same legitimacy pattern as Steam OS / Tesla OS / DJI OS — Linux underneath, custom experience on top. NOT building a kernel from scratch. NOT using Windows (deprecated IoT, too heavy). NOT using Android (no Pi 5 support, privacy collapses).",
        "phase": "v0",
        "dual_mode": "single image with /consumer (open, plugins loadable) and /secure (signed-only, audit-logged, no network egress) flag",
        "boot_strategy": "overlayroot read-only root + systemd watchdog + A/B partition for OTA",
        "ota_strategy": "our update server only — never Google / Microsoft push channels",
    },
    {
        "name": "gesture_control_via_mediapipe_hands",
        "decision": "Use Google MediaPipe Hands (free, on-device) for gesture detection — runs on Pi Camera 3 feed, no extra hardware",
        "rationale": "User's #1 priority. MediaPipe is free, runs ~12-15 fps on Pi 5 / Pi Zero 2 W. Avoids £70-100 Leap Motion module.",
        "gestures_v0": "pinch (confirm), open palm (cancel), swipe (navigate), point+hold (identify), fist (push-to-talk)",
        "latency_target_ms": "100",
        "phase": "v0-v1",
    },
    {
        "name": "adjustable_focal_length_strategy",
        "decision": "v0/v1: design frame to fit OVER existing prescription glasses (clip-on style). v2+: custom frame with prescription lens inserts sourced from Indian optical labs (~₹4-6K).",
        "rationale": "User's #2 priority. Over-glasses fit costs nothing extra and accommodates any prescription. Prescription inserts match Meta Quest 3's approach.",
        "phase_v0": "over-glasses fit (no extra cost)",
        "phase_v2": "prescription insert slot in custom frame",
        "indian_optical_labs": "Surat / Ahmedabad / Bengaluru — ₹4-6K per insert pair",
    },
    {
        "name": "skill_launcher_app_store_pattern",
        "decision": "Build a JARVIS Skill Launcher (tile-based home screen) that gives the user Android-app-store feel without using Android. Skills are curated JARVIS plugins, sandboxed, signed.",
        "rationale": "User wanted Android-like app downloads. Doing it our way preserves privacy (no Play Store telemetry), works on Linux (no Android port), keeps military path open (signed-only catalog).",
        "skills_v1_catalog": "Navigate, Translate, Read, Identify, Health, Notes, Spotify Control, Web Search, Calculator, Reminders",
        "sandboxing": "each skill uses only JARVIS APIs we expose — better isolation than Android apps",
        "phase": "v1-v2",
    },
    {
        "name": "wifi_link_protocol",
        "decision": "Edge ↔ Brain communication over local WiFi WebSocket, JSON message protocol",
        "rationale": "User wanted wireless link (the 'WiFi pendrive' comment interpreted as wireless tethering). Local WiFi keeps traffic off the internet.",
        "messages_up": "camera_frame, audio_chunk, gesture_event, sensor_telemetry",
        "messages_down": "tts_audio, hud_overlay_data, command",
        "reconnect": "heartbeat every 2s, auto-reconnect on drop",
        "secure_mode_encryption": "ChaCha20-Poly1305 + isolated SSID with no internet egress",
    },
]


# ─── 3. v0 Bill of Materials ──────────────────────────────────────────────
V0_BOM = [
    ("pi_zero_2w", "Raspberry Pi Zero 2 W — goggles compute, has built-in WiFi", "15", "The Pi Hut"),
    ("pi_zero_camera_cable", "Pi Zero camera adapter cable (small connector to standard)", "4", "The Pi Hut"),
    ("pi_camera_module_3_wide", "Pi Camera Module 3 Wide — 12MP, wide angle, autofocus", "35", "Pimoroni"),
    ("usb_lavalier_mic", "FIFINE K053 USB lavalier microphone — pre-soldered USB", "15", "Amazon UK"),
    ("bone_conduction_transducer", "Bone conduction transducer + pre-built PAM8403 amp module", "25", "Amazon UK"),
    ("lipo_battery_3000mah", "3000mAh single-cell LiPo + USB-C charging board", "12", "Amazon UK"),
    ("microsd_32gb_a2", "SanDisk Extreme 32GB A2 microSD", "8", "Amazon UK"),
    ("safety_glasses_v0_frame", "Safety glasses for v0 frame — modifiable with foam tape", "8", "Amazon UK"),
    ("mounting_kit", "Industrial double-sided foam tape + cable clips + heat-shrink kit", "8", "Amazon UK"),
]


def main():
    print("=" * 70)
    print(" JARVIS — Seeding Stormbreaker project context into knowledge graph")
    print("=" * 70)

    kg = KnowledgeGraph()

    print("\n[1/3] Saving goals + constraints...")
    n_goals = 0
    for item in GOALS_AND_CONSTRAINTS:
        kg.add_entity(item["name"], item["type"], item["facts"])
        n_goals += 1
    print(f"  -> {n_goals} goals/constraints saved")

    print("\n[2/3] Saving architecture decisions...")
    n_decisions = 0
    for d in ARCHITECTURE_DECISIONS:
        decision_text = d.pop("decision")
        rationale = d.pop("rationale", "")
        name = d.pop("name")
        save_decision(
            name=name,
            decision=decision_text,
            rationale=rationale,
            locked=True,
            knowledge_graph=kg,
            **d,
        )
        n_decisions += 1
    print(f"  -> {n_decisions} architecture decisions saved")

    print("\n[3/3] Saving v0 BOM...")
    n_bom = 0
    for name, desc, cost, vendor in V0_BOM:
        save_bom_item(
            name=name,
            description=desc,
            cost=f"GBP {cost}",
            vendor=vendor,
            phase="v0",
            knowledge_graph=kg,
        )
        n_bom += 1
    print(f"  -> {n_bom} BOM items saved")

    print("\n" + "=" * 70)
    print(" Total saved: ", n_goals + n_decisions + n_bom, "entities")
    print("=" * 70)

    # Smoke test: pull preamble for a few queries
    print("\n=== Smoke test: pull preamble for 'goggles compute' ===")
    from core.project_context import build_preamble
    preamble = build_preamble(query="goggles compute architecture", max_entities=5)
    print(preamble[:1200] + ("..." if len(preamble) > 1200 else ""))


if __name__ == "__main__":
    main()
