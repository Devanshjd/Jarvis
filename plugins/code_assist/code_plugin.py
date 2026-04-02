"""
J.A.R.V.I.S — Code Assistant Plugin
Code execution, explanation, snippet management, and dev tools.

Commands:
    /runcode <language>    — Run code block from chat (python, js, shell)
    /explain <file>        — Explain what a code file does (via AI)
    /snippet <name> <code> — Save a code snippet
    /snippets              — List all saved snippets
    /pyrun <code>          — Quick Python one-liner execution
    /git [cmd]             — Git shortcuts (status, log, diff, branch)
    /pip <package>         — Install a pip package
    /env                   — Show Python environment info
"""

import os
import re
import sys
import json
import threading
import subprocess
import platform
from datetime import datetime

from core.plugin_manager import PluginBase
from core.config import save_config

MAX_OUTPUT = 3000


def _truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    """Truncate output to a reasonable length."""
    if len(text) > limit:
        return text[:limit] + f"\n... (truncated, {len(text)} chars total)"
    return text


def _bg(func, jarvis, *args):
    """Run a function in a background thread, post result to chat."""
    def _run():
        try:
            result = func(jarvis, *args)
            jarvis.root.after(0, lambda: jarvis.chat.add_message("assistant", result))
        except Exception as e:
            jarvis.root.after(0, lambda: jarvis.chat.add_message(
                "system", f"Code assistant error: {e}"))
    threading.Thread(target=_run, daemon=True).start()


class CodeAssistPlugin(PluginBase):
    name = "code_assist"
    description = "Code assistant — run code, explain files, snippets, git, pip"
    version = "1.0"

    LANG_COMMANDS = {
        "python": [sys.executable, "-c"],
        "py": [sys.executable, "-c"],
        "javascript": ["node", "-e"],
        "js": ["node", "-e"],
        "shell": ["bash", "-c"] if platform.system() != "Windows" else ["cmd", "/c"],
        "sh": ["bash", "-c"] if platform.system() != "Windows" else ["cmd", "/c"],
        "bat": ["cmd", "/c"],
    }

    def __init__(self, jarvis):
        super().__init__(jarvis)
        self._pending_code = None  # (language, code) awaiting confirmation

    def activate(self):
        pass

    def deactivate(self):
        pass

    # ══════════════════════════════════════════════════════════════
    #  Helpers
    # ══════════════════════════════════════════════════════════════

    def _show(self, msg: str):
        self.jarvis.chat.add_message("system", msg)

    def _get_snippets(self) -> dict:
        return self.jarvis.config.get("code_snippets", {})

    def _save_snippets(self, snippets: dict):
        self.jarvis.config["code_snippets"] = snippets
        save_config(self.jarvis.config)

    # ══════════════════════════════════════════════════════════════
    #  Command Router
    # ══════════════════════════════════════════════════════════════

    def on_command(self, command: str, args: str) -> bool:
        cmd = command.lower()

        if cmd == "/pyrun":
            if not args.strip():
                self._show("Usage: /pyrun <python code>\nExample: /pyrun print(2**10)")
                return True
            self._show(f"Running: {args.strip()}")
            _bg(self._exec_pyrun, self.jarvis, args.strip())
            return True

        if cmd == "/runcode":
            parts = args.strip().split(None, 1)
            if len(parts) < 2:
                self._show(
                    "Usage: /runcode <language> <code>\n"
                    "Supported: python, js, shell\n"
                    "Example: /runcode python print('hello')"
                )
                return True
            lang, code = parts[0].lower(), parts[1]
            if lang not in self.LANG_COMMANDS:
                self._show(f"Unsupported language: {lang}\nSupported: {', '.join(self.LANG_COMMANDS.keys())}")
                return True
            # Safety: show code and ask for confirmation
            self._pending_code = (lang, code)
            self._show(
                f"About to execute {lang} code:\n\n"
                f"```\n{code}\n```\n\n"
                "Type 'yes' or 'confirm' to run, or anything else to cancel."
            )
            return True

        if cmd == "/explain":
            filepath = args.strip()
            if not filepath:
                self._show("Usage: /explain <filepath>\nExample: /explain main.py")
                return True
            self._show(f"Reading and analyzing: {filepath}")
            _bg(self._explain_file, self.jarvis, filepath)
            return True

        if cmd == "/snippet":
            parts = args.strip().split(None, 1)
            if len(parts) < 2:
                self._show("Usage: /snippet <name> <code>\nExample: /snippet fizzbuzz for i in range(1,101): print('FizzBuzz'...)")
                return True
            name, code = parts[0], parts[1]
            snippets = self._get_snippets()
            snippets[name] = {
                "code": code,
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            self._save_snippets(snippets)
            self._show(f"Snippet '{name}' saved successfully.")
            return True

        if cmd == "/snippets":
            snippets = self._get_snippets()
            if not snippets:
                self._show("No saved snippets. Use /snippet <name> <code> to save one.")
                return True
            lines = ["Saved Code Snippets", "=" * 40]
            for name, data in snippets.items():
                code_preview = data["code"][:80] + ("..." if len(data["code"]) > 80 else "")
                saved = data.get("saved_at", "unknown")
                lines.append(f"\n  {name}  (saved {saved})")
                lines.append(f"    {code_preview}")
            self._show("\n".join(lines))
            return True

        if cmd == "/git":
            git_cmd = args.strip().lower() if args.strip() else "status"
            allowed = {"status", "log", "diff", "branch"}
            if git_cmd not in allowed:
                self._show(f"Usage: /git [status|log|diff|branch]\nGot: {git_cmd}")
                return True
            self._show(f"Running git {git_cmd}...")
            _bg(self._run_git, self.jarvis, git_cmd)
            return True

        if cmd == "/pip":
            package = args.strip()
            if not package:
                self._show("Usage: /pip <package>\nExample: /pip requests")
                return True
            self._show(f"Installing {package}...")
            _bg(self._run_pip, self.jarvis, package)
            return True

        if cmd == "/env":
            self._show("Gathering environment info...")
            _bg(self._show_env, self.jarvis)
            return True

        return False

    # ══════════════════════════════════════════════════════════════
    #  Natural Language
    # ══════════════════════════════════════════════════════════════

    def on_message(self, message: str) -> str | None:
        msg = message.lower().strip()

        # Check for /runcode confirmation
        if self._pending_code and msg in ("yes", "confirm", "y", "run"):
            lang, code = self._pending_code
            self._pending_code = None
            self._show(f"Executing {lang} code...")
            _bg(self._exec_code, self.jarvis, lang, code)
            return "__handled__"

        if self._pending_code and msg in ("no", "cancel", "n"):
            self._pending_code = None
            self._show("Code execution cancelled.")
            return "__handled__"

        # Clear pending if user says something else
        if self._pending_code:
            self._pending_code = None

        # "run this python code: ..."
        match = re.match(
            r"run\s+(?:this\s+)?(?:python|py)\s+code[:\s]+(.+)",
            msg, re.DOTALL
        )
        if match:
            code = match.group(1).strip()
            self._pending_code = ("python", code)
            self._show(
                f"About to execute Python code:\n\n"
                f"```\n{code}\n```\n\n"
                "Type 'yes' or 'confirm' to run, or anything else to cancel."
            )
            return "__handled__"

        # "what does this code do: ..."
        match = re.match(
            r"what\s+does\s+this\s+code\s+do[:\s]+(.+)",
            msg, re.DOTALL
        )
        if match:
            code = match.group(1).strip()
            self._show("Analyzing code...")
            _bg(self._explain_code_snippet, self.jarvis, code)
            return "__handled__"

        # "install <package>"
        match = re.match(r"install\s+(\S+)", msg)
        if match:
            package = match.group(1)
            # Only handle if it looks like a Python package name
            if re.match(r'^[a-zA-Z0-9_\-\.]+$', package):
                self._show(f"Installing {package}...")
                _bg(self._run_pip, self.jarvis, package)
                return "__handled__"

        # "git status" / "git log" / etc.
        match = re.match(r"git\s+(status|log|diff|branch)", msg)
        if match:
            git_cmd = match.group(1)
            self._show(f"Running git {git_cmd}...")
            _bg(self._run_git, self.jarvis, git_cmd)
            return "__handled__"

        # "show my python version" / "python version"
        if re.search(r"(?:show\s+(?:my\s+)?)?python\s+version", msg):
            self._show("Gathering environment info...")
            _bg(self._show_env, self.jarvis)
            return "__handled__"

        return None

    # ══════════════════════════════════════════════════════════════
    #  Execution Functions (run in background threads)
    # ══════════════════════════════════════════════════════════════

    def _exec_pyrun(self, jarvis, code: str) -> str:
        """Quick Python one-liner execution."""
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=15,
                cwd=os.path.expanduser("~"),
            )
            output = result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if not output.strip():
                output = "(no output)"
            return f"Python Output:\n```\n{_truncate(output.strip())}\n```"
        except subprocess.TimeoutExpired:
            return "Execution timed out (15s limit)."
        except Exception as e:
            return f"Execution error: {e}"

    def _exec_code(self, jarvis, lang: str, code: str) -> str:
        """Execute code in the specified language."""
        cmd_parts = self.LANG_COMMANDS.get(lang)
        if not cmd_parts:
            return f"Unsupported language: {lang}"

        try:
            result = subprocess.run(
                cmd_parts + [code],
                capture_output=True, text=True, timeout=15,
                cwd=os.path.expanduser("~"),
            )
            output = result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if not output.strip():
                output = "(no output)"
            return f"{lang.capitalize()} Output:\n```\n{_truncate(output.strip())}\n```"
        except subprocess.TimeoutExpired:
            return "Execution timed out (15s limit)."
        except FileNotFoundError:
            return f"Runtime not found for '{lang}'. Make sure it's installed and on PATH."
        except Exception as e:
            return f"Execution error: {e}"

    def _explain_file(self, jarvis, filepath: str) -> str:
        """Read a file and send it to the AI for explanation."""
        # Resolve relative paths
        if not os.path.isabs(filepath):
            filepath = os.path.join(os.getcwd(), filepath)

        if not os.path.exists(filepath):
            return f"File not found: {filepath}"

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return f"Error reading file: {e}"

        if not content.strip():
            return "File is empty."

        content = _truncate(content, 5000)
        filename = os.path.basename(filepath)

        # Send to AI brain for explanation
        prompt = (
            f"Explain what the following code file ({filename}) does. "
            "Give a clear, concise summary of its purpose, key functions/classes, "
            "and how it works.\n\n"
            f"```\n{content}\n```"
        )
        jarvis.brain.add_user_message(prompt)
        reply, latency = jarvis.brain.provider.chat(
            messages=jarvis.brain.history,
            system_prompt="You are JARVIS, a code analysis assistant. Explain code clearly and concisely.",
            max_tokens=jarvis.config.get("max_tokens", 2048),
        )
        jarvis.brain.add_assistant_message(reply)
        return f"Analysis of {filename}:\n\n{reply}"

    def _explain_code_snippet(self, jarvis, code: str) -> str:
        """Send a code snippet to AI for explanation."""
        prompt = (
            "Explain what the following code does. "
            "Give a clear, concise summary.\n\n"
            f"```\n{code}\n```"
        )
        jarvis.brain.add_user_message(prompt)
        reply, latency = jarvis.brain.provider.chat(
            messages=jarvis.brain.history,
            system_prompt="You are JARVIS, a code analysis assistant. Explain code clearly and concisely.",
            max_tokens=jarvis.config.get("max_tokens", 2048),
        )
        jarvis.brain.add_assistant_message(reply)
        return f"Code Explanation:\n\n{reply}"

    def _run_git(self, jarvis, git_cmd: str) -> str:
        """Run a git command and return formatted output."""
        cmd_map = {
            "status": ["git", "status", "--short"],
            "log": ["git", "log", "--oneline", "-15"],
            "diff": ["git", "diff", "--stat"],
            "branch": ["git", "branch", "-a"],
        }

        cmd = cmd_map.get(git_cmd, ["git", git_cmd])
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
                cwd=os.getcwd(),
            )
            output = result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if not output.strip():
                output = "(no output — working tree clean)" if git_cmd == "status" else "(no output)"

            header = f"Git {git_cmd.capitalize()}"
            return f"{header}\n{'=' * len(header)}\n```\n{_truncate(output.strip())}\n```"
        except FileNotFoundError:
            return "Git is not installed or not on PATH."
        except subprocess.TimeoutExpired:
            return "Git command timed out (15s limit)."
        except Exception as e:
            return f"Git error: {e}"

    def _run_pip(self, jarvis, package: str) -> str:
        """Install a pip package."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if result.returncode == 0:
                return f"Successfully installed {package}.\n```\n{_truncate(output.strip())}\n```"
            else:
                return f"Failed to install {package}.\n```\n{_truncate(output.strip())}\n```"
        except subprocess.TimeoutExpired:
            return f"Installation of {package} timed out (120s limit)."
        except Exception as e:
            return f"Pip error: {e}"

    def _show_env(self, jarvis) -> str:
        """Show Python environment information."""
        lines = [
            "Python Environment",
            "=" * 40,
            f"  Python version:  {sys.version}",
            f"  Executable:      {sys.executable}",
            f"  Platform:        {platform.platform()}",
            f"  Architecture:    {platform.machine()}",
        ]

        # Virtual environment
        venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_DEFAULT_ENV")
        if venv:
            lines.append(f"  Virtual env:     {venv}")
        else:
            lines.append("  Virtual env:     None detected")

        # Pip version
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            pip_ver = result.stdout.strip().split("\n")[0] if result.stdout else "unknown"
            lines.append(f"  Pip:             {pip_ver}")
        except Exception:
            lines.append("  Pip:             not available")

        # Installed packages count
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                lines.append(f"  Installed pkgs:  {len(packages)}")
        except Exception:
            pass

        # Working directory
        lines.append(f"  Working dir:     {os.getcwd()}")

        return "\n".join(lines)

    # ══════════════════════════════════════════════════════════════
    #  Status
    # ══════════════════════════════════════════════════════════════

    def get_status(self) -> dict:
        snippets = self._get_snippets()
        return {
            "name": self.name,
            "active": True,
            "snippets": len(snippets),
        }
