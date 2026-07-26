"""
J.A.R.V.I.S — Command Guard (defense-in-depth for shell execution)

JARVIS can run shell commands via tools, and it also ingests UNTRUSTED content
(web research, screen OCR, clipboard, files). That combination means a
prompt-injection payload could try to trigger a destructive command. This guard
blocks the catastrophic ones and the classic "pipe remote code into a shell"
pattern — regardless of where the command came from.

It is NOT a sandbox and not a complete allowlist; it is a last-line blocklist
for irreversible / system-destroying / remote-code-exec commands. Legitimate
day-to-day commands pass through untouched.

    from core.command_guard import check_command
    ok, reason = check_command(cmd)
    if not ok: refuse(reason)
"""
from __future__ import annotations

import re

# Catastrophic / irreversible / remote-code-exec patterns (case-insensitive).
# Each entry: (compiled regex, human reason).
_RULES: list[tuple[re.Pattern, str]] = [
    # ── Remote code execution: fetch-and-pipe-to-shell (the #1 injection vector)
    (re.compile(r"\b(curl|wget|iwr|invoke-webrequest|invoke-restmethod)\b.*\|\s*(sh|bash|zsh|python|powershell|pwsh|iex|cmd)", re.I),
     "downloads and executes remote code (fetch | shell)"),
    (re.compile(r"\biex\b.*\b(downloadstring|invoke-webrequest|iwr)\b", re.I),
     "executes remote code via IEX (DownloadString)"),
    # ── Recursive/forced deletion of a root or home
    (re.compile(r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME|/\*|\.\s*$)", re.I),
     "recursive force-delete of root/home"),
    (re.compile(r"\bdel\b.*/[sq].*(\\|[A-Za-z]:\\|\*)", re.I),
     "recursive/forced delete on Windows"),
    (re.compile(r"\b(rd|rmdir)\b.*/s", re.I), "recursive directory removal (Windows)"),
    (re.compile(r"\bRemove-Item\b.*-Recurse.*-Force", re.I),
     "recursive force-delete (PowerShell)"),
    # ── Disk / filesystem destruction
    (re.compile(r"\bmkfs\b", re.I), "formats a filesystem"),
    (re.compile(r"\bformat\b\s+[a-z]:", re.I), "formats a drive"),
    (re.compile(r"\bdd\b.*\bof=/dev/", re.I), "raw-writes to a block device"),
    (re.compile(r">\s*/dev/(sd|hd|nvme|disk)", re.I), "overwrites a raw disk"),
    (re.compile(r"\bdiskpart\b|\bcipher\s+/w|\bvssadmin\b.*delete", re.I),
     "disk/shadow-copy destruction"),
    # ── Fork bomb
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"), "fork bomb"),
    # ── Ownership / perms wipe on root
    (re.compile(r"\bchmod\b.*-R.*\s/(?:\s|$)|\bchown\b.*-R.*\s/(?:\s|$)", re.I),
     "recursive perms/ownership change on root"),
    # ── Power / boot / registry sabotage
    (re.compile(r"\b(shutdown|reboot|halt|poweroff)\b", re.I), "shuts down / reboots the machine"),
    (re.compile(r"\bbcdedit\b|\breg\s+delete\b\s+HK", re.I), "boot/registry tampering"),
]


def check_command(command: str) -> tuple[bool, str]:
    """Return (allowed, reason). allowed=False means BLOCK the command."""
    if not command or not command.strip():
        return True, ""
    cmd = command.strip()
    for pat, reason in _RULES:
        if pat.search(cmd):
            return False, reason
    return True, ""


def is_safe_app_name(name: str) -> bool:
    """App names must not contain shell metacharacters (they're interpolated
    into a `start "" "<name>"` shell command)."""
    return not re.search(r'[;&|`$"\'\n\r<>]', name or "")
