"""
utils/dataset_adapter.py – Normalise multiple medical QA dataset schemas
into the internal pipeline format: {"doc_id": str, "question": str, "context": str}

Supported datasets
------------------
pubmedqa   – PubMedQA (default); doc_id=PMID, context=abstract
medquad    – MedQuAD (NIH Q&A); doc_id=qid, context=answer text
archehr_qa – ArchEHR-QA on MIMIC-IV; doc_id=case_id, context=note excerpt sentences
             (requires PhysioNet access — local XML only)
             Pass --csv-path pointing to:
               • archehr-qa.xml            (key JSON auto-detected alongside it), OR
               • a directory containing archehr-qa.xml
mimic3     – MIMIC-III NOTEEVENTS; doc_id=ROW_ID, context=clinical note
             (requires PhysioNet access — local CSV only)
mimic4     – MIMIC-IV discharge notes; doc_id=note_id, context=note text
             (requires PhysioNet access — local CSV only)

Usage
-----
    from utils.dataset_adapter import load_dataset_rows, get_id_label, get_source_type

    rows = load_dataset_rows("medquad")                          # HuggingFace auto-download
    rows = load_dataset_rows("pubmedqa", csv_path=p)             # local CSV
    rows = load_dataset_rows("archehr_qa", csv_path="archehr-qa.xml")   # local XML
    rows = load_dataset_rows("archehr_qa", csv_path="/data/archehr/")   # directory
"""
from __future__ import annotations

import csv
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

log = logging.getLogger(__name__)

# ── Per-dataset metadata ───────────────────────────────────────────────────────
# id_label    : displayed in reports and citation strings  (replaces "PMID")
# source_type : used in generation prompts                 (replaces "PubMed abstracts")
# fields      : maps canonical names → actual column names in the raw data
# hf_name     : HuggingFace dataset identifier, or None if access-gated
# hf_config   : HuggingFace config/subset name, or None

DATASET_META: dict[str, dict] = {
    "pubmedqa": {
        "id_label":         "PMID",
        "source_type":      "PubMed abstracts",
        "default_retriever": "bm25",
        "fields":           {"doc_id": "doc_id", "question": "question", "context": "context", "focus": None},
        "hf_name":          "pubmed_qa",
        "hf_config":        "pqa_labeled",
    },
    "medquad": {
        "id_label":         "QID",
        "source_type":      "medical Q&A answers",
        "default_retriever": "hybrid",
        "fields":           {"doc_id": "question_id", "question": "question", "context": "answer",
                             "focus": "question_focus", "q_type": "question_type"},
        "hf_name":          "lavita/MedQuAD",
        "hf_config":        None,
    },
    "archehr_qa": {
        "id_label":         "CASE_ID",
        "source_type":      "clinical discharge notes",
        # Semantic retrieval works best: patient narratives vs clinical sentences
        "default_retriever": "semantic",
        # fields not used for XML loading — handled by load_archehr_xml()
        "fields":           {"doc_id": "case_id", "question": "clinician_question",
                             "context": "note_excerpt", "focus": "patient_narrative",
                             "q_type": "clinical_specialty"},
        "hf_name":          None,   # PhysioNet-gated; local XML only
        "hf_config":        None,
        "loader":           "xml",  # signals load_dataset_rows to use XML loader
    },
    "mimic3": {
        "id_label":         "NOTE_ID",
        "source_type":      "clinical notes",
        "default_retriever": "bm25",
        "fields":           {"doc_id": "ROW_ID", "question": None, "context": "TEXT", "focus": None},
        "hf_name":          None,   # PhysioNet-gated; local CSV only
        "hf_config":        None,
    },
    "mimic4": {
        "id_label":         "NOTE_ID",
        "source_type":      "clinical notes",
        "default_retriever": "bm25",
        "fields":           {"doc_id": "note_id", "question": None, "context": "text", "focus": None},
        "hf_name":          None,   # PhysioNet-gated; local CSV only
        "hf_config":        None,
    },
}


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_meta(dataset: str) -> dict:
    if dataset not in DATASET_META:
        raise ValueError(
            f"Unknown dataset '{dataset}'. "
            f"Supported: {', '.join(DATASET_META)}"
        )
    return DATASET_META[dataset]


def get_id_label(dataset: str) -> str:
    """Return the citation label used in prompts and reports, e.g. 'PMID' or 'QID'."""
    return get_meta(dataset)["id_label"]


def get_source_type(dataset: str) -> str:
    """Return a human-readable description of the evidence type for prompts."""
    return get_meta(dataset)["source_type"]


def get_default_retriever(dataset: str) -> str:
    """Return the recommended retriever for this dataset: 'bm25', 'semantic', or 'hybrid'."""
    return get_meta(dataset)["default_retriever"]


def normalise_row(raw: dict, dataset: str) -> dict:
    """Map a raw CSV/dict row to canonical {"doc_id", "question", "context", "focus", "q_type"}."""
    fields   = get_meta(dataset)["fields"]
    doc_id   = raw.get(fields["doc_id"], "") or ""
    q_field  = fields["question"]
    question = raw.get(q_field, "") if q_field else ""
    context  = raw.get(fields["context"], "") or ""
    f_field  = fields.get("focus")
    focus    = raw.get(f_field, "") if f_field else ""
    t_field  = fields.get("q_type")
    q_type   = raw.get(t_field, "") if t_field else ""
    return {
        "doc_id":   str(doc_id),
        "question": str(question),
        "context":  str(context),
        "focus":    str(focus or ""),
        "q_type":   str(q_type or ""),
    }


# ── ArchEHR-QA XML loader ─────────────────────────────────────────────────────

def _find_archehr_files(path: Path) -> tuple[Path, Path | None, Path | None]:
    """
    Given a path that is either the XML file itself, or a directory,
    return (xml_path, key_path, mapping_path).
    key_path and mapping_path may be None if not found.
    """
    if path.is_dir():
        xml_candidates = list(path.glob("archehr-qa*.xml")) + list(path.glob("*.xml"))
        if not xml_candidates:
            raise FileNotFoundError(f"No .xml file found in directory: {path}")
        xml_path = xml_candidates[0]
    else:
        xml_path = path

    dir_ = xml_path.parent

    def _find(suffixes: list[str]) -> Path | None:
        for s in suffixes:
            p = dir_ / s
            if p.exists():
                return p
        return None

    key_path = _find(["archehr-qa_key.json", "key.json"])
    mapping_path = _find(["archehr-qa_mapping.json", "mapping.json"])
    return xml_path, key_path, mapping_path


def load_archehr_xml(
    path: Path | str,
    max_rows: int | None = None,
) -> list[dict]:
    """
    Parse an ArchEHR-QA XML file (+ optional *_key.json / *_mapping.json)
    and return canonical rows: {doc_id, question, context, focus, q_type}.

    Real XML format (PhysioNet archehr-qa-bionlp-task-2025)
    --------------------------------------------------------
    <annotations>
      <case id="1">
        <patient_narrative>Full patient question text...</patient_narrative>
        <patient_question>
          <phrase id="0" start_char_index="0">key phrase</phrase>
        </patient_question>
        <clinician_question>Clinician reformulation...</clinician_question>
        <note_excerpt>Raw note text with ... placeholders</note_excerpt>
        <note_excerpt_sentences>       <!-- sibling of note_excerpt -->
          <sentence id="0" paragraph_id="0" start_char_index="0">Sentence text.</sentence>
          ...
        </note_excerpt_sentences>
      </case>
    </annotations>

    Key JSON  (development set only)
    ---------------------------------
    [{"case_id": "1",
      "answers": [{"sentence_id": "0", "relevance": "essential"}, ...]}]

    Mapping JSON
    ------------
    [{"case_id": "1", "document_id": "...", "document_source": "mimic-iii"}]

    Context selection
    -----------------
    If key is available: keep sentences with relevance "essential" or
    "supplementary" (skip "not-relevant").  Falls back to all sentences.

    q_type
    ------
    Populated from document_source in mapping.json ("mimic-iii" / "mimic-iv").
    Falls back to empty string if mapping not available.
    """
    path = Path(path)
    xml_path, key_path, mapping_path = _find_archehr_files(path)

    # -- relevance annotations (key JSON) --
    relevance_map: dict[str, set[str]] = {}   # case_id → set of relevant sentence ids
    if key_path:
        with open(key_path, encoding="utf-8") as f:
            key_data = json.load(f)
        if isinstance(key_data, dict):
            key_data = list(key_data.values())
        for entry in key_data:
            cid = str(entry.get("case_id", ""))
            relevant_ids = {
                str(a["sentence_id"])
                for a in entry.get("answers", [])
                if a.get("relevance") in ("essential", "supplementary")
            }
            relevance_map[cid] = relevant_ids
        log.info("Loaded relevance annotations for %d cases from %s",
                 len(relevance_map), key_path.name)
    else:
        log.info("No key JSON found — using all note sentences as context")

    # -- document source mapping --
    source_map: dict[str, str] = {}   # case_id → "mimic-iii" / "mimic-iv"
    if mapping_path:
        with open(mapping_path, encoding="utf-8") as f:
            mapping_data = json.load(f)
        for entry in mapping_data:
            cid = str(entry.get("case_id", ""))
            source_map[cid] = entry.get("document_source", "")
        log.info("Loaded source mappings for %d cases from %s",
                 len(source_map), mapping_path.name)

    # -- parse XML --
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Root may be <annotations>, <archehr-qa>, or similar; cases are <case> elements
    cases = root.findall(".//case")
    if not cases:
        cases = list(root)

    rows: list[dict] = []
    for case in cases:
        case_id = str(case.get("id", "") or "").strip()

        # Question fields — strip leading/trailing whitespace from element text
        clinician_q = (case.findtext("clinician_question") or "").strip()
        patient_narr = (case.findtext("patient_narrative") or "").strip()

        # Use clinician question as primary; fall back to patient narrative
        question = clinician_q or patient_narr

        # Clinical specialty — present in real PhysioNet data, absent in public GitHub dev
        specialty = (case.findtext("clinical_specialty") or "").strip()

        # Context: <note_excerpt_sentences> is a DIRECT child of <case>
        # (sibling of <note_excerpt>, NOT nested inside it)
        relevant_ids = relevance_map.get(case_id)  # None = no key → use all
        sentences: list[str] = []
        sent_container = case.find("note_excerpt_sentences")
        if sent_container is None:
            # Fallback: search anywhere in case subtree
            sent_container = case.find(".//note_excerpt_sentences")
        if sent_container is not None:
            for sent in sent_container.findall("sentence"):
                sid = str(sent.get("id", "")).strip()
                text = (sent.text or "").strip()
                if not text or text == "...":
                    continue
                if relevant_ids is None or sid in relevant_ids:
                    sentences.append(text)
        context = " ".join(sentences).strip()

        # Skip cases with no usable content (questions without note excerpts
        # are available in the public GitHub dev set but lack context)
        if not question:
            log.debug("Skipping case %s: no question text", case_id)
            continue
        if not context:
            log.debug("Skipping case %s: no note sentences (note excerpts may "
                      "require PhysioNet access — see README)", case_id)
            continue

        rows.append({
            "doc_id":   case_id,
            "question": question,
            "context":  context,
            "focus":    patient_narr,
            # Prefer clinical_specialty (real data) over document_source (mapping)
            "q_type":   specialty or source_map.get(case_id, ""),
        })

        if max_rows and len(rows) >= max_rows:
            break

    log.info("Loaded %d cases from %s (key=%s, mapping=%s)",
             len(rows), xml_path.name,
             "yes" if key_path else "no",
             "yes" if mapping_path else "no")
    return rows


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_csv(path: Path, dataset: str) -> list[dict]:
    """Load and normalise rows from a local CSV file."""
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            rows.append(normalise_row(raw, dataset))
    log.info("Loaded %d records from %s (dataset=%s)", len(rows), Path(path).name, dataset)
    return rows


def load_hf(dataset: str, max_rows: int | None = None) -> list[dict]:
    """Download from HuggingFace Hub and normalise rows."""
    from datasets import load_dataset as _load_hf

    meta = get_meta(dataset)
    if meta["hf_name"] is None:
        raise RuntimeError(
            f"Dataset '{dataset}' has no HuggingFace source — "
            "provide a local CSV with --csv-path."
        )

    log.info("Downloading '%s' from HuggingFace …", meta["hf_name"])
    kwargs: dict = {}
    if meta["hf_config"]:
        kwargs["name"] = meta["hf_config"]

    ds = _load_hf(meta["hf_name"], **kwargs)
    split = next(iter(ds))
    fields = meta["fields"]
    rows: list[dict] = []

    for item in ds[split]:
        # PubMedQA has a nested context dict — flatten it
        focus = ""
        q_type = ""
        if dataset == "pubmedqa":
            ctx_raw = item.get("context", {})
            context = " ".join(ctx_raw.get("contexts", [])) if isinstance(ctx_raw, dict) else str(ctx_raw)
            doc_id  = str(item.get("pubid", ""))
            question = item.get("question", "")
        else:
            context  = str(item.get(fields["context"], "") or "")
            doc_id   = str(item.get(fields["doc_id"], "") or "")
            q_field  = fields["question"]
            question = str(item.get(q_field, "") or "") if q_field else ""
            f_field  = fields.get("focus")
            focus    = str(item.get(f_field, "") or "") if f_field else ""
            t_field  = fields.get("q_type")
            q_type   = str(item.get(t_field, "") or "") if t_field else ""

        rows.append({"doc_id": doc_id, "question": question, "context": context,
                     "focus": focus, "q_type": q_type})
        if max_rows and len(rows) >= max_rows:
            break

    log.info("Loaded %d records from HuggingFace (dataset=%s)", len(rows), dataset)
    return rows


def load_dataset_rows(
    dataset: str,
    csv_path: Path | str | None = None,
    max_rows: int | None = None,
) -> list[dict]:
    """
    Load normalised rows for any supported dataset.

    Priority
    --------
    1. Local file/directory at csv_path (if provided and exists):
         • .xml or directory → XML loader (ArchEHR-QA)
         • otherwise         → CSV loader
    2. HuggingFace auto-download (if hf_name is configured for this dataset)
    3. Raise an informative FileNotFoundError

    Parameters
    ----------
    dataset  : one of the keys in DATASET_META
    csv_path : path to a local CSV/XML file or directory (optional)
    max_rows : cap the number of rows returned (useful for quick tests)
    """
    meta = get_meta(dataset)

    if csv_path:
        p = Path(csv_path)
        if p.exists():
            # Route XML-based datasets through the XML loader
            if meta.get("loader") == "xml" or p.suffix.lower() == ".xml" or p.is_dir():
                rows = load_archehr_xml(p, max_rows=max_rows)
                return rows
            rows = load_csv(p, dataset)
            return rows[:max_rows] if max_rows else rows
        # Path provided but doesn't exist
        log.warning("csv_path '%s' does not exist — falling back to HuggingFace", csv_path)

    if meta["hf_name"]:
        return load_hf(dataset, max_rows=max_rows)

    raise FileNotFoundError(
        f"No local data found at '{csv_path}' and dataset '{dataset}' "
        "requires credentialed access (PhysioNet). "
        "Download archehr-qa.xml from https://physionet.org/content/archehr-qa-bionlp-task-2025/ "
        "and pass --csv-path pointing to the file or its directory."
    )
