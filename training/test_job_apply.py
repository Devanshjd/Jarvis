"""
Job Application Mode tests — the honesty rails.

The one that matters most: JARVIS NEVER invents an answer. A form field is filled
only from a fact on file; anything else is handed back to you. Also: credentials
are never auto-filled, the profile summary leaks no PII, and ranking is pure
scoring over real listings.

Run:  python training/test_job_apply.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.job_apply import map_form, rank_listings, to_actions
from core.job_profile import JobProfile

_FIELDS = [
    {"label": "Email Address", "type": "email", "selector": "#email"},
    {"label": "Full Name", "selector": "#name"},
    {"label": "Country", "tag": "select", "selector": "#country"},
    {"label": "Upload your CV", "type": "file", "selector": "#cv"},
    {"label": "Expected Salary", "selector": "#sal"},
    {"label": "LinkedIn Profile", "selector": "#li"},
    {"label": "Password", "type": "password", "selector": "#pw"},
    {"label": "Why do you want to work here?", "tag": "textarea", "selector": "#why"},
    {"label": "Portfolio", "selector": "#pf"},          # matched key, but no fact on file
]


def _profile(tmp: Path) -> JobProfile:
    p = JobProfile(tmp / "job_profile.json")
    p.set({
        "identity": {"full_name": "Test User", "first_name": "Test",
                     "email": "test@example.com", "phone": "+44 700 000000",
                     "city": "London", "country": "United Kingdom"},
        "links": {"linkedin": "https://linkedin.com/in/test",
                  "github": "https://github.com/test"},
        "resume_path": "C:/resume.pdf",
        "work_authorization": "UK student visa",
        "approved_answers": {"salary_expectation": "35000", "notice_period": "2 weeks",
                             "willing_to_relocate": "Yes"},
        "preferences": {"titles": ["security analyst", "soc"],
                        "locations": ["london", "remote"], "remote": True},
    })
    p.save()
    return p


def test_profile_round_trip_and_pii_free_summary() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = _profile(Path(d))
        p2 = JobProfile(Path(d) / "job_profile.json")           # reload from disk
        assert p2.value_for("email") == "test@example.com"
        assert p2.value_for("resume_path") == "C:/resume.pdf"
        assert p2.value_for("salary_expectation") == "35000"
        assert p2.value_for("portfolio") is None                # not on file
        summ = p2.summary()
        blob = json.dumps(summ)
        assert "test@example.com" not in blob and "+44" not in blob, \
            "the summary must expose which facts exist, not their PII values"
        # ...and no filesystem path (the home dir leaks the OS username).
        assert "path" not in summ, "summary must not expose the profile file path"
        assert str(p2.path) not in blob and ".jarvis" not in blob, \
            "summary must not leak the profile location"


def test_map_form_fills_only_from_profile() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = _profile(Path(d))
        plan = map_form(_FIELDS, p)
        by_label = {s["label"]: s for s in plan}

        assert by_label["Email Address"]["action"] == {"action": "fill", "selector": "#email", "text": "test@example.com"}
        assert by_label["Full Name"]["action"]["text"] == "Test User"
        assert by_label["Country"]["action"] == {"action": "select", "selector": "#country", "value": "United Kingdom"}
        assert by_label["Upload your CV"]["action"] == {"action": "upload", "selector": "#cv", "path": "C:/resume.pdf"}
        assert by_label["Expected Salary"]["action"]["text"] == "35000"
        assert by_label["LinkedIn Profile"]["action"]["text"] == "https://linkedin.com/in/test"


def test_unknowns_and_credentials_are_handed_back() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = _profile(Path(d))
        by_label = {s["label"]: s for s in map_form(_FIELDS, p)}
        assert by_label["Password"]["needs_user"] is True
        assert by_label["Why do you want to work here?"]["needs_user"] is True
        # matched a key (portfolio) but there's no fact on file → you fill it, NOT invented
        pf = by_label["Portfolio"]
        assert pf["needs_user"] is True and pf.get("matched_key") == "portfolio"
        assert "action" not in pf, "a needs_user field must carry no fill action"


def test_never_fabricates_a_value() -> None:
    """Every auto-filled value must equal a fact actually in the profile."""
    with tempfile.TemporaryDirectory() as d:
        p = _profile(Path(d))
        plan = map_form(_FIELDS, p)
        profile_values = set()
        for grp in ("identity", "links", "approved_answers"):
            profile_values.update(str(v) for v in (p.data.get(grp) or {}).values())
        profile_values.update([p.data.get("resume_path"), p.data.get("work_authorization")])
        for step in plan:
            if step.get("needs_user"):
                continue
            act = step["action"]
            val = act.get("text") or act.get("value") or act.get("path")
            assert val in profile_values, f"fabricated value {val!r} for {step['label']!r}"


def test_ranking_orders_by_preferences() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = _profile(Path(d))
        listings = [
            {"title": "Head Chef", "location": "Paris"},
            {"title": "Security Analyst", "location": "London"},
            {"title": "SOC Engineer", "location": "Remote"},
        ]
        ranked = rank_listings(listings, p)
        assert ranked[0]["title"] in ("Security Analyst", "SOC Engineer")
        assert ranked[-1]["title"] == "Head Chef", "an unrelated job should rank last"


def main() -> None:
    tests = [
        ("profile round-trip + PII-free summary", test_profile_round_trip_and_pii_free_summary),
        ("map_form fills only from profile", test_map_form_fills_only_from_profile),
        ("unknowns + credentials handed back", test_unknowns_and_credentials_are_handed_back),
        ("NEVER fabricates a value", test_never_fabricates_a_value),
        ("ranking orders by preferences", test_ranking_orders_by_preferences),
    ]
    print("=" * 64)
    print(" JOB APPLICATION MODE TESTS")
    print("=" * 64)
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as exc:
            import traceback
            print(f"  [FAIL] {name} -> {exc}")
            traceback.print_exc()
    print(f"\n  {passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    main()
