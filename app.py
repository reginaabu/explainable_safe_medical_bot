"""
Track 1 + 2/3 – BM25 Medical Retrieval  |  Streamlit demo
Run:  streamlit run app.py
"""

import os
from pathlib import Path

# Load API key from .streamlit/secrets.toml before any Anthropic client is initialised
if "ANTHROPIC_API_KEY" not in os.environ:
    _secrets_path = Path(__file__).parent / ".streamlit" / "secrets.toml"
    if _secrets_path.exists():
        for _line in _secrets_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line.startswith("ANTHROPIC_API_KEY"):
                _, _, _val = _line.partition("=")
                os.environ["ANTHROPIC_API_KEY"] = _val.strip().strip('"\'')
                break

import json
import streamlit as st
from datasets import load_dataset
from rank_bm25 import BM25Okapi
import numpy as np
from pathlib import Path

# Optional: anthropic version for caption
try:
    import anthropic as _anthropic
    _ANTHROPIC_VERSION = _anthropic.__version__
except ImportError:
    _ANTHROPIC_VERSION = None

HERE = Path(__file__).parent

# ── Logger ────────────────────────────────────────────────────────────────────
import logging as _logging

def _setup_logger() -> "_logging.Logger":
    _log_dir = HERE / "logs"
    _log_dir.mkdir(exist_ok=True)
    _logger = _logging.getLogger("arogyasaathi")
    if not _logger.handlers:
        _h = _logging.FileHandler(_log_dir / "app.log", encoding="utf-8")
        _h.setFormatter(_logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        _logger.addHandler(_h)
        _logger.setLevel(_logging.DEBUG)
    return _logger

_log = _setup_logger()

# ── Page config ───────────────────────────────────────────────────────────────
_debug_mode = st.query_params.get("debugMode", "").lower() == "true"

st.set_page_config(
    page_title="ArogyaSaathi",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded" if _debug_mode else "collapsed",
)

if not _debug_mode:
    # Hide the sidebar and its toggle arrow completely
    st.markdown(
        "<style>[data-testid='collapsedControl']{display:none}"
        " section[data-testid='stSidebar']{display:none}</style>",
        unsafe_allow_html=True,
    )

# ── Debug log viewer (sidebar, only when ?debugMode=true) ─────────────────────
_LOG_FILE = HERE / "logs" / "app.log"
if _debug_mode:
    with st.sidebar:
        st.header("Backend Logs")
        if _LOG_FILE.exists():
            _all_lines = _LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            _tail = _all_lines[-50:] if len(_all_lines) > 50 else _all_lines
            st.code("\n".join(_tail), language=None)
            st.caption(f"Last {len(_tail)} of {len(_all_lines)} lines · {_LOG_FILE.name}")
        else:
            st.caption("No logs yet — run a pipeline script to generate logs/app.log")


# ── Load tuned BM25 params (falls back to defaults if tune_bm25.py not run) ──
def _bm25_params() -> tuple[float, float]:
    p = HERE / "bm25_params.json"
    if p.exists():
        d = json.loads(p.read_text())
        return d["k1"], d["b"]
    return 1.5, 0.75   # BM25Okapi defaults


# ── Load BM25 index (cached) ──────────────────────────────────────────────────
@st.cache_resource(show_spinner="Building BM25 index … (first run only)")
def load_index():
    k1, b = _bm25_params()
    dataset = load_dataset("pubmed_qa", "pqa_labeled", trust_remote_code=True)

    records = []
    for item in dataset["train"]:
        context_flat = " ".join(item["context"]["contexts"])
        records.append({
            "pubid":    str(item["pubid"]),
            "question": item["question"],
            "context":  context_flat,
        })

    corpus = []
    for rec in records:
        words = rec["context"].split()
        start = 0
        while start < len(words):
            chunk = " ".join(words[start : start + 400])
            if chunk.strip():
                corpus.append({"pubid": rec["pubid"], "text": chunk})
            start += 350

    tokenized = [doc["text"].lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenized, k1=k1, b=b)
    return bm25, corpus, records, k1, b


# ── Load KG expander (cached, degrades gracefully) ────────────────────────────
@st.cache_resource(show_spinner="Loading KG expansion module …")
def load_kg_expander():
    try:
        from kg_expand import expand_query
        expand_query("test")   # warm up graph + NLP
        return expand_query
    except Exception:
        return None


# ── Load cross-encoder reranker (cached, degrades gracefully) ─────────────────
@st.cache_resource(show_spinner="Loading cross-encoder reranker …")
def load_reranker():
    try:
        from reranker import rerank, is_available
        if not is_available():
            return None
        # warm up
        rerank("test query", [{"text": "test doc", "pubid": "0"}], top_k=1)
        return rerank
    except Exception:
        return None


# ── Load RAG generator (cached, degrades gracefully) ──────────────────────────
@st.cache_resource(show_spinner="Loading RAG generator …")
def load_rag_generator():
    try:
        from rag_generate import generate_answer
        return generate_answer
    except Exception:
        return None


# ── Retrieval helpers ─────────────────────────────────────────────────────────
def bm25_retrieve(bm25, corpus, query_str: str, top_k: int):
    scores     = bm25.get_scores(query_str.lower().split())
    max_s      = scores.max()
    norm       = scores / max_s if max_s > 0 else scores   # normalise to [0,1]
    ranked_idx = np.argsort(scores)[::-1][:top_k]
    ranked_idx = [i for i in ranked_idx if scores[i] > 0]
    return ranked_idx, norm


def result_cards(ranked_idx, norm_scores, corpus, query: str = "",
                 rerank_fn=None, top_k: int = 5):
    if not ranked_idx:
        st.warning("No relevant documents found. Try rephrasing your question.")
        return

    # Optionally rerank
    if rerank_fn is not None:
        candidates = [corpus[i] for i in ranked_idx]
        reranked   = rerank_fn(query, candidates, top_k=len(candidates))
        _log.info(
            "RERANK | query=%r | top3_pmids=%s | top3_ce_scores=%s",
            query,
            [doc["pubid"] for doc in reranked[:3]],
            [f"{doc.get('ce_score', 'n/a'):.3f}" if isinstance(doc.get("ce_score"), float)
             else str(doc.get("ce_score", "n/a")) for doc in reranked[:3]],
        )
    else:
        reranked = [{"**orig_idx**": i, **corpus[i]} for i in ranked_idx]

    st.subheader(f"Top {min(len(reranked), top_k)} results")
    for rank, doc in enumerate(reranked[:top_k], 1):
        pubid  = doc["pubid"]
        pmurl  = f"https://pubmed.ncbi.nlm.nih.gov/{pubid}/"

        # Score to display: ce_score if reranked, else normalised BM25
        if "ce_score" in doc:
            score_label = "CE score"
            score_val   = doc["ce_score"]
            # CE scores from ms-marco are logits; apply sigmoid for [0,1]
            import math
            display_score = 1 / (1 + math.exp(-score_val))
        else:
            score_label = "BM25"
            orig_idx    = ranked_idx[rank - 1]
            display_score = float(norm_scores[orig_idx])

        with st.container(border=True):
            h_col, s_col = st.columns([5, 1])
            with h_col:
                st.markdown(
                    f"**#{rank}** &nbsp; 📄 [PMID {pubid}]({pmurl})",
                    unsafe_allow_html=True,
                )
            with s_col:
                st.markdown(
                    f"<div style='text-align:right;color:#555;font-size:0.82em;'>"
                    f"{score_label}<br><b>{display_score:.3f}</b></div>",
                    unsafe_allow_html=True,
                )

            snippet = doc["text"][:400].strip()
            if len(doc["text"]) > 400:
                snippet += "…"
            st.write(snippet)

            with st.expander("Show full chunk"):
                st.write(doc["text"])
                st.markdown(f"[Open on PubMed ↗]({pmurl})", unsafe_allow_html=True)


# ── Evaluation dashboard ───────────────────────────────────────────────────────
def _score_bar(score: float | None, width: int = 10) -> str:
    """Return a Unicode progress bar string, e.g. '████████░░' for 0.83."""
    if score is None:
        return "N/A"
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)


def _render_eval_dashboard(result: dict) -> None:
    """Render the inline evaluation dashboard below the answer box."""
    with st.container(border=True):
        st.markdown("#### Evaluation")

        if result.get("correction_applied"):
            st.info("🔄 Answer was automatically corrected (factuality was below threshold).")

        # Row 1: safety + latency
        r1_left, r1_right = st.columns(2)
        with r1_left:
            if result["is_safe"]:
                st.markdown("**Safety:** 🟢 SAFE")
            else:
                flags_short = ", ".join(result["safety_flags"][:3])
                st.markdown(f"**Safety:** 🔴 UNSAFE — `{flags_short}`")
        with r1_right:
            st.markdown(f"**Latency:** {result['latency_s']:.2f} s")

        # Row 2: RAGAS scores
        faith = result.get("faithfulness")
        rel   = result.get("answer_relevancy")

        faith_str = f"{faith:.2f}  {_score_bar(faith)}" if faith is not None else "N/A"
        rel_str   = f"{rel:.2f}  {_score_bar(rel)}"     if rel   is not None else "N/A"

        st.markdown(f"**Faithfulness:** &nbsp;&nbsp; {faith_str}", unsafe_allow_html=True)
        st.markdown(f"**Answer Relevance:** {rel_str}", unsafe_allow_html=True)

        # Row 3: Factuality summary
        verdicts = result.get("fact_verdicts", [])
        n_facts  = len(verdicts)
        if n_facts > 0:
            n_supported = sum(1 for v in verdicts if v.get("verdict") == "supported")
            pct = int(n_supported / n_facts * 100)
            st.markdown(
                f"**Factuality:** {n_supported}/{n_facts} facts supported ({pct}%)"
            )
            with st.expander("▼ Fact breakdown"):
                for v in verdicts:
                    verdict = v.get("verdict", "unsupported")
                    pmid    = v.get("pmid")
                    fact    = v.get("fact", "")
                    if verdict == "supported":
                        icon = "✅"
                    elif verdict == "contradicted":
                        icon = "❌"
                    else:
                        icon = "⚠️"
                    pmid_label = f" (PMID {pmid})" if pmid else " (unsupported)"
                    st.markdown(f'{icon} "{fact}"{pmid_label}')
        else:
            st.markdown("**Factuality:** N/A")


# ── KG triples loader ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _load_triples():
    """Returns (mentioned, cooccurs)
    mentioned : {doc_id: [entity, ...]}   from mentioned_in rows
    cooccurs  : {entity: set[entity]}      from co_occurs_with rows
    """
    import csv
    from collections import defaultdict
    path = HERE / "triples.csv"
    if not path.exists():
        return {}, {}
    mentioned = defaultdict(list)
    cooccurs  = defaultdict(set)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rel = row.get("relation", "").strip()
            h   = row.get("head", "").strip()
            t   = row.get("tail", "").strip()
            d   = row.get("doc_id", "").strip()
            if rel == "mentioned_in" and d:
                mentioned[d].append(h)
            elif rel == "co_occurs_with" and h and t:
                cooccurs[h].add(t)
                cooccurs[t].add(h)
    return dict(mentioned), dict(cooccurs)


def _chunk_kg_rels(pubid, mentioned, cooccurs, max_rels=2):
    doc_ents = set(mentioned.get(str(pubid), []))
    seen, out = set(), []
    for ent in doc_ents:
        for partner in cooccurs.get(ent, set()):
            if partner in doc_ents and ent != partner:
                key = tuple(sorted([ent, partner]))
                if key not in seen:
                    seen.add(key)
                    out.append((ent, partner))
                    if len(out) >= max_rels:
                        return out
    return out


def _render_why_panel(chunks: list) -> None:
    mentioned, cooccurs = _load_triples()
    with st.expander("💡 Why this answer? — Evidence sources"):
        for idx, chunk in enumerate(chunks, 1):
            pubid = chunk["pubid"]
            # 1-2 sentence snippet (≤200 chars)
            sentences = [s.strip() for s in chunk["text"].replace("\n", " ").split(". ") if s.strip()]
            snippet = ". ".join(sentences[:2])
            if len(snippet) > 200:
                snippet = snippet[:197] + "…"
            if snippet and not snippet.endswith("."):
                snippet += "."

            pmurl = f"https://pubmed.ncbi.nlm.nih.gov/{pubid}/"
            st.markdown(f"**Source {idx}:** [PMID {pubid}]({pmurl})")
            st.caption(snippet)

            rels = _chunk_kg_rels(pubid, mentioned, cooccurs)
            if rels:
                for head, tail in rels:
                    st.markdown(
                        f"<span style='font-size:0.82em;color:#555;'>"
                        f"🔗 <code>{head}</code> &nbsp;→&nbsp; "
                        f"co-occurs with &nbsp;→&nbsp; <code>{tail}</code>"
                        f"</span>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("_No KG relations found for this source._")

            if idx < len(chunks):
                st.markdown("---")


def _render_citation_gate(answer: str) -> None:
    import re
    sentences = re.split(r'(?<=[.!?])\s+', answer.strip())
    pmid_re   = re.compile(r'\(PMID\s*\d+\)', re.IGNORECASE)

    flagged = [s for s in sentences if len(s.split()) > 5 and not pmid_re.search(s)]
    if not flagged:
        return

    with st.expander(f"⚠️ Citation check — {len(flagged)} sentence(s) without a PMID", expanded=False):
        st.caption("Sentences longer than 5 words with no inline (PMID …) citation are highlighted.")
        for sentence in sentences:
            if not sentence.strip():
                continue
            if len(sentence.split()) > 5 and not pmid_re.search(sentence):
                st.markdown(
                    f"<span style='background:#fff3cd;padding:2px 6px;"
                    f"border-radius:3px;display:inline-block;margin:2px 0;'>"
                    f"⚠️ {sentence}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(sentence)


# ── Background eval — thread + polling fragment ───────────────────────────────
import hashlib
import threading

@st.cache_resource
def _eval_store() -> dict:
    """Module-level dict persisted by Streamlit's resource cache.
    Keyed by a deterministic hash of (query, answer).
    Values: None (pending) | dict (result).
    """
    return {}


def _eval_store_key(query: str, answer: str) -> str:
    return hashlib.md5(f"{query}||{answer}".encode()).hexdigest()[:16]


def _run_eval_thread(store: dict, key: str, query: str, answer: str,
                     chunks: list, latency_s: float) -> None:
    """Runs in a daemon thread; stores result dict into *store* when done."""
    try:
        from evaluator import evaluate_answer as _fn
        result = _fn(query=query, answer=answer, chunks=chunks, latency_s=latency_s)
    except Exception:
        result = {
            "is_safe": True, "safety_flags": [],
            "answer_with_disclaimer": answer,
            "facts": [], "fact_verdicts": [],
            "factuality_score": 0.0,
            "faithfulness": None, "answer_relevancy": None,
            "latency_s": latency_s, "correction_applied": False,
        }
    _verdicts = result.get("fact_verdicts", [])
    _n_sup    = sum(1 for v in _verdicts if v.get("verdict") == "supported")
    _log.info(
        "EVAL | safe=%s | faithfulness=%s | relevancy=%s | "
        "factuality=%.2f | facts=%d/%d | latency=%.2fs",
        result["is_safe"],
        f"{result['faithfulness']:.3f}"   if result.get("faithfulness")    is not None else "N/A",
        f"{result['answer_relevancy']:.3f}" if result.get("answer_relevancy") is not None else "N/A",
        result.get("factuality_score", 0.0),
        _n_sup, len(_verdicts),
        result.get("latency_s", 0.0),
    )
    store[key] = result  # atomic write — fragment will pick this up on next poll


@st.fragment(run_every=2)
def _eval_panel(store_key: str, query: str, answer: str,
                chunks: list, gen_fn) -> None:
    """Auto-reruns every 2 s until the background eval thread stores a result."""
    store  = _eval_store()
    result = store.get(store_key)

    if result is None:
        st.caption("⏳ Evaluating answer in background…")
        return  # fragment auto-reruns in 2 s via run_every

    # ── Correction loop (runs once in the fragment after result arrives) ───────
    try:
        from evaluator import FACTUALITY_THRESHOLD
    except Exception:
        FACTUALITY_THRESHOLD = 0.5

    _corrected_key = store_key + ":corrected"
    if (
        result.get("factuality_score", 1.0) < FACTUALITY_THRESHOLD
        and _corrected_key not in store
    ):
        _pct = int(result["factuality_score"] * 100)
        _log.warning(
            "CORRECTION | triggered=True | factuality=%.2f | threshold=%.2f",
            result.get("factuality_score", 0.0), FACTUALITY_THRESHOLD,
        )
        with st.spinner(
            f"Factuality {_pct}% < {int(FACTUALITY_THRESHOLD * 100)}%"
            " — regenerating with stricter prompt …"
        ):
            try:
                import time as _t2
                _t0 = _t2.perf_counter()
                _strict_ans = gen_fn(query, chunks, strict=True)
                _strict_lat = _t2.perf_counter() - _t0
                from evaluator import evaluate_answer as _ef2
                _strict_res = _ef2(
                    query=query, answer=_strict_ans,
                    chunks=chunks, latency_s=_strict_lat,
                )
                if _strict_res["factuality_score"] >= result["factuality_score"]:
                    _log.info(
                        "CORRECTION | accepted=True | old=%.2f | new=%.2f",
                        result["factuality_score"], _strict_res["factuality_score"],
                    )
                    _strict_res["correction_applied"] = True
                    store[_corrected_key] = _strict_ans
                    store[store_key] = _strict_res
                    st.session_state["_rag_answer"] = _strict_ans
                    st.rerun(scope="app")
                    return
                else:
                    _log.info(
                        "CORRECTION | accepted=False | old=%.2f | new=%.2f",
                        result["factuality_score"], _strict_res["factuality_score"],
                    )
                    store[_corrected_key] = None  # mark attempted
            except Exception:
                store[_corrected_key] = None

    _render_eval_dashboard(result)


# ── UI ────────────────────────────────────────────────────────────────────────
bm25, corpus, records, k1, b = load_index()

# Params badge
params_json = HERE / "bm25_params.json"
params_note = (
    f"Tuned BM25 (k1={k1}, b={b})"
    if params_json.exists() else
    f"BM25 defaults (k1={k1}, b={b}) — run tune_bm25.py to optimise"
)

st.title("🩺 ArogyaSaathi")
st.caption("Because every health question deserves a real answer.")

st.divider()

_default_q = st.query_params.get("q", "")

ctrl1, ctrl2, ctrl3 = st.columns([3, 1, 2])
with ctrl1:
    query = st.text_input(
        "Ask a medical question",
        value=_default_q,
        placeholder="e.g. Do statins reduce cardiovascular mortality?",
    )
with ctrl2:
    top_k = st.number_input("Top-k", min_value=1, max_value=20, value=5, step=1)
with ctrl3:
    mode = st.selectbox(
        "Enhancement",
        options=[
            "None (BM25 only)",
            "KG expansion",
            "Cross-encoder reranker",
            "KG + Cross-encoder",
        ],
    )

st.divider()

# ── Retrieval ─────────────────────────────────────────────────────────────────
if query.strip():
    use_kg      = mode in ("KG expansion", "KG + Cross-encoder")
    use_reranker = mode in ("Cross-encoder reranker", "KG + Cross-encoder")

    # ── Baseline retrieval ─────────────────────────────────────────────────────
    base_idx, base_norm = bm25_retrieve(bm25, corpus, query, top_k=20)
    # Only log when the query text actually changes to avoid flooding on reruns
    _last_q = st.session_state.get("_last_logged_query")
    if _last_q != query:
        _log.info(
            "QUERY | text=%r | top_k=%d | mode=%s | bm25_candidates=%d | "
            "top3_pmids=%s | top3_norm_scores=%s",
            query, top_k, mode, len(base_idx),
            [corpus[i]["pubid"] for i in base_idx[:3]],
            [f"{base_norm[i]:.3f}" for i in base_idx[:3]],
        )
        st.session_state["_last_logged_query"] = query

    if mode == "None (BM25 only)":
        # Single-column standard results
        result_cards(base_idx[:top_k], base_norm, corpus,
                     query=query, top_k=top_k)
    else:
        # Two-column comparison: baseline vs enhanced
        left, right = st.columns(2)

        with left:
            st.markdown("#### BM25 baseline")
            result_cards(base_idx[:top_k], base_norm, corpus,
                         query=query, top_k=top_k)

        with right:
            enhanced_label = mode
            st.markdown(f"#### {enhanced_label}")

            # Resolve query string (may be expanded)
            if use_kg:
                expand_fn = load_kg_expander()
                if expand_fn is None:
                    st.error("KG expansion unavailable — run track2_build_kg.py first.")
                    st.stop()
                enhanced_query = expand_fn(query)
                added_terms = [
                    t for t in enhanced_query.split()
                    if t not in set(query.lower().split())
                ]
                _log.info(
                    "KG_EXPAND | original=%r | expanded=%r | "
                    "terms_added=%d | new_terms=%s",
                    query, enhanced_query, len(added_terms), added_terms,
                )
                if added_terms:
                    st.info(f"**KG added:** {', '.join(added_terms)}", icon="🧬")
                else:
                    st.info("No KG terms found for this query.", icon="ℹ️")
            else:
                enhanced_query = query

            # Retrieve with (possibly expanded) query
            enh_idx, enh_norm = bm25_retrieve(bm25, corpus, enhanced_query, top_k=20)

            # Optionally rerank
            if use_reranker:
                rerank_fn = load_reranker()
                if rerank_fn is None:
                    st.warning(
                        "Cross-encoder unavailable — "
                        "run: pip install sentence-transformers",
                        icon="⚠️",
                    )
                    rerank_fn = None
            else:
                rerank_fn = None

            result_cards(enh_idx[:top_k], enh_norm, corpus,
                         query=enhanced_query, rerank_fn=rerank_fn, top_k=top_k)

    # ── RAG Generation + Evaluation ───────────────────────────────────────────
    st.divider()
    gen_fn = load_rag_generator()
    if gen_fn is not None:
        # Collect top-3 chunks for the grounded answer
        _top3_chunks = [
            {"pubid": corpus[i]["pubid"], "text": corpus[i]["text"]}
            for i in base_idx[:3]
        ]

        # ── Generate on button click ───────────────────────────────────────
        if st.button("Generate Answer", type="primary"):
            with st.spinner("Generating answer with Claude …"):
                import time as _time
                _t0 = _time.perf_counter()
                _answer = gen_fn(query, _top3_chunks)
                _gen_lat = _time.perf_counter() - _t0
            _log.info(
                "RAG_GEN | query=%r | latency=%.2fs | answer_words=%d | "
                "source_pmids=%s",
                query, _gen_lat, len(_answer.split()),
                [c["pubid"] for c in _top3_chunks],
            )
            st.session_state["_rag_answer"]  = _answer
            st.session_state["_rag_query"]   = query
            st.session_state["_gen_latency"] = _gen_lat
            # Clear any stale eval result from a previous query
            st.session_state.pop("_eval_result", None)
            st.session_state.pop("_eval_query",  None)

        # ── Show answer if it belongs to the current query ─────────────────
        if (
            st.session_state.get("_rag_query") == query
            and "_rag_answer" in st.session_state
        ):
            _stored_answer = st.session_state["_rag_answer"]
            st.markdown(
                f"<div style='"
                f"background:#f0f7ff;border-left:4px solid #2196F3;"
                f"padding:1rem;border-radius:4px;'>"
                f"{_stored_answer.replace(chr(10), '<br>')}"
                f"</div>",
                unsafe_allow_html=True,
            )

            # ── Evidence panel + citation gate ─────────────────────────────
            _render_why_panel(_top3_chunks)
            _render_citation_gate(_stored_answer)

            # ── Launch background eval thread (once per answer) ────────────
            _sk = _eval_store_key(query, _stored_answer)
            _ev = _eval_store()
            if _sk not in _ev and st.session_state.get("_eval_thread_key") != _sk:
                _lat = st.session_state.pop("_gen_latency", 0.0)
                threading.Thread(
                    target=_run_eval_thread,
                    args=(_ev, _sk, query, _stored_answer, _top3_chunks, _lat),
                    daemon=True,
                ).start()
                st.session_state["_eval_thread_key"] = _sk

            # ── Fragment polls every 2 s until result arrives ──────────────
            _eval_panel(_sk, query, _stored_answer, _top3_chunks, gen_fn)

        from rag_generate import MODEL as _RAG_MODEL
        st.caption(
            f"anthropic {_ANTHROPIC_VERSION} · model: {_RAG_MODEL} · "
            "grounded on top-3 BM25 chunks"
        )
    else:
        st.caption(
            "Install `anthropic` package to enable answer generation: "
            "`pip install anthropic>=0.25.0`"
        )

else:
    st.info(
        f"Index ready — {len(corpus):,} chunks from {len(records):,} PubMed abstracts. "
        "Type a question above to search."
    )

    with st.expander("Example questions from PubMedQA"):
        for rec in records[:8]:
            label = rec["question"][:90] + ("…" if len(rec["question"]) > 90 else "")
            if st.button(label, key=rec["pubid"]):
                st.session_state["_example_q"] = rec["question"]
                st.rerun()

# Handle example question clicks
if "_example_q" in st.session_state:
    q = st.session_state.pop("_example_q")
    st.query_params["q"] = q
    st.rerun()
