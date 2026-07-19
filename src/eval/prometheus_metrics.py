"""
src/eval/prometheus_metrics.py

Defines system-wide Prometheus metrics for RAG quality, cache performance,
hallucination rates, and LLM reliability. Imported by main.py and other services.
"""

from prometheus_client import Counter, Histogram, Gauge

# ── Retrieval Quality Metrics ────────────────────────────────────────────────
RETRIEVAL_PRECISION_AT_5 = Gauge(
    "retrieval_precision_at5",
    "Precision at 5 of search retrieval lane (evaluated by LLM judge or feedback)",
    ["domain"]
)

RETRIEVAL_RECALL_AT_5 = Gauge(
    "retrieval_recall_at5",
    "Recall at 5 of search retrieval lane",
    ["domain"]
)

RETRIEVAL_MRR = Gauge(
    "retrieval_mrr",
    "Mean Reciprocal Rank of search retrieval lane",
    ["domain"]
)

RETRIEVAL_NDCG_AT_5 = Gauge(
    "retrieval_ndcg_at5",
    "Normalized Discounted Cumulative Gain at 5 of search retrieval lane",
    ["domain"]
)

# ── Hallucination & Answer Quality ───────────────────────────────────────────
HALLUCINATION_RATE_HIST = Histogram(
    "hallucination_rate_ratio",
    "NLI sentence-level hallucination rate ratio",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

EVAL_SCORE_HIST = Histogram(
    "eval_score_overall",
    "Weighted overall RAG answer quality score (from 7-metric judge)",
    buckets=[0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# ── System Cache & Fallbacks ─────────────────────────────────────────────────
CACHE_HITS_TOTAL = Counter(
    "cache_hits_total",
    "Total semantic cache hits"
)

CACHE_MISSES_TOTAL = Counter(
    "cache_misses_total",
    "Total semantic cache misses"
)

ARXIV_FALLBACK_TOTAL = Counter(
    "arxiv_fallback_total",
    "Total arXiv live fetch fallback events triggered"
)

# ── Guardrails & Intents ─────────────────────────────────────────────────────
GUARDRAIL_BLOCKS_TOTAL = Counter(
    "guardrail_blocks_total",
    "Total input or output guardrail safety blocks",
    ["guardrail_type", "reason"]
)

INTENT_CLASSIFICATION_TOTAL = Counter(
    "intent_classification_total",
    "Total user queries classified by intent",
    ["intent"]
)

# ── LLM Service Reliability ──────────────────────────────────────────────────
CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "State of LLM provider circuit breakers (0=closed, 1=half-open, 2=open)",
    ["provider"]
)
