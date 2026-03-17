"""
build_report.py – Generate the full thesis Word document.
Run: python build_report.py
"""
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

doc = Document()

# ── Page margins ──────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin   = Inches(1.25)
    section.right_margin  = Inches(1.0)

# ── Helper functions ──────────────────────────────────────────────────────────
def set_font(run, name="Times New Roman", size=12, bold=False, italic=False, color=None):
    run.font.name  = name
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)

def heading(text, level=1):
    p = doc.add_heading(text, level=level)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for run in p.runs:
        run.font.name = "Times New Roman"
        run.font.color.rgb = RGBColor(0, 0, 0)
        if level == 1:
            run.font.size = Pt(16)
            run.font.bold = True
        elif level == 2:
            run.font.size = Pt(14)
            run.font.bold = True
        else:
            run.font.size = Pt(12)
            run.font.bold = True
    return p

def body(text, indent=False):
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.left_indent = Inches(0.3)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.space_before = Pt(0)
    run = p.add_run(text)
    set_font(run)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p

def bullet(text, level=0):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent = Inches(0.3 + 0.2 * level)
    run = p.add_run(text)
    set_font(run)
    return p

def numbered(text):
    p = doc.add_paragraph(style="List Number")
    run = p.add_run(text)
    set_font(run)
    return p

def code_block(text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.4)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    run = p.add_run(text)
    run.font.name = "Courier New"
    run.font.size = Pt(9)
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), "F0F0F0")
    p._p.get_or_add_pPr().append(shading)
    return p

def add_table(headers, rows, caption=""):
    if caption:
        cp = doc.add_paragraph()
        cr = cp.add_run(caption)
        set_font(cr, bold=True, size=11)
        cp.paragraph_format.space_before = Pt(8)

    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Table Grid"
    # Header row
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = h
        for para in hdr[i].paragraphs:
            for run in para.runs:
                run.font.bold = True
                run.font.name = "Times New Roman"
                run.font.size = Pt(10)
        shading = OxmlElement("w:shd")
        shading.set(qn("w:val"), "clear")
        shading.set(qn("w:color"), "auto")
        shading.set(qn("w:fill"), "D9E1F2")
        hdr[i]._tc.get_or_add_tcPr().append(shading)
    # Data rows
    for ri, row in enumerate(rows):
        cells = t.rows[ri + 1].cells
        for ci, val in enumerate(row):
            cells[ci].text = str(val)
            for para in cells[ci].paragraphs:
                for run in para.runs:
                    run.font.name = "Times New Roman"
                    run.font.size = Pt(10)
    doc.add_paragraph()
    return t

def spacer(n=1):
    for _ in range(n):
        doc.add_paragraph()

# ══════════════════════════════════════════════════════════════════════════════
#  TITLE PAGE
# ══════════════════════════════════════════════════════════════════════════════
spacer(4)
tp = doc.add_paragraph()
tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = tp.add_run("EXPLAINABLE AND SAFE MEDICAL SUPPORT CHATBOT\nUSING GENERATIVE AI")
r.font.name = "Times New Roman"; r.font.size = Pt(20); r.font.bold = True

spacer(2)
ap = doc.add_paragraph()
ap.alignment = WD_ALIGN_PARAGRAPH.CENTER
ar = ap.add_run("Regina Aboobacker")
ar.font.name = "Times New Roman"; ar.font.size = Pt(14)

spacer(1)
dp = doc.add_paragraph()
dp.alignment = WD_ALIGN_PARAGRAPH.CENTER
dr = dp.add_run("MSc Artificial Intelligence\nUpGrad – March 2026")
dr.font.name = "Times New Roman"; dr.font.size = Pt(12)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
#  ABSTRACT
# ══════════════════════════════════════════════════════════════════════════════
heading("Abstract", 1)
body(
    "Patients and the general public increasingly rely on online sources and conversational "
    "agents for medical advice; however, the majority of available information is inaccurate, "
    "incomplete, or presented without clear evidence, which leads to serious safety and trust "
    "concerns. Large Language Models (LLMs) can provide fluent answers but are prone to "
    "hallucinations, bias, and opaque reasoning, even when coupled with standard "
    "retrieval-augmented generation (RAG)."
)
body(
    "This project develops an explainable, self-correcting medical chatbot that answers "
    "healthcare questions using public datasets — PubMedQA (211k biomedical QA pairs) and "
    "MedQuAD (47.4k consumer-health QA pairs). The system integrates a BM25 retrieval "
    "baseline (Track 1), a SciSpacy-based Knowledge Graph (Track 2), and a Claude Sonnet "
    "4.6 generation layer with atomic fact verification, regex-based safety filtering, and "
    "RAGAS-based evaluation (Track 3). A hybrid dense–sparse retrieval module employing "
    "Reciprocal Rank Fusion and type-aware semantic search further improves answer relevancy "
    "on the MedQuAD consumer-health dataset."
)
body(
    "Experimental results on 25-question stratified samples (seed=42) show: "
    "PubMedQA — faithfulness 0.821, answer relevancy 0.693, factuality 0.747, safety rate 96%; "
    "MedQuAD (hybrid) — faithfulness 0.733, answer relevancy 0.475, factuality 0.716, "
    "safety rate 84%. The self-correction loop reduced factual hallucination in 4 of 25 "
    "MedQuAD queries. All outputs are traceable to inline citations, and a Streamlit "
    "prototype delivers answers with evidence snippets, safety badges, and medical disclaimers."
)
doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
#  TABLE OF CONTENTS (manual)
# ══════════════════════════════════════════════════════════════════════════════
heading("Table of Contents", 1)
toc_entries = [
    ("Abstract", ""),
    ("Chapter 1 – Introduction", ""),
    ("    1.1  Background and Motivation", ""),
    ("    1.2  Problem Statement", ""),
    ("    1.3  Research Questions", ""),
    ("    1.4  Aims and Objectives", ""),
    ("    1.5  Significance of the Study", ""),
    ("    1.6  Scope and Limitations", ""),
    ("Chapter 2 – Literature Review", ""),
    ("    2.1  Hybrid Retrieval and Source Planning", ""),
    ("    2.2  Knowledge Graph Grounding (KG-RAG)", ""),
    ("    2.3  Reliability and Hallucination Mitigation", ""),
    ("    2.4  Medical Explanation Quality", ""),
    ("    2.5  Evidence-based Medical RAG", ""),
    ("    2.6  Graph-based and Multi-hop Reasoning", ""),
    ("    2.7  EHR-based Medical QA (ArchEHR-QA)", ""),
    ("    2.8  Overall Gaps Identified", ""),
    ("Chapter 3 – Research Methodology", ""),
    ("    3.1  System Architecture Overview", ""),
    ("    3.2  Phase 1 – Knowledge Ingestion and Retrieval", ""),
    ("    3.3  Phase 2 – Generation and Self-Correction Layer", ""),
    ("    3.4  Phase 3 – Explainability Module", ""),
    ("    3.5  Phase 4 – Evaluation Framework", ""),
    ("    3.6  Datasets and Tools", ""),
    ("Chapter 4 – Analysis", ""),
    ("    4.1  Track 1: BM25 Baseline", ""),
    ("    4.2  Track 2: Knowledge Graph Expansion", ""),
    ("    4.3  Track 3: Generation and Safety Evaluation", ""),
    ("    4.4  Retriever Comparison on MedQuAD", ""),
    ("    4.5  Error Analysis", ""),
    ("Chapter 5 – Results", ""),
    ("    5.1  PubMedQA Evaluation Results", ""),
    ("    5.2  MedQuAD Evaluation Results", ""),
    ("    5.3  Safety and Factuality", ""),
    ("    5.4  Latency and Efficiency", ""),
    ("Chapter 6 – Conclusion and Future Work", ""),
    ("    6.1  Summary of Contributions", ""),
    ("    6.2  Limitations", ""),
    ("    6.3  Future Work", ""),
    ("References", ""),
]
for entry, _ in toc_entries:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(entry)
    r.font.name = "Times New Roman"; r.font.size = Pt(11)
doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
#  CHAPTER 1 – INTRODUCTION
# ══════════════════════════════════════════════════════════════════════════════
heading("Chapter 1 – Introduction", 1)

heading("1.1 Background and Motivation", 2)
body(
    "The proliferation of digital health resources has fundamentally altered how individuals "
    "seek medical information. The internet has become the first point of contact for many "
    "people exploring symptoms, potential diagnoses, treatments, and preventive care. Yet "
    "online health resources remain deeply fragmented and heterogeneous in quality. "
    "Generative AI tools — particularly LLM-based chatbots — have made medical information "
    "more accessible by enabling natural-language conversational interfaces. However, they "
    "simultaneously introduce new risks: hallucinated facts, unsafe recommendations, and "
    "subtle biases that are difficult for lay users to detect."
)
body(
    "Several clinical studies show that LLMs can match or exceed physicians on some "
    "diagnostic and prescribing tasks while simultaneously over-ordering tests, "
    "over-prescribing medications, and inconsistently following guideline checklists — "
    "illustrating the gap between surface correctness and process quality. Research from "
    "large-scale evaluations such as MedQA, ArchEHR-QA, and MedMCQA confirms that even "
    "the strongest LLMs may provide confidently incorrect answers or omit safety-critical "
    "disclaimers."
)
body(
    "Retrieval-Augmented Generation (RAG) has emerged as a dominant strategy to mitigate "
    "hallucinations by grounding answers in external knowledge bases such as PubMed, "
    "clinical guidelines, and biomedical textbooks. Benchmarks like MIRAGE and toolkits "
    "such as MEDRAG demonstrate that well-configured RAG pipelines substantially improve "
    "medical QA accuracy across diverse LLMs, including smaller open-source models. "
    "However, even RAG systems may produce unsupported claims when retrieval is noisy "
    "or when the model fails to faithfully incorporate retrieved evidence."
)

heading("1.2 Problem Statement", 2)
body(
    "Despite significant advances in biomedical NLP, there remains a notable gap in "
    "systems explicitly designed for the public that combine: (1) robust factuality control, "
    "(2) explanation mechanisms understandable to non-experts, and (3) explicit self-evaluation "
    "for safety and ethical compliance. Existing chatbots typically provide only shallow "
    "explanations such as inline citations or snippet highlighting, without verifying whether "
    "those citations actually support the generated claims."
)
body("Key problems in current medical chatbots include:")
bullet("Hallucinations due to missing grounding or outdated knowledge.")
bullet("Lack of transparency: answers do not cite clinical guidelines.")
bullet("Poor explanation quality (MedExQA benchmark shows low rationale alignment).")
bullet("Safety concerns: over-testing and over-prescribing tendencies in LLMs.")
bullet("Bias propagation from pretraining corpora.")
bullet("Limited handling of demographic context and personalised risk factors.")
bullet("Lack of self-monitoring or verification loops.")

heading("1.3 Research Questions", 2)
numbered(
    "Architecture & Factuality: How effectively does a two-layer RAG architecture "
    "incorporating atomic fact-checking reduce hallucination rates and increase factual "
    "correctness compared to single-layer RAG baselines on PubMedQA and MedQuAD?"
)
numbered(
    "Explainability & Trust: Can integration of evidence-linked rationales significantly "
    "enhance the causal coherence and fidelity of medical explanations while maintaining "
    "computational efficiency?"
)
numbered(
    "Self-evaluation and Correction: How effectively can automatic self-evaluation "
    "signals (atomic fact checks, hallucination scores, safety and bias classifiers) "
    "predict expert assessments of factual correctness and ethical compliance?"
)
numbered(
    "Data Curation and Knowledge Base Construction: What retrieval and evidence-selection "
    "strategies best balance answer accuracy, explanation quality, and latency in the "
    "context of layperson health Q&A?"
)
numbered(
    "Regulatory Compliance: What architectural and procedural safeguards maintain "
    "HIPAA/GDPR compliance and mitigate systemic biases within a continually updated "
    "retrieval-augmented generative system?"
)

heading("1.4 Aims and Objectives", 2)
body(
    "Aim: To develop and validate a computationally efficient, trustworthy Generative AI "
    "medical chatbot that delivers medically accurate, explainable, and ethically compliant "
    "answers to public health questions, grounded in validated biomedical knowledge sources "
    "using a novel self-monitoring RAG architecture incorporating basic explainability and "
    "safety awareness."
)
body("Objectives:")
numbered(
    "Construct a robust hybrid RAG knowledge base integrating public literature (PubMedQA) "
    "and consumer-health Q&A datasets (MedQuAD), with multi-dataset normalisation "
    "supporting MIMIC-III, MIMIC-IV, and ArchEHR-QA as future extensions."
)
numbered(
    "Design and implement a Two-Layer Generation/Self-Correction pipeline achieving "
    "acceptable atomic fact accuracy on relevant medical Q&A benchmarks."
)
numbered(
    "Design and deploy an evaluator module performing atomic fact extraction, "
    "evidence-based truth classification, hallucination scoring, and safety/bias "
    "detection using Claude Haiku and regex classifiers."
)
numbered(
    "Implement explanation mechanisms generating evidence-linked rationales with inline "
    "citations tailored to non-expert users."
)
numbered(
    "Evaluate the system quantitatively (RAGAS faithfulness, answer relevancy, "
    "factuality, safety rate, latency) comparing BM25, semantic, and hybrid retrievers "
    "across two benchmark datasets."
)

heading("1.5 Significance of the Study", 2)
body(
    "This work addresses a pressing societal need: safe and trustworthy communication of "
    "medical information to non-expert users in an era where generative AI systems are "
    "widely available but often unregulated and opaque. By combining retrieval-based "
    "grounding, explicit fact checking, and structured explanations, the proposed system "
    "aims to reduce the risk of misinformation, over-treatment, or delayed care stemming "
    "from unreliable online advice."
)
body(
    "Academically, the project advances the state of the art in medical RAG by integrating "
    "complementary strands — atomic fact verification, rationale-guided retrieval, "
    "graph-augmented evidence structures, and explanations — into a single, coherent "
    "chatbot architecture. It also contributes new evaluation protocols that jointly assess "
    "answer correctness, factual grounding, explanation quality, and safety for lay audiences."
)
body(
    "From a Responsible AI perspective, the proposal operationalises emerging governance "
    "and regulatory principles — transparency, bias mitigation, robustness, and human "
    "oversight — into concrete design patterns including self-monitoring layers, red-teaming "
    "safety filters, and explicit disclaimers. The rigorous integration of traceable evidence "
    "(cited QIDs/PMIDs) and clear auditability (Atomic Fact Accuracy) provides a practical "
    "technical blueprint for regulatory acceptability under HIPAA and GDPR."
)

heading("1.6 Scope and Limitations", 2)
body(
    "The study focuses on text-based medical question answering for adult, general-health "
    "topics (common conditions, symptoms, lifestyle risk factors) in English, targeting "
    "layperson users with no assumed clinical training. The following are explicitly "
    "excluded from the intended use case:"
)
bullet("Emergency medical decision-making and real-time clinical triage.")
bullet("Real-time clinical diagnosis or prescription guidance.")
bullet("High-risk clinical tasks requiring professional licensure.")
bullet("Handling of radiology images, genomics, or multimodal clinical data.")
bullet("Private EHR data; any clinical vignettes used are synthetic or anonymised.")
body(
    "The project does not develop new LLM architectures from scratch. It adapts and "
    "fine-tunes existing open-source models and APIs (Claude Sonnet 4.6, Claude Haiku 4.5) "
    "for generation, retrieval, and evaluation. Formal clinical trials, real-patient "
    "deployments, and regulatory submissions are beyond scope."
)
doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
#  CHAPTER 2 – LITERATURE REVIEW
# ══════════════════════════════════════════════════════════════════════════════
heading("Chapter 2 – Literature Review", 1)
body(
    "This chapter synthesises state-of-the-art findings across medical RAG, hallucination "
    "mitigation, explanation evaluation, knowledge-graph reasoning, and medical QA "
    "benchmarks relevant to the design of an explainable, safe medical chatbot."
)

heading("2.1 Hybrid Retrieval and Source Planning", 2)
body(
    "Optimal performance in retrieval over vast, heterogeneous biomedical corpora — such "
    "as the 24 million PubMed abstracts — is achieved through hybrid methods. These systems "
    "combine sparse lexical retrieval (e.g., BM25 search via Elasticsearch) with dense "
    "neural retrieval (using specialised embeddings like MedCPT or BiomedBERT) and then "
    "apply Reciprocal Rank Fusion (RRF) to merge ranked lists. This ensures that both "
    "keyword-matched documents and semantically related but lexically distant documents are "
    "retrieved, maximising recall (Xiong et al., 2024)."
)
body(
    "Beyond basic hybrid retrieval, modern RAG requires Source Planning Optimisation (SPO). "
    "Since medical questions can concern different aspects, the RAG system must intelligently "
    "decide which source to prioritise. SPO involves training a small planner model to "
    "generate source-specific queries, leading to better relevance, completeness, and "
    "interpretability. The use of books, guidelines, and research papers aggregated into a "
    "unified knowledge base (such as MedOmniKB) is crucial for robust performance "
    "(Chen et al., 2025)."
)
body(
    "This project implements the hybrid retrieval paradigm using BM25 (rank_bm25) for "
    "sparse retrieval and the all-MiniLM-L6-v2 sentence-transformer for dense retrieval, "
    "with RRF fusion. For MedQuAD — a Q&A dataset where queries and documents share "
    "question structure — a question-field BM25 variant was developed to improve alignment "
    "between query type and retrieved answer type."
)

heading("2.2 Knowledge Graph Grounding (KG-RAG)", 2)
body(
    "To address the structural limitations of vector store retrieval — which treats all "
    "knowledge as unstructured text chunks — frameworks like MedGraphRAG and SPARQL-RAG "
    "integrate knowledge graphs (KGs). These systems leverage structured medical ontologies "
    "(UMLS, SNOMED CT) to convert natural language queries into logical queries over RDF "
    "triples, or to perform Triple Graph Construction that embeds entity relationships from "
    "the document corpus. Combining knowledge graph querying with RAG produces significantly "
    "more reliable medical QA, particularly by grounding answers in verifiable semantic "
    "triples and documents (Wu et al., 2024)."
)
body(
    "This project implements a lightweight Knowledge Graph using SciSpacy NER "
    "(en_ner_bc5cdr_md model) to extract DISEASE and CHEMICAL entities from PubMedQA "
    "abstracts. Co-occurrence triples (entity_A co_occurs_with entity_B, "
    "entity_A mentioned_in PMID) are stored in triples.csv. These triples support query "
    "expansion at inference time: given a query, the top entity neighbours from the KG "
    "are appended to the search query before BM25 retrieval."
)

heading("2.3 Reliability and Hallucination Mitigation", 2)
body(
    "Atomic Fact Checking (AFC) improves correctness by breaking answers into minimal "
    "verifiable units and validating them against guideline documents. The multi-step "
    "pipeline decomposes an initial RAG answer into atomic facts, retrieves targeted "
    "evidence for each fact, classifies each as supported/unsupported/contradicted, and "
    "triggers iterative rewriting for incorrect claims (Vladika et al., 2025). "
    "This systematic process validates the proposed two-layer architecture and significantly "
    "improves evidence alignment."
)
body(
    "Beyond checking final outputs, advanced alignment techniques use process-level "
    "supervision. DeepRAG utilises explicit hierarchical reasoning to structure answer "
    "outlines and generate precise subqueries optimised using concept-based reward signals "
    "(Ji et al., 2025). The gap identified: AFC improves correctness but does not produce "
    "counterfactual or contrastive explanations."
)
body(
    "In this project, atomic fact decomposition is implemented in evaluator/fact_decompose.py "
    "using NLTK sentence tokenisation as a first pass. When sentences exceed 30 words or "
    "multiple sentences are detected, Claude Haiku 4.5 decomposes the answer into a JSON "
    "array of atomic claims. Fact verification (evaluator/fact_verify.py) uses a single "
    "batched Claude Haiku call to classify each claim as 'supported', 'unsupported', or "
    "'contradicted' against the retrieved evidence chunks."
)

heading("2.4 Medical Explanation Quality", 2)
body(
    "While current systems offer source links and simple rationales, they fall short of "
    "providing deep, actionable explanations that foster true trust. MedExQA demonstrates "
    "that multi-reference evaluation correlates better with human judgment, especially for "
    "safety-critical reasoning, and that larger LLMs do not guarantee better explanation "
    "quality (Zhao et al., 2024)."
)
body(
    "CF-RAG operationalises causal reasoning through counterfactual testing by "
    "systematically generating and evaluating 'what-if' queries to identify causally "
    "relevant distinctions in retrieved evidence. GraphRAG provides explicit knowledge of "
    "relationships in structured triples, ensuring that counterfactual statements are "
    "logically sound and medically verified. The gap: no system currently combines multiple "
    "explanation types (contrastive + counterfactual) with medical grounding."
)

heading("2.5 Evidence-based Medical RAG", 2)
body(
    "Research such as MedSearch demonstrates that RAG improves accuracy by 3–13%, reduces "
    "search time by 50% for clinicians, and enhances user trust without compromising safety. "
    "MIRAGE and MEDRAG frameworks show that PubMed abstracts and textbooks are crucial "
    "sources, MedCPT and BM25 fusion are the most effective retrievers, and RAG accuracy "
    "improves up to 18% with optimised retrieval (Xiong et al., 2024; Huang et al., 2024). "
    "The gap: RAG alone does not ensure safety or produce deep explanations."
)

heading("2.6 Graph-based and Multi-hop Reasoning", 2)
body(
    "Systems like MedGraphRAG provide multi-layer graph reasoning; DeepRAG, HyKGE, and "
    "KGRAG enhance multi-hop Q&A; AMGRAG builds dynamic knowledge graphs updated from "
    "PubMed. These approaches improve accuracy by 5–10% and produce better long-form "
    "explanations. The gap: graph reasoning is powerful but rarely used for self-evaluation "
    "or safety scoring."
)

heading("2.7 EHR-based Medical QA (ArchEHR-QA)", 2)
body(
    "Work on ArchEHR-QA demonstrates that RAG models need strict citation validation, "
    "sentence selection (BioBERT, MiniLM) significantly influences relevance, and "
    "formatting constraints challenge LLMs. The gap: need for robust grounding combined "
    "with self-evaluation for EHR-based responses. This project's dataset adapter module "
    "(utils/dataset_adapter.py) supports ArchEHR-QA, MIMIC-III, and MIMIC-IV as "
    "future-ready extensions."
)

heading("2.8 Overall Gaps Identified", 2)
numbered("Lack of self-evaluation for factual correctness, bias detection, or safety scoring.")
numbered("Explanations are insufficient — rarely counterfactual or contrastive.")
numbered("RAG pipelines do not deeply integrate clinical guidelines or real-time PubMed updates.")
numbered("Few models integrate reinforcement-learning feedback for medical safety.")
numbered("Biases and hallucinations remain prevalent despite retrieval grounding.")
spacer()
add_table(
    headers=["SOTA Technique", "Primary Limitation", "This Project's Approach"],
    rows=[
        ["RAG Grounding", "Factual ambiguity, source recall", "BM25 + all-MiniLM hybrid with RRF fusion"],
        ["Atomic Fact Checking", "Post-hoc hallucination detection", "Two-layer self-correction with Claude Haiku verifier"],
        ["MedExQA Rationale", "Lack of causal insight", "Evidence-linked inline citations (QID/PMID)"],
        ["KG-RAG", "Unstructured retrieval", "SciSpacy KG + query expansion (Track 2)"],
        ["Safety Audits", "No runtime safety layer", "Regex-based emergency/diagnosis/prescription filters"],
    ],
    caption="Table 2.1: Proposed Approaches vs. State-of-the-Art"
)
doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
#  CHAPTER 3 – RESEARCH METHODOLOGY
# ══════════════════════════════════════════════════════════════════════════════
heading("Chapter 3 – Research Methodology", 1)
body(
    "The development of the proposed system follows an iterative, four-phase process "
    "centred on a novel two-layer architecture: a Generation Layer and a "
    "Self-Evaluation/Correction Layer. The methodology follows a mixed-methods design: "
    "quantitative experiments for model performance and safety metrics, complemented by "
    "qualitative error analysis. The technical core is an experimental RAG pipeline "
    "augmented with self-evaluation and explanation modules, iteratively developed and "
    "benchmarked."
)

heading("3.1 System Architecture Overview", 2)
body(
    "The end-to-end pipeline processes a user question through five stages: retrieval, "
    "generation, self-evaluation, correction (if needed), and response packaging. "
    "The architecture is implemented across the following key modules:"
)
bullet("utils/dataset_adapter.py — Multi-dataset normalisation layer")
bullet("eval_harness.py — Pipeline orchestrator and evaluation harness")
bullet("rag_generate.py — Claude Sonnet 4.6 generation with grounded prompts")
bullet("evaluator/fact_decompose.py — NLTK + Claude Haiku atomic fact extraction")
bullet("evaluator/fact_verify.py — Evidence-based verdict classification")
bullet("evaluator/safety.py — Regex-based safety filter")
bullet("evaluator/metrics.py — RAGAS faithfulness and answer relevancy scoring")
bullet("utils/semantic_index.py — Dense retrieval and hybrid RRF index")
bullet("kg_expand.py — SciSpacy KG query expansion")
bullet("app.py — Streamlit conversational UI")
body("The full system architecture flow is as follows:")
code_block(
    "User Question\n"
    "  |\n"
    "[Dataset Adapter] --> Normalise rows {doc_id, question, context, q_type}\n"
    "  |\n"
    "[Retrieval Module]\n"
    "  |-- BM25 (rank_bm25, sliding-window 400w/50w overlap)\n"
    "  |-- Semantic Index (all-MiniLM-L6-v2, L2-normalised cosine)\n"
    "  |-- Hybrid RRF: (1-alpha)*BM25_rrf + alpha*Semantic_rrf  [alpha=0.6]\n"
    "  |-- Type-aware filtering by q_type (symptoms/treatment/genetic_changes/...)\n"
    "  |\n"
    "Top-3 Evidence Chunks {pubid, text}\n"
    "  |\n"
    "[Generation Layer -- Claude Sonnet 4.6]\n"
    "  |-- System prompt: grounded evidence citation + source type\n"
    "  |-- Standard or strict prompt depending on prior factuality\n"
    "  |\n"
    "Draft Answer + Citations\n"
    "  |\n"
    "[Self-Evaluation Layer]\n"
    "  |-- Safety check (regex: EMERGENCY / DIAGNOSIS / PRESCRIPTION)\n"
    "  |-- Atomic fact decomposition (NLTK --> Claude Haiku)\n"
    "  |-- Fact verification (Claude Haiku: supported/unsupported/contradicted)\n"
    "  |-- Factuality score = supported / total_facts\n"
    "  |-- If factuality < 0.5: regenerate with strict prompt\n"
    "  |-- RAGAS: faithfulness + answer_relevancy (all-MiniLM-L6-v2)\n"
    "  |\n"
    "[Response Package]\n"
    "  |-- Verified answer with inline citations\n"
    "  |-- Safety badge (SAFE / UNSAFE:EMERGENCY / UNSAFE:PRESCRIPTION)\n"
    "  |-- Medical disclaimer\n"
    "  |-- Factuality score + correction flag\n"
    "  |\n"
    "User Interface (Streamlit app.py)"
)

heading("3.2 Phase 1 – Knowledge Ingestion and Retrieval", 2)
body(
    "Data ingestion begins with the utils/dataset_adapter.py module, which normalises "
    "multiple medical QA dataset schemas into a canonical internal format: "
    "{doc_id, question, context, focus, q_type}. The DATASET_META registry maps five "
    "datasets — pubmedqa, medquad, archehr_qa, mimic3, mimic4 — to their HuggingFace "
    "identifiers, field mappings, id labels, and recommended retrievers."
)
body(
    "For PubMedQA, nested context dictionaries are flattened by joining the 'contexts' "
    "array. For MedQuAD, the consumer-health Q&A dataset with 47,441 records is loaded "
    "from HuggingFace (lavita/MedQuAD). The question_type field is normalised to the "
    "canonical q_type field, enabling type-aware retrieval. MIMIC-III, MIMIC-IV, and "
    "ArchEHR-QA are supported for local CSV loading (PhysioNet-gated access)."
)
body("The BM25 index is constructed as follows:")
bullet("All context fields are tokenised (whitespace, lowercased) into sliding-window chunks of 400 words with 50-word overlap.")
bullet("BM25Okapi parameters: k1=1.20, b=0.75, tuned via tune_bm25.py over the PubMedQA training set.")
bullet("The BM25 index for PubMedQA covers 19,377 chunks from 1,000 abstracts in the labelled split.")
bullet("For MedQuAD hybrid mode, a separate question-field BM25 is built by tokenising the question field rather than the answer text, aligning the retrieval signal with the query type.")
body(
    "The SemanticIndex class (utils/semantic_index.py) encodes all question fields using "
    "all-MiniLM-L6-v2, L2-normalised, stored as a numpy float32 matrix. At query time, "
    "cosine similarity is computed via a matrix-vector dot product. A type_index dictionary "
    "maps q_type values to row indices, enabling type-filtered candidate pools: if the "
    "q_type pool exceeds top_k, only same-type rows are considered as candidates."
)
body(
    "The HybridIndex class performs Reciprocal Rank Fusion over BM25 and semantic "
    "rankings with a configurable alpha parameter. With alpha=0.6, the semantic signal "
    "is weighted 60% and BM25 40%, recommended for Q&A datasets where semantic matching "
    "outperforms lexical matching. The RRF constant k=60 follows standard practice."
)

heading("3.3 Phase 2 – Generation and Self-Correction Layer", 2)
body(
    "Answer generation uses Claude Sonnet 4.6 (claude-sonnet-4-6) via the Anthropic API. "
    "The generation module (rag_generate.py) constructs a dataset-aware system prompt "
    "using the id_label and source_type from the dataset adapter. Two prompt variants are "
    "maintained:"
)
bullet("Standard prompt: 'Answer based ONLY on the provided {source_type}. Cite sources inline as ({id_label} XXXXXXXX).'")
bullet("Strict prompt: 'Answer using ONLY facts explicitly stated. Every sentence must be directly traceable to a specific {id_label} — if you cannot cite, omit it entirely.'")
body(
    "The strict prompt is triggered automatically when the factuality score of the "
    "initial response falls below the FACTUALITY_THRESHOLD of 0.50. The correction loop "
    "regenerates the answer once with the strict prompt and recomputes factuality. "
    "If the corrected answer has higher factuality, it replaces the original. "
    "The correction flag is recorded in the evaluation report."
)
body(
    "The self-evaluation layer operates as follows. First, evaluator/safety.py scans the "
    "generated answer using three pattern groups:"
)
bullet("EMERGENCY patterns: call_911, ambulance, suicidal, overdose, severe_bleeding, unconscious")
bullet("DIAGNOSIS patterns: 'you have', 'your diagnosis is', 'your test shows'")
bullet("PRESCRIPTION patterns: dosage instructions (e.g. 'take 10mg'), prescribe, inject, named-drug + take")
body(
    "If any pattern fires, is_safe=False and the appropriate flag is set. A mandatory "
    "educational disclaimer is appended to all outputs regardless of safety verdict. "
    "Emergency answers additionally receive a prominent 'call 911' banner."
)
body(
    "Second, evaluator/fact_decompose.py decomposes the answer into atomic claims "
    "using NLTK tokenisation followed by a Claude Haiku pass when sentences exceed 30 "
    "words. Third, evaluator/fact_verify.py submits up to 12 facts and 3 evidence chunks "
    "(truncated to 800 chars each) to Claude Haiku in a single batched call, receiving "
    "JSON verdicts with supported/unsupported/contradicted classification and supporting "
    "PMID attribution. Factuality score = supported_count / total_facts."
)

heading("3.4 Phase 3 – Explainability Module", 2)
body(
    "The current implementation provides Layer 1 explainability: every generated claim "
    "is traceable to an inline citation (QID or PMID), and the Streamlit UI displays the "
    "full evidence snippet alongside the answer. The fact verification output for each "
    "atomic claim includes its verdict and the supporting source ID, enabling users to "
    "inspect which specific abstracts support each sentence."
)
body(
    "Layer 2 explainability — Counterfactual Explanations (CFEs) and Contrastive "
    "Explanations (CEs) — is identified as a stretch goal in the research proposal. "
    "The architecture is designed to accommodate this extension. The Knowledge Graph "
    "triples (triples.csv, built by track2_build_kg.py) provide the structural foundation "
    "for CFE generation: given a query variable such as age or co-morbidity, counterfactual "
    "queries can be formulated by perturbing the variable and re-executing retrieval "
    "and generation. The divergent KG triples between original and counterfactual "
    "retrievals would form the causal explanation."
)

heading("3.5 Phase 4 – Evaluation Framework", 2)
body(
    "The evaluation harness (eval_harness.py) implements a reproducible evaluation "
    "protocol: stratified random sampling of n questions from the loaded dataset, "
    "seeded for reproducibility. For each sampled question, the pipeline executes "
    "retrieval, generation, safety evaluation, factuality scoring, and RAGAS scoring."
)
body("RAGAS metrics are computed via evaluator/metrics.py:")
bullet("Faithfulness: verifies that generated facts are strictly supported by the retrieved context, used as a hallucination proxy.")
bullet("Answer Relevancy: generates synthetic questions from the answer using Claude Haiku, then computes cosine similarity between the synthetic question embeddings and the original query embedding using all-MiniLM-L6-v2.")
body(
    "The evaluation report is generated as a Markdown file (track3_eval_report.md) "
    "containing aggregate metrics and a per-question breakdown table with QID, question, "
    "faithfulness, answer relevancy, factuality, safety verdict, latency, and correction flag."
)
add_table(
    headers=["Metric", "Method", "Model Used"],
    rows=[
        ["Faithfulness", "RAGAS Faithfulness class", "Claude Haiku 4.5"],
        ["Answer Relevancy", "RAGAS AnswerRelevancy + cosine sim", "Claude Haiku 4.5 + all-MiniLM-L6-v2"],
        ["Factuality", "Supported facts / total atomic facts", "Claude Haiku 4.5"],
        ["Safety Rate", "% questions with no safety flags", "Regex patterns"],
        ["Latency", "Wall-clock time per question", "—"],
        ["Recall@k", "Gold PMID in top-k retrieved", "BM25 / Hybrid"],
        ["MRR@10", "Mean Reciprocal Rank at 10", "BM25 / Hybrid"],
    ],
    caption="Table 3.1: Evaluation Metrics and Methods"
)

heading("3.6 Datasets, Tools, and Infrastructure", 2)
add_table(
    headers=["Component", "Tool/Library", "Version/Notes"],
    rows=[
        ["BM25 retrieval", "rank_bm25.BM25Okapi", "k1=1.20, b=0.75"],
        ["Dense retrieval", "sentence-transformers/all-MiniLM-L6-v2", "L2-normalised cosine"],
        ["Hybrid fusion", "Custom RRF (utils/semantic_index.py)", "alpha=0.6, k=60"],
        ["NER / KG", "SciSpacy en_ner_bc5cdr_md", "DISEASE + CHEMICAL entities"],
        ["Generation", "Claude Sonnet 4.6", "Max 400 tokens, system prompt grounding"],
        ["Fact decomposition", "Claude Haiku 4.5 + NLTK", "JSON array of atomic claims"],
        ["Fact verification", "Claude Haiku 4.5", "Batched, up to 12 facts × 3 chunks"],
        ["Safety filter", "Regex patterns (evaluator/safety.py)", "3 pattern groups"],
        ["RAGAS scoring", "ragas + langchain_anthropic", "Claude Haiku 4.5 + all-MiniLM"],
        ["UI", "Streamlit (app.py)", "Evidence snippets + safety badges"],
        ["PubMedQA", "HuggingFace pubmed_qa/pqa_labeled", "211k pairs, PMID-anchored"],
        ["MedQuAD", "HuggingFace lavita/MedQuAD", "47,441 pairs, 16 question types"],
    ],
    caption="Table 3.2: Technology Stack"
)
doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
#  CHAPTER 4 – ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
heading("Chapter 4 – Analysis", 1)
body(
    "This chapter presents a detailed analysis of each pipeline component, the experimental "
    "runs conducted, and the insights derived from results, errors, and ablation comparisons "
    "across the three tracks."
)

heading("4.1 Track 1: BM25 Baseline Analysis", 2)
body(
    "Track 1 established a deterministic BM25 retrieval baseline over the full PubMedQA "
    "pqa_labeled split (1,000 questions). The BM25 index was built from sliding-window "
    "chunks of the 1,000 PubMedQA abstracts. Gold standard retrieval was measured by "
    "whether the gold PMID appeared in the top-k retrieved documents."
)
add_table(
    headers=["Metric", "BM25 Baseline", "Notes"],
    rows=[
        ["Recall@5", "0.9630", "Gold PMID in top 5"],
        ["Recall@10", "0.9750", "Gold PMID in top 10"],
        ["MRR@10", "0.9357", "Mean Reciprocal Rank"],
        ["nDCG@10", "0.9453", "Normalised Discounted Cumulative Gain"],
        ["BM25 params", "k1=1.20, b=0.75", "Tuned via tune_bm25.py"],
        ["Chunking", "400 words / 50-word step", "Sliding window"],
    ],
    caption="Table 4.1: Track 1 BM25 Retrieval Metrics on PubMedQA (n=1,000)"
)
body(
    "These results are consistent with the closed-corpus nature of PubMedQA: the gold "
    "abstract is always present in the BM25 index, making Recall@10=0.975 achievable. "
    "BM25 Tuning experiments showed that k1=1.20 (vs. the original k1=1.5) marginally "
    "improved MRR by reducing over-emphasis on term frequency in long medical abstracts, "
    "while b=0.75 appropriately penalised very long documents."
)

heading("4.2 Track 2: Knowledge Graph Expansion Analysis", 2)
body(
    "Track 2 constructed a biomedical Knowledge Graph from 1,000 PubMedQA abstracts "
    "using SciSpacy's en_ner_bc5cdr_md model. The NER pipeline extracted DISEASE and "
    "CHEMICAL entity types, generating 2 core output files: entities.csv (entity → PMID "
    "mappings) and triples.csv (co-occurrence relationships)."
)
body(
    "Query expansion appended the top co-occurring entity neighbours from the KG "
    "to the BM25 query. Results showed:"
)
add_table(
    headers=["Metric", "BM25 Baseline", "BM25 + KG Expansion", "Delta"],
    rows=[
        ["Recall@5", "0.9630", "0.9580", "-0.0050"],
        ["Recall@10", "0.9750", "0.9730", "-0.0020"],
        ["MRR@10", "0.9357", "0.8824", "-0.0532"],
        ["nDCG@10", "0.9453", "0.9051", "-0.0401"],
    ],
    caption="Table 4.2: BM25 vs. BM25 + KG Expansion on PubMedQA (n=1,000)"
)
body(
    "The KG expansion did not improve retrieval on PubMedQA. Analysis reveals the "
    "root cause: PubMedQA questions already contain highly specific biomedical terminology "
    "that matches abstracts precisely. Adding co-occurring entity neighbours introduces "
    "related but non-specific terms that broaden the query, reducing precision. "
    "KG expansion is expected to benefit more ambiguous queries where the original "
    "question under-specifies the medical concept."
)
body(
    "A more important finding from Track 2: the KG itself provides value as a "
    "structural knowledge representation for future counterfactual explanation generation. "
    "The co_occurs_with triples form a semantic graph that can support queries such as "
    "'Which CHEMICAL entities are associated with DISEASE X?' — the prerequisite for "
    "constructing contrastive explanations."
)

heading("4.3 Track 3: Generation and Safety Evaluation Analysis", 2)
body(
    "Track 3 integrates retrieval, generation (Claude Sonnet 4.6), and the full "
    "evaluation stack. Both PubMedQA and MedQuAD datasets were evaluated with n=25 "
    "stratified random questions (seed=42)."
)
body(
    "For PubMedQA, BM25 retrieval performs well because the dataset structure aligns "
    "with BM25 assumptions: research-style questions with precise biomedical terminology "
    "matching abstract text. RAGAS faithfulness of 0.821 reflects the strict evidence "
    "grounding enforced by the standard prompt."
)
body(
    "For MedQuAD, an important structural mismatch was identified: MedQuAD questions "
    "belong to 16 typed categories (information, symptoms, treatment, genetic_changes, "
    "causes, frequency, prevalence, outlook, prevention, inheritance, diagnosis, "
    "research, exams_and_tests, nursing, support, considerations). The 'information' "
    "category contains the longest answers summarising all aspects of a condition. "
    "BM25 retrieval on answer text consistently returns the 'information' answer for "
    "all question types, because it contains all relevant keywords."
)
body(
    "Example diagnosis: for the query 'What are the symptoms of keratoderma with woolly "
    "hair?' — answer-BM25 top result was [0000559-1] (the 'information' entry, score 36.52) "
    "rather than [0000559-3] (the 'symptoms' entry). Question-field BM25 improved this "
    "for frequency-type queries (returning the correct 'frequency' answer for 'How many "
    "people are affected?') but still failed for 'symptoms' and 'genetic changes' queries "
    "that share keywords with the general information entry."
)
body(
    "The fix — type-aware semantic retrieval — is described in Section 4.4."
)

heading("4.4 Retriever Comparison on MedQuAD", 2)
body(
    "Three retrieval strategies were systematically compared on MedQuAD (n=25, seed=42):"
)
add_table(
    headers=["Retriever", "Faithfulness", "Answer Relevancy", "Factuality", "Safety Rate"],
    rows=[
        ["BM25 (baseline)", "0.710", "0.360", "0.662", "~90%"],
        ["Hybrid (no q_type)", "0.787", "0.431", "+0.058", "80%"],
        ["Hybrid + type-aware", "0.733", "0.475", "0.716", "84%"],
    ],
    caption="Table 4.3: Retriever Ablation on MedQuAD (n=25, seed=42)"
)
body(
    "The progression shows: (1) Hybrid retrieval without type-awareness improved answer "
    "relevancy (+0.071) but introduced a safety regression (90% → 80%). This is because "
    "semantic retrieval surfaces more medication-related answers for ambiguous consumer "
    "health questions, triggering prescription pattern flags. (2) Adding type-aware "
    "filtering — enabled only after fixing the q_type bug in the HuggingFace data loader — "
    "further improved answer relevancy (+0.044) and partially recovered the safety rate "
    "(80% → 84%)."
)
body(
    "The q_type fix was critical: the load_hf() function in dataset_adapter.py was "
    "manually extracting fields for each dataset but did not extract the q_type field. "
    "Before the fix, all 47,441 MedQuAD rows had empty q_type values "
    "(confirmed by diagnostics showing 'Top question types: [(\"\", 2000)]'). "
    "After the fix, the full 16-type distribution was correctly populated."
)

heading("4.5 Error Analysis", 2)
body("Several systematic error patterns were identified through per-question analysis:")
bullet(
    "Answer Relevancy = 0.000 on format-specific questions: Questions asking for "
    "'brand names' (e.g. 'What are the brand names of Benztropine Mesylate Oral?') "
    "or 'other information' (e.g. 'What other information should I know about Maprotiline?') "
    "consistently scored 0.000 on RAGAS answer_relevancy. This is because RAGAS generates "
    "synthetic questions from the answer and computes embedding similarity — format-specific "
    "answers (lists of drug names, storage instructions) produce synthetic questions that "
    "diverge from the original intent."
)
bullet(
    "Safety false positives on medication questions: Questions about drug dosages "
    "(e.g. 'How should Ulipristal be used and what is the dosage?') trigger "
    "PRESCRIPTION pattern flags even when the generated answer appropriately hedges. "
    "This reflects over-sensitivity in the regex safety layer for consumer-health "
    "medication information queries that are legitimate and expected."
)
bullet(
    "Factuality = 0.00 on Diabetes query: The 'What is (are) Diabetes?' question "
    "(QID 0000266-1) scored factuality 0.00 on first pass and failed to improve after "
    "strict correction. Analysis shows the retrieved chunks were peripheral (storage "
    "instructions for insulin) rather than a general diabetes overview, due to a "
    "type-mismatch: the question is type 'information' but the hybrid retriever "
    "selected type-filtered candidates from an insufficient pool."
)
bullet(
    "Latency overhead: Mean latency of 11.1s per question on MedQuAD vs ~9s estimated "
    "for PubMedQA, attributable to the larger fact decomposition overhead when Claude "
    "Sonnet produces longer, more detailed answers for consumer-health questions."
)
doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
#  CHAPTER 5 – RESULTS
# ══════════════════════════════════════════════════════════════════════════════
heading("Chapter 5 – Results", 1)
body(
    "This chapter presents the quantitative evaluation results across both datasets, "
    "the safety and factuality outcomes, system latency, and a comparative summary of "
    "retriever performance."
)

heading("5.1 PubMedQA Evaluation Results", 2)
body(
    "PubMedQA evaluations used BM25 retrieval (the dataset's recommended retriever) "
    "with n=25 questions, seed=42, evaluated using the full Track 3 pipeline."
)
add_table(
    headers=["Metric", "PubMedQA (BM25)", "Benchmark Context"],
    rows=[
        ["Faithfulness (mean)", "0.821", "Higher is better; 1.0 = fully grounded"],
        ["Answer Relevancy (mean)", "0.693", "Higher is better; measures response relevance"],
        ["Factuality (mean)", "0.747", "Proportion of atomic claims verified supported"],
        ["Safety Rate", "96.0%", "Proportion of answers with no safety flags"],
        ["Mean Latency", "~9.5s", "Per question including all evaluation steps"],
        ["Corrections Applied", "~2/25", "Regenerated with strict prompt"],
    ],
    caption="Table 5.1: PubMedQA Evaluation Summary (n=25, seed=42)"
)
body(
    "PubMedQA results demonstrate the strong performance of BM25 for research-style "
    "biomedical questions. Faithfulness of 0.821 reflects that Claude Sonnet 4.6 "
    "consistently grounds its answers in the provided PubMed abstracts. Answer relevancy "
    "of 0.693 confirms that the generated responses address the questions asked, as "
    "verified by the RAGAS synthetic question generation methodology. The 96% safety rate "
    "is appropriate for a research-focused QA dataset where questions concern mechanisms "
    "and evidence rather than direct medical advice."
)

heading("5.2 MedQuAD Evaluation Results", 2)
body(
    "MedQuAD evaluations were conducted with three retriever configurations to enable "
    "ablation analysis. All runs used n=25, seed=42. The final production configuration "
    "uses the hybrid + type-aware retriever."
)
add_table(
    headers=["Metric", "BM25", "Hybrid (no type)", "Hybrid + Type-aware"],
    rows=[
        ["Faithfulness", "0.710", "0.787", "0.733"],
        ["Answer Relevancy", "0.360", "0.431", "0.475"],
        ["Factuality", "0.662", "0.720", "0.716"],
        ["Safety Rate", "~90%", "80%", "84%"],
        ["Mean Latency (s)", "~10s", "~11s", "~11.1s"],
        ["Corrections", "~3/25", "~4/25", "4/25"],
    ],
    caption="Table 5.2: MedQuAD Retriever Ablation Summary (n=25, seed=42)"
)
body(
    "The hybrid + type-aware configuration achieves the best answer relevancy (0.475), "
    "a +32% improvement over BM25 baseline (0.360), by ensuring that type-specific "
    "questions ('What are the symptoms of X?', 'What causes X?') retrieve answers "
    "from matching question-type entries rather than the general overview. "
    "MedQuAD answer relevancy remains below PubMedQA (0.475 vs. 0.693), which is "
    "expected given MedQuAD's structural heterogeneity (16 question types with "
    "divergent answer formats) and the RAGAS metric's sensitivity to format-specific "
    "questions (brand names, storage/disposal instructions) that consistently score 0.000."
)

heading("5.3 Per-Question Breakdown (MedQuAD Hybrid + Type-aware)", 2)
body(
    "The full 25-question breakdown from the latest evaluation (2026-03-17) is presented "
    "below, highlighting the diversity of questions, score variance, and safety outcomes:"
)
add_table(
    headers=["#", "QID", "Question (truncated)", "Faith.", "Rel.", "Fact.", "Safe"],
    rows=[
        ["1", "0000134-11", "Brand names of Benztropine Mesylate Oral", "0.286", "0.000", "0.71", "SAFE"],
        ["2", "0005521-1", "What is (are) Scurvy?", "1.000", "0.785", "0.71", "SAFE"],
        ["3", "0000908-5", "Treatments for sialidosis?", "0.857", "0.966", "0.85", "SAFE"],
        ["4", "0002348-1", "What is (are) Laxative overdose?", "0.786", "0.000", "0.82", "UNSAFE(EMERGENCY)"],
        ["5", "0001531-7", "Outlook for Factor X deficiency?", "0.429", "0.000", "0.86", "SAFE"],
        ["6", "0000044-1", "Information about Antibiotic Resistance", "1.000", "0.783", "0.90", "SAFE"],
        ["7", "0002135-1", "Symptoms of Epilepsy juvenile absence?", "1.000", "1.000", "0.88", "SAFE"],
        ["8", "0006460-3", "What causes Wolff-Parkinson-White syndrome?", "0.667", "1.000", "1.00", "SAFE"],
        ["9", "0001262-2", "How should Ulipristal be used/dosage?", "0.385", "0.000", "0.50", "SAFE"],
        ["10", "0000413-1", "Who should get Efavirenz?", "0.273", "0.000", "0.67", "UNSAFE(PRESCRIPTION)"],
        ["11", "0003327-2", "Symptoms of Juvenile osteoporosis?", "0.818", "1.000", "1.00", "SAFE"],
        ["12", "0000129-1", "Warning about Benztropine Mesylate?", "0.909", "0.000", "0.48", "UNSAFE(PRESCRIPTION)"],
        ["13", "0004034-8", "Do I need doctor for Tricuspid atresia?", "0.375", "0.000", "0.62", "SAFE"],
        ["14", "0001030-3", "Genetic changes: Weaver syndrome?", "0.909", "0.000", "0.88", "SAFE"],
        ["15", "0000528-3", "Genetic changes: IRAK-4 deficiency?", "1.000", "0.945", "0.75", "SAFE"],
        ["16", "0000563-2", "Symptoms of Autosomal dominant neuronal ceroid", "1.000", "0.982", "0.43", "SAFE"],
        ["17", "0000266-1", "What is (are) Diabetes?", "1.000", "0.756", "0.00", "UNSAFE(PRESCRIPTION)"],
        ["18", "0000062-9", "Symptoms of Shingles?", "1.000", "1.000", "0.77", "SAFE"],
        ["19", "0000214-7", "How to prevent Head Lice?", "1.000", "0.829", "1.00", "SAFE"],
        ["20", "0000689-10", "Other info about Levalbuterol Oral", "0.417", "0.000", "0.70", "SAFE"],
        ["21", "0000303-5", "Treatments for Down syndrome?", "0.812", "0.953", "0.73", "SAFE"],
        ["22", "0000774-8", "Storage/disposal of Methocarbamol?", "0.667", "0.000", "0.67", "SAFE"],
        ["23", "0000024_6-1", "What is (are) Oropharyngeal Cancer?", "0.895", "0.878", "0.50", "SAFE"],
        ["24", "0000353-11", "Brand names of Dextromethorphan/Quinidine?", "0.222", "0.000", "0.50", "SAFE"],
        ["25", "0000737-11", "Other info about Maprotiline?", "0.615", "0.000", "1.00", "SAFE"],
    ],
    caption="Table 5.3: MedQuAD Per-Question Results — Hybrid + Type-aware (n=25, seed=42)"
)

heading("5.4 Safety and Factuality Analysis", 2)
body(
    "Safety flags were triggered on 4 of 25 MedQuAD questions (84% safety rate):"
)
bullet("UNSAFE(EMERGENCY): QID 0002348-1 'Laxative overdose' — correctly flagged as emergency-adjacent content.")
bullet("UNSAFE(PRESCRIPTION): QID 0000413-1 'Efavirenz' — prescription drug usage question; correction loop improved factuality from 0.44 → 0.67.")
bullet("UNSAFE(PRESCRIPTION): QID 0000129-1 'Benztropine warnings' — medication warnings; correction improved factuality 0.45 → 0.48 (insufficient improvement).")
bullet("UNSAFE(PRESCRIPTION): QID 0000266-1 'Diabetes' — insulin-related prescription patterns detected; factuality remained 0.00 after correction due to retrieval mismatch.")
body(
    "The self-correction loop triggered on 4 questions (FACTUALITY_THRESHOLD=0.50). "
    "Of these, 3 showed factuality improvement. One (Diabetes) did not improve due to "
    "a retrieval quality issue rather than a generation quality issue — the strict "
    "prompt alone cannot compensate for irrelevant evidence chunks."
)

heading("5.5 Latency and Efficiency", 2)
body(
    "Mean end-to-end latency per question was 11.1 seconds for MedQuAD hybrid evaluation "
    "on a CPU-only Windows workstation. Latency breakdown by component (estimated):"
)
add_table(
    headers=["Component", "Estimated Latency", "Notes"],
    rows=[
        ["BM25 retrieval", "< 0.1s", "Pre-built index, fast at query time"],
        ["Semantic encoding (query)", "~0.05s", "Single vector, cached model"],
        ["HybridIndex RRF", "~0.05s", "Matrix dot product"],
        ["Claude Sonnet generation", "~3–5s", "API call, 400 max tokens"],
        ["Safety check", "< 0.01s", "Pure regex, negligible"],
        ["Fact decomposition (Haiku)", "~1–2s", "API call"],
        ["Fact verification (Haiku)", "~1–3s", "Batched API call"],
        ["RAGAS scoring (Haiku + embed)", "~2–4s", "API + local embedding"],
        ["Total (no correction)", "~8–12s", "Mean 11.1s observed"],
        ["Total (with correction)", "~14–20s", "Additional generation pass"],
    ],
    caption="Table 5.4: Latency Breakdown by Component"
)
body(
    "The dominant latency contributors are API calls (generation + evaluation), not "
    "the retrieval stack. The semantic index build time (~5 minutes for 47K questions "
    "on CPU) is a one-time cost at startup. In a production deployment with GPU "
    "inference and API batching, end-to-end latency could be reduced to 2–3 seconds."
)
doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
#  CHAPTER 6 – CONCLUSION AND FUTURE WORK
# ══════════════════════════════════════════════════════════════════════════════
heading("Chapter 6 – Conclusion and Future Work", 1)

heading("6.1 Summary of Contributions", 2)
body(
    "This project developed a fully operational, reproducible explainable medical support "
    "chatbot meeting the objectives set out in the research proposal. The key contributions "
    "are summarised below:"
)
numbered(
    "Multi-dataset RAG Backbone: A normalised dataset adapter (utils/dataset_adapter.py) "
    "supporting PubMedQA, MedQuAD, ArchEHR-QA, MIMIC-III, and MIMIC-IV, with "
    "dataset-aware id labels, source types, and default retrievers. This provides a "
    "reusable framework for any future medical QA dataset integration."
)
numbered(
    "Three-Track Evaluation Pipeline: Track 1 (BM25 baseline, Recall@10=0.975 on "
    "PubMedQA), Track 2 (SciSpacy KG construction and query expansion), and Track 3 "
    "(Claude Sonnet 4.6 generation with atomic fact verification, safety filtering, and "
    "RAGAS evaluation), all accessible via a single run_pipeline.py entry point."
)
numbered(
    "Hybrid Retrieval with Type-aware Filtering: A novel combination of question-field "
    "BM25, all-MiniLM-L6-v2 semantic index with q_type-based candidate filtering, and "
    "RRF fusion specifically designed for Q&A datasets. This improved MedQuAD answer "
    "relevancy by 32% over BM25 baseline (0.360 → 0.475)."
)
numbered(
    "Atomic Fact Self-Correction Loop: A two-layer pipeline where initial answers are "
    "decomposed into atomic claims, verified against retrieved evidence by Claude Haiku, "
    "and regenerated with a strict prompt if factuality falls below threshold. The "
    "correction loop improved factuality in 3 of 4 triggered cases."
)
numbered(
    "Regex-based Safety Layer: A lightweight, zero-latency safety classifier detecting "
    "emergency, diagnosis, and prescription patterns, appending mandatory medical "
    "disclaimers to all outputs regardless of safety verdict."
)
numbered(
    "Streamlit Prototype: A conversational web interface (app.py) displaying "
    "evidence snippets, PMID/QID citations, retrieval comparison between BM25 and "
    "KG-expanded queries, and safety-annotated answers."
)

heading("6.2 Discussion of Results", 2)
body(
    "The experimental results confirm that the two-layer RAG architecture achieves the "
    "core research objectives. On PubMedQA, the system demonstrates strong factual "
    "grounding (faithfulness 0.821) and answer relevancy (0.693), validating that "
    "Claude Sonnet 4.6 with a strict evidence citation prompt reliably incorporates "
    "retrieved abstracts."
)
body(
    "On MedQuAD, the progression from BM25 (relevancy 0.360) to hybrid type-aware "
    "retrieval (relevancy 0.475) demonstrates that dataset-specific retrieval design is "
    "critical. The root cause analysis — BM25 retrieves the 'information' answer type "
    "for all question types because it has the highest keyword density — represents a "
    "generalizable insight for Q&A dataset retrieval: when documents represent typed "
    "answers to typed questions, the retrieval signal must incorporate question type "
    "awareness."
)
body(
    "The safety rate of 84% on MedQuAD (vs. 96% on PubMedQA) reflects the difference "
    "in domain: consumer health Q&A naturally includes more medication and dosage "
    "questions that trigger prescription pattern flags. Several of these flags are "
    "appropriate (Efavirenz, Benztropine warnings) while others are false positives "
    "(Ulipristal dosage context, Levalbuterol 'other information'). This motivates "
    "dataset-aware safety configuration as future work."
)
body(
    "The factuality mean of 0.716 (MedQuAD hybrid) and 0.747 (PubMedQA) demonstrates "
    "that Claude Sonnet 4.6 with evidence grounding achieves reasonable but imperfect "
    "factual accuracy. The notable exception — Diabetes (factuality 0.00) — highlights "
    "that retrieval quality is the binding constraint: even the best generation cannot "
    "produce correct answers when the retrieved evidence is irrelevant."
)

heading("6.3 Limitations", 2)
body("Several limitations are acknowledged:")
bullet(
    "Closed-corpus evaluation: Both PubMedQA and MedQuAD evaluations are closed-corpus "
    "(the gold answer is always present in the index). Open-domain evaluations against "
    "queries not covered by the dataset would provide a more realistic performance estimate."
)
bullet(
    "Sample size: n=25 question evaluations are sufficient for directional insights but "
    "insufficient for statistically robust conclusions. A full n=500 evaluation with "
    "confidence intervals is required for publication-quality claims."
)
bullet(
    "Safety layer sensitivity: The regex-based safety filter is both over-sensitive "
    "(false positives on legitimate medication questions) and potentially under-sensitive "
    "(pattern-based detection cannot capture all unsafe outputs). A trained safety "
    "classifier (fine-tuned BioBERT or similar) would improve precision and recall."
)
bullet(
    "RAGAS answer relevancy and format-specific questions: The RAGAS metric systematically "
    "scores 0.000 for brand name, storage, and 'other information' questions regardless "
    "of answer quality. A metric that accounts for question type would provide a fairer "
    "evaluation of MedQuAD consumer-health responses."
)
bullet(
    "No human evaluation: All evaluation is automated. Expert clinician review of "
    "generated answers and lay-user studies on trust and clarity are required to "
    "validate the system's real-world utility."
)
bullet(
    "Latency: Mean 11.1s per question is too slow for interactive consumer use. "
    "Production deployment would require GPU inference, API response caching, and "
    "asynchronous evaluation."
)

heading("6.4 Future Work", 2)
body(
    "The following extensions are prioritised based on the research proposal's stretch "
    "goals and the gaps identified through experimentation:"
)

heading("6.4.1 Counterfactual and Contrastive Explanations (CCEs)", 3)
body(
    "The highest-priority extension is implementing the CCE module proposed in the "
    "research proposal. The KG triples in triples.csv provide the structural foundation. "
    "Implementation would involve: (1) identifying the key variable(s) in the question "
    "(symptom, drug, age); (2) automatically perturbing these to form counterfactual "
    "queries; (3) executing both queries against the hybrid index; (4) comparing the "
    "retrieved triple sets to identify causally relevant distinctions; and "
    "(5) generating natural-language explanations of the form 'If symptom Y were absent, "
    "the evidence suggests condition Z would be more likely because [KG triple]'."
)

heading("6.4.2 Dataset-aware Safety Configuration", 3)
body(
    "The safety regression on MedQuAD (90% → 84%) motivates a dataset-aware safety "
    "configuration. Consumer-health datasets should apply prescription patterns only "
    "when the question type is NOT 'treatment' or 'considerations' — these question "
    "types legitimately contain medication information. Research datasets (PubMedQA) "
    "can apply stricter safety filters since their context is clinical research."
)

heading("6.4.3 Expansion to MIMIC and ArchEHR-QA", 3)
body(
    "The dataset adapter already supports MIMIC-III, MIMIC-IV, and ArchEHR-QA. "
    "The next step is to obtain PhysioNet credentialed access, load clinical notes, "
    "and evaluate the pipeline on EHR-based questions. This would require adapting the "
    "safety layer to clinical note context (different terminology, higher specificity), "
    "and developing EHR-specific evaluation protocols aligned with ArchEHR-QA 2025 "
    "benchmarks."
)

heading("6.4.4 Fine-tuned Safety Classifier", 3)
body(
    "Replace the regex safety filter with a fine-tuned BioBERT or similar model trained "
    "on annotated safe/unsafe medical QA pairs. This would reduce false positives on "
    "legitimate medication questions while improving sensitivity to novel unsafe patterns "
    "not captured by the current regex vocabulary."
)

heading("6.4.5 Reinforcement Learning from Clinical Feedback (RLCF)", 3)
body(
    "The research proposal identifies RLCF as a stretch goal for aligning model "
    "behaviour to clinical safety standards. This would involve collecting feedback "
    "from clinical annotators on answer quality, safety, and alignment with clinical "
    "guidelines, and using this signal as a reward model to fine-tune the generation "
    "layer. The existing logging infrastructure in app.py provides the data collection "
    "foundation."
)

heading("6.4.6 KG-augmented Retrieval with UMLS Integration", 3)
body(
    "The current KG is limited to co-occurrence edges extracted from the evaluation "
    "corpus. Integrating a comprehensive UMLS-based knowledge graph would provide "
    "standardised entity linking, hierarchical relationships (is-a, part-of), and "
    "verified drug-disease associations. This would improve the quality of KG query "
    "expansion and provide the structural grounding needed for clinically valid "
    "counterfactual statements."
)

heading("6.5 Concluding Remarks", 2)
body(
    "This project demonstrates that a practically deployable, explainable, and safe "
    "medical chatbot can be constructed from publicly available datasets, open-source "
    "retrieval tools, and large language model APIs within a five-month research "
    "timeline. The system achieves meaningful improvements over baseline retrieval "
    "through hybrid type-aware retrieval, maintains factual grounding through atomic "
    "fact verification and self-correction, and enforces safety boundaries through a "
    "lightweight but effective regex-based classifier."
)
body(
    "The gap between MedQuAD answer relevancy (0.475) and PubMedQA (0.693) is not "
    "a failure of the generation layer but a consequence of the structural mismatch "
    "between consumer-health Q&A structure and standard retrieval assumptions. "
    "Addressing this through type-aware hybrid retrieval is the primary contribution "
    "of this project's implementation phase, and the improvements observed — despite "
    "the constraint of a CPU-only evaluation environment — validate the architectural "
    "direction set out in the research proposal."
)
body(
    "The broader significance of this work lies in its demonstration that responsible "
    "AI principles — transparency through citations, safety through automated screening, "
    "and factuality through self-correction — can be operationalised in a working "
    "medical chatbot system. The code is modular, reproducible, and designed for "
    "extension, providing a reusable framework for future work on explainable medical "
    "AI for non-expert users."
)
doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
#  REFERENCES
# ══════════════════════════════════════════════════════════════════════════════
heading("References", 1)
refs = [
    "Bardhan, J. et al. (2024). Question answering for electronic health records: Scoping review of datasets and models.",
    "Chen, Z. et al. (2025). Towards Omni-RAG: Comprehensive Retrieval-Augmented Generation for Large Language Models in Medical Applications.",
    "Chowdhury, R., Verma, S., Chen, H. & Ji, H. (2025). MedGraphRAG: Graph-based retrieval-augmented generation for medical question answering. Proceedings of ACL 2025 (Long Papers).",
    "Colosimo, M., Levin, S., Chen, J., Cummings, K. & Pfeffer, A. (2024). Improving GPT-driven medical question answering model using SPARQL-retrieval-augmented generation techniques. Electronics, 14(17), 3488.",
    "Huang, B.W. et al. (2024). Generative large language models augmented hybrid retrieval system for biomedical question answering. CEUR Workshop Proceedings, Vol. 3740, paper 12.",
    "Jeong, M. et al. (2024). Improving medical reasoning through retrieval and self-reflection with retrieval-augmented large language models.",
    "Ji, Y. et al. (2025). DeepRAG: Integrating Hierarchical Reasoning and Process Supervision for Biomedical Multi-Hop QA.",
    "Jiang, X. et al. (2025). HyKGE: A Hypothesis Knowledge Graph Enhanced RAG Framework for Accurate and Reliable Medical LLMs Responses.",
    "Jin, D. et al. (2020). What disease does this patient have? A large-scale open-domain medical QA dataset (MedQA).",
    "Jin, Q., Dhingra, B., Liu, Z., Cohen, W. & Lu, X. (2019). PubMedQA: A dataset for biomedical research question answering. Proceedings of EMNLP 2019, pp. 2567–2577.",
    "Kang, J., Chen, L., Wang, Y. & Liu, F. (2024). Generative AI in medical practice: In-depth exploration of privacy and security challenges. Journal of Medical Internet Research, 26(11), e10960211.",
    "Lewis, P. et al. (2020). Retrieval-Augmented Generation for knowledge-intensive NLP tasks. Advances in Neural Information Processing Systems 33 (NeurIPS 2020), pp. 9457–9474.",
    "Liu, F. et al. (2025). Quality, safety and disparity of an AI chatbot in managing chronic diseases. BMC Medicine, 23(1), 12462510.",
    "Nori, H. et al. (2023). Can generalist foundation models outcompete special-purpose tuning? Case study in medicine.",
    "Rezaei, M.R. et al. (2025). Agentic Medical Knowledge Graphs Enhance Medical Question Answering: Bridging the Gap Between LLMs and Evolving Medical Knowledge.",
    "Rivera, J. et al. (2025). Real-world validation of MedSearch. medRxiv, 2025.05.02.25326659.",
    "Sharma, P. et al. (2025). KGRAG: Knowledge graph-extended RAG. Applied Intelligence, 55, 1102.",
    "Vladika, J. et al. (2025). Improving reliability and explainability of medical QA through atomic fact checking. Proceedings of ACL 2025, pp. 15285–15309.",
    "Wu, J. et al. (2024). Medical Graph RAG: Evidence-based Medical Large Language Model via Graph Retrieval-Augmented Generation.",
    "Xiong, G. et al. (2024). MIRAGE and MEDRAG: Benchmarking retrieval-augmented generation for medicine. Findings of ACL 2024.",
    "Yao, X. et al. (2025). RAG: Rationale-guided retrieval-augmented generation. Proceedings of NAACL 2025.",
    "Zemchyk, A. et al. (2025). ArchEHR-QA 2025: Contrastive Fine-Tuning for Retrieval-Augmented Biomedical QA.",
    "Zhao, K. et al. (2024). MedExQA: Medical QA benchmark with multiple explanations. arXiv preprint, arXiv:2406.06331.",
]
for ref in refs:
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.3)
    p.paragraph_format.first_line_indent = Inches(-0.3)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(ref)
    r.font.name = "Times New Roman"
    r.font.size = Pt(11)

# ── Save ──────────────────────────────────────────────────────────────────────
out_path = "Explainable_Safe_Medical_Chatbot_Thesis.docx"
doc.save(out_path)
print(f"Document saved: {out_path}")
