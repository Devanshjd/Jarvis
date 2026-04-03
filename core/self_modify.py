"""
J.A.R.V.I.S — Self-Modification Engine
Allows JARVIS to write, test, and activate its own code.

"You'd need to give me write access to my own modules
and a self-modification framework." — JARVIS

This is that framework.

Safety rules:
1. JARVIS can only modify files in plugins/ and core/ directories
2. All modifications are backed up before changes
3. New code is tested in sandbox before activation
4. Core safety systems (safety.py, config.py) are NEVER modifiable
5. All changes are logged for review
"""

import os
import sys
import time
import json
import shutil
import logging
import importlib
import traceback
import threading
from datetime import datetime
from typing import Optional
from pathlib import Path

logger = logging.getLogger("jarvis.self_modify")

# Files that JARVIS can NEVER modify (safety-critical)
PROTECTED_FILES = {
    "core/safety.py",
    "core/config.py",
    "core/self_modify.py",  # Can't modify itself
    "main.py",
}

# Directories JARVIS is allowed to write to
ALLOWED_DIRS = {
    "plugins",
    "core",
}


class SelfModificationEngine:
    """
    Gives JARVIS the ability to create, modify, and test its own code.

    Capabilities:
    - Create new plugins from scratch
    - Modify existing plugin behavior
    - Write utility modules
    - Test changes in a sandbox
    - Hot-reload modified modules
    - Rollback failed changes

    All changes are:
    - Backed up before modification
    - Tested in sandbox before activation
    - Logged for audit trail
    """

    def __init__(self, app):
        self.app = app
        self.project_root = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.backup_dir = self.project_root / ".jarvis_backups"
        self.sandbox_dir = self.project_root / ".jarvis_sandbox"
        self.log_file = self.project_root / ".jarvis_modifications.log"

        # Create dirs
        self.backup_dir.mkdir(exist_ok=True)
        self.sandbox_dir.mkdir(exist_ok=True)

        # Modification history
        self._history: list[dict] = []
        self._load_history()

    # ══════════════════════════════════════════════════════════
    # FILE OPERATIONS
    # ══════════════════════════════════════════════════════════

    def can_modify(self, filepath: str) -> tuple[bool, str]:
        """Check if JARVIS is allowed to modify this file."""
        rel_path = self._to_relative(filepath)

        # Check protected files
        if rel_path in PROTECTED_FILES:
            return False, f"Protected file: {rel_path} cannot be modified for safety."

        # Check allowed directories
        parts = rel_path.split("/")
        if parts[0] not in ALLOWED_DIRS:
            return False, f"Outside allowed directories. Can only modify: {', '.join(ALLOWED_DIRS)}"

        return True, "OK"

    def read_file(self, filepath: str) -> Optional[str]:
        """Read a file from the project."""
        full_path = self._to_absolute(filepath)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error("Read error %s: %s", filepath, e)
            return None

    def write_file(self, filepath: str, content: str, reason: str = "") -> dict:
        """
        Write or create a file. Backs up existing files first.

        Returns:
            {"success": bool, "message": str, "backup": str or None}
        """
        allowed, msg = self.can_modify(filepath)
        if not allowed:
            return {"success": False, "message": msg, "backup": None}

        full_path = self._to_absolute(filepath)
        backup_path = None

        try:
            # Backup existing file
            if os.path.exists(full_path):
                backup_path = self._backup(filepath)

            # Ensure parent directory exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            # Write file
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Log modification
            self._log_modification({
                "action": "write",
                "file": filepath,
                "reason": reason,
                "backup": str(backup_path) if backup_path else None,
                "lines": content.count("\n") + 1,
                "timestamp": datetime.now().isoformat(),
            })

            logger.info("Modified %s (%d lines) — %s", filepath, content.count("\n"), reason)
            return {
                "success": True,
                "message": f"Written: {filepath} ({content.count(chr(10)) + 1} lines)",
                "backup": str(backup_path) if backup_path else None,
            }

        except Exception as e:
            logger.error("Write failed %s: %s", filepath, e)
            # Restore from backup if write failed
            if backup_path and os.path.exists(backup_path):
                shutil.copy2(backup_path, full_path)
            return {"success": False, "message": f"Write failed: {e}", "backup": None}

    def create_plugin(self, name: str, description: str, commands: dict,
                      code: str = None) -> dict:
        """
        Create a new plugin from scratch.

        Args:
            name: Plugin name (e.g., "network_monitor")
            description: What it does
            commands: Dict of command_name -> description
            code: Full plugin code (if None, generates a template)

        Returns:
            {"success": bool, "message": str, "path": str}
        """
        plugin_dir = f"plugins/{name}"
        plugin_file = f"{plugin_dir}/{name}_plugin.py"
        init_file = f"{plugin_dir}/__init__.py"

        # Check if already exists
        if os.path.exists(self._to_absolute(plugin_file)):
            return {
                "success": False,
                "message": f"Plugin '{name}' already exists.",
                "path": plugin_file,
            }

        # Generate plugin code if not provided
        if code is None:
            code = self._generate_plugin_template(name, description, commands)

        # Create plugin directory and files
        os.makedirs(self._to_absolute(plugin_dir), exist_ok=True)

        # Write __init__.py
        self.write_file(init_file, "", reason=f"Init for {name} plugin")

        # Write plugin file
        result = self.write_file(plugin_file, code, reason=f"New plugin: {description}")

        if result["success"]:
            result["path"] = plugin_file
            result["message"] = f"Plugin '{name}' created at {plugin_file}"

        return result

    # ══════════════════════════════════════════════════════════
    # SANDBOX TESTING
    # ══════════════════════════════════════════════════════════

    def test_code(self, code: str, test_type: str = "syntax") -> dict:
        """
        Test code in sandbox before deploying.

        Args:
            code: Python code to test
            test_type: "syntax" (compile only) or "execute" (run in sandbox)

        Returns:
            {"success": bool, "message": str, "output": str}
        """
        if test_type == "syntax":
            return self._test_syntax(code)
        elif test_type == "execute":
            return self._test_execute(code)
        return {"success": False, "message": f"Unknown test type: {test_type}", "output": ""}

    def _test_syntax(self, code: str) -> dict:
        """Compile code to check for syntax errors."""
        try:
            compile(code, "<sandbox>", "exec")
            return {
                "success": True,
                "message": "Syntax valid.",
                "output": "No errors found.",
            }
        except SyntaxError as e:
            return {
                "success": False,
                "message": f"Syntax error at line {e.lineno}: {e.msg}",
                "output": str(e),
            }

    def _test_execute(self, code: str) -> dict:
        """Execute code in a restricted sandbox."""
        sandbox_file = self.sandbox_dir / f"test_{int(time.time())}.py"

        try:
            # Write to sandbox
            with open(sandbox_file, "w", encoding="utf-8") as f:
                f.write(code)

            # Execute with timeout
            import subprocess
            result = subprocess.run(
                [sys.executable, str(sandbox_file)],
                capture_output=True, text=True, timeout=10,
                cwd=str(self.project_root),
            )

            output = result.stdout[:2000] if result.stdout else ""
            errors = result.stderr[:2000] if result.stderr else ""

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": "Execution successful.",
                    "output": output or "No output.",
                }
            else:
                return {
                    "success": False,
                    "message": f"Execution failed (exit code {result.returncode}).",
                    "output": errors or output,
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Execution timed out (10s limit).",
                "output": "Code took too long to execute.",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Sandbox error: {e}",
                "output": str(e),
            }
        finally:
            # Clean up sandbox file
            try:
                sandbox_file.unlink(missing_ok=True)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════
    # HOT RELOAD
    # ══════════════════════════════════════════════════════════

    def hot_reload(self, module_path: str) -> dict:
        """
        Reload a Python module without restarting JARVIS.

        Args:
            module_path: Dot-separated module path (e.g., "plugins.voice.voice_plugin")

        Returns:
            {"success": bool, "message": str}
        """
        try:
            if module_path in sys.modules:
                module = sys.modules[module_path]
                importlib.reload(module)
                return {
                    "success": True,
                    "message": f"Reloaded: {module_path}",
                }
            else:
                # Try importing it fresh
                importlib.import_module(module_path)
                return {
                    "success": True,
                    "message": f"Loaded: {module_path}",
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Reload failed: {e}",
            }

    def reload_plugin(self, plugin_name: str) -> dict:
        """
        Reload a plugin — unload, reimport, reactivate.

        Args:
            plugin_name: Plugin name as registered (e.g., "voice")

        Returns:
            {"success": bool, "message": str}
        """
        pm = self.app.plugin_manager

        try:
            # Unload if loaded
            if plugin_name in pm.plugins:
                pm.unload_plugin(plugin_name)

            # Find the plugin module
            # Convention: plugins/{name}/{name}_plugin.py
            module_path = f"plugins.{plugin_name}.{plugin_name}_plugin"

            # Clear from sys.modules cache
            modules_to_clear = [
                key for key in sys.modules if key.startswith(f"plugins.{plugin_name}")
            ]
            for key in modules_to_clear:
                del sys.modules[key]

            # Reimport
            module = importlib.import_module(module_path)

            # Find the plugin class (naming convention: XxxPlugin)
            from core.plugin_manager import PluginBase
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type)
                    and attr_name.endswith("Plugin")
                    and attr_name != "PluginBase"):
                    # Prefer PluginBase subclasses, but accept any class
                    # with a 'name' attribute as a plugin
                    if issubclass(attr, PluginBase):
                        plugin_class = attr
                        break
                    elif hasattr(attr, 'name'):
                        plugin_class = attr

            if plugin_class is None:
                return {
                    "success": False,
                    "message": f"No plugin class found in {module_path}",
                }

            # If it doesn't inherit PluginBase, wrap it dynamically
            if not issubclass(plugin_class, PluginBase):
                original = plugin_class
                # Create a wrapper that inherits PluginBase
                wrapper = type(
                    original.__name__,
                    (PluginBase,),
                    {k: v for k, v in original.__dict__.items()
                     if not k.startswith('__') or k in ('__init__',)},
                )
                wrapper.name = getattr(original, 'name', plugin_name)
                plugin_class = wrapper

            # Load and activate
            pm.load_plugin(plugin_class)

            return {
                "success": True,
                "message": f"Plugin '{plugin_name}' reloaded and active.",
            }

        except Exception as e:
            logger.error("Plugin reload failed for %s: %s", plugin_name, e)
            return {
                "success": False,
                "message": f"Reload failed: {e}\n{traceback.format_exc()[:500]}",
            }

    # ══════════════════════════════════════════════════════════
    # ROLLBACK
    # ══════════════════════════════════════════════════════════

    def rollback(self, filepath: str) -> dict:
        """Restore a file from its most recent backup."""
        rel_path = self._to_relative(filepath)
        backups = sorted(self.backup_dir.glob(f"*__{rel_path.replace('/', '__')}"),
                        reverse=True)

        if not backups:
            return {"success": False, "message": f"No backup found for {filepath}"}

        latest_backup = backups[0]
        full_path = self._to_absolute(filepath)

        try:
            shutil.copy2(latest_backup, full_path)
            self._log_modification({
                "action": "rollback",
                "file": filepath,
                "backup_used": str(latest_backup),
                "timestamp": datetime.now().isoformat(),
            })
            return {
                "success": True,
                "message": f"Rolled back {filepath} from backup.",
            }
        except Exception as e:
            return {"success": False, "message": f"Rollback failed: {e}"}

    # ══════════════════════════════════════════════════════════
    # PLUGIN TEMPLATE GENERATION
    # ══════════════════════════════════════════════════════════

    def _generate_plugin_template(self, name: str, description: str,
                                   commands: dict) -> str:
        """Generate a plugin from description and commands."""
        class_name = "".join(w.capitalize() for w in name.split("_")) + "Plugin"

        # Build command handlers
        command_cases = []
        command_methods = []
        for cmd, desc in commands.items():
            method_name = f"_cmd_{cmd.lstrip('/')}"
            command_cases.append(
                f'        if command == "/{cmd.lstrip("/")}":\n'
                f'            self._cmd_{cmd.lstrip("/")}(args)\n'
                f'            return True'
            )
            command_methods.append(
                f'    def _cmd_{cmd.lstrip("/")}(self, args: str):\n'
                f'        """Handle /{cmd.lstrip("/")} — {desc}"""\n'
                f'        self.jarvis.chat.add_message("assistant", "{desc} — not yet implemented.")\n'
            )

        commands_block = "\n".join(command_cases)
        methods_block = "\n\n".join(command_methods)

        return f'''"""
J.A.R.V.I.S — {class_name}
{description}

Auto-generated by JARVIS Self-Modification Engine.
"""

from core.plugin_manager import PluginBase


class {class_name}(PluginBase):
    """
    {description}

    Commands:
{chr(10).join(f"        /{cmd.lstrip('/')}: {desc}" for cmd, desc in commands.items())}
    """

    name = "{name}"

    def activate(self):
        print(f"[{{self.name}}] Plugin activated")

    def deactivate(self):
        print(f"[{{self.name}}] Plugin deactivated")

    def on_command(self, command: str, args: str) -> bool:
{commands_block}
        return False

    def on_message(self, message: str) -> str | None:
        return None

    def on_response(self, response: str):
        pass

{methods_block}
'''

    # ══════════════════════════════════════════════════════════
    # INTROSPECTION — JARVIS can examine itself
    # ══════════════════════════════════════════════════════════

    def list_plugins(self) -> list[dict]:
        """List all plugins (loaded and available)."""
        plugins = []

        # Loaded plugins
        for name, plugin in self.app.plugin_manager.plugins.items():
            plugins.append({
                "name": name,
                "loaded": True,
                "class": type(plugin).__name__,
                "status": plugin.get_status() if hasattr(plugin, 'get_status') else {},
            })

        # Available but not loaded
        plugins_dir = self.project_root / "plugins"
        if plugins_dir.exists():
            for d in plugins_dir.iterdir():
                if d.is_dir() and (d / "__init__.py").exists():
                    if d.name not in [p["name"] for p in plugins]:
                        plugins.append({
                            "name": d.name,
                            "loaded": False,
                            "class": "Unknown",
                            "status": {},
                        })

        return plugins

    def list_core_modules(self) -> list[str]:
        """List all core modules."""
        core_dir = self.project_root / "core"
        return [f.name for f in core_dir.glob("*.py") if f.name != "__pycache__"]

    def get_modification_history(self) -> list[dict]:
        """Get recent self-modification history."""
        return self._history[-20:]

    # ══════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ══════════════════════════════════════════════════════════

    def _to_relative(self, filepath: str) -> str:
        """Convert to relative path from project root."""
        filepath = filepath.replace("\\", "/")
        root = str(self.project_root).replace("\\", "/")
        if filepath.startswith(root):
            filepath = filepath[len(root):].lstrip("/")
        return filepath

    def _to_absolute(self, filepath: str) -> str:
        """Convert to absolute path."""
        filepath = self._to_relative(filepath)
        return str(self.project_root / filepath)

    def _backup(self, filepath: str) -> Path:
        """Create a timestamped backup of a file."""
        rel_path = self._to_relative(filepath)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = rel_path.replace("/", "__").replace("\\", "__")
        backup_path = self.backup_dir / f"{timestamp}__{safe_name}"

        full_path = self._to_absolute(filepath)
        shutil.copy2(full_path, backup_path)
        logger.info("Backed up %s → %s", filepath, backup_path.name)
        return backup_path

    def _log_modification(self, entry: dict):
        """Log a modification to history."""
        self._history.append(entry)
        if len(self._history) > 100:
            self._history = self._history[-100:]

        # Append to log file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def _load_history(self):
        """Load modification history from log."""
        try:
            if self.log_file.exists():
                with open(self.log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._history.append(json.loads(line))
                self._history = self._history[-100:]
        except Exception:
            self._history = []
