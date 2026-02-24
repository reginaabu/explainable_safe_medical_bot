"""
BM25 parameter tuning – grid search over k1 and b
===================================================

Run:
    python tune_bm25.py

Searches k1 × b combinations using MRR@10 on all 1,000 PubMedQA questions.
Writes the best parameters to bm25_params.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from datasets import load_dataset
from rank_bm25 import BM25Okapi
from tqdm import tqdm

HERE = Path(__file__).parent
PARAMS_JSON = HERE / "bm25_params.json"

CHUNK_SIZE    = 400
CHUNK_STEP    = 350
MRR_K         = 10
EVAL_TOP_K    = 20   # retrieve this many before computing MRR

# Grid
K1_VALUES = [0.5, 0.75, 0.9, 1.2, 1.5, 1.8]
B_VALUES  = [0.25, 0.40, 0.55, 0.75]


def load_data():
    print("Loading PubMedQA …")
    dataset = load_dataset("pubmed_qa", "pqa_labeled", trust_remote_code=True)
    records, corpus = [], []
    for item in dataset["train"]:
        ctx = " ".join(item["context"]["contexts"])
        records.append({"doc_id": str(item["pubid"]), "question": item["question"]})
        words = ctx.split()
        start = 0
        while start < len(words):
            chunk = " ".join(words[start : start + CHUNK_SIZE])
            if chunk.strip():
                corpus.append({"doc_id": str(item["pubid"]), "text": chunk})
            start += CHUNK_STEP
    print(f"  {len(records)} questions, {len(corpus)} chunks")
    return records, corpus


def mrr_at_k(ranked_ids: list[str], gold: str, k: int) -> float:
    for i, pid in enumerate(ranked_ids[:k], 1):
        if pid == gold:
            return 1.0 / i
    return 0.0


def evaluate(bm25: BM25Okapi, records: list[dict], corpus: list[dict]) -> float:
    scores_list = []
    for rec in records:
        tokens  = rec["question"].lower().split()
        scores  = bm25.get_scores(tokens)
        top_idx = np.argsort(scores)[::-1][:EVAL_TOP_K]
        seen, ranked = set(), []
        for idx in top_idx:
            pid = corpus[idx]["doc_id"]
            if pid not in seen:
                ranked.append(pid)
                seen.add(pid)
        scores_list.append(mrr_at_k(ranked, rec["doc_id"], MRR_K))
    return float(np.mean(scores_list))


def main():
    records, corpus = load_data()
    tokenized = [doc["text"].lower().split() for doc in corpus]

    results: list[tuple[float, float, float]] = []   # (mrr, k1, b)

    total = len(K1_VALUES) * len(B_VALUES)
    print(f"\nGrid search: {len(K1_VALUES)} k1 × {len(B_VALUES)} b = {total} combinations\n")

    with tqdm(total=total, desc="Tuning") as pbar:
        for k1 in K1_VALUES:
            for b in B_VALUES:
                bm25 = BM25Okapi(tokenized, k1=k1, b=b)
                mrr  = evaluate(bm25, records, corpus)
                results.append((mrr, k1, b))
                pbar.set_postfix(k1=k1, b=b, mrr=f"{mrr:.4f}")
                pbar.update(1)

    results.sort(reverse=True)
    best_mrr, best_k1, best_b = results[0]

    # Print table
    print(f"\n{'k1':>6}  {'b':>6}  {'MRR@10':>8}")
    print("-" * 26)
    for mrr, k1, b in results:
        marker = "  <-- best" if (k1 == best_k1 and b == best_b) else ""
        print(f"{k1:>6.2f}  {b:>6.2f}  {mrr:>8.4f}{marker}")

    print(f"\nBest: k1={best_k1}, b={best_b}, MRR@10={best_mrr:.4f}")
    print(f"Default baseline (k1=1.5, b=0.75): MRR@10="
          f"{next(mrr for mrr, k1, b in results if k1==1.5 and b==0.75):.4f}")

    params = {"k1": best_k1, "b": best_b, "mrr_at_10": best_mrr}
    PARAMS_JSON.write_text(json.dumps(params, indent=2))
    print(f"\nSaved to {PARAMS_JSON.name}")


if __name__ == "__main__":
    main()
