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
            if exe.startswith("ms-"):
                os.startfile(exe)
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
