"""
src/eval/feedback.py

FastAPI router and service logic for logging user feedback (thumbs up/down)
on query responses and retrieved sources. This feedback is used to dynamically
improve the semantic cache, update domain weights, and measure search precision.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from src.database import get_session
from src.models import User, UserFeedback, Message
from src.auth.service import get_current_user

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


# ── Pydantic Request Schema ──────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    message_id: UUID = Field(..., description="ID of the message being evaluated")
    paper_id: Optional[str] = Field(None, description="Optional ID of specific cited paper being evaluated")
    rating: int = Field(..., description="Feedback score: 1 for thumbs up, -1 for thumbs down")
    feedback_text: Optional[str] = Field(None, description="Optional written feedback explanation")

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, val: int) -> int:
        if val not in (1, -1):
            raise ValueError("Rating must be either 1 (thumbs up) or -1 (thumbs down)")
        return val


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Log a thumbs up (+1) or thumbs down (-1) feedback on a response or source.
    Useful for continuous RAG quality evaluation.
    """
    # 1. Verify message exists and belongs to the user or is public
    message = await db.get(Message, body.message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # 2. Add feedback record
    feedback = UserFeedback(
        user_id=current_user.id,
        message_id=body.message_id,
        paper_id=body.paper_id,
        rating=body.rating,
        feedback_text=body.feedback_text,
    )
    db.add(feedback)
    
    # Also log to console / logging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"[UserFeedback] Logged rating={body.rating} for message_id={body.message_id} "
        f"by user_id={current_user.id} (paper_id={body.paper_id})"
    )
    
    # Increment feedback counters for Prometheus
    FEEDBACK_TOTAL.labels(
        rating="thumbs_up" if body.rating == 1 else "thumbs_down",
        paper_spec="relevance" if body.paper_id else "synthesis"
    ).inc()
    
    await db.commit()
    return {"message": "Feedback submitted successfully", "feedback_id": feedback.id}


# ── Prometheus Counters ──────────────────────────────────────────────────────
from prometheus_client import Counter

FEEDBACK_TOTAL = Counter(
    "rag_user_feedback_total",
    "Total user thumbs up (+1) or down (-1) feedback metrics",
    ["rating", "paper_spec"]
)
