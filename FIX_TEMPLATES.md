# Fix Templates (Corrected)

These templates fix the highest-priority issues found in the review.

## P0-1: Add a Valid Strict Evaluation (PMID-disjoint split)

Problem:
- Current closed-corpus setup can overestimate retrieval performance for real-world retrieval.
- Invalid approach to avoid: removing gold doc and still scoring recall against that same gold.

Use this script skeleton as `scripts/strict_eval.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
from datasets import load_dataset
from rank_bm25 import BM25Okapi

CHUNK_SIZE = 400
CHUNK_STEP = 350
TOP_K = [5, 10]


def chunk_context(doc_id: str, text: str):
    words = text.split()
    start = 0
    while start < len(words):
        chunk = " ".join(words[start:start + CHUNK_SIZE]).strip()
        if chunk:
            yield {"doc_id": doc_id, "text": chunk}
        start += CHUNK_STEP


def build_index(records):
    corpus = []
    for r in records:
        corpus.extend(chunk_context(r["doc_id"], r["context"]))
    tokenized = [c["text"].lower().split() for c in corpus]
    bm25 = BM25Okapi(tokenized)
    return bm25, corpus


def recall_at_k(ranked_doc_ids, gold, k):
    return 1.0 if gold in ranked_doc_ids[:k] else 0.0


def run_eval(eval_records, bm25, corpus):
    out = {f"Recall@{k}": [] for k in TOP_K}
    for r in eval_records:
        scores = bm25.get_scores(r["question"].lower().split())
        top_idx = np.argsort(scores)[::-1][:50]
        ranked, seen = [], set()
        for i in top_idx:
            d = corpus[i]["doc_id"]
            if d not in seen:
                ranked.append(d)
                seen.add(d)
        for k in TOP_K:
            out[f"Recall@{k}"].append(recall_at_k(ranked, r["doc_id"], k))
    return {k: float(np.mean(v)) for k, v in out.items()}


def main():
    ds = load_dataset("pubmed_qa", "pqa_labeled")
    rows = []
    for item in ds["train"]:
        rows.append({
            "doc_id": str(item["pubid"]),
            "question": item["question"],
            "context": " ".join(item["context"]["contexts"]),
        })

    # PMID-disjoint split (deterministic)
    rows = sorted(rows, key=lambda x: x["doc_id"])
    n = len(rows)
    n_train, n_dev = int(n * 0.7), int(n * 0.15)
    train = rows[:n_train]
    dev = rows[n_train:n_train + n_dev]
    test = rows[n_train + n_dev:]

    bm25, corpus = build_index(train)

    # Optional: use dev for tuning. Report only test.
    test_metrics = run_eval(test, bm25, corpus)

    out = {
        "protocol": "PMID-disjoint split; index=train only; report=test only",
        "sizes": {"train": len(train), "dev": len(dev), "test": len(test)},
        "metrics": test_metrics,
    }
    Path("strict_metrics.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
```

## P0-2: Automate SciSpacy Model Setup

Create `scripts/install_models.ps1`:

```powershell
$ErrorActionPreference = 'Stop'

python -m pip install scispacy

# Preferred model (DISEASE/CHEMICAL)
python -m pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz

# Optional fallback model:
# python -m pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz
```

Also pin compatible dependency set for spaCy/scispaCy (avoid known ABI issues with incompatible NumPy/spaCy combos in your target env).

## P0-3: Use Safety-Wrapped Answer in App Display

Current gap:
- Evaluator returns `answer_with_disclaimer`, but UI displays raw `_rag_answer`.

Patch concept in `app.py` after eval result is available:

```python
result = store.get(store_key)
render_text = st.session_state.get("_rag_answer", "")
if result and result.get("answer_with_disclaimer"):
    render_text = result["answer_with_disclaimer"]

st.markdown(
    "<div style='background:#f0f7ff;border-left:4px solid #2196F3;padding:1rem;border-radius:4px;'>"
    + render_text.replace("\n", "<br>")
    + "</div>",
    unsafe_allow_html=True,
)
```

## P0-4: Add Deterministic CLI Entry Points

Create these scripts:
- `scripts/run_track1.py` (non-notebook path for Track 1 outputs)
- `scripts/run_track2.py` (calls `track2_build_kg.py` with preflight checks)
- `scripts/run_pipeline.py` (orchestrates both and verifies output files)

Minimal preflight checks to include:
- Python version
- Required files present
- SciSpacy model availability (for Track 2)
- API key presence only for RAG/eval steps that require it

## Validation Checklist

- `strict_metrics.json` produced from PMID-disjoint protocol
- Track 1 script produces `metrics.json` and `bm25_results.csv` deterministically
- Track 2 script completes from clean env after model install
- App displays safety-wrapped answer text when available
- README commands match exact runnable scripts
