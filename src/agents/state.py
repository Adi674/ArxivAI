from typing import TypedDict, Optional


class RAGState(TypedDict):
    # ── Input ──────────────────────────────────────────────
    original_query: str
    user_id: str
    collab_ids: list[str]
    llm_mode: str                  # budget | balanced | quality | research

    # ── Agent 1: Domain Classifier ─────────────────────────
    primary_domain: str
    secondary_domains: list[str]
    domain_confidence: float

    # ── Agent 2: Query Analyzer ────────────────────────────
    query_type: str                # single_hop | multi_hop
    sub_queries: list[str]
    needs_personal_papers: bool
    needs_recent: bool

    # ── Agent 3: Search Strategy ───────────────────────────
    search_spaces: list[str]
    fetch_arxiv_fresh: bool

    # ── Agent 4: Retriever ─────────────────────────────────
    retrieved_papers: list[dict]
    reformulation_count: int

    # ── Agent 5: Reasoner ──────────────────────────────────
    findings: dict
    contradictions: list[dict]
    agreements: list[dict]
    citation_graph: dict
    knowledge_gaps: list[str]

    # ── Agent 6: Synthesis ────────────────────────────────
    draft_answer: str

    # ── Agent 7: Evaluator ────────────────────────────────
    hallucination_detected: bool
    quality_score: float
    ragas_scores: dict
    needs_refinement: bool
    refinement_count: int
    evaluator_feedback: str

    # ── Final Output ──────────────────────────────────────
    final_answer: str
    sources: list[dict]
    reasoning_trace: list[str]