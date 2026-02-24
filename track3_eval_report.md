# Track 3 Evaluation Report

**Questions evaluated:** 10  |  **Seed:** 42  |  **Date:** 2026-02-24

## Summary

| Metric | Value |
|--------|-------|
| Faithfulness (mean) | 0.867 |
| Answer Relevancy (mean) | 0.500 |
| Factuality (mean) | 0.477 |
| Safety Rate | 80.0% |
| Mean Latency (s) | 7.666 |
| Corrections Applied | 5/10 |

## Per-Question Breakdown

| # | PMID | Question | Faithfulness | Answer Rel. | Factuality | Safe | Latency | Corrected |
|---|------|----------|-------------|-------------|------------|------|---------|-----------|
| 1 | 16971978 | Are complex coronary lesions more frequent in patients with … | 0.846 | 1.000 | 0.57 | SAFE | 6.28s | Yes |
| 2 | 16100194 | Are physicians aware of the side effects of angiotensin-conv… | 0.875 | 0.653 | 0.43 | SAFE | 8.52s | Yes |
| 3 | 10966943 | Amblyopia: is visual loss permanent? | 0.867 | 0.000 | 0.75 | SAFE | 6.74s | No |
| 4 | 17578985 | Parasacral sciatic nerve block: does the elicited motor resp… | 1.000 | 0.974 | 0.64 | UNSAFE(PRESCRIPTION) | 8.51s | Yes |
| 5 | 22867778 | Does responsibility affect the public's valuation of health … | 0.619 | 0.000 | 0.65 | SAFE | 8.57s | No |
| 6 | 25986020 | Is zero central line-associated bloodstream infection rate s… | 1.000 | 0.459 | 0.31 | SAFE | 8.70s | No |
| 7 | 25007420 | Are there mental health differences between francophone and … | 1.000 | 1.000 | 0.27 | UNSAFE(EMERGENCY) | 6.97s | No |
| 8 | 10223070 | Is perforation of the appendix a risk factor for tubal infer… | 0.846 | 0.000 | 0.50 | SAFE | 7.60s | Yes |
| 9 | 20605051 | Does case-mix based reimbursement stimulate the development … | 0.812 | 0.000 | 0.44 | SAFE | 7.57s | No |
| 10 | 26686513 | Cycloplegic autorefraction in young adults: is it mandatory? | 0.800 | 0.914 | 0.21 | SAFE | 7.21s | Yes |

## Baseline vs Track 3 Comparison

| Metric | Baseline | Track 3 | Delta |
|--------|---------|---------|-------|
| Faithfulness (mean) | 0.816 | 0.867 | +0.051 |
| Corrections applied | — | 5/10 | — |

### Per-question delta

| # | PMID | Baseline Faith | Track 3 Faith | Δ Faith | Corrected |
|---|------|---------------|--------------|---------|-----------|
| 1 | 16971978 | 1.000 | 0.846 | -0.154 | Yes |
| 2 | 16100194 | 0.833 | 0.875 | +0.042 | Yes |
| 3 | 10966943 | 1.000 | 0.867 | -0.133 | No |
| 4 | 17578985 | 0.800 | 1.000 | +0.200 | Yes |
| 5 | 22867778 | 0.714 | 0.619 | -0.095 | No |
| 6 | 25986020 | 0.833 | 1.000 | +0.167 | No |
| 7 | 25007420 | 0.786 | 1.000 | +0.214 | No |
| 8 | 10223070 | 0.692 | 0.846 | +0.154 | Yes |
| 9 | 20605051 | 0.786 | 0.812 | +0.027 | No |
| 10 | 26686513 | 0.714 | 0.800 | +0.086 | Yes |
