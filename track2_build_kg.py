"""
Track 2/3 – Knowledge Graph construction + KG-augmented BM25 evaluation
=========================================================================

Run:
    python track2_build_kg.py

Outputs (all written to the same directory as this script):
    pubmedqa_subset.csv   – 1 000 records: doc_id, question, context
    entities.csv          – NER output: doc_id, entity_text, entity_type
    triples.csv           – KG edges: head, relation, tail, doc_id
    eval_results.md       – Recall/MRR/nDCG before vs after expansion

Dependencies:
    pip install -r requirements.txt
    pip install scispacy
    pip install https://s3-us-west-2.amazonaws.com/ai2-s3-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz
    # Fallback model (if bc5cdr is not available):
    pip install https://s3-us-west-2.amazonaws.com/ai2-s3-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from datasets import load_dataset
from rank_bm25 import BM25Okapi
from tqdm import tqdm

from utils.logging_config import get_logger

logger = get_logger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent
SUBSET_CSV   = HERE / "pubmedqa_subset.csv"
ENTITIES_CSV = HERE / "entities.csv"
TRIPLES_CSV  = HERE / "triples.csv"
EVAL_MD      = HERE / "eval_results.md"

# ── Constants ──────────────────────────────────────────────────────────────────
CHUNK_SIZE        = 400   # words per chunk
CHUNK_OVERLAP     = 50    # word overlap between consecutive chunks
CHUNK_STEP        = CHUNK_SIZE - CHUNK_OVERLAP   # = 350

MAX_ENTS_PER_DOC  = 20   # cap entities per doc before building combinations
                          # prevents O(n²) explosion on large abstracts
TOP_K_VALS        = [5, 10]
MRR_K             = 10
NDCG_K            = 10

EXPAND_TOP_ENTS   = 5    # entities from query to expand from
EXPAND_TOP_NBRS   = 3    # KG neighbours added per entity


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 – Load PubMedQA and save subset CSV
# ══════════════════════════════════════════════════════════════════════════════
def load_pubmedqa() -> list[dict]:
    """Load pqa_labeled, flatten context, return list of record dicts."""
    logger.info("[1/5] Loading PubMedQA …")
    dataset = load_dataset("pubmed_qa", "pqa_labeled", trust_remote_code=True)

    records: list[dict] = []
    for item in dataset["train"]:
        context_flat = " ".join(item["context"]["contexts"])
        records.append({
            "doc_id":   str(item["pubid"]),
            "question": item["question"],
            "context":  context_flat,
        })

    logger.info("    Loaded %d records.", len(records))
    return records


def save_subset_csv(records: list[dict]) -> None:
    logger.info("    Saving %s …", SUBSET_CSV.name)
    with open(SUBSET_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["doc_id", "question", "context"])
        writer.writeheader()
        writer.writerows(records)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 – Entity extraction with SciSpacy
# ══════════════════════════════════════════════════════════════════════════════
def _load_spacy_model():
    """Load bc5cdr model (DISEASE+CHEMICAL) or fall back to sci_sm (ENTITY)."""
    try:
        import spacy
        nlp = spacy.load("en_ner_bc5cdr_md")
        logger.info("    Using model: en_ner_bc5cdr_md (DISEASE, CHEMICAL)")
        return nlp
    except OSError:
        pass
    try:
        import spacy
        nlp = spacy.load("en_core_sci_sm")
        logger.info("    Using model: en_core_sci_sm (ENTITY)")
        return nlp
    except OSError:
        logger.error(
            "No SciSpacy model found. Install with:\n"
            "  pip install scispacy\n"
            "  pip install https://s3-us-west-2.amazonaws.com/ai2-s3-scispacy/"
            "releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz"
        )
        sys.exit(1)


def extract_entities_batch(
    records: list[dict],
    nlp,
    batch_size: int = 64,
) -> list[dict]:
    """
    Run NER on all records in batches.

    Returns list of dicts: {doc_id, entity_text, entity_type}.
    Entities are lowercased and deduplicated per document.
    Short tokens (< 3 chars) are filtered out.
    """
    logger.info("[2/5] Extracting entities with SciSpacy …")
    entity_rows: list[dict] = []

    texts  = [rec["context"] for rec in records]
    docids = [rec["doc_id"]  for rec in records]

    pipe = nlp.pipe(texts, batch_size=batch_size)
    for doc_id, spacy_doc in tqdm(
        zip(docids, pipe), total=len(docids), desc="NER"
    ):
        seen: set[str] = set()
        for ent in spacy_doc.ents:
            norm = ent.text.lower().strip()
            if len(norm) < 3 or norm in seen:
                continue
            seen.add(norm)
            entity_rows.append({
                "doc_id":      doc_id,
                "entity_text": norm,
                "entity_type": ent.label_,
            })

    logger.info("    Extracted %d entity mentions.", len(entity_rows))
    return entity_rows


def save_entities_csv(entity_rows: list[dict]) -> None:
    logger.info("    Saving %s …", ENTITIES_CSV.name)
    with open(ENTITIES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["doc_id", "entity_text", "entity_type"]
        )
        writer.writeheader()
        writer.writerows(entity_rows)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 – Build Knowledge Graph triples
# ══════════════════════════════════════════════════════════════════════════════
def build_triples(entity_rows: list[dict]) -> list[dict]:
    """
    Build KG triples from entity_rows.

    Two relation types:
      co_occurs_with : entity pairs that appear together in the same document
                       (upper-triangular only; undirected edge)
      mentioned_in   : entity → doc_id (provenance link)

    Caps entities at MAX_ENTS_PER_DOC per document before combination to
    avoid quadratic explosion.
    """
    logger.info("[3/5] Building KG triples …")

    # Group entities by doc_id
    doc_entities: dict[str, list[str]] = defaultdict(list)
    for row in entity_rows:
        doc_entities[row["doc_id"]].append(row["entity_text"])

    triple_rows: list[dict] = []

    # Track co-occurrence counts to deduplicate
    co_occur_counts: dict[tuple[str, str], int] = defaultdict(int)

    for doc_id, ents in tqdm(doc_entities.items(), desc="Triples"):
        # Deduplicate and cap
        unique_ents = list(dict.fromkeys(ents))[:MAX_ENTS_PER_DOC]

        # co_occurs_with edges (undirected — store sorted pair)
        for a, b in itertools.combinations(unique_ents, 2):
            pair = (min(a, b), max(a, b))
            co_occur_counts[pair] += 1

        # mentioned_in edges
        for ent in unique_ents:
            triple_rows.append({
                "head":     ent,
                "relation": "mentioned_in",
                "tail":     doc_id,
                "doc_id":   doc_id,
            })

    # Add co_occurs_with triples (one row per unique pair)
    for (a, b), count in co_occur_counts.items():
        triple_rows.append({
            "head":     a,
            "relation": "co_occurs_with",
            "tail":     b,
            "doc_id":   "",   # not tied to a single doc
        })

    co_count  = sum(1 for r in triple_rows if r["relation"] == "co_occurs_with")
    men_count = sum(1 for r in triple_rows if r["relation"] == "mentioned_in")
    logger.info("    co_occurs_with: %d  |  mentioned_in: %d", co_count, men_count)
    return triple_rows


def save_triples_csv(triple_rows: list[dict]) -> None:
    logger.info("    Saving %s …", TRIPLES_CSV.name)
    with open(TRIPLES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["head", "relation", "tail", "doc_id"]
        )
        writer.writeheader()
        writer.writerows(triple_rows)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 – BM25 index + evaluation helpers
# ══════════════════════════════════════════════════════════════════════════════
def build_bm25_corpus(records: list[dict]) -> tuple[BM25Okapi, list[dict]]:
    """Chunk records and build BM25Okapi index (same params as Track 1)."""
    logger.info("[4/5] Building BM25 index …")
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
    bm25 = BM25Okapi(tokenized)
    logger.info("    %d chunks indexed.", len(corpus))
    return bm25, corpus


def _recall_at_k(ranked_ids: list[str], gold_id: str, k: int) -> float:
    return 1.0 if gold_id in ranked_ids[:k] else 0.0


def _rr_at_k(ranked_ids: list[str], gold_id: str, k: int) -> float:
    for i, pid in enumerate(ranked_ids[:k], 1):
        if pid == gold_id:
            return 1.0 / i
    return 0.0


def _ndcg_at_k(ranked_ids: list[str], gold_id: str, k: int) -> float:
    dcg = 0.0
    for i, pid in enumerate(ranked_ids[:k], 1):
        if pid == gold_id:
            dcg = 1.0 / math.log2(i + 1)
            break
    ideal_dcg = 1.0  # single relevant doc always at rank 1 ideally
    return dcg / ideal_dcg


def evaluate(
    records: list[dict],
    bm25: BM25Okapi,
    corpus: list[dict],
    query_fn,        # callable(question: str) → query_str
    label: str = "",
) -> dict:
    """
    Run retrieval with query_fn over all records.
    Returns dict of metric → score.
    """
    metrics_accum = defaultdict(list)

    for rec in tqdm(records, desc=f"Eval {label}", leave=False):
        query_str = query_fn(rec["question"])
        tokens    = query_str.lower().split()
        scores    = bm25.get_scores(tokens)

        # Rank chunks by score; collect top-NDCG_K doc_ids (in order)
        top_idx = np.argsort(scores)[::-1][:NDCG_K]
        ranked_pubids: list[str] = []
        seen_ids: set[str] = set()
        for idx in top_idx:
            pid = corpus[idx]["doc_id"]
            if pid not in seen_ids:
                ranked_pubids.append(pid)
                seen_ids.add(pid)

        gold = rec["doc_id"]
        for k in TOP_K_VALS:
            metrics_accum[f"Recall@{k}"].append(_recall_at_k(ranked_pubids, gold, k))
        metrics_accum[f"MRR@{MRR_K}"].append(_rr_at_k(ranked_pubids, gold, MRR_K))
        metrics_accum[f"nDCG@{NDCG_K}"].append(_ndcg_at_k(ranked_pubids, gold, NDCG_K))

    return {k: float(np.mean(v)) for k, v in metrics_accum.items()}


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 – KG query expansion + evaluation + write report
# ══════════════════════════════════════════════════════════════════════════════
def _build_graph_from_triples(triple_rows: list[dict]) -> dict:
    """Build in-memory graph from triple_rows (avoids re-reading CSV)."""
    graph: dict = defaultdict(lambda: defaultdict(int))
    for row in triple_rows:
        if row["relation"] != "co_occurs_with":
            continue
        head = row["head"].lower().strip()
        tail = row["tail"].lower().strip()
        if head and tail and head != tail:
            graph[head][tail] += 1
            graph[tail][head] += 1
    return graph


def make_expand_fn(nlp, graph: dict, top_ents: int, top_nbrs: int):
    """Return a closure that expands a query using the KG graph."""

    def expand_query(query: str) -> str:
        doc = nlp(query)
        entities = [
            ent.text.lower().strip()
            for ent in doc.ents
            if len(ent.text.strip()) >= 3
        ][:top_ents]

        expansion_terms: list[str] = []
        seen = set(query.lower().split())

        for ent in entities:
            if ent not in graph:
                continue
            neighbours = sorted(
                graph[ent].items(), key=lambda x: x[1], reverse=True
            )[:top_nbrs]
            for nbr, _ in neighbours:
                if nbr not in seen:
                    expansion_terms.append(nbr)
                    seen.add(nbr)

        if not expansion_terms:
            return query
        return query + " " + " ".join(expansion_terms)

    return expand_query


def write_eval_results(
    metrics_original: dict,
    metrics_expanded: dict,
) -> None:
    """Write eval_results.md with a before/after comparison table."""
    logger.info("    Writing %s …", EVAL_MD.name)

    metric_keys = [f"Recall@{k}" for k in TOP_K_VALS] + [
        f"MRR@{MRR_K}",
        f"nDCG@{NDCG_K}",
    ]

    lines = [
        "# Evaluation Results – BM25 vs KG-Expanded BM25",
        "",
        "**Dataset:** PubMedQA `pqa_labeled` · 1,000 questions  ",
        "**Gold matching:** exact PMID (`doc_id = pubid`)  ",
        "**Chunking:** 400 words, 50-word overlap  ",
        "**KG expansion:** SciSpacy NER → top co-occurrence neighbours  ",
        "",
        "## Metrics",
        "",
        "| Metric | BM25 (baseline) | BM25 + KG Expansion | Δ |",
        "|--------|:--------------:|:------------------:|:--:|",
    ]

    for key in metric_keys:
        orig = metrics_original.get(key, 0.0)
        exp  = metrics_expanded.get(key, 0.0)
        delta = exp - orig
        sign  = "+" if delta >= 0 else ""
        lines.append(
            f"| {key} | {orig:.4f} | {exp:.4f} | {sign}{delta:.4f} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- BM25 baseline uses the same parameters as Track 1 (k1=1.5, b=0.75, whitespace tokenisation).",
        "- KG expansion appends the top co-occurring biomedical entities from the knowledge graph.",
        "- Co-occurrence edges are built from SciSpacy NER on the 1,000 PubMedQA abstracts.",
        f"- Expansion parameters: top_entities={EXPAND_TOP_ENTS}, top_neighbours={EXPAND_TOP_NBRS}.",
        "",
        "## Interpretation",
        "",
        "Positive Δ means KG expansion improved the metric.  ",
        "Negative Δ means the original query was more precise than the expanded version.",
        "This is expected for BM25: adding terms that are related but not literally in the",
        "gold abstract can hurt precision while improving recall on ambiguous queries.",
        "",
        "_Generated by `track2_build_kg.py`_",
    ]

    EVAL_MD.write_text("\n".join(lines), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    # 1. Load data
    records = load_pubmedqa()
    save_subset_csv(records)

    # 2. Entity extraction
    nlp          = _load_spacy_model()
    entity_rows  = extract_entities_batch(records, nlp)
    save_entities_csv(entity_rows)

    # 3. Build KG
    triple_rows = build_triples(entity_rows)
    save_triples_csv(triple_rows)

    # 4. BM25 index
    bm25, corpus = build_bm25_corpus(records)

    # 5. Evaluate original vs expanded
    logger.info("[5/5] Evaluating BM25 vs KG-expanded BM25 …")

    # Build in-memory graph (same data as triples.csv, avoids re-reading file)
    graph = _build_graph_from_triples(triple_rows)

    identity_fn = lambda q: q   # original query, no expansion
    expand_fn   = make_expand_fn(
        nlp, graph,
        top_ents=EXPAND_TOP_ENTS,
        top_nbrs=EXPAND_TOP_NBRS,
    )

    logger.info("    Running BM25 baseline …")
    metrics_orig = evaluate(records, bm25, corpus, identity_fn, label="baseline")

    logger.info("    Running KG-expanded BM25 …")
    metrics_exp  = evaluate(records, bm25, corpus, expand_fn,   label="expanded")

    write_eval_results(metrics_orig, metrics_exp)

    # Print summary (ASCII only — avoids Windows cp1252 encoding issues)
    sep = "-" * 50
    logger.info("\n%s", sep)
    header = f"{'Metric':<14} {'BM25':>10} {'BM25+KG':>10} {'Delta':>8}"
    logger.info(header)
    logger.info(sep)
    metric_keys = [f"Recall@{k}" for k in TOP_K_VALS] + [
        f"MRR@{MRR_K}", f"nDCG@{NDCG_K}"
    ]
    for k in metric_keys:
        orig  = metrics_orig.get(k, 0.0)
        exp   = metrics_exp.get(k,  0.0)
        delta = exp - orig
        sign  = "+" if delta >= 0 else ""
        logger.info("%s %10.4f %10.4f %s%7.4f", f"{k:<14}", orig, exp, sign, delta)
    logger.info(sep)
    logger.info("\nOutputs written to: %s", HERE)
    logger.info("  %s", SUBSET_CSV.name)
    logger.info("  %s", ENTITIES_CSV.name)
    logger.info("  %s", TRIPLES_CSV.name)
    logger.info("  %s", EVAL_MD.name)


if __name__ == "__main__":
    main()
