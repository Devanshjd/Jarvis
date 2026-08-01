"""
J.A.R.V.I.S — Job Application Mode  (find → rank → fill → YOU confirm Submit)

A workflow that sits ON TOP of the gated browser primitives — it plans, it never
bypasses a gate. The one rule that makes it safe to run in your name:

    A field is filled ONLY from a fact in your JobProfile. No fact → it's handed
    back to you (`needs_user`). JARVIS never invents an answer.

So `map_form` is deterministic: match a form field to a canonical profile key,
copy the approved value verbatim, or mark it for you. No model writes values;
credentials and free-text it has no approved answer for always go to you. The
final Submit is not emitted here at all — it stays the console's confirm-gated
step, reviewed by you.
"""
from __future__ import annotations

import re
from typing import Optional

from core.job_profile import JobProfile

# Ordered field → canonical-key heuristics (specific before generic). The KEY
# only selects which approved fact to copy; it never generates a value.
_HEURISTICS = [
    (r"first\s*name|given\s*name|forename", "first_name"),
    (r"last\s*name|surname|family\s*name", "last_name"),
    (r"full\s*name|your\s*name|applicant\s*name|^\s*name\s*$", "full_name"),
    (r"e[-\s]?mail", "email"),
    (r"phone|mobile|telephone|contact\s*number|\btel\b", "phone"),
    (r"linked\s*in", "linkedin"),
    (r"git\s*hub", "github"),
    (r"portfolio|personal\s*site|website|\burl\b", "portfolio"),
    (r"post\s*code|postal\s*code|\bzip\b", "postcode"),
    (r"\bcity\b|\btown\b", "city"),
    (r"\bcountry\b", "country"),
    (r"address|street|\blocation\b", "location"),
    (r"work\s*authoriz|right\s*to\s*work|\bvisa\b|sponsor|work\s*eligib", "work_authorization"),
    (r"salary|compensation|expected\s*pay|desired\s*pay", "salary_expectation"),
    (r"notice\s*period|availability|start\s*date", "notice_period"),
    (r"reloc", "willing_to_relocate"),
    (r"cover\s*letter", "cover_letter_path"),
    (r"resume|\bcv\b", "resume_path"),
]

# Never auto-filled — you enter these yourself.
_CRED_RE = re.compile(r"pass\s?word|passwd|pwd|\botp\b|\bcvv\b|\bcvc\b|card\s*number|"
                      r"\bssn\b|secret|security\s*question", re.I)


def _norm(field: dict) -> str:
    raw = " ".join(str(field.get(k, "")) for k in
                   ("label", "name", "id", "placeholder", "aria_label"))
    return re.sub(r"[-_./#:?\[\]=&]+", " ", raw).lower()


def _match_key(text: str) -> Optional[str]:
    for pat, key in _HEURISTICS:
        if re.search(pat, text):
            return key
    return None


def map_form(fields: list[dict], profile: JobProfile) -> list[dict]:
    """Turn a page's extracted fields into a fill plan. Each entry is either
    `needs_user` (you fill it — no approved fact, or a credential/unknown) or a
    concrete action whose value came verbatim from your profile."""
    plan: list[dict] = []
    for f in fields or []:
        sel = f.get("selector") or f.get("name") or f.get("id") or ""
        label = f.get("label") or f.get("name") or f.get("id") or sel
        typ = (f.get("type") or "").lower()
        tag = (f.get("tag") or "").lower()
        text = _norm(f)

        if typ == "password" or _CRED_RE.search(text):
            plan.append({"selector": sel, "label": label, "needs_user": True,
                         "reason": "credential — you enter this yourself"})
            continue

        key = _match_key(text)
        value = profile.value_for(key) if key else None
        if value is None:
            plan.append({"selector": sel, "label": label, "matched_key": key,
                         "needs_user": True,
                         "reason": ("no approved fact on file — you fill it" if key
                                    else "unrecognised field — you fill it")})
            continue

        if typ == "file" or key in ("resume_path", "cover_letter_path"):
            action = {"action": "upload", "selector": sel, "path": value}
        elif tag == "select":
            action = {"action": "select", "selector": sel, "value": value}
        else:
            action = {"action": "fill", "selector": sel, "text": value}
        plan.append({"selector": sel, "label": label, "matched_key": key,
                     "needs_user": False, "source": f"profile.{key}", "action": action})
    return plan


def to_actions(plan: list[dict]) -> list[dict]:
    """The auto-fillable browser actions (each still runs through the gated
    /step). needs_user fields and the final Submit are deliberately NOT here."""
    return [s["action"] for s in plan if not s.get("needs_user") and s.get("action")]


def summarise(plan: list[dict]) -> dict:
    fill = [s for s in plan if not s.get("needs_user")]
    todo = [s for s in plan if s.get("needs_user")]
    return {"fields": len(plan), "auto_fill": len(fill),
            "needs_user": [{"label": s["label"], "reason": s["reason"]} for s in todo]}


def rank_listings(listings: list[dict], profile: JobProfile) -> list[dict]:
    """Order listings by how well they match your saved preferences. Pure scoring
    — the listings come from a real `extract`, JARVIS doesn't imagine jobs."""
    prefs = profile.data.get("preferences") or {}
    titles = [t.lower() for t in prefs.get("titles", [])]
    locs = [l.lower() for l in prefs.get("locations", [])]
    remote_ok = bool(prefs.get("remote"))
    scored = []
    for it in listings or []:
        title = str(it.get("title", "")).lower()
        loc = str(it.get("location", "")).lower()
        score = sum(3 for kw in titles if kw and kw in title)
        score += sum(2 for kw in locs if kw and kw in loc)
        if remote_ok and "remote" in loc:
            score += 2
        scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    return [{"score": s, **it} for s, it in scored]
