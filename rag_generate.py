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


def _build_system_prompts(id_label: str, source_type: str) -> tuple[str, str]:
    """Return (standard_prompt, strict_prompt) for the given dataset vocabulary."""
    standard = (
        "You are a medical evidence assistant. "
        f"Answer the question based ONLY on the provided {source_type}. "
        "Return plain prose only: no markdown headings, no bullets, and no separate evidence section. "
        "Keep the answer concise, ideally 1-3 sentences. "
        f"Every factual sentence must include an inline source citation as ({id_label} XXXXXXXX). "
        f"Cite sources inline as ({id_label} XXXXXXXX). "
        "If the evidence is insufficient, say so."
    )
    strict = (
        "You are a medical evidence assistant. "
        f"Answer using ONLY facts explicitly stated in the provided {source_type}. "
        "Return plain prose only: no markdown headings, no bullets, and no separate evidence section. "
        "Keep the answer concise, ideally 1-3 sentences. "
        f"Every sentence must be directly traceable to a specific {id_label} — "
        f"if you cannot cite a {id_label} for a claim, omit it entirely. "
        "Be conservative: fewer well-supported claims are better than many unsupported ones. "
        f"Cite sources inline as ({id_label} XXXXXXXX)."
    )
    return standard, strict


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
    id_label: str = "PMID",
    source_type: str = "PubMed abstracts",
) -> str:
    """
    Pass retrieved chunks to Claude and return a grounded answer.

    Parameters
    ----------
    query       : the user's medical question
    chunks      : list of {"pubid": str, "text": str}
    max_tokens  : max tokens in the generated response
    strict      : if True, use conservative prompt requiring every claim to be cited
    id_label    : identifier label used in citations, e.g. "PMID" or "QID"
    source_type : description of evidence type for the prompt, e.g. "PubMed abstracts"

    Returns
    -------
    Claude's answer string with inline source citations.
    """
    context = "\n\n".join(
        f"[{id_label} {c['pubid']}]\n{c['text']}" for c in chunks
    )

    standard, strict_prompt = _build_system_prompts(id_label, source_type)
    system = strict_prompt if strict else standard

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
