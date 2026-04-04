"""
Auth utilities — JWT creation, verification, and FastAPI dependency.

Use get_current_user in any route that needs authentication:

    @router.get("/my-route")
    async def my_route(user: User = Depends(get_current_user)):
        # user is now a fully loaded SQLAlchemy User object
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
import os

from database.connection import get_db
from models.models import User

security = HTTPBearer()

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30


def create_access_token(user_id: str, email: str) -> str:
    """Create a JWT token for a user."""
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token. Raises 401 if invalid."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract user from JWT Bearer token. Raises 401 if invalid."""
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
