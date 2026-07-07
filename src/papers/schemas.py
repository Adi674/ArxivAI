from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID

VALID_DOMAINS = ["ML", "NLP", "CV", "AI", "Biology", "Physics", "Chemistry", "Math", "Theory", "Systems"]
VALID_SOURCES = ["arxiv", "user_uploaded", "arxiv_fetched"]
VALID_VISIBILITY = ["private", "collaborative", "public"]


class PaperUpload(BaseModel):
    title: str
    authors: str
    domain: str
    pdf_url: Optional[str] = None

    @validator("domain")
    def validate_domain(cls, v):
        if v not in VALID_DOMAINS:
            raise ValueError(f"Domain must be one of: {VALID_DOMAINS}")
        return v


class PaperUpdate(BaseModel):
    title: Optional[str] = None
    visibility: Optional[str] = None

    @validator("visibility")
    def validate_visibility(cls, v):
        if v and v not in VALID_VISIBILITY:
            raise ValueError(f"Visibility must be one of: {VALID_VISIBILITY}")
        return v


class PaperOut(BaseModel):
    id: str
    user_id: Optional[UUID]
    title: str
    authors: str
    domain: str
    source: str
    visibility: str
    pdf_url: Optional[str]
    citation_count: int
    upload_date: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class PaperListResponse(BaseModel):
    papers: List[PaperOut]
    total: int