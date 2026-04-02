"""
J.A.R.V.I.S — Cybersecurity Plugin v2.0
Network analysis, security auditing, threat intelligence, and proactive defense.

Commands:
    /portscan <host>       — Scan common ports on a target
    /netscan               — Discover devices on local network
    /dnslookup <domain>    — DNS records lookup
    /whois <domain>        — WHOIS domain information
    /headers <url>         — Analyze HTTP security headers
    /pwcheck <password>    — Password strength analysis
    /hashid <hash>         — Identify hash type
    /hashcrack <hash>      — Check hash against known databases
    /mynet                 — Show local network info
    /wifi                  — List nearby WiFi networks (Windows)
    /processes             — List running processes with network access
    /threat <ip>           — Threat intelligence lookup for an IP
    /urlscan <url>         — Scan URL for phishing/malware
    /filescan <path>       — Scan file hash for malware
    /audit                 — Full system security audit
    /phish                 — Analyze pasted email for phishing
    /netmon                — Toggle real-time network monitor
    /seclog                — View security action log

All tools are for DEFENSIVE / EDUCATIONAL purposes only.
"""

import os
import socket
import struct
import threading
import platform
import subprocess
import re
import json
import urllib.request
import urllib.parse
import urllib.error
import hashlib
import string
import time
from datetime import datetime

from core.plugin_manager import PluginBase


def _fetch(url: str, timeout: int = 10) -> dict | str:
    """Fetch JSON or text from a URL."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "JARVIS-Security/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
    except Exception as e:
        return {"error": str(e)}


def _bg(func, jarvis, *args):
    """Run a function in background thread, post result to chat.
    Passes jarvis as first arg to the function, then *args after."""
    def _run():
        try:
            result = func(jarvis, *args)
            jarvis.root.after(0, lambda: jarvis.chat.add_message("assistant", result))
        except Exception as e:
            jarvis.root.after(0, lambda: jarvis.chat.add_message(
                "system", f"Security module error: {e}"))
    threading.Thread(target=_run, daemon=True).start()


class CyberPlugin(PluginBase):
    name = "cyber"
    description = "Cybersecurity — scanning, auditing, threat intel, proactive defense"
    version = "2.0"

    def __init__(self, jarvis):
        super().__init__(jarvis)
        self._netmon_active = False
        self._netmon_thread = None
        self._known_connections = set()
        self._security_log = []

    def activate(self):
        pass

    def deactivate(self):
        self._netmon_active = False

    def on_command(self, command: str, args: str) -> bool:
        cmd = command.lower()
        if cmd == "/portscan":
            self._show("Scanning ports...")
            _bg(self.port_scan, self.jarvis, args)
            return True
        if cmd == "/netscan":
            self._show("Scanning local network...")
            _bg(self.net_scan, self.jarvis)
            return True
        if cmd == "/dnslookup":
            self._show("Looking up DNS...")
            _bg(self.dns_lookup, self.jarvis, args)
            return True
        if cmd == "/whois":
            self._show("Running WHOIS lookup...")
            _bg(self.whois_lookup, self.jarvis, args)
            return True
        if cmd == "/headers":
            self._show("Analyzing security headers...")
            _bg(self.check_headers, self.jarvis, args)
            return True
        if cmd == "/pwcheck":
            self._show("Analyzing password...")
            _bg(self.password_check, self.jarvis, args)
            return True
        if cmd == "/hashid":
            self._show("Identifying hash...")
            _bg(self.hash_identify, self.jarvis, args)
            return True
        if cmd == "/hashcrack":
            self._show("Checking hash databases...")
            _bg(self.hash_crack, self.jarvis, args)
            return True
        if cmd == "/mynet":
            self._show("Gathering network info...")
            _bg(self.my_network, self.jarvis)
            return True
        if cmd == "/wifi":
            self._show("Scanning WiFi networks...")
            _bg(self.wifi_scan, self.jarvis)
            return True
        if cmd == "/processes":
            self._show("Listing network processes...")
            _bg(self.net_processes, self.jarvis)
            return True
        if cmd == "/threat":
            self._show("Checking threat intelligence...")
            _bg(self.threat_lookup, self.jarvis, args)
            return True
        if cmd == "/urlscan":
            self._show("Scanning URL for threats...")
            _bg(self.url_scan, self.jarvis, args)
            return True
        if cmd == "/filescan":
            self._show("Scanning file...")
            _bg(self.file_scan, self.jarvis, args)
            return True
        if cmd == "/audit":
            self._show("Running full security audit...")
            _bg(self.security_audit, self.jarvis)
            return True
        if cmd == "/phish":
            self._show("Analyzing for phishing indicators...")
            _bg(self.phishing_detect, self.jarvis, args)
            return True
        if cmd == "/netmon":
            self._toggle_netmon()
            return True
        if cmd == "/seclog":
            self._show_security_log()
            return True
        return False

    def _show(self, msg: str):
        self.jarvis.chat.add_message("system", msg)

    # ══════════════════════════════════════════════════════════════
    # PORT SCANNING
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def port_scan(jarvis, host: str) -> str:
        if not host:
            return "Usage: /portscan <host or IP>\nExample: /portscan 192.168.1.1"

        host = host.strip()

        # Resolve hostname
        try:
            ip = socket.gethostbyname(host)
        except socket.gaierror:
            return f"Could not resolve host: {host}"

        # Common ports with service names
        PORTS = {
            21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
            53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP",
            443: "HTTPS", 445: "SMB", 993: "IMAPS", 995: "POP3S",
            3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
            5900: "VNC", 6379: "Redis", 8080: "HTTP-Alt",
            8443: "HTTPS-Alt", 27017: "MongoDB",
        }

        result = (
            f"Port Scan — {host} ({ip})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        open_ports = []
        closed_count = 0

        for port, service in sorted(PORTS.items()):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                conn = sock.connect_ex((ip, port))
                if conn == 0:
                    open_ports.append((port, service))
                else:
                    closed_count += 1
                sock.close()
            except Exception:
                closed_count += 1

        if open_ports:
            for port, service in open_ports:
                result += f"  {port:>5}/tcp   OPEN    {service}\n"
        else:
            result += "  No open ports found in common range.\n"

        result += f"\n  {len(open_ports)} open, {closed_count} closed"

        # Security warnings
        warnings = []
        open_port_nums = [p for p, _ in open_ports]
        if 23 in open_port_nums:
            warnings.append("Telnet (23) is insecure — use SSH instead")
        if 21 in open_port_nums:
            warnings.append("FTP (21) sends passwords in plaintext")
        if 3389 in open_port_nums:
            warnings.append("RDP (3389) exposed — consider VPN")
        if 445 in open_port_nums:
            warnings.append("SMB (445) open — risk of EternalBlue exploits")

        if warnings:
            result += "\n\n  ⚠ Security Warnings:\n"
            for w in warnings:
                result += f"    • {w}\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # LOCAL NETWORK SCAN (ARP)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def net_scan(jarvis) -> str:
        if platform.system() != "Windows":
            return "Network scan currently supports Windows only."

        try:
            output = subprocess.run(
                "arp -a", shell=True, capture_output=True, text=True, timeout=10
            ).stdout

            result = "Local Network Devices\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            devices = []
            for line in output.split("\n"):
                match = re.search(
                    r"(\d+\.\d+\.\d+\.\d+)\s+([\w-]+)\s+(\w+)", line
                )
                if match:
                    ip, mac, dtype = match.groups()
                    if ip != "255.255.255.255" and not ip.startswith("224."):
                        devices.append((ip, mac, dtype))
                        result += f"  {ip:<18} {mac:<20} {dtype}\n"

            result += f"\n  {len(devices)} devices found"
            return result
        except Exception as e:
            return f"Network scan error: {e}"

    # ══════════════════════════════════════════════════════════════
    # DNS LOOKUP
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def dns_lookup(jarvis, domain: str) -> str:
        if not domain:
            return "Usage: /dnslookup <domain>\nExample: /dnslookup google.com"

        domain = domain.strip().replace("http://", "").replace("https://", "").split("/")[0]

        result = f"DNS Lookup — {domain}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        # A records
        try:
            ips = socket.getaddrinfo(domain, None, socket.AF_INET)
            seen = set()
            for _, _, _, _, (ip, _) in ips:
                if ip not in seen:
                    result += f"  A      {ip}\n"
                    seen.add(ip)
        except socket.gaierror:
            result += "  Could not resolve A records.\n"

        # AAAA records (IPv6)
        try:
            ips6 = socket.getaddrinfo(domain, None, socket.AF_INET6)
            seen6 = set()
            for _, _, _, _, (ip, _, _, _) in ips6:
                if ip not in seen6:
                    result += f"  AAAA   {ip}\n"
                    seen6.add(ip)
        except Exception:
            pass

        # Use nslookup for more details on Windows
        if platform.system() == "Windows":
            try:
                ns_out = subprocess.run(
                    f"nslookup -type=MX {domain}", shell=True,
                    capture_output=True, text=True, timeout=5
                ).stdout
                for line in ns_out.split("\n"):
                    if "mail exchanger" in line.lower() or "MX" in line:
                        result += f"  MX     {line.strip()}\n"
            except Exception:
                pass

        return result

    # ══════════════════════════════════════════════════════════════
    # WHOIS LOOKUP (free API)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def whois_lookup(jarvis, domain: str) -> str:
        if not domain:
            return "Usage: /whois <domain>\nExample: /whois google.com"

        domain = domain.strip().replace("http://", "").replace("https://", "").split("/")[0]
        data = _fetch(f"https://api.api-ninjas.com/v1/whois?domain={domain}")

        if isinstance(data, dict) and not data.get("error"):
            result = f"WHOIS — {domain}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            fields = [
                ("domain_name", "Domain"),
                ("registrar", "Registrar"),
                ("creation_date", "Created"),
                ("expiration_date", "Expires"),
                ("name_servers", "Nameservers"),
                ("dnssec", "DNSSEC"),
            ]
            for key, label in fields:
                val = data.get(key, "N/A")
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val[:3])
                result += f"  {label:<14} {val}\n"
            return result
        else:
            # Fallback to command line
            if platform.system() == "Windows":
                return f"WHOIS lookup requires API access. Try: /dnslookup {domain}"
            return f"Could not fetch WHOIS for {domain}"

    # ══════════════════════════════════════════════════════════════
    # HTTP SECURITY HEADERS
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def check_headers(jarvis, url: str) -> str:
        if not url:
            return "Usage: /headers <url>\nExample: /headers https://google.com"

        if not url.startswith("http"):
            url = "https://" + url

        try:
            req = urllib.request.Request(url, method="HEAD", headers={
                "User-Agent": "JARVIS-Security/1.0"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                headers = dict(resp.headers)
        except Exception as e:
            return f"Could not reach {url}: {e}"

        result = f"Security Headers — {url}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        # Check important security headers
        checks = {
            "Strict-Transport-Security": ("HSTS", "Forces HTTPS connections"),
            "Content-Security-Policy": ("CSP", "Prevents XSS attacks"),
            "X-Frame-Options": ("Clickjack Protection", "Prevents iframe embedding"),
            "X-Content-Type-Options": ("MIME Sniffing", "Prevents MIME type attacks"),
            "X-XSS-Protection": ("XSS Filter", "Browser XSS protection"),
            "Referrer-Policy": ("Referrer Policy", "Controls referrer info"),
            "Permissions-Policy": ("Permissions", "Controls browser features"),
        }

        score = 0
        total = len(checks)

        for header, (short_name, desc) in checks.items():
            value = headers.get(header, None)
            if value:
                result += f"  ✓ {short_name:<22} {value[:50]}\n"
                score += 1
            else:
                result += f"  ✗ {short_name:<22} MISSING — {desc}\n"

        # Server header (info leak)
        server = headers.get("Server", "")
        if server:
            result += f"\n  ⚠ Server header exposes: {server}\n"
            result += "    Consider hiding server version.\n"

        grade = "A+" if score == total else "A" if score >= 6 else "B" if score >= 4 else "C" if score >= 2 else "F"
        result += f"\n  Security Score: {score}/{total} — Grade: {grade}"

        return result

    # ══════════════════════════════════════════════════════════════
    # PASSWORD STRENGTH CHECK
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def password_check(jarvis, password: str) -> str:
        if not password:
            return "Usage: /pwcheck <password>\nI'll analyze its strength (not stored)."

        length = len(password)
        has_upper = bool(re.search(r"[A-Z]", password))
        has_lower = bool(re.search(r"[a-z]", password))
        has_digit = bool(re.search(r"\d", password))
        has_special = bool(re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]", password))
        has_space = " " in password

        # Calculate entropy
        charset = 0
        if has_lower: charset += 26
        if has_upper: charset += 26
        if has_digit: charset += 10
        if has_special: charset += 32
        if has_space: charset += 1

        import math
        entropy = length * math.log2(charset) if charset > 0 else 0

        # Score
        score = 0
        if length >= 8: score += 1
        if length >= 12: score += 1
        if length >= 16: score += 1
        if has_upper: score += 1
        if has_lower: score += 1
        if has_digit: score += 1
        if has_special: score += 1
        if not re.search(r"(.)\1{2,}", password): score += 1  # No repeated chars

        # Common patterns
        warnings = []
        if re.search(r"(123|abc|qwerty|password|admin|letmein)", password.lower()):
            warnings.append("Contains common pattern")
            score -= 2
        if length < 8:
            warnings.append("Too short — minimum 8 characters")
        if re.search(r"^[a-zA-Z]+$", password):
            warnings.append("Letters only — add numbers and symbols")
        if re.search(r"^\d+$", password):
            warnings.append("Numbers only — very weak")

        # Rating
        if score >= 7: rating = "EXCELLENT"
        elif score >= 5: rating = "STRONG"
        elif score >= 3: rating = "MODERATE"
        elif score >= 1: rating = "WEAK"
        else: rating = "CRITICAL"

        # Crack time estimation
        guesses_per_sec = 10_000_000_000  # 10B guesses/sec (GPU)
        combinations = charset ** length if charset > 0 else 1
        seconds = combinations / guesses_per_sec

        if seconds < 1: crack_time = "Instantly"
        elif seconds < 60: crack_time = f"{seconds:.0f} seconds"
        elif seconds < 3600: crack_time = f"{seconds/60:.0f} minutes"
        elif seconds < 86400: crack_time = f"{seconds/3600:.0f} hours"
        elif seconds < 31536000: crack_time = f"{seconds/86400:.0f} days"
        elif seconds < 31536000 * 1000: crack_time = f"{seconds/31536000:.0f} years"
        else: crack_time = "Centuries+"

        result = (
            f"Password Analysis\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Length:      {length} characters\n"
            f"  Uppercase:   {'✓' if has_upper else '✗'}\n"
            f"  Lowercase:   {'✓' if has_lower else '✗'}\n"
            f"  Numbers:     {'✓' if has_digit else '✗'}\n"
            f"  Symbols:     {'✓' if has_special else '✗'}\n"
            f"  Entropy:     {entropy:.1f} bits\n"
            f"  Crack Time:  {crack_time} (at 10B guesses/sec)\n"
            f"\n  Rating: {rating} ({score}/8)\n"
        )

        if warnings:
            result += "\n  ⚠ Warnings:\n"
            for w in warnings:
                result += f"    • {w}\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # HASH IDENTIFICATION
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def hash_identify(jarvis, hash_str: str) -> str:
        if not hash_str:
            return "Usage: /hashid <hash string>"

        hash_str = hash_str.strip()
        length = len(hash_str)

        # Common hash lengths and types
        hash_types = {
            32: ["MD5", "NTLM", "MD4"],
            40: ["SHA-1", "RIPEMD-160"],
            56: ["SHA-224"],
            64: ["SHA-256", "SHA3-256", "Keccak-256"],
            96: ["SHA-384", "SHA3-384"],
            128: ["SHA-512", "SHA3-512", "Whirlpool"],
        }

        result = f"Hash Identification\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        result += f"  Input:  {hash_str[:60]}{'...' if len(hash_str) > 60 else ''}\n"
        result += f"  Length: {length} characters\n\n"

        # Check if it's hex
        if re.match(r"^[a-fA-F0-9]+$", hash_str):
            matches = hash_types.get(length, [])
            if matches:
                result += "  Possible types:\n"
                for h in matches:
                    result += f"    • {h}\n"
            else:
                result += f"  Unknown hash length ({length}). Not a standard hash.\n"

            # Check for bcrypt/scrypt patterns
            if hash_str.startswith("$2") and "$" in hash_str[2:]:
                result = f"  Type: bcrypt (password hash)\n"
        elif hash_str.startswith("$2"):
            result += "  Type: bcrypt\n"
        elif hash_str.startswith("$6$"):
            result += "  Type: SHA-512 crypt (Unix)\n"
        elif hash_str.startswith("$5$"):
            result += "  Type: SHA-256 crypt (Unix)\n"
        elif hash_str.startswith("$1$"):
            result += "  Type: MD5 crypt (Unix)\n"
        else:
            result += "  Could not identify hash format.\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # HASH LOOKUP (HaveIBeenPwned-style range check)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def hash_crack(jarvis, hash_str: str) -> str:
        if not hash_str:
            return "Usage: /hashcrack <hash or password>\nChecks if password hash appears in breach databases."

        hash_str = hash_str.strip()

        # If it looks like a plain password, hash it first
        if not re.match(r"^[a-fA-F0-9]{20,}$", hash_str):
            # Treat as password — check against HIBP
            password = hash_str
            sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
            prefix = sha1[:5]
            suffix = sha1[5:]

            try:
                data = _fetch(f"https://api.pwnedpasswords.com/range/{prefix}")
                if isinstance(data, str):
                    for line in data.split("\n"):
                        parts = line.strip().split(":")
                        if len(parts) == 2 and parts[0] == suffix:
                            count = int(parts[1])
                            return (
                                f"Password Breach Check\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"  ⚠ THIS PASSWORD HAS BEEN BREACHED!\n"
                                f"  Found {count:,} times in breach databases.\n"
                                f"  DO NOT use this password anywhere.\n"
                            )
                    return (
                        f"Password Breach Check\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"  ✓ Not found in known breach databases.\n"
                        f"  This doesn't guarantee safety — use strong, unique passwords.\n"
                    )
            except Exception as e:
                return f"Could not check breach database: {e}"
        else:
            return (
                f"Hash: {hash_str[:40]}...\n"
                f"To check if a password is breached, provide the plaintext.\n"
                f"I'll hash it with SHA-1 and check HaveIBeenPwned (k-anonymity, safe)."
            )

    # ══════════════════════════════════════════════════════════════
    # LOCAL NETWORK INFO
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def my_network(jarvis) -> str:
        result = "Network Configuration\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        # Hostname
        result += f"  Hostname: {socket.gethostname()}\n"

        # Local IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            result += f"  Local IP: {local_ip}\n"
        except Exception:
            result += "  Local IP: Could not determine\n"

        # Public IP
        try:
            pub_data = _fetch("https://ipapi.co/json/")
            if isinstance(pub_data, dict):
                result += f"  Public IP: {pub_data.get('ip', '?')}\n"
                result += f"  ISP: {pub_data.get('org', '?')}\n"
                result += f"  Location: {pub_data.get('city', '?')}, {pub_data.get('country_name', '?')}\n"
        except Exception:
            pass

        # Network interfaces (Windows)
        if platform.system() == "Windows":
            try:
                ipconfig = subprocess.run(
                    "ipconfig", shell=True, capture_output=True, text=True, timeout=5
                ).stdout
                # Extract gateway
                gw_match = re.search(r"Default Gateway.*?:\s*([\d.]+)", ipconfig)
                if gw_match:
                    result += f"  Gateway: {gw_match.group(1)}\n"
                # Extract subnet
                sub_match = re.search(r"Subnet Mask.*?:\s*([\d.]+)", ipconfig)
                if sub_match:
                    result += f"  Subnet: {sub_match.group(1)}\n"
                # DNS
                dns_out = subprocess.run(
                    "ipconfig /all", shell=True, capture_output=True, text=True, timeout=5
                ).stdout
                dns_matches = re.findall(r"DNS Servers.*?:\s*([\d.]+)", dns_out)
                if dns_matches:
                    result += f"  DNS: {', '.join(dns_matches[:2])}\n"
            except Exception:
                pass

        return result

    # ══════════════════════════════════════════════════════════════
    # WIFI SCAN (Windows)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def wifi_scan(jarvis) -> str:
        if platform.system() != "Windows":
            return "WiFi scan currently supports Windows only."

        try:
            output = subprocess.run(
                'netsh wlan show networks mode=Bssid',
                shell=True, capture_output=True, text=True, timeout=10,
            ).stdout

            result = "WiFi Networks\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            networks = []
            current = {}

            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("SSID") and "BSSID" not in line:
                    if current and current.get("ssid"):
                        networks.append(current)
                    ssid = line.split(":", 1)[1].strip() if ":" in line else ""
                    current = {"ssid": ssid or "(Hidden)"}
                elif "Authentication" in line:
                    current["auth"] = line.split(":", 1)[1].strip() if ":" in line else "?"
                elif "Encryption" in line:
                    current["enc"] = line.split(":", 1)[1].strip() if ":" in line else "?"
                elif "Signal" in line:
                    current["signal"] = line.split(":", 1)[1].strip() if ":" in line else "?"
                elif "Channel" in line and "channel" not in current:
                    current["channel"] = line.split(":", 1)[1].strip() if ":" in line else "?"

            if current and current.get("ssid"):
                networks.append(current)

            if not networks:
                return "No WiFi networks found. Is your WiFi adapter enabled?"

            # Sort by signal strength
            for net in networks:
                signal = net.get("signal", "0%").rstrip("%")
                try:
                    bars = int(signal)
                except ValueError:
                    bars = 0
                signal_bars = "█" * (bars // 20) + "░" * (5 - bars // 20)

                auth = net.get("auth", "?")
                security = "🔒" if "WPA" in auth or "WEP" in auth else "🔓"

                result += (
                    f"  {security} {net['ssid']:<28} {signal_bars} {net.get('signal', '?')}\n"
                    f"     Auth: {auth}  Enc: {net.get('enc', '?')}  Ch: {net.get('channel', '?')}\n"
                )

            # Security warnings
            open_nets = [n for n in networks if "Open" in n.get("auth", "")]
            wep_nets = [n for n in networks if "WEP" in n.get("auth", "")]
            if open_nets:
                result += f"\n  ⚠ {len(open_nets)} open network(s) — avoid for sensitive data\n"
            if wep_nets:
                result += f"  ⚠ {len(wep_nets)} WEP network(s) — WEP is crackable, use WPA2/3\n"

            result += f"\n  {len(networks)} networks found"
            return result
        except Exception as e:
            return f"WiFi scan error: {e}"

    # ══════════════════════════════════════════════════════════════
    # RUNNING PROCESSES WITH NETWORK
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def net_processes(jarvis) -> str:
        if platform.system() != "Windows":
            return "Process scan currently supports Windows only."

        try:
            output = subprocess.run(
                'netstat -b -n', shell=True, capture_output=True,
                text=True, timeout=10,
            ).stdout

            result = "Processes with Network Connections\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

            processes = {}
            current_proc = None

            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current_proc = line[1:-1]
                elif line.startswith("TCP") or line.startswith("UDP"):
                    parts = line.split()
                    if len(parts) >= 3:
                        proto = parts[0]
                        local = parts[1]
                        remote = parts[2] if len(parts) > 2 else "-"
                        state = parts[3] if len(parts) > 3 else ""
                        if current_proc:
                            if current_proc not in processes:
                                processes[current_proc] = []
                            processes[current_proc].append(
                                f"{proto} {local} → {remote} {state}"
                            )

            if processes:
                for proc, connections in sorted(processes.items()):
                    result += f"\n  [{proc}]\n"
                    for conn in connections[:3]:  # Limit per process
                        result += f"    {conn}\n"
                    if len(connections) > 3:
                        result += f"    ... +{len(connections)-3} more\n"
            else:
                result += "  No network connections found (try running as admin).\n"

            return result
        except Exception as e:
            return f"Process scan error: {e}\n(May need admin privileges)"

    # ══════════════════════════════════════════════════════════════
    # THREAT INTELLIGENCE (free APIs)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def threat_lookup(jarvis, ip: str) -> str:
        if not ip:
            return "Usage: /threat <IP address>\nChecks IP against threat databases."

        ip = ip.strip()

        result = f"Threat Intelligence — {ip}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        # AbuseIPDB check (free, limited)
        try:
            abuse_data = _fetch(f"https://api.abuseipdb.com/api/v2/check?ipAddress={ip}")
            if isinstance(abuse_data, dict) and abuse_data.get("data"):
                data = abuse_data["data"]
                score = data.get("abuseConfidenceScore", 0)
                reports = data.get("totalReports", 0)
                result += f"  Abuse Score: {score}%\n"
                result += f"  Reports: {reports}\n"
        except Exception:
            pass

        # IP geolocation for context
        try:
            geo = _fetch(f"https://ipapi.co/{ip}/json/")
            if isinstance(geo, dict) and not geo.get("error"):
                result += f"  Location: {geo.get('city', '?')}, {geo.get('country_name', '?')}\n"
                result += f"  ISP: {geo.get('org', '?')}\n"
                result += f"  ASN: {geo.get('asn', '?')}\n"
        except Exception:
            pass

        # Reverse DNS
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            result += f"  Reverse DNS: {hostname}\n"
        except Exception:
            result += "  Reverse DNS: No PTR record\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # URL SAFETY SCANNER (Phishing Detection)
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def url_scan(jarvis, url: str) -> str:
        if not url:
            return "Usage: /urlscan <url>\nExample: /urlscan https://suspicious-site.com"

        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        result = f"URL Safety Scan\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n  URL: {url}\n\n"
        risk_score = 0
        warnings = []

        # 1. Parse URL for suspicious patterns
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Check for IP address instead of domain
        if re.match(r"^\d+\.\d+\.\d+\.\d+", domain):
            risk_score += 30
            warnings.append("Uses IP address instead of domain name")

        # Check for excessive subdomains (phishing tactic)
        parts = domain.split(".")
        if len(parts) > 4:
            risk_score += 20
            warnings.append(f"Excessive subdomains ({len(parts)} levels)")

        # Check for lookalike domains
        lookalikes = {
            "paypa1": "paypal", "g00gle": "google", "micros0ft": "microsoft",
            "amaz0n": "amazon", "faceb00k": "facebook", "app1e": "apple",
            "netfl1x": "netflix", "1nstagram": "instagram",
        }
        for fake, real in lookalikes.items():
            if fake in domain:
                risk_score += 50
                warnings.append(f"Lookalike domain — mimics {real}")

        # Check for suspicious TLDs
        sus_tlds = [".xyz", ".top", ".club", ".work", ".buzz", ".tk", ".ml", ".ga", ".cf"]
        for tld in sus_tlds:
            if domain.endswith(tld):
                risk_score += 15
                warnings.append(f"Suspicious TLD: {tld}")

        # Check for URL obfuscation
        if "@" in url:
            risk_score += 40
            warnings.append("Contains @ symbol — possible URL obfuscation")
        if url.count("/") > 8:
            risk_score += 10
            warnings.append("Deeply nested path — possible phishing redirect")
        if re.search(r"%[0-9a-fA-F]{2}", url):
            encoded_count = len(re.findall(r"%[0-9a-fA-F]{2}", url))
            if encoded_count > 3:
                risk_score += 15
                warnings.append(f"Heavy URL encoding ({encoded_count} encoded chars)")

        # Check for login/credential keywords in URL
        cred_words = ["login", "signin", "verify", "secure", "account", "update",
                       "confirm", "password", "banking", "wallet"]
        for word in cred_words:
            if word in url.lower():
                risk_score += 10
                warnings.append(f"Contains credential keyword: '{word}'")
                break

        # 2. Check domain age / DNS
        try:
            ip = socket.gethostbyname(parsed.hostname or domain)
            result += f"  Resolved IP: {ip}\n"
        except socket.gaierror:
            risk_score += 25
            warnings.append("Domain does not resolve — may be dead or new")

        # 3. Check HTTPS
        if parsed.scheme != "https":
            risk_score += 20
            warnings.append("Not using HTTPS — data sent in plaintext")

        # 4. Try to fetch and check response
        try:
            req = urllib.request.Request(url, method="HEAD", headers={
                "User-Agent": "JARVIS-Security/1.0"
            })
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.getcode()
                final_url = resp.url
                if final_url != url:
                    risk_score += 15
                    warnings.append(f"Redirects to: {final_url[:60]}")
                result += f"  Status: {status}\n"
        except urllib.error.HTTPError as e:
            result += f"  Status: {e.code}\n"
        except Exception:
            risk_score += 10
            warnings.append("Could not reach URL")

        # 5. Google Safe Browsing check (transparency report)
        try:
            sb_data = _fetch(
                f"https://transparencyreport.google.com/safe-browsing/search?url={urllib.parse.quote(url)}"
            )
            if isinstance(sb_data, str) and "unsafe" in sb_data.lower():
                risk_score += 40
                warnings.append("Flagged by Google Safe Browsing")
        except Exception:
            pass

        # Calculate verdict
        risk_score = min(risk_score, 100)
        if risk_score >= 70:
            verdict = "DANGEROUS"
            emoji = "🔴"
        elif risk_score >= 40:
            verdict = "SUSPICIOUS"
            emoji = "🟡"
        elif risk_score >= 15:
            verdict = "CAUTION"
            emoji = "🟠"
        else:
            verdict = "LIKELY SAFE"
            emoji = "🟢"

        result += f"\n  {emoji} Verdict: {verdict}\n"
        result += f"  Risk Score: {risk_score}/100\n"

        if warnings:
            result += "\n  Findings:\n"
            for w in warnings:
                result += f"    ⚠ {w}\n"
        else:
            result += "\n  No suspicious indicators found.\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # FILE MALWARE SCANNER
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def file_scan(jarvis, path: str) -> str:
        if not path:
            return "Usage: /filescan <file path>\nScans file hash against malware databases."

        path = path.strip().strip('"').strip("'")

        if not os.path.exists(path):
            return f"File not found: {path}"

        result = f"File Security Scan\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        result += f"  File: {os.path.basename(path)}\n"

        # File size
        size = os.path.getsize(path)
        if size > 1024 * 1024:
            result += f"  Size: {size / (1024*1024):.1f} MB\n"
        else:
            result += f"  Size: {size / 1024:.1f} KB\n"

        # Extension check
        ext = os.path.splitext(path)[1].lower()
        risky_exts = [".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".wsf",
                      ".scr", ".pif", ".msi", ".dll", ".com", ".hta"]
        if ext in risky_exts:
            result += f"  ⚠ Risky file type: {ext}\n"

        # Calculate hashes
        try:
            with open(path, "rb") as f:
                data = f.read()
            md5 = hashlib.md5(data).hexdigest()
            sha1 = hashlib.sha1(data).hexdigest()
            sha256 = hashlib.sha256(data).hexdigest()

            result += f"\n  MD5:    {md5}\n"
            result += f"  SHA-1:  {sha1}\n"
            result += f"  SHA-256: {sha256}\n"
        except PermissionError:
            return f"Permission denied: {path}"
        except Exception as e:
            return f"Error reading file: {e}"

        # Check against MalwareBazaar (free, no key)
        try:
            post_data = urllib.parse.urlencode({"query": "get_info", "hash": sha256}).encode()
            req = urllib.request.Request(
                "https://mb-api.abuse.ch/api/v1/",
                data=post_data,
                headers={"User-Agent": "JARVIS-Security/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                mb_data = json.loads(resp.read().decode())

            if mb_data.get("query_status") == "hash_not_found":
                result += "\n  ✓ Not found in MalwareBazaar database.\n"
            elif mb_data.get("query_status") == "ok":
                malware = mb_data.get("data", [{}])[0]
                result += f"\n  🔴 MALWARE DETECTED!\n"
                result += f"  Name: {malware.get('signature', 'Unknown')}\n"
                result += f"  Type: {malware.get('file_type', '?')}\n"
                result += f"  Tags: {', '.join(malware.get('tags', []))}\n"
                result += f"  First seen: {malware.get('first_seen', '?')}\n"
        except Exception:
            result += "\n  Could not check MalwareBazaar (offline/timeout).\n"

        # Check HaveIBeenPwned-style for passwords in the file
        if ext in [".txt", ".csv", ".log"]:
            result += "\n  Tip: For password files, use /hashcrack to check individual entries.\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # SYSTEM SECURITY AUDIT
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def security_audit(jarvis) -> str:
        if platform.system() != "Windows":
            return "Security audit currently supports Windows only."

        result = "System Security Audit\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        score = 0
        total = 0

        # 1. Windows Firewall
        total += 1
        try:
            fw = subprocess.run(
                'netsh advfirewall show allprofiles state',
                shell=True, capture_output=True, text=True, timeout=5,
            ).stdout
            if "ON" in fw.upper():
                result += "  ✓ Firewall: ENABLED\n"
                score += 1
            else:
                result += "  ✗ Firewall: DISABLED — enable immediately!\n"
        except Exception:
            result += "  ? Firewall: Could not check\n"

        # 2. Windows Defender / Antivirus
        total += 1
        try:
            av = subprocess.run(
                'powershell -c "Get-MpComputerStatus | Select-Object -Property AntivirusEnabled,RealTimeProtectionEnabled,AntivirusSignatureLastUpdated"',
                shell=True, capture_output=True, text=True, timeout=10,
            ).stdout
            if "True" in av:
                result += "  ✓ Antivirus: ACTIVE\n"
                score += 1
                # Check if signatures are recent
                sig_match = re.search(r"(\d+/\d+/\d+)", av)
                if sig_match:
                    result += f"     Last updated: {sig_match.group(1)}\n"
            else:
                result += "  ✗ Antivirus: INACTIVE — enable Windows Defender!\n"
        except Exception:
            result += "  ? Antivirus: Could not check\n"

        # 3. Windows Update
        total += 1
        try:
            upd = subprocess.run(
                'powershell -c "(Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 1).InstalledOn"',
                shell=True, capture_output=True, text=True, timeout=15,
            ).stdout.strip()
            if upd:
                result += f"  ✓ Last update: {upd}\n"
                score += 1
            else:
                result += "  ? Updates: Could not determine last update\n"
        except Exception:
            result += "  ? Updates: Could not check\n"

        # 4. Auto-login check
        total += 1
        try:
            autologin = subprocess.run(
                'reg query "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon" /v AutoAdminLogon',
                shell=True, capture_output=True, text=True, timeout=5,
            ).stdout
            if "0x1" in autologin:
                result += "  ✗ Auto-login: ENABLED — security risk!\n"
            else:
                result += "  ✓ Auto-login: Disabled\n"
                score += 1
        except Exception:
            result += "  ✓ Auto-login: Disabled\n"
            score += 1

        # 5. Remote Desktop
        total += 1
        try:
            rdp = subprocess.run(
                'reg query "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" /v fDenyTSConnections',
                shell=True, capture_output=True, text=True, timeout=5,
            ).stdout
            if "0x1" in rdp:
                result += "  ✓ Remote Desktop: Disabled\n"
                score += 1
            else:
                result += "  ⚠ Remote Desktop: ENABLED — disable if not needed\n"
        except Exception:
            result += "  ? Remote Desktop: Could not check\n"

        # 6. UAC (User Account Control)
        total += 1
        try:
            uac = subprocess.run(
                'reg query "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" /v EnableLUA',
                shell=True, capture_output=True, text=True, timeout=5,
            ).stdout
            if "0x1" in uac:
                result += "  ✓ UAC: Enabled\n"
                score += 1
            else:
                result += "  ✗ UAC: DISABLED — serious security risk!\n"
        except Exception:
            result += "  ? UAC: Could not check\n"

        # 7. Open ports check
        total += 1
        try:
            netstat = subprocess.run(
                'netstat -an | findstr LISTENING',
                shell=True, capture_output=True, text=True, timeout=5,
            ).stdout
            listening = len(netstat.strip().split("\n")) if netstat.strip() else 0
            if listening < 20:
                result += f"  ✓ Listening ports: {listening} (normal)\n"
                score += 1
            else:
                result += f"  ⚠ Listening ports: {listening} (higher than typical)\n"
        except Exception:
            result += "  ? Ports: Could not check\n"

        # 8. Guest account
        total += 1
        try:
            guest = subprocess.run(
                'net user guest',
                shell=True, capture_output=True, text=True, timeout=5,
            ).stdout
            if "Account active               No" in guest:
                result += "  ✓ Guest account: Disabled\n"
                score += 1
            else:
                result += "  ⚠ Guest account: ACTIVE — consider disabling\n"
        except Exception:
            result += "  ? Guest account: Could not check\n"

        # Grade
        pct = (score / total * 100) if total > 0 else 0
        if pct >= 90: grade = "A"
        elif pct >= 75: grade = "B"
        elif pct >= 60: grade = "C"
        elif pct >= 40: grade = "D"
        else: grade = "F"

        result += f"\n  Security Score: {score}/{total} — Grade: {grade}\n"

        if pct < 75:
            result += "\n  Recommendations:\n"
            if score < total:
                result += "    • Fix all items marked with ✗\n"
            result += "    • Keep Windows and apps updated\n"
            result += "    • Use a password manager\n"
            result += "    • Enable 2FA on all accounts\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # EMAIL PHISHING DETECTOR
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def phishing_detect(jarvis, email_text: str) -> str:
        if not email_text:
            return (
                "Usage: /phish <paste email content>\n"
                "Or paste the email body and I'll analyze it for phishing."
            )

        result = "Email Phishing Analysis\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        risk_score = 0
        findings = []

        text = email_text.lower()

        # 1. Urgency language
        urgency = ["urgent", "immediately", "act now", "expire", "suspended",
                    "verify your", "confirm your", "within 24 hours",
                    "account will be", "action required", "limited time"]
        found_urgency = [u for u in urgency if u in text]
        if found_urgency:
            risk_score += 25
            findings.append(f"Urgency language: {', '.join(found_urgency[:3])}")

        # 2. Suspicious links
        urls = re.findall(r"https?://\S+", email_text)
        for url in urls:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower()
            if re.match(r"^\d+\.\d+\.\d+\.\d+", domain):
                risk_score += 30
                findings.append(f"Link uses IP address: {url[:50]}")
            if "@" in url:
                risk_score += 30
                findings.append(f"Link contains @ (obfuscation): {url[:50]}")
            sus_tlds = [".xyz", ".top", ".club", ".tk", ".ml"]
            for tld in sus_tlds:
                if domain.endswith(tld):
                    risk_score += 15
                    findings.append(f"Suspicious domain TLD in link: {domain}")

        # 3. Credential requests
        cred_words = ["password", "credit card", "ssn", "social security",
                       "bank account", "login credentials", "pin number"]
        found_creds = [c for c in cred_words if c in text]
        if found_creds:
            risk_score += 30
            findings.append(f"Requests sensitive info: {', '.join(found_creds)}")

        # 4. Sender spoofing indicators
        spoof_patterns = ["no-reply", "noreply", "support@", "admin@",
                           "security@", "helpdesk@"]
        for p in spoof_patterns:
            if p in text:
                risk_score += 5
                findings.append(f"Common spoofed sender pattern: {p}")
                break

        # 5. Grammar/spelling red flags
        grammar_flags = ["dear customer", "dear user", "dear sir/madam",
                          "we have detected", "your account has been",
                          "click here to", "click the link below"]
        found_grammar = [g for g in grammar_flags if g in text]
        if found_grammar:
            risk_score += 15
            findings.append(f"Generic phishing phrases: {', '.join(found_grammar[:2])}")

        # 6. Attachment mentions
        if re.search(r"(?:attached|attachment|download|open the file)", text):
            risk_score += 10
            findings.append("References attachments — verify sender before opening")

        # 7. Mismatched branding
        brands = ["paypal", "amazon", "microsoft", "apple", "google",
                   "netflix", "bank of america", "wells fargo", "chase"]
        brand_found = [b for b in brands if b in text]
        if brand_found and urls:
            for url in urls:
                for brand in brand_found:
                    if brand not in url.lower():
                        risk_score += 20
                        findings.append(f"Claims to be {brand.title()} but link goes elsewhere")
                        break

        # Verdict
        risk_score = min(risk_score, 100)
        if risk_score >= 70:
            verdict = "LIKELY PHISHING"
            emoji = "🔴"
        elif risk_score >= 40:
            verdict = "SUSPICIOUS"
            emoji = "🟡"
        elif risk_score >= 15:
            verdict = "MILD CONCERN"
            emoji = "🟠"
        else:
            verdict = "APPEARS LEGITIMATE"
            emoji = "🟢"

        result += f"\n  {emoji} Verdict: {verdict}\n"
        result += f"  Phishing Score: {risk_score}/100\n"

        if findings:
            result += "\n  Findings:\n"
            for f in findings:
                result += f"    ⚠ {f}\n"

        result += "\n  Tips:\n"
        result += "    • Never click links in suspicious emails\n"
        result += "    • Go directly to the website instead\n"
        result += "    • Check the sender's actual email address\n"

        return result

    # ══════════════════════════════════════════════════════════════
    # REAL-TIME NETWORK MONITOR
    # ══════════════════════════════════════════════════════════════

    def _toggle_netmon(self):
        if self._netmon_active:
            self._netmon_active = False
            self.jarvis.chat.add_message("system", "Network monitor: STOPPED")
            self._log_action("netmon", "Network monitor stopped")
        else:
            self._netmon_active = True
            self.jarvis.chat.add_message("system",
                "Network monitor: ACTIVE — watching for new connections...")
            self._log_action("netmon", "Network monitor started")
            self._netmon_thread = threading.Thread(
                target=self._netmon_loop, daemon=True
            )
            self._netmon_thread.start()

    def _netmon_loop(self):
        """Background loop that watches for new network connections."""
        # Get initial baseline
        self._known_connections = self._get_connections()

        while self._netmon_active:
            time.sleep(10)  # Check every 10 seconds
            try:
                current = self._get_connections()
                new_conns = current - self._known_connections

                if new_conns:
                    for conn in list(new_conns)[:5]:  # Limit alerts
                        proto, local, remote, state, proc = conn

                        # Check if remote IP is suspicious
                        alert_level = "info"
                        remote_ip = remote.split(":")[0] if ":" in remote else remote

                        # Known suspicious port ranges
                        try:
                            remote_port = int(remote.split(":")[-1]) if ":" in remote else 0
                        except ValueError:
                            remote_port = 0

                        if remote_port in (4444, 5555, 1337, 31337):
                            alert_level = "warning"
                        if proc and proc.lower() in ("cmd.exe", "powershell.exe"):
                            alert_level = "warning"

                        if alert_level == "warning":
                            msg = f"⚠ Suspicious connection: [{proc}] → {remote}"
                            self._log_action("netmon_alert", msg)
                        else:
                            msg = f"New connection: [{proc or '?'}] {proto} → {remote}"

                        self.jarvis.root.after(0, lambda m=msg, a=alert_level:
                            self.jarvis.chat.add_message(
                                "system" if a == "warning" else "system", f"🛡 {m}"
                            ))

                self._known_connections = current
            except Exception:
                pass

    def _get_connections(self) -> set:
        """Get current network connections as a set of tuples."""
        connections = set()
        try:
            output = subprocess.run(
                'netstat -b -n' if platform.system() == "Windows" else 'netstat -tunp',
                shell=True, capture_output=True, text=True, timeout=5,
            ).stdout

            current_proc = None
            for line in output.split("\n"):
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current_proc = line[1:-1]
                elif line.startswith("TCP") or line.startswith("UDP"):
                    parts = line.split()
                    if len(parts) >= 3:
                        proto = parts[0]
                        local = parts[1]
                        remote = parts[2]
                        state = parts[3] if len(parts) > 3 else ""
                        connections.add((proto, local, remote, state, current_proc or ""))
                        current_proc = None
        except Exception:
            pass
        return connections

    # ══════════════════════════════════════════════════════════════
    # SECURITY ACTION LOG
    # ══════════════════════════════════════════════════════════════

    def _log_action(self, action: str, detail: str):
        """Log a security action with timestamp."""
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "detail": detail,
        }
        self._security_log.append(entry)
        # Keep last 100 entries
        if len(self._security_log) > 100:
            self._security_log = self._security_log[-100:]

    def _show_security_log(self):
        if not self._security_log:
            self.jarvis.chat.add_message("system", "Security log is empty.")
            return

        result = "Security Action Log\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for entry in self._security_log[-15:]:  # Show last 15
            result += f"  [{entry['time']}] {entry['action']}: {entry['detail']}\n"
        result += f"\n  Total entries: {len(self._security_log)}"
        self.jarvis.chat.add_message("assistant", result)

    # ══════════════════════════════════════════════════════════════
    # NATURAL LANGUAGE DETECTION
    # ══════════════════════════════════════════════════════════════

    def on_message(self, message: str) -> str | None:
        msg = message.lower().strip()

        if re.search(r"scan\s+(?:the\s+)?ports?\s+(?:on\s+|of\s+)?(\S+)", msg):
            match = re.search(r"scan\s+(?:the\s+)?ports?\s+(?:on\s+|of\s+)?(\S+)", msg)
            self._show("Scanning ports...")
            self._log_action("portscan", match.group(1))
            _bg(self.port_scan, self.jarvis, match.group(1))
            return "__handled__"

        if re.search(r"check\s+(?:my\s+)?password\s+(?:strength|security)", msg):
            return None  # Let AI handle — don't extract password from message

        if re.search(r"(?:scan|show)\s+(?:the\s+)?(?:local\s+)?network", msg):
            self._show("Scanning network...")
            self._log_action("netscan", "Local network scan")
            _bg(self.net_scan, self.jarvis)
            return "__handled__"

        if re.search(r"(?:scan|show|list)\s+(?:the\s+)?wifi", msg):
            self._show("Scanning WiFi...")
            self._log_action("wifi_scan", "WiFi networks scan")
            _bg(self.wifi_scan, self.jarvis)
            return "__handled__"

        if re.search(r"(?:my|show|get)\s+(?:network|ip)\s+(?:info|details|config)", msg):
            self._show("Gathering network info...")
            _bg(self.my_network, self.jarvis)
            return "__handled__"

        # URL safety check
        if re.search(r"(?:is\s+(?:this\s+)?(?:link|url|site|website)\s+safe|scan\s+(?:this\s+)?(?:url|link))", msg):
            urls = re.findall(r"https?://\S+", message)
            if urls:
                self._show("Scanning URL...")
                self._log_action("url_scan", urls[0][:60])
                _bg(self.url_scan, self.jarvis, urls[0])
                return "__handled__"

        # Security audit
        if re.search(r"(?:am i|is my (?:computer|pc|system))\s+(?:secure|safe|protected)", msg):
            self._show("Running security audit...")
            self._log_action("audit", "Full system audit")
            _bg(self.security_audit, self.jarvis)
            return "__handled__"

        if re.search(r"security\s+(?:audit|check|scan|status)", msg):
            self._show("Running security audit...")
            self._log_action("audit", "Full system audit")
            _bg(self.security_audit, self.jarvis)
            return "__handled__"

        return None

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "active": True,
            "netmon_active": self._netmon_active,
            "log_entries": len(self._security_log),
        }
