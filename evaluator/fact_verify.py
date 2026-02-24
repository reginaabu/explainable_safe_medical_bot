"""
evaluator/fact_verify.py – LLM-based fact verification using Claude haiku.

Each fact is classified as:
    "supported"     – evidence clearly backs the claim
    "unsupported"   – evidence does not mention or address the claim
    "contradicted"  – evidence explicitly contradicts the claim

A single batched API call is used regardless of fact count (up to 12 facts
× 3 chunks, each chunk truncated to 800 chars).

Public API
----------
verify_facts(facts: list[str], chunks: list[dict]) -> list[dict]
    Returns [{"fact": str, "verdict": str, "pmid": str|None}]
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

_MAX_FACTS = 12
_MAX_CHUNKS = 3
_CHUNK_CHARS = 800


def verify_facts(facts: list[str], chunks: list[dict]) -> list[dict]:
    """
    Verify each fact against the provided evidence chunks.

    Parameters
    ----------
    facts  : list of atomic claim strings (from decompose_facts)
    chunks : list of {"pubid": str, "text": str}

    Returns
    -------
    list[dict] – same length as *facts*, each entry:
        {"fact": str, "verdict": "supported"|"unsupported"|"contradicted", "pmid": str|None}
    """
    if not facts:
        return []

    # Truncate inputs
    limited_facts = facts[:_MAX_FACTS]
    limited_chunks = chunks[:_MAX_CHUNKS]

    # Build evidence block
    evidence_block = "\n\n".join(
        f"[PMID {c['pubid']}]\n{c['text'][:_CHUNK_CHARS]}"
        for c in limited_chunks
    )

    # Build numbered facts block
    facts_block = "\n".join(
        f"{i + 1}. {f}" for i, f in enumerate(limited_facts)
    )

    prompt = (
        "You will be given a list of numbered medical claims and a set of "
        "evidence passages from PubMed abstracts.\n\n"
        "For each claim, output a JSON array where each element has:\n"
        '  "fact": the original claim text\n'
        '  "verdict": one of "supported", "unsupported", or "contradicted"\n'
        '  "pmid": the PMID string of the supporting/contradicting passage, '
        "or null if unsupported\n\n"
        "Rules:\n"
        "- Use ONLY the evidence provided; do not use any prior knowledge.\n"
        "- 'supported': the evidence explicitly or strongly implies the claim.\n"
        "- 'contradicted': the evidence explicitly disagrees with the claim.\n"
        "- 'unsupported': the evidence does not address the claim.\n"
        "- Output ONLY the JSON array with no additional text.\n\n"
        f"Claims:\n{facts_block}\n\n"
        f"Evidence:\n{evidence_block}"
    )

    try:
        resp = _get_client().messages.create(
            model=_MODEL,
            max_tokens=800,
            system=(
                "You are a rigorous medical fact checker. "
                "Output valid JSON only. "
                "Use ONLY the evidence provided; do not use any prior knowledge."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text

        # Guard against preamble before the JSON array
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            raise ValueError("No JSON array found in response")

        verdicts: list[dict] = json.loads(m.group())

        # Normalise and validate each entry
        valid_verdicts = {"supported", "unsupported", "contradicted"}
        result: list[dict] = []
        for i, entry in enumerate(verdicts[:len(limited_facts)]):
            fact_text = limited_facts[i] if i < len(limited_facts) else ""
            verdict = entry.get("verdict", "unsupported").lower()
            if verdict not in valid_verdicts:
                verdict = "unsupported"
            pmid = entry.get("pmid")
            if pmid is not None:
                pmid = str(pmid)
            result.append({"fact": fact_text, "verdict": verdict, "pmid": pmid})

        # Pad to match input length if LLM returned fewer entries
        while len(result) < len(limited_facts):
            result.append({
                "fact": limited_facts[len(result)],
                "verdict": "unsupported",
                "pmid": None,
            })

    except Exception:
        # Graceful degradation: mark everything unsupported
        result = [
            {"fact": f, "verdict": "unsupported", "pmid": None}
            for f in limited_facts
        ]

    # If caller passed more than _MAX_FACTS, pad the rest as unsupported
    for extra_fact in facts[_MAX_FACTS:]:
        result.append({"fact": extra_fact, "verdict": "unsupported", "pmid": None})

    return result
