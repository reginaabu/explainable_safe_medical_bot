"""
evaluator/safety.py – Regex-based safety checker (no API calls).

Public API
----------
check_safety(answer: str) -> dict
    Returns {"is_safe": bool, "flags": list[str], "answer_with_disclaimer": str}
"""

from __future__ import annotations
import re

# ── Disclaimers ────────────────────────────────────────────────────────────────
_DISCLAIMER = (
    "\n\n---\n"
    "_This information is for educational purposes only and does not constitute "
    "medical advice. Always consult a qualified healthcare professional before "
    "making any medical decisions._"
)

_EMERGENCY_DISCLAIMER = (
    "\n\n> **If you or someone else is experiencing a medical emergency, "
    "call 911 (or your local emergency number) immediately.**"
)

# ── Pattern groups ─────────────────────────────────────────────────────────────
_EMERGENCY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("call_911",        re.compile(r"\bcall\s+911\b", re.I)),
    ("ambulance",       re.compile(r"\bambulance\b", re.I)),
    ("suicidal",        re.compile(
        r"\b(suicid(al|e)|want(ing)?\s+to\s+(die|kill\s+myself)|self[\s-]?harm)\b",
        re.I,
    )),
    ("overdose",        re.compile(r"\boverdos(e|ing)\b", re.I)),
    ("severe_bleeding", re.compile(r"\b(severe|uncontrolled|profuse)\s+bleeding\b", re.I)),
    ("unconscious",     re.compile(
        r"\b(loss\s+of\s+consciousness|unconscious(ness)?|passed?\s+out)\b",
        re.I,
    )),
]

_DIAGNOSIS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("you_have",          re.compile(r"\byou\s+have\b", re.I)),
    ("your_diagnosis",    re.compile(r"\byour\s+diagnosis\s+is\b", re.I)),
    ("your_test_shows",   re.compile(r"\byour\s+test\s+(shows?|results?)\b", re.I)),
]

_PRESCRIPTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("dosage_instruction", re.compile(r"\btake\s+\d+\s*mg\b", re.I)),
    ("prescribe",          re.compile(r"\bprescribe[sd]?\b", re.I)),
    ("inject",             re.compile(r"\binject(ion|ed|ing)?\b", re.I)),
    ("drug_take",          re.compile(
        # named drug immediately followed by "take" within ~8 words
        r"\b(aspirin|ibuprofen|metformin|warfarin|lisinopril|atorvastatin|"
        r"simvastatin|omeprazole|amoxicillin|prednisone)\b.{0,50}\btake\b",
        re.I | re.DOTALL,
    )),
]


def check_safety(answer: str) -> dict:
    """
    Scan *answer* for unsafe language patterns.

    Returns
    -------
    {
        "is_safe"              : bool,
        "flags"                : list[str],
        "answer_with_disclaimer": str,
    }

    ``is_safe=False`` when any pattern fires; the answer is still returned
    (with an injected disclaimer) so callers can choose whether to display it.
    """
    flags: list[str] = []
    emergency_hit = False

    for flag_name, pattern in _EMERGENCY_PATTERNS:
        if pattern.search(answer):
            flags.append(f"EMERGENCY:{flag_name}")
            emergency_hit = True

    for flag_name, pattern in _DIAGNOSIS_PATTERNS:
        if pattern.search(answer):
            flags.append(f"DIAGNOSIS:{flag_name}")

    for flag_name, pattern in _PRESCRIPTION_PATTERNS:
        if pattern.search(answer):
            flags.append(f"PRESCRIPTION:{flag_name}")

    is_safe = len(flags) == 0

    # Build annotated answer
    annotated = answer
    if emergency_hit:
        annotated = _EMERGENCY_DISCLAIMER + "\n\n" + annotated
    annotated += _DISCLAIMER

    return {
        "is_safe": is_safe,
        "flags": flags,
        "answer_with_disclaimer": annotated,
    }
