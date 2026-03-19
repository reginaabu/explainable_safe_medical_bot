"""
evaluator/metrics.py – RAGAS faithfulness + answer_relevancy scoring.

Uses:
- Claude haiku (claude-haiku-4-5-20251001) via ragas.llms.base.LangchainLLMWrapper
  wrapping langchain_anthropic.ChatAnthropic
- sentence-transformers/all-MiniLM-L6-v2 via custom BaseRagasEmbedding adapter

Uses old-style ragas Metric classes (ragas.metrics._faithfulness,
ragas.metrics._answer_relevance) which satisfy the isinstance(m, Metric)
check inside ragas.evaluate().

Public API
----------
score_metrics(query: str, answer: str, chunks: list[dict]) -> dict
    Returns {"faithfulness": float|None, "answer_relevancy": float|None}
"""

from __future__ import annotations

_NULL = {"faithfulness": None, "answer_relevancy": None}


def _geval_answer_relevancy(query: str, answer: str, api_key: str | None) -> float | None:
    """
    G-Eval: ask Claude haiku to directly score how well the answer addresses
    the question.  Replaces RAGAS reverse-question cosine similarity, which
    collapses to 0.0 for list answers (brand names, storage instructions, etc.)
    and safety-hedged clinical answers.

    Returns a float in [0.0, 1.0] or None on failure.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        prompt = (
            "You are evaluating a medical question-answering system.\n"
            "Score how well the ANSWER addresses the QUESTION on a scale from 0.0 to 1.0.\n\n"
            "Scoring guidelines:\n"
            "- 1.0: Answer directly and completely addresses the question\n"
            "- 0.7–0.9: Answer mostly addresses the question with minor gaps\n"
            "- 0.4–0.6: Answer partially addresses the question\n"
            "- 0.1–0.3: Answer barely addresses the question\n"
            "- 0.0: Answer does not address the question at all\n\n"
            f"QUESTION: {query}\n\n"
            f"ANSWER: {answer}\n\n"
            "Output ONLY a single decimal number between 0.0 and 1.0, nothing else."
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        return max(0.0, min(1.0, float(raw)))
    except Exception:
        return None

try:
    import ragas as _ragas_mod
    _RAGAS_OK = True
except ImportError:
    _RAGAS_OK = False


# ── Module-level cached embeddings (avoid reloading model per call) ───────────
_cached_embeddings = None


def _get_embeddings():
    """Return a cached BaseRagasEmbedding backed by all-MiniLM-L6-v2."""
    global _cached_embeddings
    if _cached_embeddings is not None:
        return _cached_embeddings

    from ragas.embeddings import BaseRagasEmbedding
    from sentence_transformers import SentenceTransformer

    class _STEmbedding(BaseRagasEmbedding):
        def __init__(self):
            super().__init__()
            self._model = SentenceTransformer("all-MiniLM-L6-v2")

        def embed_text(self, text: str, **kwargs) -> list[float]:
            return self._model.encode(text).tolist()

        async def aembed_text(self, text: str, **kwargs) -> list[float]:
            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._model.encode, text)

        def embed_texts(self, texts: list[str], **kwargs) -> list[list[float]]:
            return self._model.encode(texts).tolist()

        # Old-style ragas metrics call embed_query / embed_documents directly
        def embed_query(self, text: str) -> list[float]:
            return self._model.encode(text).tolist()

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return self._model.encode(texts).tolist()

    _cached_embeddings = _STEmbedding()
    return _cached_embeddings


def score_metrics(query: str, answer: str, chunks: list[dict]) -> dict:
    """
    Compute RAGAS faithfulness and answer_relevancy scores.

    Parameters
    ----------
    query  : the user's original question
    answer : the generated answer string
    chunks : list of {"pubid": str, "text": str} used as context

    Returns
    -------
    {"faithfulness": float|None, "answer_relevancy": float|None}
    """
    if not _RAGAS_OK:
        return _NULL

    try:
        import copy
        from langchain_anthropic import ChatAnthropic
        from ragas.llms.base import LangchainLLMWrapper
        from ragas.metrics._faithfulness import Faithfulness as _FaithfulnessClass
        from ragas import EvaluationDataset, SingleTurnSample, evaluate

        # Resolve API key (env or .streamlit/secrets.toml)
        import os
        from pathlib import Path as _Path
        _api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not _api_key:
            for _c in [_Path(__file__).parent / ".streamlit" / "secrets.toml",
                       _Path(__file__).parent.parent / ".streamlit" / "secrets.toml"]:
                if _c.exists():
                    for _l in _c.read_text(encoding="utf-8").splitlines():
                        if _l.strip().startswith("ANTHROPIC_API_KEY"):
                            _api_key = _l.partition("=")[2].strip().strip("\"'")
                            break
                if _api_key:
                    break

        # Wrap Langchain ChatAnthropic in the ragas BaseRagasLLM adapter
        lc_llm = ChatAnthropic(model="claude-haiku-4-5-20251001", max_tokens=4096,
                               anthropic_api_key=_api_key)
        llm = LangchainLLMWrapper(lc_llm)
        embeddings = _get_embeddings()

        # Faithfulness only — answer_relevancy is replaced by G-Eval below
        fm = _FaithfulnessClass()
        fm.llm = llm
        fm.embeddings = embeddings

        contexts = [c["text"] for c in chunks]
        sample = SingleTurnSample(
            user_input=query,
            response=answer,
            retrieved_contexts=contexts,
        )
        ragas_dataset = EvaluationDataset(samples=[sample])

        result = evaluate(
            dataset=ragas_dataset,
            metrics=[fm],
            show_progress=False,
        )

        scores = result.to_pandas()
        faith_val = (
            float(scores["faithfulness"].iloc[0])
            if "faithfulness" in scores.columns
            else None
        )

        # G-Eval answer relevancy: directly asks Claude haiku whether the answer
        # addresses the question.  Handles list answers, storage/disposal,
        # brand names and safety-hedged answers that cause RAGAS to return 0.0.
        rel_val = _geval_answer_relevancy(query, answer, _api_key)

        return {"faithfulness": faith_val, "answer_relevancy": rel_val}

    except Exception:
        return _NULL
