"""
J.A.R.V.I.S — Cybersecurity Plugin
Network analysis, security auditing, and threat intelligence.

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

All tools are for DEFENSIVE / EDUCATIONAL purposes only.
"""

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
    """Run a function in background thread, post result to chat."""
    def _run():
        try:
            result = func(*args)
            jarvis.root.after(0, lambda: jarvis.chat.add_message("assistant", result))
        except Exception as e:
            jarvis.root.after(0, lambda: jarvis.chat.add_message(
                "system", f"Security module error: {e}"))
    threading.Thread(target=_run, daemon=True).start()


class CyberPlugin(PluginBase):
    name = "cyber"
    description = "Cybersecurity — network scanning, password audit, threat intel"
    version = "1.0"

    def activate(self):
        pass

    def deactivate(self):
        pass

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
    # NATURAL LANGUAGE DETECTION
    # ══════════════════════════════════════════════════════════════

    def on_message(self, message: str) -> str | None:
        msg = message.lower().strip()

        if re.search(r"scan\s+(?:the\s+)?ports?\s+(?:on\s+|of\s+)?(\S+)", msg):
            match = re.search(r"scan\s+(?:the\s+)?ports?\s+(?:on\s+|of\s+)?(\S+)", msg)
            self._show("Scanning ports...")
            _bg(self.port_scan, self.jarvis, match.group(1))
            return "__handled__"

        if re.search(r"check\s+(?:my\s+)?password\s+(?:strength|security)", msg):
            return None  # Let AI handle — don't extract password from message

        if re.search(r"(?:scan|show)\s+(?:the\s+)?(?:local\s+)?network", msg):
            self._show("Scanning network...")
            _bg(self.net_scan, self.jarvis)
            return "__handled__"

        if re.search(r"(?:scan|show|list)\s+(?:the\s+)?wifi", msg):
            self._show("Scanning WiFi...")
            _bg(self.wifi_scan, self.jarvis)
            return "__handled__"

        if re.search(r"(?:my|show|get)\s+(?:network|ip)\s+(?:info|details|config)", msg):
            self._show("Gathering network info...")
            _bg(self.my_network, self.jarvis)
            return "__handled__"

        return None

    def get_status(self) -> dict:
        return {"name": self.name, "active": True}
