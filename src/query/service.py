import uuid
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.graph import get_compiled_graph
from src.agents.state import RAGState
from src.models import Conversation, Message, ConversationContext, SessionState, DBModelEvalResult

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
        "search_tool": "hybrid",        # Agent 3 will override this

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
        # Safety & Guardrails (Phase 4)
        "guardrail_allowed": True,
        "guardrail_reason": "",
        "cleaned_query": query,
        "guardrail_risk_score": 0.0,
        "pii_found": False,
        "pipeline_short_circuited": False,
        "output_guardrail_clean": "",
        "citation_verify_passed": True,
        "invalid_citations_found": [],
        # Intent Classifier (Phase 5)
        "intent": "research",
        "is_conversational": False,
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

    # 5b. Trigger evaluation asynchronously in the background so it doesn't block the user response
    import asyncio
    asyncio.create_task(
        _evaluate_background_task(
            message_id=assistant_msg.id,
            query=query,
            answer=final_state["final_answer"],
            retrieved_papers=final_state["retrieved_papers"],
        )
    )

    if final_state.get("arxiv_fallback_triggered"):
        from src.eval.prometheus_metrics import ARXIV_FALLBACK_TOTAL
        ARXIV_FALLBACK_TOTAL.inc()

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


async def _evaluate_background_task(
    message_id: uuid.UUID,
    query: str,
    answer: str,
    retrieved_papers: list[dict],
):
    import time
    from src.database import get_async_session_maker
    from src.eval import llm_judge, hallucination as nli_module
    from src.models import Message, DBModelEvalResult
    from groq import Groq
    from src.config import get_settings
    import asyncio

    logger.info(f"[BackgroundEval] Starting async evaluation for message {message_id}")
    start_time = time.time()
    
    settings = get_settings()
    if not settings.GROQ_API_KEY:
        logger.warning("[BackgroundEval] GROQ_API_KEY not set. Skipping background evaluation.")
        return

    groq_client = Groq(api_key=settings.GROQ_API_KEY)

    try:
        # 1. Run LLM judge + NLI check in parallel
        judge_task = llm_judge.evaluate(
            query=query,
            answer=answer,
            retrieved_papers=retrieved_papers,
            groq_client=groq_client,
        )
        nli_task = asyncio.get_event_loop().run_in_executor(
            None,
            nli_module.check_hallucination,
            answer,
            retrieved_papers,
        )

        eval_result, nli_result = await asyncio.gather(judge_task, nli_task, return_exceptions=True)

        if isinstance(eval_result, Exception):
            logger.error(f"[BackgroundEval] LLM judge failed: {eval_result}")
            from src.eval.metrics import EvalResult
            eval_result = EvalResult()
            eval_result.overall_score = 0.5
        
        if isinstance(nli_result, Exception):
            logger.error(f"[BackgroundEval] NLI check failed: {nli_result}")
            nli_result = {"hallucination_rate": 0.0, "unsupported_claims": [], "attribution_map": {}}

        # 2. Merge NLI
        eval_result.hallucination_rate = nli_result.get("hallucination_rate", 0.0)
        eval_result.unsupported_claims = nli_result.get("unsupported_claims", [])
        eval_result.attribution_map = nli_result.get("attribution_map", {})
        eval_result.compute_overall()

        eval_scores = eval_result.to_dict()
        latency_ms = int((time.time() - start_time) * 1000)
        eval_scores["eval_latency_ms"] = latency_ms

        # 3. Save to database
        session_maker = get_async_session_maker()
        async with session_maker() as db_session:
            from sqlalchemy import select
            msg_stmt = select(Message).where(Message.id == message_id)
            msg_result = await db_session.execute(msg_stmt)
            message = msg_result.scalar_one_or_none()
            
            if message:
                message.quality_score = eval_result.overall_score
                message.ragas_scores = eval_scores
                
                db_eval = DBModelEvalResult(
                    message_id=message_id,
                    query=query,
                    answer=answer,
                    faithfulness=float(eval_scores.get("faithfulness", 0.0)),
                    answer_relevancy=float(eval_scores.get("answer_relevancy", 0.0)),
                    context_recall=float(eval_scores.get("context_recall", 0.0)),
                    coherence=float(eval_scores.get("coherence", 0.0)),
                    context_precision=float(eval_scores.get("context_precision", 0.0)),
                    citation_accuracy=float(eval_scores.get("citation_accuracy", 0.0)),
                    hallucination_rate=float(eval_scores.get("hallucination_rate", 0.0)),
                    overall_score=float(eval_result.overall_score),
                    feedback=eval_result.build_combined_feedback(),
                    latency_ms=latency_ms,
                )
                db_session.add(db_eval)
                await db_session.commit()
                logger.info(f"[BackgroundEval] Successfully saved evaluation results for message {message_id}")
            else:
                logger.error(f"[BackgroundEval] Message {message_id} not found in DB")

        # 4. Record metrics in Prometheus
        from src.eval.prometheus_metrics import HALLUCINATION_RATE_HIST, EVAL_SCORE_HIST
        EVAL_SCORE_HIST.observe(float(eval_result.overall_score))
        HALLUCINATION_RATE_HIST.observe(float(eval_result.hallucination_rate))

    except Exception as exc:
        logger.error(f"[BackgroundEval] Error running background evaluation: {exc}")