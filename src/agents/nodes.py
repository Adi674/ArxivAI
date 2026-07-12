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
    Retrieve papers using the search tool chosen by Agent 3.
    Dispatches to semantic_search, keyword_search, or hybrid_search.
    Reformulates query if avg relevance < 0.6 (max 2 times).
    """
    from src.vectordb.searcher import semantic_search, keyword_search, hybrid_search, calculate_avg_relevance

    # Dispatch to the correct search tool
    _SEARCH_TOOLS = {
        "semantic": semantic_search,
        "keyword": keyword_search,
        "hybrid": hybrid_search,
    }
    tool_name = state.get("search_tool", "hybrid")
    search_fn = _SEARCH_TOOLS.get(tool_name, hybrid_search)
    logger.info(f"Using search tool: {tool_name}")

    query = state["original_query"]
    results = await search_fn(
        query=query,
        user_id=state["user_id"],
        domain=state["primary_domain"],
        k=10,
        collab_ids=state["collab_ids"],
    )

    avg = calculate_avg_relevance(results)
    logger.info(f"Initial retrieval: {len(results)} results, avg relevance={avg}")

    # Reformulate if low relevance (max 2 times) — always escalate to hybrid on retry
    if avg < 0.6 and state["reformulation_count"] < 2:
        llm = get_llm("retriever", state["llm_mode"])
        prompt = QUERY_REFORMULATE_PROMPT.format(
            query=query,
            domain=state["primary_domain"],
            score=avg,
        )
        new_query = call_llm(llm, prompt).strip()
        logger.info(f"Reformulated query: {new_query}")

        # Always use hybrid on retry for maximum recall
        results = await hybrid_search(
            query=new_query,
            user_id=state["user_id"],
            domain=state["primary_domain"],
            k=10,
            collab_ids=state["collab_ids"],
        )
        state["reformulation_count"] += 1
        state["reasoning_trace"].append(
            f"[Retriever] Reformulated query (attempt {state['reformulation_count']}): {new_query[:80]}"
        )

    state["retrieved_papers"] = results
    state["reasoning_trace"].append(
        f"[Retriever] tool={tool_name} → {len(results)} papers retrieved, "
        f"avg relevance={calculate_avg_relevance(results)}"
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

def evaluate_answer(state: RAGState) -> RAGState:
    """
    Run quality checks on the draft answer.
    Sets needs_refinement=True if quality < 0.7 and refinement_count < 3.
    """
    llm = get_llm("evaluator", state["llm_mode"])

    papers_summary = "\n".join(
        f"- {p.get('title', p['paper_id'])}: {p.get('content', '')[:300]}"
        for p in state["retrieved_papers"][:5]
    )

    # Hallucination check
    hallucination_prompt = HALLUCINATION_CHECK_PROMPT.format(
        answer=state["draft_answer"],
        papers=papers_summary,
    )
    hall_raw = call_llm(llm, hallucination_prompt)
    hall_result = _parse_json(hall_raw, {"hallucination_detected": False, "unsupported_claims": []})

    # Quality/completeness check
    quality_prompt = COMPLETENESS_CHECK_PROMPT.format(
        query=state["original_query"],
        answer=state["draft_answer"],
    )
    quality_raw = call_llm(llm, quality_prompt)
    quality_result = _parse_json(quality_raw, {
        "faithfulness": 0.7,
        "completeness": 0.7,
        "relevance": 0.7,
        "citation_accuracy": 0.7,
        "overall": 0.7,
        "feedback": "",
    })

    state["hallucination_detected"] = bool(hall_result.get("hallucination_detected", False))
    state["ragas_scores"] = {
        "faithfulness": quality_result.get("faithfulness", 0.7),
        "completeness": quality_result.get("completeness", 0.7),
        "relevance": quality_result.get("relevance", 0.7),
        "citation_accuracy": quality_result.get("citation_accuracy", 0.7),
    }
    state["quality_score"] = float(quality_result.get("overall", 0.7))
    state["evaluator_feedback"] = quality_result.get("feedback", "")

    should_refine = (
        state["quality_score"] < 0.7
        and state["refinement_count"] < 3
        and not state["hallucination_detected"]
    )
    state["needs_refinement"] = should_refine
    state["refinement_count"] += 1

    state["reasoning_trace"].append(
        f"[Evaluator] → quality={state['quality_score']}, hallucination={state['hallucination_detected']}, refine={state['needs_refinement']}"
    )
    logger.info(f"Quality score: {state['quality_score']}, needs_refinement: {state['needs_refinement']}")
    return state


def should_refine(state: RAGState) -> str:
    """
    LangGraph conditional edge.
    Routes back to synthesis if quality is poor, else to format output.
    """
    if state["needs_refinement"] and state["refinement_count"] < 3:
        return "synthesis"
    return "format_output"


# ─────────────────────────────────────────────────────────────
# FORMAT OUTPUT (terminal node)
# ─────────────────────────────────────────────────────────────

def format_output(state: RAGState) -> RAGState:
    """
    Finalize answer and build sources list for the API response.
    """
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