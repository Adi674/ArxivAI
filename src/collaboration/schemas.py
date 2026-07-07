from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class CollaborationCreate(BaseModel):
    type: str
    project_name: Optional[str] = None
    description: Optional[str] = None
    domains: List[str] = []

    @validator("type")
    def validate_type(cls, v):
        if v not in ["direct_invite", "project"]:
            raise ValueError("type must be 'direct_invite' or 'project'")
        return v


class CollaborationOut(BaseModel):
    id: UUID
    type: str
    creator_id: UUID
    project_name: Optional[str]
    description: Optional[str]
    domains: List[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class InviteByEmail(BaseModel):
    email: str


class MemberOut(BaseModel):
    user_id: UUID
    role: str
    joined_at: datetime

    class Config:
        from_attributes = True


class ApplicationCreate(BaseModel):
    interest_note: Optional[str] = None


class ApplicationOut(BaseModel):
    id: UUID
    collaboration_id: UUID
    user_id: UUID
    status: str
    interest_note: Optional[str]
    applied_at: datetime

    class Config:
        from_attributes = True