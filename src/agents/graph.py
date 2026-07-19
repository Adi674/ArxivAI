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
    gate_input,
    gate_output,
    check_input_guardrail,
    classify_intent_node,
    run_conversational_node,
    route_intent,
)

logger = logging.getLogger(__name__)


def build_graph():
    """
    Build and compile the LangGraph StateGraph.

    Flow with Safety Guardrails & Intent Routing:
      gate_input (Agent 0)
        ├─ check_input_guardrail?
        │    ├─ BLOCKED → format_output (short-circuited)
        │    └─ ALLOWED → classify_intent_node (Agent 1)
        │                   ├─ research       → classify_domain (full RAG)
        │                   ├─ conversational → run_conversational_node (Agent 9)
        │                   └─ out_of_scope   → format_output (polite decline)
        │
      (Conversational Path)
        run_conversational_node ──► gate_output ──► format_output ──► END
        
      (Research RAG Path)
        classify_domain → analyze_query → decide_search_strategy → retrieve_papers
          → reason_over_papers → synthesis → evaluate_answer
              ├─ YES (refine) → synthesis (loop)
              └─ NO (done)    → gate_output (Agent 8) ──► format_output ──► END
    """
    graph = StateGraph(RAGState)

    # Register all nodes
    graph.add_node("gate_input", gate_input)
    graph.add_node("classify_intent_node", classify_intent_node)
    graph.add_node("run_conversational_node", run_conversational_node)
    graph.add_node("classify_domain", classify_domain)
    graph.add_node("analyze_query", analyze_query)
    graph.add_node("decide_search_strategy", decide_search_strategy)
    graph.add_node("retrieve_papers", retrieve_papers)
    graph.add_node("reason_over_papers", reason_over_papers)
    graph.add_node("synthesis", synthesize_answer)
    graph.add_node("gate_output", gate_output)
    graph.add_node("format_output", format_output)

    # 1. Entry safety gate conditional routing
    graph.set_entry_point("gate_input")
    graph.add_conditional_edges(
        "gate_input",
        check_input_guardrail,
        {
            "classify_intent_node": "classify_intent_node",
            "format_output": "format_output",
        }
    )

    # 2. Intent classifier conditional routing
    graph.add_conditional_edges(
        "classify_intent_node",
        route_intent,
        {
            "classify_domain": "classify_domain",
            "run_conversational_node": "run_conversational_node",
            "format_output": "format_output",
        }
    )

    # 3. Conversational node exit flow
    graph.add_edge("run_conversational_node", "gate_output")

    # 4. Research RAG pipeline sequential flow
    graph.add_edge("classify_domain", "analyze_query")
    graph.add_edge("analyze_query", "decide_search_strategy")
    graph.add_edge("decide_search_strategy", "retrieve_papers")
    graph.add_edge("retrieve_papers", "reason_over_papers")
    graph.add_edge("reason_over_papers", "synthesis")
    graph.add_edge("synthesis", "gate_output")

    # 6. Output safety gate to final formatting
    graph.add_edge("gate_output", "format_output")
    graph.add_edge("format_output", END)

    compiled = graph.compile()
    logger.info("LangGraph pipeline with guardrails & intent routing compiled successfully")
    return compiled


@lru_cache(maxsize=1)
def get_compiled_graph():
    """Cached singleton — compiled once at startup."""
    return build_graph()