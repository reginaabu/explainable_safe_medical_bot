# Project Review (Updated)

Date: 2026-03-13  
Repo: `reginaabu/explainable_safe_medical_bot`  
Verdict: P0 FIXES IMPLEMENTED, FINAL SIGN-OFF PENDING RUNTIME CHECKS

## 1) Scope Alignment

Project intent vs implementation:
- Track 1 BM25 baseline: implemented.
- Track 2 KG query expansion: implemented.
- RAG answer generation with citations: implemented.
- Lightweight self-monitoring: implemented (safety + fact decomposition/verification + scoring).

Stretch goals (RL alignment / heavy GraphRAG training): not implemented, and not required for core completion.

## 2) What Is Done (Verifiable)

### Deterministic run paths
- `run_pipeline.py` provides one-command entry points:
  - `track1`, `track2`, `strict-eval`, `track3-eval`, `app`
- `scripts/run_track1.py` generates:
  - `metrics.json`
  - `bm25_results.csv`
  - `error_analysis.md`
- `scripts/strict_eval.py` generates:
  - `strict_metrics.json`
  - `strict_eval.md`

### App behavior fixes
- RAG grounding now follows selected retrieval mode (BM25/KG/reranker mode path), not always BM25 baseline.
- Safety-wrapped answer display path now uses `answer_with_disclaimer` when evaluation data is available.

### Evaluation harness integrity fixes
- `eval_harness.py` now fails fast and exits non-zero when:
  - Anthropic key is missing
  - generation fails
  - evaluation fails
- It does not write a misleading success report on failed runs.

### Reproducibility hardening
- `requirements.txt` pinned for SciSpacy compatibility:
  - `numpy==1.26.4`
  - `spacy==3.7.5`
  - `scispacy==0.5.4`
- `scripts/install_scispacy.py` added for automated base dependency + model install flow.
- SciSpacy model URL typo fixed from `ai2-s3-scispacy` to `ai2-s2-scispacy`.
- Loaders in `app.py`, `track2_build_kg.py`, `scripts/run_track1.py`, `scripts/strict_eval.py` now prefer local `pubmedqa_subset.csv` for offline reliability.

## 3) Verified Command Outcomes

Verified in this audit environment:
- `python run_pipeline.py track1`: PASS, artifacts written.
- `python run_pipeline.py strict-eval`: PASS, artifacts written.
- `python eval_harness.py --n 1 --seed 1` without API key: exits code 2 (fail-fast), no report overwrite.
- `python run_pipeline.py track2 --skip-model-install`: exits with clear missing-model error message.

User-side observation captured:
- Base SciSpacy packages install succeeds.
- Previous model download failed due stale URL bucket (now patched to `ai2-s2`).

## 4) What Is Still Pending for Full Sign-Off

1. Track 2 full run must be re-verified after URL fix:
   - `python scripts/install_scispacy.py`
   - `python run_pipeline.py track2 --skip-model-install`
2. Track 3 full keyed run should be executed once with real `ANTHROPIC_API_KEY`:
   - `python run_pipeline.py track3-eval --n 25 --seed 42 --compare`
3. App smoke test should confirm all four retrieval modes + generation path:
   - `python run_pipeline.py app`

## 5) Evaluation Validity Notes

- Strict split (`strict_eval.py`) addresses tuning leakage by using train/dev/test query splits with dev model selection and test-only reporting.
- Retrieval remains closed-corpus over PubMedQA subset; metrics are still optimistic relative to open-domain PubMed retrieval.
- Current recommendation: report both:
  - closed-corpus baseline (`metrics.json`)
  - strict split (`strict_metrics.json`)

## 6) P0 / P1 / P2 Status

### P0 (must-fix)
- Deterministic Track 1 command and outputs: DONE
- SciSpacy compatibility pins + installer: DONE
- Fail-fast eval harness: DONE
- App disclaimer and retrieval-grounding wiring: DONE
- Strict evaluation protocol script: DONE

### P1 (should-fix)
- Add CI/integration smoke tests for `track1`, `strict-eval`, `track2` (if model exists), app import/start.
- Add explicit artifact versioning per run (timestamped output folder).
- Add one short "evaluation protocol" section to manuscript/report using strict+closed-corpus side by side.

### P2 (nice-to-have)
- Optional hard-set benchmark (`build_hard_set.py`) integrated into `run_pipeline.py`.
- Optional config file for model/dependency toggles.

## 7) Final Statement

Core implementation now matches proposal intent and major correctness/reproducibility gaps were patched in code.  
Project is ready for final sign-off once Track 2 model install rerun and one keyed Track 3 evaluation run are confirmed in the target local environment.
