import uuid
import logging
from typing import Optional, List
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from fastapi import HTTPException

from src.models import Paper, CollaborationMember
from src.papers.schemas import PaperUpload, PaperUpdate

logger = logging.getLogger(__name__)


async def create_paper(
    user_id: uuid.UUID,
    schema: PaperUpload,
    source: str = "user_uploaded",
    db: AsyncSession = None,
) -> Paper:
    """
    Create a paper record in PostgreSQL.
    Chroma ingestion is triggered separately as a background task.
    """
    paper_id = str(uuid.uuid4())

    paper = Paper(
        id=paper_id,
        user_id=user_id,
        title=schema.title,
        authors=schema.authors,
        domain=schema.domain,
        source=source,
        visibility="private",
        pdf_url=schema.pdf_url,
        chroma_ids=[],
        citation_count=0,
    )

    db.add(paper)
    await db.commit()
    await db.refresh(paper)
    logger.info(f"Paper created: {paper_id}")
    return paper


async def get_paper(
    paper_id: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Paper:
    """
    Fetch a single paper. Checks ownership or public visibility.
    """
    result = await db.execute(select(Paper).where(Paper.id == paper_id, Paper.deleted_at == None))
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if paper.visibility == "public":
        return paper

    if str(paper.user_id) == str(user_id):
        return paper

    # Check if user is a collaborator
    if paper.visibility == "collaborative":
        from src.models import CollaborationPaper
        collab_check = await db.execute(
            select(CollaborationMember)
            .join(CollaborationPaper, CollaborationMember.collaboration_id == CollaborationPaper.collaboration_id)
            .where(
                CollaborationPaper.paper_id == paper_id,
                CollaborationMember.user_id == user_id
            )
        )
        if collab_check.scalar_one_or_none():
            return paper

    raise HTTPException(status_code=403, detail="Access denied")


async def get_user_papers(
    user_id: uuid.UUID,
    domain: Optional[str],
    db: AsyncSession,
) -> List[Paper]:
    """
    Return all papers the user owns (private + collaborative + public).
    """
    query = select(Paper).where(
        Paper.user_id == user_id,
        Paper.deleted_at == None,
    )
    if domain:
        query = query.where(Paper.domain == domain)

    query = query.order_by(Paper.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


async def get_public_papers(
    domain: Optional[str],
    db: AsyncSession,
) -> List[Paper]:
    """
    Return all public papers, optionally filtered by domain.
    """
    query = select(Paper).where(
        Paper.visibility == "public",
        Paper.deleted_at == None,
    )
    if domain:
        query = query.where(Paper.domain == domain)

    result = await db.execute(query.order_by(Paper.created_at.desc()))
    return result.scalars().all()


async def update_paper(
    paper_id: str,
    user_id: uuid.UUID,
    schema: PaperUpdate,
    db: AsyncSession,
) -> Paper:
    """
    Update paper title or visibility. Only owner can update.
    Public papers cannot be made private again.
    """
    result = await db.execute(select(Paper).where(Paper.id == paper_id, Paper.deleted_at == None))
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if str(paper.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Only the owner can update this paper")

    if schema.title:
        paper.title = schema.title

    if schema.visibility:
        # Public is irreversible
        if paper.visibility == "public" and schema.visibility != "public":
            raise HTTPException(status_code=400, detail="Public papers cannot be made private")
        paper.visibility = schema.visibility

    await db.commit()
    await db.refresh(paper)
    return paper


async def delete_paper(
    paper_id: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> bool:
    """
    Soft delete a paper. Only owner can delete. Public papers cannot be deleted.
    Also removes from Chroma using stored chroma_ids.
    """
    result = await db.execute(select(Paper).where(Paper.id == paper_id, Paper.deleted_at == None))
    paper = result.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if str(paper.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Only the owner can delete this paper")

    if paper.visibility == "public":
        raise HTTPException(status_code=400, detail="Public papers cannot be deleted")

    # Remove chunks from Chroma if any
    if paper.chroma_ids:
        try:
            from src.vectordb.chroma_client import get_vectorstore
            vectorstore = get_vectorstore()
            vectorstore._collection.delete(ids=paper.chroma_ids)
            logger.info(f"Deleted {len(paper.chroma_ids)} chunks from Chroma for paper {paper_id}")
        except Exception as e:
            logger.warning(f"Could not delete from Chroma: {e}")

    # Soft delete
    paper.deleted_at = datetime.utcnow()
    await db.commit()
    logger.info(f"Paper soft-deleted: {paper_id}")
    return True