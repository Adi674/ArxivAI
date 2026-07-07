from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

from src.database import get_session
from src.models import User
from src.auth.service import get_current_user
from src.query import service

router = APIRouter(prefix="/api/query", tags=["Query"])


# ── Request / Response schemas ────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    conversation_id: UUID
    llm_mode: Optional[str] = "balanced"  # budget | balanced | quality | research


class QueryResponse(BaseModel):
    final_answer: str
    sources: list[dict]
    domain: str
    quality_score: float
    ragas_scores: dict
    hallucination_detected: bool
    reasoning_trace: list[str]


class ConversationCreate(BaseModel):
    title: str
    domain: Optional[str] = None


class ConversationOut(BaseModel):
    id: UUID
    title: str
    domain: Optional[str]
    is_archived: bool
    last_message_at: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    detected_domain: Optional[str]
    papers_referenced: list[str]
    quality_score: Optional[float]
    created_at: str

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Start a new conversation."""
    conv = await service.create_conversation(
        user_id=current_user.id,
        title=body.title,
        domain=body.domain,
        db=db,
    )
    return conv


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all conversations for the current user."""
    return await service.get_user_conversations(user_id=current_user.id, db=db)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get full message history of a conversation."""
    return await service.get_conversation_history(
        conversation_id=conversation_id,
        user_id=current_user.id,
        db=db,
    )


@router.post("/", response_model=QueryResponse)
async def submit_query(
    body: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Submit a research query. Runs the full 7-agent LangGraph pipeline.
    Requires an existing conversation_id (create one first via POST /api/query/conversations).
    """
    # Get user's collab IDs for Chroma access filter
    from sqlalchemy import select
    from src.models import CollaborationMember
    collab_result = await db.execute(
        select(CollaborationMember.collaboration_id).where(
            CollaborationMember.user_id == current_user.id
        )
    )
    collab_ids = [str(row[0]) for row in collab_result.fetchall()]

    result = await service.run_query(
        query=body.query,
        user_id=current_user.id,
        llm_mode=body.llm_mode or "balanced",
        conversation_id=body.conversation_id,
        collab_ids=collab_ids,
        db=db,
    )
    return result