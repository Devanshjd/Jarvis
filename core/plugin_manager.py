"""
J.A.R.V.I.S — Plugin Manager
Discovers and manages plugins that extend JARVIS capabilities.
"""

import importlib
import os


class PluginBase:
    """Base class for all JARVIS plugins."""

    name = "unnamed_plugin"
    description = "No description"
    version = "1.0"

    def __init__(self, jarvis):
        """
        Args:
            jarvis: Reference to the main JarvisApp for accessing brain, config, UI, etc.
        """
        self.jarvis = jarvis

    def activate(self):
        """Called when the plugin is activated."""
        pass

    def deactivate(self):
        """Called when the plugin is deactivated."""
        pass

    def on_command(self, command: str, args: str) -> bool:
        """
        Handle a slash command. Return True if handled.
        Args:
            command: The command name (e.g., "voice")
            args: Everything after the command
        """
        return False

    def on_message(self, message: str) -> str | None:
        """
        Intercept a user message before it goes to the AI.
        Return modified message or None to pass through unchanged.
        """
        return None

    def on_response(self, response: str):
        """Called after JARVIS generates a response."""
        pass

    def get_status(self) -> dict:
        """Return plugin status for the UI dashboard."""
        return {"name": self.name, "active": True}


class PluginManager:
    """Discovers and manages JARVIS plugins."""

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.plugins: dict[str, PluginBase] = {}

    def load_plugin(self, plugin_class: type[PluginBase]):
        """Load and activate a plugin."""
        plugin = plugin_class(self.jarvis)
        self.plugins[plugin.name] = plugin
        plugin.activate()
        return plugin

    def unload_plugin(self, name: str):
        """Deactivate and remove a plugin."""
        if name in self.plugins:
            self.plugins[name].deactivate()
            del self.plugins[name]

    def handle_command(self, command: str, args: str) -> bool:
        """Route a command to plugins. Returns True if any plugin handled it."""
        for plugin in self.plugins.values():
            if plugin.on_command(command, args):
                return True
        return False

    def process_message(self, message: str) -> str:
        """Let plugins modify a message before AI processing."""
        for plugin in self.plugins.values():
            result = plugin.on_message(message)
            if result is not None:
                message = result
        return message

    def on_response(self, response: str):
        """Notify all plugins of an AI response."""
        for plugin in self.plugins.values():
            plugin.on_response(response)

    def get_plugin(self, name: str):
        """Get a loaded plugin by name, or None."""
        return self.plugins.get(name)

    def get_all_status(self) -> list[dict]:
        """Get status from all loaded plugins."""
        return [p.get_status() for p in self.plugins.values()]
