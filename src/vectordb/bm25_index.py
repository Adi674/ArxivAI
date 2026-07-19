"""
src/vectordb/bm25_index.py

In-memory BM25 index built from paper_chunks stored in Supabase pgvector.
Uses rank_bm25 (BM25Okapi implementation) — no new service required.

Lifecycle:
  - Built once at FastAPI startup via build()
  - Held in module-level singleton (_index, _corpus)
  - Invalidated + rebuilt whenever new papers are ingested (call invalidate())
  - search() returns ranked (chunk_dict, bm25_score) pairs

Design decisions:
  - Tokenisation: lowercase + split on non-alphanumeric chars (no stopword removal —
    academic terms like "of", "in" can be meaningful in paper titles)
  - BM25Okapi: k1=1.5, b=0.75 — standard defaults, well-calibrated for academic text
  - Scores are normalised to [0, 1] by dividing by the max score in the result set
  - Thread-safe read — asyncio.Lock guards the build/invalidate cycle
"""

import asyncio
import logging
import re
from typing import Optional

from rank_bm25 import BM25Okapi
from sqlalchemy import text

from src.database import get_async_session_maker

logger = logging.getLogger(__name__)

# ─── Module-level singletons ─────────────────────────────────────────────────
_index: Optional[BM25Okapi] = None          # BM25 index object
_corpus: list[dict] = []                    # parallel list of chunk dicts
_build_lock = asyncio.Lock()               # prevents concurrent rebuilds
_is_built: bool = False


def _tokenize(text_: str) -> list[str]:
    """
    Simple whitespace + punctuation tokeniser for BM25.
    Lowercases everything, splits on non-alphanumeric characters.
    Keeps tokens of length >= 2.
    """
    tokens = re.split(r"[^a-zA-Z0-9]+", text_.lower())
    return [t for t in tokens if len(t) >= 2]


async def build() -> None:
    """
    Load all paper chunks from Supabase and build the in-memory BM25 index.
    Skips rebuild if already built (idempotent). Force a fresh build by calling
    invalidate() first.

    Called at FastAPI startup (in main.py lifespan) and after any ingestion run.
    """
    global _index, _corpus, _is_built

    async with _build_lock:
        if _is_built:
            logger.info("[BM25Index] Already built — skipping rebuild.")
            return

        logger.info("[BM25Index] Loading chunks from Supabase for BM25 index build…")

        sql = text("""
            SELECT pc.paper_id, pc.content, pc.chunk_index,
                   p.title, p.authors, p.domain, p.source,
                   p.visibility, p.pdf_url
            FROM paper_chunks pc
            JOIN papers p ON pc.paper_id = p.id
            WHERE p.deleted_at IS NULL
              AND p.visibility = 'public'
            ORDER BY pc.paper_id, pc.chunk_index
        """)

        session_maker = get_async_session_maker()
        rows = []
        async with session_maker() as db:
            result = await db.execute(sql)
            rows = result.all()

        if not rows:
            logger.warning("[BM25Index] No chunks found — BM25 index will be empty.")
            _corpus = []
            _index = BM25Okapi([[]])     # empty index
            _is_built = True
            return

        # Build the corpus: concatenate title + content for richer BM25 matching
        tokenized_corpus: list[list[str]] = []
        new_corpus: list[dict] = []

        for row in rows:
            combined_text = f"{row.title or ''} {row.authors or ''} {row.content or ''}"
            tokens = _tokenize(combined_text)
            tokenized_corpus.append(tokens)
            new_corpus.append({
                "paper_id": row.paper_id,
                "content": row.content,
                "chunk_index": row.chunk_index,
                "title": row.title,
                "authors": row.authors,
                "domain": row.domain,
                "source": row.source,
                "visibility": row.visibility,
                "pdf_url": getattr(row, "pdf_url", None),
            })

        _corpus = new_corpus
        _index = BM25Okapi(tokenized_corpus, k1=1.5, b=0.75)
        _is_built = True

        logger.info(
            f"[BM25Index] Built: {len(_corpus)} chunks from Supabase. "
            f"Approx RAM: {len(_corpus) * 1500 // (1024 * 1024)}MB"
        )


def invalidate() -> None:
    """
    Mark the BM25 index as stale. Next call to build() will reload from DB.
    Call this after any ingestion run completes.
    """
    global _is_built
    _is_built = False
    logger.info("[BM25Index] Index invalidated — will rebuild on next request.")


def search(query: str, k: int = 20) -> list[dict]:
    """
    Search the in-memory BM25 index.

    Returns up to k results, each dict containing:
        paper_id, title, authors, domain, content, chunk_index,
        bm25_score (raw), relevance_score (normalised 0–1), search_lane="bm25"

    Returns [] if the index has not been built yet (safe — hybrid_search_v2
    handles empty BM25 results gracefully by falling back to semantic results).
    """
    global _index, _corpus

    if _index is None or not _corpus:
        logger.warning("[BM25Index] Index not built yet — returning empty BM25 results.")
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    raw_scores: list[float] = _index.get_scores(tokens).tolist()

    # Get top-k indices sorted by score descending
    indexed_scores = sorted(enumerate(raw_scores), key=lambda x: x[1], reverse=True)
    top_k = indexed_scores[:k]

    # Filter zero-score results (no BM25 match at all)
    top_k = [(idx, score) for idx, score in top_k if score > 0.0]

    if not top_k:
        return []

    # Normalise scores to [0, 1] relative to max in this result set
    max_score = top_k[0][1]

    results: list[dict] = []
    for idx, raw_score in top_k:
        chunk = _corpus[idx]
        normalised = round(raw_score / max_score, 4) if max_score > 0 else 0.0
        results.append({
            **chunk,
            "bm25_score": round(raw_score, 6),
            "relevance_score": normalised,
            "search_lane": "bm25",
        })

    logger.debug(f"[BM25Index] {len(results)} BM25 matches for '{query[:60]}'")
    return results


def is_built() -> bool:
    """Return True if the index is ready for queries."""
    return _is_built
