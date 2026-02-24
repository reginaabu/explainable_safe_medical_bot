"""
rag_generate.py – RAG generation layer using Claude (Anthropic API)

Public API
----------
generate_answer(query, chunks, max_tokens) -> str

Requires:
    pip install anthropic>=0.25.0
    ANTHROPIC_API_KEY environment variable set

CLI usage:
    python rag_generate.py "Do statins reduce cardiovascular risk?"
"""

from __future__ import annotations

import anthropic

MODEL  = "claude-sonnet-4-6"
_CLIENT: anthropic.Anthropic | None = None

_STANDARD_SYSTEM = (
    "You are a medical evidence assistant. "
    "Answer the question based ONLY on the provided PubMed abstracts. "
    "Cite sources inline as (PMID XXXXXXXX). "
    "If the evidence is insufficient, say so."
)

_STRICT_SYSTEM = (
    "You are a medical evidence assistant. "
    "Answer using ONLY facts explicitly stated in the provided abstracts. "
    "Every sentence must be directly traceable to a specific PMID — "
    "if you cannot cite a PMID for a claim, omit it entirely. "
    "Be conservative: fewer well-supported claims are better than many unsupported ones. "
    "Cite sources inline as (PMID XXXXXXXX)."
)


def _get_api_key() -> str | None:
    """Read ANTHROPIC_API_KEY from env or .streamlit/secrets.toml."""
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
    """Return a cached Anthropic client (lazy-init so env key is available)."""
    global _CLIENT
    if _CLIENT is None:
        key = _get_api_key()
        _CLIENT = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
    return _CLIENT


def generate_answer(
    query: str,
    chunks: list[dict],
    max_tokens: int = 400,
    strict: bool = False,
) -> str:
    """
    Pass retrieved chunks to Claude and return a grounded answer.

    Parameters
    ----------
    query      : the user's medical question
    chunks     : list of {"pubid": str, "text": str}
    max_tokens : max tokens in the generated response
    strict     : if True, use conservative prompt requiring every claim to cite a PMID

    Returns
    -------
    Claude's answer string, citing PMIDs inline as (PMID XXXXXXXX).
    """
    context = "\n\n".join(
        f"[PMID {c['pubid']}]\n{c['text']}" for c in chunks
    )

    system = _STRICT_SYSTEM if strict else _STANDARD_SYSTEM

    resp = _get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[
            {
                "role": "user",
                "content": f"Question: {query}\n\nEvidence:\n{context}",
            }
        ],
    )
    return resp.content[0].text


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print('Usage: python rag_generate.py "<question>"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    # Load a few example chunks from the local CSV for a quick smoke-test
    subset_csv = Path(__file__).parent / "pubmedqa_subset.csv"
    if not subset_csv.exists():
        print("pubmedqa_subset.csv not found — run track2_build_kg.py first.")
        sys.exit(1)

    import csv
    sample_chunks: list[dict] = []
    with open(subset_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            sample_chunks.append({"pubid": row["doc_id"], "text": row["context"][:600]})
            if i >= 2:
                break

    print(f"Query   : {query}")
    print(f"Model   : {MODEL}")
    print(f"Chunks  : {len(sample_chunks)}")
    print("-" * 60)
    answer = generate_answer(query, sample_chunks)
    print(answer)
