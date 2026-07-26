"""
J.A.R.V.I.S — CVSS 3.1 base-score calculator + CWE map.

Standalone (no internal imports) so both core.bug_bounty and core.vuln_hunter
can use it without circular imports. Implements the official CVSS v3.1 base
score equations so reports carry a real, defensible severity — the number
triagers on HackerOne/Intigriti expect to see.

Reference: FIRST CVSS v3.1 specification, section 7.1 (Base score equations).
"""
from __future__ import annotations

import math
from typing import Tuple

# ─── Metric weights (CVSS v3.1 spec, table in section 7.4) ───────────────────
_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.20}
_AC = {"L": 0.77, "H": 0.44}
_UI = {"N": 0.85, "R": 0.62}
_CIA = {"N": 0.0, "L": 0.22, "H": 0.56}
# Privileges Required depends on Scope (changed vs unchanged).
_PR_U = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_C = {"N": 0.85, "L": 0.68, "H": 0.50}


def _roundup(x: float) -> float:
    """CVSS v3.1 roundup: round up to the nearest 0.1 (spec Appendix A)."""
    int_input = round(x * 100000)
    if int_input % 10000 == 0:
        return int_input / 100000.0
    return (math.floor(int_input / 10000) + 1) / 10.0


def severity_of(score: float) -> str:
    """Qualitative severity rating for a base score (spec section 5)."""
    if score <= 0.0:
        return "none"
    if score < 4.0:
        return "low"
    if score < 7.0:
        return "medium"
    if score < 9.0:
        return "high"
    return "critical"


def parse_vector(vector: str) -> dict:
    """Parse a 'AV:N/AC:L/...' vector into {metric: value}. Ignores the
    optional 'CVSS:3.1/' prefix and any temporal/environmental metrics."""
    out = {}
    for part in vector.strip().split("/"):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        out[k.strip().upper()] = v.strip().upper()
    return out


def score(vector: str) -> Tuple[float, str, str]:
    """Compute (base_score, severity, normalised_vector) from a CVSS v3.1
    base vector. Missing metrics fall back to a conservative default so a
    partial vector still yields a usable number.

    Example:
        >>> score("AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N")
        (7.5, 'high', 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N')
    """
    m = parse_vector(vector)
    av = _AV.get(m.get("AV", "N"), 0.85)
    ac = _AC.get(m.get("AC", "L"), 0.77)
    ui = _UI.get(m.get("UI", "N"), 0.85)
    scope_changed = m.get("S", "U") == "C"
    pr_table = _PR_C if scope_changed else _PR_U
    pr = pr_table.get(m.get("PR", "N"), 0.85)
    c = _CIA.get(m.get("C", "N"), 0.0)
    i = _CIA.get(m.get("I", "N"), 0.0)
    a = _CIA.get(m.get("A", "N"), 0.0)

    iss = 1 - (1 - c) * (1 - i) * (1 - a)
    if scope_changed:
        impact = 7.52 * (iss - 0.029) - 3.25 * ((iss - 0.02) ** 15)
    else:
        impact = 6.42 * iss
    exploitability = 8.22 * av * ac * pr * ui

    if impact <= 0:
        base = 0.0
    elif scope_changed:
        base = _roundup(min(1.08 * (impact + exploitability), 10.0))
    else:
        base = _roundup(min(impact + exploitability, 10.0))

    norm = ("CVSS:3.1/AV:{AV}/AC:{AC}/PR:{PR}/UI:{UI}/S:{S}/C:{C}/I:{I}/A:{A}"
            .format(AV=m.get("AV", "N"), AC=m.get("AC", "L"), PR=m.get("PR", "N"),
                    UI=m.get("UI", "N"), S=m.get("S", "U"), C=m.get("C", "N"),
                    I=m.get("I", "N"), A=m.get("A", "N")))
    return base, severity_of(base), norm


# ─── Per-bug-class presets: CVSS vector + CWE + one-line remediation ──────────
# Starting points a human tunes to the actual finding. Vectors reflect the
# *typical* case; adjust C/I/A and PR to your real impact before submitting.
BUG_TYPES = {
    "idor": {
        "name": "Insecure Direct Object Reference (IDOR)",
        "cwe": ("CWE-639", "Authorization Bypass Through User-Controlled Key"),
        "vector": "AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
        "remediation": "Enforce object-level authorization server-side: verify the "
                       "authenticated user owns or may access every referenced object; "
                       "use unguessable identifiers as defence in depth, not as the control.",
    },
    "access-control": {
        "name": "Broken Access Control / Missing Function-Level Authorization",
        "cwe": ("CWE-284", "Improper Access Control"),
        "vector": "AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N",
        "remediation": "Deny by default and enforce role/permission checks on every "
                       "privileged endpoint server-side, not only in the UI.",
    },
    "ssrf": {
        "name": "Server-Side Request Forgery (SSRF)",
        "cwe": ("CWE-918", "Server-Side Request Forgery"),
        "vector": "AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:L/A:N",
        "remediation": "Validate and allow-list outbound destinations; block internal "
                       "ranges and cloud metadata IPs; resolve and pin hostnames.",
    },
    "open-redirect": {
        "name": "Open Redirect",
        "cwe": ("CWE-601", "URL Redirection to Untrusted Site"),
        "vector": "AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:N/A:N",
        "remediation": "Allow-list redirect targets or use relative paths only; never "
                       "redirect to a raw user-supplied absolute URL.",
    },
    "cors": {
        "name": "CORS Misconfiguration",
        "cwe": ("CWE-942", "Permissive Cross-domain Policy with Untrusted Domains"),
        "vector": "AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:N/A:N",
        "remediation": "Reflect only an explicit allow-list of trusted origins; never "
                       "combine a reflected/wildcard origin with credentials.",
    },
    "info-disclosure": {
        "name": "Sensitive Information Disclosure",
        "cwe": ("CWE-200", "Exposure of Sensitive Information to an Unauthorized Actor"),
        "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
        "remediation": "Remove the exposed resource from the web root, rotate any leaked "
                       "secrets, and block access to VCS/config/backup paths at the edge.",
    },
    "subdomain-takeover": {
        "name": "Subdomain Takeover",
        "cwe": ("CWE-350", "Reliance on Reverse DNS Resolution for a Security-Critical Action"),
        "vector": "AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:N",
        "remediation": "Remove the dangling DNS record or reclaim the referenced service; "
                       "audit CNAMEs pointing to de-provisioned providers.",
    },
    "xss-reflected": {
        "name": "Reflected Cross-Site Scripting (XSS)",
        "cwe": ("CWE-79", "Improper Neutralization of Input During Web Page Generation"),
        "vector": "AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N",
        "remediation": "Context-aware output encoding; a strict Content-Security-Policy "
                       "as defence in depth.",
    },
    "xss-stored": {
        "name": "Stored Cross-Site Scripting (XSS)",
        "cwe": ("CWE-79", "Improper Neutralization of Input During Web Page Generation"),
        "vector": "AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:L/A:N",
        "remediation": "Encode on output in every rendering context; validate/sanitise "
                       "on input; apply a strict CSP.",
    },
    "sqli": {
        "name": "SQL Injection",
        "cwe": ("CWE-89", "Improper Neutralization of Special Elements in an SQL Command"),
        "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "remediation": "Use parameterised queries / prepared statements exclusively; "
                       "never build SQL by string concatenation.",
    },
    "auth-bypass": {
        "name": "Authentication Bypass",
        "cwe": ("CWE-287", "Improper Authentication"),
        "vector": "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
        "remediation": "Enforce authentication on every protected route server-side; "
                       "validate session/token integrity and expiry.",
    },
}


def bug_type(key: str) -> dict:
    """Look up a preset by key (case/spacing-insensitive), or return a generic
    'medium' template if unknown so the report still renders."""
    k = (key or "").strip().lower().replace(" ", "-").replace("_", "-")
    if k in BUG_TYPES:
        return dict(BUG_TYPES[k])
    return {
        "name": key or "Security Vulnerability",
        "cwe": ("CWE-0", "Unclassified"),
        "vector": "AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:N",
        "remediation": "<describe the fix: enforce the missing control at the server>",
    }
