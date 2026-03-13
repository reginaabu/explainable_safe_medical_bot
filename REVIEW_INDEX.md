# Review Index

Project: `explainable_safe_medical_bot`  
Status: P0 FIXES IMPLEMENTED, FINAL VALIDATION PENDING  
Last updated: 2026-03-13

## Read Order

1. `REVIEW_SUMMARY.md`
- One-page current status
- What works now
- Remaining sign-off checks

2. `PROJECT_REVIEW.md`
- Full technical detail
- Exact fixes implemented
- What still needs runtime confirmation

3. `FIX_TEMPLATES.md`
- Historical templates for fixes
- Kept as reference; code now contains implemented versions

## Key Corrections Since Earlier Draft

- Deterministic Track 1 script is now implemented (`scripts/run_track1.py`).
- Single CLI entrypoint exists (`run_pipeline.py`).
- Strict eval script exists (`scripts/strict_eval.py`) and artifacts are generated.
- App now uses selected retrieval mode for generation grounding.
- App disclaimer display path is wired to evaluator output.
- Eval harness now fails fast and exits non-zero on generation/eval/key failures.
- SciSpacy dependency pins and installer script were added; model URL typo fixed to `ai2-s2-scispacy`.

## Quick Verdict

- Implementation: strong for proposal core
- Reproducibility: substantially improved
- Evaluation integrity: improved (strict split added), still closed-corpus by design
- Remaining blocker: final local runtime confirmation for Track 2 model install and keyed Track 3 eval

