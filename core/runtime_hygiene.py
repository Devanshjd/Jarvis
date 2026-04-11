"""
J.A.R.V.I.S - Runtime hygiene helpers

Shared filters that keep secrets, giant prompt payloads, and low-signal junk
out of long-term memory, learning stores, and AI context.
"""

from __future__ import annotations

import re
from typing import Iterable


_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|pass|pwd|token|api[_ -]?key|secret|authorization|cookie|session)\b"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|pass|pwd|token|api[_ -]?key|secret|authorization)\b\s*[:=]?\s*\S+"
)
_SECRET_TOKEN_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{12,}|gsk_[A-Za-z0-9_-]{12,}|AIza[0-9A-Za-z_-]{20,}|"
    r"ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
)
_PROMPT_MARKERS = (
    "you are ",
    "current problem:",
    "goal:",
    "core design principles",
    "output requirement:",
    "important:",
    "this is not",
    "if the result looks like",
)
_LOW_SIGNAL_VALUES = {
    "and", "or", "to", "on", "in", "it", "that", "this", "there", "here",
    "yes", "no", "ok", "okay", "please", "again", "now", "then",
}


def normalize_text(text: str, limit: int = 220) -> str:
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if len(clean) > limit:
        return clean[: limit - 3] + "..."
    return clean


def redact_secrets(text: str) -> str:
    clean = normalize_text(text, limit=max(220, len((text or "").strip()) + 1))
    clean = _SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)} [redacted]", clean)
    clean = _SECRET_TOKEN_RE.sub("[redacted]", clean)
    return clean


def looks_like_secret(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if _SECRET_TOKEN_RE.search(raw):
        return True
    if _SECRET_ASSIGNMENT_RE.search(raw):
        return True
    if len(raw) >= 24 and re.fullmatch(r"[A-Za-z0-9_\-.:/+=]+", raw):
        return True
    return False


def looks_like_prompt_payload(text: str) -> bool:
    clean = normalize_text(text, limit=max(500, len((text or "").strip()) + 1)).lower()
    if not clean:
        return False
    marker_hits = sum(1 for marker in _PROMPT_MARKERS if marker in clean)
    if marker_hits >= 2 and len(clean) > 80:
        return True
    if clean.startswith("you are ") and len(clean) > 140:
        return True
    return False


def sanitize_operator_memory(text: str, limit: int = 180) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if looks_like_secret(raw):
        return None
    if looks_like_prompt_payload(raw):
        return None
    clean = redact_secrets(raw)
    if "[redacted]" in clean and _SECRET_PATTERN.search(clean):
        return None
    clean = normalize_text(clean, limit=limit)
    return clean or None


def filter_operator_memories(memories: Iterable[str], limit: int = 25) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in memories or []:
        safe = sanitize_operator_memory(item)
        if not safe:
            continue
        key = safe.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(safe)
        if len(cleaned) >= limit:
            break
    return cleaned


def sanitize_learning_text(text: str, limit: int = 220, *, allow_prompt: bool = False) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if looks_like_secret(raw):
        return ""
    if not allow_prompt and looks_like_prompt_payload(raw):
        return ""
    clean = normalize_text(redact_secrets(raw), limit=limit)
    if "[redacted]" in clean and _SECRET_PATTERN.search(clean):
        return ""
    return clean


def is_meaningful_learning_value(value, key: str = "") -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        clean = value.strip()
        if not clean or clean == "[redacted]":
            return False
        if looks_like_secret(clean) or looks_like_prompt_payload(clean):
            return False
        if clean.lower() in _LOW_SIGNAL_VALUES:
            return False
        if len(clean) == 1 and not clean.isdigit():
            return False
        if key.lower() in {"contact", "contact_query", "platform", "message"} and clean.lower() in _LOW_SIGNAL_VALUES:
            return False
        return True
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def should_cache_learning(question: str, answer: str) -> bool:
    q = (question or "").strip()
    a = (answer or "").strip()
    if not q or not a:
        return False
    if looks_like_secret(q) or looks_like_secret(a):
        return False
    if looks_like_prompt_payload(q) or looks_like_prompt_payload(a):
        return False
    if len(q) > 320 or len(a) > 1200:
        return False
    return True
