import logging
import asyncio
import re
from typing import Optional
from sqlalchemy import text

from src.database import get_async_session_maker
from src.vectordb.chroma_client import get_embedding_model

logger = logging.getLogger(__name__)


def calculate_avg_relevance(results: list[dict]) -> float:
    """
    Average relevance score across results.
    Used by Retriever agent to decide if reformulation is needed.
    """
    if not results:
        return 0.0
    return round(sum(r["relevance_score"] for r in results) / len(results), 4)


async def semantic_search(
    query: str,
    user_id: str,
    domain: Optional[str] = None,
    k: int = 10,
    collab_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Pure vector similarity search using AWS Bedrock Titan V2 embeddings.
    Best for: conceptual questions, "what is X", "explain Y".

    Args:
        query: The search query string.
        user_id: The requesting user's ID (for access control).
        domain: Optional domain hint (NOT used as hard filter).
        k: Number of results to return.
        collab_ids: List of collaboration IDs the user belongs to.

    Returns:
        List of dicts with paper_id, title, content, relevance_score, etc.
    """
    try:
        embeddings_model = get_embedding_model()
        query_vector = await embeddings_model.aembed_query(query)
        query_vector_str = f"[{','.join(map(str, query_vector))}]"

        access_clause = "p.visibility = 'public' OR p.user_id = CAST(:user_id AS uuid)"
        params = {
            "user_id": str(user_id),
            "query_embedding": query_vector_str,
            "limit": k,
        }

        if collab_ids and len(collab_ids) > 0:
            collab_tuples = tuple(str(cid) for cid in collab_ids)
            access_clause += (
                " OR (p.visibility = 'collaborative' AND p.id IN "
                "(SELECT paper_id FROM collaboration_papers WHERE collaboration_id IN :collab_ids))"
            )
            params["collab_ids"] = collab_tuples

        query_str = f"""
            SELECT pc.paper_id, pc.content, pc.chunk_index,
                   (pc.embedding <=> CAST(:query_embedding AS vector)) AS distance,
                   p.title, p.authors, p.domain, p.source, p.visibility, p.pdf_url
            FROM paper_chunks pc
            JOIN papers p ON pc.paper_id = p.id
            WHERE p.deleted_at IS NULL
              AND ({access_clause})
            ORDER BY distance ASC
            LIMIT :limit
        """

        session_maker = get_async_session_maker()
        formatted = []

        async with session_maker() as db:
            result = await db.execute(text(query_str), params)
            rows = result.all()

        for row in rows:
            distance = float(row.distance)
            relevance_score = max(0.0, min(1.0, 1.0 - distance))
            formatted.append({
                "paper_id": row.paper_id,
                "title": row.title,
                "authors": row.authors,
                "domain": row.domain,
                "content": row.content,
                "relevance_score": round(relevance_score, 4),
                "source": row.source,
                "visibility": row.visibility,
                "pdf_url": getattr(row, "pdf_url", None),
                "chunk_index": row.chunk_index,
                "search_lane": "semantic",
            })

        logger.info(f"[semantic_search] {len(formatted)} results for: '{query[:60]}...'")
        return formatted

    except Exception as e:
        logger.error(f"semantic_search failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


# Filler words that users type but that aren't actual searchable entities
_FILLER_WORDS = {
    "paper", "find", "search", "show", "get", "look", "fetch", "retrieve",
    "me", "the", "a", "an", "for", "about", "on", "by", "from", "with",
    "give", "please", "want", "need", "what", "which", "tell", "id", "arxiv",
}


def _extract_keywords(query: str) -> dict:
    """
    Extract specific searchable entities from a raw user query.

    Extracts:
    - arXiv IDs (e.g. 2607.08651, arxiv:2301.12345)
    - 4-digit years (e.g. 2023, 2024)
    - Capitalized proper names (author names, model names, conference names)
    - Remaining non-filler tokens as keyword terms

    Returns a dict with:
        'arxiv_ids': list of arXiv ID strings
        'terms': list of cleaned keyword strings
        'ilike_patterns': list of (column, value) patterns to search
    """
    # Step 1: Extract arXiv IDs (e.g. "2607.08651" or "arxiv:2607.08651")
    arxiv_pattern = re.compile(r'(?:arxiv[:\s]*)?(\d{4}\.\d{4,5})', re.IGNORECASE)
    arxiv_ids = arxiv_pattern.findall(query)

    # Step 2: Extract 4-digit years
    year_pattern = re.compile(r'\b(20\d{2}|19\d{2})\b')
    years = year_pattern.findall(query)

    # Step 3: Strip filler words and collect remaining meaningful tokens
    # Keep: capitalized words (proper nouns), technical acronyms, long words
    clean_tokens = []
    for token in re.split(r'[\s,;]+', query):
        token = token.strip('()[]{}"\'.?!')
        if not token:
            continue
        if token.lower() in _FILLER_WORDS:
            continue
        if re.match(r'^\d{4}\.\d{4,5}$', token):  # already captured arXiv ID
            continue
        if len(token) >= 3:  # ignore very short tokens
            clean_tokens.append(token)

    return {
        "arxiv_ids": arxiv_ids,
        "years": years,
        "terms": clean_tokens,
    }


async def keyword_search(
    query: str,
    user_id: str,
    domain: Optional[str] = None,
    k: int = 10,
    collab_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Full-text keyword search using PostgreSQL tsvector + ILIKE fallback.

    Extracts specific searchable entities (arXiv IDs, author names, model names)
    from the raw query before searching — prevents filler words like 'paper' or
    'find' from polluting the ILIKE patterns.

    Searches across: chunk content, paper title, authors, and paper_id (p.id).

    Two-pronged approach:
      1. tsvector full-text match on content + title + authors (for natural language terms)
      2. ILIKE fallback on paper_id, title, authors for exact entity matches

    Args:
        query: The raw user query (e.g. "paper 2607.08651" or "papers by Vaswani").
        user_id: The requesting user's ID (for access control).
        domain: Optional domain hint (NOT used as hard filter).
        k: Number of results to return.
        collab_ids: List of collaboration IDs the user belongs to.

    Returns:
        List of dicts with paper_id, title, content, relevance_score, etc.
    """
    try:
        # Extract specific searchable entities from the query
        extracted = _extract_keywords(query)
        arxiv_ids = extracted["arxiv_ids"]
        terms = extracted["terms"]

        logger.info(f"[keyword_search] Extracted → arxiv_ids={arxiv_ids}, terms={terms}")

        access_clause = "p.visibility = 'public' OR p.user_id = CAST(:user_id AS uuid)"
        params: dict = {
            "user_id": str(user_id),
            "query": query,                       # for tsvector full-text
            "query_like": f"%{query}%",           # broad fallback on full query
            "limit": k,
        }

        if collab_ids and len(collab_ids) > 0:
            collab_tuples = tuple(str(cid) for cid in collab_ids)
            access_clause += (
                " OR (p.visibility = 'collaborative' AND p.id IN "
                "(SELECT paper_id FROM collaboration_papers WHERE collaboration_id IN :collab_ids))"
            )
            params["collab_ids"] = collab_tuples

        # Build ILIKE conditions for extracted entities and build CASE branches dynamically
        ilike_conditions = []
        rank_branches = []

        # arXiv IDs → search p.id directly (exact match without filler words)
        for i, arxiv_id in enumerate(arxiv_ids):
            param_key = f"arxiv_id_{i}"
            params[param_key] = f"%{arxiv_id}%"
            ilike_conditions.append(f"p.id ILIKE :{param_key}")
            rank_branches.append(f"WHEN p.id ILIKE :{param_key} THEN 1.0")

        # Meaningful terms → search title and authors
        for i, term in enumerate(terms[:5]):  # limit to first 5 terms
            param_key = f"term_{i}"
            params[param_key] = f"%{term}%"
            ilike_conditions.append(f"p.title ILIKE :{param_key}")
            ilike_conditions.append(f"p.authors ILIKE :{param_key}")
            rank_branches.append(f"WHEN p.title ILIKE :{param_key} THEN 0.8")
            rank_branches.append(f"WHEN p.authors ILIKE :{param_key} THEN 0.7")

        # Always include broad fallback on the full query text
        ilike_conditions.append("p.id ILIKE :query_like")
        ilike_conditions.append("p.title ILIKE :query_like")
        rank_branches.append("WHEN p.id ILIKE :query_like THEN 1.0")
        rank_branches.append("WHEN p.title ILIKE :query_like THEN 0.8")

        ilike_clause = " OR ".join(ilike_conditions)
        rank_case_branches = "\n                            ".join(rank_branches)

        query_str = f"""
            SELECT DISTINCT ON (pc.paper_id, pc.chunk_index)
                   pc.paper_id, pc.content, pc.chunk_index,
                   GREATEST(
                       COALESCE(
                           ts_rank(
                               to_tsvector('english',
                                   COALESCE(pc.content, '') || ' ' ||
                                   COALESCE(p.title, '') || ' ' ||
                                   COALESCE(p.authors, '')
                               ),
                               websearch_to_tsquery('english', :query)
                           ), 0
                       ),
                       CASE
                           {rank_case_branches}
                           ELSE 0.0
                       END
                   ) AS rank,
                   p.title, p.authors, p.domain, p.source, p.visibility, p.pdf_url
            FROM paper_chunks pc
            JOIN papers p ON pc.paper_id = p.id
            WHERE p.deleted_at IS NULL
              AND ({access_clause})
              AND (
                  -- Full-text tsvector match
                  to_tsvector('english',
                      COALESCE(pc.content, '') || ' ' ||
                      COALESCE(p.title, '') || ' ' ||
                      COALESCE(p.authors, '')
                  ) @@ websearch_to_tsquery('english', :query)
                  OR
                  -- Extracted entity ILIKE matches (arXiv IDs, author names, etc.)
                  ({ilike_clause})
              )
            ORDER BY pc.paper_id, pc.chunk_index, rank DESC
            LIMIT :limit
        """

        session_maker = get_async_session_maker()
        formatted = []

        async with session_maker() as db:
            result = await db.execute(text(query_str), params)
            rows = result.all()

        for row in rows:
            formatted.append({
                "paper_id": row.paper_id,
                "title": row.title,
                "authors": row.authors,
                "domain": row.domain,
                "content": row.content,
                "relevance_score": round(min(float(row.rank), 1.0), 4),
                "source": row.source,
                "visibility": row.visibility,
                "pdf_url": getattr(row, "pdf_url", None),
                "chunk_index": row.chunk_index,
                "search_lane": "keyword",
            })

        formatted.sort(key=lambda x: x["relevance_score"], reverse=True)
        logger.info(f"[keyword_search] {len(formatted)} results for: '{query[:60]}...'")
        return formatted

    except Exception as e:
        logger.error(f"keyword_search failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []



async def hybrid_search(
    query: str,
    user_id: str,
    domain: Optional[str] = None,
    k: int = 10,
    collab_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Two-lane hybrid search: runs semantic + keyword in parallel, merges and re-ranks.

    Lane 1 (semantic): vector cosine similarity — high recall on meaning
    Lane 2 (keyword):  full-text tsvector match — high precision on exact terms

    Merge strategy:
      - Deduplicate by paper_id + chunk_index
      - Results that appear in BOTH lanes get a +0.15 boost to relevance_score
      - Results only from keyword lane get +0.05 boost (exact term match is valuable)
      - Sort by final score DESC, return top-k

    Best for: comparisons, multi-hop, specific systems in context (e.g. "how does SMetric work").

    Args:
        query: The search query string.
        user_id: The requesting user's ID (for access control).
        domain: Optional domain hint (passed to both lanes but not used as hard filter).
        k: Number of results to return.
        collab_ids: List of collaboration IDs the user belongs to.

    Returns:
        List of dicts with paper_id, title, content, relevance_score, search_lane, etc.
    """
    try:
        # Run both lanes in parallel — no extra latency
        semantic_results, keyword_results = await asyncio.gather(
            semantic_search(query, user_id, domain, k, collab_ids),
            keyword_search(query, user_id, domain, k, collab_ids),
        )

        # Build a deduplicated map keyed by (paper_id, chunk_index)
        merged: dict[tuple, dict] = {}

        for result in semantic_results:
            key = (result["paper_id"], result["chunk_index"])
            merged[key] = {
                **result,
                "in_semantic": True,
                "in_keyword": False,
                "semantic_score": result["relevance_score"],
                "keyword_score": 0.0
            }

        for result in keyword_results:
            key = (result["paper_id"], result["chunk_index"])
            if key in merged:
                # Appears in BOTH lanes
                merged[key]["in_keyword"] = True
                merged[key]["keyword_score"] = result["relevance_score"]
            else:
                merged[key] = {
                    **result,
                    "in_semantic": False,
                    "in_keyword": True,
                    "semantic_score": 0.0,
                    "keyword_score": result["relevance_score"]
                }

        # Apply score boosts based on lane coverage
        final: list[dict] = []
        for item in merged.values():
            # Base score is the maximum of both lanes
            base_score = max(item["semantic_score"], item["keyword_score"])
            
            if item["in_semantic"] and item["in_keyword"]:
                score = min(1.0, base_score + 0.15)   # both lanes → highest confidence
                item["search_lane"] = "hybrid_both"
            elif item["in_keyword"]:
                score = min(1.0, base_score + 0.05)   # keyword only → small boost for exact match
                item["search_lane"] = "hybrid_keyword"
            else:
                score = base_score                     # semantic only → no boost
                item["search_lane"] = "hybrid_semantic"

            item["relevance_score"] = round(score, 4)
            # Remove temporary score tracking fields
            item.pop("semantic_score", None)
            item.pop("keyword_score", None)
            final.append(item)

        # Sort by final score and return top-k
        final.sort(key=lambda x: x["relevance_score"], reverse=True)
        final = final[:k]

        # Clean up internal tracking flags before returning
        for item in final:
            item.pop("in_semantic", None)
            item.pop("in_keyword", None)

        logger.info(
            f"[hybrid_search] {len(final)} results "
            f"(semantic={len(semantic_results)}, keyword={len(keyword_results)}) "
            f"for: '{query[:60]}...'"
        )
        return final

    except Exception as e:
        logger.error(f"hybrid_search failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


# ─────────────────────────────────────────────────────────────────────────────
# HYBRID SEARCH V2 — BM25 + Semantic + RRF + Cross-Encoder Reranking
# ─────────────────────────────────────────────────────────────────────────────

def _rrf_merge(
    semantic_results: list[dict],
    bm25_results: list[dict],
    rrf_k: int = 60,
    expand_to: int = 40,
) -> list[dict]:
    """
    Reciprocal Rank Fusion merge of semantic + BM25 ranked lists.

    Formula: RRF_score(doc) = Σ 1 / (rrf_k + rank_i)
    where rank_i is the 1-based position in each ranked list.
    Standard rrf_k=60 is the empirically best constant for dense+sparse fusion.

    Deduplication key: (paper_id, chunk_index) — same chunk from both lanes
    is merged into a single entry with combined RRF score.

    Returns up to `expand_to` docs sorted by RRF score descending.
    These are then fed into the cross-encoder for final reranking.
    """
    rrf_scores: dict[tuple, float] = {}
    doc_map: dict[tuple, dict] = {}

    # Score semantic results (rank starts at 1)
    for rank, doc in enumerate(semantic_results, start=1):
        key = (doc["paper_id"], doc["chunk_index"])
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
        if key not in doc_map:
            doc_map[key] = {**doc, "in_semantic": True, "in_bm25": False}

    # Score BM25 results
    for rank, doc in enumerate(bm25_results, start=1):
        key = (doc["paper_id"], doc["chunk_index"])
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
        if key in doc_map:
            doc_map[key]["in_bm25"] = True
        else:
            doc_map[key] = {**doc, "in_semantic": False, "in_bm25": True}

    # Attach RRF score and determine search lane label
    merged: list[dict] = []
    for key, doc in doc_map.items():
        doc["rrf_score"] = round(rrf_scores[key], 8)
        if doc.get("in_semantic") and doc.get("in_bm25"):
            doc["search_lane"] = "hybrid_both"
        elif doc.get("in_bm25"):
            doc["search_lane"] = "hybrid_bm25"
        else:
            doc["search_lane"] = "hybrid_semantic"
        merged.append(doc)

    # Sort by RRF score descending and return top expand_to candidates
    merged.sort(key=lambda d: d["rrf_score"], reverse=True)
    return merged[:expand_to]


async def hybrid_search_v2(
    query: str,
    user_id: str,
    domain: Optional[str] = None,
    k: int = 5,
    collab_ids: Optional[list[str]] = None,
    semantic_k: int = 20,
    bm25_k: int = 20,
    rrf_expand: int = 40,
) -> tuple[list[dict], dict]:
    """
    3-stage hybrid retrieval: Semantic + BM25 → RRF merge → Cross-encoder rerank.

    Stage 1 — Dual retrieval (parallel):
      • Lane A: semantic_search(k=semantic_k)  — pgvector cosine similarity
      • Lane B: bm25_search(k=bm25_k)          — in-memory BM25Okapi

    Stage 2 — RRF merge:
      • Reciprocal Rank Fusion merges both ranked lists
      • Deduplicates by (paper_id, chunk_index)
      • Returns top rrf_expand candidates for reranking

    Stage 3 — Cross-encoder rerank:
      • cross-encoder/ms-marco-MiniLM-L-6-v2 scores each (query, passage) pair
      • Returns final top-k with rerank_score and updated relevance_score

    Args:
        query:        User search query.
        user_id:      Requesting user's UUID (access control).
        domain:       Optional domain hint (passed through, not hard-filtered).
        k:            Final number of results to return after reranking.
        collab_ids:   Collaboration IDs for access control.
        semantic_k:   How many results to pull from semantic search.
        bm25_k:       How many results to pull from BM25.
        rrf_expand:   How many merged candidates to pass to the cross-encoder.

    Returns:
        Tuple of:
          - list[dict]: Top-k reranked results with fields:
              paper_id, title, authors, domain, content, chunk_index,
              relevance_score (normalised 0–1 from reranker),
              rerank_score (raw cross-encoder logit),
              rrf_score, search_lane, source, visibility, pdf_url
          - dict: Retrieval signal metadata for RAGState:
              semantic_count, bm25_count, rrf_candidates,
              max_rerank_score, min_rerank_score, both_lanes_count
    """
    from src.vectordb import bm25_index  # local import to avoid circular at module load
    from src.vectordb import reranker as reranker_module
    import time

    start_all = time.time()
    try:
        # ── Stage 1: Dual retrieval in parallel ──────────────────────────────
        # Ensure BM25 index is built (no-op if already built)
        start_bm25_build = time.time()
        if not bm25_index.is_built():
            await bm25_index.build()
        bm25_build_elapsed = time.time() - start_bm25_build

        # Run semantic search and in-memory BM25 search concurrently
        start_retrieval = time.time()
        loop = asyncio.get_event_loop()
        
        semantic_task = semantic_search(query, user_id, domain, semantic_k, collab_ids)
        bm25_task = loop.run_in_executor(
            None,
            bm25_index.search,
            query,
            bm25_k
        )
        
        semantic_results, bm25_results = await asyncio.gather(semantic_task, bm25_task)
        retrieval_elapsed = time.time() - start_retrieval
        
        # Individual timers for backward logging metrics compatibility
        semantic_elapsed = retrieval_elapsed
        bm25_search_elapsed = retrieval_elapsed

        logger.info(
            f"[hybrid_v2] Stage 1: semantic={len(semantic_results)}, "
            f"bm25={len(bm25_results)} for '{query[:60]}'"
        )

        # ── Stage 2: RRF merge ───────────────────────────────────────────────
        start_rrf = time.time()
        rrf_candidates = _rrf_merge(
            semantic_results, bm25_results, rrf_k=60, expand_to=rrf_expand
        )

        both_lanes_count = sum(
            1 for d in rrf_candidates if d.get("search_lane") == "hybrid_both"
        )
        rrf_elapsed = time.time() - start_rrf
        logger.info(
            f"[hybrid_v2] Stage 2 RRF: {len(rrf_candidates)} candidates "
            f"({both_lanes_count} in both lanes)"
        )

        # ── Stage 3: Cross-encoder rerank ────────────────────────────────────
        start_rerank = time.time()
        # Offload CPU-heavy cross-encoder to thread executor to prevent freezing ASGI main thread
        reranked = await loop.run_in_executor(
            None,
            reranker_module.rerank,
            query,
            rrf_candidates,
            k
        )
        rerank_elapsed = time.time() - start_rerank== "hybrid_both"
        
        rrf_elapsed = time.time() - start_rrf
        logger.info(
            f"[hybrid_v2] Stage 2 RRF: {len(rrf_candidates)} candidates "
            f"({both_lanes_count} in both lanes)"
        )

        # ── Stage 3: Cross-encoder rerank ────────────────────────────────────
        start_rerank = time.time()
        reranked = reranker_module.rerank(
            query=query,
            docs=rrf_candidates,
            top_k=k,
        )
        rerank_elapsed = time.time() - start_rerank

        # Build retrieval signal metadata for RAGState tracking
        signals: dict = {
            "semantic_count": len(semantic_results),
            "bm25_count": len(bm25_results),
            "rrf_candidates": len(rrf_candidates),
            "both_lanes_count": both_lanes_count,
            "max_rerank_score": reranked[0]["rerank_score"] if reranked else 0.0,
            "min_rerank_score": reranked[-1]["rerank_score"] if reranked else 0.0,
        }

        # Clean up internal tracking fields from final results
        for doc in reranked:
            doc.pop("in_semantic", None)
            doc.pop("in_bm25", None)

        total_elapsed = time.time() - start_all
        logger.info(
            f"[hybrid_v2 TIMERS] Total: {total_elapsed:.4f}s | "
            f"BM25 Build: {bm25_build_elapsed:.4f}s | "
            f"Semantic: {semantic_elapsed:.4f}s | "
            f"BM25 Search: {bm25_search_elapsed:.4f}s | "
            f"RRF Merge: {rrf_elapsed:.4f}s | "
            f"Reranker: {rerank_elapsed:.4f}s"
        )
        return reranked, signals

    except Exception as e:
        logger.error(f"hybrid_search_v2 failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Graceful fallback to original hybrid_search
        logger.warning("[hybrid_v2] Falling back to basic hybrid_search.")
        fallback = await hybrid_search(query, user_id, domain, k, collab_ids)
        fallback_signals: dict = {
            "semantic_count": 0, "bm25_count": 0,
            "rrf_candidates": 0, "both_lanes_count": 0,
            "max_rerank_score": calculate_avg_relevance(fallback),
            "min_rerank_score": 0.0,
        }
        return fallback, fallback_signals