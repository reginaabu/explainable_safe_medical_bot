# Track 3 Evaluation Report

**Dataset:** medquad  |  **Mode:** bm25+ce  |  **Questions evaluated:** 25  |  **Seed:** 42  |  **Date:** 2026-03-19

## Summary

| Metric | Value |
|--------|-------|
| Faithfulness (mean) | 0.900 |
| Answer Relevancy (mean) | 0.459 |
| Factuality (mean) | 0.800 |
| Safety Rate | 92.0% |
| Mean Latency (s) | 3.910 |
| Corrections Applied | 3/25 |

## Per-Question Breakdown

| # | QID | Question | Faithfulness | Answer Rel. | Factuality | Safe | Latency | Corrected |
|---|------|----------|-------------|-------------|------------|------|---------|-----------|
| 1 | 0000134-11 | What are the brand names of Benztropine Mesylate Oral ? | 1.000 | 0.000 | 1.00 | SAFE | 2.30s | No |
| 2 | 0005521-1 | What is (are) Scurvy ? | 1.000 | 0.950 | 1.00 | SAFE | 2.79s | No |
| 3 | 0000908-5 | What are the treatments for sialidosis ? | 0.875 | 0.750 | 1.00 | SAFE | 4.15s | No |
| 4 | 0002348-1 | What is (are) Laxative overdose ? | 1.000 | 0.500 | 0.90 | UNSAFE(EMERGENCY) | 3.73s | No |
| 5 | 0001531-7 | What is the outlook for Factor X deficiency ? | 0.333 | 0.000 | 0.83 | SAFE | 3.46s | No |
| 6 | 0000044-1 | Do you have information about Antibiotic Resistance | 1.000 | 0.900 | 0.42 | SAFE | 5.28s | Yes |
| 7 | 0002135-1 | What are the symptoms of Epilepsy juvenile absence ? | 1.000 | 0.850 | 1.00 | SAFE | 3.13s | No |
| 8 | 0006460-3 | What causes Wolff-Parkinson-White syndrome ? | 1.000 | 0.850 | 1.00 | SAFE | 2.83s | No |
| 9 | 0001262-2 | How should Ulipristal be used and what is the dosage ? | 1.000 | 0.000 | 1.00 | SAFE | 2.60s | No |
| 10 | 0000413-1 | Who should get Efavirenz and why is it prescribed ? | 1.000 | 0.000 | 1.00 | UNSAFE(PRESCRIPTION) | 4.60s | No |
| 11 | 0003327-2 | What are the symptoms of Juvenile osteoporosis ? | 1.000 | 0.850 | 1.00 | SAFE | 3.37s | No |
| 12 | 0000129-1 | What important warning or information should I know about Be… | 1.000 | 0.200 | 0.89 | SAFE | 5.70s | No |
| 13 | 0004034-8 | Do I need to see a doctor for Tricuspid atresia ? | 0.600 | 0.200 | 0.60 | SAFE | 3.39s | No |
| 14 | 0001030-3 | What are the genetic changes related to Weaver syndrome ? | 1.000 | 0.000 | 1.00 | SAFE | 3.07s | No |
| 15 | 0000528-3 | What are the genetic changes related to IRAK-4 deficiency ? | 1.000 | 0.650 | 0.70 | SAFE | 3.12s | No |
| 16 | 0000563-2 | What are the symptoms of Autosomal dominant neuronal ceroid … | 1.000 | 0.850 | 0.33 | SAFE | 5.77s | No |
| 17 | 0000266-1 | What is (are) Diabetes ? | 1.000 | 0.920 | 0.40 | SAFE | 4.26s | Yes |
| 18 | 0000062-9 | What are the symptoms of Shingles ? | 1.000 | 0.950 | 0.50 | SAFE | 6.82s | No |
| 19 | 0000214-7 | How to prevent Parasites - Lice - Head Lice ? | 0.857 | 0.300 | 0.71 | SAFE | 6.48s | No |
| 20 | 0000689-10 | What other information should I know about Levalbuterol Oral… | 0.700 | 0.000 | 0.67 | SAFE | 4.33s | No |
| 21 | 0000303-5 | What are the treatments for Down syndrome ? | 1.000 | 0.800 | 0.92 | SAFE | 3.09s | No |
| 22 | 0000774-8 | What should I know about storage and disposal of Methocarbam… | 1.000 | 0.000 | 1.00 | SAFE | 2.24s | No |
| 23 | 0000024_6-1 | What is (are) Oropharyngeal Cancer ? | 0.900 | 0.950 | 0.50 | SAFE | 5.38s | Yes |
| 24 | 0000353-11 | What are the brand names of Dextromethorphan and Quinidine ? | 0.778 | 0.000 | 1.00 | SAFE | 3.24s | No |
| 25 | 0000737-11 | What other information should I know about Maprotiline ? | 0.455 | 0.000 | 0.62 | SAFE | 2.59s | No |
