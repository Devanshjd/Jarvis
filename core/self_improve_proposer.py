"""
J.A.R.V.I.S — Self-Improvement Proposer (human-gated)

The safe version of "JARVIS improves its own code". It does NOT touch live
source on its own. Instead it:

    1. Takes a target file + an instruction (what to improve)
    2. Drafts a modified version with the local LLM
    3. TESTS the draft in the sandbox — multiple simulations:
         · syntax compile
         · loads/imports cleanly (imports resolve) — run N times
    4. REPORTS back honestly:
         · ✅ "it works — here's the change, approve to apply?"  OR
         · ❌ "couldn't do it — here's the exact error and why"
    5. Only applies AFTER the human approves (apply()), with a backup.

This closes the loop with the live-learning corpus: JARVIS knows what it fails
at, drafts a fix, proves it in the sandbox, and asks you before touching
anything. No brick-yourself risk, no silent self-rewrites.
"""
from __future__ import annotations

import difflib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_DIR = PROJECT_ROOT / ".jarvis_sandbox"

# Cap the file size we'll let the local model rewrite — a 4B model mangles
# large files. Focused files/functions only.
MAX_FILE_CHARS = 12000


class SelfImprovementProposer:
    def __init__(self, jarvis=None):
        self.jarvis = jarvis
        SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        # Stash of the last proposal awaiting approval.
        self._pending: Optional[dict] = None
        # Reuse the real engine's safety guards + backup/write if present.
        try:
            from core.self_modify import SelfModificationEngine
            self._engine = SelfModificationEngine(jarvis)
        except Exception:
            self._engine = None

    # ─── Safety ───────────────────────────────────────────────────────────
    def _can_modify(self, filepath: str) -> tuple[bool, str]:
        if self._engine and hasattr(self._engine, "can_modify"):
            return self._engine.can_modify(filepath)
        # Conservative fallback: only inside core/ or plugins/.
        rel = Path(filepath)
        if rel.parts and rel.parts[0] in ("core", "plugins"):
            return True, "ok"
        return False, "Only core/ and plugins/ files may be modified."

    # ─── Propose + test ───────────────────────────────────────────────────
    def propose_and_test(self, filepath: str, instruction: str,
                         simulations: int = 3) -> dict:
        """Draft a change, test it, and return an honest report. Does NOT
        apply anything."""
        report = {
            "file": filepath, "instruction": instruction,
            "status": "failed", "diff": "", "simulations": [],
            "error": "", "why": "", "ready_to_apply": False,
        }

        ok, why = self._can_modify(filepath)
        if not ok:
            report["error"] = "Not allowed to modify this file."
            report["why"] = why
            return report

        abs_path = PROJECT_ROOT / filepath
        if not abs_path.exists():
            report["error"] = f"{filepath} does not exist."
            report["why"] = "Nothing to improve — the file wasn't found."
            return report

        original = abs_path.read_text(encoding="utf-8")
        if len(original) > MAX_FILE_CHARS:
            report["error"] = f"File too large ({len(original)} chars > {MAX_FILE_CHARS})."
            report["why"] = ("Local model can't safely rewrite a file this big. "
                             "Point me at a smaller file or a specific function.")
            return report

        # 1) Draft the improved version with the local LLM.
        proposed = self._draft(original, instruction)
        if not proposed:
            report["error"] = "The local model did not return a usable rewrite."
            report["why"] = ("Ollama was unreachable or returned nothing. "
                             "Is the model running? (ollama serve / gemma3:4b)")
            return report
        if proposed.strip() == original.strip():
            report["error"] = "No change produced."
            report["why"] = "The model returned the file unchanged — nothing to apply."
            return report

        report["diff"] = self._diff(original, proposed, filepath)

        # 2) Simulations.
        sims = []
        # sim: syntax
        sims.append(self._sim_syntax(proposed))
        # sim: load/import N times
        for i in range(max(1, simulations)):
            sims.append(self._sim_import(proposed, i + 1))
        report["simulations"] = sims

        failed = [s for s in sims if not s["passed"]]
        if failed:
            first = failed[0]
            report["status"] = "failed"
            report["error"] = first["error"]
            report["why"] = self._explain(first["error"], instruction)
            report["ready_to_apply"] = False
            return report

        # 3) All green — stash for approval.
        report["status"] = "ready"
        report["ready_to_apply"] = True
        report["why"] = (f"Passed all {len(sims)} sandbox checks "
                         f"({len(sims)-simulations} syntax + {simulations} load simulations).")
        self._pending = {"file": filepath, "content": proposed,
                         "instruction": instruction}
        return report

    def apply(self, filepath: Optional[str] = None) -> dict:
        """Apply the pending proposal — ONLY call after the human approves.
        Backs up first (via the engine)."""
        if not self._pending:
            return {"success": False, "message": "No proposal is pending approval."}
        if filepath and filepath != self._pending["file"]:
            return {"success": False, "message": "Pending proposal is for a different file."}
        p = self._pending
        if self._engine and hasattr(self._engine, "write_file"):
            res = self._engine.write_file(p["file"], p["content"],
                                          reason=f"self-improve: {p['instruction']}")
        else:
            abs_path = PROJECT_ROOT / p["file"]
            backup = abs_path.with_suffix(abs_path.suffix + f".bak.{int(time.time())}")
            backup.write_text(abs_path.read_text(encoding="utf-8"), encoding="utf-8")
            abs_path.write_text(p["content"], encoding="utf-8")
            res = {"success": True, "message": f"Applied. Backup: {backup}"}
        self._pending = None
        return res

    def discard(self) -> dict:
        self._pending = None
        return {"success": True, "message": "Proposal discarded."}

    # ─── Autonomous weakness analysis ─────────────────────────────────────
    def analyze_weaknesses(self, top: int = 5) -> dict:
        """Read the live-learning corpus, surface JARVIS's recurring failures
        (turns the user corrected), and suggest what to look at. This is the
        autonomous 'find your own weakness' step — but it only SUGGESTS; the
        human still confirms a target before any code is drafted."""
        from collections import Counter
        log = PROJECT_ROOT / "training" / "learning_log.jsonl"
        failures: list[dict] = []
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("source") == "live_session" and d.get("outcome") == "failure":
                    failures.append(d)

        if not failures:
            return {
                "weaknesses": [], "total_failures": 0,
                "note": ("No live failures logged yet. Use JARVIS normally — when you "
                         "correct it, those turns get captured here, and this will "
                         "surface the recurring ones to fix."),
            }

        # Group by the approach/tool that kept getting corrected.
        by_approach = Counter(f.get("tool_used", "unknown") for f in failures)
        weaknesses = []
        for approach, count in by_approach.most_common(top):
            examples = [f.get("user_input", "")[:80]
                        for f in failures if f.get("tool_used") == approach][:3]
            weaknesses.append({
                "approach": approach, "failure_count": count, "examples": examples,
            })
        return {
            "weaknesses": weaknesses, "total_failures": len(failures),
            "note": ("These are the areas you corrected most. Pick one and tell me the "
                     "file + fix, and I'll draft it, test it in the sandbox, and show "
                     "you the result for approval."),
        }

    # ─── Simulations ──────────────────────────────────────────────────────
    def _sim_syntax(self, code: str) -> dict:
        try:
            compile(code, "<proposed>", "exec")
            return {"name": "syntax compile", "passed": True, "output": "compiles cleanly", "error": ""}
        except SyntaxError as e:
            return {"name": "syntax compile", "passed": False,
                    "output": "", "error": f"SyntaxError: {e.msg} (line {e.lineno})"}

    def _sim_import(self, code: str, n: int) -> dict:
        """Write the proposed module to the sandbox and try to load it in a
        fresh subprocess (its imports resolve against the real package)."""
        sandbox_file = SANDBOX_DIR / f"proposed_{int(time.time()*1000)}_{n}.py"
        sandbox_file.write_text(code, encoding="utf-8")
        runner = (
            "import importlib.util, sys\n"
            f"sys.path.insert(0, r'{PROJECT_ROOT}')\n"
            f"spec = importlib.util.spec_from_file_location('sb_mod', r'{sandbox_file}')\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "print('LOAD_OK')\n"
        )
        try:
            r = subprocess.run([sys.executable, "-c", runner],
                               capture_output=True, text=True, timeout=30,
                               cwd=str(PROJECT_ROOT))
            passed = r.returncode == 0 and "LOAD_OK" in (r.stdout or "")
            err = ""
            if not passed:
                # Last meaningful line of the traceback = the real reason.
                stderr = (r.stderr or "").strip()
                err = stderr.splitlines()[-1] if stderr else "unknown load error"
            return {"name": f"load simulation #{n}", "passed": passed,
                    "output": "module loaded" if passed else "", "error": err}
        except subprocess.TimeoutExpired:
            return {"name": f"load simulation #{n}", "passed": False,
                    "output": "", "error": "timed out (30s) while loading"}
        finally:
            try:
                sandbox_file.unlink(missing_ok=True)
            except Exception:
                pass

    # ─── LLM helpers ──────────────────────────────────────────────────────
    # Preferred code-drafting models, best first. A code-specialised 7B beats a
    # general model of the same size for writing Python. We pick the first one
    # that's actually installed; otherwise fall back to the configured model.
    _CODER_PREFERENCES = ("qwen2.5-coder:7b", "qwen2.5-coder", "deepseek-coder-v2", "codellama")

    def _installed_models(self) -> set[str]:
        try:
            import requests
            r = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            if r.status_code == 200:
                return {m.get("name", "") for m in r.json().get("models", [])}
        except Exception:
            pass
        return set()

    def _model(self) -> str:
        installed = self._installed_models()
        for pref in self._CODER_PREFERENCES:
            # match exact or as a prefix (e.g. "qwen2.5-coder" -> "qwen2.5-coder:7b")
            for name in installed:
                if name == pref or name.startswith(pref):
                    return name
        # Fall back to the configured general model.
        model = "gemma3:4b"
        try:
            cfg = json.loads((Path.home() / ".jarvis_config.json").read_text(encoding="utf-8"))
            model = (cfg.get("ollama") or {}).get("model") or model
        except Exception:
            pass
        return model

    def _draft(self, original: str, instruction: str) -> str:
        # Pull related code from the rest of the repo via the Code Oracle so the
        # model understands dependencies (functions/classes this file uses) —
        # smarter fixes, fewer sandbox failures. Best-effort; needs core/ indexed.
        related = ""
        try:
            from core.code_oracle import get_oracle
            related = get_oracle().context_for(str(PROJECT_ROOT / "core"), instruction, k=3)
        except Exception:
            related = ""

        try:
            import requests
            system = (
                "You are editing a Python file. Return the COMPLETE, updated file "
                "and NOTHING else — no explanations, no markdown fences. Preserve "
                "all existing behaviour except the specific improvement requested. "
                "Keep imports, keep the module importable.")
            prompt = f"IMPROVEMENT REQUESTED: {instruction}\n\n"
            if related:
                prompt += (f"RELATED CODE FROM THE REPO (for context — do not include "
                           f"in output):\n{related[:3000]}\n\n")
            prompt += (f"CURRENT FILE:\n{original}\n\n"
                       f"Return the full updated file:")
            r = requests.post(
                "http://127.0.0.1:11434/api/chat",
                json={"model": self._model(), "stream": False, "keep_alive": "5m",
                      "options": {"temperature": 0.2, "num_predict": 4096},
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": prompt}]},
                timeout=180)
            if r.status_code != 200:
                return ""
            out = (r.json().get("message", {}).get("content") or "").strip()
            # Strip accidental markdown fences.
            if out.startswith("```"):
                out = out.split("\n", 1)[-1]
                if out.rstrip().endswith("```"):
                    out = out.rstrip()[:-3]
            return out.strip()
        except Exception:
            return ""

    def _explain(self, error: str, instruction: str) -> str:
        """Plain-language 'why it failed'. LLM if available, else the raw error."""
        try:
            import requests
            r = requests.post(
                "http://127.0.0.1:11434/api/chat",
                json={"model": self._model(), "stream": False, "keep_alive": "5m",
                      "options": {"temperature": 0.2, "num_predict": 200},
                      "messages": [
                          {"role": "system", "content":
                           "Explain in ONE or TWO plain sentences why this Python "
                           "change failed its test, for the developer. No code."},
                          {"role": "user", "content": f"Error: {error}"}]},
                timeout=45)
            if r.status_code == 200:
                txt = (r.json().get("message", {}).get("content") or "").strip()
                if txt:
                    return txt
        except Exception:
            pass
        return f"The proposed change did not load: {error}"

    def _diff(self, a: str, b: str, filepath: str) -> str:
        d = difflib.unified_diff(a.splitlines(), b.splitlines(),
                                 fromfile=f"a/{filepath}", tofile=f"b/{filepath}",
                                 lineterm="")
        return "\n".join(list(d)[:400])


_proposer: Optional[SelfImprovementProposer] = None


def get_proposer(jarvis=None) -> SelfImprovementProposer:
    global _proposer
    if _proposer is None:
        _proposer = SelfImprovementProposer(jarvis)
    return _proposer
