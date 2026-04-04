"""
Auth routes — Google OAuth token verification + JWT issuance.

Flow:
1. Frontend signs in via NextAuth (Google OAuth)
2. Frontend sends the Google ID token to POST /api/auth/login
3. We verify the token with Google, create/update the user in DB
4. Return a JWT that the frontend uses for all subsequent API calls
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
import httpx
import os

from database.connection import get_db
from models.models import User
from utils.auth import get_current_user

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30


# ── Request/Response schemas ─────────────────────────────────────────────────

class GoogleLoginRequest(BaseModel):
    """Frontend sends the Google ID token after NextAuth sign-in."""
    id_token: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str | None
    email: str

class RefreshRequest(BaseModel):
    access_token: str


# ── JWT helpers ──────────────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ── Google token verification ────────────────────────────────────────────────

async def verify_google_token(id_token: str) -> dict:
    """Verify Google ID token by calling Google's tokeninfo endpoint."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )
    data = resp.json()
    # Verify the token was issued for our app
    expected_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if expected_client_id and data.get("aud") != expected_client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token not issued for this application",
        )
    return data


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login_with_google(body: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Verify Google ID token → create or update user → return JWT.
    Called by the frontend after NextAuth Google sign-in.
    """
    google_data = await verify_google_token(body.id_token)
    google_id = google_data["sub"]
    email = google_data.get("email", "")
    name = google_data.get("name", "")
    picture = google_data.get("picture", "")

    # Find existing user or create new one
    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if user:
        # Update last login and any changed profile info
        user.last_login = datetime.now(timezone.utc)
        user.name = name or user.name
        user.avatar_url = picture or user.avatar_url
    else:
        # New user — create with free tier
        user = User(
            email=email,
            name=name,
            avatar_url=picture,
            google_id=google_id,
            last_login=datetime.now(timezone.utc),
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    # Issue JWT
    access_token = create_access_token(user.id, user.email)

    return TokenResponse(
        access_token=access_token,
        user_id=user.id,
        name=user.name,
        email=user.email,
    )


@router.get("/me")
async def get_current_user_info(user: User = Depends(get_current_user)):
    """Return current authenticated user's profile."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "subscription_tier": user.subscription_tier.value if user.subscription_tier else "free",
        "risk_tolerance": user.risk_tolerance.value if user.risk_tolerance else "moderate",
        "investment_horizon": user.investment_horizon,
        "experience_level": user.experience_level,
        "queries_used_this_month": user.queries_used_this_month or 0,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
