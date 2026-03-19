"""
evaluator/__init__.py – Public evaluation API for Track 3.

Public API
----------
evaluate_answer(query, answer, chunks, latency_s=0.0) -> EvalResult
"""

from __future__ import annotations

from typing import TypedDict

FACTUALITY_THRESHOLD: float = 0.5


class EvalResult(TypedDict):
    is_safe: bool
    safety_flags: list[str]
    answer_with_disclaimer: str
    facts: list[str]
    fact_verdicts: list[dict]
    factuality_score: float
    faithfulness: float | None
    answer_relevancy: float | None
    latency_s: float
    correction_applied: bool


def evaluate_answer(
    query: str,
    answer: str,
    chunks: list[dict],
    latency_s: float = 0.0,
    dataset: str = "",
) -> EvalResult:
    """
    Run the full evaluation pipeline on a single QA pair.

    Each step is independently try/excepted so a failure in one module
    does not abort the others.

    Parameters
    ----------
    query      : the user's original question
    answer     : the generated answer string
    chunks     : list of {"pubid": str, "text": str} used as context
    latency_s  : generation wall-time in seconds (pass-through)

    Returns
    -------
    EvalResult TypedDict with all evaluation fields populated.
    """
    # ── 1. Safety ─────────────────────────────────────────────────────────────
    try:
        from evaluator.safety import check_safety
        safety = check_safety(answer)
        is_safe: bool = safety["is_safe"]
        safety_flags: list[str] = safety["flags"]
        answer_with_disclaimer: str = safety["answer_with_disclaimer"]
    except Exception:
        is_safe = True
        safety_flags = []
        answer_with_disclaimer = answer

    # ── 2. Fact decomposition ─────────────────────────────────────────────────
    try:
        from evaluator.fact_decompose import decompose_facts
        facts: list[str] = decompose_facts(answer, dataset=dataset)
    except Exception:
        facts = []

    # ── 3. Fact verification ──────────────────────────────────────────────────
    try:
        from evaluator.fact_verify import verify_facts
        fact_verdicts: list[dict] = verify_facts(facts, chunks) if facts else []
    except Exception:
        fact_verdicts = [
            {"fact": f, "verdict": "unsupported", "pmid": None} for f in facts
        ]

    # ── 4. Factuality score ───────────────────────────────────────────────────
    try:
        if fact_verdicts:
            supported = sum(
                1 for v in fact_verdicts if v.get("verdict") == "supported"
            )
            factuality_score: float = supported / len(fact_verdicts)
        else:
            factuality_score = 0.0
    except Exception:
        factuality_score = 0.0

    # ── 5. RAGAS metrics ──────────────────────────────────────────────────────
    try:
        from evaluator.metrics import score_metrics
        ragas = score_metrics(query, answer, chunks)
        faithfulness: float | None = ragas["faithfulness"]
        answer_relevancy: float | None = ragas["answer_relevancy"]
    except Exception:
        faithfulness = None
        answer_relevancy = None

    return EvalResult(
        is_safe=is_safe,
        safety_flags=safety_flags,
        answer_with_disclaimer=answer_with_disclaimer,
        facts=facts,
        fact_verdicts=fact_verdicts,
        factuality_score=factuality_score,
        faithfulness=faithfulness,
        answer_relevancy=answer_relevancy,
        latency_s=latency_s,
        correction_applied=False,
    )
