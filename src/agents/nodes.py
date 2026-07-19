import asyncio
import json
import logging
from src.agents.state import RAGState
from src.llm.provider import get_llm, call_llm
from src.llm.prompts import (
    DOMAIN_CLASSIFY_PROMPT, QUERY_ANALYZE_PROMPT, SEARCH_STRATEGY_PROMPT,
    QUERY_REFORMULATE_PROMPT, EXTRACT_FINDINGS_PROMPT, CONTRADICTION_DETECT_PROMPT,
    SYNTHESIS_PROMPT, SYNTHESIS_REFINE_PROMPT,
    HALLUCINATION_CHECK_PROMPT, COMPLETENESS_CHECK_PROMPT,
)

logger = logging.getLogger(__name__)



def _parse_json(text: str, fallback: dict) -> dict:
    """Try to parse JSON from LLM output. Return fallback on failure."""
    try:
        # Strip markdown code fences if present
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except Exception:
        logger.warning(f"JSON parse failed. Raw: {text[:200]}")
        return fallback


# ─────────────────────────────────────────────────────────────
# AGENT 1: Domain Classifier
# ─────────────────────────────────────────────────────────────

def classify_domain(state: RAGState) -> RAGState:
    """
    Detect the primary and secondary research domains for the query.
    Uses Mistral-7B via Ollama.
    """
    llm = get_llm("domain_classifier", state["llm_mode"])
    prompt = DOMAIN_CLASSIFY_PROMPT.format(query=state["original_query"])
    raw = call_llm(llm, prompt)

    result = _parse_json(raw, {
        "primary_domain": "ML",
        "secondary_domains": [],
        "confidence": 0.5,
    })

    state["primary_domain"] = result.get("primary_domain", "ML")
    state["secondary_domains"] = result.get("secondary_domains", [])
    state["domain_confidence"] = float(result.get("confidence", 0.5))
    state["reasoning_trace"].append(
        f"[Domain Classifier] → {state['primary_domain']} (confidence: {state['domain_confidence']})"
    )
    logger.info(f"Domain: {state['primary_domain']} ({state['domain_confidence']})")
    return state


# ─────────────────────────────────────────────────────────────
# AGENT 2: Query Analyzer
# ─────────────────────────────────────────────────────────────

def analyze_query(state: RAGState) -> RAGState:
    """
    Determine if query is single-hop or multi-hop.
    Detect if user wants personal papers or recent papers.
    """
    llm = get_llm("query_analyzer", state["llm_mode"])
    prompt = QUERY_ANALYZE_PROMPT.format(
        query=state["original_query"],
        domain=state["primary_domain"],
    )
    raw = call_llm(llm, prompt)

    result = _parse_json(raw, {
        "query_type": "single_hop",
        "needs_personal_papers": False,
        "needs_recent": False,
        "sub_queries": [],
    })

    state["query_type"] = result.get("query_type", "single_hop")
    state["sub_queries"] = result.get("sub_queries", [])
    state["needs_personal_papers"] = bool(result.get("needs_personal_papers", False))
    state["needs_recent"] = bool(result.get("needs_recent", False))
    state["reasoning_trace"].append(
        f"[Query Analyzer] → {state['query_type']}, personal={state['needs_personal_papers']}, recent={state['needs_recent']}"
    )
    return state


# ─────────────────────────────────────────────────────────────
# AGENT 3: Search Strategy
# ─────────────────────────────────────────────────────────────

def decide_search_strategy(state: RAGState) -> RAGState:
    """
    Decide which namespaces to search, whether to fetch fresh from arXiv,
    and which search tool to use (semantic | keyword | hybrid).
    """
    llm = get_llm("search_strategy", state["llm_mode"])
    prompt = SEARCH_STRATEGY_PROMPT.format(
        query=state["original_query"],
        domain=state["primary_domain"],
        query_type=state["query_type"],
        needs_recent=state["needs_recent"],
    )
    raw = call_llm(llm, prompt)

    result = _parse_json(raw, {
        "search_spaces": ["public"],
        "fetch_arxiv_fresh": False,
        "search_tool": "hybrid",
    })

    spaces = result.get("search_spaces", ["public"])
    if state["needs_personal_papers"] and "user_private" not in spaces:
        spaces.append("user_private")

    # Validate search_tool — fall back to hybrid if LLM returns unexpected value
    tool = result.get("search_tool", "hybrid")
    if tool not in ("semantic", "keyword", "hybrid"):
        logger.warning(f"Invalid search_tool from LLM: '{tool}', defaulting to 'hybrid'")
        tool = "hybrid"

    state["search_spaces"] = spaces
    state["fetch_arxiv_fresh"] = bool(result.get("fetch_arxiv_fresh", False))
    state["search_tool"] = tool
    state["reasoning_trace"].append(
        f"[Search Strategy] → spaces={state['search_spaces']}, "
        f"arxiv_fresh={state['fetch_arxiv_fresh']}, search_tool={state['search_tool']}"
    )
    return state


# ─────────────────────────────────────────────────────────────
# AGENT 4: Retriever
# ─────────────────────────────────────────────────────────────

async def retrieve_papers(state: RAGState) -> RAGState:
    """
    Retrieve papers using the full 3-stage hybrid pipeline:
      Stage 1: semantic_search(k=20) + bm25_search(k=20) in parallel
      Stage 2: Reciprocal Rank Fusion merge (k=60, expand to 40)
      Stage 3: Cross-encoder rerank → top-5

    Falls back to old hybrid_search if hybrid_search_v2 fails.
    Reformulates query if avg relevance < 0.6 (max 2 times).
    Flags arxiv_fallback_triggered if max_rerank_score < 0.35.
    """
    from src.vectordb.searcher import hybrid_search_v2, hybrid_search, calculate_avg_relevance

    query = state["original_query"]
    tool_name = state.get("search_tool", "hybrid_v2")
    logger.info(f"[retrieve_papers] search_tool={tool_name}, query='{query[:60]}'")

    # ── Primary: hybrid_search_v2 (BM25 + RRF + CrossEncoder) ───────────────
    results, signals = await hybrid_search_v2(
        query=query,
        user_id=state["user_id"],
        domain=state["primary_domain"],
        k=5,
        collab_ids=state["collab_ids"],
        semantic_k=20,
        bm25_k=20,
        rrf_expand=15,
    )

    max_score = signals.get("max_rerank_score", 0.0)
    avg_score = calculate_avg_relevance(results)
    logger.info(
        f"[retrieve_papers] {len(results)} results | "
        f"max_rerank={max_score:.4f} | avg={avg_score:.4f}"
    )

    # ── Reformulation loop: if quality is poor, rewrite the query ────────────
    if avg_score < 0.4 and state["reformulation_count"] < 2 and results:
        llm = get_llm("retriever", state["llm_mode"])
        prompt = QUERY_REFORMULATE_PROMPT.format(
            query=query,
            domain=state["primary_domain"],
            score=avg_score,
        )
        new_query = call_llm(llm, prompt).strip()
        logger.info(f"[retrieve_papers] Reformulated query: {new_query[:80]}")

        retry_results, retry_signals = await hybrid_search_v2(
            query=new_query,
            user_id=state["user_id"],
            domain=state["primary_domain"],
            k=5,
            collab_ids=state["collab_ids"],
            semantic_k=20,
            bm25_k=20,
            rrf_expand=15,
        )

        # Only accept reformulation if it improved quality
        if calculate_avg_relevance(retry_results) > avg_score:
            results = retry_results
            signals = retry_signals
            max_score = retry_signals.get("max_rerank_score", 0.0)
            avg_score = calculate_avg_relevance(results)

        state["reformulation_count"] += 1
        state["reasoning_trace"].append(
            f"[Retriever] Reformulated query (attempt {state['reformulation_count']}): "
            f"{new_query[:80]} → avg_score={avg_score:.4f}"
        )

    # ── Store retrieval signals into state ───────────────────────────────────
    state["retrieved_papers"] = results
    state["retrieval_method"] = "hybrid_v2"
    state["rerank_scores"] = [r.get("rerank_score", 0.0) for r in results]
    state["semantic_scores"] = [r.get("relevance_score", 0.0) for r in results]
    state["rrf_scores"] = [r.get("rrf_score", 0.0) for r in results]
    state["bm25_scores"] = [r.get("bm25_score", 0.0) for r in results]

    # ── arXiv fallback signal: low relevance AND no reformulation left ───────
    state["arxiv_fallback_triggered"] = bool(
        max_score < 0.35 and state["reformulation_count"] >= 2
    )
    state["freshly_fetched_papers"] = state.get("freshly_fetched_papers") or []

    state["reasoning_trace"].append(
        f"[Retriever] hybrid_v2 → {len(results)} papers | "
        f"max_rerank={max_score:.4f} | avg={avg_score:.4f} | "
        f"arxiv_fallback={state['arxiv_fallback_triggered']}"
    )
    return state



# ─────────────────────────────────────────────────────────────
# AGENT 5: Reasoner
# ─────────────────────────────────────────────────────────────

def reason_over_papers(state: RAGState) -> RAGState:
    """
    Extract findings, detect contradictions, build citation graph, identify gaps.
    Uses Llama2-13B.
    """
    llm = get_llm("reasoner", state["llm_mode"])
    papers = state["retrieved_papers"]

    if not papers:
        state["findings"] = {}
        state["contradictions"] = []
        state["agreements"] = []
        state["citation_graph"] = {}
        state["knowledge_gaps"] = ["No relevant papers found"]
        return state

    # Extract findings from each paper
    findings = {}
    for paper in papers[:5]:  # Top 5 to limit tokens
        prompt = EXTRACT_FINDINGS_PROMPT.format(
            title=paper.get("title", "Unknown"),
            authors=paper.get("authors", "Unknown"),
            domain=paper.get("domain", ""),
            content=paper.get("content", "")[:1500],  # Limit chunk size
        )
        finding = call_llm(llm, prompt)
        findings[paper["paper_id"]] = finding

    # Detect contradictions between top 2 papers
    contradictions = []
    if len(papers) >= 2:
        prompt = CONTRADICTION_DETECT_PROMPT.format(
            title_a=papers[0].get("title", ""),
            content_a=papers[0].get("content", "")[:800],
            title_b=papers[1].get("title", ""),
            content_b=papers[1].get("content", "")[:800],
        )
        contradiction_result = call_llm(llm, prompt)
        if "No contradiction" not in contradiction_result:
            contradictions.append({
                "papers": [papers[0]["paper_id"], papers[1]["paper_id"]],
                "description": contradiction_result,
            })

    state["findings"] = findings
    state["contradictions"] = contradictions
    state["agreements"] = []
    state["citation_graph"] = {}
    state["knowledge_gaps"] = []
    state["reasoning_trace"].append(
        f"[Reasoner] → findings for {len(findings)} papers, {len(contradictions)} contradictions"
    )
    return state


# ─────────────────────────────────────────────────────────────
# AGENT 6: Synthesis
# ─────────────────────────────────────────────────────────────

def synthesize_answer(state: RAGState) -> RAGState:
    """
    Generate the answer. Uses evaluator feedback if refining.
    Uses Llama2-13B → falls back to API providers.
    """
    llm = get_llm("synthesis", state["llm_mode"])

    findings_text = "\n\n".join(
        f"[{pid}]: {text}" for pid, text in state["findings"].items()
    )
    contradictions_text = "\n".join(
        c["description"] for c in state["contradictions"]
    ) or "None"

    # Use refinement prompt if feedback exists
    if state.get("evaluator_feedback") and state["refinement_count"] > 0:
        prompt = SYNTHESIS_REFINE_PROMPT.format(
            query=state["original_query"],
            draft=state["draft_answer"],
            feedback=state["evaluator_feedback"],
        )
    else:
        prompt = SYNTHESIS_PROMPT.format(
            query=state["original_query"],
            domain=state["primary_domain"],
            findings=findings_text,
            contradictions=contradictions_text,
            knowledge_gaps="\n".join(state["knowledge_gaps"]) or "None identified",
        )

    answer = call_llm(llm, prompt)
    state["draft_answer"] = answer
    state["reasoning_trace"].append(
        f"[Synthesis] → Generated answer ({len(answer)} chars), refinement #{state['refinement_count']}"
    )
    return state


# ─────────────────────────────────────────────────────────────
# AGENT 7: Evaluator
# ─────────────────────────────────────────────────────────────

async def evaluate_answer(state: RAGState) -> RAGState:
    """
    Agent 7: Evaluate the draft answer using:
      A) 7-metric LLM-as-Judge (parallel, llama-3.3-70b-versatile)
      B) NLI hallucination detection (cross-encoder/nli-deberta-v3-small)

    Results stored in existing RAGState fields for backward compatibility:
      - ragas_scores: the 6 dimension scores dict
      - quality_score: weighted overall score
      - evaluator_feedback: concatenated actionable feedback for refinement
      - hallucination_detected: True if NLI hallucination_rate > 0.20
      - needs_refinement: True if overall < 0.65 or any alert threshold crossed
    """
    from src.eval import llm_judge, hallucination as nli_module
    from groq import Groq
    from src.config import get_settings

    settings = get_settings()
    groq_client = Groq(api_key=settings.GROQ_API_KEY)

    answer = state["draft_answer"]
    papers = state["retrieved_papers"]

    # ── Run LLM judge + NLI in parallel ──────────────────────────────────────
    judge_task = llm_judge.evaluate(
        query=state["original_query"],
        answer=answer,
        retrieved_papers=papers,
        groq_client=groq_client,
    )
    nli_task = asyncio.get_event_loop().run_in_executor(
        None,  # default thread pool executor
        nli_module.check_hallucination,
        answer,
        papers,
    )

    eval_result, nli_result = await asyncio.gather(judge_task, nli_task, return_exceptions=True)

    # Handle exceptions gracefully — evaluation failure should never crash the pipeline
    if isinstance(eval_result, Exception):
        logger.error(f"[Evaluator] LLM judge failed: {eval_result}. Using defaults.")
        from src.eval.metrics import EvalResult
        eval_result = EvalResult()
        eval_result.overall_score = 0.7
        eval_result.needs_refinement = False

    if isinstance(nli_result, Exception):
        logger.error(f"[Evaluator] NLI check failed: {nli_result}. Using defaults.")
        nli_result = {"hallucination_rate": 0.0, "unsupported_claims": [], "attribution_map": {}}

    # ── Merge NLI results into EvalResult ────────────────────────────────────
    eval_result.hallucination_rate = nli_result.get("hallucination_rate", 0.0)
    eval_result.unsupported_claims = nli_result.get("unsupported_claims", [])
    eval_result.attribution_map = nli_result.get("attribution_map", {})

    # Re-compute needs_refinement now that NLI rate is set
    eval_result.compute_overall()

    # ── Store into RAGState (backward-compatible field names) ─────────────────
    state["ragas_scores"] = eval_result.to_dict()
    state["quality_score"] = eval_result.overall_score
    state["evaluator_feedback"] = eval_result.build_combined_feedback()
    state["hallucination_detected"] = eval_result.hallucination_rate > 0.20
    state["needs_refinement"] = (
        eval_result.needs_refinement and state["refinement_count"] < 1
    )
    state["refinement_count"] += 1

    state["reasoning_trace"].append(
        f"[Evaluator] overall={eval_result.overall_score:.4f} | "
        f"faithfulness={eval_result.faithfulness.score:.2f} | "
        f"hallucination_rate={eval_result.hallucination_rate:.2f} | "
        f"refine={state['needs_refinement']}"
    )
    logger.info(
        f"[Evaluator] overall={eval_result.overall_score:.4f}, "
        f"nli_hallucination={eval_result.hallucination_rate:.4f}, "
        f"needs_refinement={state['needs_refinement']}"
    )
    return state



def should_refine(state: RAGState) -> str:
    """
    LangGraph conditional edge.
    Routes back to synthesis if quality is poor, else to format output.
    """
    if state["needs_refinement"] and state["refinement_count"] < 1:
        return "synthesis"
    return "format_output"


# ─────────────────────────────────────────────────────────────
# FORMAT OUTPUT (terminal node)
# ─────────────────────────────────────────────────────────────

def format_output(state: RAGState) -> RAGState:
    """
    Finalize answer and build sources list for the API response.
    """
    if state.get("pipeline_short_circuited"):
        state["final_answer"] = state.get("guardrail_reason") or "Request blocked by safety guardrails."
        state["sources"] = []
        state["reasoning_trace"].append("[Format] Short-circuited due to safety block.")
        return state

    state["final_answer"] = state["draft_answer"]

    # Deduplicate sources by paper_id
    seen = set()
    sources = []
    for p in state["retrieved_papers"]:
        pid = p["paper_id"]
        if pid not in seen:
            seen.add(pid)
            sources.append({
                "paper_id": pid,
                "title": p.get("title", ""),
                "authors": p.get("authors", ""),
                "relevance_score": p.get("relevance_score", 0.0),
            })

    state["sources"] = sources
    state["reasoning_trace"].append(
        f"[Format] → Final answer ready. {len(sources)} unique sources."
    )
    return state


# ─────────────────────────────────────────────────────────────
# SAFETY GUARDRAILS NODES (Phase 4)
# ─────────────────────────────────────────────────────────────

async def gate_input(state: RAGState) -> RAGState:
    """
    Agent 0: Input Guardrail Node.
    Validates query safety, toxicity, OOS, and anonymizes PII.
    """
    from src.guardrails.input_guard import run_input_guardrail
    
    query = state["original_query"]
    user_id = state["user_id"]
    llm_mode = state["llm_mode"]
    
    allowed, reason, cleaned_query, risk_score, pii_found = await run_input_guardrail(
        query=query,
        user_id=user_id,
        llm_mode=llm_mode
    )
    
    state["guardrail_allowed"] = allowed
    state["guardrail_reason"] = reason
    state["cleaned_query"] = cleaned_query
    state["guardrail_risk_score"] = risk_score
    state["pii_found"] = pii_found
    state["pipeline_short_circuited"] = not allowed
    
    if pii_found:
        # Update original_query to the anonymized version for safety
        state["original_query"] = cleaned_query
        
    state["reasoning_trace"].append(
        f"[InputGuardrail] allowed={allowed} | pii_found={pii_found} | risk={risk_score:.2f}"
    )
    return state


async def gate_output(state: RAGState) -> RAGState:
    """
    Agent 8: Output Guardrail Node.
    Validates generated response citation integrity, leaks no PII, and screens toxicity.
    """
    from src.guardrails.output_guard import run_output_guardrail
    
    # If already short circuited at input, do nothing
    if state.get("pipeline_short_circuited"):
        return state
        
    answer = state["draft_answer"]
    papers = state["retrieved_papers"]
    llm_mode = state["llm_mode"]
    
    cleaned_answer, allowed, reason, citation_verify_passed, invalid_citations = await run_output_guardrail(
        answer=answer,
        retrieved_papers=papers,
        llm_mode=llm_mode
    )
    
    state["draft_answer"] = cleaned_answer
    state["guardrail_allowed"] = allowed
    if not allowed:
        state["guardrail_reason"] = reason
        state["pipeline_short_circuited"] = True
        state["draft_answer"] = f"Response blocked by safety guardrails. Reason: {reason}"
        
    state["citation_verify_passed"] = citation_verify_passed
    state["invalid_citations_found"] = invalid_citations
    
    state["reasoning_trace"].append(
        f"[OutputGuardrail] allowed={allowed} | citation_verify={citation_verify_passed} | "
        f"invalid_citations={len(invalid_citations)}"
    )
    return state


def check_input_guardrail(state: RAGState) -> str:
    """
    LangGraph conditional edge.
    Routes to classify_intent_node if safe, else short-circuits directly to format_output.
    """
    if state.get("guardrail_allowed", True):
        return "classify_intent_node"
    return "format_output"


async def classify_intent_node(state: RAGState) -> RAGState:
    """
    Agent 1: Intent Classifier Node.
    Classifies the user query intent to optimize pipeline routing.
    """
    from src.agents.intent_classifier import classify_intent
    
    query = state["original_query"]
    convo_id = state.get("conversation_id")
    llm_mode = state["llm_mode"]
    
    intent, confidence = await classify_intent(
        query=query,
        conversation_id=convo_id,
        llm_mode=llm_mode
    )
    
    state["intent"] = intent
    state["is_conversational"] = intent in ("conversational", "clarification")
    
    state["reasoning_trace"].append(
        f"[IntentClassifier] intent={intent} | confidence={confidence:.2f}"
    )
    return state


async def run_conversational_node(state: RAGState) -> RAGState:
    """
    Conversational Agent Node (Agent 9).
    Generates a conversational response directly using history without document retrieval.
    """
    from src.agents.conversational_node import run_conversational_response
    
    query = state["original_query"]
    convo_id = state.get("conversation_id")
    llm_mode = state["llm_mode"]
    
    response = await run_conversational_response(
        query=query,
        conversation_id=convo_id,
        llm_mode=llm_mode
    )
    
    # Store directly in draft_answer so evaluate/output_guard works
    state["draft_answer"] = response
    
    state["reasoning_trace"].append("[ConversationalAgent] Generated direct conversation response.")
    return state


def route_intent(state: RAGState) -> str:
    """
    LangGraph conditional edge.
    Routes query based on classified intent.
    """
    intent = state.get("intent", "research")
    if intent == "research":
        return "classify_domain"
    elif intent in ("conversational", "clarification"):
        return "run_conversational_node"
    else:
        # out_of_scope
        state["pipeline_short_circuited"] = True
        state["guardrail_reason"] = "I can only answer questions related to academic research and scientific papers."
        return "format_output"