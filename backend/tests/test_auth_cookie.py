"""Cookie-based JWT auth tests.

Verifies that get_current_user reads the session token from the
investai_session cookie (and the legacy Bearer header) and rejects
unauthenticated requests.
"""
import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock

from utils.auth import create_access_token, get_current_user
from database.connection import get_db


def _build_app(stub_user) -> FastAPI:
    app = FastAPI()

    async def _override_db():
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=stub_user)
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_db] = _override_db

    @app.get("/protected")
    async def protected(user=Depends(get_current_user)):
        return {"user_id": user.id, "email": user.email}

    return app


@pytest.mark.asyncio
async def test_cookie_auth_reads_token():
    stub_user = MagicMock(id="user_123", email="test@example.com")
    app = _build_app(stub_user)
    token = create_access_token("user_123", "test@example.com")

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/protected", cookies={"investai_session": token})

    assert resp.status_code == 200
    assert resp.json()["user_id"] == "user_123"


@pytest.mark.asyncio
async def test_cookie_auth_missing_token_rejected():
    app = _build_app(stub_user=None)

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/protected")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_cookie_auth_invalid_token_rejected():
    app = _build_app(stub_user=None)

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/protected", cookies={"investai_session": "not-a-jwt"})

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_legacy_bearer_header_still_accepted():
    """During migration, the Authorization header keeps working."""
    stub_user = MagicMock(id="user_456", email="legacy@example.com")
    app = _build_app(stub_user)
    token = create_access_token("user_456", "legacy@example.com")

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert resp.json()["user_id"] == "user_456"


@pytest.mark.asyncio
async def test_user_not_found_in_db_rejected():
    app = _build_app(stub_user=None)
    token = create_access_token("ghost_user", "ghost@example.com")

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/protected", cookies={"investai_session": token})

    assert resp.status_code == 401
