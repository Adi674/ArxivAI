from typing import TypedDict, Optional


class RAGState(TypedDict):
    # ── Input ──────────────────────────────────────────────
    original_query: str
    user_id: str
    collab_ids: list[str]
    llm_mode: str                  # budget | balanced | quality | research
    conversation_id: Optional[str] # NEW: for intent + conversational node history

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
    search_tool: str               # semantic | keyword | hybrid | hybrid_v2

    # ── Agent 4: Retriever ─────────────────────────────────
    retrieved_papers: list[dict]
    reformulation_count: int

    # Retrieval signal fields — NEW (Phase 1)
    retrieval_method: Optional[str]           # "hybrid_v2" | "hybrid" | "semantic" | "bm25_only"
    semantic_scores: Optional[list[float]]    # relevance scores from semantic lane
    bm25_scores: Optional[list[float]]        # normalised BM25 scores
    rrf_scores: Optional[list[float]]         # RRF merged scores
    rerank_scores: Optional[list[float]]      # cross-encoder scores (final ranking signal)
    arxiv_fallback_triggered: Optional[bool]  # did we trigger an arXiv live fetch?
    freshly_fetched_papers: Optional[list[str]]  # paper_ids ingested in this request

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

    # ── Safety Guardrails — NEW (Phase 4) ────────────────
    guardrail_allowed: Optional[bool]
    guardrail_reason: Optional[str]
    cleaned_query: Optional[str]
    guardrail_risk_score: Optional[float]
    pii_found: Optional[bool]
    pipeline_short_circuited: Optional[bool]
    output_guardrail_clean: Optional[str]
    citation_verify_passed: Optional[bool]
    invalid_citations_found: Optional[list[str]]

    # ── Intent Routing — NEW (Phase 5) ──────────────────
    intent: Optional[str]
    is_conversational: Optional[bool]
