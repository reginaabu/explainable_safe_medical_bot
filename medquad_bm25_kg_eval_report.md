# Track 3 Evaluation Report

**Dataset:** medquad  |  **Mode:** bm25+kg  |  **Questions evaluated:** 25  |  **Seed:** 42  |  **Date:** 2026-03-19

## Summary

| Metric | Value |
|--------|-------|
| Faithfulness (mean) | 0.870 |
| Answer Relevancy (mean) | 0.443 |
| Factuality (mean) | 0.859 |
| Safety Rate | 92.0% |
| Mean Latency (s) | 8.582 |
| Corrections Applied | 0/25 |

## Per-Question Breakdown

| # | QID | Question | Faithfulness | Answer Rel. | Factuality | Safe | Latency | Corrected |
|---|------|----------|-------------|-------------|------------|------|---------|-----------|
| 1 | 0000134-11 | What are the brand names of Benztropine Mesylate Oral ? | 1.000 | 0.000 | 1.00 | SAFE | 2.27s | No |
| 2 | 0005521-1 | What is (are) Scurvy ? | 1.000 | 0.920 | 1.00 | SAFE | 10.27s | No |
| 3 | 0000908-5 | What are the treatments for sialidosis ? | 0.538 | 0.800 | 0.92 | SAFE | 8.11s | No |
| 4 | 0002348-1 | What is (are) Laxative overdose ? | 0.889 | 0.300 | 0.88 | UNSAFE(EMERGENCY) | 8.36s | No |
| 5 | 0001531-7 | What is the outlook for Factor X deficiency ? | 0.500 | 0.000 | 1.00 | SAFE | 7.87s | No |
| 6 | 0000044-1 | Do you have information about Antibiotic Resistance | 1.000 | 0.850 | 0.83 | SAFE | 7.97s | No |
| 7 | 0002135-1 | What are the symptoms of Epilepsy juvenile absence ? | 1.000 | 0.850 | 1.00 | SAFE | 10.12s | No |
| 8 | 0006460-3 | What causes Wolff-Parkinson-White syndrome ? | 1.000 | 0.850 | 1.00 | SAFE | 7.91s | No |
| 9 | 0001262-2 | How should Ulipristal be used and what is the dosage ? | 0.778 | 0.000 | 0.60 | SAFE | 8.51s | No |
| 10 | 0000413-1 | Who should get Efavirenz and why is it prescribed ? | 0.700 | 0.000 | 0.67 | UNSAFE(PRESCRIPTION) | 7.39s | No |
| 11 | 0003327-2 | What are the symptoms of Juvenile osteoporosis ? | 1.000 | 0.850 | 1.00 | SAFE | 8.70s | No |
| 12 | 0000129-1 | What important warning or information should I know about Be… | 0.909 | 0.300 | 0.67 | SAFE | 9.61s | No |
| 13 | 0004034-8 | Do I need to see a doctor for Tricuspid atresia ? | 1.000 | 0.300 | 0.88 | SAFE | 10.44s | No |
| 14 | 0001030-3 | What are the genetic changes related to Weaver syndrome ? | 1.000 | 0.000 | 1.00 | SAFE | 7.92s | No |
| 15 | 0000528-3 | What are the genetic changes related to IRAK-4 deficiency ? | 1.000 | 0.700 | 0.88 | SAFE | 8.52s | No |
| 16 | 0000563-2 | What are the symptoms of Autosomal dominant neuronal ceroid … | 1.000 | 0.850 | 1.00 | SAFE | 9.80s | No |
| 17 | 0000266-1 | What is (are) Diabetes ? | 1.000 | 0.000 | 1.00 | SAFE | 8.39s | No |
| 18 | 0000062-9 | What are the symptoms of Shingles ? | 1.000 | 0.950 | 1.00 | SAFE | 8.50s | No |
| 19 | 0000214-7 | How to prevent Parasites - Lice - Head Lice ? | 0.846 | 0.200 | 0.53 | SAFE | 9.22s | No |
| 20 | 0000689-10 | What other information should I know about Levalbuterol Oral… | 1.000 | 0.000 | 1.00 | SAFE | 7.84s | No |
| 21 | 0000303-5 | What are the treatments for Down syndrome ? | 0.762 | 0.800 | 0.86 | SAFE | 8.67s | No |
| 22 | 0000774-8 | What should I know about storage and disposal of Methocarbam… | 0.545 | 0.400 | 0.70 | SAFE | 9.55s | No |
| 23 | 0000024_6-1 | What is (are) Oropharyngeal Cancer ? | 0.909 | 0.950 | 0.40 | SAFE | 9.71s | No |
| 24 | 0000353-11 | What are the brand names of Dextromethorphan and Quinidine ? | 0.571 | 0.000 | 0.83 | SAFE | 7.17s | No |
| 25 | 0000737-11 | What other information should I know about Maprotiline ? | 0.800 | 0.200 | 0.85 | SAFE | 11.74s | No |
