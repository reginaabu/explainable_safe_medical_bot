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
import csv
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

# ── PHI scrubber ──────────────────────────────────────────────────────────────
try:
    from utils.phi_scrub import scrub as _scrub_phi
except ImportError:
    _scrub_phi = None   # degrades gracefully if utils package not on path

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
    subset_csv = HERE / "pubmedqa_subset.csv"
    records = []

    # Prefer local subset to avoid network dependency on app startup.
    if subset_csv.exists():
        with subset_csv.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append({
                    "pubid":    str(row.get("doc_id") or row.get("pubid") or ""),
                    "question": row["question"],
                    "context":  row["context"],
                })

    if not records:
        dataset = load_dataset("pubmed_qa", "pqa_labeled", trust_remote_code=True)
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


# ── Retrieval constants ───────────────────────────────────────────────────────
_RETRIEVE_K      = 20     # internal candidate pool size (never shown to user)
_SCORE_THRESHOLD = 0.85   # minimum normalised score to display a result


# ── Retrieval helpers ─────────────────────────────────────────────────────────
def bm25_retrieve(bm25, corpus, query_str: str):
    scores     = bm25.get_scores(query_str.lower().split())
    max_s      = scores.max()
    norm       = scores / max_s if max_s > 0 else scores   # normalise to [0,1]
    ranked_idx = np.argsort(scores)[::-1][:_RETRIEVE_K]
    ranked_idx = [i for i in ranked_idx if scores[i] > 0]
    return ranked_idx, norm


def result_cards(ranked_idx, norm_scores, corpus, query: str = "",
                 rerank_fn=None):
    import math

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

    # ── Filter: only show results at or above the score threshold ─────────────
    passing = []
    for rank0, doc in enumerate(reranked):
        if "ce_score" in doc:
            display_score = 1 / (1 + math.exp(-doc["ce_score"]))
            score_label   = "CE"
        else:
            orig_idx      = ranked_idx[rank0] if rank0 < len(ranked_idx) else 0
            display_score = float(norm_scores[orig_idx])
            score_label   = "BM25"
        if display_score >= _SCORE_THRESHOLD:
            passing.append((doc, display_score, score_label))

    if not passing:
        st.info(
            f"No results met the {_SCORE_THRESHOLD:.0%} relevance threshold. "
            "Try rephrasing your question.",
            icon="🔎",
        )
        return

    st.subheader(f"{len(passing)} result{'s' if len(passing) != 1 else ''} "
                 f"above {_SCORE_THRESHOLD:.0%} relevance")
    for rank, (doc, display_score, score_label) in enumerate(passing, 1):
        pubid = doc["pubid"]
        pmurl = f"https://pubmed.ncbi.nlm.nih.gov/{pubid}/"

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

        # Row 2: Factuality summary
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


# ── Pipeline helpers ──────────────────────────────────────────────────────────
import hashlib
import threading


@st.cache_resource
def _ragas_store() -> dict:
    """Module-level store for async RAGAS results. Keyed by hash(query+answer)."""
    return {}


def _ragas_key(query: str, answer: str) -> str:
    return hashlib.md5(f"{query}||{answer}".encode()).hexdigest()[:16]


def _run_ragas_thread(
    store: dict, key: str,
    query: str, answer: str, chunks: list,
    answer_time: float,
) -> None:
    """Background thread: run RAGAS metrics and write result into store."""
    import time as _t
    t0 = _t.perf_counter()
    try:
        from evaluator.metrics import score_metrics
        r = score_metrics(query, answer, chunks)
        faithfulness     = r.get("faithfulness")
        answer_relevancy = r.get("answer_relevancy")
    except Exception:
        faithfulness = None
        answer_relevancy = None
    ragas_time = _t.perf_counter() - t0
    store[key] = {
        "faithfulness":     faithfulness,
        "answer_relevancy": answer_relevancy,
        "ragas_time":       ragas_time,
        "answer_time":      answer_time,
    }
    _log.info(
        "RAGAS | faithfulness=%s | relevancy=%s | ragas_time=%.2fs",
        f"{faithfulness:.3f}" if faithfulness      is not None else "N/A",
        f"{answer_relevancy:.3f}" if answer_relevancy is not None else "N/A",
        ragas_time,
    )


@st.fragment(run_every=2)
def _ragas_panel(store_key: str) -> None:
    """Fragment that polls the RAGAS store every 2 s and renders when ready."""
    store  = _ragas_store()
    result = store.get(store_key)

    if result is None:
        st.caption("📊 Scoring faithfulness & relevance in background…")
        return

    faith = result.get("faithfulness")
    rel   = result.get("answer_relevancy")
    ragas_time  = result.get("ragas_time",  0.0)
    answer_time = result.get("answer_time", 0.0)

    with st.container(border=True):
        st.markdown("#### Quality Scores")

        t_col1, t_col2 = st.columns(2)
        with t_col1:
            st.metric("⚡ Answer rendered in", f"{answer_time:.2f} s")
        with t_col2:
            st.metric("📊 RAGAS scored in", f"{ragas_time:.2f} s")

        faith_str = f"{faith:.2f}  {_score_bar(faith)}" if faith is not None else "N/A"
        rel_str   = f"{rel:.2f}  {_score_bar(rel)}"     if rel   is not None else "N/A"
        st.markdown(f"**Faithfulness:** &nbsp;&nbsp; {faith_str}", unsafe_allow_html=True)
        st.markdown(f"**Answer Relevance:** {rel_str}", unsafe_allow_html=True)


# ── Core pipeline: generate → safety → factcheck → self-correct ───────────────

def _run_core_pipeline(
    query: str,
    chunks: list,
    gen_fn,
) -> dict:
    """
    Run generation + safety + factcheck + self-correction synchronously,
    showing live steps in an st.status() widget.  RAGAS is NOT run here —
    it is launched asynchronously after this function returns.

    Returns a result dict compatible with _render_eval_dashboard(), plus
    a 'core_time' key with the wall-clock seconds for this pipeline.
    """
    import time as _time
    from evaluator import FACTUALITY_THRESHOLD
    from evaluator.safety import check_safety
    from evaluator.fact_decompose import decompose_facts
    from evaluator.fact_verify import verify_facts

    t_start = _time.perf_counter()

    with st.status("Checking your answer — please wait…", expanded=True) as _status:

        # ── Step 1: Generate ──────────────────────────────────────────────────
        st.write("🤖 Generating answer with Claude…")
        _t0 = _time.perf_counter()
        answer = gen_fn(query, chunks)
        gen_lat = _time.perf_counter() - _t0

        # ── Step 2: Safety check ──────────────────────────────────────────────
        st.write("🛡️ Running safety check…")
        try:
            _safety = check_safety(answer)
        except Exception:
            _safety = {"is_safe": True, "flags": [],
                       "answer_with_disclaimer": answer}

        # ── Step 3: Extract atomic claims ─────────────────────────────────────
        st.write("🔬 Extracting atomic claims…")
        try:
            facts = decompose_facts(answer)
        except Exception:
            facts = []

        # ── Step 4: Verify claims against sources ─────────────────────────────
        n_facts = len(facts)
        st.write(f"🔍 Verifying {n_facts} claim{'s' if n_facts != 1 else ''} "
                 f"against retrieved sources…")
        try:
            verdicts = verify_facts(facts, chunks) if facts else []
        except Exception:
            verdicts = [{"fact": f, "verdict": "unsupported", "pmid": None}
                        for f in facts]

        n_sup = sum(1 for v in verdicts if v.get("verdict") == "supported")
        score = n_sup / len(verdicts) if verdicts else 0.0
        corrected = False

        # ── Step 5: Self-correction if factuality below threshold ─────────────
        if score < FACTUALITY_THRESHOLD:
            _pct = int(score * 100)
            _thr = int(FACTUALITY_THRESHOLD * 100)
            st.write(f"⚠️ Factuality {_pct}% below {_thr}% — regenerating…")
            _log.warning("CORRECTION | triggered=True | factuality=%.2f", score)
            try:
                _tc = _time.perf_counter()
                _strict_ans = gen_fn(query, chunks, strict=True)
                gen_lat += _time.perf_counter() - _tc
                _strict_facts    = decompose_facts(_strict_ans)
                _strict_verdicts = verify_facts(_strict_facts, chunks) if _strict_facts else []
                _strict_n_sup    = sum(1 for v in _strict_verdicts
                                       if v.get("verdict") == "supported")
                _strict_score    = (_strict_n_sup / len(_strict_verdicts)
                                    if _strict_verdicts else 0.0)
                if _strict_score >= score:
                    answer, facts, verdicts = _strict_ans, _strict_facts, _strict_verdicts
                    n_sup, score, corrected = _strict_n_sup, _strict_score, True
                    _safety = check_safety(answer)
                    st.write(f"✅ Corrected — factuality → {int(score * 100)}%")
                    _log.info("CORRECTION | accepted=True | new=%.2f", score)
                else:
                    st.write("ℹ️ Strict regeneration didn't improve factuality — "
                             "keeping original.")
                    _log.info("CORRECTION | accepted=False | new=%.2f", _strict_score)
            except Exception:
                pass

        core_time = _time.perf_counter() - t_start
        _status.update(
            label=f"✅ Answer ready — scoring quality in background…",
            state="complete", expanded=False,
        )

    result = {
        "is_safe":                _safety["is_safe"],
        "safety_flags":           _safety["flags"],
        "answer_with_disclaimer": _safety.get("answer_with_disclaimer", answer),
        "facts":                  facts,
        "fact_verdicts":          verdicts,
        "factuality_score":       score,
        "latency_s":              gen_lat,
        "core_time":              core_time,
        "correction_applied":     corrected,
    }
    _n_sup = sum(1 for v in verdicts if v.get("verdict") == "supported")
    _log.info(
        "CORE_EVAL | safe=%s | factuality=%.2f | facts=%d/%d | "
        "core_time=%.2fs | corrected=%s",
        result["is_safe"], score, _n_sup, len(verdicts), core_time, corrected,
    )
    return result


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

# Align all form-column widgets to the same baseline
st.markdown(
    "<style>"
    "[data-testid='column'] { display:flex; flex-direction:column; justify-content:flex-end; }"
    "</style>",
    unsafe_allow_html=True,
)

st.divider()

_default_q = st.query_params.get("q", "")

# ── Search form — Press Enter or click Search to trigger the full pipeline ──
with st.form("search_form", border=False, clear_on_submit=False):
    fc1, fc2, fc3 = st.columns([5, 2, 1])
    with fc1:
        query = st.text_input(
            "Ask a medical question",
            value=_default_q,
            placeholder="e.g. Do statins reduce cardiovascular mortality?",
            label_visibility="collapsed",
        )
    with fc2:
        mode = st.selectbox(
            "Enhancement",
            options=[
                "None (BM25 only)",
                "KG expansion",
                "Cross-encoder reranker",
                "KG + Cross-encoder",
            ],
            label_visibility="collapsed",
        )
    with fc3:
        submitted = st.form_submit_button(
            "Search ↵", type="primary", use_container_width=True
        )

st.divider()

# ── Retrieval ─────────────────────────────────────────────────────────────────
if query.strip():
    # ── HIPAA Safe Harbour PHI scrubbing ──────────────────────────────────────
    # Replaces up to 11 identifier categories (SSN, phone, email, dates, ZIP,
    # names, MRN, IP, URL, device IDs, ages >89) with neutral placeholders
    # before any text is passed to the retrieval index or external LLM API.
    # The displayed query in the text box is unchanged; only the downstream
    # processing uses the scrubbed version.
    if _scrub_phi is not None:
        _scrub = _scrub_phi(query)
        if _scrub.found:
            _categories = ", ".join(_scrub.found)
            st.info(
                f"**Privacy protection active** — {len(_scrub.found)} identifier "
                f"type(s) detected ({_categories}) and replaced before processing. "
                f"Your original text is never stored or transmitted.",
                icon="🔒",
            )
            _log.info(
                "PHI_SCRUB | categories=%s | original_len=%d | scrubbed_len=%d",
                _categories, len(query), len(_scrub.text),
            )
        query = _scrub.text   # use scrubbed version for all downstream calls

    use_kg      = mode in ("KG expansion", "KG + Cross-encoder")
    use_reranker = mode in ("Cross-encoder reranker", "KG + Cross-encoder")
    rag_top3_chunks: list[dict] = []
    rag_grounding_label = "top-3 BM25 chunks"

    # ── Baseline retrieval ─────────────────────────────────────────────────────
    base_idx, base_norm = bm25_retrieve(bm25, corpus, query)
    # Only log when the query text actually changes to avoid flooding on reruns
    _last_q = st.session_state.get("_last_logged_query")
    if _last_q != query:
        _log.info(
            "QUERY | text(scrubbed)=%r | mode=%s | bm25_candidates=%d | "
            "top3_pmids=%s | top3_norm_scores=%s",
            query, mode, len(base_idx),
            [corpus[i]["pubid"] for i in base_idx[:3]],
            [f"{base_norm[i]:.3f}" for i in base_idx[:3]],
        )
        st.session_state["_last_logged_query"] = query

    if mode == "None (BM25 only)":
        # Single-column standard results
        result_cards(base_idx, base_norm, corpus, query=query)
        rag_top3_chunks = [
            {"pubid": corpus[i]["pubid"], "text": corpus[i]["text"]}
            for i in base_idx[:3]
        ]
        rag_grounding_label = "top-3 BM25 chunks"
    else:
        # Two-column comparison: baseline vs enhanced
        left, right = st.columns(2)

        with left:
            st.markdown("#### BM25 baseline")
            result_cards(base_idx, base_norm, corpus, query=query)

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
                pass  # KG expansion applied silently
            else:
                enhanced_query = query

            # Retrieve with (possibly expanded) query
            enh_idx, enh_norm = bm25_retrieve(bm25, corpus, enhanced_query)

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

            result_cards(enh_idx, enh_norm, corpus,
                         query=enhanced_query, rerank_fn=rerank_fn)

            # Ground generation on the currently selected retrieval mode.
            if rerank_fn is not None:
                _cand_docs = [corpus[i] for i in enh_idx]
                _gen_docs = rerank_fn(enhanced_query, _cand_docs, top_k=3)
                rag_top3_chunks = [
                    {"pubid": d["pubid"], "text": d["text"]}
                    for d in _gen_docs
                ]
                rag_grounding_label = "top-3 KG+CE chunks" if use_kg else "top-3 CE chunks"
            else:
                rag_top3_chunks = [
                    {"pubid": corpus[i]["pubid"], "text": corpus[i]["text"]}
                    for i in enh_idx[:3]
                ]
                rag_grounding_label = "top-3 KG-expanded BM25 chunks" if use_kg else "top-3 BM25 chunks"

    # ── RAG Generation + Evaluation ───────────────────────────────────────────
    st.divider()
    gen_fn = load_rag_generator()
    if gen_fn is not None:
        _top3_chunks = rag_top3_chunks or [
            {"pubid": corpus[i]["pubid"], "text": corpus[i]["text"]}
            for i in base_idx[:3]
        ]

        # ── Auto-trigger core pipeline when form is submitted ─────────────
        if submitted and query.strip():
            if not _top3_chunks:
                st.warning("No retrieval evidence available to ground generation.")
                st.stop()
            _log.info("RAG_GEN | query=%r | source_pmids=%s",
                      query, [c["pubid"] for c in _top3_chunks])
            _result = _run_core_pipeline(query, _top3_chunks, gen_fn)
            st.session_state["_rag_result"] = _result
            st.session_state["_rag_query"]  = query

            # Launch RAGAS asynchronously — pass answer_time for the timer
            _rk = _ragas_key(query, _result["answer_with_disclaimer"])
            _rs = _ragas_store()
            _rs[_rk] = None  # mark as pending
            threading.Thread(
                target=_run_ragas_thread,
                args=(_rs, _rk, query,
                      _result["answer_with_disclaimer"],
                      _top3_chunks,
                      _result["core_time"]),
                daemon=True,
            ).start()
            st.session_state["_ragas_key"] = _rk

        # ── Render answer once core pipeline has completed for this query ──
        if (
            st.session_state.get("_rag_query") == query
            and "_rag_result" in st.session_state
        ):
            _result         = st.session_state["_rag_result"]
            _display_answer = _result["answer_with_disclaimer"]

            st.markdown(
                f"<div style='"
                f"background:#f0f7ff;border-left:4px solid #2196F3;"
                f"padding:1rem;border-radius:4px;'>"
                f"{_display_answer.replace(chr(10), '<br>')}"
                f"</div>",
                unsafe_allow_html=True,
            )

            # ── Evidence panel + citation gate ─────────────────────────────
            _render_why_panel(_top3_chunks)
            _render_citation_gate(_display_answer)

            # ── Core eval: safety + factuality (immediately available) ─────
            _render_eval_dashboard(_result)

            # ── Async RAGAS panel: polls every 2s, shows both timers ───────
            if "_ragas_key" in st.session_state:
                _ragas_panel(st.session_state["_ragas_key"])

        from rag_generate import MODEL as _RAG_MODEL
        st.caption(
            f"anthropic {_ANTHROPIC_VERSION} · model: {_RAG_MODEL} · "
            f"grounded on {rag_grounding_label}"
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
