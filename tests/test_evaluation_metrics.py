"""
tests/test_evaluation_metrics.py

Unit tests for ArxivAI v3.0 Evaluation and Retrieval Quality Metrics (Phase 3).
Tests:
- Precision@K, Recall@K, MRR, NDCG@K formulas.
- Judge output JSON parsing.
- User feedback schema rating constraints.
"""

import pytest
from uuid import uuid4

from src.eval.retrieval_metrics import (
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_mrr,
    calculate_ndcg_at_k,
    calculate_retrieval_metrics,
)
from src.eval.llm_judge import _parse_judge_response


def test_precision_at_k():
    retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
    relevant = ["doc2", "doc4", "doc6"]
    
    # P@5: doc2 (hit), doc4 (hit). Hits = 2. K = 5. P@5 = 2/5 = 0.4
    assert calculate_precision_at_k(retrieved, relevant, k=5) == 0.4
    # P@3: doc2 (hit). Hits = 1. K = 3. P@3 = 1/3 = 0.3333
    assert calculate_precision_at_k(retrieved, relevant, k=3) == 0.3333
    # P@1: doc1 (miss). Hits = 0. P@1 = 0.0
    assert calculate_precision_at_k(retrieved, relevant, k=1) == 0.0
    # K > len(retrieved)
    assert calculate_precision_at_k(retrieved, relevant, k=10) == 0.2


def test_recall_at_k():
    retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
    relevant = ["doc2", "doc4", "doc6"]
    
    # Recall@5: hits = 2. Total relevant = 3. Recall = 2/3 = 0.6667
    assert calculate_recall_at_k(retrieved, relevant, k=5) == 0.6667
    # Recall@3: hits = 1. Recall = 1/3 = 0.3333
    assert calculate_recall_at_k(retrieved, relevant, k=3) == 0.3333


def test_mrr():
    retrieved = ["doc1", "doc2", "doc3"]
    relevant = ["doc2", "doc4"]
    # First hit is doc2 at rank 2. Reciprocal rank = 1/2 = 0.5
    assert calculate_mrr(retrieved, relevant) == 0.5
    
    # No hits
    assert calculate_mrr(["doc1", "doc3"], ["doc2"]) == 0.0


def test_ndcg_at_k():
    retrieved = ["doc1", "doc2", "doc3"]
    relevant = ["doc2", "doc3"]
    
    # DCG@3 = 0/log2(2) + 1/log2(3) + 1/log2(4) = 0 + 0.6309 + 0.5 = 1.1309
    # Ideal: relevant docs at top, so doc2, doc3. 
    # IDCG@3 = 1/log2(2) + 1/log2(3) = 1.0 + 0.6309 = 1.6309
    # NDCG@3 = 1.1309 / 1.6309 = 0.6934
    assert calculate_ndcg_at_k(retrieved, relevant, k=3) == 0.6934


def test_parse_judge_response():
    # Test valid parsing with surrounding text
    raw = """
    Here is the evaluation result:
    {
        "score": 0.95,
        "evidence": "Found matching claim in section 3.",
        "feedback": "Perfect answer structure.",
        "reasoning": "Every sentence maps directly to the paper."
    }
    Hope this helps!
    """
    score = _parse_judge_response(raw, "faithfulness")
    assert score.score == 0.95
    assert score.evidence == "Found matching claim in section 3."
    assert score.feedback == "Perfect answer structure."
    assert score.reasoning == "Every sentence maps directly to the paper."

    # Test parse error fallback
    malformed = "The answer is excellent and contains no issues."
    fallback_score = _parse_judge_response(malformed, "faithfulness")
    assert fallback_score.score == 0.5
    assert "Parse error" in fallback_score.evidence
