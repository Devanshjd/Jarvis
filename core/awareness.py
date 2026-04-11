"""
J.A.R.V.I.S — Awareness Engine
Screen monitoring, clipboard watching, active window tracking,
system health monitoring, and environment sensing.

Movie JARVIS sees the world around Tony.
This engine gives JARVIS eyes on the environment.
"""

import os
import re
import time
import json
import threading
import logging
import subprocess
import ctypes
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Callable

logger = logging.getLogger("jarvis.awareness")


# ═══════════════════════════════════════════════════════════
#  Data structures
# ═══════════════════════════════════════════════════════════

@dataclass
class SystemHealth:
    """Snapshot of system vitals."""
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    disk_percent: float = 0.0
    battery_percent: Optional[float] = None
    battery_plugged: Optional[bool] = None
    uptime_hours: float = 0.0
    process_count: int = 0
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.cpu_percent < 85 and self.ram_percent < 90

    @property
    def status_text(self) -> str:
        parts = [f"CPU {self.cpu_percent:.0f}%", f"RAM {self.ram_percent:.0f}%"]
        if self.battery_percent is not None:
            plug = "⚡" if self.battery_plugged else "🔋"
            parts.append(f"{plug}{self.battery_percent:.0f}%")
        return " · ".join(parts)

    @property
    def alert_level(self) -> str:
        """Returns 'green', 'yellow', or 'red'."""
        if self.cpu_percent > 90 or self.ram_percent > 95:
            return "red"
        if self.cpu_percent > 75 or self.ram_percent > 85:
            return "yellow"
        return "green"


@dataclass
class WindowInfo:
    """Information about the currently active window."""
    title: str = ""
    process_name: str = ""
    timestamp: float = 0.0

    @property
    def app_category(self) -> str:
        """Classify the active app into a category."""
        title_lower = self.title.lower()
        proc_lower = self.process_name.lower()

        # Code editors
        if any(x in proc_lower for x in ["code", "pycharm", "idea", "sublime", "vim", "nvim"]):
            return "coding"
        if any(x in title_lower for x in ["visual studio", ".py", ".js", ".java", ".cpp"]):
            return "coding"

        # Browsers
        if any(x in proc_lower for x in ["chrome", "firefox", "edge", "brave", "opera"]):
            # Check if it's a specific site
            if any(x in title_lower for x in ["github", "gitlab", "stackoverflow"]):
                return "coding"
            if any(x in title_lower for x in ["youtube", "netflix", "twitch"]):
                return "entertainment"
            if any(x in title_lower for x in ["gmail", "outlook", "mail"]):
                return "email"
            if any(x in title_lower for x in ["linkedin", "indeed", "glassdoor"]):
                return "job_search"
            return "browsing"

        # Terminal
        if any(x in proc_lower for x in ["cmd", "powershell", "terminal", "bash", "wt"]):
            return "terminal"

        # Documents
        if any(x in proc_lower for x in ["word", "docs", "notion", "obsidian"]):
            return "writing"
        if any(x in proc_lower for x in ["excel", "sheets", "calc"]):
            return "spreadsheet"
        if any(x in proc_lower for x in ["powerpoint", "slides"]):
            return "presentation"

        # Communication
        if any(x in proc_lower for x in ["discord", "slack", "teams", "telegram", "whatsapp"]):
            return "communication"

        # Security tools
        if any(x in proc_lower for x in ["wireshark", "burp", "nmap", "metasploit"]):
            return "security"

        return "other"


@dataclass
class ClipboardState:
    """Tracks clipboard content."""
    content: str = ""
    content_type: str = "text"  # text, url, code, email, path
    timestamp: float = 0.0
    analyzed: bool = False


@dataclass
class AwarenessEvent:
    """An event detected by the awareness engine."""
    event_type: str          # clipboard_url, high_cpu, suspicious_url, new_window, etc.
    severity: str            # info, warning, alert
    message: str             # Human-readable description
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    handled: bool = False


# ═══════════════════════════════════════════════════════════
#  Awareness Engine
# ═══════════════════════════════════════════════════════════

class AwarenessEngine:
    """
    Monitors the user's environment and generates events.

    Watches:
    - Active window (what app, what content)
    - Clipboard (URLs, code, suspicious content)
    - System health (CPU, RAM, battery, disk)
    - Network activity
    - Process list changes
    """

    def __init__(self, app):
        self.app = app
        self._running = False
        self._threads = []

        # State
        self.system_health = SystemHealth()
        self.active_window = WindowInfo()
        self.clipboard = ClipboardState()
        self._last_clipboard = ""
        self._previous_window = ""

        # Event queue
        self._events: list[AwarenessEvent] = []
        self._event_handlers: list[Callable] = []
        self._max_events = 100

        # Monitoring intervals (seconds)
        self._system_interval = 15
        self._window_interval = 3
        self._clipboard_interval = 2

        # Thresholds for alerts
        self._cpu_warning = 85
        self._ram_warning = 90
        self._battery_warning = 15

        # Track what we've already alerted about
        self._alerted = set()

    def start(self):
        """Start all monitoring threads."""
        self._running = True

        monitors = [
            ("jarvis-sysmon", self._system_monitor_loop),
            ("jarvis-winmon", self._window_monitor_loop),
            ("jarvis-clipmon", self._clipboard_monitor_loop),
        ]

        for name, target in monitors:
            t = threading.Thread(target=target, daemon=True, name=name)
            t.start()
            self._threads.append(t)

        logger.info("Awareness engine online — %d monitors active", len(monitors))

    def stop(self):
        self._running = False

    def on_event(self, handler: Callable):
        """Register an event handler."""
        self._event_handlers.append(handler)

    # ══════════════════════════════════════════════════════════
    # SYSTEM HEALTH MONITORING
    # ══════════════════════════════════════════════════════════

    def _system_monitor_loop(self):
        while self._running:
            try:
                self._update_system_health()
                self._check_system_alerts()
            except Exception as e:
                logger.error("System monitor error: %s", e)
            time.sleep(self._system_interval)

    def _update_system_health(self):
        try:
            import psutil
        except ImportError:
            return

        try:
            self.system_health.cpu_percent = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            self.system_health.ram_percent = mem.percent
            self.system_health.ram_used_gb = mem.used / (1024 ** 3)
            self.system_health.ram_total_gb = mem.total / (1024 ** 3)

            disk = psutil.disk_usage("/")
            self.system_health.disk_percent = disk.percent

            self.system_health.process_count = len(psutil.pids())

            # Battery
            bat = psutil.sensors_battery()
            if bat:
                self.system_health.battery_percent = bat.percent
                self.system_health.battery_plugged = bat.power_plugged

            # Network I/O
            net = psutil.net_io_counters()
            self.system_health.network_sent_mb = net.bytes_sent / (1024 ** 2)
            self.system_health.network_recv_mb = net.bytes_recv / (1024 ** 2)

            # Uptime
            boot = psutil.boot_time()
            self.system_health.uptime_hours = (time.time() - boot) / 3600

        except Exception as e:
            logger.error("Health update failed: %s", e)

    def _check_system_alerts(self):
        h = self.system_health

        # CPU warning
        if h.cpu_percent > self._cpu_warning:
            alert_key = "high_cpu"
            if alert_key not in self._alerted:
                self._emit_event(AwarenessEvent(
                    event_type="high_cpu",
                    severity="warning",
                    message=f"CPU usage is at {h.cpu_percent:.0f}%. Something may be straining your system.",
                    data={"cpu_percent": h.cpu_percent},
                ))
                self._alerted.add(alert_key)
        else:
            self._alerted.discard("high_cpu")

        # RAM warning
        if h.ram_percent > self._ram_warning:
            alert_key = "high_ram"
            if alert_key not in self._alerted:
                self._emit_event(AwarenessEvent(
                    event_type="high_ram",
                    severity="warning",
                    message=f"RAM usage at {h.ram_percent:.0f}%. Consider closing some applications.",
                    data={"ram_percent": h.ram_percent},
                ))
                self._alerted.add(alert_key)
        else:
            self._alerted.discard("high_ram")

        # Battery warning
        if h.battery_percent is not None and not h.battery_plugged:
            if h.battery_percent < self._battery_warning:
                alert_key = "low_battery"
                if alert_key not in self._alerted:
                    self._emit_event(AwarenessEvent(
                        event_type="low_battery",
                        severity="alert",
                        message=f"Battery at {h.battery_percent:.0f}%. Plug in soon.",
                        data={"battery_percent": h.battery_percent},
                    ))
                    self._alerted.add(alert_key)
            else:
                self._alerted.discard("low_battery")

        # Disk space warning
        if h.disk_percent > 90:
            alert_key = "disk_full"
            if alert_key not in self._alerted:
                self._emit_event(AwarenessEvent(
                    event_type="disk_full",
                    severity="warning",
                    message=f"Disk usage at {h.disk_percent:.0f}%. Running low on space.",
                    data={"disk_percent": h.disk_percent},
                ))
                self._alerted.add(alert_key)
        else:
            self._alerted.discard("disk_full")

    # ══════════════════════════════════════════════════════════
    # ACTIVE WINDOW MONITORING
    # ══════════════════════════════════════════════════════════

    def _window_monitor_loop(self):
        while self._running:
            try:
                self._update_active_window()
            except Exception as e:
                logger.error("Window monitor error: %s", e)
            time.sleep(self._window_interval)

    def _update_active_window(self):
        """Get the currently focused window title and process."""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()

            # Window title
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

            # Process name
            process_name = ""
            try:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                import psutil
                proc = psutil.Process(pid.value)
                process_name = proc.name()
            except Exception:
                pass

            # Detect window change
            if title != self._previous_window and title:
                self._previous_window = title
                self.active_window = WindowInfo(
                    title=title,
                    process_name=process_name,
                    timestamp=time.time(),
                )

                # Emit window change event
                self._emit_event(AwarenessEvent(
                    event_type="window_change",
                    severity="info",
                    message=f"Switched to: {process_name or title[:40]}",
                    data={
                        "title": title,
                        "process": process_name,
                        "category": self.active_window.app_category,
                    },
                ))

        except Exception:
            pass  # Not on Windows or missing ctypes

    # ══════════════════════════════════════════════════════════
    # CLIPBOARD MONITORING
    # ══════════════════════════════════════════════════════════

    def _clipboard_monitor_loop(self):
        while self._running:
            try:
                self._check_clipboard()
            except Exception as e:
                logger.error("Clipboard monitor error: %s", e)
            time.sleep(self._clipboard_interval)

    def _check_clipboard(self):
        """Check clipboard for new content and classify it."""
        try:
            content = self._read_clipboard_text()

            if not content or content == self._last_clipboard:
                return

            self._last_clipboard = content
            content_type = self._classify_clipboard(content)

            self.clipboard = ClipboardState(
                content=content[:2000],  # Limit stored size
                content_type=content_type,
                timestamp=time.time(),
                analyzed=False,
            )

            # Emit events for interesting clipboard content
            if content_type == "url":
                self._emit_event(AwarenessEvent(
                    event_type="clipboard_url",
                    severity="info",
                    message=f"URL copied: {content[:80]}",
                    data={"url": content, "type": content_type},
                ))

                # Check for suspicious URLs
                if self._is_suspicious_url(content):
                    self._emit_event(AwarenessEvent(
                        event_type="suspicious_url",
                        severity="alert",
                        message=f"That URL looks suspicious: {content[:60]}",
                        data={"url": content},
                    ))

            elif content_type == "code":
                self._emit_event(AwarenessEvent(
                    event_type="clipboard_code",
                    severity="info",
                    message="Code snippet copied to clipboard.",
                    data={"code_preview": content[:200]},
                ))

            elif content_type == "error":
                self._emit_event(AwarenessEvent(
                    event_type="clipboard_error",
                    severity="info",
                    message="Error text copied. Need help debugging?",
                    data={"error_preview": content[:300]},
                ))

        except Exception:
            pass

    def _read_clipboard_text(self) -> str:
        """
        Read clipboard text without touching Tk from a worker thread.

        Tk clipboard calls from background threads can terminate the app on
        Windows without a clean traceback, so the awareness monitor uses the
        native clipboard API instead.
        """
        if os.name != "nt":
            return ""

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        cf_unicode_text = 13

        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_int
        user32.GetClipboardData.argtypes = [ctypes.c_uint]
        user32.GetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_int

        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_int

        for _ in range(3):
            if user32.OpenClipboard(None):
                break
            time.sleep(0.05)
        else:
            return ""

        try:
            handle = user32.GetClipboardData(cf_unicode_text)
            if not handle:
                return ""

            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return ""

            try:
                return ctypes.wstring_at(pointer) or ""
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def _classify_clipboard(self, text: str) -> str:
        """Classify clipboard content type."""
        text = text.strip()

        # URL
        if re.match(r"https?://\S+", text):
            return "url"

        # File path
        if re.match(r"[A-Z]:\\", text) or text.startswith("/"):
            return "path"

        # Email
        if re.match(r"[^@]+@[^@]+\.[^@]+$", text):
            return "email"

        # Error/traceback
        if any(x in text.lower() for x in [
            "traceback", "error:", "exception:", "failed",
            "errno", "syntaxerror", "typeerror", "valueerror",
        ]):
            return "error"

        # Code
        code_signals = [
            "def ", "class ", "import ", "function ",
            "const ", "let ", "var ", "return ",
            "if (", "for (", "while (",
            "=>", "->", "::", "#!/",
        ]
        if any(sig in text for sig in code_signals):
            return "code"

        # IP address
        if re.match(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", text):
            return "ip"

        return "text"

    def _is_suspicious_url(self, url: str) -> bool:
        """Quick heuristic check for suspicious URLs."""
        url_lower = url.lower()
        suspicious_patterns = [
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",  # IP-based URL
            r"bit\.ly|tinyurl|t\.co|goo\.gl",          # URL shorteners
            r"login|signin|account|verify|secure|update|confirm",  # Phishing keywords
            r"\.ru/|\.cn/|\.tk/|\.ml/|\.ga/|\.cf/",   # Suspicious TLDs
            r"@",                                       # @ in URL (credential stuffing)
            r"-{3,}",                                   # Many dashes (typosquatting)
        ]

        # Check for misspelled popular domains
        typosquat = [
            r"g00gle|googIe|gogle",
            r"faceb00k|facbook",
            r"paypa1|paypaI",
            r"amaz0n|amazom",
            r"micros0ft|microsft",
        ]

        for pattern in suspicious_patterns + typosquat:
            if re.search(pattern, url_lower):
                return True

        return False

    # ══════════════════════════════════════════════════════════
    # EVENT SYSTEM
    # ══════════════════════════════════════════════════════════

    def _emit_event(self, event: AwarenessEvent):
        """Emit an awareness event to all handlers."""
        self._events.append(event)
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error("Event handler error: %s", e)

    def get_recent_events(self, count: int = 10,
                          severity: str = None) -> list[AwarenessEvent]:
        """Get recent events, optionally filtered by severity."""
        events = self._events
        if severity:
            events = [e for e in events if e.severity == severity]
        return events[-count:]

    def get_unhandled_alerts(self) -> list[AwarenessEvent]:
        """Get alerts that haven't been shown to the user yet."""
        return [e for e in self._events
                if e.severity in ("warning", "alert") and not e.handled]

    def mark_handled(self, event: AwarenessEvent):
        event.handled = True

    # ══════════════════════════════════════════════════════════
    # QUERIES — for natural language requests
    # ══════════════════════════════════════════════════════════

    def get_system_status(self) -> str:
        """Natural language system status for JARVIS to speak."""
        h = self.system_health

        parts = []

        # CPU
        if h.cpu_percent > 80:
            parts.append(f"CPU is running hot at {h.cpu_percent:.0f}%.")
        elif h.cpu_percent > 50:
            parts.append(f"CPU at {h.cpu_percent:.0f}%, moderate load.")
        else:
            parts.append(f"CPU at {h.cpu_percent:.0f}%, running smooth.")

        # RAM
        parts.append(f"Memory at {h.ram_percent:.0f}% ({h.ram_used_gb:.1f}/{h.ram_total_gb:.1f} GB).")

        # Battery
        if h.battery_percent is not None:
            if h.battery_plugged:
                parts.append(f"Battery at {h.battery_percent:.0f}%, charging.")
            elif h.battery_percent < 20:
                parts.append(f"Battery low — {h.battery_percent:.0f}%. Plug in soon.")
            else:
                parts.append(f"Battery at {h.battery_percent:.0f}%.")

        # Disk
        if h.disk_percent > 85:
            parts.append(f"Disk at {h.disk_percent:.0f}% — getting tight.")
        else:
            parts.append(f"Disk at {h.disk_percent:.0f}%.")

        # Uptime
        if h.uptime_hours > 0:
            if h.uptime_hours > 24:
                days = int(h.uptime_hours / 24)
                parts.append(f"System uptime: {days} day{'s' if days > 1 else ''}.")
            else:
                parts.append(f"System uptime: {h.uptime_hours:.0f} hours.")

        # Processes
        parts.append(f"{h.process_count} processes running.")

        return " ".join(parts)

    def get_current_context(self) -> str:
        """What is the user currently doing? (for LLM context)"""
        win = self.active_window
        if not win.title:
            return ""

        category = win.app_category
        category_labels = {
            "coding": "writing code",
            "browsing": "browsing the web",
            "terminal": "working in the terminal",
            "writing": "writing a document",
            "communication": "chatting",
            "email": "checking email",
            "entertainment": "watching content",
            "security": "running security tools",
            "job_search": "looking at job listings",
        }

        activity = category_labels.get(category, f"using {win.process_name}")
        return f"[CONTEXT] Dev is currently {activity} ({win.title[:60]})"

    def get_clipboard_context(self) -> str:
        """Clipboard context for LLM."""
        cb = self.clipboard
        if not cb.content or (time.time() - cb.timestamp) > 300:
            return ""
        return f"[CLIPBOARD] {cb.content_type}: {cb.content[:200]}"
