"""
reranker.py – Cross-encoder reranking layer (Track 3 enhancement)

Uses:  cross-encoder/ms-marco-MiniLM-L-6-v2  (fast, ~85 MB)
       Falls back gracefully if sentence-transformers is not installed.

Public API
----------
is_available() -> bool
rerank(query, candidate_docs, top_k) -> list[dict]
    candidate_docs : list of {"doc_id": str, "text": str, ...}
    returns        : same dicts, sorted by cross-encoder score descending,
                     with "ce_score" key added

Install:
    pip install sentence-transformers
"""

from __future__ import annotations

from typing import Optional

from utils.logging_config import get_logger

logger = get_logger(__name__)

_model = None
_available: Optional[bool] = None

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def is_available() -> bool:
    """Return True if sentence-transformers + model can be loaded."""
    global _available
    if _available is not None:
        return _available
    try:
        from sentence_transformers import CrossEncoder  # noqa: F401
        _available = True
    except ImportError:
        _available = False
    return _available


def _load_model():
    global _model
    if _model is not None:
        return _model
    logger.info("Loading cross-encoder model: %s", MODEL_NAME)
    from sentence_transformers import CrossEncoder
    _model = CrossEncoder(MODEL_NAME, max_length=512)
    logger.info("Cross-encoder model loaded.")
    return _model


def rerank(
    query: str,
    candidate_docs: list[dict],
    top_k: int,
) -> list[dict]:
    """
    Re-score *candidate_docs* with a cross-encoder and return top_k.

    Parameters
    ----------
    query          : raw query string (not pre-tokenised)
    candidate_docs : list of dicts, each must have a "text" key
    top_k          : how many to return

    Returns
    -------
    List of dicts (subset of candidate_docs) sorted by ce_score descending.
    Each dict gets a new "ce_score" float key.
    """
    if not candidate_docs:
        return []

    model = _load_model()
    pairs = [[query, doc["text"]] for doc in candidate_docs]
    raw_scores = model.predict(pairs, show_progress_bar=False)

    scored = [
        {**doc, "ce_score": float(score)}
        for doc, score in zip(candidate_docs, raw_scores)
    ]
    scored.sort(key=lambda x: x["ce_score"], reverse=True)
    return scored[:top_k]
