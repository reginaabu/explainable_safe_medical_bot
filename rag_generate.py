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


def _build_system_prompts(id_label: str, source_type: str, dataset: str = "") -> tuple[str, str]:
    """Return (standard_prompt, strict_prompt) for the given dataset vocabulary."""

    # PubMedQA: yes/no research questions — keep answers to 1–2 sentences so the
    # fact verifier has fewer specific statistical claims to check.  Paraphrased
    # numbers are the main cause of factuality failures on this dataset.
    if dataset == "pubmedqa":
        standard = (
            "You are a medical evidence assistant. "
            f"Answer the question based ONLY on the provided {source_type}. "
            "Rules:\n"
            "1. Restate the key subject of the question in your opening sentence "
            "(e.g., 'This study found that…' or 'The evidence indicates that…').\n"
            "2. Answer in 1–2 sentences maximum: state the conclusion directly "
            "(yes / no / unclear / insufficient evidence) with one brief supporting reason.\n"
            "3. Use ONLY information explicitly stated in the provided evidence. "
            "Do NOT add general medical knowledge not present in the evidence.\n"
            f"4. Cite every factual claim inline as ({id_label} XXXXXXXX).\n"
            "5. Do NOT paraphrase statistics — either quote exact figures from the "
            "evidence or omit them entirely."
        )
        strict = (
            "You are a medical evidence assistant. "
            f"Answer using ONLY facts explicitly stated in the provided {source_type}. "
            "Rules:\n"
            "1. One sentence only: restate the question subject, state the conclusion, "
            f"and cite the source as ({id_label} XXXXXXXX).\n"
            "2. No claims without a direct citation. No paraphrased statistics.\n"
            "3. No general medical knowledge beyond what is in the evidence."
        )
        return standard, strict

    standard = (
        "You are a medical evidence assistant. "
        f"Answer the question based ONLY on the provided {source_type}. "
        "Rules:\n"
        "1. Open with a direct, specific answer to the exact question asked — "
        "restate the key subject of the question in your opening sentence "
        "(e.g., 'The brand names of X are…', 'The symptoms of Y include…', "
        "'The treatment for Z involves…'). "
        "Do not open with background or definitions unless the question asks for them.\n"
        "2. Use ONLY information explicitly stated in the provided evidence. "
        "Do NOT add general medical knowledge, background facts, or context from "
        "your training data that is not present in the evidence.\n"
        "3. Be concise: 3–5 sentences maximum.\n"
        f"4. Cite every factual claim inline as ({id_label} XXXXXXXX).\n"
        "5. If the evidence does not contain enough information to answer, "
        "state only what the evidence does say and note the gap — do not speculate."
    )
    strict = (
        "You are a medical evidence assistant. "
        f"Answer using ONLY facts explicitly stated in the provided {source_type}. "
        "Rules:\n"
        "1. Open with a direct answer to the specific question asked, restating "
        "the key subject of the question in your opening sentence.\n"
        "2. Every sentence must be traceable to a specific source — "
        f"if you cannot cite a {id_label} for a claim, omit it entirely.\n"
        "3. Be concise: 2–4 sentences of well-supported claims only.\n"
        f"4. Cite every claim inline as ({id_label} XXXXXXXX).\n"
        "5. No general medical knowledge beyond what is in the evidence."
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
    max_tokens: int = 500,
    strict: bool = False,
    id_label: str = "PMID",
    source_type: str = "PubMed abstracts",
    dataset: str = "",
    chat_history: list[dict] | None = None,
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
    # Build per-chunk context headers using the correct label for each source.
    # When chunks come from multiple datasets (federated), each gets its own label
    # so the LLM always has the exact citation prefix to copy.
    _DS_LABEL_MAP = {
        "pubmedqa":   "PMID",
        "medquad":    "QID",
        "archehr_qa": "Case",
    }
    context_parts = []
    for c in chunks:
        ds = c.get("_dataset", "")
        chunk_label = _DS_LABEL_MAP.get(ds, id_label)
        context_parts.append(f"[{chunk_label} {c['pubid']}]\n{c['text']}")
    context = "\n\n".join(context_parts)

    # Check whether sources are mixed to update prompt wording
    ds_labels_used = {_DS_LABEL_MAP.get(c.get("_dataset", ""), id_label) for c in chunks}
    if len(ds_labels_used) > 1:
        source_type = "medical evidence records"
        id_label = "the identifier shown in brackets (PMID / QID / Case)"

    standard, strict_prompt = _build_system_prompts(id_label, source_type, dataset=dataset)
    system = strict_prompt if strict else standard

    _messages: list[dict] = []
    for _turn in (chat_history or []):
        _messages.append({"role": _turn["role"], "content": _turn["content"]})
    _messages.append({
        "role": "user",
        "content": f"Question: {query}\n\nEvidence:\n{context}",
    })

    resp = _get_client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=_messages,
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
