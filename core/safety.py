"""
J.A.R.V.I.S — Safety Layer
Detects dangerous commands and enforces confirmation before execution.
"""

import re


# Commands that require user confirmation before running
DANGEROUS_PATTERNS = [
    # File system destruction
    r"rm\s+-rf",
    r"rmdir\s+/s",
    r"del\s+/[sfq]",
    r"format\s+[a-zA-Z]:",
    # System-level
    r"shutdown",
    r"restart",
    r"taskkill",
    r"reg\s+delete",
    r"regedit",
    # Network
    r"netsh\s+.*reset",
    r"ipconfig\s+/release",
    # Disk
    r"diskpart",
    r"cipher\s+/w",
    # PowerShell danger
    r"Remove-Item\s+.*-Recurse",
    r"Stop-Process",
    r"Set-ExecutionPolicy",
]

# Tools that always need confirmation
CONFIRM_TOOLS = {
    "run_command",
    "delete_file",
    "lock_screen",
    "shutdown",
    "restart",
}

# Tools that are always safe
SAFE_TOOLS = {
    "open_app",
    "web_search",
    "get_weather",
    "get_news",
    "get_crypto",
    "get_wiki",
    "get_definition",
    "get_translation",
    "get_quote",
    "get_joke",
    "get_fact",
    "get_ip_info",
    "get_nasa",
    "system_info",
    "scan_screen",
    "type_text",
    "set_volume",
}


def is_dangerous_command(command: str) -> bool:
    """Check if a shell command matches known dangerous patterns."""
    cmd_lower = command.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower, re.IGNORECASE):
            return True
    return False


def needs_confirmation(tool_name: str, tool_args: dict) -> bool:
    """Decide if a tool invocation needs user confirmation."""
    if tool_name in SAFE_TOOLS:
        return False
    if tool_name in CONFIRM_TOOLS:
        return True
    # Extra check: if run_command contains dangerous content
    if tool_name == "run_command":
        cmd = tool_args.get("command", "")
        return is_dangerous_command(cmd)
    return False


def describe_risk(tool_name: str, tool_args: dict) -> str:
    """Generate a human-readable risk description for confirmation dialogs."""
    if tool_name == "run_command":
        cmd = tool_args.get("command", "")
        if is_dangerous_command(cmd):
            return f"⚠ This command could be destructive:\n  {cmd}\n\nAllow execution?"
        return f"Run system command:\n  {cmd}\n\nProceed?"

    if tool_name == "delete_file":
        return f"Delete file: {tool_args.get('path', '?')}\n\nThis cannot be undone. Proceed?"

    if tool_name in ("shutdown", "restart"):
        return f"This will {tool_name} your computer. Proceed?"

    if tool_name == "lock_screen":
        return "Lock your workstation?"

    return f"Execute action: {tool_name}?\nArgs: {tool_args}"
