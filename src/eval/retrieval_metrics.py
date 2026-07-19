"""
src/eval/retrieval_metrics.py

Calculates standard Information Retrieval (IR) metrics to evaluate search quality:
- Precision@K
- Recall@K
- Mean Reciprocal Rank (MRR)
- Normalized Discounted Cumulative Gain (NDCG@K)

These metrics evaluate the quality of retriever outputs against ground truth (relevant) paper IDs.
"""

import math
from typing import Sequence


def calculate_precision_at_k(retrieved_ids: Sequence[str], relevant_ids: Sequence[str], k: int = 5) -> float:
    """
    Precision@K is the fraction of retrieved documents that are relevant.
    P@K = (number of relevant documents in top K) / K
    """
    if k <= 0:
        return 0.0
    
    # Truncate to K
    retrieved_k = retrieved_ids[:k]
    if not retrieved_k:
        return 0.0
    
    relevant_set = set(relevant_ids)
    hits = sum(1 for rid in retrieved_k if rid in relevant_set)
    return round(hits / k, 4)


def calculate_recall_at_k(retrieved_ids: Sequence[str], relevant_ids: Sequence[str], k: int = 5) -> float:
    """
    Recall@K is the fraction of relevant documents that are retrieved.
    Recall@K = (number of relevant documents in top K) / (total number of relevant documents)
    """
    if not relevant_ids:
        return 0.0
    
    retrieved_k = retrieved_ids[:k]
    relevant_set = set(relevant_ids)
    hits = sum(1 for rid in retrieved_k if rid in relevant_set)
    return round(hits / len(relevant_ids), 4)


def calculate_mrr(retrieved_ids: Sequence[str], relevant_ids: Sequence[str]) -> float:
    """
    Mean Reciprocal Rank (MRR) calculates the reciprocal rank of the first relevant document.
    MRR = 1 / rank of first relevant doc (or 0.0 if none found)
    """
    relevant_set = set(relevant_ids)
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_set:
            return round(1.0 / rank, 4)
    return 0.0


def calculate_ndcg_at_k(retrieved_ids: Sequence[str], relevant_ids: Sequence[str], k: int = 5) -> float:
    """
    Normalized Discounted Cumulative Gain (NDCG@K) measures performance relative to ideal ordering.
    Binary relevance is assumed (1 for relevant, 0 for irrelevant).
    """
    if k <= 0:
        return 0.0
        
    retrieved_k = retrieved_ids[:k]
    if not retrieved_k:
        return 0.0
        
    relevant_set = set(relevant_ids)
    
    # Compute DCG@K
    dcg = 0.0
    for rank, rid in enumerate(retrieved_k, start=1):
        if rid in relevant_set:
            dcg += 1.0 / math.log2(rank + 1)
            
    # Compute IDCG@K (Ideal DCG where all relevant documents are placed at the top)
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    
    if idcg == 0.0:
        return 0.0
        
    return round(dcg / idcg, 4)


def calculate_retrieval_metrics(
    retrieved_ids: Sequence[str],
    relevant_ids: Sequence[str],
    k: int = 5
) -> dict[str, float]:
    """
    Compute Precision@K, Recall@K, MRR, and NDCG@K for a set of retrieved and relevant documents.
    """
    return {
        "precision_at_k": calculate_precision_at_k(retrieved_ids, relevant_ids, k),
        "recall_at_k": calculate_recall_at_k(retrieved_ids, relevant_ids, k),
        "mrr": calculate_mrr(retrieved_ids, relevant_ids),
        "ndcg_at_k": calculate_ndcg_at_k(retrieved_ids, relevant_ids, k),
    }
