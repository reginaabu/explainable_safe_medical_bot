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
        from ragas.metrics._answer_relevance import AnswerRelevancy as _AnswerRelevancyClass
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

        # Create fresh metric instances (don't mutate global singletons)
        fm = _FaithfulnessClass()
        rm = _AnswerRelevancyClass()
        fm.llm = llm
        rm.llm = llm
        rm.embeddings = embeddings

        contexts = [c["text"] for c in chunks]
        sample = SingleTurnSample(
            user_input=query,
            response=answer,
            retrieved_contexts=contexts,
        )
        dataset = EvaluationDataset(samples=[sample])

        result = evaluate(
            dataset=dataset,
            metrics=[fm, rm],
            show_progress=False,
        )

        scores = result.to_pandas()
        faith_val = (
            float(scores["faithfulness"].iloc[0])
            if "faithfulness" in scores.columns
            else None
        )
        rel_val = (
            float(scores["answer_relevancy"].iloc[0])
            if "answer_relevancy" in scores.columns
            else None
        )

        return {"faithfulness": faith_val, "answer_relevancy": rel_val}

    except Exception:
        return _NULL
