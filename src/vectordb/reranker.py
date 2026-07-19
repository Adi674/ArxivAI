"""
src/vectordb/reranker.py

Cross-encoder reranker using sentence-transformers.
Model: cross-encoder/ms-marco-MiniLM-L-6-v2

Design:
  - Lazy-loaded on first use — no startup cost if reranker is never called
  - Singleton pattern — model loaded only once for the process lifetime
  - CPU inference only — no GPU required (~14MB model, ~150ms for 40 pairs)
  - Input:  query string + list of candidate chunk dicts (from RRF merge)
  - Output: same dicts, re-ordered by cross-encoder relevance score (desc)
            with `rerank_score` field added to each dict

The cross-encoder reads (query, passage) jointly — it attends across both
strings simultaneously, giving far more accurate relevance judgement than
embedding cosine similarity which encodes query and passage independently.

Typical usage:
    top_k = reranker.rerank(query="transformer attention", docs=rrf_merged, top_k=5)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Singleton state ─────────────────────────────────────────────────────────
_model = None
_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_model():
    """Lazy-load the cross-encoder model on first call."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"[Reranker] Loading cross-encoder model: {_MODEL_NAME}")
            _model = CrossEncoder(_MODEL_NAME, max_length=512)
            logger.info("[Reranker] Cross-encoder model loaded successfully.")
        except ImportError:
            logger.error(
                "[Reranker] sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
            raise
        except Exception as e:
            logger.error(f"[Reranker] Failed to load model: {e}")
            raise
    return _model


def rerank(
    query: str,
    docs: list[dict],
    top_k: int = 5,
    content_field: str = "content",
    title_field: str = "title",
) -> list[dict]:
    """
    Rerank a list of candidate documents using the cross-encoder.

    Each document is scored based on joint encoding of (query, passage_text)
    where passage_text = title + content (first 400 chars of content).

    Args:
        query:         The user's original or reformulated search query.
        docs:          List of chunk dicts from RRF merge step.
        top_k:         Number of top results to return after reranking.
        content_field: Key in each dict containing the passage text.
        title_field:   Key in each dict containing the paper title.

    Returns:
        Top-k dicts sorted by rerank_score DESC, with `rerank_score` field added.
        If the model fails or docs is empty, returns original docs[:top_k] unchanged.
    """
    if not docs:
        return []

    if len(docs) <= top_k:
        # Not enough docs to meaningfully rerank — still run it to add rerank_score
        pass

    try:
        model = _get_model()

        # Build (query, passage) pairs for the cross-encoder
        # Concatenate title + first 400 chars of content for richer context
        pairs: list[tuple[str, str]] = []
        for doc in docs:
            title = doc.get(title_field) or ""
            content = doc.get(content_field) or ""
            passage = f"{title}. {content[:400]}".strip()
            pairs.append((query, passage))

        # Score all pairs in one forward pass
        scores: list[float] = model.predict(pairs).tolist()

        # Attach score to each doc
        for doc, score in zip(docs, scores):
            doc["rerank_score"] = round(float(score), 6)

        # Sort by rerank_score descending
        docs.sort(key=lambda d: d["rerank_score"], reverse=True)

        # Normalise rerank scores to [0, 1] range for consistent downstream use
        # Cross-encoder outputs logits (unbounded) — normalise relative to max
        if docs:
            max_score = docs[0]["rerank_score"]
            min_score = docs[-1]["rerank_score"]
            score_range = max_score - min_score if max_score != min_score else 1.0
            for doc in docs:
                doc["relevance_score"] = round(
                    (doc["rerank_score"] - min_score) / score_range, 4
                )

        top = docs[:top_k]
        logger.debug(
            f"[Reranker] Reranked {len(docs)} docs → top {len(top)} "
            f"(scores: {[d['rerank_score'] for d in top]})"
        )
        return top

    except Exception as e:
        logger.error(f"[Reranker] Reranking failed: {e}. Returning original order.")
        # Graceful fallback — return original docs without reranking
        for doc in docs:
            doc.setdefault("rerank_score", doc.get("relevance_score", 0.0))
        return docs[:top_k]
