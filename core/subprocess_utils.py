"""
Helpers for subprocess execution that stay stable on Windows.

The default `text=True` path in subprocess uses the active code page and can
raise UnicodeDecodeError when child processes emit bytes outside that mapping.
JARVIS spawns a lot of background commands, so we capture bytes and decode
safely instead of letting reader threads crash.
"""

from __future__ import annotations

import locale
import os
import subprocess
from typing import Iterable


def safe_decode(data: bytes | str | None, extra_encodings: Iterable[str] | None = None) -> str:
    """Decode subprocess output without raising UnicodeDecodeError."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data

    candidates: list[str] = []
    if extra_encodings:
        candidates.extend([enc for enc in extra_encodings if enc])

    preferred = locale.getpreferredencoding(False)
    candidates.extend([
        "utf-8",
        "utf-8-sig",
        preferred,
        "cp65001",
        "mbcs",
        "cp1252",
        "latin-1",
    ])

    seen: set[str] = set()
    for encoding in candidates:
        key = encoding.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue

    return data.decode("utf-8", errors="replace")


def run_text(*popenargs, timeout: float | None = None, **kwargs) -> subprocess.CompletedProcess:
    """
    Run a subprocess and always return text stdout/stderr safely.

    This intentionally avoids subprocess's own text decoding path on Windows.
    """
    run_kwargs = dict(kwargs)
    run_kwargs.pop("text", None)
    run_kwargs.pop("encoding", None)
    run_kwargs.pop("errors", None)

    env = dict(os.environ)
    env.update(run_kwargs.pop("env", {}) or {})
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    run_kwargs["env"] = env

    result = subprocess.run(*popenargs, timeout=timeout, **run_kwargs)
    result.stdout = safe_decode(result.stdout)
    result.stderr = safe_decode(result.stderr)
    return result
