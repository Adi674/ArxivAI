# ============================================================================
# src/auth/service.py — Authentication Service
# Password hashing, JWT token generation/validation, user operations
# ============================================================================

from datetime import datetime, timedelta
from typing import Optional
import logging
import uuid

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.config import get_settings
from src.models import User
from src.auth.schemas import UserRegister, UserLogin, UserOut, TokenOut

settings = get_settings()

logger = logging.getLogger(__name__)

# ── PASSWORD HASHING ───────────────────────────────────────────────────────
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # Security level
)


def hash_password(password: str) -> str:
    """
    Hash a plain-text password using bcrypt.
    
    Args:
        password: Plain-text password
    
    Returns:
        str: Hashed password (safe to store)
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against its hash.
    
    Args:
        plain_password: Plain-text password to verify
        hashed_password: Stored hash to compare against
    
    Returns:
        bool: True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT TOKEN HANDLING ────────────────────────────────────────────────────
def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> tuple[str, int]:
    """
    Create a JWT access token.
    
    Args:
        user_id: User ID to encode in token
        expires_delta: Token expiry time (default: from config)
    
    Returns:
        tuple: (token_string, expires_in_seconds)
    
    Raises:
        Exception: If token creation fails
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=settings.JWT_EXPIRE_HOURS)
    
    expire_time = datetime.utcnow() + expires_delta
    expires_in_seconds = int(expires_delta.total_seconds())
    
    payload = {
        "sub": str(user_id),  # Subject (user ID)
        "exp": expire_time,   # Expiry time
        "iat": datetime.utcnow(),  # Issued at
        "type": "access",
    }
    
    try:
        encoded_jwt = jwt.encode(
            payload,
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )
        logger.debug(f"✅ Created JWT token for user {user_id}")
        return encoded_jwt, expires_in_seconds
    except Exception as e:
        logger.error(f"❌ Failed to create JWT token: {e}")
        raise


def decode_token(token: str) -> Optional[str]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        str: User ID if token is valid
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: str = payload.get("sub")
        
        if user_id is None:
            logger.warning("❌ Token missing 'sub' claim")
            raise ValueError("Invalid token")
        
        logger.debug(f"✅ Decoded JWT token for user {user_id}")
        return user_id
    
    except JWTError as e:
        logger.error(f"❌ JWT validation failed: {e}")
        raise ValueError(f"Invalid token: {e}")


# ── USER REGISTRATION ────────────────────────────────────────────────────
async def register_user(
    data: UserRegister,
    db: AsyncSession
) -> UserOut:
    """
    Register a new user account.
    
    Args:
        data: Registration data
        db: Database session
    
    Returns:
        UserOut: Created user profile
    
    Raises:
        ValueError: If email already exists
    """
    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == data.email.lower())
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        logger.warning(f"❌ Registration attempt with existing email: {data.email}")
        raise ValueError(f"Email already registered: {data.email}")
    
    # Create new user
    new_user = User(
        id=uuid.uuid4(),
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        domains=data.domains or [],
        organization=data.organization,
        is_active=True,
    )
    
    try:
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        logger.info(f"✅ New user registered: {data.email}")
        return UserOut.model_validate(new_user)
    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Error registering user: {e}")
        raise


# ── USER LOGIN ──────────────────────────────────────────────────────────
async def login_user(
    data: UserLogin,
    db: AsyncSession
) -> TokenOut:
    """
    Authenticate user and return JWT token.
    
    Args:
        data: Login credentials
        db: Database session
    
    Returns:
        TokenOut: JWT access token and metadata
    
    Raises:
        ValueError: If credentials are invalid
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == data.email.lower())
    )
    user = result.scalar_one_or_none()
    
    if not user:
        logger.warning(f"❌ Login attempt with non-existent email: {data.email}")
        raise ValueError("Invalid email or password")
    
    # Verify password
    if not verify_password(data.password, user.hashed_password):
        logger.warning(f"❌ Failed login attempt for user: {data.email}")
        raise ValueError("Invalid email or password")
    
    # Check if account is active
    if not user.is_active:
        logger.warning(f"❌ Login attempt with inactive account: {data.email}")
        raise ValueError("Account is not active")
    
    # Create JWT token
    token, expires_in = create_access_token(user.id)
    
    logger.info(f"✅ User logged in: {data.email}")
    
    return TokenOut(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
    )


from fastapi import Depends, Header, HTTPException, status
from src.database import get_session

async def get_token_from_header(
    authorization: str = Header(None)
) -> str:
    """
    Extract JWT token from Authorization header.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return parts[1]


# ── GET CURRENT USER ────────────────────────────────────────────────────
async def get_current_user(
    token: str = Depends(get_token_from_header),
    db: AsyncSession = Depends(get_session)
) -> UserOut:
    """
    Get current user from JWT token.
    Used as FastAPI dependency for protected routes.
    """
    try:
        # Decode token
        user_id = decode_token(token)
        
        # Fetch user from database
        result = await db.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"❌ User not found: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
            logger.warning(f"❌ Inactive user accessing protected route: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is not active",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return UserOut.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── GET USER BY ID ────────────────────────────────────────────────────
async def get_user_by_id(
    user_id: str,
    db: AsyncSession
) -> Optional[UserOut]:
    """
    Get user by ID.
    
    Args:
        user_id: User ID (UUID string)
        db: Database session
    
    Returns:
        UserOut: User profile or None if not found
    """
    try:
        result = await db.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )
        user = result.scalar_one_or_none()
        return UserOut.model_validate(user) if user else None
    except Exception as e:
        logger.error(f"❌ Error fetching user: {e}")
        return None


# ── GET USER BY EMAIL ──────────────────────────────────────────────────
async def get_user_by_email(
    email: str,
    db: AsyncSession
) -> Optional[UserOut]:
    """
    Get user by email.
    
    Args:
        email: Email address
        db: Database session
    
    Returns:
        UserOut: User profile or None if not found
    """
    try:
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        user = result.scalar_one_or_none()
        return UserOut.model_validate(user) if user else None
    except Exception as e:
        logger.error(f"❌ Error fetching user by email: {e}")
        return None