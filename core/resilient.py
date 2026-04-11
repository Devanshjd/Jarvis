"""
J.A.R.V.I.S — Resilient Execution Engine
Never give up. Never stop. Analyze, fix, retry, learn.

When JARVIS hits an error, it doesn't say "something went wrong."
It says "Let me try another approach."

This is the difference between a script and an AI.

Architecture:
    1. Execute task
    2. If error → analyze the error
    3. Generate a fix based on error type
    4. Retry with the fix
    5. If still failing → escalate strategy
    6. If strategy exhausted → spawn a micro-agent to solve it
    7. Log everything → never make the same mistake twice
"""

import os
import re
import sys
import time
import json
import traceback
import subprocess
import threading
import logging
from datetime import datetime
from typing import Optional, Callable, Any
from pathlib import Path

from core.subprocess_utils import run_text

logger = logging.getLogger("jarvis.resilient")


# ═══════════════════════════════════════════════════════════
#  Error Knowledge Base — learn from every failure
# ═══════════════════════════════════════════════════════════

class ErrorKnowledge:
    """
    Persistent database of errors JARVIS has seen and how it fixed them.
    Next time the same error appears → instant fix.
    """

    def __init__(self):
        self._db_path = Path.home() / ".jarvis_error_knowledge.json"
        self._knowledge: dict = self._load()

    def _load(self) -> dict:
        try:
            if self._db_path.exists():
                with open(self._db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"errors": {}, "fixes": {}, "patterns": {}}

    def _save(self):
        try:
            with open(self._db_path, "w", encoding="utf-8") as f:
                json.dump(self._knowledge, f, indent=2)
        except Exception:
            pass

    def record_error(self, error_type: str, error_msg: str, context: str):
        """Record an error we encountered."""
        key = f"{error_type}:{error_msg[:100]}"
        errors = self._knowledge.get("errors", {})
        if key not in errors:
            errors[key] = {
                "count": 0, "first_seen": datetime.now().isoformat(),
                "context": context[:200], "fixed": False, "fix": None,
            }
        errors[key]["count"] = errors[key].get("count", 0) + 1
        errors[key]["last_seen"] = datetime.now().isoformat()
        self._knowledge["errors"] = errors
        self._save()

    def record_fix(self, error_type: str, error_msg: str, fix_description: str,
                   fix_code: str = ""):
        """Record how we fixed an error — never repeat the same mistake."""
        key = f"{error_type}:{error_msg[:100]}"
        fixes = self._knowledge.get("fixes", {})
        fixes[key] = {
            "description": fix_description,
            "code": fix_code[:2000],
            "timestamp": datetime.now().isoformat(),
            "success": True,
        }
        self._knowledge["fixes"] = fixes

        # Mark the error as fixed
        errors = self._knowledge.get("errors", {})
        if key in errors:
            errors[key]["fixed"] = True
            errors[key]["fix"] = fix_description
            self._knowledge["errors"] = errors

        self._save()

    def get_known_fix(self, error_type: str, error_msg: str) -> Optional[dict]:
        """Check if we've seen this error before and know how to fix it."""
        key = f"{error_type}:{error_msg[:100]}"
        fixes = self._knowledge.get("fixes", {})
        if key in fixes:
            return fixes[key]

        # Fuzzy match — check if similar error exists
        for k, v in fixes.items():
            if error_type in k and self._similar(error_msg, k.split(":", 1)[-1]):
                return v
        return None

    def record_pattern(self, pattern_name: str, data: dict):
        """Record a general pattern (e.g., 'Microsoft OAuth uses loginfmt')."""
        patterns = self._knowledge.get("patterns", {})
        patterns[pattern_name] = {**data, "timestamp": datetime.now().isoformat()}
        self._knowledge["patterns"] = patterns
        self._save()

    def get_pattern(self, pattern_name: str) -> Optional[dict]:
        return self._knowledge.get("patterns", {}).get(pattern_name)

    @staticmethod
    def _similar(a: str, b: str, threshold: float = 0.5) -> bool:
        """Quick similarity check."""
        a_words = set(a.lower().split())
        b_words = set(b.lower().split())
        if not a_words or not b_words:
            return False
        overlap = len(a_words & b_words)
        return overlap / max(len(a_words), len(b_words)) > threshold


# ═══════════════════════════════════════════════════════════
#  Error Analyzer — understand what went wrong
# ═══════════════════════════════════════════════════════════

class ErrorAnalyzer:
    """
    Parses Python errors and determines the fix strategy.
    """

    # Error patterns → fix strategies
    FIX_STRATEGIES = {
        # Import errors
        r"ModuleNotFoundError: No module named '(\w+)'": {
            "type": "missing_module",
            "fix": "pip_install",
            "description": "Install missing module: {match}",
        },
        r"ImportError: cannot import name '(\w+)' from '(\S+)'": {
            "type": "import_error",
            "fix": "update_import",
            "description": "Fix import path for {match}",
        },

        # Selenium / browser errors
        r"no such element.*Unable to locate element.*\"(\w+)\"\:\"([^\"]+)\"": {
            "type": "element_not_found",
            "fix": "try_alternate_selectors",
            "description": "Element not found, try alternate selectors",
        },
        r"WebDriverException|SessionNotCreatedException": {
            "type": "webdriver_error",
            "fix": "restart_webdriver",
            "description": "WebDriver session broken, restart",
        },
        r"TimeoutException": {
            "type": "timeout",
            "fix": "increase_wait",
            "description": "Element took too long to appear, increase wait time",
        },

        # Connection errors
        r"ConnectionRefusedError|ConnectionResetError|ConnectionError": {
            "type": "connection_error",
            "fix": "retry_with_backoff",
            "description": "Connection failed, retry with backoff",
        },
        r"URLError|HTTPError|RemoteDisconnected": {
            "type": "network_error",
            "fix": "retry_with_backoff",
            "description": "Network request failed, retry",
        },

        # Encoding errors
        r"UnicodeEncodeError.*'charmap'.*can't encode character": {
            "type": "encoding_error",
            "fix": "fix_encoding",
            "description": "Encoding error — use UTF-8 or strip special chars",
        },
        r"UnicodeDecodeError": {
            "type": "encoding_error",
            "fix": "fix_encoding",
            "description": "Decoding error — specify correct encoding",
        },

        # Attribute / Type errors
        r"AttributeError: '(\w+)' object has no attribute '(\w+)'": {
            "type": "attribute_error",
            "fix": "check_api",
            "description": "Object {match} missing attribute",
        },
        r"TypeError: (\w+)\(\) (got|takes|missing)": {
            "type": "type_error",
            "fix": "fix_arguments",
            "description": "Function called with wrong arguments",
        },
        r"NoneType.*has no attribute": {
            "type": "none_error",
            "fix": "add_none_check",
            "description": "Variable is None — add null check",
        },

        # File errors
        r"FileNotFoundError.*No such file.*'([^']+)'": {
            "type": "file_not_found",
            "fix": "create_or_find_file",
            "description": "File not found: {match}",
        },
        r"PermissionError": {
            "type": "permission_error",
            "fix": "run_elevated",
            "description": "Permission denied — try alternate path or elevation",
        },

        # Syntax errors
        r"SyntaxError": {
            "type": "syntax_error",
            "fix": "fix_syntax",
            "description": "Syntax error in code — needs rewrite",
        },

        # Key / Index errors
        r"KeyError: '?(\w+)'?": {
            "type": "key_error",
            "fix": "use_get_default",
            "description": "Missing key: {match} — use .get() with default",
        },
        r"IndexError": {
            "type": "index_error",
            "fix": "add_bounds_check",
            "description": "Index out of range — add bounds checking",
        },

        # Process / OS errors
        r"subprocess\.TimeoutExpired": {
            "type": "process_timeout",
            "fix": "increase_timeout",
            "description": "Process timed out — increase timeout or use async",
        },
    }

    def analyze(self, error_text: str) -> dict:
        """
        Analyze an error and return fix strategy.

        Returns:
            {
                "error_type": str,
                "fix_strategy": str,
                "description": str,
                "match_groups": tuple,
                "confidence": float,
            }
        """
        for pattern, strategy in self.FIX_STRATEGIES.items():
            match = re.search(pattern, error_text, re.IGNORECASE)
            if match:
                desc = strategy["description"]
                if "{match}" in desc:
                    desc = desc.format(match=match.group(1) if match.groups() else "")

                return {
                    "error_type": strategy["type"],
                    "fix_strategy": strategy["fix"],
                    "description": desc,
                    "match_groups": match.groups(),
                    "confidence": 0.9,
                }

        # Unknown error — needs AI analysis
        return {
            "error_type": "unknown",
            "fix_strategy": "ai_analyze",
            "description": f"Unknown error — needs AI analysis",
            "match_groups": (),
            "confidence": 0.3,
        }

    def extract_error_info(self, error_text: str) -> dict:
        """Extract structured info from a Python traceback."""
        info = {
            "error_class": "",
            "error_message": "",
            "file": "",
            "line": 0,
            "function": "",
            "code_line": "",
        }

        # Extract error class and message
        err_match = re.search(r"(\w+Error|\w+Exception): (.+?)$", error_text, re.MULTILINE)
        if err_match:
            info["error_class"] = err_match.group(1)
            info["error_message"] = err_match.group(2).strip()

        # Extract file and line number
        file_match = re.search(r'File "([^"]+)", line (\d+), in (\w+)', error_text)
        if file_match:
            info["file"] = file_match.group(1)
            info["line"] = int(file_match.group(2))
            info["function"] = file_match.group(3)

        return info


# ═══════════════════════════════════════════════════════════
#  Auto-Fixer — generate code fixes for common errors
# ═══════════════════════════════════════════════════════════

class AutoFixer:
    """
    Generates code fixes based on error analysis.
    Each fix strategy has a corresponding implementation.
    """

    def __init__(self, app):
        self.app = app

    def apply_fix(self, code: str, error_text: str, analysis: dict) -> Optional[str]:
        """
        Try to fix the code based on error analysis.
        Returns fixed code or None if can't fix.
        """
        strategy = analysis.get("fix_strategy", "")
        groups = analysis.get("match_groups", ())

        fixer = getattr(self, f"_fix_{strategy}", None)
        if fixer:
            return fixer(code, error_text, groups)
        return None

    def _fix_pip_install(self, code: str, error: str, groups: tuple) -> Optional[str]:
        """Install missing module and return code unchanged."""
        if groups:
            module = groups[0]
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", module],
                    capture_output=True, timeout=60,
                )
                logger.info("Auto-installed module: %s", module)
                return code  # Return same code — it should work now
            except Exception:
                pass
        return None

    def _fix_encoding(self, code: str, error: str, groups: tuple) -> Optional[str]:
        """Fix encoding issues — replace problematic chars or set UTF-8."""
        # Replace common problematic characters
        replacements = {
            "✓": "[OK]", "✗": "[X]", "●": "*", "○": "o",
            "→": "->", "←": "<-", "↓": "v", "↑": "^",
            "—": "--", "–": "-", "'": "'", "'": "'",
            """: '"', """: '"', "…": "...",
            "☕": "", "🛡️": "", "⚡": "", "💾": "",
            "🔋": "", "💿": "", "🔍": "", "📋": "",
            "🌙": "", "☰": "",
        }
        fixed = code
        for old, new in replacements.items():
            fixed = fixed.replace(old, new)

        # Also wrap print statements with encoding handling
        if "print(" in fixed:
            # Add encoding fix at top
            encoding_fix = (
                "import sys, io\n"
                "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')\n"
            )
            if encoding_fix not in fixed:
                fixed = encoding_fix + fixed

        return fixed

    def _fix_try_alternate_selectors(self, code: str, error: str,
                                      groups: tuple) -> Optional[str]:
        """When a web element isn't found, try different selectors."""
        # This needs AI assistance — return None to escalate
        return None

    def _fix_restart_webdriver(self, code: str, error: str,
                                groups: tuple) -> Optional[str]:
        """Add WebDriver restart logic."""
        restart_block = """
# Auto-fix: restart WebDriver
try:
    driver.quit()
except:
    pass
import time
time.sleep(2)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
options = Options()
options.add_experimental_option("detach", True)
driver = webdriver.Chrome(options=options)
"""
        # Insert before the first driver.get() call
        get_match = re.search(r"(driver\.get\(.+?\))", code)
        if get_match:
            return code.replace(get_match.group(0),
                              restart_block + "\n" + get_match.group(0))
        return None

    def _fix_increase_wait(self, code: str, error: str,
                            groups: tuple) -> Optional[str]:
        """Increase wait times in Selenium code."""
        # Double all explicit waits
        fixed = re.sub(r"WebDriverWait\(driver,\s*(\d+)\)",
                       lambda m: f"WebDriverWait(driver, {int(m.group(1)) * 2})",
                       code)
        # Double all sleep times
        fixed = re.sub(r"time\.sleep\((\d+)\)",
                       lambda m: f"time.sleep({int(m.group(1)) * 2})",
                       fixed)
        return fixed if fixed != code else None

    def _fix_retry_with_backoff(self, code: str, error: str,
                                 groups: tuple) -> Optional[str]:
        """Wrap network operations in retry logic."""
        wrapper = '''
import time

def _retry(func, max_retries=3, backoff=2):
    """Retry with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = backoff ** attempt
            print(f"Attempt {attempt+1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)

'''
        if "_retry" not in code:
            return wrapper + code
        return None

    def _fix_add_none_check(self, code: str, error: str,
                             groups: tuple) -> Optional[str]:
        """Add None checks before attribute access."""
        # Find the line that caused the error
        match = re.search(r'File "[^"]+", line (\d+)', error)
        if match:
            line_num = int(match.group(1))
            lines = code.split("\n")
            if 0 < line_num <= len(lines):
                line = lines[line_num - 1]
                # Add a None check
                indent = len(line) - len(line.lstrip())
                spaces = " " * indent
                lines.insert(line_num - 1,
                           f"{spaces}if {line.strip().split('.')[0].strip()} is None:\n"
                           f"{spaces}    print('Warning: variable is None')\n"
                           f"{spaces}    pass\n{spaces}else:")
                return "\n".join(lines)
        return None

    def _fix_use_get_default(self, code: str, error: str,
                              groups: tuple) -> Optional[str]:
        """Replace dict[key] with dict.get(key, default)."""
        if groups:
            key = groups[0]
            # Replace [key] with .get(key, None)
            fixed = code.replace(f'["{key}"]', f'.get("{key}", None)')
            fixed = fixed.replace(f"['{key}']", f".get('{key}', None)")
            if fixed != code:
                return fixed
        return None

    def _fix_increase_timeout(self, code: str, error: str,
                               groups: tuple) -> Optional[str]:
        """Increase subprocess timeouts."""
        fixed = re.sub(r"timeout=(\d+)",
                       lambda m: f"timeout={int(m.group(1)) * 3}",
                       code)
        return fixed if fixed != code else None


# ═══════════════════════════════════════════════════════════
#  Resilient Executor — the never-give-up engine
# ═══════════════════════════════════════════════════════════

class ResilientExecutor:
    """
    Wraps any execution with automatic error recovery.

    Flow:
    1. Try to execute
    2. If error → analyze it
    3. Check knowledge base for known fix
    4. If known fix → apply and retry
    5. If unknown → try auto-fix strategies
    6. If auto-fix fails → ask AI to rewrite the code
    7. If AI fix fails → spawn a micro-agent
    8. Record everything for next time

    Max retries: 5 (configurable)
    """

    def __init__(self, app):
        self.app = app
        self.knowledge = ErrorKnowledge()
        self.analyzer = ErrorAnalyzer()
        self.fixer = AutoFixer(app)
        self.max_retries = 5
        self._active_retries: dict[str, int] = {}

    def execute_code(self, code: str, description: str = "",
                     on_success: Callable = None,
                     on_final_failure: Callable = None,
                     attempt: int = 0) -> dict:
        """
        Execute Python code with full resilience.

        Returns:
            {
                "success": bool,
                "output": str,
                "attempts": int,
                "fixes_applied": list[str],
            }
        """
        fixes_applied = []
        current_code = code

        for attempt_num in range(attempt, self.max_retries):
            result = self._run_code(current_code)

            if result["success"]:
                # Success — record if we applied fixes
                if fixes_applied:
                    logger.info("Succeeded after %d fix(es): %s",
                               len(fixes_applied), ", ".join(fixes_applied))
                    # Record the successful fix for future reference
                    self.knowledge.record_fix(
                        "execution", description,
                        f"Fixed with: {', '.join(fixes_applied)}",
                        current_code,
                    )

                if on_success:
                    on_success(result)

                return {
                    "success": True,
                    "output": result["output"],
                    "attempts": attempt_num + 1,
                    "fixes_applied": fixes_applied,
                    "final_code": current_code,
                }

            # ── Error occurred — start fixing ──
            error_text = result["error"]
            logger.info("Attempt %d failed: %s", attempt_num + 1,
                       error_text[:200])

            # 1. Analyze the error
            analysis = self.analyzer.analyze(error_text)
            error_info = self.analyzer.extract_error_info(error_text)

            # Record the error
            self.knowledge.record_error(
                analysis["error_type"], error_text[:200], description,
            )

            # 2. Check knowledge base for known fix
            known_fix = self.knowledge.get_known_fix(
                analysis["error_type"], error_text[:200],
            )
            if known_fix and known_fix.get("code"):
                logger.info("Applying known fix: %s", known_fix["description"])
                current_code = known_fix["code"]
                fixes_applied.append(f"known_fix:{known_fix['description']}")
                continue

            # 3. Try auto-fix
            fixed_code = self.fixer.apply_fix(current_code, error_text, analysis)
            if fixed_code and fixed_code != current_code:
                logger.info("Auto-fix applied: %s", analysis["description"])
                current_code = fixed_code
                fixes_applied.append(f"auto_fix:{analysis['description']}")
                continue

            # 4. Ask AI to fix the code
            if attempt_num < self.max_retries - 1:
                ai_fixed = self._ai_fix(current_code, error_text, analysis)
                if ai_fixed and ai_fixed != current_code:
                    logger.info("AI fix applied for: %s", analysis["error_type"])
                    current_code = ai_fixed
                    fixes_applied.append(f"ai_fix:{analysis['error_type']}")
                    continue

            # 5. If we're on the last attempt, try spawning a micro-agent
            if attempt_num == self.max_retries - 2:
                agent_result = self._spawn_fix_agent(
                    current_code, error_text, analysis, description,
                )
                if agent_result:
                    current_code = agent_result
                    fixes_applied.append("agent_fix")
                    continue

        # All attempts exhausted
        if on_final_failure:
            on_final_failure(f"Failed after {self.max_retries} attempts. "
                           f"Fixes tried: {', '.join(fixes_applied) or 'none'}")

        return {
            "success": False,
            "output": result.get("error", "Unknown error"),
            "attempts": self.max_retries,
            "fixes_applied": fixes_applied,
            "final_code": current_code,
        }

    def execute_tool(self, tool_func: Callable, tool_args: dict,
                     tool_name: str = "") -> dict:
        """
        Execute a tool function with resilience.
        Retries on failure with modified arguments.
        """
        last_error = ""

        for attempt in range(self.max_retries):
            try:
                result = tool_func(tool_args)
                if hasattr(result, 'success') and result.success:
                    return {"success": True, "result": result, "attempts": attempt + 1}
                elif hasattr(result, 'error') and result.error:
                    last_error = result.error
                    # Analyze and try to fix
                    analysis = self.analyzer.analyze(last_error)
                    logger.info("Tool %s attempt %d failed: %s",
                               tool_name, attempt + 1, analysis["description"])

                    # Try modifying arguments based on error
                    modified_args = self._modify_tool_args(
                        tool_args, last_error, analysis,
                    )
                    if modified_args != tool_args:
                        tool_args = modified_args
                        continue
                else:
                    return {"success": True, "result": result, "attempts": attempt + 1}

            except Exception as e:
                last_error = str(e)
                logger.error("Tool %s exception: %s", tool_name, e)

            time.sleep(0.5 * (attempt + 1))  # Brief backoff

        return {
            "success": False,
            "error": last_error,
            "attempts": self.max_retries,
        }

    # ══════════════════════════════════════════════════════════
    # INTERNAL — Code execution
    # ══════════════════════════════════════════════════════════

    def _run_code(self, code: str) -> dict:
        """Run Python code in a subprocess."""
        try:
            # Write to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                             delete=False, encoding="utf-8") as f:
                f.write(code)
                temp_path = f.name

            result = run_text(
                [sys.executable, temp_path],
                capture_output=True, timeout=30,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

            os.unlink(temp_path)

            if result.returncode == 0:
                return {"success": True, "output": result.stdout[:3000]}
            else:
                return {
                    "success": False,
                    "error": result.stderr[:3000] or result.stdout[:3000],
                    "output": result.stdout[:1000],
                }

        except subprocess.TimeoutExpired:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            return {"success": False, "error": "Execution timed out (30s limit)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ══════════════════════════════════════════════════════════
    # AI-POWERED FIX
    # ══════════════════════════════════════════════════════════

    def _ai_fix(self, code: str, error: str, analysis: dict) -> Optional[str]:
        """Ask the AI provider to fix the code."""
        try:
            brain = self.app.brain

            fix_prompt = (
                "You are a Python debugging expert. Fix this code.\n\n"
                f"ERROR:\n{error[:500]}\n\n"
                f"ERROR TYPE: {analysis['error_type']}\n"
                f"FIX HINT: {analysis['description']}\n\n"
                f"CODE:\n```python\n{code}\n```\n\n"
                "Return ONLY the fixed Python code. No explanation. No markdown fences. "
                "Just the working code."
            )

            reply, _ = brain._chat_with_fallback(
                messages=[{"role": "user", "content": fix_prompt}],
                system_prompt="You are a code fixer. Return only fixed Python code. Nothing else.",
                max_tokens=4096,
            )

            # Clean the response
            fixed = reply.strip()
            # Remove markdown fences if present
            if fixed.startswith("```"):
                lines = fixed.split("\n")
                fixed = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            # Verify it's valid Python
            try:
                compile(fixed, "<ai_fix>", "exec")
                return fixed
            except SyntaxError:
                return None

        except Exception as e:
            logger.error("AI fix failed: %s", e)
            return None

    # ══════════════════════════════════════════════════════════
    # MICRO-AGENT SPAWNING
    # ══════════════════════════════════════════════════════════

    def _spawn_fix_agent(self, code: str, error: str, analysis: dict,
                          description: str) -> Optional[str]:
        """
        Spawn a micro-agent to solve a specific problem.
        The agent gets the full context and can write new code from scratch.
        """
        try:
            brain = self.app.brain

            agent_prompt = (
                "You are an autonomous debugging agent for JARVIS AI system.\n"
                "A task has failed multiple times. Your job is to write a COMPLETELY "
                "new solution from scratch that avoids the error entirely.\n\n"
                f"TASK: {description}\n\n"
                f"ORIGINAL CODE:\n```python\n{code[:2000]}\n```\n\n"
                f"ERROR (occurred multiple times):\n{error[:500]}\n\n"
                f"ERROR ANALYSIS: {analysis['description']}\n\n"
                "INSTRUCTIONS:\n"
                "1. Do NOT just patch the existing code — rethink the approach\n"
                "2. Use alternative libraries or methods if needed\n"
                "3. Add proper error handling\n"
                "4. Add retry logic where appropriate\n"
                "5. Handle edge cases the original code missed\n"
                "6. Return ONLY the complete working Python code\n"
                "7. No explanations, no markdown — just the code"
            )

            reply, _ = brain._chat_with_fallback(
                messages=[{"role": "user", "content": agent_prompt}],
                system_prompt=(
                    "You are a specialist debugging agent. Return only working Python code. "
                    "Your code must handle errors gracefully and never crash."
                ),
                max_tokens=4096,
            )

            # Clean response
            fixed = reply.strip()
            if fixed.startswith("```"):
                lines = fixed.split("\n")
                fixed = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            try:
                compile(fixed, "<agent_fix>", "exec")
                logger.info("Micro-agent produced valid fix")
                return fixed
            except SyntaxError:
                return None

        except Exception as e:
            logger.error("Micro-agent failed: %s", e)
            return None

    # ══════════════════════════════════════════════════════════
    # TOOL ARGUMENT MODIFICATION
    # ══════════════════════════════════════════════════════════

    def _modify_tool_args(self, args: dict, error: str,
                           analysis: dict) -> dict:
        """Try to fix tool arguments based on error."""
        modified = dict(args)
        error_type = analysis.get("error_type", "")

        if error_type == "element_not_found":
            # For Selenium — the micro-agent approach is better
            pass

        if error_type == "connection_error":
            # Add retry flag
            modified["_retry"] = True

        if error_type == "timeout":
            # Double any timeout values
            for key in ["timeout", "wait", "delay"]:
                if key in modified:
                    modified[key] = modified[key] * 2

        return modified

    # ══════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════

    def get_error_stats(self) -> dict:
        """Stats about errors encountered and fixed."""
        errors = self.knowledge._knowledge.get("errors", {})
        fixes = self.knowledge._knowledge.get("fixes", {})
        total_errors = len(errors)
        total_fixed = sum(1 for e in errors.values() if e.get("fixed"))
        recurring = sum(1 for e in errors.values() if e.get("count", 0) > 1)

        return {
            "total_errors_seen": total_errors,
            "total_fixed": total_fixed,
            "fix_rate": f"{(total_fixed/total_errors*100):.0f}%" if total_errors else "N/A",
            "known_fixes": len(fixes),
            "recurring_errors": recurring,
        }
