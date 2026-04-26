"""
Auth routes — Google OAuth token verification + JWT issuance via httpOnly cookie.

Flow:
1. Frontend signs in via NextAuth (Google OAuth)
2. Frontend sends the Google ID token to POST /api/auth/login
3. We verify the token with Google, create/update the user in DB
4. Issue a JWT and set it in an httpOnly, Secure, SameSite=strict cookie.
   Subsequent calls authenticate via the cookie automatically.
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import httpx

from database.connection import get_db
from models.models import User
from utils.auth import COOKIE_NAME, create_access_token, get_current_user

router = APIRouter()

COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days, must match ACCESS_TOKEN_EXPIRE_DAYS

# Cookie security: in production we want Secure + SameSite=strict; in local dev
# without HTTPS the browser drops Secure cookies on http://localhost, so allow
# an opt-out via INSECURE_COOKIES=true for local testing.
_INSECURE_COOKIES = os.getenv("INSECURE_COOKIES", "").strip().lower() in {"1", "true", "yes", "on"}


# ── Request/Response schemas ─────────────────────────────────────────────────

class GoogleLoginRequest(BaseModel):
    """Frontend sends the Google ID token after NextAuth sign-in."""
    id_token: str
    invite_code: str | None = None


class LoginResponse(BaseModel):
    user_id: str
    name: str | None
    email: str


# ── Soft-launch invite gate ──────────────────────────────────────────────────

VALID_INVITE_CODES = {"early2026", "investai-beta"}


def _invite_required() -> bool:
    return os.getenv("BETA_INVITE_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}


def _verify_invite(code: str | None) -> bool:
    if not _invite_required():
        return True
    if not code:
        return False
    return code.strip().lower() in {c.lower() for c in VALID_INVITE_CODES}


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
    expected_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if expected_client_id and data.get("aud") != expected_client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token not issued for this application",
        )
    return data


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not _INSECURE_COOKIES,
        samesite="strict",
        max_age=COOKIE_MAX_AGE,
        path="/",
    )


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login_with_google(
    response: Response,
    body: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify Google ID token → create or update user → set JWT in httpOnly cookie.
    Called by the frontend after NextAuth Google sign-in.
    """
    if not _verify_invite(body.invite_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Private beta requires a valid invite code.",
        )

    google_data = await verify_google_token(body.id_token)
    google_id = google_data["sub"]
    email = google_data.get("email", "")
    name = google_data.get("name", "")
    picture = google_data.get("picture", "")

    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if user:
        user.last_login = datetime.now(timezone.utc)
        user.name = name or user.name
        user.avatar_url = picture or user.avatar_url
    else:
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

    access_token = create_access_token(user.id, user.email)
    _set_session_cookie(response, access_token)

    return LoginResponse(user_id=user.id, name=user.name, email=user.email)


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "ok"}


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
        "country": user.country,
        "state": user.state,
        "experience_level": user.experience_level,
        "queries_used_this_month": user.queries_used_this_month or 0,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
