# Preprocessing Choices – Track 1 BM25 Baseline

This document explicitly records every preprocessing decision made in the pipeline.
These choices directly affect retrieval performance and must be reproduced exactly
to replicate the reported metrics.

---

## 1. Input Data

**Source:** PubMedQA `pqa_labeled` split loaded via Hugging Face `datasets`.

Each record contains:
- `pubid` — PubMed article ID (used as gold label)
- `question` — the medical question
- `context.contexts` — a list of strings (sentences/paragraphs from the abstract)

**Normalization:** The list of context strings is joined with a single space into one flat string:
```python
context_flat = " ".join(item["context"]["contexts"])
```
No other cleaning is applied at this stage (no HTML stripping, no special-character removal).

---

## 2. Lowercasing

**Applied: Yes**

Both the document corpus and queries are lowercased before tokenization:
```python
# Index time
tokenized_corpus = [doc["text"].lower().split() for doc in corpus]

# Query time
scores = bm25.get_scores(query.lower().split())
```

This ensures case-insensitive matching (e.g., "BM25" matches "bm25").

---

## 3. Stopword Removal

**Applied: No**

Stopwords (e.g., "the", "is", "of") are **not removed**. This is a deliberate choice:
- BM25's IDF weighting naturally down-weights high-frequency terms, making explicit stopword removal less critical.
- Removing stopwords can hurt recall on medical queries where prepositions carry meaning
  (e.g., "cancer of the liver" vs. "liver cancer").
- Keeping stopwords preserves phrase-level patterns that BM25 scores partially capture.

---

## 4. Tokenization

**Method: Whitespace split (`.split()`)**

```python
tokens = text.lower().split()
```

- No punctuation stripping (commas, periods, hyphens remain attached to tokens).
- No stemming or lemmatization (e.g., "treated" ≠ "treatment").
- No subword tokenization.

**Rationale:** Simple whitespace split is fast, reproducible, and consistent between
index time and query time. NLTK `word_tokenize` was tested in early cells but replaced
with `.split()` for consistency (see cell-10 in the notebook).

**Known limitation:** Tokens like "mortality," (with trailing comma) and "mortality"
are treated as different tokens, slightly reducing effective overlap.

---

## 5. Document Chunking

**Applied: Yes**

Long abstracts are split into overlapping fixed-size word chunks:

| Parameter | Value |
|-----------|-------|
| Chunk size | 400 words |
| Overlap | 50 words |
| Step size | 350 words (= chunk\_size − overlap) |

```python
def chunk_text(text, chunk_size=400, overlap=50):
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        chunks.append(" ".join(words[start:start + chunk_size]))
        start += chunk_size - overlap
    return chunks
```

**Why 400 words / 50 overlap?**
- PubMedQA abstracts average ~250–350 words; most fit in a single chunk.
- 400-word chunks ensure short abstracts are never split unnecessarily.
- 50-word overlap prevents relevant sentences at chunk boundaries from being missed.
- Result: 1,000 records → **1,026 chunks** (≈1 chunk per record on average, a few records produce 2).

**Chunk identity:** Each chunk inherits its parent record's `pubid`. Gold matching
checks whether any retrieved chunk shares the query's gold `pubid`.

---

## 6. Summary Table

| Step | Applied | Value / Method |
|------|---------|----------------|
| Input normalization | Yes | Join `context.contexts` list with space |
| Lowercasing | Yes | `.lower()` at index and query time |
| Stopword removal | No | — |
| Punctuation removal | No | — |
| Stemming / lemmatization | No | — |
| Tokenization | Yes | Whitespace split `.split()` |
| Chunking | Yes | 400 words, 50-word overlap |
| BM25 variant | — | BM25Okapi (rank-bm25 default) |
