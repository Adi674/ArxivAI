"""
src/worker/eval_tasks.py

Weekly/scheduled background task that evaluates search quality on a sample of
recent queries. Uses a judge LLM to label retrieved paper chunks as relevant/irrelevant,
computes Precision@5, Recall@5, MRR, and NDCG@5, and reports them to Prometheus.
"""

import json
import logging
import asyncio
from sqlalchemy import select
from typing import Optional, Any

from src.database import get_async_session_maker
from src.models import SessionState
from src.llm.provider import get_llm, call_llm
from src.llm.prompts import RELEVANCE_JUDGE_PROMPT
from src.eval.retrieval_metrics import calculate_retrieval_metrics
from src.eval.prometheus_metrics import (
    RETRIEVAL_PRECISION_AT_5,
    RETRIEVAL_RECALL_AT_5,
    RETRIEVAL_MRR,
    RETRIEVAL_NDCG_AT_5,
)

logger = logging.getLogger(__name__)


def _parse_indexes(text: str) -> list[int]:
    """Parse list of indexes from judge JSON output."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return []
        data = json.loads(text[start:end])
        return [int(idx) for idx in data.get("relevant_indexes", [])]
    except Exception as e:
        logger.warning(f"[EvalTask] Failed to parse relevance index output: {e}. Raw: {text[:200]}")
        return []


async def evaluate_recent_queries(sample_size: int = 10) -> dict[str, Any]:
    """
    Sample recent queries, judge chunk relevance, compute IR metrics, and update Prometheus.
    This function can be triggered as a weekly scheduled cron task.
    """
    logger.info(f"[EvalTask] Starting retrieval quality evaluation task (sample_size={sample_size})")
    session_maker = get_async_session_maker()
    
    # 1. Fetch recent completed sessions
    async with session_maker() as db:
        stmt = (
            select(SessionState)
            .where(SessionState.completed_at.isnot(None))
            .order_by(SessionState.created_at.desc())
            .limit(sample_size)
        )
        result = await db.execute(stmt)
        sessions = result.scalars().all()
        
    if not sessions:
        logger.warning("[EvalTask] No completed query sessions found to evaluate.")
        return {"status": "no_data"}

    llm = get_llm("evaluator", "balanced")
    
    metrics_by_domain: dict[str, list[dict[str, float]]] = {}
    
    for session in sessions:
        query = session.original_query
        domain = session.primary_domain or "General"
        retrieved = session.retrieved_papers  # list of dicts from state
        
        if not retrieved or not isinstance(retrieved, list):
            continue
            
        # Format the retrieved chunks for the LLM judge
        chunks_str = ""
        for idx, doc in enumerate(retrieved[:5]):
            title = doc.get("title", "Unknown Paper")
            authors = doc.get("authors", "Unknown Authors")
            content = doc.get("content", "")[:350]
            chunks_str += f"[{idx}] Paper: {title} by {authors}\n    Content: {content}\n\n"
            
        # Ask LLM judge which chunks are actually relevant
        prompt = RELEVANCE_JUDGE_PROMPT.format(query=query, chunks=chunks_str)
        try:
            raw_response = call_llm(llm, prompt)
            relevant_indexes = _parse_indexes(raw_response)
        except Exception as e:
            logger.error(f"[EvalTask] LLM judge call failed for session {session.id}: {e}")
            continue

        # We construct list of retrieved chunk identifiers
        # Key: (paper_id, chunk_index)
        retrieved_ids = [f"{doc.get('paper_id')}_{doc.get('chunk_index')}" for doc in retrieved[:5]]
        
        # Relevant chunk IDs based on judge index predictions
        relevant_ids = [
            retrieved_ids[idx] for idx in relevant_indexes if idx < len(retrieved_ids)
        ]
        
        # Compute metrics
        stats = calculate_retrieval_metrics(retrieved_ids, relevant_ids, k=5)
        metrics_by_domain.setdefault(domain, []).append(stats)
        
        logger.debug(
            f"[EvalTask] Query: '{query[:40]}...' | "
            f"Precision@5: {stats['precision_at_k']} | MRR: {stats['mrr']}"
        )

    # 3. Aggregate metrics per domain and publish to Prometheus
    aggregated_results: dict[str, Any] = {}
    for domain, score_list in metrics_by_domain.items():
        if not score_list:
            continue
        avg_precision = sum(s["precision_at_k"] for s in score_list) / len(score_list)
        avg_recall = sum(s["recall_at_k"] for s in score_list) / len(score_list)
        avg_mrr = sum(s["mrr"] for s in score_list) / len(score_list)
        avg_ndcg = sum(s["ndcg_at_k"] for s in score_list) / len(score_list)
        
        # Push to Prometheus metrics
        RETRIEVAL_PRECISION_AT_5.labels(domain=domain).set(avg_precision)
        RETRIEVAL_RECALL_AT_5.labels(domain=domain).set(avg_recall)
        RETRIEVAL_MRR.labels(domain=domain).set(avg_mrr)
        RETRIEVAL_NDCG_AT_5.labels(domain=domain).set(avg_ndcg)
        
        aggregated_results[domain] = {
            "queries_evaluated": len(score_list),
            "precision_at_5": round(avg_precision, 4),
            "recall_at_5": round(avg_recall, 4),
            "mrr": round(avg_mrr, 4),
            "ndcg_at_5": round(avg_ndcg, 4),
        }
        
        logger.info(
            f"[EvalTask] Domain: {domain} aggregated: "
            f"P@5={avg_precision:.4f}, Recall@5={avg_recall:.4f}, MRR={avg_mrr:.4f}, NDCG@5={avg_ndcg:.4f}"
        )

    return {"status": "success", "results": aggregated_results}
