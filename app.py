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

# ── Dataset adapter ────────────────────────────────────────────────────────────
try:
    from utils.dataset_adapter import (
        DATASET_META, load_dataset_rows,
        get_id_label, get_source_type, get_default_retriever,
    )
    _DATASET_ADAPTER_OK = True
except ImportError:
    _DATASET_ADAPTER_OK = False

# All datasets available in the app, with display labels and local paths.
# mimic3 / mimic4 require credentialed PhysioNet access — not included.
_FEDERATED_DATASETS: dict[str, dict] = {
    "pubmedqa":   {"label": "PubMedQA",  "local_path": None},
    "medquad":    {"label": "MedQuAD",   "local_path": None},
    "archehr_qa": {"label": "ArchEHR-QA","local_path": str(HERE / "data" / "archehr_qa")},
}

# Short badge shown on each result card
_DATASET_BADGE: dict[str, str] = {
    "pubmedqa":   "📄 PubMed",
    "medquad":    "💊 MedQuAD",
    "archehr_qa": "🏥 ArchEHR",
}

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


# ── Load index (cached per dataset) ───────────────────────────────────────────
@st.cache_resource(show_spinner="Building index … (first run only)")
def load_index(dataset_name: str = "pubmedqa", csv_path: str | None = None):
    """
    Build the retrieval index for *dataset_name*.  Returns a bundle dict:
      type      : "bm25" | "semantic" | "hybrid"
      corpus    : list of {"pubid": doc_id, "text": chunk}
      records   : list of canonical rows (doc_id, question, context, …)
      k1, b     : BM25 params (for display badge)
      bm25      : BM25Okapi instance (type=="bm25" only)
      idx       : SemanticIndex or HybridIndex (type=="semantic"/"hybrid")
    """
    k1, b = _bm25_params()

    # ── Load raw records ───────────────────────────────────────────────────────
    if dataset_name == "pubmedqa":
        # Prefer local subset CSV for fast startup; fall back to HuggingFace.
        subset_csv = HERE / "pubmedqa_subset.csv"
        raw_records: list[dict] = []
        if subset_csv.exists():
            with subset_csv.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_records.append({
                        "doc_id":   str(row.get("doc_id") or row.get("pubid") or ""),
                        "pubid":    str(row.get("doc_id") or row.get("pubid") or ""),
                        "question": row["question"],
                        "context":  row["context"],
                    })
        if not raw_records:
            dataset_hf = load_dataset("pubmed_qa", "pqa_labeled", trust_remote_code=True)
            for item in dataset_hf["train"]:
                context_flat = " ".join(item["context"]["contexts"])
                raw_records.append({
                    "doc_id":   str(item["pubid"]),
                    "pubid":    str(item["pubid"]),
                    "question": item["question"],
                    "context":  context_flat,
                })
        records = raw_records
    else:
        # Use dataset_adapter for all other datasets.
        rows = load_dataset_rows(dataset_name, csv_path=csv_path, max_rows=None)
        # Normalise: add "pubid" alias so chunks and retrieval code use one key.
        # MedQuAD's 12 source files reuse the same QID numbering, so up to 10
        # completely different topics share the same doc_id (e.g. "0000118-1"
        # covers Sleep Apnea, Bone Marrow Transplantation, cholestasis, …).
        # Deduplicate by appending __N to the second and later occurrences so
        # each QA pair gets its own unique pubid and its own context in the index.
        _seen_ids: dict[str, int] = {}
        records = []
        for r in rows:
            base_id = r["doc_id"]
            if base_id not in _seen_ids:
                _seen_ids[base_id] = 0
                uid = base_id
            else:
                _seen_ids[base_id] += 1
                uid = f"{base_id}__{_seen_ids[base_id]}"
            records.append({**r, "doc_id": uid, "pubid": uid})

    # ── Build chunked corpus (shared by all retriever types) ──────────────────
    corpus: list[dict] = []
    for rec in records:
        doc_id = rec.get("pubid") or rec.get("doc_id", "")
        words  = rec["context"].split()
        start  = 0
        while start < len(words):
            chunk = " ".join(words[start : start + 400])
            if chunk.strip():
                corpus.append({"pubid": doc_id, "text": chunk})
            start += 350

    # ── Select retriever ──────────────────────────────────────────────────────
    retriever_type = (
        get_default_retriever(dataset_name)
        if _DATASET_ADAPTER_OK else "bm25"
    )

    if retriever_type == "semantic":
        try:
            from utils.semantic_index import SemanticIndex
            idx = SemanticIndex(records)
            return {"type": "semantic", "idx": idx, "dataset": dataset_name,
                    "corpus": corpus, "records": records, "k1": k1, "b": b}
        except Exception as _se:
            _log.warning("Semantic index build failed (%s) — falling back to BM25", _se)

    elif retriever_type == "hybrid":
        try:
            from utils.semantic_index import HybridIndex
            q_corpus = [{"pubid": r["pubid"], "text": r["question"]} for r in records]
            tokenized_q = [r["question"].lower().split() for r in records]
            q_bm25 = BM25Okapi(tokenized_q, k1=k1, b=b)
            idx = HybridIndex(records, q_bm25, q_corpus)
            return {"type": "hybrid", "idx": idx, "dataset": dataset_name,
                    "corpus": corpus, "records": records, "k1": k1, "b": b}
        except Exception as _he:
            _log.warning("Hybrid index build failed (%s) — falling back to BM25", _he)

    # BM25 (default / fallback)
    tokenized = [doc["text"].lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenized, k1=k1, b=b)

    # Build a question-field BM25 and a pubid→record-index map for per-candidate
    # Q-field gating.  At query time we score the query against each *candidate*
    # document's question (not over all questions) to check whether the candidate
    # research question is at all related to the user query.
    # e.g. "Is halofantrine ototoxic?" scores 0 against
    # "How many people are affected by keratoderma with woolly hair?" because
    # none of the query terms appear in the halofantrine question.
    tokenized_q = [r.get("question", "").lower().split() for r in records]
    q_bm25 = BM25Okapi(tokenized_q, k1=k1, b=b)
    pubid_to_rec_idx = {
        r.get("pubid") or r.get("doc_id", ""): i for i, r in enumerate(records)
    }

    return {"type": "bm25", "bm25": bm25, "q_bm25": q_bm25,
            "pubid_to_rec_idx": pubid_to_rec_idx, "dataset": dataset_name,
            "corpus": corpus, "records": records, "k1": k1, "b": b}


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
    return ranked_idx, norm, float(max_s)


# Minimum raw BM25 score for a source to participate in federated retrieval.
_MIN_BM25_SCORE   = 1.5
# Minimum cosine similarity for semantic/hybrid sources.
_MIN_SEM_SCORE    = 0.50
# Minimum per-candidate question-field BM25 score (content terms only).
# A score of 0 means the candidate document's question shares no content words
# with the user query → it is a false BM25 match and should be excluded.
_MIN_Q_BM25_SCORE = 8.0

# Stop words excluded from per-candidate Q-field gating so only content words
# (disease names, procedures, drugs, etc.) determine topic relevance.
_BM25_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "can", "what", "which", "who", "whom", "when", "where", "why",
    "how", "this", "that", "these", "those", "it", "its", "they", "we",
    "you", "not", "no", "nor", "many", "much", "more", "most", "some",
    "any", "all", "each", "if", "as", "so", "than", "then", "very",
    "have", "has", "had", "their", "our", "your", "my", "his", "her",
    # Generic epidemiology / research words that appear in unrelated questions
    # and would cause false positive Q-field matches (e.g. "people" in
    # "Do French lay people find it acceptable…" matching keratoderma query).
    "people", "affected", "patients", "patient", "person", "individuals",
    "study", "studies", "data", "result", "results", "effect", "effects",
    "use", "used", "using", "based", "new", "between", "compared",
    "associated", "related", "known", "given", "found", "number",
    # Generic clinical-research verbs/nouns that appear in many unrelated questions
    # and produce false Q-field matches (e.g. "influence" in "Does music influence
    # stress?" matching the hematopoietic contamination query).
    "influence", "influences", "improve", "improves", "affect", "affects",
    "outcomes", "outcome", "success", "risk", "risks", "rate", "rates",
    "increase", "decrease", "reduce", "causes", "cause", "prevent",
    "predict", "determine", "evaluate", "assess", "develop", "developed",
    "show", "shows", "showed", "indicate", "indicates", "suggest", "suggests",
    "provide", "provides", "lead", "leads", "include", "includes",
})


def _infer_medquad_q_type(query: str) -> str | None:
    """
    Map a free-text query to one of MedQuAD's question_type values so the
    hybrid/semantic index can restrict candidates to the matching question facet.
    Rules are ordered from most specific to most general.
    Returns None when no rule fires (falls back to unfiltered retrieval).
    """
    q = query.lower()
    if any(w in q for w in ["brand name", "brand names"]):
        return "brand names"
    if any(w in q for w in ["storage", "disposal", "store and dispos"]):
        return "storage and disposal"
    if any(w in q for w in ["forgot a dose", "forget a dose", "missed dose", "miss a dose"]):
        return "forget a dose"
    if any(w in q for w in ["side effect", "adverse effect", "adverse reaction"]):
        return "side effects"
    if any(w in q for w in ["overdose", "emergency overdose"]):
        return "emergency or overdose"
    if any(w in q for w in ["important warning", "warnings"]):
        return "important warning"
    if any(w in q for w in ["genetic change", "gene mutation", "genetic mutation"]):
        return "genetic changes"
    if any(w in q for w in ["inherit", "hereditary", "is it inherited"]):
        return "inheritance"
    if any(w in q for w in ["symptom", "sign of", "signs of"]):
        return "symptoms"
    if any(w in q for w in ["cause", "causes", "what causes"]):
        return "causes"
    if any(w in q for w in ["treatment", "treat ", "therapy", "therapies", "manage ", "cure"]):
        return "treatment"
    if any(w in q for w in ["diagnos", "test for", "how is it detected", "exams"]):
        return "exams and tests"
    if any(w in q for w in ["prevent", "prevention"]):
        return "prevention"
    if any(w in q for w in ["outlook", "prognos"]):
        return "outlook"
    if any(w in q for w in ["see a doctor", "need a doctor", "contact a medical", "when to call"]):
        return "when to contact a medical professional"
    if any(w in q for w in ["complication"]):
        return "complications"
    if any(w in q for w in ["how many", "how common", "how frequent", "prevalence", "frequency"]):
        return "frequency"
    if any(w in q for w in ["how should", "how to use", "dosage", "how much to take"]):
        return "usage"
    if any(w in q for w in ["who should get", "prescribed for", "why is it prescribed", "indication"]):
        return "indication"
    if any(w in q for w in ["other information", "what else should", "what other information"]):
        return "other information"
    if any(w in q for w in ["precaution"]):
        return "precautions"
    if any(w in q for w in ["suscept", "who is at risk", "risk factor"]):
        return "susceptibility"
    if any(w in q for w in ["dietary", "food", "eat "]):
        return "dietary"
    if any(w in q for w in ["research", "latest research"]):
        return "research"
    if any(w in q for w in ["what is", "what are", "describe", "information about"]):
        return "information"
    return None


def _retrieve_docs(query: str, bundle: dict, k: int = _RETRIEVE_K) -> list:
    """
    Unified retrieval dispatch.  Returns list of (doc_dict, score, score_label).
    doc_dict always has "pubid" and "text" keys.
    Returns an empty list when the source has no genuine matches for this query.
    """
    if bundle["type"] == "bm25":
        idx, norm, max_s = bm25_retrieve(bundle["bm25"], bundle["corpus"], query)
        # Gate: if the best raw BM25 score is below threshold, this source has
        # no relevant documents for this query — exclude entirely.
        if max_s < _MIN_BM25_SCORE:
            return []
        # Per-candidate Q-field BM25 gate (content words only).
        # Score each candidate's *own* question against the query's content words
        # (stop words removed).  A score of 0 means the candidate's question
        # shares no content vocabulary with the query → false BM25 match → drop.
        # e.g. "Is halofantrine ototoxic?" scores 0.000 against content terms
        # [people, affected, keratoderma, woolly, hair] → correctly excluded.
        _q_bm25        = bundle.get("q_bm25")
        _pubid_to_ridx = bundle.get("pubid_to_rec_idx", {})
        if _q_bm25 is not None and _pubid_to_ridx:
            _content_terms = [
                t.strip("?,.:;!()'\"")
                for t in query.lower().split()
                if t.strip("?,.:;!()'\"") not in _BM25_STOP_WORDS
                and len(t.strip("?,.:;!()'\""  )) > 4
            ]
            if _content_terms:
                _q_scores = _q_bm25.get_scores(_content_terms)
                _filtered = []
                for i in idx:
                    _pid   = bundle["corpus"][i]["pubid"]
                    _ridx  = _pubid_to_ridx.get(_pid, -1)
                    _qs    = float(_q_scores[_ridx]) if _ridx >= 0 else _MIN_Q_BM25_SCORE
                    if _qs >= _MIN_Q_BM25_SCORE:
                        _filtered.append(i)
                if not _filtered:
                    _log.info(
                        "BM25 Q-field gate: all %d candidates excluded "
                        "(content_terms=%s) for query %r",
                        len(idx), _content_terms, query[:60],
                    )
                    return []
                if len(_filtered) < len(idx):
                    _log.info(
                        "BM25 Q-field gate: kept %d/%d candidates for query %r",
                        len(_filtered), len(idx), query[:60],
                    )
                idx = _filtered
        return [(bundle["corpus"][i], float(norm[i]), "BM25") for i in idx]
    elif bundle["type"] == "semantic":
        # Infer question type for MedQuAD/ArchEHR to restrict semantic candidates
        # to the matching question facet (symptoms, treatment, outlook, etc.).
        _q_type = (
            _infer_medquad_q_type(query)
            if bundle.get("dataset") == "medquad" else None
        )
        chunks = bundle["idx"].query(query, top_k=k, q_type=_q_type)
        filtered = [c for c in chunks if c.get("sem_score", 0.0) >= _MIN_SEM_SCORE]
        return [(c, c.get("sem_score", 1.0), "Sem") for c in filtered]
    elif bundle["type"] == "hybrid":
        # Same q_type inference for MedQuAD hybrid index.
        _q_type = (
            _infer_medquad_q_type(query)
            if bundle.get("dataset") == "medquad" else None
        )
        chunks = bundle["idx"].query(query, top_k=k, q_type=_q_type)
        filtered = [c for c in chunks if c.get("sem_score", 0.0) >= _MIN_SEM_SCORE]
        return [(c, c.get("sem_score", 1.0), "Hybrid") for c in filtered]
    return []


def retrieve_federated(query: str, bundles: dict, k_per: int = 10) -> list:
    """
    Query every loaded index and merge results with Reciprocal Rank Fusion.

    bundles : {dataset_name: bundle_dict}  from load_index()
    Returns list of (doc_dict, rrf_score, retriever_label, dataset_name),
    sorted by descending RRF score.  doc_dict has "pubid", "text", "_dataset".
    """
    _RRF_K = 60
    all_results: dict[str, tuple] = {}   # key → (doc, dataset_name, retriever_label)
    dataset_ranks: dict[str, dict[str, int]] = {}  # dataset → {key: rank}

    for ds_name, bundle in bundles.items():
        retrieved = _retrieve_docs(query, bundle, k=k_per)
        ranks: dict[str, int] = {}
        for rank, (doc, score, label) in enumerate(retrieved):
            key = f"{ds_name}::{doc['pubid']}"
            doc_with_ds = {**doc, "_dataset": ds_name}
            all_results[key] = (doc_with_ds, ds_name, label)
            ranks[key] = rank
        dataset_ranks[ds_name] = ranks

    # RRF: score each key across all datasets
    scored: list[tuple[float, str]] = []
    for key in all_results:
        rrf = sum(
            1 / (_RRF_K + dataset_ranks[ds].get(key, k_per))
            for ds in dataset_ranks
        )
        scored.append((rrf, key))

    scored.sort(reverse=True)
    # Normalise scores to [0, 1] so top result = 1.0 (raw RRF values ≈ 0.016 are
    # rank-fusion weights, NOT accuracy — normalisation avoids confusion in the UI)
    max_rrf = scored[0][0] if scored else 1.0
    return [
        (all_results[key][0], rrf / max_rrf, all_results[key][2], all_results[key][1])
        for rrf, key in scored
    ]


def result_cards(retrieved: list, query: str = "", rerank_fn=None):
    """
    Display retrieval results from federated or single-dataset search.

    retrieved : list of (doc_dict, score, score_label, dataset_name)
                doc_dict has "pubid", "text", and optionally "_dataset".
    """
    import math

    if not retrieved:
        st.warning("No relevant documents found. Try rephrasing your question.")
        return

    # ── Optional cross-encoder reranking ─────────────────────────────────────
    if rerank_fn is not None:
        candidates = [doc for doc, _, _, _ in retrieved]
        reranked_docs = rerank_fn(query, candidates, top_k=len(candidates))
        _log.info(
            "RERANK | query=%r | top3_ids=%s | top3_ce_scores=%s",
            query,
            [doc["pubid"] for doc in reranked_docs[:3]],
            [f"{doc.get('ce_score', 'n/a'):.3f}" if isinstance(doc.get("ce_score"), float)
             else str(doc.get("ce_score", "n/a")) for doc in reranked_docs[:3]],
        )
        # Preserve dataset_name from original retrieved list
        ds_map = {doc["pubid"]: ds for doc, _, _, ds in retrieved}
        retrieved_display = [
            (doc,
             1 / (1 + math.exp(-doc["ce_score"])) if "ce_score" in doc else 1.0,
             "CE",
             ds_map.get(doc["pubid"], "pubmedqa"))
            for doc in reranked_docs
        ]
    else:
        retrieved_display = retrieved

    if not retrieved_display:
        st.info("No results found. Try rephrasing your question.", icon="🔎")
        return

    st.subheader(f"{len(retrieved_display)} result{'s' if len(retrieved_display) != 1 else ''} found")

    for rank, (doc, display_score, score_label, ds_name) in enumerate(retrieved_display, 1):
        doc_id   = doc["pubid"]
        badge    = _DATASET_BADGE.get(ds_name, ds_name)
        id_label = get_id_label(ds_name) if _DATASET_ADAPTER_OK else "ID"

        if ds_name == "pubmedqa":
            pmurl  = f"https://pubmed.ncbi.nlm.nih.gov/{doc_id}/"
            header = f"**#{rank}** &nbsp; {badge} &nbsp; [{id_label} {doc_id}]({pmurl})"
        else:
            header = f"**#{rank}** &nbsp; {badge} &nbsp; {id_label} {doc_id}"

        with st.container(border=True):
            h_col, s_col = st.columns([5, 1])
            with h_col:
                st.markdown(header, unsafe_allow_html=True)
            with s_col:
                # score_label is the retriever type (BM25/Hybrid/Semantic/CE);
                # always show "Relevance" to users to avoid confusion with accuracy
                st.markdown(
                    f"<div style='text-align:right;color:#555;font-size:0.82em;'>"
                    f"Relevance<br><b>{display_score:.3f}</b></div>",
                    unsafe_allow_html=True,
                )

            snippet = doc["text"][:400].strip()
            if len(doc["text"]) > 400:
                snippet += "…"
            st.write(snippet)

            with st.expander("Show full chunk"):
                st.write(doc["text"])
                if ds_name == "pubmedqa":
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
    """
    chunks: list of doc dicts with "pubid", "text", and optional "_dataset".
    """
    mentioned, cooccurs = _load_triples()
    with st.expander("💡 Why this answer? — Evidence sources"):
        for idx, chunk in enumerate(chunks, 1):
            doc_id   = chunk["pubid"]
            ds_name  = chunk.get("_dataset", "pubmedqa")
            badge    = _DATASET_BADGE.get(ds_name, ds_name)
            id_label = get_id_label(ds_name) if _DATASET_ADAPTER_OK else "PMID"

            sentences = [s.strip() for s in chunk["text"].replace("\n", " ").split(". ") if s.strip()]
            snippet = ". ".join(sentences[:2])
            if len(snippet) > 200:
                snippet = snippet[:197] + "…"
            if snippet and not snippet.endswith("."):
                snippet += "."

            if ds_name == "pubmedqa":
                pmurl = f"https://pubmed.ncbi.nlm.nih.gov/{doc_id}/"
                st.markdown(f"**Source {idx}:** {badge} [{id_label} {doc_id}]({pmurl})")
            else:
                st.markdown(f"**Source {idx}:** {badge} {id_label} {doc_id}")
            st.caption(snippet)

            # KG relations are only available for the PubMedQA knowledge graph.
            if ds_name == "pubmedqa":
                rels = _chunk_kg_rels(doc_id, mentioned, cooccurs)
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
    # Match any inline citation format: (PMID 123), (QID 0001234-5), (Case 001), (Source ...)
    cite_re = re.compile(
        r'\((PMID|QID|Case|Source)\s+[\w\-]+\)',
        re.IGNORECASE,
    )

    def _should_ignore(sentence: str) -> bool:
        lowered = sentence.lower().strip()
        return any(
            phrase in lowered for phrase in [
                "this information is for educational purposes only",
                "does not constitute medical advice",
                "consult a qualified healthcare professional",
                "call 911",
                "local emergency number",
            ]
        )

    flagged = [
        s for s in sentences
        if len(s.split()) > 5
        and not cite_re.search(s)
        and not _should_ignore(s)
    ]
    if not flagged:
        return

    with st.expander(f"⚠️ Citation check — {len(flagged)} sentence(s) without an inline citation", expanded=False):
        st.caption("Sentences longer than 5 words with no inline citation (PMID / QID / Case / Source) are highlighted.")
        for sentence in sentences:
            if not sentence.strip():
                continue
            if _should_ignore(sentence):
                st.caption(sentence)
                continue
            if len(sentence.split()) > 5 and not cite_re.search(sentence):
                st.markdown(
                    f"<span style='background:#fff3cd;padding:2px 6px;"
                    f"border-radius:3px;display:inline-block;margin:2px 0;'>"
                    f"⚠️ {sentence}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(sentence)


def _inject_inline_citations(answer: str, verdicts: list[dict]) -> str:
    """Attach PMID citations to uncited answer sentences when support is clear."""
    import re

    pmid_re = re.compile(r'\(PMIDs?\s*\d+(?:\s*,\s*\d+)*\)', re.IGNORECASE)
    stopwords = {
        "about", "after", "against", "among", "because", "before", "between",
        "could", "during", "every", "evidence", "first", "have", "into",
        "more", "most", "other", "over", "same", "such", "than", "that",
        "their", "there", "these", "they", "this", "those", "through",
        "under", "using", "which", "with", "within", "would",
    }

    def _tokens(text: str) -> set[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())
        return {w for w in words if w not in stopwords}

    supported = []
    for verdict in verdicts:
        if verdict.get("verdict") != "supported" or not verdict.get("pmid"):
            continue
        supported.append({
            "pmid": str(verdict["pmid"]),
            "tokens": _tokens(verdict.get("fact", "")),
        })

    if not answer.strip() or not supported:
        return answer

    unique_pmids: list[str] = []
    for item in supported:
        if item["pmid"] not in unique_pmids:
            unique_pmids.append(item["pmid"])

    def _append_citation(sentence: str, pmid: str) -> str:
        stripped = sentence.strip()
        match = re.search(r"([.!?])$", stripped)
        if match:
            return f"{stripped[:-1]} (PMID {pmid}){match.group(1)}"
        return f"{stripped} (PMID {pmid})"

    sentences = re.split(r'(?<=[.!?])\s+', answer.strip())
    revised: list[str] = []

    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            continue
        if len(stripped.split()) <= 5 or pmid_re.search(stripped):
            revised.append(stripped)
            continue

        sent_tokens = _tokens(stripped)
        best_pmid = None
        best_score = 0.0

        for item in supported:
            fact_tokens = item["tokens"]
            if not sent_tokens or not fact_tokens:
                continue
            score = len(sent_tokens & fact_tokens) / max(1, len(sent_tokens | fact_tokens))
            if score > best_score:
                best_score = score
                best_pmid = item["pmid"]

        if best_pmid and best_score >= 0.12:
            revised.append(_append_citation(stripped, best_pmid))
        elif len(unique_pmids) == 1:
            revised.append(_append_citation(stripped, unique_pmids[0]))
        else:
            revised.append(stripped)

    return " ".join(revised) if revised else answer


def _soften_low_factuality_answer(
    answer: str,
    verdicts: list[dict],
    score: float,
    threshold: float,
) -> str:
    """Make low-confidence answers visibly more conservative."""
    import re

    if not answer.strip() or score >= threshold:
        return answer

    supported_pmids = [
        str(v["pmid"]) for v in verdicts
        if v.get("verdict") == "supported" and v.get("pmid")
    ]
    supported_pmids = list(dict.fromkeys(supported_pmids))
    if len(supported_pmids) > 1:
        pmid_suffix = f" (PMIDs {', '.join(supported_pmids[:2])})"
    elif supported_pmids:
        pmid_suffix = f" (PMID {supported_pmids[0]})"
    else:
        pmid_suffix = ""

    caution = (
        "The retrieved evidence only partially supports a confident answer, "
        "so this summary is tentative"
        f"{pmid_suffix}."
    )

    sentences = re.split(r'(?<=[.!?])\s+', answer.strip())
    disclaimer_markers = (
        "this information is for educational purposes only",
        "does not constitute medical advice",
        "consult a qualified healthcare professional",
    )

    concise_sentence = ""
    for sentence in sentences:
        stripped = sentence.strip()
        lowered = stripped.lower()
        if not stripped:
            continue
        if any(marker in lowered for marker in disclaimer_markers):
            continue
        concise_sentence = stripped
        break

    if concise_sentence:
        return f"{caution}\n\n{concise_sentence}"
    return caution


def _extract_answer_body(answer: str) -> str:
    """Strip raw markdown section scaffolding from the model output."""
    import re

    text = (answer or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()

        if re.match(r"^#{1,6}\s*(key evidence|evidence|evidence sources?|why this answer)\b", stripped, re.IGNORECASE):
            break
        if not cleaned_lines and re.match(r"^#{1,6}\s+.+", stripped):
            continue
        if re.match(r"^#{1,6}\s*(answer|summary)\b", stripped, re.IGNORECASE):
            continue
        if stripped == "---":
            continue

        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned or text

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
        # Resolve correct citation label from the source datasets in the chunks.
        # Federated results can mix pubmedqa (PMID), medquad (QID), archehr_qa (Case).
        _DS_LABELS = {
            "pubmedqa":   ("PMID",   "PubMed abstracts"),
            "medquad":    ("QID",    "MedQuAD Q&A records"),
            "archehr_qa": ("Case",   "clinical EHR notes"),
        }
        _ds_set = {c.get("_dataset", "pubmedqa") for c in chunks}
        if len(_ds_set) == 1:
            _single_ds = next(iter(_ds_set))
            _id_label, _src_type = _DS_LABELS.get(_single_ds, ("Source", "medical evidence records"))
        else:
            _single_ds = ""
            _id_label, _src_type = "Source", "medical evidence records"
        _t0 = _time.perf_counter()
        answer = gen_fn(query, chunks, id_label=_id_label, source_type=_src_type, dataset=_single_ds)
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
            facts = decompose_facts(answer, dataset=_single_ds)
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
                _strict_ans = gen_fn(query, chunks, strict=True, id_label=_id_label, source_type=_src_type, dataset=_single_ds)
                gen_lat += _time.perf_counter() - _tc
                _strict_facts    = decompose_facts(_strict_ans, dataset=_single_ds)
                _strict_verdicts = verify_facts(_strict_facts, chunks) if _strict_facts else []
                _strict_n_sup    = sum(1 for v in _strict_verdicts
                                       if v.get("verdict") == "supported")
                _strict_score    = (_strict_n_sup / len(_strict_verdicts)
                                    if _strict_verdicts else 0.0)
                if _strict_score >= score:
                    answer, facts, verdicts = _strict_ans, _strict_facts, _strict_verdicts
                    n_sup, score, corrected = _strict_n_sup, _strict_score, True
                    st.write(f"✅ Corrected — factuality → {int(score * 100)}%")
                    _log.info("CORRECTION | accepted=True | new=%.2f", score)
                else:
                    st.write("ℹ️ Strict regeneration didn't improve factuality — "
                             "keeping original.")
                    _log.info("CORRECTION | accepted=False | new=%.2f", _strict_score)
            except Exception:
                pass

        answer = _inject_inline_citations(answer, verdicts)
        answer = _soften_low_factuality_answer(
            answer, verdicts, score, FACTUALITY_THRESHOLD
        )
        try:
            _safety = check_safety(answer)
        except Exception:
            _safety = {"is_safe": True, "flags": [],
                       "answer_with_disclaimer": answer}

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

# ── Load all indexes at startup (each cached independently) ───────────────────
_bundles: dict[str, dict] = {}
_index_errors: list[str] = []
for _ds, _cfg in _FEDERATED_DATASETS.items():
    try:
        _bundles[_ds] = load_index(_ds, _cfg["local_path"])
    except Exception as _ie:
        _index_errors.append(f"{_cfg['label']}: {_ie}")
        _log.warning("Index load failed for %s: %s", _ds, _ie)

if not _bundles:
    st.error("No knowledge base could be loaded. Check logs for details.")
    st.stop()

if _index_errors:
    st.warning("Some knowledge bases unavailable: " + " | ".join(_index_errors), icon="⚠️")

# Summary of loaded indexes
_total_chunks  = sum(len(b["corpus"])  for b in _bundles.values())
_total_records = sum(len(b["records"]) for b in _bundles.values())
_loaded_labels = [_FEDERATED_DATASETS[d]["label"] for d in _bundles]

# Params badge (PubMedQA BM25 params, shown for reference)
params_json = HERE / "bm25_params.json"
k1 = _bundles["pubmedqa"]["k1"] if "pubmedqa" in _bundles else 1.5
b  = _bundles["pubmedqa"]["b"]  if "pubmedqa" in _bundles else 0.75

_default_q = st.query_params.get("q", "")
_mode_options = [
    "None (BM25 only)",
    "KG expansion",
    "Cross-encoder reranker",
    "KG + Cross-encoder",
]
_default_mode = st.session_state.get("_ui_mode", _mode_options[0])

# ── Search form ────────────────────────────────────────────────────────────────
with st.form("search_form", border=False, clear_on_submit=False):
    fc1, fc2 = st.columns([6, 1])
    with fc1:
        query = st.text_input(
            "Ask a medical question",
            value=_default_q,
            placeholder="e.g. Do statins reduce cardiovascular mortality?",
            label_visibility="collapsed",
        )
    with fc2:
        submitted = st.form_submit_button(
            "Search ↵", type="primary", use_container_width=True
        )

    with st.expander("Advanced retrieval options", expanded=False):
        mode = st.selectbox(
            "Retrieval mode",
            options=_mode_options,
            index=_mode_options.index(_default_mode) if _default_mode in _mode_options else 0,
            help="Use this only when comparing retrieval strategies; the default keeps the product UX simple.",
        )

st.session_state["_ui_mode"] = mode

st.divider()

# ── Retrieval ─────────────────────────────────────────────────────────────────
if query.strip():
    # ── HIPAA Safe Harbour PHI scrubbing ──────────────────────────────────────
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
        query = _scrub.text

    use_kg       = mode in ("KG expansion", "KG + Cross-encoder")
    use_reranker = mode in ("Cross-encoder reranker", "KG + Cross-encoder")
    rag_top3_chunks: list[dict] = []
    rag_grounding_label = "top-5 federated chunks"

    # ── KG query expansion (applies to all datasets) ──────────────────────────
    search_query = query
    if use_kg:
        expand_fn = load_kg_expander()
        if expand_fn is None:
            st.warning("KG expansion unavailable — run track2_build_kg.py first.", icon="⚠️")
            use_kg = False
        else:
            search_query = expand_fn(query)
            added_terms = [t for t in search_query.split()
                           if t not in set(query.lower().split())]
            _log.info("KG_EXPAND | original=%r | expanded=%r | terms_added=%d",
                      query, search_query, len(added_terms))

    # ── Federated retrieval across all loaded indexes ─────────────────────────
    base_federated = retrieve_federated(search_query, _bundles, k_per=10)[:5]

    _last_q = st.session_state.get("_last_logged_query")
    if _last_q != query:
        _log.info(
            "QUERY | text(scrubbed)=%r | mode=%s | sources=%s | total_candidates=%d | "
            "top3_ids=%s",
            query, mode, list(_bundles.keys()), len(base_federated),
            [f"{ds}:{doc['pubid']}" for doc, _, _, ds in base_federated[:3]],
        )
        st.session_state["_last_logged_query"] = query

    # ── Optional CE reranking ─────────────────────────────────────────────────
    rerank_fn = None
    if use_reranker:
        rerank_fn = load_reranker()
        if rerank_fn is None:
            st.warning("Cross-encoder unavailable — run: pip install sentence-transformers",
                       icon="⚠️")

    if mode == "None":
        result_cards(base_federated, query=query)
        rag_top3_chunks = [
            {**doc} for doc, _, _, _ in base_federated[:5]
        ]
        rag_grounding_label = "top-5 federated chunks"
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("#### Federated baseline")
            result_cards(base_federated, query=query)

        with right:
            st.markdown(f"#### {mode}")
            enh_federated = retrieve_federated(search_query, _bundles, k_per=10)[:5]
            result_cards(enh_federated, query=search_query, rerank_fn=rerank_fn)

            if rerank_fn is not None:
                _cand_docs = [doc for doc, _, _, _ in enh_federated]
                _gen_docs  = rerank_fn(search_query, _cand_docs, top_k=5)
                rag_top3_chunks = [{**d} for d in _gen_docs]
                rag_grounding_label = "top-5 KG+CE federated chunks" if use_kg else "top-5 CE federated chunks"
            else:
                rag_top3_chunks = [{**doc} for doc, _, _, _ in enh_federated[:5]]
                rag_grounding_label = "top-5 KG federated chunks" if use_kg else "top-5 federated chunks"

    # ── RAG Generation + Evaluation ───────────────────────────────────────────
    st.divider()
    gen_fn = load_rag_generator()
    if gen_fn is not None:
        _top3_chunks = rag_top3_chunks or [
            {**doc} for doc, _, _, _ in base_federated[:5]
        ]

        _auto_submit = st.session_state.pop("_example_submitted", False)
        if (submitted or _auto_submit) and query.strip():
            if not _top3_chunks:
                st.warning("No retrieval evidence available to ground generation.")
                st.stop()
            _log.info("RAG_GEN | query=%r | source_ids=%s",
                      query, [c["pubid"] for c in _top3_chunks])
            _result = _run_core_pipeline(query, _top3_chunks, gen_fn)
            st.session_state["_rag_result"] = _result
            st.session_state["_rag_query"]  = query

            _rk = _ragas_key(query, _result["answer_with_disclaimer"])
            _rs = _ragas_store()
            _rs[_rk] = None
            threading.Thread(
                target=_run_ragas_thread,
                args=(_rs, _rk, query,
                      _result["answer_with_disclaimer"],
                      _top3_chunks,
                      _result["core_time"]),
                daemon=True,
            ).start()
            st.session_state["_ragas_key"] = _rk

        if (
            st.session_state.get("_rag_query") == query
            and "_rag_result" in st.session_state
        ):
            _result         = st.session_state["_rag_result"]
            _display_answer = _result["answer_with_disclaimer"]
            _answer_body    = _extract_answer_body(_display_answer)

            st.markdown("#### Answer")
            st.markdown(
                f"<div style='"
                f"background:#f0f7ff;border-left:4px solid #2196F3;"
                f"padding:1rem;border-radius:4px;line-height:1.7;'>"
                f"{_answer_body.replace(chr(10), '<br>')}"
                f"</div>",
                unsafe_allow_html=True,
            )

            _render_why_panel(_top3_chunks)
            _render_citation_gate(_answer_body)
            _render_eval_dashboard(_result)

            if "_ragas_key" in st.session_state:
                _ragas_panel(st.session_state["_ragas_key"])

        from rag_generate import MODEL as _RAG_MODEL
        st.caption(
            f"anthropic {_ANTHROPIC_VERSION} · model: {_RAG_MODEL} · "
            f"grounded on {rag_grounding_label} · "
            f"sources: {', '.join(_loaded_labels)}"
        )
    else:
        st.caption(
            "Install `anthropic` package to enable answer generation: "
            "`pip install anthropic>=0.25.0`"
        )

else:
    st.info(
        f"Ready — {_total_chunks:,} chunks from {_total_records:,} records across "
        f"{', '.join(_loaded_labels)}. Type a question above to search."
    )

    # Example questions drawn from each dataset
    for _ds, _bundle in _bundles.items():
        _ds_label = _FEDERATED_DATASETS[_ds]["label"]
        with st.expander(f"Example questions from {_ds_label}"):
            for rec in _bundle["records"][:5]:
                q_text = rec.get("question", "") or ""
                label  = q_text[:90] + ("…" if len(q_text) > 90 else "")
                doc_id = rec.get("pubid") or rec.get("doc_id", "")
                if st.button(label, key=f"{_ds}::{doc_id}"):
                    st.session_state["_example_q"] = q_text
                    st.rerun()

# Handle example question clicks
if "_example_q" in st.session_state:
    q = st.session_state.pop("_example_q")
    st.query_params["q"] = q
    st.session_state["_example_submitted"] = True
    st.rerun()



