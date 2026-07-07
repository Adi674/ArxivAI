import logging
from typing import Optional
from uuid import UUID

from src.vectordb.chroma_client import get_vectorstore

logger = logging.getLogger(__name__)


def build_access_filter(
    user_id: str,
    domain: Optional[str] = None,
    collab_ids: Optional[list[str]] = None,
) -> dict:
    """
    Build Chroma metadata filter for access control.
    A user can see:
      - Their own private papers
      - All public papers
      - Collaborative papers they belong to

    Args:
        user_id: Current user's UUID as string
        domain: Optional domain to filter by
        collab_ids: List of collaboration IDs the user belongs to

    Returns:
        Chroma `where` filter dict.
    """
    visibility_conditions = [
        {"visibility": {"$eq": "public"}},
        {"user_id": {"$eq": user_id}},
    ]

    if collab_ids:
        visibility_conditions.append(
            {"collaboration_id": {"$in": collab_ids}}
        )

    access_filter = {"$or": visibility_conditions}

    if domain:
        return {
            "$and": [
                {"domain": {"$eq": domain}},
                access_filter,
            ]
        }

    return access_filter


def semantic_search(
    query: str,
    user_id: str,
    domain: Optional[str] = None,
    k: int = 10,
    collab_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Run semantic similarity search in Chroma with access control.

    Returns:
        List of dicts with paper_id, content, relevance_score, metadata.
    """
    vectorstore = get_vectorstore()
    where_filter = build_access_filter(user_id=user_id, domain=domain, collab_ids=collab_ids)

    try:
        results = vectorstore.similarity_search_with_relevance_scores(
            query=query,
            k=k,
            filter=where_filter,
        )

        formatted = []
        for doc, score in results:
            formatted.append({
                "paper_id": doc.metadata.get("paper_id"),
                "title": doc.metadata.get("title", ""),
                "authors": doc.metadata.get("authors", ""),
                "domain": doc.metadata.get("domain", ""),
                "content": doc.page_content,
                "relevance_score": round(score, 4),
                "source": doc.metadata.get("source", ""),
                "visibility": doc.metadata.get("visibility", ""),
                "chunk_index": doc.metadata.get("chunk_index", 0),
            })

        logger.info(f"Semantic search returned {len(formatted)} results for query: '{query[:60]}...'")
        return formatted

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return []


def calculate_avg_relevance(results: list[dict]) -> float:
    """
    Average relevance score across results.
    Used by Retriever agent to decide if reformulation is needed.
    """
    if not results:
        return 0.0
    return round(sum(r["relevance_score"] for r in results) / len(results), 4)