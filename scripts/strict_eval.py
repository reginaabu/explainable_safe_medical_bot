"""
Strict evaluation protocol for leakage control.

Protocol:
  1) Split queries by PMID into train/dev/test (deterministic, disjoint sets).
  2) Tune BM25 params on train only.
  3) Select best params on dev.
  4) Report final metrics on test only.

Notes:
  - This removes tuning leakage from headline numbers.
  - Candidate corpus remains the full PubMedQA subset corpus; this is still a closed-corpus benchmark.

Outputs:
  - strict_metrics.json
  - strict_eval.md
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
from datasets import load_dataset
from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parent.parent
SUBSET_CSV = ROOT / "pubmedqa_subset.csv"

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
CHUNK_STEP = CHUNK_SIZE - CHUNK_OVERLAP

K1_GRID = [0.75, 1.2, 1.5, 1.8]
B_GRID = [0.4, 0.75]


def load_records() -> list[dict]:
    # Prefer local subset for offline reproducibility.
    if SUBSET_CSV.exists():
        rows: list[dict] = []
        with SUBSET_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(
                    {
                        "doc_id": str(row.get("doc_id") or row.get("pubid") or ""),
                        "question": row["question"],
                        "context": row["context"],
                    }
                )
        if rows:
            return rows

    ds = load_dataset("pubmed_qa", "pqa_labeled")
    records: list[dict] = []
    for item in ds["train"]:
        records.append(
            {
                "doc_id": str(item["pubid"]),
                "question": item["question"],
                "context": " ".join(item["context"]["contexts"]),
            }
        )
    return records


def build_corpus(records: list[dict]) -> list[dict]:
    corpus: list[dict] = []
    for rec in records:
        words = rec["context"].split()
        start = 0
        while start < len(words):
            chunk = " ".join(words[start:start + CHUNK_SIZE]).strip()
            if chunk:
                corpus.append({"doc_id": rec["doc_id"], "text": chunk})
            start += CHUNK_STEP
    return corpus


def split_records(records: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    recs = sorted(records, key=lambda r: r["doc_id"])
    n = len(recs)
    n_train = int(n * 0.7)
    n_dev = int(n * 0.15)
    train = recs[:n_train]
    dev = recs[n_train:n_train + n_dev]
    test = recs[n_train + n_dev:]
    return train, dev, test


def _recall_at_k(ranked: list[str], gold: str, k: int) -> float:
    return 1.0 if gold in ranked[:k] else 0.0


def _rr_at_k(ranked: list[str], gold: str, k: int) -> float:
    for i, pid in enumerate(ranked[:k], 1):
        if pid == gold:
            return 1.0 / i
    return 0.0


def _ndcg_at_k(ranked: list[str], gold: str, k: int) -> float:
    for i, pid in enumerate(ranked[:k], 1):
        if pid == gold:
            return 1.0 / math.log2(i + 1)
    return 0.0


def evaluate(records: list[dict], bm25: BM25Okapi, corpus: list[dict]) -> dict:
    rec5, rec10, rr10, ndcg10 = [], [], [], []
    for rec in records:
        scores = bm25.get_scores(rec["question"].lower().split())
        top_idx = np.argsort(scores)[::-1][:30]

        ranked_doc_ids: list[str] = []
        seen = set()
        for i in top_idx:
            did = corpus[i]["doc_id"]
            if did not in seen:
                ranked_doc_ids.append(did)
                seen.add(did)

        gold = rec["doc_id"]
        rec5.append(_recall_at_k(ranked_doc_ids, gold, 5))
        rec10.append(_recall_at_k(ranked_doc_ids, gold, 10))
        rr10.append(_rr_at_k(ranked_doc_ids, gold, 10))
        ndcg10.append(_ndcg_at_k(ranked_doc_ids, gold, 10))

    return {
        "Recall@5": float(np.mean(rec5)),
        "Recall@10": float(np.mean(rec10)),
        "MRR@10": float(np.mean(rr10)),
        "nDCG@10": float(np.mean(ndcg10)),
    }


def main() -> int:
    print("Loading data...")
    records = load_records()
    corpus = build_corpus(records)
    tokenized = [d["text"].lower().split() for d in corpus]
    train, dev, test = split_records(records)

    print(f"Split sizes: train={len(train)} dev={len(dev)} test={len(test)}")
    print("Tuning on train, selecting on dev...")

    best = None
    best_dev = -1.0
    for k1 in K1_GRID:
        for b in B_GRID:
            bm25 = BM25Okapi(tokenized, k1=k1, b=b)
            dev_metrics = evaluate(dev, bm25, corpus)
            score = dev_metrics["MRR@10"]
            if score > best_dev:
                best_dev = score
                best = (k1, b, dev_metrics)

    assert best is not None
    best_k1, best_b, best_dev_metrics = best
    final_bm25 = BM25Okapi(tokenized, k1=best_k1, b=best_b)
    test_metrics = evaluate(test, final_bm25, corpus)

    out = {
        "protocol": {
            "name": "PMID-disjoint query split (train/dev/test)",
            "tuning": "train only",
            "selection": "best dev MRR@10",
            "final_report": "test only",
            "corpus_scope": "closed corpus (PubMedQA subset)",
        },
        "split_sizes": {"train": len(train), "dev": len(dev), "test": len(test)},
        "best_params": {"k1": best_k1, "b": best_b},
        "dev_metrics_best": best_dev_metrics,
        "test_metrics": test_metrics,
    }

    (ROOT / "strict_metrics.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = [
        "# Strict Evaluation (PMID-disjoint split)",
        "",
        "- Tuning set: train queries only",
        "- Model selection: dev MRR@10",
        "- Final report: test queries only",
        "- Corpus: closed PubMedQA subset corpus",
        "",
        f"- Best params: k1={best_k1}, b={best_b}",
        "",
        "## Test Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Recall@5 | {test_metrics['Recall@5']:.4f} |",
        f"| Recall@10 | {test_metrics['Recall@10']:.4f} |",
        f"| MRR@10 | {test_metrics['MRR@10']:.4f} |",
        f"| nDCG@10 | {test_metrics['nDCG@10']:.4f} |",
        "",
        "## Caveat",
        "",
        "This protocol removes tuning leakage, but remains closed-corpus evaluation.",
    ]
    (ROOT / "strict_eval.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("Saved strict_metrics.json and strict_eval.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
