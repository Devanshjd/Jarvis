"""
J.A.R.V.I.S — Privacy Scrubber  (the gate before anything leaves the box)

Before any text can climb to the cloud rung of the escalation ladder, it passes
through here. Two jobs:

  · redact  — replace PII (emails, IPs, phone numbers, card numbers) with typed
              placeholders so a generic question can still be asked.
  · block   — HARD-STOP on high-severity secrets (private keys, cloud keys, live
              tokens). These are never redacted-and-sent; their presence means
              "do not use the cloud — escalate to the human instead."

Engine: fast, dependency-free regex/heuristics that catch the cases that
actually matter (keys, tokens, credentials, PII). This is the honest MVP — a
richer NLP layer (Microsoft Presidio + spaCy) can enrich name/address detection
later, but it is heavy on Windows and not required to make the gate safe.

    from core.scrubber import scrub, has_hard_secret
    clean, report = scrub("email me at a@b.com from 10.0.0.5")
    if has_hard_secret(text): ...   # refuse the cloud, go to the human
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── HARD secrets — presence blocks the cloud rung entirely ────────────────
_HARD = {
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    "aws_access_key":    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "aws_secret_key":    re.compile(r"\baws_secret_access_key\s*[=:]\s*\S{30,}", re.I),
    "gcp_api_key":       re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    "github_token":      re.compile(r"\bgh[pousr]_[0-9A-Za-z]{20,}\b"),
    "slack_token":       re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    "openai_key":        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "jwt":               re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "generic_secret_kv": re.compile(
        r"\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\s*[=:]\s*['\"]?[^\s'\"]{6,}", re.I),
}

# ── PII — redacted (typed placeholder), still safe to send ────────────────
_PII = {
    "EMAIL":       re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "IPV4":        re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
    "CARD":        re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "PHONE":       re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}(?!\d)"),
}

# IPv4s that are noise, not PII — don't redact these.
_IP_ALLOW = {"127.0.0.1", "0.0.0.0", "255.255.255.255", "169.254.169.254"}


@dataclass
class ScrubReport:
    redactions: dict[str, int] = field(default_factory=dict)   # type -> count
    hard_secrets: list[str] = field(default_factory=list)      # names of blockers
    safe_for_cloud: bool = True

    def summary(self) -> str:
        if self.hard_secrets:
            return "BLOCKED — secrets present: " + ", ".join(sorted(set(self.hard_secrets)))
        if self.redactions:
            return "redacted " + ", ".join(f"{n}×{k}" for k, n in self.redactions.items())
        return "clean — nothing sensitive found"


def _luhn_ok(digits: str) -> bool:
    d = [int(c) for c in digits if c.isdigit()]
    if not (13 <= len(d) <= 16):
        return False
    s, alt = 0, False
    for n in reversed(d):
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        s += n
        alt = not alt
    return s % 10 == 0


def find_hard_secrets(text: str) -> list[str]:
    return [name for name, pat in _HARD.items() if pat.search(text or "")]


def has_hard_secret(text: str) -> bool:
    return bool(find_hard_secrets(text))


def scrub(text: str) -> tuple[str, ScrubReport]:
    """Return (redacted_text, report). If a hard secret is present the report is
    marked NOT safe_for_cloud — the caller must not send it; escalate to a human."""
    report = ScrubReport()
    text = text or ""

    hard = find_hard_secrets(text)
    if hard:
        report.hard_secrets = hard
        report.safe_for_cloud = False
        # Still mask the secret values so nothing leaks even into logs.
        for name, pat in _HARD.items():
            text = pat.sub(f"[REDACTED_{name.upper()}]", text)

    for label, pat in _PII.items():
        def _repl(m: "re.Match") -> str:
            val = m.group(0)
            if label == "IPV4" and val in _IP_ALLOW:
                return val
            if label == "CARD" and not _luhn_ok(val):
                return val   # not a real card number, leave it
            report.redactions[label] = report.redactions.get(label, 0) + 1
            return f"[{label}]"
        text = pat.sub(_repl, text)

    return text, report


if __name__ == "__main__":
    samples = [
        "Ping the box at 10.0.0.42 and email ops@acme.com about the outage.",
        "Here is my key sk-ABCDEF0123456789ABCDEF and AKIAIOSFODNN7EXAMPLE — help.",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEp=...\n-----END RSA PRIVATE KEY-----",
        "Card 4111 1111 1111 1111 declined; call +1 (415) 555-0172.",
        "The server is on 127.0.0.1 and 169.254.169.254 (metadata) — that's fine.",
    ]
    print("=" * 66)
    print(" PRIVACY SCRUBBER")
    print("=" * 66)
    for s in samples:
        clean, rep = scrub(s)
        flag = "  <== HARD BLOCK (go to human)" if not rep.safe_for_cloud else ""
        print(f"\n  in : {s[:70]}")
        print(f"  out: {clean[:70]}")
        print(f"  -> {rep.summary()}{flag}")
