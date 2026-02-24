"""
build_hard_set.py – Curated hard-set evaluation: BM25 failures + KG recovery
=============================================================================

Pipeline
--------
1. Load PubMedQA + build tuned BM25 index (reads bm25_params.json)
2. Run BM25@5 on all 1,000 queries  → collect failures (gold not in top-5)
3. For each failure, run KG expansion → re-run BM25@5
4. Count recoveries (gold in top-5 with KG expansion)
5. Save hard_queries.csv + curated_eval.md, print summary table

Outputs
-------
    hard_queries.csv   – doc_id, question, failure_reason, kg_recovered
    curated_eval.md    – markdown results table + interpretation

Run:
    python build_hard_set.py
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from datasets import load_dataset
from rank_bm25 import BM25Okapi
from tqdm import tqdm

from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
HERE           = Path(__file__).parent
PARAMS_JSON    = HERE / "bm25_params.json"
HARD_CSV       = HERE / "hard_queries.csv"
CURATED_MD     = HERE / "curated_eval.md"

# ── Constants ──────────────────────────────────────────────────────────────────
CHUNK_SIZE  = 400
CHUNK_STEP  = 350   # 400 - 50 overlap

TOP_K_HARD  = 5    # defines the "hard" set (BM25 failures at @5)
EVAL_KS     = [5, 10]
MRR_K       = 10


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════
def _bm25_params() -> tuple[float, float]:
    if PARAMS_JSON.exists():
        d = json.loads(PARAMS_JSON.read_text())
        return d["k1"], d["b"]
    logger.warning("bm25_params.json not found — using defaults (k1=1.5, b=0.75)")
    return 1.5, 0.75


def _load_pubmedqa() -> list[dict]:
    logger.info("Loading PubMedQA pqa_labeled …")
    dataset = load_dataset("pubmed_qa", "pqa_labeled", trust_remote_code=True)
    records = []
    for item in dataset["train"]:
        context_flat = " ".join(item["context"]["contexts"])
        records.append({
            "doc_id":   str(item["pubid"]),
            "question": item["question"],
            "context":  context_flat,
        })
    logger.info("Loaded %d records.", len(records))
    return records


def _build_bm25(records: list[dict], k1: float, b: float):
    logger.info("Building BM25 index (k1=%.2f, b=%.2f) …", k1, b)
    corpus: list[dict] = []
    for rec in records:
        words = rec["context"].split()
        start = 0
        while start < len(words):
            chunk = " ".join(words[start : start + CHUNK_SIZE])
            if chunk.strip():
                corpus.append({"doc_id": rec["doc_id"], "text": chunk})
            start += CHUNK_STEP
    tokenized = [doc["text"].lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenized, k1=k1, b=b)
    logger.info("Index built: %d chunks.", len(corpus))
    return bm25, corpus


def _top_doc_ids(bm25, corpus, query_str: str, top_n: int = 10) -> list[str]:
    tokens  = query_str.lower().split()
    scores  = bm25.get_scores(tokens)
    top_idx = np.argsort(scores)[::-1][:top_n * 3]   # over-fetch then dedupe
    seen: set[str] = set()
    ranked: list[str] = []
    for idx in top_idx:
        pid = corpus[idx]["doc_id"]
        if pid not in seen:
            ranked.append(pid)
            seen.add(pid)
        if len(ranked) >= top_n:
            break
    return ranked


def _recall(ranked: list[str], gold: str, k: int) -> float:
    return 1.0 if gold in ranked[:k] else 0.0


def _mrr(ranked: list[str], gold: str, k: int) -> float:
    for i, pid in enumerate(ranked[:k], 1):
        if pid == gold:
            return 1.0 / i
    return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    # 1. Load data + build index
    k1, b    = _bm25_params()
    records  = _load_pubmedqa()
    bm25, corpus = _build_bm25(records, k1, b)

    # 2. Full-set BM25 evaluation
    logger.info("Running BM25 on full set (%d queries) …", len(records))
    full_r5: list[float]  = []
    full_r10: list[float] = []
    full_mrr: list[float] = []
    failures: list[dict]  = []

    for rec in tqdm(records, desc="Full-set BM25"):
        ranked = _top_doc_ids(bm25, corpus, rec["question"], top_n=10)
        gold   = rec["doc_id"]
        r5  = _recall(ranked, gold, 5)
        r10 = _recall(ranked, gold, 10)
        mrr = _mrr(ranked, gold, MRR_K)
        full_r5.append(r5)
        full_r10.append(r10)
        full_mrr.append(mrr)

        if r5 == 0.0:   # BM25@5 failure → hard set
            failures.append(rec)

    full_metrics = {
        "Recall@5":  float(np.mean(full_r5)),
        "Recall@10": float(np.mean(full_r10)),
        "MRR@10":    float(np.mean(full_mrr)),
    }
    logger.info(
        "Full set — Recall@5=%.4f  Recall@10=%.4f  MRR@10=%.4f",
        full_metrics["Recall@5"], full_metrics["Recall@10"], full_metrics["MRR@10"],
    )
    logger.info("Hard set size: %d failures at BM25@5.", len(failures))

    # 3. KG expansion on the hard set
    logger.info("Loading KG expander …")
    try:
        from kg_expand import expand_query
        expand_query("test")   # warm-up: loads graph + NLP model
        logger.info("KG expander ready.")
        kg_available = True
    except Exception as exc:
        logger.warning("KG expander unavailable (%s). Skipping KG recovery.", exc)
        kg_available = False

    hard_r5_bm25: list[float]  = []
    hard_r10_bm25: list[float] = []
    hard_mrr_bm25: list[float] = []
    hard_r5_kg: list[float]    = []
    hard_r10_kg: list[float]   = []
    hard_mrr_kg: list[float]   = []

    hard_rows: list[dict] = []

    logger.info("Evaluating hard set with BM25 and BM25+KG …")
    for rec in tqdm(failures, desc="Hard-set eval"):
        gold = rec["doc_id"]

        # BM25 on hard set (by definition Recall@5 = 0, but @10/MRR may not be)
        ranked_bm25 = _top_doc_ids(bm25, corpus, rec["question"], top_n=10)
        hard_r5_bm25.append(_recall(ranked_bm25, gold, 5))
        hard_r10_bm25.append(_recall(ranked_bm25, gold, 10))
        hard_mrr_bm25.append(_mrr(ranked_bm25, gold, MRR_K))

        # BM25+KG on hard set
        kg_recovered = False
        if kg_available:
            expanded     = expand_query(rec["question"])
            ranked_kg    = _top_doc_ids(bm25, corpus, expanded, top_n=10)
            r5_kg  = _recall(ranked_kg, gold, 5)
            r10_kg = _recall(ranked_kg, gold, 10)
            mrr_kg = _mrr(ranked_kg, gold, MRR_K)
            hard_r5_kg.append(r5_kg)
            hard_r10_kg.append(r10_kg)
            hard_mrr_kg.append(mrr_kg)
            kg_recovered = r5_kg > 0.0
        else:
            hard_r5_kg.append(0.0)
            hard_r10_kg.append(0.0)
            hard_mrr_kg.append(0.0)

        hard_rows.append({
            "doc_id":         rec["doc_id"],
            "question":       rec["question"],
            "failure_reason": "Gold not in BM25@5",
            "kg_recovered":   kg_recovered,
        })

    # 4. Aggregate hard-set metrics
    hard_bm25_metrics = {
        "Recall@5":  float(np.mean(hard_r5_bm25))  if hard_r5_bm25  else 0.0,
        "Recall@10": float(np.mean(hard_r10_bm25)) if hard_r10_bm25 else 0.0,
        "MRR@10":    float(np.mean(hard_mrr_bm25)) if hard_mrr_bm25 else 0.0,
    }
    hard_kg_metrics = {
        "Recall@5":  float(np.mean(hard_r5_kg))  if hard_r5_kg  else 0.0,
        "Recall@10": float(np.mean(hard_r10_kg)) if hard_r10_kg else 0.0,
        "MRR@10":    float(np.mean(hard_mrr_kg)) if hard_mrr_kg else 0.0,
    }

    recoveries = sum(1 for r in hard_rows if r["kg_recovered"])
    logger.info(
        "Hard set — BM25+KG recovered %d/%d queries at @5.",
        recoveries, len(failures),
    )

    # 5a. Save hard_queries.csv
    logger.info("Saving %s …", HARD_CSV.name)
    with open(HARD_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["doc_id", "question", "failure_reason", "kg_recovered"]
        )
        writer.writeheader()
        writer.writerows(hard_rows)

    # 5b. Write curated_eval.md
    logger.info("Writing %s …", CURATED_MD.name)
    _write_curated_md(full_metrics, hard_bm25_metrics, hard_kg_metrics, len(failures), recoveries)

    # 6. Print summary table (ASCII-safe)
    sep = "-" * 62
    print(f"\n{sep}")
    print(f"{'Subset':<28} {'Recall@5':>9} {'Recall@10':>10} {'MRR@10':>8}")
    print(sep)
    print(f"{'Full set – BM25':<28} {full_metrics['Recall@5']:>9.3f} "
          f"{full_metrics['Recall@10']:>10.3f} {full_metrics['MRR@10']:>8.3f}")
    print(f"{'Hard set – BM25':<28} {hard_bm25_metrics['Recall@5']:>9.3f} "
          f"{hard_bm25_metrics['Recall@10']:>10.3f} {hard_bm25_metrics['MRR@10']:>8.3f}")
    print(f"{'Hard set – BM25 + KG':<28} {hard_kg_metrics['Recall@5']:>9.3f} "
          f"{hard_kg_metrics['Recall@10']:>10.3f} {hard_kg_metrics['MRR@10']:>8.3f}")
    print(sep)

    # KG gate check
    delta_r5 = hard_kg_metrics["Recall@5"] - hard_bm25_metrics["Recall@5"]
    if delta_r5 > 0:
        print(f"\nKG GATE: PASSED (+{delta_r5:.3f} Recall@5 on hard set, "
              f"{recoveries} queries recovered)")
    else:
        print(f"\nKG GATE: NOT PASSED (delta Recall@5 = {delta_r5:+.3f})")

    print(f"\nOutputs written to: {HERE}")
    print(f"  {HARD_CSV.name}")
    print(f"  {CURATED_MD.name}")


def _write_curated_md(
    full: dict,
    hard_bm25: dict,
    hard_kg: dict,
    hard_set_size: int,
    recoveries: int,
) -> None:
    delta_r5  = hard_kg["Recall@5"]  - hard_bm25["Recall@5"]
    delta_r10 = hard_kg["Recall@10"] - hard_bm25["Recall@10"]
    delta_mrr = hard_kg["MRR@10"]    - hard_bm25["MRR@10"]

    gate_status = (
        f"**PASSED** — KG improved Recall@5 by +{delta_r5:.3f} "
        f"({recoveries} queries recovered out of {hard_set_size})"
        if delta_r5 > 0
        else f"**NOT PASSED** — KG did not improve Recall@5 (Δ = {delta_r5:+.3f})"
    )

    lines = [
        "# Curated Hard-Set Evaluation: KG Gate",
        "",
        "## Setup",
        "",
        "- **Full set:** PubMedQA `pqa_labeled` — 1,000 questions",
        "- **Hard set:** queries where BM25@5 fails to return the gold document",
        f"- **Hard set size:** {hard_set_size} queries",
        "- **KG expansion:** SciSpacy NER → top co-occurrence neighbours from triples.csv",
        "",
        "## Results",
        "",
        "| Subset | Recall@5 | Recall@10 | MRR@10 |",
        "|--------|----------|-----------|--------|",
        f"| Full set – BM25 | {full['Recall@5']:.3f} | {full['Recall@10']:.3f} | {full['MRR@10']:.3f} |",
        f"| Hard set – BM25 | {hard_bm25['Recall@5']:.3f} | {hard_bm25['Recall@10']:.3f} | {hard_bm25['MRR@10']:.3f} |",
        f"| Hard set – BM25 + KG | {hard_kg['Recall@5']:.3f} | {hard_kg['Recall@10']:.3f} | {hard_kg['MRR@10']:.3f} |",
        "",
        "## Deltas (Hard set: KG vs BM25)",
        "",
        f"| Metric | Δ |",
        f"|--------|---|",
        f"| Recall@5  | {delta_r5:+.3f} |",
        f"| Recall@10 | {delta_r10:+.3f} |",
        f"| MRR@10    | {delta_mrr:+.3f} |",
        "",
        "## KG Gate Status",
        "",
        gate_status,
        "",
        "## Interpretation",
        "",
        "The hard set contains queries where BM25 alone cannot retrieve the gold",
        "document in the top 5 results. This is the exact failure mode that KG",
        "expansion is designed to address: by appending biomedical co-occurrence",
        "terms, the expanded query may bridge vocabulary gaps between the question",
        "and the abstract.",
        "",
        "A positive Δ Recall@5 on the hard set confirms that KG expansion provides",
        "real value for the queries where vanilla BM25 struggles most.",
        "",
        "_Generated by `build_hard_set.py`_",
    ]

    CURATED_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
