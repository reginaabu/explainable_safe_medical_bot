# explainable_safe_medical_bot

Medical retrieval and grounded answer generation over PubMedQA.

Implemented core tracks:
- Track 1: BM25 retrieval baseline with saved metrics/results/error analysis.
- Track 2: SciSpacy entity extraction, KG construction, and KG query expansion.
- App: Streamlit retrieval UI with evidence snippets and PMID citations.
- Track 3 (lightweight): Claude-based answer generation plus safety/factuality checks.

## 1) Environment setup

Python 3.12 recommended.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 2) API keys

- `ANTHROPIC_API_KEY` is required only for generation/evaluation paths:
  - `app.py` "Generate Answer"
  - `eval_harness.py`
  - evaluator fact verification modules
- BM25 and KG pipelines do not require an API key.

You can set the key as an environment variable or in `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY = "your_key_here"
```

## 3) Reproducible run commands

Use the single entrypoint:

```bash
python run_pipeline.py track1
python run_pipeline.py track2
python run_pipeline.py strict-eval
python run_pipeline.py track3-eval --n 25 --seed 42
python run_pipeline.py app
```

### Track 1 output

`python run_pipeline.py track1` writes:
- `metrics.json`
- `bm25_results.csv`
- `error_analysis.md`

### Track 2 output

`python run_pipeline.py track2` does:
1. installs SciSpacy model via `scripts/install_scispacy.py`
2. runs `track2_build_kg.py`

Outputs:
- `pubmedqa_subset.csv`
- `entities.csv`
- `triples.csv`
- `eval_results.md`

### Strict evaluation output

`python run_pipeline.py strict-eval` writes:
- `strict_metrics.json`
- `strict_eval.md`

This protocol removes tuning leakage (train/dev/test separation for parameter search), but remains a closed-corpus benchmark.

### App launch

If `streamlit` command is not found, run via Python module:

```bash
python -m streamlit run app.py
```

or:

```bash
python run_pipeline.py app
```

## 4) Direct scripts (without run_pipeline.py)

- Track 1 baseline: `python scripts/run_track1.py`
- Track 2 KG build: `python track2_build_kg.py`
- Strict eval: `python scripts/strict_eval.py`
- Track 3 eval harness: `python eval_harness.py --n 25 --seed 42 --compare`

## 5) Notes on evaluation integrity

- Closed-corpus BM25 numbers can be optimistic versus open-domain retrieval.
- Use `scripts/strict_eval.py` alongside the standard metrics to separate tuning from test reporting.
- Report the exact protocol used when comparing methods.

## 6) Key files

- `app.py`: Streamlit app (BM25/KG/reranker retrieval + grounded generation UI)
- `track2_build_kg.py`: KG extraction/build/evaluation pipeline
- `kg_expand.py`: query expansion (`expand_query`)
- `eval_harness.py`: Track 3 CLI evaluation report generator
- `rag_generate.py`: Claude generation helper
- `evaluator/`: safety, fact decomposition/verification, and scoring modules

