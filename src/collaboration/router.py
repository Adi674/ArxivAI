from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from src.database import get_session
from src.models import User
from src.auth.service import get_current_user
from src.collaboration.schemas import (
    CollaborationCreate, CollaborationOut,
    InviteByEmail, MemberOut,
    ApplicationCreate, ApplicationOut,
)
from src.collaboration import service

router = APIRouter(prefix="/api/collaborations", tags=["Collaboration"])


@router.post("/", response_model=CollaborationOut, status_code=201)
async def create_collaboration(
    schema: CollaborationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Create a new collaboration (direct_invite or project)."""
    return await service.create_collaboration(creator_id=current_user.id, schema=schema, db=db)


@router.get("/", response_model=List[CollaborationOut])
async def my_collaborations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all collaborations the current user is a member of."""
    return await service.get_user_collaborations(user_id=current_user.id, db=db)


@router.get("/open-projects", response_model=List[CollaborationOut])
async def open_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Discover open project-type collaborations."""
    return await service.get_open_projects(db=db)


@router.post("/{collaboration_id}/invite", response_model=MemberOut)
async def invite_user(
    collaboration_id: UUID,
    body: InviteByEmail,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Invite a user by email. Creator only."""
    return await service.invite_user(
        collaboration_id=collaboration_id,
        email=body.email,
        inviter_id=current_user.id,
        db=db,
    )


@router.get("/{collaboration_id}/members", response_model=List[MemberOut])
async def get_members(
    collaboration_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get all members of a collaboration. Members only."""
    return await service.get_members(
        collaboration_id=collaboration_id,
        user_id=current_user.id,
        db=db,
    )


@router.post("/{collaboration_id}/apply", response_model=ApplicationOut, status_code=201)
async def apply(
    collaboration_id: UUID,
    schema: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Apply to join a project. Project-type only."""
    return await service.apply_to_project(
        collaboration_id=collaboration_id,
        user_id=current_user.id,
        schema=schema,
        db=db,
    )


@router.post("/applications/{application_id}/approve", response_model=ApplicationOut)
async def approve_application(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Approve an application. Creator only."""
    return await service.review_application(
        application_id=application_id,
        reviewer_id=current_user.id,
        approve=True,
        db=db,
    )


@router.post("/applications/{application_id}/reject", response_model=ApplicationOut)
async def reject_application(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Reject an application. Creator only."""
    return await service.review_application(
        application_id=application_id,
        reviewer_id=current_user.id,
        approve=False,
        db=db,
    )