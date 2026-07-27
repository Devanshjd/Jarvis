"""
J.A.R.V.I.S — Code Scanner  (real SAST for ULTRON / FRIDAY)

Static application security testing that finds REAL vulnerabilities with a
proven rule engine instead of letting the LLM guess CWEs. This is the same
lesson the sandbox taught with CVSS: a deterministic tool beats a bigger model.

Engine: **Bandit** — pure-Python, runs natively on Windows/3.13, and Python is
exactly what JARVIS's own code (and most of what FRIDAY touches) is written in.
Semgrep would add multi-language coverage but has no native Windows engine, so
it's left as an optional later hook (`_scan_semgrep`) behind WSL/Docker.

Usage:
    from core.code_scan import scan_python, summary
    findings = scan_python(code="os.system('ping '+host)")
    print(summary(findings))
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CodeFinding:
    tool: str            # "bandit"
    rule: str            # "B605"
    severity: str        # high | medium | low
    cwe: str             # "CWE-78" or ""
    line: int
    message: str
    confidence: str = "" # high | medium | low

    def one_line(self) -> str:
        cwe = f" [{_cwe_name(self.cwe)}]" if self.cwe else ""
        return f"{self.severity.upper():<6} L{self.line}: {self.message}{cwe}  ({self.rule})"


def _cwe_name(cwe: str) -> str:
    """Enrich a bare 'CWE-78' with its canonical name, if the catalogue is
    available. Grounds the taxonomy in data rather than a number alone."""
    try:
        try:
            from core.cwe_lookup import enrich
        except ImportError:
            from cwe_lookup import enrich
        return enrich(cwe)
    except Exception:
        return cwe


_SEV_ORDER = {"high": 3, "medium": 2, "low": 1, "": 0}


def bandit_available() -> bool:
    try:
        r = subprocess.run([sys.executable, "-m", "bandit", "--version"],
                           capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def _parse_bandit(stdout: str) -> list[CodeFinding]:
    findings: list[CodeFinding] = []
    try:
        data = json.loads(stdout or "{}")
    except Exception:
        return findings
    for r in data.get("results", []) or []:
        cwe_id = ((r.get("issue_cwe") or {}).get("id"))
        findings.append(CodeFinding(
            tool="bandit",
            rule=r.get("test_id", "?"),
            severity=(r.get("issue_severity", "") or "").lower(),
            cwe=(f"CWE-{cwe_id}" if cwe_id else ""),
            line=int(r.get("line_number", 0) or 0),
            message=(r.get("issue_text", "") or "").strip().replace("\n", " "),
            confidence=(r.get("issue_confidence", "") or "").lower(),
        ))
    return findings


def scan_python(code: Optional[str] = None, path: Optional[str] = None,
                min_severity: str = "low", timeout: float = 60.0) -> list[CodeFinding]:
    """Scan a Python snippet or a file/dir path with Bandit. Returns findings
    at or above `min_severity`, sorted worst-first. Empty list = clean (or the
    scanner is unavailable — check `bandit_available()` to disambiguate)."""
    if not bandit_available():
        return []

    tmp: Optional[Path] = None
    target: str
    if code is not None:
        tmp = Path(tempfile.gettempdir()) / f"jarvis_scan_{abs(hash(code)) & 0xffffff:x}.py"
        tmp.write_text(code, encoding="utf-8")
        target = str(tmp)
    elif path is not None:
        target = str(Path(path))
    else:
        raise ValueError("scan_python needs either code= or path=")

    cmd = [sys.executable, "-m", "bandit", "-f", "json", "-q"]
    if Path(target).is_dir():
        cmd += ["-r"]
    cmd.append(target)

    try:
        # Bandit exits non-zero when it finds issues — that's not an error.
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        findings = _parse_bandit(r.stdout)
    except Exception:
        findings = []
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except Exception:
                pass

    floor = _SEV_ORDER.get(min_severity.lower(), 1)
    findings = [f for f in findings if _SEV_ORDER.get(f.severity, 0) >= floor]
    findings.sort(key=lambda f: (-_SEV_ORDER.get(f.severity, 0), f.line))
    return findings


def _scan_semgrep(*_a, **_k) -> list[CodeFinding]:  # pragma: no cover
    """Placeholder for multi-language Semgrep coverage. Semgrep has no native
    Windows engine; wire this via WSL or Docker when cross-language scanning is
    needed. Bandit covers Python natively in the meantime."""
    return []


def summary(findings: list[CodeFinding]) -> str:
    if not findings:
        return "No issues found by static analysis (Python/Bandit)."
    by_sev = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    head = (f"{len(findings)} finding(s): "
            f"{by_sev['high']} high, {by_sev['medium']} medium, {by_sev['low']} low")
    lines = "\n".join("  " + f.one_line() for f in findings[:20])
    return head + "\n" + lines


def available() -> dict:
    return {"bandit": bandit_available(), "semgrep": False}


if __name__ == "__main__":
    demo = (
        "import os, hashlib\n"
        "def run(host):\n"
        "    os.system('ping -c 1 ' + host)\n"
        "def q(name):\n"
        "    return \"SELECT * FROM users WHERE n='\" + name + \"'\"\n"
        "SECRET = 'hunter2'\n"
        "def h(x):\n"
        "    return hashlib.md5(x).hexdigest()\n"
    )
    print("scanners available:", available())
    print("-" * 60)
    fs = scan_python(code=demo)
    print(summary(fs))
