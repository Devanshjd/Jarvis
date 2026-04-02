"""
J.A.R.V.I.S — Smart Home Plugin v1.0
Simulated smart home control with real API hooks for Philips Hue and Home Assistant.

Commands:
    /devices                   — List all smart home devices
    /lights <on|off|dim N>     — Control lights
    /thermostat <temp>         — Set temperature
    /scene <name>              — Activate a scene (morning, movie, sleep, work, party)
    /adddevice <type> <name>   — Register a new device
    /removedevice <name>       — Remove a device
    /homestat                  — Show home status dashboard

Natural language:
    "turn on/off the lights", "dim the lights to 50%",
    "set temperature to 72", "activate movie mode",
    "good morning", "good night", "what devices are connected"
"""

import re
import json
import threading
import urllib.request
import urllib.error
from datetime import datetime

from core.plugin_manager import PluginBase
from core.config import save_config


# ── Default device registry ─────────────────────────────────────────────────

DEFAULT_DEVICES = [
    {"name": "Living Room Light", "type": "light", "state": "off",
     "brightness": 100, "room": "Living Room"},
    {"name": "Bedroom Light", "type": "light", "state": "off",
     "brightness": 100, "room": "Bedroom"},
    {"name": "Kitchen Light", "type": "light", "state": "off",
     "brightness": 100, "room": "Kitchen"},
    {"name": "Main Thermostat", "type": "thermostat", "state": "on",
     "temperature": 72, "room": "Hallway"},
    {"name": "Living Room Fan", "type": "fan", "state": "off",
     "room": "Living Room"},
    {"name": "Front Door Lock", "type": "lock", "state": "on",
     "room": "Entrance"},
    {"name": "Living Room Speaker", "type": "speaker", "state": "off",
     "room": "Living Room"},
    {"name": "Front Door Camera", "type": "camera", "state": "on",
     "room": "Entrance"},
    {"name": "Bedroom Curtains", "type": "switch", "state": "off",
     "room": "Bedroom"},
]

VALID_DEVICE_TYPES = {"light", "thermostat", "switch", "speaker", "camera", "lock", "fan"}

# ── Scene definitions ────────────────────────────────────────────────────────

SCENES = {
    "morning": {
        "description": "Good morning — bright lights, comfortable temperature",
        "actions": [
            {"target_type": "light", "state": "on", "brightness": 80},
            {"target_type": "thermostat", "temperature": 72},
        ],
    },
    "movie": {
        "description": "Movie night — dim lights, curtains closed",
        "actions": [
            {"target_type": "light", "state": "on", "brightness": 20},
            {"target_name": "Bedroom Curtains", "state": "on"},  # "on" = closed
        ],
    },
    "sleep": {
        "description": "Good night — lights off, cool temperature",
        "actions": [
            {"target_type": "light", "state": "off", "brightness": 0},
            {"target_type": "thermostat", "temperature": 68},
        ],
    },
    "work": {
        "description": "Work mode — full brightness, focus mode",
        "actions": [
            {"target_type": "light", "state": "on", "brightness": 100},
        ],
    },
    "party": {
        "description": "Party mode — lights cycling colors (simulated)",
        "actions": [
            {"target_type": "light", "state": "on", "brightness": 90},
            {"target_type": "speaker", "state": "on"},
        ],
    },
}


# ── Helpers ──────────────────────────────────────────────────────────────────

TYPE_ICONS = {
    "light": "💡",
    "thermostat": "🌡️",
    "switch": "🔌",
    "speaker": "🔊",
    "camera": "📷",
    "lock": "🔒",
    "fan": "🌀",
}


def _msg(jarvis, role, text):
    """Post a message to the chat UI (thread-safe)."""
    jarvis.root.after(0, lambda: jarvis.chat.add_message(role, text))


# ── Plugin class ─────────────────────────────────────────────────────────────

class SmartHomePlugin(PluginBase):
    name = "smart_home"
    description = "Smart Home — control lights, thermostat, scenes, and devices"
    version = "1.0"

    # ── Lifecycle ────────────────────────────────────────────────────────

    def activate(self):
        cfg = self.jarvis.config
        if "smart_home" not in cfg:
            cfg["smart_home"] = {
                "devices": [dict(d) for d in DEFAULT_DEVICES],
                "hue_bridge_ip": "",
                "hue_api_key": "",
                "ha_url": "",
                "ha_token": "",
            }
            save_config(cfg)
        self._sh = cfg["smart_home"]

    def deactivate(self):
        pass

    # ── Persistence ──────────────────────────────────────────────────────

    def _save(self):
        self.jarvis.config["smart_home"] = self._sh
        save_config(self.jarvis.config)

    # ── Device helpers ───────────────────────────────────────────────────

    def _devices(self):
        return self._sh.get("devices", [])

    def _find_device(self, name: str):
        for d in self._devices():
            if d["name"].lower() == name.lower():
                return d
        return None

    def _devices_by_type(self, dtype: str):
        return [d for d in self._devices() if d["type"] == dtype]

    # ── Real API hooks (stubs) ───────────────────────────────────────────

    def _hue_control(self, device: dict, action: dict):
        """Philips Hue API stub. Configure hue_bridge_ip and hue_api_key in config."""
        ip = self._sh.get("hue_bridge_ip", "")
        key = self._sh.get("hue_api_key", "")
        if not ip or not key:
            return  # Not configured — skip silently
        # Placeholder: would PUT to http://{ip}/api/{key}/lights/{id}/state
        try:
            url = f"http://{ip}/api/{key}/lights/1/state"
            payload = json.dumps(action).encode()
            req = urllib.request.Request(url, data=payload, method="PUT",
                                        headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception:
            pass  # Log in future version

    def _ha_control(self, device: dict, action: dict):
        """Home Assistant API stub. Configure ha_url and ha_token in config."""
        url = self._sh.get("ha_url", "")
        token = self._sh.get("ha_token", "")
        if not url or not token:
            return  # Not configured — skip silently
        # Placeholder: would POST to {url}/api/services/{domain}/{service}
        try:
            endpoint = f"{url.rstrip('/')}/api/services/light/turn_on"
            payload = json.dumps(action).encode()
            req = urllib.request.Request(endpoint, data=payload, method="POST",
                                        headers={
                                            "Content-Type": "application/json",
                                            "Authorization": f"Bearer {token}",
                                        })
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception:
            pass

    def _try_real_apis(self, device: dict, action: dict):
        """Attempt to forward action to real smart home APIs."""
        threading.Thread(target=self._hue_control, args=(device, action), daemon=True).start()
        threading.Thread(target=self._ha_control, args=(device, action), daemon=True).start()

    # ── Core actions ─────────────────────────────────────────────────────

    def _set_lights(self, state: str, brightness: int | None = None):
        lights = self._devices_by_type("light")
        if not lights:
            return "No light devices registered."
        for light in lights:
            light["state"] = state
            if brightness is not None:
                light["brightness"] = max(0, min(100, brightness))
            elif state == "off":
                light["brightness"] = 0
            self._try_real_apis(light, {"on": state == "on",
                                        "bri": int(light.get("brightness", 100) * 2.54)})
        self._save()
        if brightness is not None:
            return f"Lights set to {brightness}% brightness, sir."
        return f"Lights turned {state}, sir."

    def _set_thermostat(self, temp: int):
        thermos = self._devices_by_type("thermostat")
        if not thermos:
            return "No thermostat devices registered."
        for t in thermos:
            t["state"] = "on"
            t["temperature"] = temp
            self._try_real_apis(t, {"temperature": temp})
        self._save()
        return f"Thermostat set to {temp}°F, sir."

    def _activate_scene(self, scene_name: str):
        scene_name = scene_name.lower().strip()
        if scene_name not in SCENES:
            available = ", ".join(SCENES.keys())
            return f"Unknown scene '{scene_name}'. Available: {available}"
        scene = SCENES[scene_name]
        results = [f"🎬 Activating **{scene_name}** scene — {scene['description']}"]
        for action in scene["actions"]:
            if "target_type" in action:
                devices = self._devices_by_type(action["target_type"])
            elif "target_name" in action:
                dev = self._find_device(action["target_name"])
                devices = [dev] if dev else []
            else:
                continue
            for dev in devices:
                if "state" in action:
                    dev["state"] = action["state"]
                if "brightness" in action:
                    dev["brightness"] = action["brightness"]
                if "temperature" in action:
                    dev["temperature"] = action["temperature"]
                self._try_real_apis(dev, action)
            dtype = action.get("target_type", action.get("target_name", "device"))
            icon = TYPE_ICONS.get(dtype, "•")
            results.append(f"  {icon} {dtype}: {action}")
        self._save()
        return "\n".join(results)

    # ── Command routing ──────────────────────────────────────────────────

    def on_command(self, command: str, args: str) -> bool:
        cmd = command.lower()
        args = args.strip()

        if cmd == "devices":
            self._cmd_devices()
            return True
        elif cmd == "lights":
            self._cmd_lights(args)
            return True
        elif cmd == "thermostat":
            self._cmd_thermostat(args)
            return True
        elif cmd == "scene":
            self._cmd_scene(args)
            return True
        elif cmd == "adddevice":
            self._cmd_add_device(args)
            return True
        elif cmd == "removedevice":
            self._cmd_remove_device(args)
            return True
        elif cmd == "homestat":
            self._cmd_homestat()
            return True
        return False

    # ── Slash-command implementations ────────────────────────────────────

    def _cmd_devices(self):
        devices = self._devices()
        if not devices:
            self.jarvis.chat.add_message("assistant",
                                         "No devices registered. Use /adddevice <type> <name>.")
            return
        lines = ["📡 **Smart Home Devices**", ""]
        for d in devices:
            icon = TYPE_ICONS.get(d["type"], "•")
            state_str = "🟢 ON" if d["state"] == "on" else "🔴 OFF"
            extra = ""
            if d["type"] == "light" and d["state"] == "on":
                extra = f" ({d.get('brightness', 100)}%)"
            elif d["type"] == "thermostat":
                extra = f" ({d.get('temperature', 72)}°F)"
            lines.append(f"  {icon} {d['name']} [{d['room']}] — {state_str}{extra}")
        self.jarvis.chat.add_message("assistant", "\n".join(lines))

    def _cmd_lights(self, args: str):
        if not args:
            self.jarvis.chat.add_message("system",
                                         "Usage: /lights <on|off|dim N>")
            return
        parts = args.lower().split()
        if parts[0] in ("on", "off"):
            result = self._set_lights(parts[0])
        elif parts[0] == "dim" and len(parts) >= 2:
            try:
                brightness = int(parts[1].replace("%", ""))
                result = self._set_lights("on", brightness)
            except ValueError:
                result = "Invalid brightness value. Use: /lights dim 50"
        else:
            result = "Usage: /lights <on|off|dim N>"
        self.jarvis.chat.add_message("assistant", result)

    def _cmd_thermostat(self, args: str):
        if not args:
            self.jarvis.chat.add_message("system",
                                         "Usage: /thermostat <temperature>")
            return
        try:
            temp = int(args.replace("°", "").replace("F", "").replace("f", "").strip())
            result = self._set_thermostat(temp)
        except ValueError:
            result = "Invalid temperature. Use: /thermostat 72"
        self.jarvis.chat.add_message("assistant", result)

    def _cmd_scene(self, args: str):
        if not args:
            lines = ["Available scenes:"]
            for name, scene in SCENES.items():
                lines.append(f"  • {name} — {scene['description']}")
            self.jarvis.chat.add_message("assistant", "\n".join(lines))
            return
        result = self._activate_scene(args)
        self.jarvis.chat.add_message("assistant", result)

    def _cmd_add_device(self, args: str):
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            self.jarvis.chat.add_message("system",
                                         "Usage: /adddevice <type> <name>\n"
                                         f"Types: {', '.join(sorted(VALID_DEVICE_TYPES))}")
            return
        dtype, dname = parts[0].lower(), parts[1].strip()
        if dtype not in VALID_DEVICE_TYPES:
            self.jarvis.chat.add_message("system",
                                         f"Invalid type '{dtype}'. "
                                         f"Valid: {', '.join(sorted(VALID_DEVICE_TYPES))}")
            return
        if self._find_device(dname):
            self.jarvis.chat.add_message("system",
                                         f"Device '{dname}' already exists.")
            return
        device = {
            "name": dname,
            "type": dtype,
            "state": "off",
            "room": "Unassigned",
        }
        if dtype == "light":
            device["brightness"] = 100
        elif dtype == "thermostat":
            device["temperature"] = 72
        self._sh["devices"].append(device)
        self._save()
        icon = TYPE_ICONS.get(dtype, "•")
        self.jarvis.chat.add_message("assistant",
                                     f"{icon} Device '{dname}' ({dtype}) added, sir.")

    def _cmd_remove_device(self, args: str):
        if not args:
            self.jarvis.chat.add_message("system",
                                         "Usage: /removedevice <name>")
            return
        name = args.strip()
        device = self._find_device(name)
        if not device:
            self.jarvis.chat.add_message("system",
                                         f"Device '{name}' not found.")
            return
        self._sh["devices"].remove(device)
        self._save()
        self.jarvis.chat.add_message("assistant",
                                     f"Device '{device['name']}' removed, sir.")

    def _cmd_homestat(self):
        devices = self._devices()
        total = len(devices)
        on_count = sum(1 for d in devices if d["state"] == "on")
        off_count = total - on_count

        lines = [
            "🏠 **Smart Home Status Dashboard**",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  Total devices: {total}",
            f"  Online: 🟢 {on_count}  |  Offline: 🔴 {off_count}",
            "",
        ]

        # Group by room
        rooms: dict[str, list] = {}
        for d in devices:
            rooms.setdefault(d.get("room", "Unassigned"), []).append(d)

        for room, devs in sorted(rooms.items()):
            lines.append(f"  📍 {room}")
            for d in devs:
                icon = TYPE_ICONS.get(d["type"], "•")
                state_str = "🟢" if d["state"] == "on" else "🔴"
                extra = ""
                if d["type"] == "light" and d["state"] == "on":
                    extra = f" — {d.get('brightness', 100)}%"
                elif d["type"] == "thermostat":
                    extra = f" — {d.get('temperature', 72)}°F"
                lines.append(f"    {icon} {state_str} {d['name']}{extra}")
            lines.append("")

        # API status
        hue_ok = bool(self._sh.get("hue_bridge_ip") and self._sh.get("hue_api_key"))
        ha_ok = bool(self._sh.get("ha_url") and self._sh.get("ha_token"))
        lines.append("  🔗 Integrations")
        lines.append(f"    Philips Hue: {'✅ configured' if hue_ok else '⚠️ not configured'}")
        lines.append(f"    Home Assistant: {'✅ configured' if ha_ok else '⚠️ not configured'}")

        self.jarvis.chat.add_message("assistant", "\n".join(lines))

    # ── Natural language processing ──────────────────────────────────────

    def on_message(self, message: str) -> str | None:
        msg = message.lower().strip()

        # "turn on/off the lights"
        m = re.search(r"turn\s+(on|off)\s+(?:the\s+)?lights?", msg)
        if m:
            result = self._set_lights(m.group(1))
            self.jarvis.chat.add_message("assistant", result)
            return ""

        # "dim the lights to N%"
        m = re.search(r"dim\s+(?:the\s+)?lights?\s+(?:to\s+)?(\d+)\s*%?", msg)
        if m:
            result = self._set_lights("on", int(m.group(1)))
            self.jarvis.chat.add_message("assistant", result)
            return ""

        # "set temperature to N"
        m = re.search(r"set\s+(?:the\s+)?(?:temp(?:erature)?|thermostat)\s+(?:to\s+)?(\d+)", msg)
        if m:
            result = self._set_thermostat(int(m.group(1)))
            self.jarvis.chat.add_message("assistant", result)
            return ""

        # "activate X mode" / "set scene to X"
        m = re.search(r"(?:activate|set\s+scene\s+to|switch\s+to)\s+(\w+)\s*(?:mode|scene)?", msg)
        if m:
            scene = m.group(1)
            if scene in SCENES:
                result = self._activate_scene(scene)
                self.jarvis.chat.add_message("assistant", result)
                return ""

        # "good morning"
        if re.search(r"\bgood\s+morning\b", msg):
            result = self._activate_scene("morning")
            self.jarvis.chat.add_message("assistant", result)
            return ""

        # "good night"
        if re.search(r"\bgood\s*night\b", msg):
            result = self._activate_scene("sleep")
            self.jarvis.chat.add_message("assistant", result)
            return ""

        # "what devices are connected"
        if re.search(r"(?:what|which|list|show)\s+(?:devices?|smart\s*home)", msg):
            self._cmd_devices()
            return ""

        return None

    # ── Status ───────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        devices = self._devices()
        on_count = sum(1 for d in devices if d["state"] == "on")
        return {
            "name": self.name,
            "active": True,
            "devices": len(devices),
            "online": on_count,
        }
