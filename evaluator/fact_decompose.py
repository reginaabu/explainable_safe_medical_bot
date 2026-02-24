"""
evaluator/fact_decompose.py – Atomic fact decomposition.

Strategy
--------
1. NLTK sentence tokenization (downloads punkt_tab on first run).
2. If >1 sentence OR any sentence >30 words → single Claude haiku call
   to further break each sentence into atomic claims.
3. Falls back to NLTK sentences if the API call fails.

Public API
----------
decompose_facts(answer: str) -> list[str]
"""

from __future__ import annotations
import json
import re

import anthropic

_MODEL = "claude-haiku-4-5-20251001"
_CLIENT: anthropic.Anthropic | None = None


def _get_api_key() -> str | None:
    import os
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    from pathlib import Path
    for candidate in [
        Path(__file__).parent / ".streamlit" / "secrets.toml",
        Path(__file__).parent.parent / ".streamlit" / "secrets.toml",
    ]:
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("ANTHROPIC_API_KEY"):
                    return line.partition("=")[2].strip().strip("\"'")
    return None


def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        key = _get_api_key()
        _CLIENT = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    return _CLIENT


def _nltk_sentences(text: str) -> list[str]:
    """Return sentences via NLTK, downloading punkt_tab if needed."""
    try:
        import nltk
        try:
            return nltk.sent_tokenize(text)
        except LookupError:
            nltk.download("punkt_tab", quiet=True)
            return nltk.sent_tokenize(text)
    except Exception:
        # Hard fallback: split on ". "
        return [s.strip() for s in text.split(". ") if s.strip()]


def decompose_facts(answer: str) -> list[str]:
    """
    Decompose *answer* into a flat list of atomic claim strings.

    Returns
    -------
    list[str]  – each element is one indivisible factual claim.
    """
    sentences = _nltk_sentences(answer)

    # Decide whether we need the LLM pass
    needs_llm = len(sentences) > 1 or any(
        len(s.split()) > 30 for s in sentences
    )

    if not needs_llm:
        return [s for s in sentences if s.strip()]

    # ── LLM atomic decomposition ──────────────────────────────────────────────
    prompt = (
        "Decompose the following medical text into a JSON array of atomic "
        "factual claims. Each claim must be a single, self-contained sentence "
        "that asserts exactly one fact. Output ONLY the JSON array with no "
        "additional commentary.\n\n"
        f"Text:\n{answer}"
    )

    try:
        resp = _get_client().messages.create(
            model=_MODEL,
            max_tokens=600,
            system="You are a precise medical fact extractor. Output valid JSON only.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text

        # Guard against preamble before the JSON array
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return sentences

        raw_facts = json.loads(m.group())
        # Handle both plain strings and {"claim": "...", ...} dicts
        result: list[str] = []
        for f in raw_facts:
            if isinstance(f, str) and f.strip():
                result.append(f.strip())
            elif isinstance(f, dict):
                # Extract text from common LLM-returned keys
                for key in ("claim", "fact", "statement", "text"):
                    val = f.get(key, "")
                    if isinstance(val, str) and val.strip():
                        result.append(val.strip())
                        break
        return result

    except Exception:
        # Graceful degradation: return NLTK sentences
        return [s for s in sentences if s.strip()]
