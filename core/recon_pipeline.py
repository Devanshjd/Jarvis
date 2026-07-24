"""
J.A.R.V.I.S — Recon Pipeline (local, scope-gated)

Semi-autonomous recon for AUTHORISED bug-bounty testing. JARVIS orchestrates
the standard tools a human hunter already uses, then triages the noise with
the local LLM. It does NOT replace your judgement — it clears the busywork.

Pipeline:
    root domain
      → subfinder   (enumerate subdomains)
      → [SCOPE FILTER]  ← every host must pass the program's in-scope check
      → httpx       (which subdomains are live)
      → nuclei      (known-CVE / misconfig templates, capped severity)
      → LLM triage  (dedupe, rank, summarise)  ← local Ollama
      → ranked findings you VERIFY and submit

Hard safety rules (non-negotiable, enforced in code):
  1. A target is only scanned if the root domain is explicitly IN-SCOPE for a
     tracked program (core.bug_bounty). Unknown/out-of-scope → refused.
  2. Every enumerated host is re-checked against scope before it is scanned.
     Out-of-scope hosts are dropped, never touched.
  3. Fully local — no cloud, no data leaves the machine.

This is legal ONLY against programs that authorise testing, on in-scope assets.
Scanning anything else is a crime; the scope gate exists to stop that.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from core.bug_bounty import get_tracker

SCAN_DIR = Path.home() / ".jarvis" / "bug_bounty" / "scans"

# Tool registry: name → (purpose, install hint)
TOOLS = {
    "subfinder": ("subdomain enumeration", "go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"),
    "httpx":     ("live-host probing",     "go install github.com/projectdiscovery/httpx/cmd/httpx@latest"),
    "nuclei":    ("known-vuln templates",  "go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"),
    "nmap":      ("port/service scan",     "https://nmap.org/download (installer)"),
}

# Extra dirs where go-installed binaries commonly live (Windows + *nix).
EXTRA_BINDIRS = [
    Path.home() / "go" / "bin",
    Path.home() / ".local" / "bin",
    Path("/usr/local/bin"),
]


def _which(tool: str) -> Optional[str]:
    p = shutil.which(tool)
    if p:
        return p
    for d in EXTRA_BINDIRS:
        for name in (tool, tool + ".exe"):
            cand = d / name
            if cand.exists():
                return str(cand)
    return None


def detect_tools() -> dict:
    """Return {tool: {installed, path, purpose, install}} for each known tool."""
    out = {}
    for name, (purpose, install) in TOOLS.items():
        path = _which(name)
        out[name] = {"installed": bool(path), "path": path,
                     "purpose": purpose, "install": install}
    return out


def tools_report() -> str:
    d = detect_tools()
    lines = ["Recon tool status:", ""]
    for name, info in d.items():
        mark = "✅" if info["installed"] else "❌"
        lines.append(f"  {mark} {name:10s} — {info['purpose']}")
        if not info["installed"]:
            lines.append(f"       install: {info['install']}")
    core = ["subfinder", "httpx", "nuclei"]
    core_ready = all(d[n]["installed"] for n in core)
    if core_ready:
        lines += ["", "Core pipeline ready — run: /bounty scan <target_id> <root-domain>"]
        if not d["nmap"]["installed"]:
            lines += ["(nmap is optional — install only if you want port scanning.)"]
    else:
        lines += ["", "Install the missing ProjectDiscovery tools above (they're "
                  "single binaries — drop them in ~/go/bin), then re-check."]
    return "\n".join(lines)


def _run(cmd: list[str], timeout: int, stdin_text: str = "") -> tuple[bool, str]:
    """Run a subprocess, return (ok, stdout). Never raises."""
    try:
        r = subprocess.run(cmd, input=stdin_text, capture_output=True,
                           text=True, timeout=timeout)
        return (r.returncode == 0 or bool(r.stdout)), (r.stdout or "")
    except FileNotFoundError:
        return False, "__NOT_INSTALLED__"
    except subprocess.TimeoutExpired:
        return False, "__TIMEOUT__"
    except Exception as e:  # noqa: BLE001
        return False, f"__ERROR__ {e}"


class ReconPipeline:
    def __init__(self, jarvis=None):
        self.jarvis = jarvis
        self.bounty = get_tracker(jarvis)
        SCAN_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Scope gate ───────────────────────────────────────────────────────
    def _scope_ok(self, target_id: str, host: str) -> bool:
        """True ONLY if the host clearly matches recorded in-scope (not None)."""
        return self.bounty.in_scope(target_id, host) is True

    # ─── Stages ───────────────────────────────────────────────────────────
    def _subdomains(self, tools: dict, root: str) -> list[str]:
        if not tools["subfinder"]["installed"]:
            return [root]
        ok, out = _run([tools["subfinder"]["path"], "-silent", "-d", root], timeout=180)
        subs = [l.strip() for l in out.splitlines() if l.strip()] if ok else []
        return subs or [root]

    def _live_hosts(self, tools: dict, hosts: list[str]) -> list[str]:
        if not tools["httpx"]["installed"] or not hosts:
            return hosts
        ok, out = _run([tools["httpx"]["path"], "-silent"], timeout=180,
                       stdin_text="\n".join(hosts))
        return [l.strip() for l in out.splitlines() if l.strip()] if ok else hosts

    def _nuclei(self, tools: dict, urls: list[str]) -> list[str]:
        if not tools["nuclei"]["installed"] or not urls:
            return []
        # Cap severity to reduce noise; templates are known-vuln checks only.
        ok, out = _run([tools["nuclei"]["path"], "-silent", "-severity",
                        "low,medium,high,critical"], timeout=600,
                       stdin_text="\n".join(urls))
        return [l.strip() for l in out.splitlines() if l.strip()] if ok else []

    # ─── Triage (local LLM) ───────────────────────────────────────────────
    def _triage(self, findings: list[str]) -> str:
        if not findings:
            return "No findings from the scanners."
        raw = "\n".join(findings[:200])
        try:
            import requests
            model = "llama3.2:latest"
            try:
                cfg = json.loads((Path.home() / ".jarvis_config.json").read_text(encoding="utf-8"))
                model = (cfg.get("ollama") or {}).get("model") or model
            except Exception:
                pass
            r = requests.post(
                "http://127.0.0.1:11434/api/chat",
                json={"model": model, "stream": False, "keep_alive": "5m",
                      "options": {"temperature": 0.3, "num_predict": 700},
                      "messages": [
                          {"role": "system", "content":
                           "You triage bug-bounty scanner output for an authorised tester. "
                           "Group duplicates, rank by likely severity/exploitability, and flag "
                           "which findings are worth manual verification vs likely false positives. "
                           "Be concise. Remind the tester to verify before reporting."},
                          {"role": "user", "content": f"Scanner findings:\n{raw}\n\nTriage:"}]},
                timeout=90)
            if r.status_code == 200:
                txt = (r.json().get("message", {}).get("content") or "").strip()
                if txt:
                    return txt
        except Exception:
            pass
        # Fallback: just the de-duped list
        uniq = sorted(set(findings))
        return "Local LLM unavailable — raw de-duped findings:\n" + "\n".join(uniq[:80])

    # ─── Orchestration ────────────────────────────────────────────────────
    def run(self, target_id: str, root_domain: str) -> str:
        t = self.bounty.get(target_id)          # raises if unknown
        root = root_domain.strip().lower().lstrip("*.")

        # GATE 1: root must be in scope.
        if not self._scope_ok(target_id, root):
            return (f"⛔ Refused: '{root}' is not confirmed IN-SCOPE for "
                    f"[{t.id}] {t.program}. Add it first:\n"
                    f"  /bounty scope {t.id} in {root}\n"
                    f"Only scan assets the program authorises — off-scope scanning is illegal.")

        tools = detect_tools()
        if not any(i["installed"] for i in tools.values()):
            return ("No recon tools installed yet, so there's nothing to run.\n\n"
                    + tools_report())

        started = time.time()
        log = [f"Recon run — [{t.id}] {t.program} — root: {root}", ""]

        subs = self._subdomains(tools, root)
        # GATE 2: drop anything not in scope.
        in_scope = [h for h in subs if self._scope_ok(target_id, h)]
        dropped = len(subs) - len(in_scope)
        log.append(f"Subdomains: {len(subs)} found, {len(in_scope)} in-scope"
                   + (f" ({dropped} out-of-scope dropped)" if dropped else ""))
        if not in_scope:
            in_scope = [root] if self._scope_ok(target_id, root) else []
        if not in_scope:
            return "\n".join(log + ["", "Nothing in-scope to scan."])

        live = self._live_hosts(tools, in_scope)
        log.append(f"Live hosts: {len(live)}")

        findings = self._nuclei(tools, live)
        log.append(f"Scanner findings: {len(findings)}")

        triage = self._triage(findings)

        # Persist scan
        stamp = time.strftime("%Y%m%d-%H%M%S")
        (SCAN_DIR / f"{t.id}-{stamp}.json").write_text(
            json.dumps({"target": t.id, "root": root, "subdomains": subs,
                        "in_scope": in_scope, "live": live, "findings": findings,
                        "triage": triage, "elapsed_s": round(time.time() - started)},
                       indent=2, ensure_ascii=False), encoding="utf-8")

        log += ["", "─── TRIAGE (verify before reporting) ───", triage,
                "", f"(scan saved · {round(time.time()-started)}s · "
                f"tools: {', '.join(n for n,i in tools.items() if i['installed']) or 'none'})"]
        return "\n".join(log)


_pipeline: Optional[ReconPipeline] = None


def get_pipeline(jarvis=None) -> ReconPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ReconPipeline(jarvis)
    return _pipeline
