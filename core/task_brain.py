"""
J.A.R.V.I.S - Task Brain

Persistent episodic and procedural memory for operator tasks.

This is the layer that helps JARVIS move beyond:
- remembering facts about Dev
- tracking moods and tool reliability

and toward:
- remembering what tasks it attempted
- remembering which approaches actually worked
- reusing successful procedures for future requests
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import threading
from typing import Any
from core.runtime_hygiene import is_meaningful_learning_value, sanitize_learning_text


TASK_BRAIN_FILE = Path.home() / ".jarvis_task_brain.json"
MAX_EPISODES = 300
MAX_RECENT_GOALS = 10
MAX_RECENT_RESULTS = 10

SENSITIVE_KEYS = {
    "password", "pass", "pwd", "token", "api_key", "apikey",
    "secret", "authorization", "auth", "cookie", "session",
}


@dataclass
class TaskProcedure:
    tool_name: str
    successes: int
    failures: int
    cancelled: int
    avg_attempts: float
    common_args: list[str]
    last_status: str
    last_used: str
    sample_goals: list[str]

    def to_prompt_line(self) -> str:
        arg_text = ", ".join(self.common_args) if self.common_args else "the required tool inputs"
        caution = " Verify carefully." if self.failures > self.successes else ""
        return (
            f"- {self.tool_name}: {self.successes} successful runs, {self.failures} failures. "
            f"It usually works when {arg_text} are filled first and the result is verified.{caution}"
        )

    def to_user_line(self) -> str:
        arg_text = ", ".join(self.common_args) if self.common_args else "no stable inputs yet"
        return (
            f"- {self.tool_name}: {self.successes} success, {self.failures} fail, "
            f"avg attempts {self.avg_attempts:.1f}, common inputs: {arg_text}"
        )


class TaskBrain:
    """Learns task episodes and stable procedures from tool execution outcomes."""

    def __init__(self, jarvis=None, path: Path | None = None):
        self.jarvis = jarvis
        self.path = path or TASK_BRAIN_FILE
        self._lock = threading.Lock()
        self._state = self._load()

    def _load(self) -> dict:
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
        except Exception:
            data = {}

        data.setdefault("episodes", [])
        data.setdefault("procedures", {})
        data.setdefault("stats", {
            "recorded": 0,
            "successes": 0,
            "failures": 0,
            "cancelled": 0,
        })
        return data

    def _save(self) -> None:
        try:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._state, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def record_task_outcome(
        self,
        *,
        goal: str,
        tool_name: str,
        args: dict | None,
        status: str,
        result_text: str = "",
        attempts: int = 0,
        step: str = "",
        session_id: str = "",
    ) -> None:
        """Record one task episode and update the learned procedure for that tool."""
        tool_name = (tool_name or "").strip()
        if not tool_name:
            return

        safe_goal = self._clean_text(goal, 180)
        safe_result = self._clean_text(result_text, 220)
        safe_args = self._sanitize_args(args or {})
        episode = {
            "time": datetime.now().isoformat(),
            "session_id": session_id,
            "goal": safe_goal,
            "tool": tool_name,
            "args": safe_args,
            "status": status,
            "step": step or status,
            "attempts": max(0, int(attempts or 0)),
            "result": safe_result,
        }

        with self._lock:
            episodes = self._state["episodes"]
            episodes.append(episode)
            self._state["episodes"] = episodes[-MAX_EPISODES:]
            self._update_stats(status)
            self._update_procedure(tool_name, safe_goal, safe_args, status, safe_result, episode["attempts"])
            self._save()

    def get_prompt_context(self, user_text: str = "", limit: int = 4) -> str:
        procedures = self.find_relevant_procedures(user_text, limit=limit)
        if not procedures:
            procedures = self.get_stable_procedures(limit=limit)
        if not procedures:
            return ""

        lines = ["[TASK BRAIN]"]
        lines.append("Known procedures learned from previous task outcomes:")
        for proc in procedures:
            lines.append(proc.to_prompt_line())
        lines.append(
            "[TASK BRAIN RULES]\n"
            "- Prefer repeating a known-good procedure before improvising a new one.\n"
            "- Ask only for the inputs that are still missing.\n"
            "- Treat repeated failures as a signal to slow down, verify more, and explain what went wrong."
        )
        return "\n".join(lines)

    def describe_for_user(self, limit: int = 6) -> str:
        stats = self._state.get("stats", {})
        procedures = self.get_stable_procedures(limit=limit)
        episodes = self.get_recent_episodes(limit=3)

        lines = [
            "Task Brain:",
            f"- Episodes: {stats.get('recorded', 0)}",
            f"- Successes: {stats.get('successes', 0)} | Failures: {stats.get('failures', 0)} | Cancelled: {stats.get('cancelled', 0)}",
        ]
        if procedures:
            lines.append("- Learned procedures:")
            for proc in procedures:
                lines.append(f"  {proc.to_user_line()}")
        if episodes:
            lines.append("- Recent episodes:")
            for ep in episodes:
                lines.append(
                    f"  {ep['tool']} [{ep['status']}] attempts={ep.get('attempts', 0)}"
                    + (f" | {ep['goal']}" if ep.get("goal") else "")
                )
        return "\n".join(lines)

    def describe_dataset_export(self) -> str:
        stats = self._state.get("stats", {})
        successes = int(stats.get("successes", 0))
        failures = int(stats.get("failures", 0))
        episodes = int(stats.get("recorded", 0))
        return (
            "JARVIS training dataset export\n"
            f"- Recorded task episodes: {episodes}\n"
            f"- Successful episodes usable for planner SFT: {successes}\n"
            f"- Failed episodes kept in raw logs for analysis: {failures}\n"
            "- Export command: /dataset export\n"
            "- Output files: raw episodes JSONL, planner SFT JSONL, learned procedures JSON"
        )

    def export_datasets(self, output_dir: str | Path) -> dict:
        """Export task-brain data into training-friendly files."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            episodes = list(self._state.get("episodes", []))
            procedures_state = dict(self._state.get("procedures", {}))
            stats = dict(self._state.get("stats", {}))

        episode_rows = [self._episode_export_row(ep) for ep in episodes]
        successful = [ep for ep in episodes if ep.get("status") == "completed" and ep.get("goal") and ep.get("tool")]
        planner_rows = [self._planner_export_row(ep, procedures_state.get(ep["tool"], {})) for ep in successful]
        procedure_rows = [self._procedure_export_row(name, data) for name, data in procedures_state.items()]

        episodes_path = out_dir / "jarvis_task_episodes.jsonl"
        planner_path = out_dir / "jarvis_task_planner_sft.jsonl"
        procedures_path = out_dir / "jarvis_task_procedures.json"
        manifest_path = out_dir / "manifest.json"

        self._write_jsonl(episodes_path, episode_rows)
        self._write_jsonl(planner_path, planner_rows)
        procedures_path.write_text(json.dumps(procedure_rows, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest = {
            "schema_version": "jarvis.dataset_manifest.v1",
            "generated_at": datetime.now().isoformat(),
            "source_store": str(self.path),
            "stats": stats,
            "files": {
                "episodes": episodes_path.name,
                "planner_sft": planner_path.name,
                "procedures": procedures_path.name,
            },
            "counts": {
                "episodes": len(episode_rows),
                "planner_sft": len(planner_rows),
                "procedures": len(procedure_rows),
            },
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "output_dir": str(out_dir),
            "episodes_path": str(episodes_path),
            "planner_path": str(planner_path),
            "procedures_path": str(procedures_path),
            "manifest_path": str(manifest_path),
            "episodes": len(episode_rows),
            "planner_examples": len(planner_rows),
            "procedures": len(procedure_rows),
        }

    def get_capability_hint(self, tool_name: str) -> str:
        proc = self._procedure_for(tool_name)
        if not proc:
            return ""
        if proc.successes <= 0:
            return ""
        args_text = ", ".join(proc.common_args) if proc.common_args else "the required inputs"
        hint = f"{proc.successes} successful runs; usually works when {args_text} are filled first"
        if proc.failures > proc.successes:
            hint += "; verify more carefully"
        return hint

    def get_recent_episodes(self, limit: int = 5) -> list[dict]:
        episodes = list(self._state.get("episodes", []))
        return list(reversed(episodes[-limit:]))

    def get_stable_procedures(self, limit: int = 5) -> list[TaskProcedure]:
        procedures = [self._procedure_from_state(name, data) for name, data in self._state.get("procedures", {}).items()]
        procedures = [
            proc for proc in procedures
            if proc.successes > 0 and proc.successes >= proc.failures
        ]
        procedures.sort(key=lambda proc: (proc.successes - proc.failures, proc.successes, proc.last_used), reverse=True)
        return procedures[:limit]

    def find_relevant_procedures(self, user_text: str, limit: int = 4) -> list[TaskProcedure]:
        query_tokens = self._tokenize(user_text)
        if not query_tokens:
            return []

        ranked: list[tuple[float, TaskProcedure]] = []
        for name, data in self._state.get("procedures", {}).items():
            proc = self._procedure_from_state(name, data)
            if proc.successes <= 0:
                continue
            haystack = " ".join([proc.tool_name, " ".join(proc.sample_goals), " ".join(proc.common_args)]).lower()
            haystack_tokens = self._tokenize(haystack)
            score = float(len(query_tokens & haystack_tokens))
            if proc.tool_name in user_text.lower():
                score += 2.0
            if score > 0:
                ranked.append((score, proc))

        ranked.sort(key=lambda item: (item[0], item[1].successes - item[1].failures, item[1].successes), reverse=True)
        return [proc for _, proc in ranked[:limit]]

    def _procedure_for(self, tool_name: str) -> TaskProcedure | None:
        data = self._state.get("procedures", {}).get(tool_name)
        if not data:
            return None
        return self._procedure_from_state(tool_name, data)

    def _episode_export_row(self, episode: dict) -> dict:
        return {
            "schema": "jarvis.task_episode.v1",
            "time": episode.get("time", ""),
            "goal": episode.get("goal", ""),
            "tool_name": episode.get("tool", ""),
            "args": dict(episode.get("args", {})),
            "status": episode.get("status", ""),
            "step": episode.get("step", ""),
            "attempts": int(episode.get("attempts", 0)),
            "result": episode.get("result", ""),
        }

    def _planner_export_row(self, episode: dict, procedure: dict) -> dict:
        tool_name = episode.get("tool", "")
        args = dict(episode.get("args", {}))
        required_args = sorted([key for key, value in args.items() if self._is_meaningful(value)])
        procedure_hint = self.get_capability_hint(tool_name)
        target = {
            "tool_name": tool_name,
            "args": args,
            "required_args_present": required_args,
            "verification_required": True,
            "expected_status": episode.get("status", "completed"),
            "attempts": int(episode.get("attempts", 0)),
        }
        if procedure_hint:
            target["procedure_hint"] = procedure_hint
        return {
            "schema": "jarvis.task_planner_sft.v1",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are JARVIS task planner. Choose the best single tool for the user's goal, "
                        "fill the tool arguments from context, and require verification before claiming success. "
                        "Reply as JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": episode.get("goal", ""),
                },
                {
                    "role": "assistant",
                    "content": json.dumps(target, ensure_ascii=False),
                },
            ],
            "metadata": {
                "source": "task_brain",
                "tool_name": tool_name,
                "status": episode.get("status", ""),
                "procedure_successes": int(procedure.get("successes", 0)),
            },
        }

    def _procedure_export_row(self, tool_name: str, data: dict) -> dict:
        proc = self._procedure_from_state(tool_name, data)
        return {
            "schema": "jarvis.task_procedure.v1",
            "tool_name": proc.tool_name,
            "successes": proc.successes,
            "failures": proc.failures,
            "cancelled": proc.cancelled,
            "avg_attempts": proc.avg_attempts,
            "common_args": proc.common_args,
            "last_status": proc.last_status,
            "last_used": proc.last_used,
            "sample_goals": proc.sample_goals,
        }

    def _write_jsonl(self, path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _procedure_from_state(self, tool_name: str, data: dict) -> TaskProcedure:
        return TaskProcedure(
            tool_name=tool_name,
            successes=int(data.get("successes", 0)),
            failures=int(data.get("failures", 0)),
            cancelled=int(data.get("cancelled", 0)),
            avg_attempts=float(data.get("avg_attempts", 0.0)),
            common_args=list(data.get("common_args", [])),
            last_status=data.get("last_status", "unknown"),
            last_used=data.get("last_used", ""),
            sample_goals=list(data.get("sample_goals", [])),
        )

    def _update_stats(self, status: str) -> None:
        stats = self._state["stats"]
        stats["recorded"] = int(stats.get("recorded", 0)) + 1
        if status == "completed":
            stats["successes"] = int(stats.get("successes", 0)) + 1
        elif status == "failed":
            stats["failures"] = int(stats.get("failures", 0)) + 1
        elif status == "cancelled":
            stats["cancelled"] = int(stats.get("cancelled", 0)) + 1

    def _update_procedure(
        self,
        tool_name: str,
        goal: str,
        args: dict,
        status: str,
        result_text: str,
        attempts: int,
    ) -> None:
        procedures = self._state["procedures"]
        proc = procedures.setdefault(tool_name, {
            "successes": 0,
            "failures": 0,
            "cancelled": 0,
            "attempt_total": 0,
            "attempt_samples": 0,
            "arg_counts": {},
            "sample_goals": [],
            "recent_results": [],
            "last_status": "",
            "last_used": "",
        })

        if status == "completed":
            proc["successes"] = int(proc.get("successes", 0)) + 1
        elif status == "failed":
            proc["failures"] = int(proc.get("failures", 0)) + 1
        elif status == "cancelled":
            proc["cancelled"] = int(proc.get("cancelled", 0)) + 1

        if attempts > 0 and status in {"completed", "failed"}:
            proc["attempt_total"] = int(proc.get("attempt_total", 0)) + attempts
            proc["attempt_samples"] = int(proc.get("attempt_samples", 0)) + 1

        for key, value in args.items():
            if status == "completed" and self._is_meaningful(value, key):
                counts = proc.setdefault("arg_counts", {})
                counts[key] = int(counts.get(key, 0)) + 1

        if goal:
            sample_goals = proc.setdefault("sample_goals", [])
            if goal not in sample_goals:
                sample_goals.append(goal)
                proc["sample_goals"] = sample_goals[-MAX_RECENT_GOALS:]

        if result_text:
            results = proc.setdefault("recent_results", [])
            results.append(result_text)
            proc["recent_results"] = results[-MAX_RECENT_RESULTS:]

        proc["last_status"] = status
        proc["last_used"] = datetime.now().isoformat()
        samples = int(proc.get("attempt_samples", 0))
        if samples > 0:
            proc["avg_attempts"] = round(float(proc.get("attempt_total", 0)) / samples, 2)
        else:
            proc["avg_attempts"] = 0.0
        proc["common_args"] = self._common_args(proc.get("arg_counts", {}), proc.get("successes", 0), proc.get("failures", 0))

    def _common_args(self, counts: dict, successes: int, failures: int) -> list[str]:
        if not counts:
            return []
        baseline = max(1, min(max(successes, 1), max(successes + failures, 1)))
        items = [(key, count) for key, count in counts.items() if count >= baseline or count >= 2]
        items.sort(key=lambda item: (-item[1], item[0]))
        return [key for key, _ in items[:6]]

    def _sanitize_args(self, args: dict) -> dict:
        safe = {}
        for key, value in (args or {}).items():
            key_lower = str(key).lower()
            if any(token in key_lower for token in SENSITIVE_KEYS):
                safe[key] = "[redacted]"
                continue
            cleaned = self._sanitize_value(value)
            if self._is_meaningful(cleaned, str(key)):
                safe[key] = cleaned
        return safe

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if self._looks_secret(text):
                return "[redacted]"
            return self._clean_text(text, 160)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value[:6]]
        if isinstance(value, dict):
            return {str(k): self._sanitize_value(v) for k, v in list(value.items())[:8]}
        return self._clean_text(str(value), 160)

    def _clean_text(self, text: str, limit: int) -> str:
        return sanitize_learning_text(text, limit=limit)

    def _looks_secret(self, text: str) -> bool:
        if not text:
            return False
        if len(text) >= 24 and re.fullmatch(r"[A-Za-z0-9_\-.:/+=]+", text):
            return True
        if text.startswith(("sk-", "gsk_", "AIza", "hf_", "ghp_")):
            return True
        return False

    def _is_meaningful(self, value: Any, key: str = "") -> bool:
        return is_meaningful_learning_value(value, key)

    def _tokenize(self, text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9_+-]+", (text or "").lower()) if len(token) > 1}
