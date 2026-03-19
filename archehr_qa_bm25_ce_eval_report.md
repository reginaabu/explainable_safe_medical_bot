# Track 3 Evaluation Report

**Dataset:** archehr_qa  |  **Mode:** bm25+ce  |  **Questions evaluated:** 20  |  **Seed:** 42  |  **Date:** 2026-03-19

## Summary

| Metric | Value |
|--------|-------|
| Faithfulness (mean) | 0.653 |
| Answer Relevancy (mean) | 0.665 |
| Factuality (mean) | 0.787 |
| Safety Rate | 95.0% |
| Mean Latency (s) | 5.338 |
| Corrections Applied | 2/20 |

## Per-Question Breakdown

| # | CASE_ID | Question | Faithfulness | Answer Rel. | Factuality | Safe | Latency | Corrected |
|---|------|----------|-------------|-------------|------------|------|---------|-----------|
| 1 | 4 | Why was cardiac catheterization recommended to the patient? | 0.091 | 0.800 | 0.90 | SAFE | 4.10s | No |
| 2 | 1 | Why was ERCP recommended to him over continuing a medication… | 0.909 | 0.200 | 1.00 | SAFE | 5.15s | No |
| 3 | 9 | What treatments did she receive for complications during her… | 1.000 | 0.750 | 0.43 | SAFE | 7.21s | No |
| 4 | 8 | Will the poison damage to his body last and is the confusion… | 0.938 | 0.200 | 0.50 | SAFE | 7.58s | No |
| 5 | 17 | What should he do to relieve palpitations and anxiety? | 0.333 | 0.500 | 1.00 | SAFE | 4.69s | No |
| 6 | 3 | What is the expected course of recovery for him? | 0.900 | 0.750 | 0.73 | SAFE | 4.34s | No |
| 7 | 12 | What can cause her persistent stomach pain? | 1.000 | 0.750 | 0.90 | SAFE | 4.99s | No |
| 8 | 2 | Why was he given lasix and his oxygen flow rate was reduced? | 0.833 | 0.850 | 0.83 | SAFE | 4.02s | No |
| 9 | 11 | What is the expected course of her recovery? | 0.600 | 0.500 | 0.27 | SAFE | 5.58s | Yes |
| 10 | 18 | Should he go back to the ER if he has diarrhea and vomiting? | 0.500 | 0.500 | 1.00 | SAFE | 4.74s | No |
| 11 | 13 | What should the patient do if she is in in pain and cannot m… | 0.429 | 0.850 | 0.57 | SAFE | 4.85s | Yes |
| 12 | 7 | Are there specific instructions about blood thinners due to … | 0.889 | 0.850 | 0.89 | SAFE | 5.59s | No |
| 13 | 19 | Are her symptoms related to anxiety or cardiovascular proces… | 0.636 | 0.950 | 1.00 | SAFE | 4.43s | No |
| 14 | 16 | Could her back pain and dizziness be concerning for a stroke… | 1.000 | 0.800 | 0.91 | SAFE | 4.84s | No |
| 15 | 14 | Was there any evidence for stomach cancer? | 0.000 | 0.950 | 0.89 | SAFE | 3.67s | No |
| 16 | 10 | Did she sustain any brain damage from the heart attack? | 0.727 | 0.200 | 0.56 | SAFE | 6.21s | No |
| 17 | 5 | Is the pain connected to the overdose or something else? | 0.000 | 0.750 | 0.65 | UNSAFE(EMERGENCY) | 6.48s | No |
| 18 | 15 | Did his infection spread to other anatomies causing infertil… | 0.500 | 1.000 | 1.00 | SAFE | 3.81s | No |
| 19 | 6 | Why did they find out later that he had fungal pneumonia? | 0.833 | 0.350 | 0.79 | SAFE | 9.18s | No |
| 20 | 20 | How did they diagnose her with migraine for spinning sensati… | 0.933 | 0.800 | 0.92 | SAFE | 5.30s | No |
