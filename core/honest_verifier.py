"""
J.A.R.V.I.S — Honest Verifier

Reads the actual contents of specific app windows (Calculator display,
Notepad text, etc.) to verify whether an agent action achieved its goal.

Replaces the whole-screen OCR approach that gave us false positives by
reading my own Claude Code chat history. Each verifier targets a specific
app and reads only that app's content via:
  - pywinauto UI Automation (preferred — reads exact field values)
  - Window-specific screenshot + OCR (fallback when UI Auto fails)

Verification verdicts are honest:
  VERIFIED → can prove the goal was achieved (with evidence)
  FAILED   → can prove the goal was NOT achieved (with evidence)
  UNKNOWN  → can't determine either way (honest uncertainty)

The agent should treat UNKNOWN as "needs user confirmation" — never as
silent success.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger("jarvis.verifier")

try:
    from pywinauto import Application, Desktop
    from pywinauto.findwindows import ElementNotFoundError
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False
    logger.warning("pywinauto not available — honest verification disabled")


class Verdict(Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class VerifyResult:
    verdict: Verdict
    evidence: str          # what was actually read from the app
    expected: str = ""     # what the agent expected
    method: str = ""       # how we read it (ui_automation, ocr, etc.)
    error: str = ""        # if UNKNOWN/FAILED, why

    @property
    def ok(self) -> bool:
        return self.verdict == Verdict.VERIFIED

    def __repr__(self) -> str:
        return (
            f"VerifyResult(verdict={self.verdict.value}, "
            f"expected={self.expected!r}, evidence={self.evidence[:80]!r}, "
            f"method={self.method!r})"
        )


# ─── Per-app verifiers ────────────────────────────────────────────────────


def verify_calculator_display(expected: str) -> VerifyResult:
    """Read Windows Calculator's display value and compare to expected.

    expected is a string like "161" or "25". Spaces and thousands separators
    are normalized away before comparison.
    """
    if not HAS_PYWINAUTO:
        return VerifyResult(Verdict.UNKNOWN, "", expected,
                            method="none", error="pywinauto unavailable")

    expected_norm = re.sub(r"[\s,]", "", str(expected))

    # Win11 Calculator is a UWP app. Use Desktop+UIA to find it reliably.
    try:
        wins = Desktop(backend="uia").windows(title_re=r".*Calculator.*")
        if not wins:
            return VerifyResult(Verdict.UNKNOWN, "", expected,
                                method="Desktop/uia",
                                error="no Calculator window visible")

        for win in wins:
            evidence_chunks = []
            try:
                # Read all descendant Text elements — Calculator's display
                # appears as one of them with content like "Display is 161"
                for d in win.descendants(control_type="Text"):
                    try:
                        t = (d.window_text() or "").strip()
                    except Exception:
                        continue
                    if not t:
                        continue
                    evidence_chunks.append(t)
                    # Normalize and check
                    cleaned = re.sub(r"^Display is\s*", "", t, flags=re.IGNORECASE)
                    cleaned = re.sub(r"[\s,]", "", cleaned)
                    if cleaned == expected_norm:
                        return VerifyResult(Verdict.VERIFIED, t, expected,
                                            method="uia/Text-descendant")
            except Exception as e:
                logger.debug("Calculator descendant read failed: %s", e)

            # Also try the "Display" Group / CalculatorResults AutomationId
            for ident in ("CalculatorResults", "Display", "DisplayContainer"):
                try:
                    elem = win.child_window(auto_id=ident)
                    t = (elem.window_text() or "").strip()
                    if t:
                        evidence_chunks.append(f"{ident}={t}")
                        cleaned = re.sub(r"^Display is\s*", "", t, flags=re.IGNORECASE)
                        cleaned = re.sub(r"[\s,]", "", cleaned)
                        if cleaned == expected_norm:
                            return VerifyResult(Verdict.VERIFIED, t, expected,
                                                method=f"uia/{ident}")
                except Exception:
                    continue

            # We have evidence chunks but didn't find expected → FAILED with evidence
            if evidence_chunks:
                joined = " | ".join(evidence_chunks[:6])
                # Final check: maybe expected appears anywhere in the joined text
                joined_clean = re.sub(r"[\s,]", "", joined)
                if expected_norm in joined_clean:
                    return VerifyResult(Verdict.VERIFIED, joined, expected,
                                        method="uia/joined-evidence")
                return VerifyResult(Verdict.FAILED, joined, expected,
                                    method="uia/exhaustive",
                                    error=f"expected {expected_norm!r} not in Calculator state")

        return VerifyResult(Verdict.UNKNOWN, "", expected,
                            method="uia",
                            error="Calculator open but no readable text content")

    except Exception as e:
        return VerifyResult(Verdict.UNKNOWN, "", expected,
                            method="uia", error=f"verifier error: {e}")


def verify_notepad_text(expected: str) -> VerifyResult:
    """Read Notepad's text content and verify expected substring is present.

    Reads the Edit control directly — exact text, no OCR.
    """
    if not HAS_PYWINAUTO:
        return VerifyResult(Verdict.UNKNOWN, "", expected,
                            method="none", error="pywinauto unavailable")

    candidates = [
        ("uia", {"title_re": r".*Notepad.*"}),
        ("win32", {"title_re": r".*Notepad.*", "class_name": "Notepad"}),
    ]

    for backend, kwargs in candidates:
        try:
            app = Application(backend=backend).connect(**kwargs, timeout=2)
            win = app.window(**kwargs)
            try:
                # Get the Edit control (the main text area)
                if backend == "win32":
                    edit = win.Edit
                    text = edit.window_text()
                else:
                    # UIA: find a child Edit/Document control
                    edit = None
                    for ctl_type in ("Edit", "Document"):
                        try:
                            edit = win.child_window(control_type=ctl_type)
                            text = edit.window_text()
                            if text is not None:
                                break
                        except Exception:
                            continue
                    if edit is None:
                        raise RuntimeError("no Edit/Document control found")

                expected_clean = expected.lower().strip()
                text_clean = (text or "").lower()
                if expected_clean in text_clean:
                    return VerifyResult(Verdict.VERIFIED, text, expected,
                                        method=f"pywinauto/{backend}/Edit")
                else:
                    return VerifyResult(Verdict.FAILED, text, expected,
                                        method=f"pywinauto/{backend}/Edit",
                                        error=f"text {text[:80]!r} doesn't contain {expected!r}")
            except Exception as e:
                logger.debug("Notepad verify control read failed: %s", e)
                continue
        except (ElementNotFoundError, Exception) as e:
            logger.debug("Notepad verify backend %s failed: %s", backend, e)
            continue

    return VerifyResult(Verdict.UNKNOWN, "", expected,
                        method="none", error="could not connect to Notepad window")


def verify_window_exists(title_substring: str) -> VerifyResult:
    """Just check whether a window with the given title substring exists."""
    if not HAS_PYWINAUTO:
        return VerifyResult(Verdict.UNKNOWN, "", title_substring,
                            method="none", error="pywinauto unavailable")
    try:
        wins = Desktop(backend="uia").windows(title_re=f".*{re.escape(title_substring)}.*")
        if wins:
            titles = [w.window_text() for w in wins[:3]]
            return VerifyResult(Verdict.VERIFIED, " | ".join(titles), title_substring,
                                method="pywinauto/Desktop")
        return VerifyResult(Verdict.FAILED, "", title_substring,
                            method="pywinauto/Desktop",
                            error="no matching window")
    except Exception as e:
        return VerifyResult(Verdict.UNKNOWN, "", title_substring,
                            method="pywinauto/Desktop", error=str(e))


# ─── Smart dispatcher: pick verifier from app/expected hints ──────────────


def verify_outcome(
    app_hint: str = "",
    expected_text: str = "",
    expected_number: str = "",
) -> VerifyResult:
    """Dispatch to the right per-app verifier based on hints.

    Use this from agent_loop after each step. Examples:
        verify_outcome(app_hint="calculator", expected_number="161")
        verify_outcome(app_hint="notepad", expected_text="hello jarvis")
        verify_outcome(app_hint="paint")  # just verify window exists
    """
    app = (app_hint or "").lower().strip()

    if "calc" in app and expected_number:
        return verify_calculator_display(expected_number)
    if "notepad" in app and expected_text:
        return verify_notepad_text(expected_text)
    if app:
        return verify_window_exists(app)

    return VerifyResult(Verdict.UNKNOWN, "", expected_text or expected_number,
                        method="none", error="no verifier matched the hints")
