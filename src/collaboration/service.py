import uuid
import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from src.models import (
    User, Collaboration, CollaborationMember,
    CollaborationApplication, CollaborationPaper
)
from src.collaboration.schemas import CollaborationCreate, ApplicationCreate

logger = logging.getLogger(__name__)


async def create_collaboration(
    creator_id: uuid.UUID,
    schema: CollaborationCreate,
    db: AsyncSession,
) -> Collaboration:
    """Create a new collaboration. Auto-adds creator as member."""
    collab = Collaboration(
        type=schema.type,
        creator_id=creator_id,
        project_name=schema.project_name,
        description=schema.description,
        domains=schema.domains,
        status="active",
    )
    db.add(collab)
    await db.flush()  # get collab.id before commit

    # Add creator as first member
    member = CollaborationMember(
        collaboration_id=collab.id,
        user_id=creator_id,
        role="creator",
    )
    db.add(member)
    await db.commit()
    await db.refresh(collab)
    logger.info(f"Collaboration created: {collab.id}")
    return collab


async def invite_user(
    collaboration_id: uuid.UUID,
    email: str,
    inviter_id: uuid.UUID,
    db: AsyncSession,
) -> CollaborationMember:
    """
    Invite a user by email directly (for direct_invite type).
    Adds them as a member immediately.
    """
    # Check inviter is creator
    collab_result = await db.execute(select(Collaboration).where(Collaboration.id == collaboration_id))
    collab = collab_result.scalar_one_or_none()
    if not collab:
        raise HTTPException(404, "Collaboration not found")
    if str(collab.creator_id) != str(inviter_id):
        raise HTTPException(403, "Only the creator can invite users")

    # Find user by email
    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, f"No user found with email: {email}")

    # Check not already a member
    existing = await db.execute(
        select(CollaborationMember).where(
            CollaborationMember.collaboration_id == collaboration_id,
            CollaborationMember.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "User is already a member")

    member = CollaborationMember(
        collaboration_id=collaboration_id,
        user_id=user.id,
        role="member",
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def get_user_collaborations(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> List[Collaboration]:
    """Return all collaborations the user is a member of."""
    result = await db.execute(
        select(Collaboration)
        .join(CollaborationMember, Collaboration.id == CollaborationMember.collaboration_id)
        .where(CollaborationMember.user_id == user_id, Collaboration.status == "active")
    )
    return result.scalars().all()


async def get_members(
    collaboration_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> List[CollaborationMember]:
    """Get all members. User must be a member to view."""
    # Check requesting user is a member
    check = await db.execute(
        select(CollaborationMember).where(
            CollaborationMember.collaboration_id == collaboration_id,
            CollaborationMember.user_id == user_id,
        )
    )
    if not check.scalar_one_or_none():
        raise HTTPException(403, "You are not a member of this collaboration")

    result = await db.execute(
        select(CollaborationMember).where(CollaborationMember.collaboration_id == collaboration_id)
    )
    return result.scalars().all()


async def apply_to_project(
    collaboration_id: uuid.UUID,
    user_id: uuid.UUID,
    schema: ApplicationCreate,
    db: AsyncSession,
) -> CollaborationApplication:
    """Apply to join a project-type collaboration."""
    collab_result = await db.execute(select(Collaboration).where(Collaboration.id == collaboration_id))
    collab = collab_result.scalar_one_or_none()
    if not collab:
        raise HTTPException(404, "Collaboration not found")
    if collab.type != "project":
        raise HTTPException(400, "Can only apply to project-type collaborations")

    # Check not already applied
    existing = await db.execute(
        select(CollaborationApplication).where(
            CollaborationApplication.collaboration_id == collaboration_id,
            CollaborationApplication.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "You have already applied")

    application = CollaborationApplication(
        collaboration_id=collaboration_id,
        user_id=user_id,
        status="pending",
        interest_note=schema.interest_note,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


async def review_application(
    application_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    approve: bool,
    db: AsyncSession,
) -> CollaborationApplication:
    """Approve or reject an application. Creator only."""
    from datetime import datetime

    app_result = await db.execute(select(CollaborationApplication).where(CollaborationApplication.id == application_id))
    application = app_result.scalar_one_or_none()
    if not application:
        raise HTTPException(404, "Application not found")

    collab_result = await db.execute(select(Collaboration).where(Collaboration.id == application.collaboration_id))
    collab = collab_result.scalar_one_or_none()
    if str(collab.creator_id) != str(reviewer_id):
        raise HTTPException(403, "Only the creator can review applications")

    application.status = "approved" if approve else "rejected"
    application.reviewed_at = datetime.utcnow()

    if approve:
        member = CollaborationMember(
            collaboration_id=application.collaboration_id,
            user_id=application.user_id,
            role="member",
        )
        db.add(member)

    await db.commit()
    await db.refresh(application)
    return application


async def get_open_projects(
    db: AsyncSession,
) -> List[Collaboration]:
    """Return all active project-type collaborations (public discovery)."""
    result = await db.execute(
        select(Collaboration).where(
            Collaboration.type == "project",
            Collaboration.status == "active",
        )
    )
    return result.scalars().all()