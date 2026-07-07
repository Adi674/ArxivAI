import logging
from functools import lru_cache
from langgraph.graph import StateGraph, END

from src.agents.state import RAGState
from src.agents.nodes import (
    classify_domain,
    analyze_query,
    decide_search_strategy,
    retrieve_papers,
    reason_over_papers,
    synthesize_answer,
    evaluate_answer,
    format_output,
    should_refine,
)

logger = logging.getLogger(__name__)


def build_graph():
    """
    Build and compile the LangGraph StateGraph.

    Flow:
      classify_domain
        → analyze_query
          → decide_search_strategy
            → retrieve_papers
              → reason_over_papers
                → synthesize_answer
                  → evaluate_answer
                    → [should_refine?]
                        YES → synthesize_answer (max 3 loops)
                        NO  → format_output → END
    """
    graph = StateGraph(RAGState)

    # Register all nodes
    graph.add_node("classify_domain", classify_domain)
    graph.add_node("analyze_query", analyze_query)
    graph.add_node("decide_search_strategy", decide_search_strategy)
    graph.add_node("retrieve_papers", retrieve_papers)
    graph.add_node("reason_over_papers", reason_over_papers)
    graph.add_node("synthesis", synthesize_answer)
    graph.add_node("evaluate_answer", evaluate_answer)
    graph.add_node("format_output", format_output)

    # Sequential edges
    graph.set_entry_point("classify_domain")
    graph.add_edge("classify_domain", "analyze_query")
    graph.add_edge("analyze_query", "decide_search_strategy")
    graph.add_edge("decide_search_strategy", "retrieve_papers")
    graph.add_edge("retrieve_papers", "reason_over_papers")
    graph.add_edge("reason_over_papers", "synthesis")
    graph.add_edge("synthesis", "evaluate_answer")

    # Conditional edge: refine or finish
    graph.add_conditional_edges(
        "evaluate_answer",
        should_refine,
        {
            "synthesis": "synthesis",
            "format_output": "format_output",
        }
    )

    graph.add_edge("format_output", END)

    compiled = graph.compile()
    logger.info("LangGraph pipeline compiled successfully")
    return compiled


@lru_cache(maxsize=1)
def get_compiled_graph():
    """Cached singleton — compiled once at startup."""
    return build_graph()