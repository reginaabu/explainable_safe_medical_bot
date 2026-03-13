"""
kg_expand.py – Track 2/3: Knowledge-Graph query expansion

Public API
----------
extract_entities(text)  → list[tuple[str, str]]   (entity_text, entity_type)
expand_query(query)     → str                       expanded query string
get_entity_neighbors(entity, top_n=5)
                        → list[tuple[str, int]]     [(neighbour, count), ...]

The module loads triples.csv once at first call and caches in memory.
The SciSpacy NLP model is also loaded once and cached.

Models tried (in order):
  1. en_ner_bc5cdr_md   → DISEASE, CHEMICAL   (preferred)
  2. en_core_sci_sm     → ENTITY              (fallback)

Install models with:
  pip install scispacy
  pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz
  pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
TRIPLES_CSV = _HERE / "triples.csv"

# ── Constants ─────────────────────────────────────────────────────────────────
# Entities appearing in more than this many documents are too generic
# (e.g. "cells", "patients") and add noise to query expansion.
MAX_DOC_FREQ = 100   # out of 1,000 corpus docs = top 10% threshold

# ── Module-level caches ────────────────────────────────────────────────────────
_nlp = None          # spacy model
_graph: Optional[dict] = None    # {entity: {neighbour: count}}
_doc_freq: Optional[dict] = None # {entity: num_docs_containing_it}


# ── NLP loader ────────────────────────────────────────────────────────────────
def _load_nlp():
    """Load SciSpacy model (bc5cdr preferred, sci_sm fallback)."""
    global _nlp
    if _nlp is not None:
        return _nlp

    # Try bc5cdr first (DISEASE + CHEMICAL labels)
    try:
        import spacy
        _nlp = spacy.load("en_ner_bc5cdr_md")
        return _nlp
    except OSError:
        pass

    # Fallback: en_core_sci_sm (single ENTITY label)
    try:
        import spacy
        _nlp = spacy.load("en_core_sci_sm")
        return _nlp
    except OSError as exc:
        raise RuntimeError(
            "No SciSpacy model found. Install with:\n"
            "  pip install scispacy\n"
            "  pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/"
            "releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz"
        ) from exc


# ── Graph loader ───────────────────────────────────────────────────────────────
def _load_graph() -> dict:
    """
    Load triples.csv into an in-memory adjacency dict and compute doc frequencies.

    Structure: graph[head][tail] = co-occurrence count
    Also populates _doc_freq[entity] = number of docs the entity appears in,
    derived from 'mentioned_in' edges (entity → doc_id).
    """
    global _graph, _doc_freq
    if _graph is not None:
        return _graph

    if not TRIPLES_CSV.exists():
        raise FileNotFoundError(
            f"triples.csv not found at {TRIPLES_CSV}. "
            "Run track2_build_kg.py first to generate it."
        )

    graph: dict = defaultdict(lambda: defaultdict(int))
    doc_sets: dict = defaultdict(set)   # entity → set of doc_ids

    with open(TRIPLES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            relation = row["relation"]
            if relation == "co_occurs_with":
                head = row["head"].lower().strip()
                tail = row["tail"].lower().strip()
                if head and tail and head != tail:
                    graph[head][tail] += 1
                    graph[tail][head] += 1   # symmetric
            elif relation == "mentioned_in":
                entity = row["head"].lower().strip()
                doc_id = row["tail"].strip()
                if entity and doc_id:
                    doc_sets[entity].add(doc_id)

    _graph = dict(graph)
    _doc_freq = {ent: len(docs) for ent, docs in doc_sets.items()}
    return _graph


# ── Public API ─────────────────────────────────────────────────────────────────
def extract_entities(text: str) -> list[tuple[str, str]]:
    """
    Run SciSpacy NER on *text* and return a list of (entity_text, entity_type).

    Entities are lowercased and deduplicated within the same text.
    Short tokens (< 3 chars) are filtered out.
    """
    nlp = _load_nlp()
    doc = nlp(text)

    seen: set[str] = set()
    results: list[tuple[str, str]] = []
    for ent in doc.ents:
        norm = ent.text.lower().strip()
        if len(norm) < 3 or norm in seen:
            continue
        seen.add(norm)
        results.append((norm, ent.label_))
    return results


def get_entity_neighbors(
    entity: str,
    top_n: int = 5,
    max_doc_freq: int = MAX_DOC_FREQ,
) -> list[tuple[str, int]]:
    """
    Return the top-N co-occurring entities for *entity* from the KG.

    Neighbours that appear in more than *max_doc_freq* documents are excluded
    — they are too generic (e.g. "cells", "patients") and add noise.

    Returns a list of (neighbour_text, count) sorted descending by count.
    Returns an empty list if the entity is not in the graph.
    """
    graph = _load_graph()
    entity = entity.lower().strip()
    if entity not in graph:
        return []

    neighbours = {
        nbr: cnt
        for nbr, cnt in graph[entity].items()
        if (_doc_freq or {}).get(nbr, 0) <= max_doc_freq
    }
    sorted_neighbours = sorted(neighbours.items(), key=lambda x: x[1], reverse=True)
    return sorted_neighbours[:top_n]


def expand_query(
    query: str,
    top_entities: int = 5,
    top_neighbours: int = 3,
) -> str:
    """
    Expand *query* using KG co-occurrence neighbours.

    Steps:
      1. Extract biomedical entities from the query text.
      2. For each entity (up to *top_entities*), fetch its top KG neighbours.
      3. Append unique neighbours to the query string.

    Parameters
    ----------
    query          : original query string
    top_entities   : max number of query entities to expand from
    top_neighbours : max neighbours to add per entity

    Returns
    -------
    Expanded query string.  If no neighbours found, returns original query.
    """
    entities = extract_entities(query)
    if not entities:
        return query

    expansion_terms: list[str] = []
    seen_terms: set[str] = set(query.lower().split())

    for ent_text, _ in entities[:top_entities]:
        neighbours = get_entity_neighbors(ent_text, top_n=top_neighbours)
        for neighbour, _count in neighbours:
            if neighbour not in seen_terms:
                expansion_terms.append(neighbour)
                seen_terms.add(neighbour)

    if not expansion_terms:
        return query

    return query + " " + " ".join(expansion_terms)


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from utils.logging_config import get_logger as _get_logger

    _log = _get_logger("kg_expand")

    if len(sys.argv) < 2:
        _log.error('Usage: python kg_expand.py "<query>"')
        sys.exit(1)

    q = " ".join(sys.argv[1:])
    _log.info("Original : %s", q)

    ents = extract_entities(q)
    _log.info("Entities : %s", ents)

    expanded = expand_query(q)
    _log.info("Expanded : %s", expanded)
