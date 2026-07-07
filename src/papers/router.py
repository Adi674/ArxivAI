from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from src.database import get_session
from src.models import User
from src.auth.service import get_current_user
from src.papers.schemas import PaperUpload, PaperUpdate, PaperOut, PaperListResponse
from src.papers import service

router = APIRouter(prefix="/api/papers", tags=["Papers"])


@router.post("/", response_model=PaperOut, status_code=201)
async def upload_paper(
    schema: PaperUpload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Upload a new paper (metadata only). PDF ingestion happens via /ingest."""
    return await service.create_paper(user_id=current_user.id, schema=schema, db=db)


@router.get("/my-papers", response_model=PaperListResponse)
async def list_my_papers(
    domain: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all papers owned by the current user."""
    papers = await service.get_user_papers(user_id=current_user.id, domain=domain, db=db)
    return PaperListResponse(papers=papers, total=len(papers))


@router.get("/public", response_model=PaperListResponse)
async def list_public_papers(
    domain: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """List all public papers."""
    papers = await service.get_public_papers(domain=domain, db=db)
    return PaperListResponse(papers=papers, total=len(papers))


@router.get("/{paper_id}", response_model=PaperOut)
async def get_paper(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get a single paper by ID."""
    return await service.get_paper(paper_id=paper_id, user_id=current_user.id, db=db)


@router.patch("/{paper_id}", response_model=PaperOut)
async def update_paper(
    paper_id: str,
    schema: PaperUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Update paper title or visibility. Owner only."""
    return await service.update_paper(paper_id=paper_id, user_id=current_user.id, schema=schema, db=db)


@router.delete("/{paper_id}", status_code=204)
async def delete_paper(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Soft delete a paper. Owner only. Public papers cannot be deleted."""
    await service.delete_paper(paper_id=paper_id, user_id=current_user.id, db=db)