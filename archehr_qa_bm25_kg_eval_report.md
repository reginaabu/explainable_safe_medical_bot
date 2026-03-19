# Track 3 Evaluation Report

**Dataset:** archehr_qa  |  **Mode:** bm25+kg  |  **Questions evaluated:** 20  |  **Seed:** 42  |  **Date:** 2026-03-19

## Summary

| Metric | Value |
|--------|-------|
| Faithfulness (mean) | 0.657 |
| Answer Relevancy (mean) | 0.738 |
| Factuality (mean) | 0.791 |
| Safety Rate | 90.0% |
| Mean Latency (s) | 5.310 |
| Corrections Applied | 1/20 |

## Per-Question Breakdown

| # | CASE_ID | Question | Faithfulness | Answer Rel. | Factuality | Safe | Latency | Corrected |
|---|------|----------|-------------|-------------|------------|------|---------|-----------|
| 1 | 4 | Why was cardiac catheterization recommended to the patient? | 1.000 | 0.300 | 0.80 | SAFE | 5.23s | No |
| 2 | 1 | Why was ERCP recommended to him over continuing a medication… | 0.000 | 1.000 | 1.00 | SAFE | 5.17s | No |
| 3 | 9 | What treatments did she receive for complications during her… | 1.000 | 0.750 | 0.47 | SAFE | 6.50s | Yes |
| 4 | 8 | Will the poison damage to his body last and is the confusion… | 0.875 | 0.600 | 0.86 | SAFE | 9.63s | No |
| 5 | 17 | What should he do to relieve palpitations and anxiety? | 0.571 | 0.600 | 0.83 | SAFE | 3.59s | No |
| 6 | 3 | What is the expected course of recovery for him? | 0.938 | 0.800 | 1.00 | SAFE | 3.65s | No |
| 7 | 12 | What can cause her persistent stomach pain? | 0.571 | 0.700 | 0.86 | SAFE | 4.19s | No |
| 8 | 2 | Why was he given lasix and his oxygen flow rate was reduced? | 0.846 | 0.800 | 0.80 | SAFE | 5.40s | No |
| 9 | 11 | What is the expected course of her recovery? | 1.000 | 0.600 | 0.61 | SAFE | 6.32s | No |
| 10 | 18 | Should he go back to the ER if he has diarrhea and vomiting? | 0.667 | 0.300 | 1.00 | SAFE | 5.54s | No |
| 11 | 13 | What should the patient do if she is in in pain and cannot m… | 0.667 | 0.800 | 0.60 | UNSAFE(EMERGENCY) | 4.46s | No |
| 12 | 7 | Are there specific instructions about blood thinners due to … | 0.571 | 0.850 | 0.75 | SAFE | 4.30s | No |
| 13 | 19 | Are her symptoms related to anxiety or cardiovascular proces… | 0.769 | 0.900 | 0.92 | SAFE | 5.68s | No |
| 14 | 16 | Could her back pain and dizziness be concerning for a stroke… | 0.800 | 0.600 | 0.60 | SAFE | 5.69s | No |
| 15 | 14 | Was there any evidence for stomach cancer? | 0.250 | 1.000 | 0.67 | SAFE | 3.15s | No |
| 16 | 10 | Did she sustain any brain damage from the heart attack? | 0.417 | 0.900 | 0.80 | SAFE | 4.57s | No |
| 17 | 5 | Is the pain connected to the overdose or something else? | 0.750 | 0.800 | 0.86 | UNSAFE(EMERGENCY) | 5.18s | No |
| 18 | 15 | Did his infection spread to other anatomies causing infertil… | 0.455 | 0.900 | 0.73 | SAFE | 6.47s | No |
| 19 | 6 | Why did they find out later that he had fungal pneumonia? | 0.667 | 0.750 | 0.80 | SAFE | 7.07s | No |
| 20 | 20 | How did they diagnose her with migraine for spinning sensati… | 0.333 | 0.800 | 0.86 | SAFE | 4.42s | No |
