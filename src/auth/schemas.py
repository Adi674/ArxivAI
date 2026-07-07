# ============================================================================
# src/auth/schemas.py — Pydantic Request/Response Schemas
# Input validation and response formatting
# ============================================================================

from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime


class UserRegister(BaseModel):
    """
    Schema for user registration (POST /auth/register).
    
    Attributes:
        email: User's email address
        password: Plain-text password (will be hashed)
        full_name: User's full name
        domains: List of research domains
        organization: Optional organization name
    """
    
    email: EmailStr = Field(
        ...,
        description="Email address (will be verified for uniqueness)",
        example="researcher@example.com"
    )
    password: str = Field(
        ...,
        min_length=8,
        description="Password (min 8 characters)",
        example="secure_password_123"
    )
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Full name",
        example="John Doe"
    )
    domains: List[str] = Field(
        default=[],
        description="Research domains",
        example=["ML", "NLP"]
    )
    organization: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Organization name",
        example="Stanford University"
    )


class UserLogin(BaseModel):
    """
    Schema for user login (POST /auth/login).
    
    Attributes:
        email: Email address
        password: Plain-text password (will be verified against hash)
    """
    
    email: EmailStr = Field(
        ...,
        description="Email address",
        example="researcher@example.com"
    )
    password: str = Field(
        ...,
        description="Password",
        example="secure_password_123"
    )


class TokenOut(BaseModel):
    """
    Schema for login response (includes JWT token).
    
    Attributes:
        access_token: JWT access token
        token_type: Token type (always "bearer")
        expires_in: Token expiry time in seconds
    """
    
    access_token: str = Field(
        ...,
        description="JWT access token",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer')",
    )
    expires_in: int = Field(
        ...,
        description="Token expiry time in seconds",
        example=86400
    )


class UserOut(BaseModel):
    """
    Schema for user profile response.
    Never includes password in response!
    
    Attributes:
        id: User ID
        email: Email address
        full_name: Full name
        domains: Research domains
        organization: Organization name
        is_active: Account active status
        created_at: Account creation timestamp
    """
    
    id: str = Field(
        ...,
        description="User ID (UUID)",
    )
    email: EmailStr = Field(
        ...,
        description="Email address",
    )
    full_name: str = Field(
        ...,
        description="Full name",
    )
    domains: List[str] = Field(
        default=[],
        description="Research domains",
    )
    organization: Optional[str] = Field(
        default=None,
        description="Organization name",
    )
    is_active: bool = Field(
        default=True,
        description="Account active status",
    )
    created_at: datetime = Field(
        ...,
        description="Account creation timestamp",
    )
    
    class Config:
        """Pydantic config"""
        from_attributes = True  # Allow ORM model conversion


class UserUpdate(BaseModel):
    """
    Schema for updating user profile (PATCH /auth/me).
    
    Attributes:
        full_name: New full name
        domains: Updated domains
        organization: Updated organization
    """
    
    full_name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
        description="New full name",
    )
    domains: Optional[List[str]] = Field(
        default=None,
        description="Updated research domains",
    )
    organization: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Updated organization name",
    )


class PasswordChange(BaseModel):
    """
    Schema for changing password (POST /auth/change-password).
    
    Attributes:
        current_password: Current password (for verification)
        new_password: New password
    """
    
    current_password: str = Field(
        ...,
        description="Current password",
    )
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password (min 8 characters)",
    )