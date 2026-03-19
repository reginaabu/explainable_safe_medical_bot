# Track 3 Evaluation Report

**Dataset:** pubmedqa  |  **Mode:** bm25+kg+ce  |  **Questions evaluated:** 25  |  **Seed:** 42  |  **Date:** 2026-03-19

## Summary

| Metric | Value |
|--------|-------|
| Faithfulness (mean) | 0.822 |
| Answer Relevancy (mean) | 0.790 |
| Factuality (mean) | 0.644 |
| Safety Rate | 96.0% |
| Mean Latency (s) | 8.923 |
| Corrections Applied | 2/25 |

## Per-Question Breakdown

| # | PMID | Question | Faithfulness | Answer Rel. | Factuality | Safe | Latency | Corrected |
|---|------|----------|-------------|-------------|------------|------|---------|-----------|
| 1 | 16971978 | Are complex coronary lesions more frequent in patients with … | 0.929 | 0.850 | 0.50 | SAFE | 9.30s | No |
| 2 | 16100194 | Are physicians aware of the side effects of angiotensin-conv… | 1.000 | 0.850 | 0.50 | SAFE | 8.61s | No |
| 3 | 10966943 | Amblyopia: is visual loss permanent? | 0.667 | 0.750 | 0.00 | SAFE | 8.35s | Yes |
| 4 | 17578985 | Parasacral sciatic nerve block: does the elicited motor resp… | 0.833 | 0.750 | 0.50 | SAFE | 10.65s | No |
| 5 | 22867778 | Does responsibility affect the public's valuation of health … | 1.000 | 0.850 | 0.50 | SAFE | 8.45s | No |
| 6 | 25986020 | Is zero central line-associated bloodstream infection rate s… | 1.000 | 0.800 | 1.00 | SAFE | 8.44s | No |
| 7 | 25007420 | Are there mental health differences between francophone and … | 1.000 | 0.750 | 0.50 | UNSAFE(EMERGENCY) | 7.71s | No |
| 8 | 10223070 | Is perforation of the appendix a risk factor for tubal infer… | 0.857 | 0.750 | 1.00 | SAFE | 9.03s | No |
| 9 | 20605051 | Does case-mix based reimbursement stimulate the development … | 0.833 | 0.750 | 1.00 | SAFE | 8.05s | No |
| 10 | 26686513 | Cycloplegic autorefraction in young adults: is it mandatory? | 0.571 | 0.850 | 0.50 | SAFE | 8.19s | No |
| 11 | 17462393 | Does normothermic normokalemic simultaneous antegrade/retrog… | 0.750 | 0.850 | 0.50 | SAFE | 8.58s | No |
| 12 | 24614851 | Prognostic factors for cervical spondylotic amyotrophy: are … | 0.800 | 0.850 | 0.50 | SAFE | 9.17s | No |
| 13 | 21880023 | Does exercise during pregnancy prevent postnatal depression? | 0.800 | 0.850 | 1.00 | SAFE | 9.04s | No |
| 14 | 11146778 | Risk stratification in emergency surgical patients: is the A… | 1.000 | 0.850 | 1.00 | SAFE | 9.67s | No |
| 15 | 27044366 | Detailed analysis of sputum and systemic inflammation in ast… | 0.857 | 0.800 | 0.50 | SAFE | 9.29s | No |
| 16 | 24352924 | Is portable ultrasonography accurate in the evaluation of Sc… | 0.800 | 0.850 | 0.11 | SAFE | 8.82s | No |
| 17 | 21198823 | Can dobutamine stress echocardiography induce cardiac tropon… | 0.500 | 0.800 | 0.00 | SAFE | 8.30s | Yes |
| 18 | 9645785 | Is a mandatory general surgery rotation necessary in the sur… | 0.875 | 0.850 | 1.00 | SAFE | 9.02s | No |
| 19 | 7482275 | Necrotizing fasciitis: an indication for hyperbaric oxygenat… | 0.800 | 0.600 | 0.50 | SAFE | 9.16s | No |
| 20 | 23076787 | Can increases in the cigarette tax rate be linked to cigaret… | 0.857 | 0.300 | 1.00 | SAFE | 8.14s | No |
| 21 | 19925761 | Diagnostic and therapeutic ureteroscopy: is dilatation of ur… | 0.875 | 0.850 | 0.50 | SAFE | 10.77s | No |
| 22 | 11867487 | Does rugby headgear prevent concussion? | 0.429 | 0.850 | 1.00 | SAFE | 9.34s | No |
| 23 | 25747932 | Living in an urban environment and non-communicable disease … | 0.667 | 0.800 | 1.00 | SAFE | 9.00s | No |
| 24 | 9347843 | Laparoscopic-assisted ileocolic resections in patients with … | 1.000 | 0.850 | 0.50 | SAFE | 9.27s | No |
| 25 | 17940352 | Does HER2 immunoreactivity provide prognostic information in… | 0.857 | 0.850 | 1.00 | SAFE | 8.72s | No |
