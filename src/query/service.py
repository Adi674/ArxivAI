import uuid
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.graph import get_compiled_graph
from src.agents.state import RAGState
from src.models import Conversation, Message, ConversationContext, SessionState

logger = logging.getLogger(__name__)


async def run_query(
    query: str,
    user_id: uuid.UUID,
    llm_mode: str,
    conversation_id: uuid.UUID,
    collab_ids: list[str],
    db: AsyncSession,
) -> dict:
    """
    Run the full 7-agent LangGraph pipeline for a user query.

    Steps:
    1. Save user message to DB
    2. Build initial RAGState
    3. Run compiled graph
    4. Save assistant message + session state to DB
    5. Update conversation context
    6. Return final answer + sources

    Args:
        query: User's question
        user_id: Authenticated user UUID
        llm_mode: budget | balanced | quality | research
        conversation_id: Which conversation this belongs to
        collab_ids: Collaboration IDs user is a member of (for Chroma filter)
        db: Async database session

    Returns:
        dict with final_answer, sources, quality_score, reasoning_trace
    """

    # 1. Save user message
    user_msg = Message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=query,
    )
    db.add(user_msg)
    await db.flush()

    # 2. Build initial state
    initial_state: RAGState = {
        "original_query": query,
        "user_id": str(user_id),
        "collab_ids": collab_ids,
        "llm_mode": llm_mode,
        # defaults — agents fill these in
        "primary_domain": "",
        "secondary_domains": [],
        "domain_confidence": 0.0,
        "query_type": "single_hop",
        "sub_queries": [],
        "needs_personal_papers": False,
        "needs_recent": False,
        "search_spaces": [],
        "fetch_arxiv_fresh": False,
        "retrieved_papers": [],
        "reformulation_count": 0,
        "findings": {},
        "contradictions": [],
        "agreements": [],
        "citation_graph": {},
        "knowledge_gaps": [],
        "draft_answer": "",
        "hallucination_detected": False,
        "quality_score": 0.0,
        "ragas_scores": {},
        "needs_refinement": False,
        "refinement_count": 0,
        "evaluator_feedback": "",
        "final_answer": "",
        "sources": [],
        "reasoning_trace": [],
    }

    # 3. Run pipeline
    graph = get_compiled_graph()
    logger.info(f"Running query pipeline for user {user_id}: '{query[:80]}'")
    final_state: RAGState = await graph.ainvoke(initial_state)

    # 4. Save assistant message
    assistant_msg = Message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        content=final_state["final_answer"],
        detected_domain=final_state["primary_domain"],
        papers_referenced=[p["paper_id"] for p in final_state["sources"]],
        quality_score=final_state["quality_score"],
        ragas_scores=final_state["ragas_scores"],
    )
    db.add(assistant_msg)
    await db.flush()

    # 5. Save session state for debugging
    session = SessionState(
        conversation_id=conversation_id,
        message_id=assistant_msg.id,
        original_query=query,
        primary_domain=final_state["primary_domain"],
        secondary_domains=final_state["secondary_domains"],
        domain_confidence=final_state["domain_confidence"],
        query_type=final_state["query_type"],
        sub_queries=final_state["sub_queries"],
        needs_personal_papers=final_state["needs_personal_papers"],
        needs_recent=final_state["needs_recent"],
        search_spaces=final_state["search_spaces"],
        retrieved_papers={p["paper_id"]: p["relevance_score"] for p in final_state["retrieved_papers"]},
        reformulation_count=final_state["reformulation_count"],
        findings=final_state["findings"],
        contradictions=final_state["contradictions"],
        final_answer=final_state["final_answer"],
        hallucination_detected=final_state["hallucination_detected"],
        quality_score=final_state["quality_score"],
        ragas_scores=final_state["ragas_scores"],
        sources=final_state["sources"],
        reasoning_trace=final_state["reasoning_trace"],
        completed_at=datetime.utcnow(),
    )
    db.add(session)

    # 6. Update conversation context
    from sqlalchemy import select
    ctx_result = await db.execute(
        select(ConversationContext).where(ConversationContext.conversation_id == conversation_id)
    )
    ctx = ctx_result.scalar_one_or_none()
    if ctx:
        ctx.primary_domain = final_state["primary_domain"]
        ctx.papers_referenced = list(set(
            (ctx.papers_referenced or []) + [p["paper_id"] for p in final_state["sources"]]
        ))
        ctx.turns_count = (ctx.turns_count or 0) + 1
        ctx.reformulations_count = (ctx.reformulations_count or 0) + final_state["reformulation_count"]
        ctx.papers_citations_count = (ctx.papers_citations_count or 0) + len(final_state["sources"])

    # Update conversation last_message_at
    from src.models import Conversation
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if conv:
        conv.last_message_at = datetime.utcnow()

    await db.commit()
    logger.info(f"Query complete. Quality: {final_state['quality_score']}, Sources: {len(final_state['sources'])}")

    return {
        "final_answer": final_state["final_answer"],
        "sources": final_state["sources"],
        "domain": final_state["primary_domain"],
        "quality_score": final_state["quality_score"],
        "ragas_scores": final_state["ragas_scores"],
        "hallucination_detected": final_state["hallucination_detected"],
        "reasoning_trace": final_state["reasoning_trace"],
    }


async def create_conversation(
    user_id: uuid.UUID,
    title: str,
    domain: str | None,
    db: AsyncSession,
) -> Conversation:
    """
    Start a new conversation. Creates conversation + context + settings records.
    """
    from src.models import ConversationSettings

    conv = Conversation(
        user_id=user_id,
        title=title,
        domain=domain,
        is_archived=False,
    )
    db.add(conv)
    await db.flush()

    ctx = ConversationContext(
        conversation_id=conv.id,
        primary_domain=domain,
        papers_referenced=[],
        turns_count=0,
    )
    db.add(ctx)

    settings = ConversationSettings(
        conversation_id=conv.id,
    )
    db.add(settings)

    await db.commit()
    await db.refresh(conv)
    return conv


async def get_conversation_history(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[Message]:
    """
    Return all messages in a conversation in chronological order.
    Verifies user owns the conversation.
    """
    from sqlalchemy import select
    from fastapi import HTTPException

    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return result.scalars().all()


async def get_user_conversations(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[Conversation]:
    """Return all non-archived conversations for the user, newest first."""
    from sqlalchemy import select

    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id, Conversation.is_archived == False)
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()