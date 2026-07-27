"""
J.A.R.V.I.S — CWE Lookup  (deterministic taxonomy for ULTRON)

Grounds ULTRON's vulnerability classification in FACT. The sandbox showed local
models confidently misname CWEs (IDOR called CWE-200, mass assignment called
CWE-94). Bandit gives CWE *numbers*; this gives exact CWE *names* and maps a
vuln description to its canonical CWE — so the taxonomy comes from a table, not
a guess. Same lesson as the CVSS calculator.

Curated from the MITRE CWE catalogue: the ~50 weaknesses that actually show up
in web/app security work (OWASP Top 10 territory). The full catalogue can be
ingested later; this covers the common cases instantly and offline.

    from core.cwe_lookup import describe, search, classify, enrich
    describe(639)             -> "CWE-639: Authorization Bypass Through ... (OWASP A01)"
    classify("this is an idor") -> (639, {...}, score)
    enrich("CWE-78")          -> "CWE-78: OS Command Injection (OWASP A03)"
"""
from __future__ import annotations

import re
from typing import Optional


# id -> {name, owasp, aka:[trigger phrases for classify/search]}
CWE: dict[int, dict] = {
    20:  {"name": "Improper Input Validation", "owasp": "A03", "aka": ["input validation", "unvalidated input"]},
    22:  {"name": "Path Traversal", "owasp": "A01", "aka": ["path traversal", "directory traversal", "../", "lfi", "local file inclusion", "arbitrary file read"]},
    77:  {"name": "Command Injection", "owasp": "A03", "aka": ["command injection"]},
    78:  {"name": "OS Command Injection", "owasp": "A03", "aka": ["os command injection", "os command", "shell injection", "os.system", "subprocess shell", "command inject"]},
    79:  {"name": "Cross-site Scripting (XSS)", "owasp": "A03", "aka": ["xss", "cross-site scripting", "cross site scripting", "stored xss", "reflected xss"]},
    89:  {"name": "SQL Injection", "owasp": "A03", "aka": ["sql injection", "sqli", "sql query"]},
    90:  {"name": "LDAP Injection", "owasp": "A03", "aka": ["ldap injection"]},
    94:  {"name": "Code Injection", "owasp": "A03", "aka": ["code injection", "arbitrary code", "eval injection"]},
    113: {"name": "HTTP Response Splitting", "owasp": "A03", "aka": ["response splitting", "header injection", "crlf injection"]},
    116: {"name": "Improper Encoding or Escaping of Output", "owasp": "A03", "aka": ["output encoding", "improper escaping"]},
    119: {"name": "Improper Restriction of Operations within Bounds of a Memory Buffer", "owasp": "", "aka": ["buffer overflow", "memory corruption"]},
    125: {"name": "Out-of-bounds Read", "owasp": "", "aka": ["out of bounds read", "oob read"]},
    190: {"name": "Integer Overflow or Wraparound", "owasp": "", "aka": ["integer overflow"]},
    200: {"name": "Exposure of Sensitive Information", "owasp": "A01", "aka": ["information disclosure", "data exposure", "sensitive information exposure", "info leak"]},
    209: {"name": "Generation of Error Message Containing Sensitive Information", "owasp": "A05", "aka": ["verbose error", "stack trace", "error message leak"]},
    256: {"name": "Plaintext Storage of a Password", "owasp": "A02", "aka": ["plaintext password", "cleartext password storage"]},
    259: {"name": "Use of Hard-coded Password", "owasp": "A07", "aka": ["hardcoded password", "hard-coded password"]},
    269: {"name": "Improper Privilege Management", "owasp": "A01", "aka": ["privilege management", "improper privilege"]},
    284: {"name": "Improper Access Control", "owasp": "A01", "aka": ["access control", "improper access"]},
    287: {"name": "Improper Authentication", "owasp": "A07", "aka": ["improper authentication", "auth bypass", "authentication bypass"]},
    295: {"name": "Improper Certificate Validation", "owasp": "A07", "aka": ["certificate validation", "cert validation", "tls validation"]},
    306: {"name": "Missing Authentication for Critical Function", "owasp": "A07", "aka": ["missing authentication", "unauthenticated endpoint", "no auth"]},
    307: {"name": "Improper Restriction of Excessive Authentication Attempts", "owasp": "A07", "aka": ["brute force", "no rate limit", "credential stuffing"]},
    311: {"name": "Missing Encryption of Sensitive Data", "owasp": "A02", "aka": ["missing encryption", "unencrypted data"]},
    319: {"name": "Cleartext Transmission of Sensitive Information", "owasp": "A02", "aka": ["cleartext transmission", "http not https", "no tls", "plaintext transmission"]},
    327: {"name": "Use of a Broken or Risky Cryptographic Algorithm", "owasp": "A02", "aka": ["weak crypto", "broken crypto", "md5", "sha1", "weak cipher", "risky algorithm"]},
    328: {"name": "Use of Weak Hash", "owasp": "A02", "aka": ["weak hash", "unsalted hash"]},
    330: {"name": "Use of Insufficiently Random Values", "owasp": "A02", "aka": ["weak random", "insufficient randomness"]},
    338: {"name": "Use of Cryptographically Weak PRNG", "owasp": "A02", "aka": ["weak prng", "insecure random", "predictable random"]},
    347: {"name": "Improper Verification of Cryptographic Signature", "owasp": "A02", "aka": ["signature verification", "jwt alg", "alg confusion", "alg none", "jwt none", "unsigned token"]},
    352: {"name": "Cross-Site Request Forgery (CSRF)", "owasp": "A01", "aka": ["csrf", "cross-site request forgery", "cross site request forgery"]},
    362: {"name": "Race Condition", "owasp": "", "aka": ["race condition", "concurrency bug"]},
    367: {"name": "Time-of-check Time-of-use (TOCTOU) Race Condition", "owasp": "", "aka": ["toctou", "time-of-check", "time of check", "check then use"]},
    400: {"name": "Uncontrolled Resource Consumption", "owasp": "", "aka": ["denial of service", "dos", "resource exhaustion"]},
    416: {"name": "Use After Free", "owasp": "", "aka": ["use after free", "uaf"]},
    434: {"name": "Unrestricted Upload of File with Dangerous Type", "owasp": "A04", "aka": ["file upload", "unrestricted upload", "malicious upload"]},
    476: {"name": "NULL Pointer Dereference", "owasp": "", "aka": ["null pointer", "null deref"]},
    502: {"name": "Deserialization of Untrusted Data", "owasp": "A08", "aka": ["deserialization", "insecure deserialization", "pickle", "unpickle", "unsafe deserialize"]},
    522: {"name": "Insufficiently Protected Credentials", "owasp": "A07", "aka": ["unprotected credentials", "weak credential storage"]},
    601: {"name": "URL Redirection to Untrusted Site (Open Redirect)", "owasp": "A01", "aka": ["open redirect", "url redirection", "unvalidated redirect"]},
    611: {"name": "Improper Restriction of XML External Entity Reference (XXE)", "owasp": "A05", "aka": ["xxe", "xml external entity", "external entity", "doctype file"]},
    639: {"name": "Authorization Bypass Through User-Controlled Key (IDOR)", "owasp": "A01", "aka": ["idor", "insecure direct object reference", "broken object level", "bola", "object reference", "user-controlled key"]},
    643: {"name": "XPath Injection", "owasp": "A03", "aka": ["xpath injection"]},
    732: {"name": "Incorrect Permission Assignment for Critical Resource", "owasp": "A05", "aka": ["incorrect permissions", "world writable", "loose permissions"]},
    770: {"name": "Allocation of Resources Without Limits or Throttling", "owasp": "", "aka": ["no rate limiting", "unbounded allocation"]},
    787: {"name": "Out-of-bounds Write", "owasp": "", "aka": ["out of bounds write", "oob write", "buffer overflow write"]},
    798: {"name": "Use of Hard-coded Credentials", "owasp": "A07", "aka": ["hardcoded credentials", "hard-coded credentials", "hardcoded api key", "hardcoded secret"]},
    862: {"name": "Missing Authorization", "owasp": "A01", "aka": ["missing authorization", "no authorization check"]},
    863: {"name": "Incorrect Authorization", "owasp": "A01", "aka": ["incorrect authorization", "improper authorization"]},
    915: {"name": "Improperly Controlled Modification of Dynamically-Determined Object Attributes (Mass Assignment)", "owasp": "A08", "aka": ["mass assignment", "over-posting", "overposting", "auto-binding", "autobinding", "object injection binding"]},
    918: {"name": "Server-Side Request Forgery (SSRF)", "owasp": "A10", "aka": ["ssrf", "server-side request forgery", "server side request forgery", "metadata endpoint", "169.254.169.254"]},
    1021: {"name": "Improper Restriction of Rendered UI Layers (Clickjacking)", "owasp": "A05", "aka": ["clickjacking", "ui redress", "x-frame-options", "frame-ancestors"]},
    1336: {"name": "Server-Side Template Injection (SSTI)", "owasp": "A03", "aka": ["ssti", "server-side template injection", "template injection", "render_template_string"]},
}


def lookup(cwe_id: int) -> Optional[dict]:
    return CWE.get(int(cwe_id))


def _fmt(cwe_id: int, entry: dict) -> str:
    owasp = f" (OWASP {entry['owasp']})" if entry.get("owasp") else ""
    return f"CWE-{cwe_id}: {entry['name']}{owasp}"


def describe(cwe_id: int) -> str:
    entry = lookup(cwe_id)
    return _fmt(cwe_id, entry) if entry else f"CWE-{cwe_id}: (not in local catalogue)"


def enrich(cwe_str: str) -> str:
    """Turn a bare 'CWE-78' (e.g. from Bandit) into its full name."""
    m = re.search(r"(\d+)", cwe_str or "")
    return describe(int(m.group(1))) if m else (cwe_str or "")


def search(term: str, k: int = 5) -> list[tuple[int, dict]]:
    """Find CWEs whose name/aliases contain the term."""
    t = (term or "").lower().strip()
    if not t:
        return []
    hits: list[tuple[int, int, dict]] = []
    for cid, e in CWE.items():
        score = 0
        if t in e["name"].lower():
            score += 5
        for a in e["aka"]:
            if t == a:
                score += 6
            elif t in a or a in t:
                score += 3
        if score:
            hits.append((score, cid, e))
    hits.sort(key=lambda x: -x[0])
    return [(cid, e) for _s, cid, e in hits[:k]]


def classify(text: str) -> Optional[tuple[int, dict, int]]:
    """Best-match CWE for a free-text vulnerability description. Returns
    (cwe_id, entry, score) or None. Matches on canonical alias phrases so
    'this looks like an IDOR' resolves to CWE-639, not a guess."""
    tl = (text or "").lower()
    if not tl:
        return None
    best: Optional[tuple[int, int, dict]] = None
    for cid, e in CWE.items():
        score = 0
        for a in e["aka"]:
            if a in tl:
                score += 3 + len(a.split())      # longer phrases are stronger signal
        if e["name"].lower() in tl:
            score += 5
        if score and (best is None or score > best[0]):
            best = (score, cid, e)
    if not best:
        return None
    return (best[1], best[2], best[0])


if __name__ == "__main__":
    print("CWE catalogue entries:", len(CWE))
    print("-" * 60)
    for q in ["idor", "ssrf", "xxe", "mass assignment", "os command injection",
              "sql injection", "weak md5 hash", "jwt alg none"]:
        hit = search(q, k=1)
        got = describe(hit[0][0]) if hit else "(no match)"
        print(f"  search {q!r:<24} -> {got}")
    print("-" * 60)
    for desc in [
        "Changing account_id in the URL shows another user's invoice — looks like an IDOR",
        "The server fetches any URL you supply (SSRF) reaching the metadata endpoint",
        "Request binds is_admin=true straight onto the model (mass assignment)",
        "os.system with user input is a command injection",
    ]:
        c = classify(desc)
        got = describe(c[0]) if c else "(unclassified)"
        print(f"  classify -> {got}")
    print("-" * 60)
    print("  enrich Bandit 'CWE-78':", enrich("CWE-78"))
