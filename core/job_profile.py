"""
J.A.R.V.I.S — Job Profile  (local, facts-only source of truth for applications)

Job Application Mode fills forms ONLY from what's here, and here holds only what
YOU approved. This is the honesty rail: an application goes out in your name, so
JARVIS must never fabricate an answer (a made-up "5 years of Kubernetes" is worse
than a blank field). If a fact isn't in this profile, the form field is handed
back to you — never guessed.

Privacy: this is PII (name, contact, history). It lives OUTSIDE the repo at
~/.jarvis/job_profile.json (the repo is public), is never logged in full, and is
never sent to the cloud rung (the scrubber would strip it anyway).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_DEFAULT = Path.home() / ".jarvis" / "job_profile.json"

# Canonical fact keys a form field can map to. Values come from the profile only.
_IDENTITY = ("full_name", "first_name", "last_name", "email", "phone",
             "location", "city", "country", "postcode")
_LINKS = ("linkedin", "github", "portfolio", "website")
_FILES = ("resume_path", "cover_letter_path")
_TOP = ("work_authorization",)


class JobProfile:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _DEFAULT
        self.data: dict = {}
        self.load()

    def load(self) -> "JobProfile":
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}
        return self

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        return self.path

    def set(self, data: dict) -> "JobProfile":
        """Replace the profile with a validated shape (unknown top-level keys are
        dropped, so callers can't stuff arbitrary data through)."""
        clean: dict = {}
        clean["identity"] = {k: str(v) for k, v in (data.get("identity") or {}).items()
                             if k in _IDENTITY and v}
        clean["links"] = {k: str(v) for k, v in (data.get("links") or {}).items()
                          if k in _LINKS and v}
        for k in _FILES + _TOP:
            if data.get(k):
                clean[k] = str(data[k])
        clean["approved_answers"] = {str(k): str(v)
                                     for k, v in (data.get("approved_answers") or {}).items() if v}
        clean["preferences"] = data.get("preferences") or {}
        self.data = clean
        return self

    # ── the only way a value ever reaches a form ─────────────────────────
    def value_for(self, key: str) -> Optional[str]:
        """Return the approved fact for a canonical key, or None. None means
        'you fill this' — it is NEVER a signal to invent something."""
        if not key:
            return None
        if key in _IDENTITY:
            return (self.data.get("identity") or {}).get(key) or None
        if key in _LINKS:
            return (self.data.get("links") or {}).get(key) or None
        if key in _FILES or key in _TOP:
            return self.data.get(key) or None
        # Otherwise it's a pre-approved screening answer (salary, notice, etc.)
        return (self.data.get("approved_answers") or {}).get(key) or None

    def is_empty(self) -> bool:
        return not (self.data.get("identity") or self.data.get("links")
                    or self.data.get("approved_answers"))

    def summary(self) -> dict:
        """PII-free view for the UI: WHICH facts are on file, not their values —
        and no filesystem path (the home dir leaks the OS username)."""
        ident = self.data.get("identity") or {}
        return {
            "has_profile": not self.is_empty(),
            "identity_fields": sorted(ident.keys()),
            "links": sorted((self.data.get("links") or {}).keys()),
            "resume": bool(self.data.get("resume_path")),
            "cover_letter": bool(self.data.get("cover_letter_path")),
            "approved_answers": sorted((self.data.get("approved_answers") or {}).keys()),
            "preferences": self.data.get("preferences") or {},
        }
