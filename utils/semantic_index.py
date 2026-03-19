"""
utils/semantic_index.py – Dense and hybrid retrieval for Q&A datasets.

For corpora like MedQuAD where documents are Q&A pairs, BM25 on answer text
performs poorly because queries are questions, not answers.  This module encodes
*question* text with all-MiniLM-L6-v2 (already installed for RAGAS) and finds
nearest neighbours at query time.

Type-aware retrieval
--------------------
MedQuAD has multiple questions per condition of different types (information,
symptoms, treatment, causes, …).  The "What is X?" answer is the longest and
contains all keywords, so BM25 always returns it regardless of question type.
Pass q_type= to SemanticIndex.query() to restrict candidates to the same type.

Public API
----------
    idx = SemanticIndex(rows)                           # builds index over question fields
    chunks = idx.query(question, k=3)                   # plain cosine NN
    chunks = idx.query(question, k=3, q_type="symptoms") # type-filtered

    hidx = HybridIndex(rows, q_bm25, q_corpus)          # q_bm25 = question-field BM25
    chunks = hidx.query(question, k=3, alpha=0.6, q_type="symptoms")
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from rank_bm25 import BM25Okapi

log = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        log.info("Loading sentence-transformer model: %s", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


class SemanticIndex:
    """
    Dense retrieval index over the *question* field of a normalised row list.

    Each row becomes one retrieval unit: the question is encoded as the lookup
    key, and the context (answer) is returned as the chunk text.
    """

    def __init__(self, rows: list[dict]) -> None:
        # Filter to rows that have both a question and context
        self._rows = [r for r in rows if r["question"].strip() and r["context"].strip()]
        if not self._rows:
            raise ValueError("No rows with non-empty question and context fields.")

        # Build a type→[index] lookup for fast type-aware filtering
        self._type_index: dict[str, list[int]] = {}
        for i, r in enumerate(self._rows):
            qt = r.get("q_type", "").strip().lower()
            self._type_index.setdefault(qt, []).append(i)

        model = _get_model()
        questions = [r["question"] for r in self._rows]
        log.info("Encoding %d questions for semantic index …", len(questions))
        raw = model.encode(questions, show_progress_bar=False, convert_to_numpy=True)
        # L2-normalise so dot product == cosine similarity
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        self._embeddings: np.ndarray = raw / norms
        log.info("Semantic index ready (%d vectors, dim=%d, types=%d)",
                 len(self._rows), raw.shape[1], len(self._type_index))

    def query(
        self,
        question: str,
        top_k: int = 3,
        q_type: str | None = None,
    ) -> list[dict]:
        """
        Return top_k chunks sorted by cosine similarity to question.

        Parameters
        ----------
        question : query text
        top_k    : number of results
        q_type   : if provided, restrict candidates to rows with matching q_type.
                   Falls back to full index if the type pool is too small (<= top_k).
        """
        model = _get_model()
        qvec = model.encode([question], show_progress_bar=False, convert_to_numpy=True)[0]
        norm = np.linalg.norm(qvec)
        if norm > 0:
            qvec = qvec / norm

        # Determine candidate indices — type-filtered when possible
        candidate_indices: list[int] | None = None
        if q_type:
            pool = self._type_index.get(q_type.strip().lower(), [])
            if len(pool) > top_k:
                candidate_indices = pool

        if candidate_indices is not None:
            emb_subset = self._embeddings[candidate_indices]
            scores_subset = emb_subset @ qvec
            local_ranked = np.argsort(scores_subset)[::-1][:top_k]
            ranked_global = [candidate_indices[j] for j in local_ranked]
            scores_map = {candidate_indices[j]: float(scores_subset[j])
                          for j in local_ranked}
        else:
            scores_full = self._embeddings @ qvec
            ranked_global = list(np.argsort(scores_full)[::-1][:top_k])
            scores_map = {i: float(scores_full[i]) for i in ranked_global}

        results = []
        for i in ranked_global:
            row = self._rows[i]
            results.append({
                "pubid":     row["doc_id"],
                "text":      row["context"],
                "sem_score": scores_map[i],
            })
        return results


class HybridIndex:
    """
    Reciprocal Rank Fusion (RRF) of BM25 and semantic retrieval.

    For Q&A datasets (MedQuAD), pass a question-field BM25 (built on question
    text rather than answer text) so both signals search the same field as the
    semantic index.  Also pass alpha=0.6 to favour the semantic component.

    alpha controls how much to weight semantic vs BM25:
      alpha=0.0  → pure BM25
      alpha=1.0  → pure semantic
      alpha=0.6  → semantic-biased (recommended for Q&A datasets)
    """

    _RRF_K = 60  # standard RRF constant

    def __init__(
        self,
        rows: list[dict],
        bm25: "BM25Okapi",
        corpus: list[dict],
    ) -> None:
        self._bm25   = bm25
        self._corpus = corpus
        self._sem    = SemanticIndex(rows)
        # Build pubid → context lookup so BM25-ranked results always return
        # answer/context text (not question text from q_corpus).
        self._pubid_to_context: dict[str, str] = {
            r["doc_id"]: r["context"] for r in rows
            if r.get("context", "").strip()
        }

    def query(
        self,
        question: str,
        top_k: int = 3,
        alpha: float = 0.6,
        q_type: str | None = None,
    ) -> list[dict]:
        """Return top_k chunks using RRF over BM25 and semantic rankings."""
        candidate_n = max(top_k * 4, 20)

        # ── BM25 candidates ───────────────────────────────────────────────────
        bm25_scores = self._bm25.get_scores(question.lower().split())
        bm25_ranked = np.argsort(bm25_scores)[::-1][:candidate_n]
        # map corpus index → {"pubid", "text"} chunk with its BM25 rank
        bm25_chunks: dict[int, dict] = {}
        for rank, idx in enumerate(bm25_ranked):
            if bm25_scores[idx] > 0:
                bm25_chunks[idx] = {**self._corpus[idx], "bm25_rank": rank}

        # ── Semantic candidates (type-filtered when q_type provided) ──────────
        sem_results = self._sem.query(question, top_k=candidate_n, q_type=q_type)
        # key by (pubid, text) to deduplicate against BM25 corpus
        sem_by_key: dict[tuple, tuple[int, dict]] = {}
        for rank, chunk in enumerate(sem_results):
            key = (chunk["pubid"], chunk["text"][:50])
            sem_by_key[key] = (rank, chunk)

        # ── RRF merge ─────────────────────────────────────────────────────────
        # Collect all candidate doc identifiers
        all_keys: set[tuple] = set()
        bm25_key_to_rank: dict[tuple, int] = {}
        for rank, idx in enumerate(bm25_ranked):
            key = (self._corpus[idx]["pubid"], self._corpus[idx]["text"][:50])
            all_keys.add(key)
            bm25_key_to_rank[key] = rank

        sem_key_to_rank: dict[tuple, int] = {}
        for key, (rank, _) in sem_by_key.items():
            all_keys.add(key)
            sem_key_to_rank[key] = rank

        k = self._RRF_K
        scored: list[tuple[float, tuple]] = []
        for key in all_keys:
            bm25_r = bm25_key_to_rank.get(key, candidate_n)
            sem_r  = sem_key_to_rank.get(key, candidate_n)
            rrf = (1 - alpha) * (1 / (k + bm25_r)) + alpha * (1 / (k + sem_r))
            scored.append((rrf, key))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Reconstruct chunk dicts for top_k winners
        # Build a quick lookup: key → chunk
        key_to_chunk: dict[tuple, dict] = {}
        for idx in bm25_ranked:
            c = self._corpus[idx]
            key_to_chunk[(c["pubid"], c["text"][:50])] = c
        for key, (_, chunk) in sem_by_key.items():
            key_to_chunk.setdefault(key, chunk)

        # Build pubid → sem_score for gate checks
        pubid_to_sem: dict[str, float] = {
            chunk["pubid"]: chunk.get("sem_score", 0.0)
            for _, chunk in sem_by_key.values()
        }

        results = []
        seen_pubids: set[str] = set()
        for _, key in scored[:top_k]:
            chunk = key_to_chunk.get(key)
            if chunk:
                pubid = chunk["pubid"]
                if pubid in seen_pubids:
                    continue  # skip duplicate pubid (q-text and ctx-text both ranked)
                seen_pubids.add(pubid)
                # Always return the answer/context text, not the question text
                # (BM25 is built on questions for ranking but context is the evidence)
                context = self._pubid_to_context.get(pubid, chunk["text"])
                results.append({
                    "pubid":     pubid,
                    "text":      context,
                    "sem_score": pubid_to_sem.get(pubid, 0.0),
                })

        return results
