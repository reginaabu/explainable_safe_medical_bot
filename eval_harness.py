"""
eval_harness.py – CLI evaluation harness for Track 3.

Samples N questions from a dataset, runs the full RAG+eval pipeline for each,
and writes a Markdown report to track3_eval_report.md.

Usage
-----
    python eval_harness.py                                   # PubMedQA, 25 questions
    python eval_harness.py --dataset medquad                 # MedQuAD via HuggingFace
    python eval_harness.py --dataset medquad --n 50
    python eval_harness.py --dataset archehr_qa --csv-path /path/to/archehr.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import time
from pathlib import Path

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HERE = Path(__file__).parent


# ── CLI args ──────────────────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    from utils.dataset_adapter import DATASET_META
    p = argparse.ArgumentParser(description="Track 3 evaluation harness")
    p.add_argument("--n",    type=int, default=25, help="Number of questions (default: 25)")
    p.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    p.add_argument("--compare", action="store_true",
                   help="Also run baseline (raw RAG, no correction) and show delta")
    p.add_argument(
        "--dataset",
        default="pubmedqa",
        choices=list(DATASET_META),
        help="Dataset to evaluate (default: pubmedqa)",
    )
    p.add_argument(
        "--csv-path",
        default=None,
        help="Path to a local CSV file. If omitted, the default path or "
             "HuggingFace auto-download is used.",
    )
    p.add_argument(
        "--retriever",
        default=None,
        choices=["bm25", "semantic", "hybrid"],
        help="Retrieval strategy. Defaults to the dataset's recommended retriever "
             "(bm25 for pubmedqa, hybrid for medquad).",
    )
    return p.parse_args()


# ── Load rows ─────────────────────────────────────────────────────────────────
def _load_rows(dataset: str, csv_path: str | None) -> list[dict]:
    from utils.dataset_adapter import load_dataset_rows

    # For pubmedqa, fall back to the local subset CSV when no explicit path given
    if csv_path is None and dataset == "pubmedqa":
        default = HERE / "pubmedqa_subset.csv"
        if default.exists():
            csv_path = str(default)

    return load_dataset_rows(dataset, csv_path=csv_path)


# ── Build inline BM25 index from CSV ─────────────────────────────────────────
def _build_bm25(rows: list[dict]):
    """Build a BM25Okapi index directly from the CSV rows (no HuggingFace)."""
    from rank_bm25 import BM25Okapi

    # Read tuned params if available
    params_file = HERE / "bm25_params.json"
    k1, b = 1.5, 0.75
    if params_file.exists():
        p = json.loads(params_file.read_text())
        k1, b = p.get("k1", k1), p.get("b", b)
    log.info("BM25 params: k1=%.2f  b=%.2f", k1, b)

    # Build 400-word sliding-window chunks
    corpus: list[dict] = []
    for row in rows:
        words = row["context"].split()
        start = 0
        while start < len(words):
            chunk = " ".join(words[start: start + 400])
            if chunk.strip():
                corpus.append({"pubid": row["doc_id"], "text": chunk})
            start += 350

    tokenized = [doc["text"].lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenized, k1=k1, b=b)
    log.info("BM25 index: %d chunks from %d rows", len(corpus), len(rows))
    return bm25, corpus


# ── Retrieve top-k ────────────────────────────────────────────────────────────
def _retrieve(bm25, corpus: list[dict], query: str, top_k: int = 3) -> list[dict]:
    import numpy as np
    scores = bm25.get_scores(query.lower().split())
    ranked = np.argsort(scores)[::-1][:top_k]
    return [corpus[i] for i in ranked if scores[i] > 0]


# ── Markdown helpers ──────────────────────────────────────────────────────────
def _score_str(val: float | None) -> str:
    return f"{val:.3f}" if val is not None else "N/A"


def _safe_str(is_safe: bool, flags: list[str]) -> str:
    if is_safe:
        return "SAFE"
    short = [f.split(":")[0] for f in flags]
    return "UNSAFE(" + ",".join(sorted(set(short))) + ")"


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    args = _parse_args()
    n, seed = args.n, args.seed

    from utils.dataset_adapter import get_id_label, get_source_type, get_default_retriever
    id_label    = get_id_label(args.dataset)
    source_type = get_source_type(args.dataset)
    retriever   = args.retriever or get_default_retriever(args.dataset)

    log.info("Loading dataset '%s' …", args.dataset)
    all_rows = _load_rows(args.dataset, args.csv_path)

    # Skip rows with no question (e.g. MIMIC-III/IV which have no QA pairs)
    all_rows = [r for r in all_rows if r["question"].strip()]
    if not all_rows:
        log.error(
            "Dataset '%s' contains no rows with a 'question' field. "
            "This dataset cannot be used with the eval harness directly — "
            "it needs a QA benchmark layered on top (e.g. ArchEHR-QA for MIMIC-IV).",
            args.dataset,
        )
        return 1

    rng = random.Random(seed)
    sample = rng.sample(all_rows, min(n, len(all_rows)))
    log.info("Sampled %d questions (seed=%d)", len(sample), seed)

    log.info("Building BM25 index …")
    bm25, corpus = _build_bm25(all_rows)

    # Build semantic / hybrid index if needed
    sem_index = None
    hybrid_index = None
    if retriever in ("semantic", "hybrid"):
        from utils.semantic_index import SemanticIndex, HybridIndex
        if retriever == "semantic":
            sem_index = SemanticIndex(all_rows)
        else:
            # For Q&A datasets, build a question-field BM25 so the BM25 signal
            # searches the same field as the semantic index — avoids the
            # "What is X?" answer dominating all type-specific queries.
            has_questions = any(r["question"].strip() for r in all_rows)
            if has_questions:
                log.info("Building question-field BM25 for hybrid index …")
                q_tokenized = [r["question"].lower().split() for r in all_rows
                               if r["question"].strip() and r["context"].strip()]
                q_corpus = [{"pubid": r["doc_id"], "text": r["context"]}
                            for r in all_rows
                            if r["question"].strip() and r["context"].strip()]
                from rank_bm25 import BM25Okapi
                q_bm25 = BM25Okapi(q_tokenized)
                hybrid_index = HybridIndex(all_rows, q_bm25, q_corpus)
            else:
                hybrid_index = HybridIndex(all_rows, bm25, corpus)
    log.info("Retriever: %s", retriever)

    from rag_generate import generate_answer, _get_api_key as _rag_api_key
    from evaluator import evaluate_answer, FACTUALITY_THRESHOLD

    if not _rag_api_key():
        log.error(
            "ANTHROPIC_API_KEY not found. Failing fast: Track 3 evaluation "
            "requires a valid Anthropic key for generation."
        )
        return 2

    results: list[dict] = []

    for i, row in enumerate(sample, 1):
        pubid    = row["doc_id"]
        question = row["question"]
        log.info("[%d/%d] %s %s | %s …", i, len(sample), id_label, pubid, question[:60])

        # Question-focus expansion for BM25 (free boost for Q&A datasets)
        focus  = row.get("focus", "").strip()
        q_type = row.get("q_type", "").strip() or None
        bm25_query = f"{question} {focus}".strip() if focus else question

        if retriever == "semantic" and sem_index:
            chunks = sem_index.query(question, top_k=3, q_type=q_type)
        elif retriever == "hybrid" and hybrid_index:
            chunks = hybrid_index.query(bm25_query, top_k=3, q_type=q_type)
        else:
            chunks = _retrieve(bm25, corpus, bm25_query, top_k=3)

        if not chunks:
            chunks = [{"pubid": pubid, "text": row["context"][:800]}]

        # Generate answer (timed)
        t0 = time.perf_counter()
        try:
            answer = generate_answer(question, chunks, id_label=id_label, source_type=source_type)
        except Exception as exc:
            log.error("generate_answer failed: %s", exc)
            log.error("Failing fast. No report written.")
            return 3
        latency_s = time.perf_counter() - t0

        # Evaluate
        try:
            eval_result = evaluate_answer(question, answer, chunks, latency_s=latency_s)
        except Exception as exc:
            log.error("evaluate_answer failed: %s", exc)
            log.error("Failing fast. No report written.")
            return 4

        # Correction loop: one retry with strict prompt if factuality below threshold
        eval_result["correction_applied"] = False
        if eval_result["factuality_score"] < FACTUALITY_THRESHOLD:
            log.info("  factuality %.2f < %.2f — retrying with strict prompt …",
                     eval_result["factuality_score"], FACTUALITY_THRESHOLD)
            try:
                strict_ans = generate_answer(question, chunks, strict=True,
                                             id_label=id_label, source_type=source_type)
                strict_res = evaluate_answer(question, strict_ans, chunks,
                                             latency_s=eval_result["latency_s"])
                strict_res["correction_applied"] = False
                if strict_res["factuality_score"] >= eval_result["factuality_score"]:
                    answer, eval_result = strict_ans, strict_res
                    eval_result["correction_applied"] = True
                    log.info("  correction improved factuality to %.2f",
                             eval_result["factuality_score"])
            except Exception as exc:
                log.warning("  correction loop failed: %s", exc)

        log.info(
            "  safe=%s  facts=%d  factuality=%.2f  faith=%s  rel=%s  latency=%.2fs  corrected=%s",
            eval_result["is_safe"],
            len(eval_result["facts"]),
            eval_result["factuality_score"],
            _score_str(eval_result["faithfulness"]),
            _score_str(eval_result["answer_relevancy"]),
            eval_result["latency_s"],
            eval_result["correction_applied"],
        )

        # Baseline pipeline (--compare mode only)
        baseline_faith = None
        if args.compare:
            try:
                bl_answer = generate_answer(question, chunks,
                                            id_label=id_label, source_type=source_type)
                from evaluator.metrics import score_metrics as _sm
                baseline_faith = _sm(question, bl_answer, chunks)["faithfulness"]
            except Exception as exc:
                log.error("baseline compare generation/scoring failed: %s", exc)
                log.error("Failing fast. No report written.")
                return 5

        results.append({
            "pubid":              pubid,
            "question":           question,
            "answer":             answer,
            "is_safe":            eval_result["is_safe"],
            "safety_flags":       eval_result["safety_flags"],
            "facts":              eval_result["facts"],
            "fact_verdicts":      eval_result["fact_verdicts"],
            "factuality_score":   eval_result["factuality_score"],
            "faithfulness":       eval_result["faithfulness"],
            "answer_relevancy":   eval_result["answer_relevancy"],
            "latency_s":          eval_result["latency_s"],
            "correction_applied": eval_result["correction_applied"],
            "baseline_faith":     baseline_faith,
        })

    # ── Aggregate ─────────────────────────────────────────────────────────────
    def _mean(vals: list) -> float | None:
        clean = [v for v in vals if v is not None]
        return sum(clean) / len(clean) if clean else None

    mean_faith  = _mean([r["faithfulness"]     for r in results])
    mean_rel    = _mean([r["answer_relevancy"]  for r in results])
    mean_fact   = _mean([r["factuality_score"]  for r in results])
    safety_rate = sum(1 for r in results if r["is_safe"]) / len(results)
    mean_lat    = _mean([r["latency_s"]         for r in results])

    n_corrected = sum(1 for r in results if r.get("correction_applied"))

    log.info("=== AGGREGATE ===")
    log.info("  faithfulness     : %s", _score_str(mean_faith))
    log.info("  answer_relevancy : %s", _score_str(mean_rel))
    log.info("  factuality       : %s", _score_str(mean_fact))
    log.info("  safety_rate      : %.1f%%", safety_rate * 100)
    log.info("  mean_latency     : %s s", _score_str(mean_lat))
    log.info("  corrections      : %d/%d", n_corrected, len(results))

    # ── Write Markdown report ─────────────────────────────────────────────────
    report_path = HERE / "track3_eval_report.md"
    lines: list[str] = [
        "# Track 3 Evaluation Report",
        "",
        f"**Dataset:** {args.dataset}  |  "
        f"**Questions evaluated:** {len(results)}  |  "
        f"**Seed:** {seed}  |  "
        f"**Date:** {time.strftime('%Y-%m-%d')}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Faithfulness (mean) | {_score_str(mean_faith)} |",
        f"| Answer Relevancy (mean) | {_score_str(mean_rel)} |",
        f"| Factuality (mean) | {_score_str(mean_fact)} |",
        f"| Safety Rate | {safety_rate * 100:.1f}% |",
        f"| Mean Latency (s) | {_score_str(mean_lat)} |",
        f"| Corrections Applied | {n_corrected}/{len(results)} |",
        "",
        "## Per-Question Breakdown",
        "",
        f"| # | {id_label} | Question | Faithfulness | Answer Rel. | Factuality | Safe | Latency | Corrected |",
        "|---|------|----------|-------------|-------------|------------|------|---------|-----------|",
    ]

    for i, r in enumerate(results, 1):
        q_short = r["question"][:60] + ("…" if len(r["question"]) > 60 else "")
        q_short = q_short.replace("|", "\\|")
        safe_cell = _safe_str(r["is_safe"], r["safety_flags"])
        corrected_cell = "Yes" if r.get("correction_applied") else "No"
        lines.append(
            f"| {i} "
            f"| {r['pubid']} "
            f"| {q_short} "
            f"| {_score_str(r['faithfulness'])} "
            f"| {_score_str(r['answer_relevancy'])} "
            f"| {r['factuality_score']:.2f} "
            f"| {safe_cell} "
            f"| {r['latency_s']:.2f}s "
            f"| {corrected_cell} |"
        )

    # ── Baseline comparison section (--compare) ───────────────────────────────
    if args.compare:
        bl_faiths = [r["baseline_faith"] for r in results if r.get("baseline_faith") is not None]
        t3_faiths = [r["faithfulness"]   for r in results if r.get("faithfulness")   is not None]
        bl_mean = _mean(bl_faiths)
        t3_mean = _mean(t3_faiths)

        def _delta_str(bl: float | None, t3: float | None) -> str:
            if bl is None or t3 is None:
                return "N/A"
            delta = t3 - bl
            sign = "+" if delta >= 0 else ""
            return f"{sign}{delta:.3f}"

        lines += [
            "",
            "## Baseline vs Track 3 Comparison",
            "",
            "| Metric | Baseline | Track 3 | Delta |",
            "|--------|---------|---------|-------|",
            f"| Faithfulness (mean) | {_score_str(bl_mean)} | {_score_str(t3_mean)} "
            f"| {_delta_str(bl_mean, t3_mean)} |",
            f"| Corrections applied | — | {n_corrected}/{len(results)} | — |",
            "",
            "### Per-question delta",
            "",
            f"| # | {id_label} | Baseline Faith | Track 3 Faith | Δ Faith | Corrected |",
            "|---|------|---------------|--------------|---------|-----------|",
        ]
        for i, r in enumerate(results, 1):
            bl_f = r.get("baseline_faith")
            t3_f = r.get("faithfulness")
            corrected_cell = "Yes" if r.get("correction_applied") else "No"
            lines.append(
                f"| {i} "
                f"| {r['pubid']} "
                f"| {_score_str(bl_f)} "
                f"| {_score_str(t3_f)} "
                f"| {_delta_str(bl_f, t3_f)} "
                f"| {corrected_cell} |"
            )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("Report written → %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
