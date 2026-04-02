"""
J.A.R.V.I.S — Automation Plugin
System control, app launching, and task automation.

Commands:
    /open <app>        — Open an application
    /run <command>     — Run a system command
    /search <query>    — Search the web
    /type <text>       — Type text at cursor position
    /screenshot        — Take a screenshot
    /sys               — System information
"""

import os
import subprocess
import platform
import threading

from core.plugin_manager import PluginBase

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


# Common Windows applications and their paths/commands
APP_MAP = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "browser": "chrome",
    "firefox": "firefox",
    "edge": "msedge",
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "explorer": "explorer",
    "file explorer": "explorer",
    "files": "explorer",
    "terminal": "wt",
    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "code": "code",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "task manager": "taskmgr",
    "settings": "ms-settings:",
    "paint": "mspaint",
    "word": "winword",
    "microsoft word": "winword",
    "ms word": "winword",
    "excel": "excel",
    "microsoft excel": "excel",
    "ms excel": "excel",
    "powerpoint": "powerpnt",
    "microsoft powerpoint": "powerpnt",
    "ppt": "powerpnt",
    "outlook": "outlook",
    "microsoft outlook": "outlook",
    "spotify": "spotify",
    "discord": "discord",
    "slack": "slack",
    "teams": "teams",
    "snipping tool": "snippingtool",
    "control panel": "control",
}


class AutomationPlugin(PluginBase):
    name = "automation"
    description = "System automation — open apps, run commands, control PC"
    version = "1.0"

    def activate(self):
        pass

    def deactivate(self):
        pass

    def on_command(self, command: str, args: str) -> bool:
        if command == "/open":
            self._open_app(args)
            return True
        if command == "/run":
            self._run_command(args)
            return True
        if command == "/search":
            self._web_search(args)
            return True
        if command == "/type":
            self._type_text(args)
            return True
        if command == "/sys":
            self._system_info()
            return True
        if command == "/screenshot":
            self.jarvis.scan_screen()
            return True
        if command == "/lock":
            self._lock_screen()
            return True
        if command == "/volume":
            self._set_volume(args)
            return True
        return False

    def on_message(self, message: str) -> str | None:
        """Detect natural language commands like 'open chrome' or 'launch notepad'."""
        msg_lower = message.lower().strip()

        # "open X" / "can you open X" / "please open X" patterns
        import re
        match = re.search(
            r"(?:can you |please |could you )?(?:open|launch|start)\s+(.+?)(?:\s+for me|\s+please)?$",
            msg_lower,
        )
        if match:
            app_name = match.group(1).strip()
            # Try exact match first, then partial
            if app_name in APP_MAP:
                self._open_app(app_name)
                return "__handled__"
            # Try matching known app names within the phrase
            for known_app in sorted(APP_MAP.keys(), key=len, reverse=True):
                if known_app in app_name:
                    self._open_app(known_app)
                    return "__handled__"

        return None  # Pass through to AI

    # ══════════════════════════════════════════════════════════════
    # ACTIONS
    # ══════════════════════════════════════════════════════════════

    def _open_app(self, app_name: str):
        app_name = app_name.lower().strip()
        exe = APP_MAP.get(app_name, app_name)

        self.jarvis.chat.add_message("system", f"Opening {app_name}...")

        def _launch():
            try:
                if exe.startswith("ms-"):
                    os.startfile(exe)
                else:
                    subprocess.Popen(
                        exe, shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                self.jarvis.root.after(0, lambda: self.jarvis.chat.add_message(
                    "assistant", f"Done, sir. {app_name.title()} has been launched."))
            except Exception as e:
                self.jarvis.root.after(0, lambda: self.jarvis.chat.add_message(
                    "system", f"Failed to open {app_name}: {e}"))

        threading.Thread(target=_launch, daemon=True).start()

    def _run_command(self, command: str):
        if not command:
            self.jarvis.chat.add_message("system", "Usage: /run <command>")
            return

        self.jarvis.chat.add_message("system", f"Executing: {command}")

        def _exec():
            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True,
                    text=True, timeout=30,
                )
                output = result.stdout or result.stderr or "(no output)"
                # Truncate long output
                if len(output) > 2000:
                    output = output[:2000] + "\n... (truncated)"
                self.jarvis.root.after(0, lambda: self.jarvis.chat.add_message(
                    "assistant", f"Command output:\n```\n{output}\n```"))
            except subprocess.TimeoutExpired:
                self.jarvis.root.after(0, lambda: self.jarvis.chat.add_message(
                    "system", "Command timed out (30s limit)"))
            except Exception as e:
                self.jarvis.root.after(0, lambda: self.jarvis.chat.add_message(
                    "system", f"Command error: {e}"))

        threading.Thread(target=_exec, daemon=True).start()

    def _web_search(self, query: str):
        if not query:
            self.jarvis.chat.add_message("system", "Usage: /search <query>")
            return
        import webbrowser
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        webbrowser.open(url)
        self.jarvis.chat.add_message("assistant", f"Searching for: {query}")

    def _type_text(self, text: str):
        if not HAS_PYAUTOGUI:
            self.jarvis.chat.add_message("system", "Install pyautogui: pip install pyautogui")
            return
        if not text:
            self.jarvis.chat.add_message("system", "Usage: /type <text>")
            return

        import time
        time.sleep(1)  # Give user time to click target window
        pyautogui.typewrite(text, interval=0.02)
        self.jarvis.chat.add_message("system", f"Typed: {text}")

    def _system_info(self):
        import psutil
        try:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            battery = psutil.sensors_battery()

            info = (
                f"System Status Report\n"
                f"────────────────────\n"
                f"OS: {platform.system()} {platform.release()}\n"
                f"Machine: {platform.machine()}\n"
                f"Processor: {platform.processor()}\n"
                f"CPU Usage: {cpu}%\n"
                f"RAM: {ram.percent}% ({ram.used // (1024**3)}GB / {ram.total // (1024**3)}GB)\n"
                f"Disk: {disk.percent}% ({disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB)\n"
            )
            if battery:
                info += f"Battery: {battery.percent}% {'(Charging)' if battery.power_plugged else '(On Battery)'}\n"

            self.jarvis.chat.add_message("assistant", info)
        except ImportError:
            # Fallback without psutil
            info = (
                f"System: {platform.system()} {platform.release()}\n"
                f"Machine: {platform.machine()}\n"
                f"Processor: {platform.processor()}\n"
                f"(Install psutil for detailed stats: pip install psutil)"
            )
            self.jarvis.chat.add_message("assistant", info)

    def _lock_screen(self):
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            self.jarvis.chat.add_message("system", "Workstation locked, sir.")

    def _set_volume(self, level: str):
        """Set system volume (Windows)."""
        try:
            level = int(level.strip().rstrip("%"))
            if platform.system() == "Windows":
                # Use nircmd if available, otherwise PowerShell
                subprocess.run(
                    f'powershell -c "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"',
                    shell=True, capture_output=True,
                )
                self.jarvis.chat.add_message("system",
                    f"Volume adjustment requested. For precise control, install nircmd.")
        except ValueError:
            self.jarvis.chat.add_message("system", "Usage: /volume <0-100>")

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "active": True,
            "pyautogui_available": HAS_PYAUTOGUI,
        }
