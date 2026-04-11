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
import logging

from core.schemas import ToolResult
from core.subprocess_utils import run_text


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
            # Pentest / Bug bounty tools
            "recon": self._pentest_tool("full_recon"),
            "subdomain_enum": self._pentest_tool("subdomain_enum"),
            "tech_detect": self._pentest_tool("tech_detect"),
            "dir_fuzz": self._pentest_tool("dir_fuzz"),
            "google_dorks": self._pentest_tool("google_dorks"),
            "ssl_check": self._pentest_tool("ssl_check"),
            "cors_check": self._pentest_tool("cors_check"),
            "xss_test": self._pentest_tool("xss_test"),
            "sqli_test": self._pentest_tool("sqli_test"),
            "open_redirect": self._pentest_tool("open_redirect_test"),
            "header_audit": self._pentest_tool("deep_header_audit"),
            "wayback": self._pentest_tool("wayback_urls"),
            "cve_search": self._pentest_tool("cve_search"),
            "exploit_search": self._pentest_tool("exploit_search"),
            # Chain execution tools
            "pentest_chain": self._chain_tool("full_pentest_chain"),
            "quick_recon_chain": self._chain_tool("quick_recon_chain"),
            # Web research tools
            "web_research": self._research_tool("research"),
            "research_cve": self._research_tool("research_cve"),
            "research_target": self._research_tool("research_target"),
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
            # Web automation tools
            "web_login": self._web_login,
            "web_navigate": self._web_navigate,
            "web_click": self._web_click,
            # AI screen interaction (vision-based)
            "screen_find": self._screen_interact_tool("find"),
            "screen_click": self._screen_interact_tool("click"),
            "screen_type": self._screen_interact_tool("type_into"),
            "screen_read": self._screen_interact_tool("read"),
            # Dev agent
            "build_project": self._dev_agent_tool(),
            # Messaging
            "send_msg": self._messaging_tool(),
            # Mouse & keyboard control (requires permission)
            "mouse_click": self._input_control("mouse_click"),
            "mouse_move": self._input_control("mouse_move"),
            "mouse_scroll": self._input_control("mouse_scroll"),
            "key_press": self._input_control("key_press"),
            "key_combo": self._input_control("key_combo"),
            "type_text": self._input_control("type_text"),
            "take_screenshot": self._input_control("screenshot"),
        }

    @property
    def available_tools(self) -> list[str]:
        return list(self._tools.keys())

    def execute(self, tool_name: str, tool_args: dict) -> ToolResult:
        """Execute a tool by name with given arguments.

        If the tool fails and a ResilientExecutor is available,
        retries with escalating fix strategies before giving up.
        """
        handler = self._tools.get(tool_name)
        if not handler:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
            )
        try:
            result = handler(tool_args)

            # If tool failed, decide: retry or ask for clarification
            if not result.success and result.error:
                # Don't retry INPUT errors — these need user clarification, not retries
                input_errors = [
                    "no message", "no contact", "no app name", "no search query",
                    "no command", "not specified", "not provided", "no file",
                    "no url", "no domain", "no host", "no target", "no query",
                    "user declined", "user denied", "cancelled",
                ]
                is_input_error = any(phrase in result.error.lower() for phrase in input_errors)

                if is_input_error:
                    # Return a helpful message instead of retrying
                    return ToolResult(
                        success=False,
                        error=result.error,  # clean error, no "Failed after X attempts"
                    )

                # Genuine execution error — try resilient retry
                resilient = getattr(self.jarvis, "resilient", None)
                if resilient:
                    import logging
                    logging.getLogger("jarvis.executor").info(
                        "Tool %s failed, engaging resilient executor: %s",
                        tool_name, result.error[:100],
                    )
                    retry = resilient.execute_tool(
                        handler, tool_args, tool_name=tool_name,
                    )
                    if retry.get("success"):
                        retry_result = retry.get("result")
                        if isinstance(retry_result, ToolResult):
                            return retry_result
                        return ToolResult(
                            success=True,
                            output=str(retry_result) if retry_result else "Done (after retry).",
                        )
                    # Resilient also failed — return the last error
                    return ToolResult(
                        success=False,
                        error=f"Failed after {retry.get('attempts', '?')} attempts: {retry.get('error', result.error)}",
                        data=self._auto_repair_data(tool_name, tool_args, retry.get('error', result.error)),
                    )

            if not result.success and result.error:
                result.data = {
                    **(result.data or {}),
                    **self._auto_repair_data(tool_name, tool_args, result.error),
                }
            return result

        except Exception as e:
            # Exception path — also try resilient retry
            resilient = getattr(self.jarvis, "resilient", None)
            if resilient:
                retry = resilient.execute_tool(
                    handler, tool_args, tool_name=tool_name,
                )
                if retry.get("success"):
                    retry_result = retry.get("result")
                    if isinstance(retry_result, ToolResult):
                        return retry_result
                    return ToolResult(
                        success=True,
                        output=str(retry_result) if retry_result else "Done (after retry).",
                    )
            return ToolResult(
                success=False,
                error=str(e),
                data=self._auto_repair_data(tool_name, tool_args, str(e)),
            )

    def _auto_repair_data(self, tool_name: str, tool_args: dict, error: str) -> dict:
        """Queue a conservative self-repair attempt when a mapped tool keeps failing."""
        engine = getattr(self.jarvis, "auto_repair", None)
        if not engine or not error:
            return {}
        try:
            info = engine.note_tool_failure(tool_name, tool_args, error)
            return {"auto_repair": info} if info else {}
        except Exception as exc:
            logging.getLogger("jarvis.executor").warning(
                "Auto-repair scheduling failed for %s: %s", tool_name, exc,
            )
            return {}

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
                # URI schemes (steam://, whatsapp:, ms-settings:) need webbrowser or os.startfile
                if "://" in exe or (exe.endswith(":") and len(exe) > 2):
                    os.startfile(exe)
                else:
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
            # Fallback: try Windows start menu search via pyautogui
            try:
                import pyautogui
                pyautogui.hotkey("win")
                import time
                time.sleep(0.5)
                pyautogui.write(app_name, interval=0.03)
                time.sleep(1)
                pyautogui.press("enter")
                time.sleep(1)
                return ToolResult(success=True, output=f"Launched {app_name} via Start menu.")
            except Exception:
                return ToolResult(success=False, error=f"Failed to open {app_name}: {e}")

    def _run_command(self, args: dict) -> ToolResult:
        command = args.get("command", "")
        if not command:
            return ToolResult(success=False, error="No command provided.")

        try:
            result = run_text(
                command, shell=True, capture_output=True,
                timeout=30,
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
        platform_name = args.get("platform", "").lower()
        if not query:
            return ToolResult(success=False, error="No search query.")

        # Route to the right platform
        platform_urls = {
            "youtube": "https://www.youtube.com/results?search_query={}",
            "google": "https://www.google.com/search?q={}",
            "github": "https://github.com/search?q={}",
            "stackoverflow": "https://stackoverflow.com/search?q={}",
            "stack overflow": "https://stackoverflow.com/search?q={}",
            "reddit": "https://www.reddit.com/search/?q={}",
            "amazon": "https://www.amazon.com/s?k={}",
            "wikipedia": "https://en.wikipedia.org/wiki/Special:Search/{}",
            "twitter": "https://twitter.com/search?q={}",
            "x": "https://twitter.com/search?q={}",
            "linkedin": "https://www.linkedin.com/search/results/all/?keywords={}",
            "spotify": "https://open.spotify.com/search/{}",
        }

        url_template = platform_urls.get(platform_name, platform_urls["google"])
        url = url_template.format(query.replace(' ', '+'))
        webbrowser.open(url)

        if platform_name:
            return ToolResult(success=True, output=f"Searching '{query}' on {platform_name}.")
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

    def _screen_interact_tool(self, action: str):
        """Factory: AI-powered screen element interaction."""
        def handler(args: dict) -> ToolResult:
            si = getattr(self.jarvis, "screen_interact", None)
            if not si:
                return ToolResult(success=False, error="Screen interaction engine not available.")

            description = args.get("description", args.get("element", ""))
            if not description:
                return ToolResult(success=False, error="No element description provided.")

            try:
                if action == "find":
                    result = si.find_element(description)
                    if result.get("found"):
                        return ToolResult(success=True,
                            output=f"Found '{description}' at ({result['x']}, {result['y']})")
                    return ToolResult(success=False, error=f"Could not find '{description}' on screen.")

                elif action == "click":
                    button = args.get("button", "left")
                    result = si.click_element(description, button=button)
                    if result.get("success"):
                        return ToolResult(success=True,
                            output=f"Clicked '{description}' at ({result['x']}, {result['y']})")
                    return ToolResult(success=False,
                        error=result.get("error", f"Could not click '{description}'"))

                elif action == "type_into":
                    text = args.get("text", "")
                    result = si.type_into_element(description, text)
                    if result.get("typed"):
                        return ToolResult(success=True,
                            output=f"Typed into '{description}'")
                    return ToolResult(success=False,
                        error=result.get("error", f"Could not type into '{description}'"))

                elif action == "read":
                    text = si.read_element(description)
                    return ToolResult(success=True, output=f"Text near '{description}': {text}")

            except Exception as e:
                return ToolResult(success=False, error=f"Screen interaction failed: {e}")

            return ToolResult(success=False, error=f"Unknown screen action: {action}")
        return handler

    def _dev_agent_tool(self):
        """Handler for autonomous project building OR self-improvement."""
        import re as _re

        # Patterns that indicate "improve JARVIS itself" rather than "build new project"
        _SELF_IMPROVE_PATTERNS = [
            r"improv\w+ (?:yourself|jarvis|your(?:self| own))",
            r"implement (?:all |the )?improve",
            r"fix (?:yourself|your (?:own )?(?:code|bugs|errors))",
            r"upgrade (?:yourself|jarvis|your)",
            r"modify (?:yourself|your (?:own )?code)",
            r"update (?:yourself|your (?:own )?)",
            r"make yourself (?:better|smarter|faster)",
            r"self[- ]?(?:improve|upgrade|fix|modify|update)",
        ]

        def _is_self_improvement(goal: str) -> bool:
            goal_lower = goal.lower().strip()
            for pat in _SELF_IMPROVE_PATTERNS:
                if _re.search(pat, goal_lower):
                    return True
            return False

        def handler(args: dict) -> ToolResult:
            dev = getattr(self.jarvis, "dev_agent", None)
            if not dev:
                return ToolResult(success=False, error="Dev agent not available.")

            goal = args.get("goal", args.get("description", ""))
            language = args.get("language", "python")
            if not goal:
                return ToolResult(success=False, error="No project goal provided.")

            # ── Self-improvement detection ──
            # If user says "improve yourself", "implement all improvements", etc.
            # DON'T create a new project in jarvis_projects/
            # Instead, return guidance to use modify_file tool on JARVIS's own code
            if _is_self_improvement(goal):
                jarvis_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                return ToolResult(
                    success=True,
                    output=(
                        f"Self-improvement request detected. I should NOT create a separate project.\n"
                        f"JARVIS codebase is at: {jarvis_dir}\n"
                        f"To improve myself, I'll use the modify_file tool to edit my own source files directly.\n"
                        f"Key files:\n"
                        f"  - core/orchestrator.py — command routing & pattern matching\n"
                        f"  - core/executor.py — tool execution\n"
                        f"  - core/planner.py — AI task planning\n"
                        f"  - plugins/voice/voice_plugin.py — voice input/output\n"
                        f"  - plugins/messaging/messaging_plugin.py — WhatsApp/Telegram\n"
                        f"  - plugins/automation/auto_plugin.py — app launching\n"
                        f"  - ui/app.py — main UI\n"
                        f"\nI'll analyze what needs improving and make targeted edits."
                    ),
                )

            # ── Normal project building ──
            # Run in background with progress
            def _progress(step, msg):
                try:
                    self.jarvis.root.after(0, lambda: self.jarvis.chat.add_message(
                        "system", f"  [{step}] {msg}"))
                except Exception:
                    pass

            try:
                result = dev.build_project(goal, language=language, progress_cb=_progress)
                if result.success:
                    return ToolResult(success=True,
                        output=f"Project built successfully!\n"
                               f"  Location: {result.project_dir}\n"
                               f"  Files: {len(result.files_created)}\n"
                               f"  Fix attempts: {result.fix_attempts}\n"
                               f"  {result.summary}")
                else:
                    return ToolResult(success=False,
                        error=f"Project build failed after {result.fix_attempts} fix attempts.\n"
                              f"  Errors: {'; '.join(result.errors[:3])}\n"
                              f"  {result.summary}")
            except Exception as e:
                return ToolResult(success=False, error=f"Dev agent error: {e}")
        return handler

    def _messaging_tool(self):
        """Handler for sending messages via WhatsApp/Telegram/etc."""
        def handler(args: dict) -> ToolResult:
            plugin = self.jarvis.plugin_manager.plugins.get("messaging")
            if not plugin:
                return ToolResult(success=False, error="Messaging plugin not loaded.")

            app = args.get("platform") or args.get("app") or "whatsapp"
            contact = args.get("contact", "")
            message = args.get("message", "")

            if not contact:
                return ToolResult(success=False, error="No contact specified.")
            if not message:
                return ToolResult(success=False, error="No message to send.")

            try:
                result = plugin.send_message(app, contact, message)
                success = bool(result.get("success"))
                message_text = (
                    result.get("message")
                    or result.get("error")
                    or f"Messaging action finished for {contact} via {app}."
                )
                data = result.get("data") or {}

                if success:
                    return ToolResult(success=True, output=message_text, data=data)
                return ToolResult(success=False, error=message_text, data=data)
            except Exception as e:
                return ToolResult(success=False, error=f"Messaging failed: {e}")
        return handler

    def _input_control(self, action: str):
        """Factory: mouse/keyboard control with MANDATORY permission prompt."""
        def handler(args: dict) -> ToolResult:
            try:
                import pyautogui
            except ImportError:
                return ToolResult(success=False,
                    error="pyautogui not installed. Run: pip install pyautogui")

            # ── ALWAYS ask permission ──
            action_desc = {
                "mouse_click": f"Click at ({args.get('x', '?')}, {args.get('y', '?')})"
                               + (f" — {args.get('button', 'left')} button" if args.get('button') else ""),
                "mouse_move": f"Move mouse to ({args.get('x', '?')}, {args.get('y', '?')})",
                "mouse_scroll": f"Scroll {'up' if args.get('amount', 0) > 0 else 'down'} "
                                f"{abs(args.get('amount', 3))} clicks",
                "key_press": f"Press key: {args.get('key', '?')}",
                "key_combo": f"Press key combo: {args.get('keys', '?')}",
                "type_text": f"Type text: \"{args.get('text', '?')[:50]}\"",
                "screenshot": "Take a screenshot",
            }.get(action, f"Perform: {action}")

            # Request permission through UI
            confirmed = self._ask_permission(
                f"JARVIS wants to control your computer:\n\n"
                f"  Action: {action_desc}\n\n"
                f"Allow this?"
            )

            if not confirmed:
                return ToolResult(
                    success=False,
                    error="User declined input control action.",
                )

            # ── Execute the action ──
            try:
                pyautogui.FAILSAFE = True  # Move mouse to corner to abort

                if action == "mouse_click":
                    x = args.get("x")
                    y = args.get("y")
                    button = args.get("button", "left")
                    clicks = args.get("clicks", 1)
                    if x is not None and y is not None:
                        pyautogui.click(x=int(x), y=int(y), button=button, clicks=int(clicks))
                    else:
                        pyautogui.click(button=button, clicks=int(clicks))
                    return ToolResult(success=True, output=f"Clicked at ({x}, {y}).")

                elif action == "mouse_move":
                    x = int(args.get("x", 0))
                    y = int(args.get("y", 0))
                    duration = float(args.get("duration", 0.5))
                    pyautogui.moveTo(x, y, duration=duration)
                    return ToolResult(success=True, output=f"Moved mouse to ({x}, {y}).")

                elif action == "mouse_scroll":
                    amount = int(args.get("amount", 3))
                    pyautogui.scroll(amount)
                    direction = "up" if amount > 0 else "down"
                    return ToolResult(success=True, output=f"Scrolled {direction}.")

                elif action == "key_press":
                    key = args.get("key", "")
                    if key:
                        pyautogui.press(key)
                        return ToolResult(success=True, output=f"Pressed {key}.")
                    return ToolResult(success=False, error="No key specified.")

                elif action == "key_combo":
                    keys = args.get("keys", "")
                    if isinstance(keys, str):
                        keys = [k.strip() for k in keys.split("+")]
                    if keys:
                        pyautogui.hotkey(*keys)
                        return ToolResult(success=True, output=f"Pressed {'+'.join(keys)}.")
                    return ToolResult(success=False, error="No keys specified.")

                elif action == "type_text":
                    text = args.get("text", "")
                    interval = float(args.get("interval", 0.03))
                    if text:
                        # Use pyperclip for non-ASCII, pyautogui for ASCII
                        if all(ord(c) < 128 for c in text):
                            pyautogui.typewrite(text, interval=interval)
                        else:
                            # For non-ASCII, use clipboard paste
                            import subprocess
                            subprocess.run(["clip.exe"], input=text.encode("utf-16-le"),
                                         check=True)
                            pyautogui.hotkey("ctrl", "v")
                        return ToolResult(success=True, output=f"Typed: \"{text[:50]}\"")
                    return ToolResult(success=False, error="No text to type.")

                elif action == "screenshot":
                    import time as _time
                    path = os.path.join(os.path.expanduser("~"), "Desktop",
                        f"jarvis_screenshot_{int(_time.time())}.png")
                    img = pyautogui.screenshot()
                    img.save(path)
                    return ToolResult(success=True, output=f"Screenshot saved: {path}")

            except Exception as e:
                return ToolResult(success=False, error=f"Input control failed: {e}")

            return ToolResult(success=False, error=f"Unknown action: {action}")
        return handler

    def _ask_permission(self, message: str) -> bool:
        """
        Ask user for permission — verbal when voice is on, GUI popup otherwise.
        """
        # Try verbal confirmation first (no popups when talking to JARVIS)
        voice = self.jarvis.plugin_manager.plugins.get("voice")
        if voice and voice.is_enabled:
            if getattr(voice, "uses_gemini_live", lambda: False)():
                return True
            return voice.verbal_confirm(message)

        # Fallback: tkinter dialog
        if not hasattr(self.jarvis, 'root') or self.jarvis.root is None:
            return False

        result_holder = [None]
        event = threading.Event()

        def _ask():
            from tkinter import messagebox
            confirmed = messagebox.askyesno(
                "JARVIS — Permission Required", message,
            )
            result_holder[0] = confirmed
            event.set()

        try:
            self.jarvis.root.after(0, _ask)
            event.wait(timeout=60)
            return result_holder[0] if result_holder[0] is not None else False
        except Exception:
            return False

    def _research_tool(self, method_name: str):
        """Factory: returns a handler for web research tools."""
        def handler(args: dict) -> ToolResult:
            researcher = getattr(self.jarvis, "researcher", None)
            if not researcher:
                return ToolResult(success=False, error="Web research engine not available.")

            try:
                if method_name == "research":
                    query = args.get("query", args.get("topic", ""))
                    depth = args.get("depth", "quick")
                    result = researcher.research(query, depth=depth)
                    output = f"{result.summary}\n\nSources: {', '.join(result.references[:5])}"
                    if result.facts_extracted:
                        output += f"\n\nFacts learned: {len(result.facts_extracted)}"
                    return ToolResult(success=True, output=output)

                elif method_name == "research_cve":
                    cve_id = args.get("cve_id", args.get("keyword", ""))
                    result = researcher.research_cve(cve_id)
                    if result:
                        output = (f"CVE: {result.get('id', cve_id)}\n"
                                  f"Description: {result.get('description', 'N/A')}\n"
                                  f"Severity: {result.get('severity', 'N/A')}\n"
                                  f"Score: {result.get('score', 'N/A')}")
                        return ToolResult(success=True, output=output)
                    return ToolResult(success=False, error=f"No data found for {cve_id}")

                elif method_name == "research_target":
                    domain = args.get("domain", "")
                    result = researcher.research_target(domain)
                    if result:
                        certs = len(result.get("certificates", []))
                        output = f"OSINT for {domain}:\n  Certificates: {certs} found"
                        if result.get("subdomains"):
                            output += f"\n  Subdomains: {', '.join(list(result['subdomains'])[:20])}"
                        return ToolResult(success=True, output=output)
                    return ToolResult(success=False, error=f"No OSINT data for {domain}")

            except Exception as e:
                return ToolResult(success=False, error=f"Research failed: {e}")

            return ToolResult(success=False, error=f"Unknown research method: {method_name}")
        return handler

    def _chain_tool(self, template_name: str):
        """Factory: returns a handler that launches a task chain."""
        def handler(args: dict) -> ToolResult:
            chain_engine = getattr(self.jarvis, "chain_engine", None)
            if not chain_engine:
                return ToolResult(success=False, error="Chain engine not available.")

            domain = args.get("domain", "")
            if not domain:
                return ToolResult(success=False, error="No domain/target specified for chain.")

            if template_name == "full_pentest_chain":
                chain = chain_engine.full_pentest_chain(domain)
            elif template_name == "quick_recon_chain":
                chain = chain_engine.quick_recon_chain(domain)
            else:
                return ToolResult(success=False, error=f"Unknown chain template: {template_name}")

            def _progress(msg: str):
                try:
                    root = getattr(self.jarvis, "root", None)
                    chat = getattr(self.jarvis, "chat", None)
                    if root and chat:
                        root.after(0, lambda m=msg: chat.add_message("system", m))
                except Exception:
                    pass

            def _done(chain_obj):
                try:
                    root = getattr(self.jarvis, "root", None)
                    chat = getattr(self.jarvis, "chat", None)
                    if root and chat:
                        summary = (
                            f"Chain complete — {chain_obj.name} [{chain_obj.status}]\n"
                            + "\n".join(f"  {s.step_id}: {s.status}" for s in chain_obj.steps)
                        )
                        root.after(0, lambda s=summary: chat.add_message("assistant", s))
                except Exception:
                    pass

            chain_engine.execute_chain(
                chain,
                progress_cb=_progress,
                done_cb=_done,
                background=True,
            )
            return ToolResult(
                success=True,
                output=f"Chain '{chain.name}' launched with {len(chain.steps)} steps on {domain}. "
                       f"Chain ID: {chain.chain_id}. I'll keep you updated as it runs.",
            )
        return handler

    def _pentest_tool(self, method_name: str):
        """Factory: returns a handler that delegates to the PentestPlugin."""
        def handler(args: dict) -> ToolResult:
            plugin = self.jarvis.plugin_manager.plugins.get("pentest")
            if not plugin:
                return ToolResult(success=False, error="Pentest plugin not loaded.")

            method_map = {
                "full_recon": lambda: plugin.full_recon(self.jarvis, args.get("domain", "")),
                "subdomain_enum": lambda: plugin.subdomain_enum(self.jarvis, args.get("domain", "")),
                "tech_detect": lambda: plugin.tech_detect(self.jarvis, args.get("url", "")),
                "dir_fuzz": lambda: plugin.dir_fuzz(self.jarvis, args.get("url", "")),
                "google_dorks": lambda: plugin.google_dorks(self.jarvis, args.get("domain", "")),
                "ssl_check": lambda: plugin.ssl_check(self.jarvis, args.get("host", "")),
                "cors_check": lambda: plugin.cors_check(self.jarvis, args.get("url", "")),
                "xss_test": lambda: plugin.xss_test(self.jarvis, args.get("url", "")),
                "sqli_test": lambda: plugin.sqli_test(self.jarvis, args.get("url", "")),
                "open_redirect_test": lambda: plugin.open_redirect_test(self.jarvis, args.get("url", "")),
                "deep_header_audit": lambda: plugin.deep_header_audit(self.jarvis, args.get("url", "")),
                "wayback_urls": lambda: plugin.wayback_urls(self.jarvis, args.get("domain", "")),
                "cve_search": lambda: plugin.cve_search(self.jarvis, args.get("keyword", "")),
                "exploit_search": lambda: plugin.exploit_search(self.jarvis, args.get("keyword", "")),
            }

            if method_name not in method_map:
                return ToolResult(success=False, error=f"Unknown pentest tool: {method_name}")

            result = method_map[method_name]()
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
                # Use resilient executor for direct code execution
                resilient = getattr(self.jarvis, "resilient", None)
                if resilient and code:
                    res = resilient.execute_code(code, description="LLM run_python tool")
                    if res["success"]:
                        output = res["output"] or "(no output)"
                        fixes = res.get("fixes_applied", [])
                        msg = f"Python output:\n{output}"
                        if fixes:
                            msg += f"\n(Auto-fixed: {', '.join(fixes)})"
                        return ToolResult(success=True, output=msg)
                    else:
                        return ToolResult(
                            success=False,
                            error=f"Failed after {res['attempts']} attempts: {res['output'][:500]}",
                        )
                # Fallback to plugin
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
            msg = result["message"]
            normalized = filepath.replace("\\", "/").strip().lstrip("./")
            parts = [p for p in normalized.split("/") if p]

            if len(parts) >= 2 and parts[0] == "plugins" and filepath.endswith(".py"):
                plugin_name = parts[1]
                reload_result = sm.reload_plugin(plugin_name)
                if reload_result["success"]:
                    msg += f"\n{reload_result['message']}"
                else:
                    msg += f"\nFile updated, but plugin reload failed: {reload_result['message']}"
            elif normalized.endswith(".py") and parts and parts[0] in {"core", "ui"}:
                msg += "\nFile updated on disk. A restart or targeted reload may still be needed before the change is active."

            return ToolResult(success=True, output=msg)
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

    # ── Web Automation Tools ────────────────────────────────

    def _web_login(self, args: dict) -> ToolResult:
        """Automated web login via Selenium."""
        plugin = self.jarvis.plugin_manager.plugins.get("web_automation")
        if not plugin:
            return ToolResult(success=False, error="Web automation plugin not loaded.")

        site = args.get("site", "")
        if site == "university":
            result = plugin._uni_login("")
        else:
            url = args.get("url", "")
            result = plugin._navigate(url) if url else "No URL provided."

        return ToolResult(success=True, output=result)

    def _web_navigate(self, args: dict) -> ToolResult:
        """Navigate to a URL in automated browser."""
        plugin = self.jarvis.plugin_manager.plugins.get("web_automation")
        if not plugin:
            return ToolResult(success=False, error="Web automation plugin not loaded.")

        url = args.get("url", "")
        if not url:
            return ToolResult(success=False, error="No URL provided.")

        result = plugin._navigate(url)
        return ToolResult(success=True, output=result)

    def _web_click(self, args: dict) -> ToolResult:
        """Click an element on the current browser page."""
        plugin = self.jarvis.plugin_manager.plugins.get("web_automation")
        if not plugin:
            return ToolResult(success=False, error="Web automation plugin not loaded.")

        selector = args.get("selector", "")
        if not selector:
            return ToolResult(success=False, error="No CSS selector provided.")

        result = plugin._click(selector)
        return ToolResult(success=True, output=result)
