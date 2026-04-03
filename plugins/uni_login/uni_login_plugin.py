"""
J.A.R.V.I.S — UniLoginPlugin
University login automation (delegates to web_automation plugin).

This is a lightweight wrapper. Use /unilogin command.
"""

from core.plugin_manager import PluginBase


class UniLoginPlugin(PluginBase):
    """Thin wrapper — delegates to web_automation for university login."""

    name = "uni_login"
    description = "University login shortcut"

    def on_command(self, command: str, args: str) -> bool:
        if command == "/unilogin":
            web = self.jarvis.plugin_manager.plugins.get("web_automation")
            if web:
                result = web._uni_login(args)
                self.jarvis.chat.add_message("assistant", result)
            else:
                self.jarvis.chat.add_message(
                    "assistant",
                    "Web automation plugin not loaded. Load it first.",
                )
            return True
        return False
