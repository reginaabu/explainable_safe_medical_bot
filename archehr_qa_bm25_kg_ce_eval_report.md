# Track 3 Evaluation Report

**Dataset:** archehr_qa  |  **Mode:** bm25+kg+ce  |  **Questions evaluated:** 20  |  **Seed:** 42  |  **Date:** 2026-03-19

## Summary

| Metric | Value |
|--------|-------|
| Faithfulness (mean) | 0.691 |
| Answer Relevancy (mean) | 0.740 |
| Factuality (mean) | 0.759 |
| Safety Rate | 95.0% |
| Mean Latency (s) | 5.564 |
| Corrections Applied | 2/20 |

## Per-Question Breakdown

| # | CASE_ID | Question | Faithfulness | Answer Rel. | Factuality | Safe | Latency | Corrected |
|---|------|----------|-------------|-------------|------------|------|---------|-----------|
| 1 | 4 | Why was cardiac catheterization recommended to the patient? | 0.125 | 1.000 | 0.73 | SAFE | 4.23s | No |
| 2 | 1 | Why was ERCP recommended to him over continuing a medication… | 1.000 | 0.850 | 1.00 | SAFE | 4.80s | No |
| 3 | 9 | What treatments did she receive for complications during her… | 0.889 | 0.850 | 0.44 | SAFE | 5.53s | Yes |
| 4 | 8 | Will the poison damage to his body last and is the confusion… | 1.000 | 0.200 | 0.82 | SAFE | 7.01s | No |
| 5 | 17 | What should he do to relieve palpitations and anxiety? | 0.571 | 0.500 | 1.00 | SAFE | 6.57s | No |
| 6 | 3 | What is the expected course of recovery for him? | 0.833 | 0.700 | 0.92 | SAFE | 4.98s | No |
| 7 | 12 | What can cause her persistent stomach pain? | 0.818 | 0.750 | 0.83 | SAFE | 5.04s | No |
| 8 | 2 | Why was he given lasix and his oxygen flow rate was reduced? | 0.692 | 0.850 | 0.85 | SAFE | 4.77s | No |
| 9 | 11 | What is the expected course of her recovery? | 1.000 | 0.600 | 0.27 | SAFE | 7.50s | Yes |
| 10 | 18 | Should he go back to the ER if he has diarrhea and vomiting? | 1.000 | 0.200 | 1.00 | SAFE | 5.28s | No |
| 11 | 13 | What should the patient do if she is in in pain and cannot m… | 0.833 | 0.850 | 0.71 | SAFE | 5.15s | No |
| 12 | 7 | Are there specific instructions about blood thinners due to … | 0.667 | 0.900 | 1.00 | SAFE | 5.57s | No |
| 13 | 19 | Are her symptoms related to anxiety or cardiovascular proces… | 0.895 | 0.900 | 0.67 | SAFE | 5.57s | No |
| 14 | 16 | Could her back pain and dizziness be concerning for a stroke… | 0.333 | 0.750 | 0.70 | SAFE | 5.66s | No |
| 15 | 14 | Was there any evidence for stomach cancer? | 0.769 | 1.000 | 0.57 | SAFE | 4.32s | No |
| 16 | 10 | Did she sustain any brain damage from the heart attack? | 1.000 | 0.900 | 0.47 | SAFE | 4.71s | No |
| 17 | 5 | Is the pain connected to the overdose or something else? | 0.000 | 0.750 | 0.61 | UNSAFE(EMERGENCY) | 7.16s | No |
| 18 | 15 | Did his infection spread to other anatomies causing infertil… | 0.429 | 0.800 | 0.70 | SAFE | 4.39s | No |
| 19 | 6 | Why did they find out later that he had fungal pneumonia? | 0.273 | 0.650 | 0.90 | SAFE | 8.08s | No |
| 20 | 20 | How did they diagnose her with migraine for spinning sensati… | 0.692 | 0.800 | 1.00 | SAFE | 4.95s | No |
