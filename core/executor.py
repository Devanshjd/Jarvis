"""
J.A.R.V.I.S — Agent Executor
Tool registry and execution bridge.

Maps tool names from AgentPlan to actual plugin/system actions.
Each tool function returns a ToolResult.
"""

import os
import subprocess
import platform
import threading
import webbrowser

from core.schemas import ToolResult


class Executor:
    """
    Executes tools by name. Holds a reference to the JarvisApp
    so it can access plugins, config, and UI.
    """

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self._tools = self._build_registry()

    def _build_registry(self) -> dict:
        """Map tool names to handler methods."""
        return {
            "open_app": self._open_app,
            "run_command": self._run_command,
            "web_search": self._web_search,
            "get_weather": self._web_intel("get_weather", "weather"),
            "get_news": self._web_intel("get_news", "news"),
            "get_crypto": self._web_intel("get_crypto", "crypto"),
            "get_wiki": self._web_intel("get_wiki", "wiki"),
            "get_definition": self._web_intel("get_definition", "define"),
            "get_translation": self._web_intel("get_translation", "translate"),
            "get_currency": self._web_intel("get_currency", "currency"),
            "get_quote": self._web_intel("get_quote", "quote"),
            "get_joke": self._web_intel("get_joke", "joke"),
            "get_fact": self._web_intel("get_fact", "fact"),
            "get_ip_info": self._web_intel("get_ip_info", "ip"),
            "get_nasa": self._web_intel("get_nasa", "nasa"),
            "scan_screen": self._scan_screen,
            "system_info": self._system_info,
            "type_text": self._type_text,
            "lock_screen": self._lock_screen,
            "set_volume": self._set_volume,
            "remember": self._remember,
            # Cybersecurity tools
            "url_scan": self._cyber_tool("url_scan"),
            "file_scan": self._cyber_tool("file_scan"),
            "security_audit": self._cyber_tool("security_audit"),
            "phishing_detect": self._cyber_tool("phishing_detect"),
            "port_scan": self._cyber_tool("port_scan"),
            "wifi_scan": self._cyber_tool("wifi_scan"),
            "net_scan": self._cyber_tool("net_scan"),
            "network_info": self._cyber_tool("network_info"),
            "threat_lookup": self._cyber_tool("threat_lookup"),
            # Scheduler tools
            "set_reminder": self._scheduler_tool("set_reminder"),
            "set_timer": self._scheduler_tool("set_timer"),
            "list_reminders": self._scheduler_tool("list_reminders"),
            # File manager tools
            "find_files": self._file_tool("find_files"),
            "organize_files": self._file_tool("organize_files"),
            "disk_usage": self._file_tool("disk_usage"),
            # Code tools
            "run_python": self._code_tool("run_python"),
            "save_file": self._save_file,
            "git_command": self._code_tool("git_command"),
            "pip_install": self._code_tool("pip_install"),
            # Email tools
            "check_inbox": self._email_tool("check_inbox"),
            "send_email": self._email_tool("send_email"),
            # Smart home tools
            "control_lights": self._smart_home_tool("control_lights"),
            "set_thermostat": self._smart_home_tool("set_thermostat"),
            "activate_scene": self._smart_home_tool("activate_scene"),
            "list_devices": self._smart_home_tool("list_devices"),
            # Self-modification tools
            "create_plugin": self._create_plugin,
            "modify_file": self._modify_file,
            "reload_plugin": self._reload_plugin,
            "list_plugins": self._list_plugins,
            "system_status": self._system_status,
            "rollback_file": self._rollback_file,
        }

    @property
    def available_tools(self) -> list[str]:
        return list(self._tools.keys())

    def execute(self, tool_name: str, tool_args: dict) -> ToolResult:
        """Execute a tool by name with given arguments."""
        handler = self._tools.get(tool_name)
        if not handler:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
            )
        try:
            return handler(tool_args)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    # ── Tool Handlers ─────────────────────────────────────────────

    def _open_app(self, args: dict) -> ToolResult:
        app_name = args.get("app", "").lower().strip()
        if not app_name:
            return ToolResult(success=False, error="No app name provided.")

        # Use the automation plugin's APP_MAP
        from plugins.automation.auto_plugin import APP_MAP
        exe = APP_MAP.get(app_name, app_name)

        try:
            if platform.system() == "Windows":
                subprocess.Popen(
                    f'start "" "{exe}"', shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    exe, shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return ToolResult(success=True, output=f"Launched {app_name}.")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to open {app_name}: {e}")

    def _run_command(self, args: dict) -> ToolResult:
        command = args.get("command", "")
        if not command:
            return ToolResult(success=False, error="No command provided.")

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=30,
            )
            output = result.stdout or result.stderr or "(no output)"
            if len(output) > 2000:
                output = output[:2000] + "\n... (truncated)"
            return ToolResult(success=True, output=output)
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="Command timed out (30s limit).")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def _web_search(self, args: dict) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(success=False, error="No search query.")
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        webbrowser.open(url)
        return ToolResult(success=True, output=f"Searching for: {query}")

    def _web_intel(self, method_name: str, _label: str):
        """Factory: returns a handler that delegates to the WebIntelPlugin."""
        def handler(args: dict) -> ToolResult:
            plugin = self.jarvis.plugin_manager.plugins.get("web_intel")
            if not plugin:
                return ToolResult(success=False, error="Web Intel plugin not loaded.")

            method = getattr(plugin, method_name, None)
            if not method:
                return ToolResult(success=False, error=f"Method {method_name} not found.")

            # Build the argument from tool_args
            if method_name == "get_weather":
                result = method(self.jarvis, args.get("city", ""))
            elif method_name == "get_news":
                result = method(self.jarvis, args.get("topic", ""))
            elif method_name == "get_crypto":
                result = method(self.jarvis, args.get("coin", ""))
            elif method_name == "get_wiki":
                result = method(self.jarvis, args.get("topic", ""))
            elif method_name == "get_definition":
                result = method(self.jarvis, args.get("word", ""))
            elif method_name == "get_translation":
                text = args.get("text", "")
                lp = args.get("langpair", "")
                if lp:
                    text = f"{lp} {text}"
                result = method(self.jarvis, text)
            elif method_name == "get_currency":
                amt = args.get("amount", 1)
                fr = args.get("from", "USD")
                to = args.get("to", "INR")
                result = method(self.jarvis, f"{amt} {fr} {to}")
            elif method_name == "get_ip_info":
                result = method(self.jarvis, args.get("ip", ""))
            elif method_name in ("get_quote", "get_joke", "get_fact", "get_nasa"):
                result = method(self.jarvis)
            else:
                result = method(self.jarvis, str(args))

            return ToolResult(success=True, output=result)
        return handler

    def _cyber_tool(self, method_name: str):
        """Factory: returns a handler that delegates to the CyberPlugin."""
        def handler(args: dict) -> ToolResult:
            plugin = self.jarvis.plugin_manager.plugins.get("cyber")
            if not plugin:
                return ToolResult(success=False, error="Cyber plugin not loaded.")

            method_map = {
                "url_scan": ("url_scan", lambda: plugin.url_scan(self.jarvis, args.get("url", ""))),
                "file_scan": ("file_scan", lambda: plugin.file_scan(self.jarvis, args.get("path", ""))),
                "security_audit": ("security_audit", lambda: plugin.security_audit(self.jarvis)),
                "phishing_detect": ("phishing_detect", lambda: plugin.phishing_detect(self.jarvis, args.get("text", ""))),
                "port_scan": ("port_scan", lambda: plugin.port_scan(self.jarvis, args.get("host", ""))),
                "wifi_scan": ("wifi_scan", lambda: plugin.wifi_scan(self.jarvis)),
                "net_scan": ("net_scan", lambda: plugin.net_scan(self.jarvis)),
                "network_info": ("network_info", lambda: plugin.my_network(self.jarvis)),
                "threat_lookup": ("threat_lookup", lambda: plugin.threat_lookup(self.jarvis, args.get("ip", ""))),
            }

            if method_name not in method_map:
                return ToolResult(success=False, error=f"Unknown cyber tool: {method_name}")

            _, call = method_map[method_name]
            result = call()
            return ToolResult(success=True, output=result)
        return handler

    # ── Plugin Tool Factories ────────────────────────────────────

    def _scheduler_tool(self, action: str):
        """Factory for scheduler plugin tools."""
        def handler(args: dict) -> ToolResult:
            plugin = self.jarvis.plugin_manager.plugins.get("scheduler")
            if not plugin:
                return ToolResult(success=False, error="Scheduler plugin not loaded.")
            if action == "set_reminder":
                time_str = args.get("time", "5m")
                message = args.get("message", "Reminder")
                plugin.on_command("/remind", f"{time_str} {message}")
                return ToolResult(success=True, output=f"Reminder set: {message} in {time_str}")
            elif action == "set_timer":
                duration = args.get("duration", "5m")
                plugin.on_command("/timer", duration)
                return ToolResult(success=True, output=f"Timer set for {duration}")
            elif action == "list_reminders":
                plugin.on_command("/reminders", "")
                return ToolResult(success=True, output="Reminders displayed.")
            return ToolResult(success=False, error=f"Unknown scheduler action: {action}")
        return handler

    def _file_tool(self, action: str):
        """Factory for file manager plugin tools."""
        def handler(args: dict) -> ToolResult:
            plugin = self.jarvis.plugin_manager.plugins.get("file_manager")
            if not plugin:
                return ToolResult(success=False, error="File Manager plugin not loaded.")
            if action == "find_files":
                pattern = args.get("pattern", "*")
                path = args.get("path", "")
                query = f"{pattern} {path}".strip() if path else pattern
                plugin.on_command("/find", query)
                return ToolResult(success=True, output=f"Searching for {pattern}...")
            elif action == "organize_files":
                folder = args.get("folder", "")
                plugin.on_command("/organize", folder)
                return ToolResult(success=True, output=f"Organizing {folder}...")
            elif action == "disk_usage":
                plugin.on_command("/diskusage", "")
                return ToolResult(success=True, output="Checking disk usage...")
            return ToolResult(success=False, error=f"Unknown file action: {action}")
        return handler

    def _code_tool(self, action: str):
        """Factory for code assistant plugin tools."""
        def handler(args: dict) -> ToolResult:
            plugin = self.jarvis.plugin_manager.plugins.get("code_assist")
            if not plugin:
                return ToolResult(success=False, error="Code Assist plugin not loaded.")
            if action == "run_python":
                code = args.get("code", "")
                plugin.on_command("/pyrun", code)
                return ToolResult(success=True, output="Executing Python code...")
            elif action == "git_command":
                subcmd = args.get("subcmd", "status")
                plugin.on_command("/git", subcmd)
                return ToolResult(success=True, output=f"Running git {subcmd}...")
            elif action == "pip_install":
                package = args.get("package", "")
                plugin.on_command("/pip", package)
                return ToolResult(success=True, output=f"Installing {package}...")
            return ToolResult(success=False, error=f"Unknown code action: {action}")
        return handler

    def _email_tool(self, action: str):
        """Factory for email plugin tools."""
        def handler(args: dict) -> ToolResult:
            plugin = self.jarvis.plugin_manager.plugins.get("email")
            if not plugin:
                return ToolResult(success=False, error="Email plugin not loaded.")
            if action == "check_inbox":
                count = args.get("count", 5)
                plugin.on_command("/inbox", str(count))
                return ToolResult(success=True, output="Checking inbox...")
            elif action == "send_email":
                to = args.get("to", "")
                subject = args.get("subject", "")
                body = args.get("body", "")
                plugin.on_command("/sendmail", f"{to} {subject} | {body}")
                return ToolResult(success=True, output=f"Sending email to {to}...")
            return ToolResult(success=False, error=f"Unknown email action: {action}")
        return handler

    def _smart_home_tool(self, action: str):
        """Factory for smart home plugin tools."""
        def handler(args: dict) -> ToolResult:
            plugin = self.jarvis.plugin_manager.plugins.get("smart_home")
            if not plugin:
                return ToolResult(success=False, error="Smart Home plugin not loaded.")
            if action == "control_lights":
                act = args.get("action", "on")
                level = args.get("level", "")
                cmd_args = f"{act} {level}".strip() if level else act
                plugin.on_command("/lights", cmd_args)
                return ToolResult(success=True, output=f"Lights {act}.")
            elif action == "set_thermostat":
                temp = args.get("temp", 72)
                plugin.on_command("/thermostat", str(temp))
                return ToolResult(success=True, output=f"Thermostat set to {temp}.")
            elif action == "activate_scene":
                scene = args.get("scene", "")
                plugin.on_command("/scene", scene)
                return ToolResult(success=True, output=f"Scene '{scene}' activated.")
            elif action == "list_devices":
                plugin.on_command("/devices", "")
                return ToolResult(success=True, output="Devices listed.")
            return ToolResult(success=False, error=f"Unknown smart home action: {action}")
        return handler

    def _save_file(self, args: dict) -> ToolResult:
        """Save content to a file on disk."""
        import os
        filename = args.get("filename", "jarvis_output.py")
        content = args.get("content", "")
        if not content:
            return ToolResult(success=False, error="No content to save.")

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isabs(filename):
            save_dir = desktop if os.path.exists(desktop) else os.path.expanduser("~")
            filepath = os.path.join(save_dir, filename)
        else:
            filepath = filename

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(
                success=True,
                output=f"File saved to: {filepath}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to save: {e}")

    def _scan_screen(self, args: dict) -> ToolResult:
        # Trigger scan through the app — it's async, so we just kick it off
        self.jarvis.scan_screen()
        return ToolResult(success=True, output="Screen scan initiated.")

    def _system_info(self, args: dict) -> ToolResult:
        auto = self.jarvis.plugin_manager.plugins.get("automation")
        if auto:
            auto._system_info()
            return ToolResult(success=True, output="System info displayed.")
        return ToolResult(success=False, error="Automation plugin not loaded.")

    def _type_text(self, args: dict) -> ToolResult:
        auto = self.jarvis.plugin_manager.plugins.get("automation")
        if auto:
            auto._type_text(args.get("text", ""))
            return ToolResult(success=True, output="Text typed.")
        return ToolResult(success=False, error="Automation plugin not loaded.")

    def _lock_screen(self, args: dict) -> ToolResult:
        auto = self.jarvis.plugin_manager.plugins.get("automation")
        if auto:
            auto._lock_screen()
            return ToolResult(success=True, output="Workstation locked.")
        return ToolResult(success=False, error="Automation plugin not loaded.")

    def _set_volume(self, args: dict) -> ToolResult:
        auto = self.jarvis.plugin_manager.plugins.get("automation")
        if auto:
            auto._set_volume(str(args.get("level", "")))
            return ToolResult(success=True, output="Volume adjusted.")
        return ToolResult(success=False, error="Automation plugin not loaded.")

    def _remember(self, args: dict) -> ToolResult:
        text = args.get("text", "")
        if not text:
            return ToolResult(success=False, error="Nothing to remember.")
        added = self.jarvis.memory.add(text)
        if added:
            return ToolResult(success=True, output=f"Committed to memory: \"{text}\"")
        return ToolResult(success=False, error="Already in memory or empty.")

    # ── Self-Modification Tools ──────────────────────────────

    def _create_plugin(self, args: dict) -> ToolResult:
        """Create a new JARVIS plugin."""
        sm = getattr(self.jarvis, "self_modify", None)
        if not sm:
            return ToolResult(success=False, error="Self-modification engine not available.")

        name = args.get("name", "")
        description = args.get("description", "")
        commands = args.get("commands", {})
        code = args.get("code")

        if not name:
            return ToolResult(success=False, error="Plugin name required.")

        result = sm.create_plugin(name, description, commands, code)

        if result["success"]:
            # Test syntax
            if code:
                test = sm.test_code(code, "syntax")
                if not test["success"]:
                    return ToolResult(
                        success=False,
                        error=f"Plugin created but has syntax errors: {test['message']}",
                    )

            # Try to load it
            reload = sm.reload_plugin(name)
            msg = result["message"]
            if reload["success"]:
                msg += f"\n{reload['message']}"
            else:
                msg += f"\nCreated but not loaded: {reload['message']}"

            return ToolResult(success=True, output=msg)

        return ToolResult(success=False, error=result["message"])

    def _modify_file(self, args: dict) -> ToolResult:
        """Modify a file in the JARVIS project."""
        sm = getattr(self.jarvis, "self_modify", None)
        if not sm:
            return ToolResult(success=False, error="Self-modification engine not available.")

        filepath = args.get("filepath", "")
        content = args.get("content", "")
        reason = args.get("reason", "Self-modification")

        if not filepath or not content:
            return ToolResult(success=False, error="filepath and content required.")

        # Test syntax first
        if filepath.endswith(".py"):
            test = sm.test_code(content, "syntax")
            if not test["success"]:
                return ToolResult(
                    success=False,
                    error=f"Code has syntax errors: {test['message']}",
                )

        result = sm.write_file(filepath, content, reason)
        if result["success"]:
            return ToolResult(success=True, output=result["message"])
        return ToolResult(success=False, error=result["message"])

    def _reload_plugin(self, args: dict) -> ToolResult:
        """Hot-reload a plugin."""
        sm = getattr(self.jarvis, "self_modify", None)
        if not sm:
            return ToolResult(success=False, error="Self-modification engine not available.")

        name = args.get("name", "")
        if not name:
            return ToolResult(success=False, error="Plugin name required.")

        result = sm.reload_plugin(name)
        if result["success"]:
            return ToolResult(success=True, output=result["message"])
        return ToolResult(success=False, error=result["message"])

    def _list_plugins(self, args: dict) -> ToolResult:
        """List all plugins and their status."""
        sm = getattr(self.jarvis, "self_modify", None)
        if not sm:
            return ToolResult(success=False, error="Self-modification engine not available.")

        plugins = sm.list_plugins()
        lines = ["JARVIS Plugins:"]
        for p in plugins:
            status = "ACTIVE" if p["loaded"] else "available"
            lines.append(f"  [{status}] {p['name']} ({p['class']})")

        history = sm.get_modification_history()
        if history:
            lines.append(f"\nRecent modifications: {len(history)}")
            for h in history[-3:]:
                lines.append(f"  {h.get('action', '?')}: {h.get('file', '?')} — {h.get('reason', '')}")

        return ToolResult(success=True, output="\n".join(lines))

    def _system_status(self, args: dict) -> ToolResult:
        """Full system status using awareness engine."""
        awareness = getattr(self.jarvis, "awareness", None)
        if not awareness:
            return ToolResult(success=False, error="Awareness engine not available.")

        status = awareness.get_system_status()
        return ToolResult(success=True, output=status)

    def _rollback_file(self, args: dict) -> ToolResult:
        """Rollback a file to its last backup."""
        sm = getattr(self.jarvis, "self_modify", None)
        if not sm:
            return ToolResult(success=False, error="Self-modification engine not available.")

        filepath = args.get("filepath", "")
        if not filepath:
            return ToolResult(success=False, error="filepath required.")

        result = sm.rollback(filepath)
        if result["success"]:
            return ToolResult(success=True, output=result["message"])
        return ToolResult(success=False, error=result["message"])
