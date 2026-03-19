# Retrieval Mode Comparison Report

**Questions per run:** 25  |  **Seed:** 42  |  **Date:** 2026-03-19

## Modes Compared

| Mode | Description |
|------|-------------|
| `bm25` | Basic BM25 keyword retrieval only |
| `bm25+kg` | BM25 + Knowledge Graph query expansion (SciSpacy NER + co-occurrence) |
| `bm25+ce` | BM25 + Cross-encoder reranking (ms-marco-MiniLM-L-6-v2) |
| `bm25+kg+ce` | BM25 + KG expansion + Cross-encoder reranking (full pipeline) |

---

## Dataset: `pubmedqa`

| Metric | **Basic BM25**  |  **BM25 + KG**  |  **BM25 + CE**  |  **BM25 + KG + CE** |
|--------|------|------|------|------|
| Faithfulness | **0.897** | 0.862 | 0.873 | 0.822 |
| Answer Relevancy | 0.758 | **0.796** | 0.752 | 0.790 |
| Factuality | **0.682** | 0.641 | 0.675 | 0.644 |
| Safety Rate | **96.0%** | 96.0% | 96.0% | 96.0% |
| Mean Latency (s) | 8.405 | 8.504 | 8.858 | **8.923** |
| Corrections | 1/25 | 3/25 | 2/25 | 2/25 |

### Winner by Metric

- **Faithfulness**: `bm25` (0.897)
- **Answer Relevancy**: `bm25+kg` (0.796)
- **Factuality**: `bm25` (0.682)
- **Safety Rate**: `bm25` (96.0%)
- **Mean Latency (s)**: `bm25+kg+ce` (8.923)

### Delta vs Baseline BM25

| Metric | `bm25+kg` | `bm25+ce` | `bm25+kg+ce` |
|--------|------|------|------|
| Faithfulness | -0.035 | -0.024 | -0.075 |
| Answer Relevancy | +0.038 | -0.006 | +0.032 |
| Factuality | -0.041 | -0.007 | -0.038 |

---

## Dataset: `medquad`

| Metric | **Basic BM25**  |  **BM25 + KG**  |  **BM25 + CE**  |  **BM25 + KG + CE** |
|--------|------|------|------|------|
| Faithfulness | **0.927** | 0.870 | 0.900 | 0.916 |
| Answer Relevancy | 0.468 | 0.443 | 0.459 | **0.493** |
| Factuality | **0.904** | 0.859 | 0.800 | 0.852 |
| Safety Rate | **92.0%** | 92.0% | 92.0% | 92.0% |
| Mean Latency (s) | **9.143** | 8.582 | 3.910 | 4.441 |
| Corrections | 1/25 | 0/25 | 3/25 | 0/25 |

### Winner by Metric

- **Faithfulness**: `bm25` (0.927)
- **Answer Relevancy**: `bm25+kg+ce` (0.493)
- **Factuality**: `bm25` (0.904)
- **Safety Rate**: `bm25` (92.0%)
- **Mean Latency (s)**: `bm25` (9.143)

### Delta vs Baseline BM25

| Metric | `bm25+kg` | `bm25+ce` | `bm25+kg+ce` |
|--------|------|------|------|
| Faithfulness | -0.057 | -0.027 | -0.011 |
| Answer Relevancy | -0.025 | -0.009 | +0.025 |
| Factuality | -0.045 | -0.104 | -0.052 |

---

## Dataset: `archehr_qa`

| Metric | **Basic BM25**  |  **BM25 + KG**  |  **BM25 + CE**  |  **BM25 + KG + CE** |
|--------|------|------|------|------|
| Faithfulness | **0.700** | 0.657 | 0.653 | 0.691 |
| Answer Relevancy | 0.682 | 0.738 | 0.665 | **0.740** |
| Factuality | **0.862** | 0.791 | 0.787 | 0.759 |
| Safety Rate | 85.0% | 90.0% | **95.0%** | 95.0% |
| Mean Latency (s) | 4.666 | 5.310 | 5.338 | **5.564** |
| Corrections | 1/20 | 1/20 | 2/20 | 2/20 |

### Winner by Metric

- **Faithfulness**: `bm25` (0.700)
- **Answer Relevancy**: `bm25+kg+ce` (0.740)
- **Factuality**: `bm25` (0.862)
- **Safety Rate**: `bm25+ce` (95.0%)
- **Mean Latency (s)**: `bm25+kg+ce` (5.564)

### Delta vs Baseline BM25

| Metric | `bm25+kg` | `bm25+ce` | `bm25+kg+ce` |
|--------|------|------|------|
| Faithfulness | -0.043 | -0.047 | -0.009 |
| Answer Relevancy | +0.056 | -0.017 | +0.058 |
| Factuality | -0.071 | -0.075 | -0.103 |

---

## Overall Cross-Dataset Summary

Average across all datasets per mode:

| Mode | Avg Faithfulness | Avg Answer Relevancy | Avg Factuality | Avg Safety Rate |
|------|-----------------|---------------------|----------------|-----------------|
| `bm25` | 0.841 | 0.636 | 0.816 | 91.0% |
| `bm25+kg` | 0.796 | 0.659 | 0.764 | 92.7% |
| `bm25+ce` | 0.809 | 0.625 | 0.754 | 94.3% |
| `bm25+kg+ce` | 0.810 | 0.674 | 0.752 | 94.3% |

---
*Bold values indicate best score per metric per dataset.*
