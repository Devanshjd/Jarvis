"""
J.A.R.V.I.S — Multi-Step Task Chain Engine
Autonomous sequential execution of complex multi-step tasks.

Designed for security workflows like:
  recon -> find subdomains -> fuzz each -> test XSS -> log findings -> report

Each chain is a directed graph of steps that pass context forward.
"""

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("jarvis.chain_engine")

# ── Persistence directory ───────────────────────────────────────
CHAINS_DIR = Path.home() / ".jarvis_chains"
CHAINS_DIR.mkdir(parents=True, exist_ok=True)


# ── Data Models ─────────────────────────────────────────────────

@dataclass
class ChainStep:
    """A single step in a task chain."""
    step_id: str
    tool_name: str
    tool_args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"          # pending | running | done | failed | skipped
    result: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2


@dataclass
class TaskChain:
    """A full multi-step task chain."""
    chain_id: str
    name: str
    steps: list[ChainStep] = field(default_factory=list)
    status: str = "pending"          # pending | running | done | aborted | failed
    created_at: str = ""
    results: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


# ── Serialization helpers ───────────────────────────────────────

def _chain_to_dict(chain: TaskChain) -> dict:
    """Convert a TaskChain to a JSON-safe dict."""
    return {
        "chain_id": chain.chain_id,
        "name": chain.name,
        "status": chain.status,
        "created_at": chain.created_at,
        "results": chain.results,
        "steps": [
            {
                "step_id": s.step_id,
                "tool_name": s.tool_name,
                "tool_args": s.tool_args,
                "depends_on": s.depends_on,
                "status": s.status,
                "result": s.result,
                "retry_count": s.retry_count,
            }
            for s in chain.steps
        ],
    }


def _save_chain(chain: TaskChain):
    """Persist chain state to disk."""
    path = CHAINS_DIR / f"{chain.chain_id}.json"
    try:
        path.write_text(json.dumps(_chain_to_dict(chain), indent=2), encoding="utf-8")
    except Exception as e:
        log.error("Failed to save chain %s: %s", chain.chain_id, e)


def _load_chain(chain_id: str) -> Optional[dict]:
    """Load a chain from disk."""
    path = CHAINS_DIR / f"{chain_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ── Target Extraction ───────────────────────────────────────────

def _extract_targets(text: str, kind: str = "urls") -> list[str]:
    """Extract targets from tool output for feeding into the next step.

    Supports extracting subdomains, URLs, IPs, and generic hostnames.
    """
    if not text:
        return []

    text = str(text)

    if kind == "subdomains":
        # Match domain-like patterns
        pattern = r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}'
        found = re.findall(pattern, text)
        # Filter out noise
        return list(dict.fromkeys(
            d for d in found
            if len(d) > 4 and not d.endswith(('.png', '.jpg', '.css', '.js'))
        ))

    if kind == "urls":
        pattern = r'https?://[^\s<>"\')\]}]+'
        return list(dict.fromkeys(re.findall(pattern, text)))

    if kind == "ips":
        pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        return list(dict.fromkeys(re.findall(pattern, text)))

    return []


# ── Chain Engine ────────────────────────────────────────────────

class ChainEngine:
    """
    Executes multi-step task chains through JARVIS's tool executor.

    Usage:
        engine = ChainEngine(jarvis)
        chain = engine.full_pentest_chain("example.com")
        engine.execute_chain(chain, progress_cb=print)
    """

    def __init__(self, jarvis):
        self.jarvis = jarvis
        self._chains: dict[str, TaskChain] = {}
        self._abort_flags: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # ── Chain Creation ──────────────────────────────────────

    def create_chain(self, name: str, steps: list[dict]) -> TaskChain:
        """Create a new TaskChain from a list of step definitions.

        Each step dict should have: tool_name, tool_args, and optionally
        depends_on (list of step_ids) and step_id.

        Returns the constructed TaskChain (not yet executed).
        """
        chain_id = uuid.uuid4().hex[:12]
        chain_steps = []

        for i, s in enumerate(steps):
            step = ChainStep(
                step_id=s.get("step_id", f"step_{i}"),
                tool_name=s["tool_name"],
                tool_args=s.get("tool_args", {}),
                depends_on=s.get("depends_on", []),
                max_retries=s.get("max_retries", 2),
            )
            chain_steps.append(step)

        chain = TaskChain(
            chain_id=chain_id,
            name=name,
            steps=chain_steps,
        )

        with self._lock:
            self._chains[chain_id] = chain

        _save_chain(chain)
        log.info("Created chain '%s' (%s) with %d steps", name, chain_id, len(chain_steps))
        return chain

    # ── Chain Execution ─────────────────────────────────────

    def execute_chain(
        self,
        chain: TaskChain,
        progress_cb: Optional[Callable[[str], None]] = None,
        done_cb: Optional[Callable[[TaskChain], None]] = None,
        background: bool = True,
    ) -> TaskChain:
        """Execute a chain. Runs in a background thread by default.

        Args:
            chain: The TaskChain to execute.
            progress_cb: Optional callback called with status strings.
            background: If True, runs in a daemon thread and returns immediately.

        Returns:
            The TaskChain (status updates in-place).
        """
        if background:
            t = threading.Thread(
                target=self._run_chain,
                args=(chain, progress_cb, done_cb),
                daemon=True,
                name=f"chain-{chain.chain_id}",
            )
            t.start()
            return chain

        self._run_chain(chain, progress_cb, done_cb)
        return chain

    def _run_chain(
        self,
        chain: TaskChain,
        progress_cb: Optional[Callable],
        done_cb: Optional[Callable[[TaskChain], None]] = None,
    ):
        """Internal: run all steps sequentially, respecting dependencies."""
        abort_event = threading.Event()
        with self._lock:
            self._abort_flags[chain.chain_id] = abort_event

        chain.status = "running"
        _notify(progress_cb, f"[CHAIN] Starting '{chain.name}' ({len(chain.steps)} steps)")

        # Build a context dict that accumulates outputs from each step
        context: dict[str, Any] = {}

        for step in chain.steps:
            if abort_event.is_set():
                step.status = "skipped"
                _notify(progress_cb, f"[CHAIN] Aborted — skipping {step.step_id}")
                continue

            # Check dependency results — skip if any dependency failed
            deps_ok = True
            for dep_id in step.depends_on:
                dep_step = self._find_step(chain, dep_id)
                if dep_step and dep_step.status == "failed":
                    deps_ok = False
                    break

            if not deps_ok:
                step.status = "skipped"
                _notify(progress_cb, f"[CHAIN] Skipping {step.step_id} — dependency failed")
                continue

            # Inject context from dependencies into tool_args
            enriched_args = self._enrich_args(step, context)

            _notify(progress_cb, f"[CHAIN] Step {step.step_id}: {step.tool_name} ...")
            step.status = "running"
            _save_chain(chain)

            result = self._execute_step(step, enriched_args)

            # Store in context for downstream steps
            context[step.step_id] = result
            chain.results[step.step_id] = result

            _save_chain(chain)

            if step.status == "done":
                _notify(progress_cb, f"[CHAIN] Step {step.step_id}: OK")
            else:
                _notify(progress_cb, f"[CHAIN] Step {step.step_id}: FAILED")

        # Final status
        failed = sum(1 for s in chain.steps if s.status == "failed")
        skipped = sum(1 for s in chain.steps if s.status == "skipped")

        if abort_event.is_set():
            chain.status = "aborted"
        elif failed == len(chain.steps):
            chain.status = "failed"
        else:
            chain.status = "done"

        summary = (
            f"[CHAIN] '{chain.name}' finished — "
            f"{len(chain.steps) - failed - skipped} passed, "
            f"{failed} failed, {skipped} skipped"
        )
        _notify(progress_cb, summary)
        _save_chain(chain)

        # Cleanup abort flag
        with self._lock:
            self._abort_flags.pop(chain.chain_id, None)

        if done_cb:
            try:
                done_cb(chain)
            except Exception:
                pass

    def _execute_step(self, step: ChainStep, args: dict) -> Optional[str]:
        """Execute a single step through the JARVIS executor, with retries."""
        executor = self.jarvis.orchestrator.executor
        attempt = 0

        while attempt <= step.max_retries:
            try:
                result = executor.execute(step.tool_name, args)

                if result.success:
                    step.status = "done"
                    step.result = result.output
                    return result.output
                else:
                    attempt += 1
                    step.retry_count = attempt
                    log.warning(
                        "Step %s attempt %d failed: %s",
                        step.step_id, attempt, result.error,
                    )
                    if attempt > step.max_retries:
                        step.status = "failed"
                        step.result = f"ERROR: {result.error}"
                        return step.result

            except Exception as e:
                attempt += 1
                step.retry_count = attempt
                log.error("Step %s exception on attempt %d: %s", step.step_id, attempt, e)
                if attempt > step.max_retries:
                    step.status = "failed"
                    step.result = f"EXCEPTION: {e}"
                    return step.result

            # Brief pause before retry
            time.sleep(1)

        step.status = "failed"
        return step.result

    def _enrich_args(self, step: ChainStep, context: dict) -> dict:
        """Inject outputs from previous steps into the current step's args.

        If a step depends on a previous step, we try to extract useful
        targets (URLs, subdomains, IPs) and merge them into tool_args.
        """
        args = dict(step.tool_args)

        if not step.depends_on:
            return args

        # Gather output from all dependencies
        dep_outputs = []
        for dep_id in step.depends_on:
            output = context.get(dep_id)
            if output and not str(output).startswith(("ERROR:", "EXCEPTION:")):
                dep_outputs.append(str(output))

        if not dep_outputs:
            return args

        combined = "\n".join(dep_outputs)

        # Smart target injection based on tool type
        tool = step.tool_name

        if tool in ("subdomain_enum", "ssl_check", "recon", "google_dorks", "wayback"):
            # These need a domain — try to find one in context
            if not args.get("domain"):
                domains = _extract_targets(combined, "subdomains")
                if domains:
                    args["domain"] = domains[0]

        elif tool in ("tech_detect", "dir_fuzz", "cors_check", "xss_test",
                       "sqli_test", "open_redirect", "header_audit"):
            # These need a URL
            if not args.get("url"):
                urls = _extract_targets(combined, "urls")
                if urls:
                    args["url"] = urls[0]
                else:
                    # Fall back to constructing from subdomains
                    subs = _extract_targets(combined, "subdomains")
                    if subs:
                        args["url"] = f"https://{subs[0]}"

        elif tool in ("port_scan", "threat_lookup"):
            if not args.get("host") and not args.get("ip"):
                ips = _extract_targets(combined, "ips")
                if ips:
                    args.setdefault("host", ips[0])
                    args.setdefault("ip", ips[0])

        # Always attach raw previous output as _context for tools that want it
        args["_context"] = combined

        return args

    def _find_step(self, chain: TaskChain, step_id: str) -> Optional[ChainStep]:
        for s in chain.steps:
            if s.step_id == step_id:
                return s
        return None

    # ── Status & Control ────────────────────────────────────

    def get_chain_status(self, chain_id: str) -> dict:
        """Return current status of a chain."""
        chain = self._chains.get(chain_id)
        if not chain:
            # Try loading from disk
            data = _load_chain(chain_id)
            if data:
                return data
            return {"error": f"Chain {chain_id} not found"}
        return _chain_to_dict(chain)

    def abort_chain(self, chain_id: str) -> bool:
        """Signal a running chain to stop after the current step."""
        with self._lock:
            event = self._abort_flags.get(chain_id)
            if event:
                event.set()
                log.info("Abort signal sent to chain %s", chain_id)
                return True
        log.warning("Cannot abort chain %s — not running or not found", chain_id)
        return False

    # ── Predefined Templates ────────────────────────────────

    def full_pentest_chain(self, domain: str) -> TaskChain:
        """Full pentest chain: recon -> subdomain -> tech -> ssl -> headers ->
        cors -> dir fuzz -> xss -> sqli."""
        url = f"https://{domain}"
        steps = [
            {
                "step_id": "recon",
                "tool_name": "recon",
                "tool_args": {"domain": domain},
            },
            {
                "step_id": "subdomains",
                "tool_name": "subdomain_enum",
                "tool_args": {"domain": domain},
                "depends_on": ["recon"],
            },
            {
                "step_id": "tech",
                "tool_name": "tech_detect",
                "tool_args": {"url": url},
                "depends_on": ["recon"],
            },
            {
                "step_id": "ssl",
                "tool_name": "ssl_check",
                "tool_args": {"host": domain},
                "depends_on": ["recon"],
            },
            {
                "step_id": "headers",
                "tool_name": "header_audit",
                "tool_args": {"url": url},
                "depends_on": ["tech"],
            },
            {
                "step_id": "cors",
                "tool_name": "cors_check",
                "tool_args": {"url": url},
                "depends_on": ["tech"],
            },
            {
                "step_id": "dirfuzz",
                "tool_name": "dir_fuzz",
                "tool_args": {"url": url},
                "depends_on": ["tech"],
            },
            {
                "step_id": "xss",
                "tool_name": "xss_test",
                "tool_args": {"url": url},
                "depends_on": ["dirfuzz"],
            },
            {
                "step_id": "sqli",
                "tool_name": "sqli_test",
                "tool_args": {"url": url},
                "depends_on": ["dirfuzz"],
            },
        ]
        return self.create_chain(f"Full Pentest: {domain}", steps)

    def quick_recon_chain(self, domain: str) -> TaskChain:
        """Quick recon chain: recon -> subdomains -> tech detect -> ssl check."""
        url = f"https://{domain}"
        steps = [
            {
                "step_id": "recon",
                "tool_name": "recon",
                "tool_args": {"domain": domain},
            },
            {
                "step_id": "subdomains",
                "tool_name": "subdomain_enum",
                "tool_args": {"domain": domain},
                "depends_on": ["recon"],
            },
            {
                "step_id": "tech",
                "tool_name": "tech_detect",
                "tool_args": {"url": url},
                "depends_on": ["recon"],
            },
            {
                "step_id": "ssl",
                "tool_name": "ssl_check",
                "tool_args": {"host": domain},
                "depends_on": ["recon"],
            },
        ]
        return self.create_chain(f"Quick Recon: {domain}", steps)

    def list_templates(self) -> list[dict]:
        """Return metadata about available chain templates."""
        return [
            {
                "name": "full_pentest_chain",
                "description": "Full penetration test — recon, subdomains, tech detect, SSL, headers, CORS, dir fuzz, XSS, SQLi",
                "args": ["domain"],
            },
            {
                "name": "quick_recon_chain",
                "description": "Quick reconnaissance — recon, subdomains, tech detect, SSL check",
                "args": ["domain"],
            },
        ]


# ── Helpers ─────────────────────────────────────────────────────

def _notify(cb: Optional[Callable[[str], None]], msg: str):
    """Send progress message to callback and logger."""
    log.info(msg)
    if cb:
        try:
            cb(msg)
        except Exception:
            pass
