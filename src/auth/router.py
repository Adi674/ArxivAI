# ============================================================================
# src/auth/router.py — Authentication Endpoints
# POST /auth/register, POST /auth/login, GET /auth/me
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from src.database import get_session
from src.auth.schemas import UserRegister, UserLogin, UserOut, TokenOut
from src.auth.service import (
    register_user,
    login_user,
    get_current_user,
    get_user_by_email,
    get_token_from_header,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── ENDPOINT: Register ────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
    responses={
        400: {"description": "Email already registered"},
    }
)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_session),
) -> UserOut:
    """
    Register a new user account.
    
    Args:
        data: Registration data (email, password, full_name, domains)
        db: Database session
    
    Returns:
        UserOut: Created user profile (no password included)
    
    Raises:
        HTTPException: If email is already registered
    """
    try:
        user = await register_user(data, db)
        logger.info(f"✅ New user registered: {data.email}")
        return user
    except ValueError as e:
        logger.warning(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration",
        )


# ── ENDPOINT: Login ───────────────────────────────────────────────────────
@router.post(
    "/login",
    response_model=TokenOut,
    summary="Login and get access token",
    responses={
        401: {"description": "Invalid credentials"},
    }
)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_session),
) -> TokenOut:
    """
    Authenticate user and return JWT access token.
    
    Args:
        data: Login credentials (email, password)
        db: Database session
    
    Returns:
        TokenOut: JWT token and metadata
    
    Raises:
        HTTPException: If credentials are invalid
    """
    try:
        token = await login_user(data, db)
        logger.info(f"✅ User logged in: {data.email}")
        return token
    except ValueError as e:
        logger.warning(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during login",
        )


# ── ENDPOINT: Get Current User ────────────────────────────────────────────
@router.get(
    "/me",
    response_model=UserOut,
    summary="Get current user profile",
    responses={
        401: {"description": "Not authenticated"},
    }
)
async def get_me(
    token: str = Depends(get_token_from_header),
    db: AsyncSession = Depends(get_session),
) -> UserOut:
    """
    Get current authenticated user's profile.
    
    Args:
        token: JWT token from Authorization header
        db: Database session
    
    Returns:
        UserOut: Current user profile
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    try:
        user = await get_current_user(token, db)
        logger.debug(f"✅ User profile retrieved: {user.email}")
        return user
    except ValueError as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred",
        )


# ── ENDPOINT: Check Email Availability ────────────────────────────────────
@router.get(
    "/check-email/{email}",
    response_model=dict,
    summary="Check if email is available",
)
async def check_email_available(
    email: str,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """
    Check if an email address is available for registration.
    
    Args:
        email: Email address to check
        db: Database session
    
    Returns:
        dict: {"available": bool, "email": str}
    """
    try:
        user = await get_user_by_email(email, db)
        available = user is None
        logger.debug(f"Email availability check for {email}: {available}")
        return {"available": available, "email": email}
    except Exception as e:
        logger.error(f"Error checking email availability: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred",
        )