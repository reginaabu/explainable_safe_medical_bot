"""
Deterministic Track 1 runner (BM25 baseline) without notebook execution.

Outputs (written to repo root by default):
  - metrics.json
  - bm25_results.csv
  - error_analysis.md

Usage:
  python scripts/run_track1.py
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
from datasets import load_dataset
from rank_bm25 import BM25Okapi

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SUBSET_CSV = ROOT / "pubmedqa_subset.csv"

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
CHUNK_STEP = CHUNK_SIZE - CHUNK_OVERLAP
EVAL_KS = [5, 10]


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    out: list[str] = []
    start = 0
    step = chunk_size - overlap
    while start < len(words):
        chunk = " ".join(words[start:start + chunk_size]).strip()
        if chunk:
            out.append(chunk)
        start += step
    return out


def load_records() -> list[dict]:
    # Prefer local subset for offline reproducibility.
    if SUBSET_CSV.exists():
        rows: list[dict] = []
        with SUBSET_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(
                    {
                        "pubid": str(row.get("doc_id") or row.get("pubid") or ""),
                        "question": row["question"],
                        "context": row["context"],
                    }
                )
        if rows:
            return rows

    ds = load_dataset("pubmed_qa", "pqa_labeled")
    records: list[dict] = []
    for item in ds["train"]:
        context_flat = " ".join(item["context"]["contexts"])
        records.append(
            {
                "pubid": str(item["pubid"]),
                "question": item["question"],
                "context": context_flat,
            }
        )
    return records


def build_corpus(records: list[dict]) -> list[dict]:
    corpus: list[dict] = []
    for rec in records:
        for chunk in chunk_text(rec["context"]):
            corpus.append({"pubid": rec["pubid"], "text": chunk})
    return corpus


def evaluate(records: list[dict], bm25: BM25Okapi, corpus: list[dict], ks: list[int]) -> tuple[dict, list[dict]]:
    max_k = max(ks)
    metrics: dict[str, float] = {}
    csv_rows: list[dict] = []

    for k in ks:
        recall_hits = 0
        reciprocal_ranks: list[float] = []
        ndcgs: list[float] = []

        for rec in records:
            query = rec["question"]
            gold = rec["pubid"]
            scores = bm25.get_scores(query.lower().split())
            ranked_idx = np.argsort(scores)[::-1][:k]
            retrieved_pubids = [corpus[i]["pubid"] for i in ranked_idx]
            found_rank = next((r for r, pid in enumerate(retrieved_pubids, 1) if pid == gold), None)

            if found_rank is not None:
                recall_hits += 1
                reciprocal_ranks.append(1.0 / found_rank)
                ndcgs.append(1.0 / math.log2(found_rank + 1))
            else:
                reciprocal_ranks.append(0.0)
                ndcgs.append(0.0)

            if k == max_k:
                top1_idx = int(ranked_idx[0]) if len(ranked_idx) > 0 else -1
                top1_score = float(scores[top1_idx]) if top1_idx >= 0 else 0.0
                top1_snippet = corpus[top1_idx]["text"][:200] if top1_idx >= 0 else ""
                csv_rows.append(
                    {
                        "query": query,
                        "gold_pubid": gold,
                        "ranked_pubids": "|".join(retrieved_pubids),
                        "top1_score": round(top1_score, 4),
                        "top1_snippet": top1_snippet,
                        "gold_retrieved": found_rank is not None,
                        "gold_rank": found_rank if found_rank is not None else -1,
                    }
                )

        metrics[f"Recall@{k}"] = round(recall_hits / len(records), 4)
        metrics[f"MRR@{k}"] = round(float(np.mean(reciprocal_ranks)), 4)
        metrics[f"nDCG@{k}"] = round(float(np.mean(ndcgs)), 4)

    metrics["dataset_size"] = len(records)
    metrics["corpus_chunks"] = len(corpus)
    metrics["gold_definition"] = "pubid_exact_match"
    metrics["chunk_size"] = CHUNK_SIZE
    metrics["chunk_overlap"] = CHUNK_OVERLAP
    return metrics, csv_rows


def diagnose(query: str, gold_snippet: str, top_snippet: str) -> str:
    qw = set(query.lower().split())
    gw = set(gold_snippet.lower().split())
    tw = set(top_snippet.lower().split())
    q_gold_overlap = len(qw & gw) / max(1, len(qw))
    q_top_overlap = len(qw & tw) / max(1, len(qw))
    if q_gold_overlap < 0.15:
        return (
            "Semantic/synonym gap: query and gold document share few surface tokens, "
            "so BM25 cannot bridge terminology differences."
        )
    if q_top_overlap > 0.35:
        return (
            "Topic collision: retrieved document shares query keywords but covers "
            "a different medical topic."
        )
    if len(gold_snippet.split()) > 300:
        return (
            "Long-context dilution: relevant evidence is spread across multiple chunks."
        )
    return (
        "Lexical mismatch: gold document uses domain-specific or abbreviated terms "
        "absent from the query."
    )


def build_error_analysis(records: list[dict], bm25: BM25Okapi, corpus: list[dict]) -> str:
    failures: list[dict] = []
    for rec in records:
        scores = bm25.get_scores(rec["question"].lower().split())
        ranked_idx = np.argsort(scores)[::-1][:10]
        retrieved_pubids = [corpus[i]["pubid"] for i in ranked_idx]
        if rec["pubid"] not in retrieved_pubids:
            failures.append(
                {
                    "query": rec["question"],
                    "gold_pubid": rec["pubid"],
                    "gold_snippet": rec["context"][:300],
                    "top3_pubids": [corpus[i]["pubid"] for i in ranked_idx[:3]],
                    "top3_snippets": [corpus[i]["text"][:250] for i in ranked_idx[:3]],
                }
            )

    lines = [
        "# Error Analysis - BM25 Failure Cases",
        "",
        "> Gold definition: hit if any chunk from the annotated PMID appears in top-10.",
        "",
        f"**Total failures at Recall@10:** {len(failures)} / {len(records)}",
        "",
    ]

    for i, case in enumerate(failures[:10], 1):
        top1 = case["top3_snippets"][0] if case["top3_snippets"] else ""
        reason = diagnose(case["query"], case["gold_snippet"], top1)
        top3 = "`, `".join(case["top3_pubids"])
        lines.extend(
            [
                "---",
                "",
                f"## Failure {i}",
                "",
                f"**Query:** {case['query']}",
                "",
                f"**Gold PMID:** `{case['gold_pubid']}`",
                "",
                f"**Top-3 retrieved PMIDs:** `{top3}`",
                "",
                f"**Gold snippet (first 300 chars):**\n> {case['gold_snippet']}",
                "",
                f"**Top-1 retrieved snippet (first 250 chars):**\n> {top1}",
                "",
                f"**Why BM25 failed:** {reason}",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## Summary of Failure Patterns",
            "",
            "| Pattern | Description |",
            "|---------|-------------|",
            "| Topic collision | Generic procedural keywords match unrelated studies |",
            "| Figurative language | Non-literal phrasing has weak lexical bridge to abstracts |",
            "| Synonym/abbreviation gap | Query and gold use different terminology for same concept |",
            "| Long-context dilution | Evidence is distributed across chunks |",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    print("Loading PubMedQA...")
    records = load_records()
    print(f"Loaded {len(records)} records")

    print("Building chunked corpus and BM25 index...")
    corpus = build_corpus(records)
    bm25 = BM25Okapi([d["text"].lower().split() for d in corpus])
    print(f"Indexed {len(corpus)} chunks")

    print("Running evaluation...")
    metrics, csv_rows = evaluate(records, bm25, corpus, EVAL_KS)

    metrics_path = ROOT / "metrics.json"
    results_path = ROOT / "bm25_results.csv"
    analysis_path = ROOT / "error_analysis.md"

    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    with results_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "query",
                "gold_pubid",
                "ranked_pubids",
                "top1_score",
                "top1_snippet",
                "gold_retrieved",
                "gold_rank",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    analysis_text = build_error_analysis(records, bm25, corpus)
    analysis_path.write_text(analysis_text, encoding="utf-8")

    print("Saved outputs:")
    print(f"  - {metrics_path.name}")
    print(f"  - {results_path.name}")
    print(f"  - {analysis_path.name}")
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
