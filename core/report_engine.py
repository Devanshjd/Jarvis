"""
Enhanced Security Report Generator for JARVIS.

Professional-grade vulnerability report engine for penetration testing
and bug bounty workflows. Implements CVSS 3.1 base score calculation,
structured finding management, and export to markdown / HackerOne formats.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


# ---------------------------------------------------------------------------
# Finding data model
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """Represents a single security finding / vulnerability."""

    id: str
    title: str
    severity: str                              # critical / high / medium / low / info
    cvss_score: float = 0.0
    cvss_vector: str = ""
    description: str = ""
    affected_url: str = ""
    steps_to_reproduce: List[str] = field(default_factory=list)
    impact: str = ""
    remediation: str = ""
    evidence: List[str] = field(default_factory=list)       # HTTP pairs, screenshots, etc.
    references: List[str] = field(default_factory=list)
    status: str = "open"                                     # open / fixed / accepted
    found_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def severity_color(severity: str) -> str:
    """Return an ANSI colour code for terminal / UI display."""
    colors = {
        "critical": "\033[91m",   # bright red
        "high":     "\033[31m",   # red
        "medium":   "\033[33m",   # yellow
        "low":      "\033[32m",   # green
        "info":     "\033[36m",   # cyan
    }
    reset = "\033[0m"
    code = colors.get(severity.lower(), "")
    return f"{code}{severity.upper()}{reset}"


def severity_to_cvss_range(severity: str) -> tuple:
    """Return the (min, max) CVSS score range for a severity label."""
    ranges = {
        "critical": (9.0, 10.0),
        "high":     (7.0, 8.9),
        "medium":   (4.0, 6.9),
        "low":      (0.1, 3.9),
        "info":     (0.0, 0.0),
    }
    return ranges.get(severity.lower(), (0.0, 0.0))


def severity_from_cvss(score: float) -> str:
    """Derive a severity label from a numeric CVSS score."""
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score >= 0.1:
        return "low"
    return "info"


# ---------------------------------------------------------------------------
# CVSS 3.1 base-score calculator (official FIRST.org formula)
# ---------------------------------------------------------------------------

# Metric value mappings — numbers taken directly from the CVSS v3.1 spec.

_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.20}
_AC = {"L": 0.77, "H": 0.44}
_PR_UNCHANGED = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_CHANGED   = {"N": 0.85, "L": 0.68, "H": 0.50}
_UI = {"N": 0.85, "R": 0.62}
_CIA = {"H": 0.56, "L": 0.22, "N": 0.0}


def _roundup(x: float) -> float:
    """CVSS 'roundup' — round to one decimal, always ceiling."""
    return math.ceil(x * 10) / 10.0


class ReportEngine:
    """Professional penetration-test report generator."""

    def __init__(self):
        self._findings: List[Finding] = []

    # ---- CVSS helpers -----------------------------------------------------

    @staticmethod
    def calculate_cvss(vector_string: str) -> float:
        """
        Calculate CVSS 3.1 base score from a full vector string.

        Example vector:
            CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H  -> 9.8
        """
        parts = {}
        for chunk in vector_string.upper().replace("CVSS:3.1/", "").replace("CVSS:3.0/", "").split("/"):
            if ":" in chunk:
                k, v = chunk.split(":", 1)
                parts[k] = v

        av = _AV.get(parts.get("AV", "N"), 0.85)
        ac = _AC.get(parts.get("AC", "L"), 0.77)
        ui = _UI.get(parts.get("UI", "N"), 0.85)
        scope_changed = parts.get("S", "U") == "C"

        pr_table = _PR_CHANGED if scope_changed else _PR_UNCHANGED
        pr = pr_table.get(parts.get("PR", "N"), 0.85)

        c = _CIA.get(parts.get("C", "N"), 0.0)
        i = _CIA.get(parts.get("I", "N"), 0.0)
        a = _CIA.get(parts.get("A", "N"), 0.0)

        # Impact Sub-Score (ISS)
        iss = 1.0 - ((1.0 - c) * (1.0 - i) * (1.0 - a))

        if iss <= 0:
            return 0.0

        # Exploitability
        exploitability = 8.22 * av * ac * pr * ui

        if scope_changed:
            impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
        else:
            impact = 6.42 * iss

        if impact <= 0:
            return 0.0

        if scope_changed:
            base = min(1.08 * (impact + exploitability), 10.0)
        else:
            base = min(impact + exploitability, 10.0)

        return _roundup(base)

    @staticmethod
    def cvss_from_finding(
        severity: str = "medium",
        attack_vector: str = "network",
        complexity: str = "low",
    ) -> float:
        """
        Generate an approximate CVSS score from simple parameters.
        Useful when a full vector string is not available.
        """
        av_map = {"network": "N", "adjacent": "A", "local": "L", "physical": "P"}
        ac_map = {"low": "L", "high": "H"}
        sev_defaults = {
            "critical": ("N", "N", "U", "H", "H", "H"),
            "high":     ("N", "N", "U", "H", "H", "N"),
            "medium":   ("L", "N", "U", "L", "L", "N"),
            "low":      ("L", "R", "U", "L", "N", "N"),
            "info":     ("N", "R", "U", "N", "N", "N"),
        }
        pr, ui, s, c, i, a = sev_defaults.get(severity.lower(), sev_defaults["medium"])
        av_code = av_map.get(attack_vector.lower(), "N")
        ac_code = ac_map.get(complexity.lower(), "L")

        vector = f"CVSS:3.1/AV:{av_code}/AC:{ac_code}/PR:{pr}/UI:{ui}/S:{s}/C:{c}/I:{i}/A:{a}"
        return ReportEngine.calculate_cvss(vector)

    # ---- Finding formatting -----------------------------------------------

    @staticmethod
    def format_finding(finding: Finding) -> str:
        """Format a single finding with all details as a markdown section."""
        lines: List[str] = []
        lines.append(f"### Finding {finding.id}: {finding.title}\n")
        lines.append(f"| Field | Value |")
        lines.append(f"|-------|-------|")
        lines.append(f"| **Severity** | {finding.severity.upper()} |")
        lines.append(f"| **CVSS Score** | {finding.cvss_score} |")
        if finding.cvss_vector:
            lines.append(f"| **CVSS Vector** | `{finding.cvss_vector}` |")
        lines.append(f"| **Status** | {finding.status.capitalize()} |")
        lines.append(f"| **Found Date** | {finding.found_date} |")
        if finding.affected_url:
            lines.append(f"| **Affected URL/Component** | `{finding.affected_url}` |")
        lines.append("")

        if finding.description:
            lines.append("**Description**\n")
            lines.append(finding.description + "\n")

        if finding.steps_to_reproduce:
            lines.append("**Steps to Reproduce**\n")
            for idx, step in enumerate(finding.steps_to_reproduce, 1):
                lines.append(f"{idx}. {step}")
            lines.append("")

        if finding.impact:
            lines.append("**Impact**\n")
            lines.append(finding.impact + "\n")

        if finding.remediation:
            lines.append("**Remediation**\n")
            lines.append(finding.remediation + "\n")

        if finding.evidence:
            lines.append("**Evidence**\n")
            for ev in finding.evidence:
                lines.append(f"```\n{ev}\n```\n")

        if finding.references:
            lines.append("**References**\n")
            for ref in finding.references:
                lines.append(f"- <{ref}>")
            lines.append("")

        return "\n".join(lines)

    # ---- Full report generation -------------------------------------------

    def generate_report(
        self,
        findings: List[Finding],
        target: str,
        scope: Optional[List[str]] = None,
        format: str = "markdown",
    ) -> str:
        """
        Generate a complete penetration-test report.

        Parameters
        ----------
        findings : list[Finding]
            All findings to include.
        target : str
            Primary target (domain, IP, application name).
        scope : list[str] | None
            List of in-scope URLs / hosts / components.
        format : str
            Output format — currently ``"markdown"`` is supported.

        Returns
        -------
        str
            The rendered report.
        """
        self._findings = sorted(
            findings,
            key=lambda f: SEVERITY_ORDER.get(f.severity.lower(), 99),
        )

        report = self._build_report(target, scope)

        if format == "markdown":
            return self.export_markdown(report)
        return report

    def _build_report(self, target: str, scope: Optional[List[str]]) -> str:
        """Assemble all report sections into a single markdown string."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        counts = self._severity_counts()
        total = len(self._findings)

        sections: List[str] = []

        # Title
        sections.append(f"# Penetration Test Report — {target}\n")
        sections.append(f"**Generated:** {now}  ")
        sections.append(f"**Total findings:** {total}\n")

        # Executive Summary
        sections.append("## Executive Summary\n")
        sections.append(
            f"A security assessment was performed against **{target}**. "
            f"The assessment identified **{total}** finding(s): "
            + ", ".join(f"**{counts.get(s, 0)} {s.capitalize()}**" for s in SEVERITY_ORDER)
            + ".\n"
        )
        if counts.get("critical", 0) or counts.get("high", 0):
            sections.append(
                "> **Immediate action recommended.** Critical and/or high-severity "
                "vulnerabilities were identified that could lead to significant compromise.\n"
            )

        # Scope
        sections.append("## Scope\n")
        if scope:
            for item in scope:
                sections.append(f"- `{item}`")
            sections.append("")
        else:
            sections.append(f"- `{target}` (primary target)\n")

        # Methodology
        sections.append("## Methodology\n")
        sections.append(
            "The assessment followed industry-standard methodologies including "
            "OWASP Testing Guide, PTES, and OSSTMM where applicable. Testing "
            "phases included reconnaissance, enumeration, vulnerability analysis, "
            "exploitation, and reporting.\n"
        )

        # Findings Summary Table
        sections.append("## Findings Summary\n")
        sections.append("| ID | Title | Severity | CVSS | Status |")
        sections.append("|----|-------|----------|------|--------|")
        for f in self._findings:
            sections.append(
                f"| {f.id} | {f.title} | {f.severity.upper()} | {f.cvss_score} | {f.status.capitalize()} |"
            )
        sections.append("")

        # Detailed Findings
        sections.append("## Detailed Findings\n")
        for f in self._findings:
            sections.append(self.format_finding(f))

        # Risk Rating Distribution
        sections.append("## Risk Rating Distribution\n")
        sections.append("| Severity | Count |")
        sections.append("|----------|-------|")
        for sev in SEVERITY_ORDER:
            sections.append(f"| {sev.capitalize()} | {counts.get(sev, 0)} |")
        sections.append("")

        # Recommendations
        sections.append("## Recommendations\n")
        if counts.get("critical", 0):
            sections.append(
                "1. **Immediately** remediate all Critical-severity findings. "
                "These represent direct paths to full system compromise."
            )
        if counts.get("high", 0):
            sections.append(
                "2. Prioritize High-severity findings within the current sprint / release cycle."
            )
        if counts.get("medium", 0):
            sections.append(
                "3. Schedule Medium-severity findings for remediation in the near-term roadmap."
            )
        if counts.get("low", 0) or counts.get("info", 0):
            sections.append(
                "4. Review Low / Informational findings during regular security hygiene passes."
            )
        sections.append(
            "\nConsider implementing a vulnerability management programme to "
            "track findings through to verified remediation.\n"
        )

        # Appendix
        sections.append("## Appendix\n")
        sections.append("### Tools Used\n")
        sections.append("- JARVIS Automated Security Scanner")
        sections.append("- Nmap, Nikto, Nuclei, ffuf (where applicable)")
        sections.append("- Manual testing and verification\n")
        sections.append("### Disclaimer\n")
        sections.append(
            "This report is provided for authorized security testing purposes only. "
            "Findings are point-in-time and do not guarantee the absence of other "
            "vulnerabilities. Re-testing is recommended after remediation.\n"
        )

        return "\n".join(sections)

    # ---- Export helpers ----------------------------------------------------

    @staticmethod
    def export_markdown(report: str) -> str:
        """Return the report as clean markdown (identity for now; hook for post-processing)."""
        return report.strip() + "\n"

    @staticmethod
    def export_hackerone(finding: Finding) -> str:
        """
        Format a single finding in HackerOne-compatible markdown.
        """
        lines: List[str] = []

        lines.append("## Summary\n")
        lines.append(f"{finding.description}\n")

        lines.append("## Severity\n")
        lines.append(f"**{finding.severity.upper()}** (CVSS {finding.cvss_score})")
        if finding.cvss_vector:
            lines.append(f"\nVector: `{finding.cvss_vector}`")
        lines.append("")

        lines.append("## Steps to Reproduce\n")
        if finding.steps_to_reproduce:
            for idx, step in enumerate(finding.steps_to_reproduce, 1):
                lines.append(f"{idx}. {step}")
        else:
            lines.append("_No reproduction steps provided._")
        lines.append("")

        lines.append("## Impact\n")
        lines.append(finding.impact if finding.impact else "_Not specified._")
        lines.append("")

        lines.append("## Supporting Material/References\n")
        if finding.evidence:
            for ev in finding.evidence:
                lines.append(f"```\n{ev}\n```\n")
        if finding.references:
            for ref in finding.references:
                lines.append(f"- {ref}")
        if not finding.evidence and not finding.references:
            lines.append("_None._")
        lines.append("")

        return "\n".join(lines).strip() + "\n"

    # ---- Internal ---------------------------------------------------------

    def _severity_counts(self) -> dict:
        counts = {s: 0 for s in SEVERITY_ORDER}
        for f in self._findings:
            key = f.severity.lower()
            counts[key] = counts.get(key, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Quick smoke-test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    engine = ReportEngine()

    demo_findings = [
        Finding(
            id="VULN-001",
            title="SQL Injection in Login Form",
            severity="critical",
            cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            description="The login endpoint is vulnerable to SQL injection via the `username` parameter.",
            affected_url="https://example.com/api/login",
            steps_to_reproduce=[
                "Navigate to https://example.com/login",
                "Enter `admin' OR '1'='1` in the username field",
                "Submit the form",
                "Observe that authentication is bypassed",
            ],
            impact="Full database access, authentication bypass, potential remote code execution.",
            remediation="Use parameterized queries / prepared statements for all database interactions.",
            references=["https://owasp.org/www-community/attacks/SQL_Injection"],
        ),
        Finding(
            id="VULN-002",
            title="Missing Security Headers",
            severity="low",
            description="Several recommended security headers are absent from HTTP responses.",
            affected_url="https://example.com",
            impact="Reduced defence-in-depth; increases risk from XSS and clickjacking.",
            remediation="Add X-Content-Type-Options, X-Frame-Options, and Content-Security-Policy headers.",
        ),
    ]

    # Auto-calculate CVSS scores
    for f in demo_findings:
        if f.cvss_vector:
            f.cvss_score = engine.calculate_cvss(f.cvss_vector)
        else:
            f.cvss_score = engine.cvss_from_finding(f.severity)

    report = engine.generate_report(demo_findings, "example.com", scope=["https://example.com/*"])
    print(report)

    print("\n" + "=" * 60 + "\n")
    print("HackerOne format for VULN-001:\n")
    print(engine.export_hackerone(demo_findings[0]))
