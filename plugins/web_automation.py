"""
Compatibility shim for web automation helpers.

The canonical plugin implementation lives in:
    plugins/web_automation/web_automation_plugin.py

This module intentionally avoids keeping a second automation
implementation in sync, and it must not contain embedded credentials.
"""

from plugins.web_automation.web_automation_plugin import WebAutomationPlugin


def web_login(jarvis, site="university", url=None):
    """Backward-compatible wrapper around the package plugin."""
    plugin = WebAutomationPlugin(jarvis)
    plugin.activate()
    try:
        if site == "university":
            if url:
                navigate_result = plugin._navigate(url)
                if navigate_result.startswith("Failed"):
                    return navigate_result
            return plugin._uni_login("")
        if url:
            return plugin._navigate(url)
        return "Please specify a URL for custom web login."
    finally:
        plugin.deactivate()


def web_navigate(jarvis, url):
    """Backward-compatible wrapper around the package plugin."""
    plugin = WebAutomationPlugin(jarvis)
    plugin.activate()
    try:
        return plugin._navigate(url)
    finally:
        plugin.deactivate()


def web_click(jarvis, selector):
    """Backward-compatible wrapper around the package plugin."""
    plugin = WebAutomationPlugin(jarvis)
    plugin.activate()
    try:
        return plugin._click(selector)
    finally:
        plugin.deactivate()
