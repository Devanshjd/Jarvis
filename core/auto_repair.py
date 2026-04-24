"""
J.A.R.V.I.S - Automatic Repair Engine

Escalates repeated tool failures into a constrained self-repair loop.
This is intentionally conservative:
  - only mapped JARVIS components are eligible
  - only after repeated failures in a short window
  - syntax is tested before any patch is written
  - plugins/modules are reloaded after a successful patch
"""

from __future__ import annotations

import re
import time
import threading
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("jarvis.auto_repair")


@dataclass(frozen=True)
class RepairTarget:
    tool_name: str
    filepath: str
    label: str
    plugin_name: str = ""
    module_path: str = ""
    component_attr: str = ""
    component_class: str = ""


# Manual overrides — tools with non-standard file/plugin mappings
_MANUAL_TARGETS: dict[str, RepairTarget] = {
    "send_msg": RepairTarget(
        tool_name="send_msg",
        filepath="plugins/messaging/messaging_plugin.py",
        label="messaging automation",
        plugin_name="messaging",
    ),
    "screen_find": RepairTarget(
        tool_name="screen_find",
        filepath="core/screen_interact.py",
        label="screen interaction engine",
        module_path="core.screen_interact",
        component_attr="screen_interact",
        component_class="ScreenInteract",
    ),
    "screen_click": RepairTarget(
        tool_name="screen_click",
        filepath="core/screen_interact.py",
        label="screen interaction engine",
        module_path="core.screen_interact",
        component_attr="screen_interact",
        component_class="ScreenInteract",
    ),
    "screen_type": RepairTarget(
        tool_name="screen_type",
        filepath="core/screen_interact.py",
        label="screen interaction engine",
        module_path="core.screen_interact",
        component_attr="screen_interact",
        component_class="ScreenInteract",
    ),
    "screen_read": RepairTarget(
        tool_name="screen_read",
        filepath="core/screen_interact.py",
        label="screen interaction engine",
        module_path="core.screen_interact",
        component_attr="screen_interact",
        component_class="ScreenInteract",
    ),
    "web_login": RepairTarget(
        tool_name="web_login",
        filepath="plugins/web_automation/web_automation_plugin.py",
        label="web automation module",
        plugin_name="web_automation",
    ),
    "web_navigate": RepairTarget(
        tool_name="web_navigate",
        filepath="plugins/web_automation/web_automation_plugin.py",
        label="web automation module",
        plugin_name="web_automation",
    ),
    "web_click": RepairTarget(
        tool_name="web_click",
        filepath="plugins/web_automation/web_automation_plugin.py",
        label="web automation module",
        plugin_name="web_automation",
    ),
    "build_project": RepairTarget(
        tool_name="build_project",
        filepath="core/dev_agent.py",
        label="developer agent",
        module_path="core.dev_agent",
        component_attr="dev_agent",
        component_class="DevAgent",
    ),
}

# Category -> (filepath, label, plugin_name, module_path, component_attr, component_class)
_CATEGORY_TO_FILE: dict[str, tuple[str, str, str, str, str, str]] = {
    "research":       ("plugins/web_intel/web_intel_plugin.py", "web intelligence", "web_intel", "", "", ""),
    "communication":  ("plugins/messaging/messaging_plugin.py", "messaging automation", "messaging", "", "", ""),
    "screen":         ("core/screen_interact.py", "screen interaction engine", "", "core.screen_interact", "screen_interact", "ScreenInteract"),
    "input_control":  ("core/executor.py", "input control handler", "", "", "", ""),
    "system":         ("core/executor.py", "system tool handler", "", "", "", ""),
    "desktop":        ("core/executor.py", "desktop tool handler", "", "", "", ""),
    "web_automation": ("plugins/web_automation/web_automation_plugin.py", "web automation module", "web_automation", "", "", ""),
    "security":       ("plugins/security/security_plugin.py", "security scanner", "security", "", "", ""),
    "smart_home":     ("plugins/smart_home/smart_home_plugin.py", "smart home controller", "smart_home", "", "", ""),
    "file_management":("core/executor.py", "file management handler", "", "", "", ""),
    "development":    ("core/dev_agent.py", "developer agent", "", "core.dev_agent", "dev_agent", "DevAgent"),
}


def _build_repair_targets() -> dict[str, RepairTarget]:
    """Build repair targets from TOOL_SCHEMAS + manual overrides.

    Manual overrides take priority.  For tools not in the manual list,
    we derive a RepairTarget from the schema's ``category`` field using
    ``_CATEGORY_TO_FILE``.
    """
    targets = dict(_MANUAL_TARGETS)

    try:
        from core.tool_schemas import TOOL_SCHEMAS
        for schema in TOOL_SCHEMAS:
            name = schema["name"]
            if name in targets:
                continue  # Manual override wins
            if schema.get("layer") != "python":
                continue  # Can't repair Electron-only tools from Python

            category = schema.get("category", "")
            mapping = _CATEGORY_TO_FILE.get(category)
            if not mapping:
                continue

            filepath, label, plugin_name, module_path, component_attr, component_class = mapping
            targets[name] = RepairTarget(
                tool_name=name,
                filepath=filepath,
                label=label,
                plugin_name=plugin_name,
                module_path=module_path,
                component_attr=component_attr,
                component_class=component_class,
            )
    except Exception as e:
        logger.warning("Could not auto-generate repair targets from schemas: %s", e)

    return targets


REPAIR_TARGETS: dict[str, RepairTarget] = _build_repair_targets()


SKIP_REPAIR_RE = re.compile(
    r"(?:api key|not configured|rate limit|credit balance|quota|403|402|401|"
    r"user declined|user denied|cancelled|no message|no contact|no app name|"
    r"no search query|no element description|install:|pyautogui not installed|"
    r"pillow not available|permission denied)",
    re.IGNORECASE,
)


class AutoRepairEngine:
    """Background self-repair coordinator for repeated runtime failures."""

    def __init__(self, app):
        self.app = app
        cfg = app.config.get("auto_repair", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.failure_threshold = int(cfg.get("failure_threshold", 3))
        self.failure_window_sec = float(cfg.get("failure_window_sec", 600))
        self.cooldown_sec = float(cfg.get("cooldown_sec", 300))
        self.max_repairs_per_target = int(cfg.get("max_repairs_per_target", 2))
        self.announce_success = bool(cfg.get("announce_success", True))

        self._lock = threading.Lock()
        self._failures: dict[str, list[dict]] = {}
        self._state: dict[str, dict] = {}

    def note_tool_failure(self, tool_name: str, tool_args: dict, error: str) -> dict:
        """
        Record a failed tool run and schedule a repair when the threshold is met.
        """
        if not self.enabled or not error:
            return {}

        target = REPAIR_TARGETS.get(tool_name)
        if not target:
            return {}
        if SKIP_REPAIR_RE.search(error):
            return {}

        now = time.time()
        with self._lock:
            failures = [
                item for item in self._failures.get(tool_name, [])
                if now - item["time"] <= self.failure_window_sec
            ]
            failures.append({
                "time": now,
                "args": dict(tool_args or {}),
                "error": str(error or "")[:1000],
            })
            self._failures[tool_name] = failures

            state = self._state.setdefault(tool_name, {
                "in_progress": False,
                "last_repair_at": 0.0,
                "repair_count": 0,
                "last_status": "",
                "last_error": "",
            })

            if state["in_progress"]:
                return {
                    "queued": False,
                    "status": "repair_in_progress",
                    "label": target.label,
                }

            if len(failures) < self.failure_threshold:
                return {
                    "queued": False,
                    "status": "waiting_threshold",
                    "label": target.label,
                    "count": len(failures),
                }

            if (now - state["last_repair_at"]) < self.cooldown_sec:
                return {
                    "queued": False,
                    "status": "cooldown",
                    "label": target.label,
                }

            if state["repair_count"] >= self.max_repairs_per_target:
                return {
                    "queued": False,
                    "status": "repair_limit_reached",
                    "label": target.label,
                }

            state["in_progress"] = True
            state["last_status"] = "queued"
            worker = threading.Thread(
                target=self._repair_worker,
                args=(tool_name,),
                daemon=True,
                name=f"jarvis-auto-repair-{tool_name}",
            )
            worker.start()
            return {
                "queued": True,
                "status": "repair_started",
                "label": target.label,
                "count": len(failures),
            }

    def _repair_worker(self, tool_name: str) -> None:
        target = REPAIR_TARGETS[tool_name]
        sm = getattr(self.app, "self_modify", None)
        brain = getattr(self.app, "brain", None)

        if not sm or not brain:
            self._finish(tool_name, success=False, error="Repair prerequisites unavailable.")
            return

        original = sm.read_file(target.filepath)
        if not original:
            self._finish(tool_name, success=False, error=f"Could not read {target.filepath}")
            return

        failure_context = self._build_failure_context(tool_name)
        screen_context = ""
        try:
            monitor = getattr(self.app, "screen_monitor", None)
            if monitor:
                screen_context = monitor.get_screen_context()
        except Exception:
            screen_context = ""

        prompt = (
            f"You are JARVIS self-repair. A runtime tool has failed repeatedly.\n\n"
            f"Target tool: {tool_name}\n"
            f"Target component: {target.label}\n"
            f"Target file: {target.filepath}\n\n"
            f"Recent failures:\n{failure_context}\n\n"
            f"Current screen context:\n{screen_context or 'No live screen context.'}\n\n"
            f"Current file content:\n```python\n{original[:24000]}\n```\n\n"
            f"Instructions:\n"
            f"- Apply the smallest safe fix that addresses the repeated failure.\n"
            f"- Preserve public method names and existing architecture.\n"
            f"- Do not add placeholders or TODOs.\n"
            f"- Return ONLY the full corrected Python source for this one file.\n"
            f"- No markdown fences. No explanation."
        )

        try:
            reply, _ = brain._chat_with_fallback(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are a careful Python maintenance engineer for JARVIS. "
                    "Return only corrected Python source code for the target file."
                ),
                max_tokens=4096,
            )
        except Exception as exc:
            self._finish(tool_name, success=False, error=f"LLM repair failed: {exc}")
            return

        candidate = self._strip_code_fences(reply or "")
        if not candidate or candidate.strip() == original.strip():
            self._finish(tool_name, success=False, error="Repair candidate was empty or unchanged.")
            return

        syntax = sm.test_code(candidate, "syntax")
        if not syntax.get("success"):
            self._finish(tool_name, success=False, error=f"Syntax test failed: {syntax.get('message', 'invalid code')}")
            return

        write_result = sm.write_file(
            target.filepath,
            candidate,
            reason=f"Automatic repair after repeated {tool_name} failures",
        )
        if not write_result.get("success"):
            self._finish(tool_name, success=False, error=write_result.get("message", "write failed"))
            return

        reload_result = self._reload_target(target)
        if not reload_result.get("success"):
            sm.rollback(target.filepath)
            self._finish(tool_name, success=False, error=reload_result.get("message", "reload failed"))
            return

        self._finish(tool_name, success=True, error="")
        self._notify_success(target.label, target.filepath)

    def _reload_target(self, target: RepairTarget) -> dict:
        sm = getattr(self.app, "self_modify", None)
        if not sm:
            return {"success": False, "message": "Self-modification engine unavailable."}

        if target.plugin_name:
            return sm.reload_plugin(target.plugin_name)

        if target.module_path:
            hot = sm.hot_reload(target.module_path)
            if not hot.get("success"):
                return hot

        if target.component_attr == "screen_interact":
            from core.screen_interact import ScreenInteract
            self.app.screen_interact = ScreenInteract(self.app)
        elif target.component_attr == "dev_agent":
            from core.dev_agent import DevAgent
            self.app.dev_agent = DevAgent(self.app)

        return {"success": True, "message": f"Reloaded {target.label}."}

    def _build_failure_context(self, tool_name: str) -> str:
        with self._lock:
            failures = list(self._failures.get(tool_name, []))[-5:]

        lines = []
        for item in failures:
            when = time.strftime("%H:%M:%S", time.localtime(item["time"]))
            lines.append(f"- {when} | args={item['args']} | error={item['error']}")
        return "\n".join(lines) or "- No failure history recorded."

    def _finish(self, tool_name: str, *, success: bool, error: str) -> None:
        with self._lock:
            state = self._state.setdefault(tool_name, {})
            state["in_progress"] = False
            state["last_repair_at"] = time.time()
            state["repair_count"] = int(state.get("repair_count", 0)) + (1 if success else 0)
            state["last_status"] = "success" if success else "failed"
            state["last_error"] = error
        if error:
            logger.warning("Auto-repair for %s failed: %s", tool_name, error)
        else:
            logger.info("Auto-repair for %s succeeded", tool_name)

    def _notify_success(self, label: str, filepath: str) -> None:
        if not self.announce_success:
            return
        root = getattr(self.app, "root", None)
        chat = getattr(self.app, "chat", None)
        if not root or not chat:
            return

        def _show():
            try:
                chat.add_message(
                    "system",
                    f"Automatic repair applied to {label}. Reloaded {filepath}.",
                )
            except Exception:
                pass

        try:
            root.after(0, _show)
        except Exception:
            pass

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()
