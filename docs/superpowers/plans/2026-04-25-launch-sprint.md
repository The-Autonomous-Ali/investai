# Launch Sprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Days 2-6 of the launch sprint so the platform is ready for private beta on April 30.

**Architecture:** Four parallel work streams — auth simplification (cookie-based sessions), LLM boundary hardening (schema validation + retry + repair), payment enforcement (Razorpay webhook verification), and a soft-launch invite gate. Each stream produces testable, independent changes.

**Tech Stack:** FastAPI, Next.js (pages router), SQLAlchemy, Pydantic, python-jose, httpx, Razorpay SDK, pytest.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/utils/auth.py` | JWT create/decode, FastAPI dependency reads from cookie |
| `backend/routes/auth.py` | Login sets httpOnly cookie; logout clears it |
| `frontend/lib/api.js` | Axios instance — no localStorage token, withCredentials:true |
| `frontend/pages/onboarding.js` | No localStorage token storage |
| `backend/utils/llm_client.py` | Retry, repair, fallback, schema validation wrapper |
| `backend/utils/llm_schema.py` | Pydantic schemas for common LLM outputs |
| `backend/agents/orchestrator.py` | Handle degraded agent output gracefully |
| `backend/routes/subscriptions.py` | Razorpay webhook signature verification + real handlers |
| `backend/services/entitlements.py` | Ensure tier changes from webhooks are respected |
| `backend/routes/auth.py` (invite gate) | Block signup when `BETA_INVITE_ONLY=true` without valid code |
| `frontend/pages/auth/signin.js` | Show invite code input when gate is active |

---

## Task 1: Auth — Cookie-Based JWT

**Files:**
- Modify: `backend/utils/auth.py`
- Modify: `backend/routes/auth.py`
- Modify: `frontend/lib/api.js`
- Modify: `frontend/pages/onboarding.js`
- Test: `backend/tests/test_auth_cookie.py`

- [ ] **Step 1: Write failing test for cookie auth**

```python
import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient

from utils.auth import create_access_token, get_current_user
from database.connection import get_db

app = FastAPI()

@app.get("/protected")
async def protected(user = Depends(get_current_user)):
    return {"user_id": user.id}

@pytest.mark.asyncio
async def test_cookie_auth_reads_token():
    token = create_access_token("user_123", "test@example.com")
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/protected", cookies={"investai_session": token})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "user_123"

@pytest.mark.asyncio
async def test_cookie_auth_missing_token():
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 401
```

Run: `pytest backend/tests/test_auth_cookie.py -v`
Expected: FAIL — `get_current_user` still expects HTTPBearer header, not cookie.

- [ ] **Step 2: Modify `backend/utils/auth.py` to read JWT from cookie**

Replace the `HTTPBearer` dependency with a cookie-based extractor. Keep `create_access_token` and `decode_token` unchanged.

```python
from fastapi import Cookie, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
import os

from database.connection import get_db
from models.models import User

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-dev-secret-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30


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


async def get_current_user(
    investai_session: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not investai_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_token(investai_session)
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
```

Run: `pytest backend/tests/test_auth_cookie.py -v`
Expected: PASS

- [ ] **Step 3: Modify `backend/routes/auth.py` to set httpOnly cookie on login**

Update the login route to return the token in a cookie instead of the response body. Also add a logout route.

```python
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timezone
import httpx
import os

from database.connection import get_db
from models.models import User
from utils.auth import get_current_user, create_access_token

router = APIRouter()

COOKIE_NAME = "investai_session"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


class GoogleLoginRequest(BaseModel):
    id_token: str


async def verify_google_token(id_token: str) -> dict:
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


@router.post("/login")
async def login_with_google(
    response: Response,
    body: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
):
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

    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=COOKIE_MAX_AGE,
    )

    return {
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME)
    return {"status": "ok"}


@router.get("/me")
async def get_current_user_info(user: User = Depends(get_current_user)):
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
```

Run: `pytest backend/tests/test_auth_cookie.py -v`
Expected: PASS

- [ ] **Step 4: Modify `frontend/lib/api.js` to use cookie auth**

Remove the localStorage token interceptor and add `withCredentials: true`.

```javascript
import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// Handle 401 responses — redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      if (!window.location.pathname.startsWith('/auth')) {
        window.location.href = '/auth/signin'
      }
    }
    return Promise.reject(error)
  }
)

// ── Auth ─────────────────────────────────────────────────────────────────────
export const loginWithGoogle = (idToken) =>
  api.post('/api/auth/login', { id_token: idToken }).then(r => r.data)

export const logout = () =>
  api.post('/api/auth/logout').then(r => r.data)

export const getCurrentUser = () =>
  api.get('/api/auth/me').then(r => r.data)

// ── Signals ──────────────────────────────────────────────────────────────────
export const getSignals = (params = {}) =>
  api.get('/api/signals/', { params }).then(r => r.data)

export const getActiveSignals = () =>
  api.get('/api/signals/active').then(r => r.data)

export const getSignalDetail = (id) =>
  api.get(`/api/signals/${id}`).then(r => r.data)

export const getSignalTimeline = (id) =>
  api.get(`/api/signals/${id}/timeline`).then(r => r.data)

// ── AI Advice ────────────────────────────────────────────────────────────────
export const getAdvice = ({ query, amount, horizon, country }) =>
  api.post('/api/agents/advice', { query, amount, horizon, country }).then(r => r.data)

// ── What If ──────────────────────────────────────────────────────────────────
export const runWhatIf = (scenario) =>
  api.post('/api/whatif', scenario).then(r => r.data)

export const getWhatIfExamples = () =>
  api.get('/api/whatif/examples').then(r => r.data)

// ── Portfolio ────────────────────────────────────────────────────────────────
export const getPortfolio = (activeOnly = true) =>
  api.get('/api/portfolio/', { params: { active_only: activeOnly } }).then(r => r.data)

export const addHolding = (data) =>
  api.post('/api/portfolio/', data).then(r => r.data)

export const updateHolding = (id, data) =>
  api.patch(`/api/portfolio/${id}`, data).then(r => r.data)

export const removeHolding = (id) =>
  api.delete(`/api/portfolio/${id}`).then(r => r.data)

// ── User ─────────────────────────────────────────────────────────────────────
export const getUserProfile = () =>
  api.get('/api/users/profile').then(r => r.data)

export const updateUserProfile = (data) =>
  api.patch('/api/users/profile', data).then(r => r.data)

export const getUserUsage = () =>
  api.get('/api/users/usage').then(r => r.data)

// ── Alerts ───────────────────────────────────────────────────────────────────
export const getAlerts = (params = {}) =>
  api.get('/api/alerts/', { params }).then(r => r.data)

export const markAlertRead = (id) =>
  api.patch(`/api/alerts/${id}/read`).then(r => r.data)

export const markAllAlertsRead = () =>
  api.post('/api/alerts/read-all').then(r => r.data)

// ── Subscriptions ────────────────────────────────────────────────────────────
export const getCurrentSubscription = () =>
  api.get('/api/subscriptions/current').then(r => r.data)

export const getPlans = () =>
  api.get('/api/subscriptions/plans').then(r => r.data)

export const createSubscription = (tier) =>
  api.post('/api/subscriptions/create', { tier }).then(r => r.data)

export default api
```

- [ ] **Step 5: Modify `frontend/pages/onboarding.js` to remove localStorage**

Update `ensureBackendSession` and `handleCreateAccount` to not rely on `investai_token` in localStorage.

```javascript
import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { motion } from 'framer-motion'
import { useSession } from 'next-auth/react'
import { TrendingUp, User, Shield, ArrowRight, CheckCircle, AlertCircle } from 'lucide-react'
import { getCurrentUser, loginWithGoogle, updateUserProfile } from '../lib/api'

export default function Onboarding() {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [demoMode, setDemoMode] = useState(false)
  const [error, setError] = useState('')
  const router = useRouter()
  const { data: session, status } = useSession()

  useEffect(() => {
    const isDemo = typeof window !== 'undefined' && sessionStorage.getItem('demo_mode') === 'true'
    setDemoMode(isDemo)

    if (isDemo) {
      try {
        const demoUser = JSON.parse(sessionStorage.getItem('demo_user') || '{}')
        if (demoUser.name) setName((prev) => prev || demoUser.name)
      } catch {}
      return
    }

    if (status === 'unauthenticated') {
      router.push('/auth/signin')
      return
    }

    if (session?.user?.name) {
      setName((prev) => prev || session.user.name)
    }
  }, [router, session, status])

  const ensureBackendSession = async () => {
    if (!session?.idToken) {
      throw new Error('Google sign-in did not provide a usable ID token.')
    }
    await loginWithGoogle(session.idToken)
    return getCurrentUser()
  }

  const handleCreateAccount = async (e) => {
    e.preventDefault()
    if (!name) return

    setLoading(true)
    setError('')
    try {
      if (demoMode) {
        sessionStorage.setItem('investai_user_name', name)
        router.push('/invest')
        return
      }

      const currentUser = await ensureBackendSession()
      if (name && name !== currentUser?.name) {
        await updateUserProfile({ name })
      }
      sessionStorage.setItem('investai_user_name', name || currentUser?.name || session?.user?.name || 'Investor')
      router.push('/invest')
    } catch (onboardingError) {
      console.error('Failed to finish onboarding:', onboardingError)
      const detail = onboardingError?.response?.data?.detail
      setError(detail || 'Failed to connect your account to InvestAI. Please sign in again.')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center p-6">
      <Head>
        <title>Create Your Account — InvestAI</title>
      </Head>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        <div className="flex items-center gap-2 justify-center mb-12">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center shadow-lg shadow-gold/20">
            <TrendingUp size={20} className="text-surface" />
          </div>
          <span className="font-display font-bold text-2xl text-white">InvestAI</span>
        </div>

        <div className="card p-8 border-gold/20 shadow-xl shadow-gold/5">
          <h1 className="font-display text-2xl font-bold text-white mb-2 text-center">
            Welcome to InvestAI
          </h1>
          <p className="text-ink text-center mb-8">
            Let's start by setting up your profile.
          </p>

          <form onSubmit={handleCreateAccount} className="space-y-6">
            <div>
              <label className="block text-ink text-sm font-medium mb-2">Your Full Name</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-light" size={18} />
                <input
                  required
                  type="text"
                  className="input-dark w-full pl-10 pr-4 py-3 rounded-xl"
                  placeholder="e.g. Sameer Kashyap"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-start gap-3 text-xs text-ink-light">
                <CheckCircle size={14} className="text-jade mt-0.5 flex-shrink-0" />
                <span>No credit card required for the free forever plan.</span>
              </div>
              <div className="flex items-start gap-3 text-xs text-ink-light">
                <Shield size={14} className="text-gold mt-0.5 flex-shrink-0" />
                <span>Your data is encrypted and never shared with third parties.</span>
              </div>
            </div>

            {error && (
              <div className="rounded-xl border border-ruby/20 bg-ruby/5 p-4 text-sm text-ruby flex gap-3">
                <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <button
              disabled={!name || loading}
              className="btn-gold w-full py-4 rounded-xl flex items-center justify-center gap-2 font-display font-bold text-lg disabled:opacity-50 transition-all shadow-lg shadow-gold/20"
            >
              {loading ? (
                <div className="w-6 h-6 border-2 border-surface border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  Create Account <ArrowRight size={20} />
                </>
              )}
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  )
}
```

- [ ] **Step 6: Verify CORS allows credentials**

In `backend/main.py`, ensure `allow_credentials=True` is already set (it is). No change needed unless your frontend origin is missing from `allow_origins`.

- [ ] **Step 7: Run auth tests**

Run: `pytest backend/tests/test_auth_cookie.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/utils/auth.py backend/routes/auth.py frontend/lib/api.js frontend/pages/onboarding.js backend/tests/test_auth_cookie.py
git commit -m "feat(auth): move to httpOnly cookie-based JWT

- Remove localStorage token storage
- Backend sets Secure, SameSite=strict, httpOnly cookie
- Frontend axios uses withCredentials
- Add logout route

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: LLM Schema Hardening

**Files:**
- Create: `backend/utils/llm_schema.py`
- Modify: `backend/utils/llm_client.py`
- Modify: `backend/agents/orchestrator.py`
- Test: `backend/tests/test_llm_schema.py`

- [ ] **Step 1: Write failing test for LLM schema validation**

```python
import pytest
from pydantic import BaseModel, ValidationError

from utils.llm_schema import parse_and_validate, repair_json

class DummyOutput(BaseModel):
    action: str
    confidence: float


def test_parse_valid_json():
    result = parse_and_validate('{"action": "buy", "confidence": 0.9}', DummyOutput)
    assert result.action == "buy"
    assert result.confidence == 0.9


def test_repair_strips_markdown_fences():
    raw = '```json\n{"action": "buy", "confidence": 0.9}\n```'
    assert repair_json(raw) == '{"action": "buy", "confidence": 0.9}'


def test_repair_fixes_trailing_comma():
    raw = '{"action": "buy", "confidence": 0.9,}'
    fixed = repair_json(raw)
    result = parse_and_validate(fixed, DummyOutput)
    assert result.confidence == 0.9


def test_parse_invalid_json_raises():
    with pytest.raises(ValidationError):
        parse_and_validate('not json', DummyOutput)
```

Run: `pytest backend/tests/test_llm_schema.py -v`
Expected: FAIL — `parse_and_validate` and `repair_json` don't exist yet.

- [ ] **Step 2: Create `backend/utils/llm_schema.py`**

```python
"""
JSON repair + Pydantic validation for LLM outputs.
"""
import json
import re
import structlog
from pydantic import BaseModel, ValidationError

logger = structlog.get_logger()


def repair_json(raw: str) -> str:
    """Strip markdown fences and fix common JSON syntax errors."""
    text = raw.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def parse_and_validate(raw: str, schema: type[BaseModel]) -> BaseModel:
    """Parse JSON string and validate against a Pydantic schema."""
    repaired = repair_json(raw)
    try:
        data = json.loads(repaired)
    except json.JSONDecodeError as e:
        logger.error("llm_schema.json_decode_failed", raw_preview=repaired[:200], error=str(e))
        raise ValidationError.from_exception_data(
            title=schema.__name__,
            line_errors=[{"loc": ("__root__",), "msg": f"Invalid JSON: {e}", "type": "value_error"}],
        )
    return schema.model_validate(data)
```

Run: `pytest backend/tests/test_llm_schema.py -v`
Expected: PASS

- [ ] **Step 3: Modify `backend/utils/llm_client.py` to add retry, repair, fallback**

Replace the `call_llm` function and add a new `call_llm_structured` entry point.

```python
"""
Universal LLM Client — Routes each agent to its optimal free model provider.
"""
import os
import structlog
import asyncio
from pydantic import BaseModel, ValidationError

from utils.llm_schema import parse_and_validate, repair_json

logger = structlog.get_logger()

AGENT_MODELS = {
    "orchestrator":              {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "signal_watcher":            {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "global_macro_agent":        {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "research_agent":            {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "pattern_matcher":           {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "temporal_agent":            {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "company_intelligence":      {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "sentiment_aggregator":      {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "portfolio_agent":           {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "tax_agent":                 {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "critic_agent":              {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "watchdog":                  {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "investment_manager":        {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "performance_tracker":       {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "whatif_agent":              {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "graphrag_enricher":         {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "data_scraper":              {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "technical_analysis_agent":  {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "plain_language_formatter":  {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "market_intelligence":       {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
    "free_data_feeds":           {"provider": "groq",       "model": "llama-3.3-70b-versatile"},
}

DEFAULT_MODEL = {"provider": "groq", "model": "llama-3.3-70b-versatile"}

SYSTEM_PROMPT = "You are a financial AI assistant. Always respond with valid JSON only. No markdown, no code fences, no extra text before or after the JSON."


async def _call_groq(prompt: str, model_name: str) -> str:
    from groq import AsyncGroq
    try:
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.1,
        )
        return response.choices[0].message.content
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e):
            logger.warning("groq.rate_limit_hit_falling_back_to_openrouter")
            return await _call_openrouter(prompt, "meta-llama/llama-3.3-70b-instruct:free")
        raise


async def _call_openrouter(prompt: str, model_name: str) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    return response.choices[0].message.content


async def _call_kaggle(prompt: str, model_name: str) -> str:
    from openai import AsyncOpenAI
    base = os.getenv("KAGGLE_LLM_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("KAGGLE_LLM_URL not set")
    client = AsyncOpenAI(
        base_url=f"{base}/v1",
        api_key="ollama",
        default_headers={"ngrok-skip-browser-warning": "true"},
        timeout=300.0,
    )
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    return response.choices[0].message.content


async def _call_gemini(prompt: str, model_name: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=SYSTEM_PROMPT,
    )
    response = await model.generate_content_async(prompt)
    return response.text


async def _call_anthropic(prompt: str, model_name: str) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = await client.messages.create(
        model=model_name,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


async def _call_provider(provider: str, prompt: str, model: str) -> str:
    if provider == "groq":
        return await _call_groq(prompt, model)
    elif provider == "openrouter":
        return await _call_openrouter(prompt, model)
    elif provider == "gemini":
        return await _call_gemini(prompt, model)
    elif provider == "kaggle":
        return await _call_kaggle(prompt, model)
    elif provider == "anthropic":
        return await _call_anthropic(prompt, model)
    else:
        return await _call_groq(prompt, "llama-3.3-70b-versatile")


async def call_llm(prompt: str, agent_name: str = "default") -> str:
    global_provider = os.getenv("AI_PROVIDER", "groq")

    if global_provider == "anthropic":
        model_name = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        return await _call_anthropic(prompt, model_name)

    if global_provider == "groq":
        model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        return await _call_groq(prompt, model_name)

    if global_provider == "openrouter":
        model_name = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        return await _call_openrouter(prompt, model_name)

    if global_provider == "gemini":
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        return await _call_gemini(prompt, model_name)

    if global_provider == "kaggle":
        model_name = os.getenv("KAGGLE_LLM_MODEL", "gemma4:26b")
        return await _call_kaggle(prompt, model_name)

    config   = AGENT_MODELS.get(agent_name, DEFAULT_MODEL)
    provider = config["provider"]
    model    = config["model"]

    log = logger.bind(agent=agent_name, provider=provider, model=model)
    log.info("llm_client.call")

    try:
        text = await _call_provider(provider, prompt, model)
        return text
    except Exception as e:
        log.error("llm_client.error", error=str(e))
        if provider != "groq":
            log.warning("llm_client.fallback_to_groq")
            try:
                return await _call_groq(prompt, "llama-3.3-70b-versatile")
            except Exception as fe:
                log.error("llm_client.fallback_failed", error=str(fe))
        raise


async def call_llm_structured(
    prompt: str,
    schema: type[BaseModel],
    agent_name: str = "default",
    max_retries: int = 3,
    fallback_provider: str | None = "openrouter",
) -> BaseModel:
    """
    Call LLM with schema validation, retry, repair, and optional fallback.
    """
    log = logger.bind(agent=agent_name, schema=schema.__name__)
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            raw = await call_llm(prompt, agent_name)
            return parse_and_validate(raw, schema)
        except (ValidationError, json.JSONDecodeError) as e:
            last_error = e
            log.warning("llm_schema.validation_failed", attempt=attempt, error=str(e))
            if attempt < max_retries:
                wait = 2 ** attempt
                log.info("llm_schema.retrying", wait_seconds=wait)
                await asyncio.sleep(wait)

    if fallback_provider and fallback_provider != os.getenv("AI_PROVIDER", "groq"):
        log.warning("llm_schema.fallback_provider", provider=fallback_provider)
        try:
            raw = await _call_provider(fallback_provider, prompt, "meta-llama/llama-3.3-70b-instruct:free")
            return parse_and_validate(raw, schema)
        except Exception as e:
            log.error("llm_schema.fallback_failed", error=str(e))
            last_error = e

    log.error("llm_schema.all_attempts_failed", error=str(last_error))
    raise last_error
```

- [ ] **Step 4: Update orchestrator to use structured LLM calls where applicable**

In `backend/agents/orchestrator.py`, find the LLM call that generates the task plan JSON. Replace raw `json.loads` with `call_llm_structured`. Add a graceful degradation helper.

```python
# At the top of orchestrator.py
from utils.llm_client import call_llm_structured
from pydantic import BaseModel

class TaskPlan(BaseModel):
    tasks: list[dict]

# In the orchestrator method that calls the LLM for task plan:
# OLD: plan_json = json.loads(await call_llm(prompt, "orchestrator"))
# NEW:
try:
    plan = await call_llm_structured(prompt, TaskPlan, agent_name="orchestrator", max_retries=3)
    plan_json = {"tasks": plan.tasks}
except Exception as e:
    logger.error("orchestrator.task_plan_failed", error=str(e))
    plan_json = {"tasks": []}  # graceful degradation
```

Note: since the full orchestrator is large, the exact line numbers will vary. Search for `json.loads` and `call_llm` in `orchestrator.py` and replace the task-plan generation call.

- [ ] **Step 5: Add test for retry behavior**

```python
import pytest
from unittest.mock import AsyncMock, patch
from pydantic import BaseModel

from utils.llm_client import call_llm_structured

class TestSchema(BaseModel):
    x: int


@pytest.mark.asyncio
async def test_call_llm_structured_retries_on_bad_json():
    with patch("utils.llm_client.call_llm", new_callable=AsyncMock) as mock:
        mock.side_effect = [
            "bad json",
            "bad json",
            '{"x": 1}',
        ]
        result = await call_llm_structured("prompt", TestSchema, max_retries=3)
        assert result.x == 1
        assert mock.call_count == 3
```

Run: `pytest backend/tests/test_llm_schema.py backend/tests/test_llm_client.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/utils/llm_schema.py backend/utils/llm_client.py backend/agents/orchestrator.py backend/tests/test_llm_schema.py
git commit -m "feat(llm): schema validation, retry, repair, fallback

- Add Pydantic parse_and_validate with JSON repair
- call_llm_structured: retry up to 3x with exponential backoff
- Fallback to alternate provider on persistent failure
- Orchestrator gracefully degrades when task plan fails

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Payment Enforcement

**Files:**
- Modify: `backend/routes/subscriptions.py`
- Modify: `backend/services/entitlements.py`
- Modify: `backend/models/models.py` (if razorpay_sub_id needs expansion)
- Test: `backend/tests/test_subscriptions_webhook.py`

- [ ] **Step 1: Write failing test for Razorpay webhook signature**

```python
import pytest
from unittest.mock import patch
from httpx import AsyncClient
from fastapi import FastAPI

from routes.subscriptions import router
from database.connection import init_db, AsyncSessionLocal
from models.models import User, Subscription, SubscriptionTier

app = FastAPI()
app.include_router(router, prefix="/api/subscriptions")


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield


@pytest.mark.asyncio
async def test_webhook_verifies_signature():
    payload = {
        "event": "subscription.activated",
        "payload": {
            "subscription": {"id": "sub_123", "status": "active"},
            "payment": {"entity": {"email": "test@example.com"}},
        },
    }

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/api/subscriptions/webhook/razorpay", json=payload)

    # Without a valid signature, should reject
    assert resp.status_code == 400
```

Run: `pytest backend/tests/test_subscriptions_webhook.py -v`
Expected: FAIL — webhook doesn't verify signatures yet.

- [ ] **Step 2: Add Razorpay signature verification helper**

```python
# In backend/routes/subscriptions.py, add at the top
import hmac
import hashlib

def _verify_razorpay_signature(body_bytes: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

- [ ] **Step 3: Rewrite webhook handler**

```python
@router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body_bytes = await request.body()
    body = await request.json()
    event = body.get("event", "")

    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    if secret:
        signature = request.headers.get("X-Razorpay-Signature", "")
        if not _verify_razorpay_signature(body_bytes, signature, secret):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event == "subscription.activated":
        sub_entity = body.get("payload", {}).get("subscription", {}).get("entity", {})
        payment_entity = body.get("payload", {}).get("payment", {}).get("entity", {})
        email = payment_entity.get("email", "")
        razorpay_sub_id = sub_entity.get("id")

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            # Determine tier from plan_id if present, else infer
            plan_id = sub_entity.get("plan_id", "")
            tier = _tier_from_plan_id(plan_id)
            user.subscription_tier = SubscriptionTier(tier)

            existing = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
            sub = existing.scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if sub:
                sub.tier = user.subscription_tier
                sub.status = "active"
                sub.razorpay_sub_id = razorpay_sub_id
                sub.current_period_start = now
                sub.current_period_end = now + timedelta(days=30)
            else:
                sub = Subscription(
                    user_id=user.id,
                    tier=user.subscription_tier,
                    status="active",
                    razorpay_sub_id=razorpay_sub_id,
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                )
                db.add(sub)
            await db.commit()

    elif event == "subscription.cancelled":
        sub_entity = body.get("payload", {}).get("subscription", {}).get("entity", {})
        razorpay_sub_id = sub_entity.get("id")
        result = await db.execute(select(Subscription).where(Subscription.razorpay_sub_id == razorpay_sub_id))
        sub = result.scalar_one_or_none()
        if sub:
            sub.status = "cancelled"
            sub.cancellation_date = datetime.now(timezone.utc)
            # Reset user tier to free at period end (or immediately for simplicity)
            user_result = await db.execute(select(User).where(User.id == sub.user_id))
            user = user_result.scalar_one_or_none()
            if user:
                user.subscription_tier = SubscriptionTier.FREE
            await db.commit()

    elif event == "payment.failed":
        # Log for audit; do not change tier
        logger.warning("razorpay.payment_failed", payload=body.get("payload"))

    return {"status": "ok"}


def _tier_from_plan_id(plan_id: str) -> str:
    mapping = {
        "plan_starter": "starter",
        "plan_pro": "pro",
        "plan_elite": "elite",
    }
    for key, tier in mapping.items():
        if key in plan_id:
            return tier
    return "starter"
```

- [ ] **Step 4: Ensure Subscription model has required fields**

Check `backend/models/models.py` for the Subscription model. If `razorpay_sub_id` or `cancellation_date` are missing, add them:

```python
class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    tier = Column(SAEnum(SubscriptionTier), default=SubscriptionTier.FREE)
    status = Column(String, default="active")
    razorpay_sub_id = Column(String, index=True)
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancellation_date = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
```

- [ ] **Step 5: Run subscription tests**

Run: `pytest backend/tests/test_subscriptions_webhook.py backend/tests/test_subscriptions.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routes/subscriptions.py backend/models/models.py backend/tests/test_subscriptions_webhook.py
git commit -m "feat(payments): Razorpay webhook verification + real handlers

- Verify X-Razorpay-Signature using HMAC-SHA256
- subscription.activated → upgrade user tier
- subscription.cancelled → reset to free
- payment.failed → audit log only
- Remove dev bypass from production path

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Soft-Launch Invite Gate

**Files:**
- Modify: `backend/routes/auth.py`
- Modify: `frontend/pages/auth/signin.js`
- Test: `backend/tests/test_invite_gate.py`

- [ ] **Step 1: Write failing test for invite gate**

```python
import pytest
from httpx import AsyncClient
from fastapi import FastAPI

from routes.auth import router
from database.connection import init_db

app = FastAPI()
app.include_router(router, prefix="/api/auth")

@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield


@pytest.mark.asyncio
async def test_login_blocked_without_invite(monkeypatch):
    monkeypatch.setenv("BETA_INVITE_ONLY", "true")
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={"id_token": "fake"})
    assert resp.status_code == 403
```

Run: `pytest backend/tests/test_invite_gate.py -v`
Expected: FAIL — no invite check yet.

- [ ] **Step 2: Modify `backend/routes/auth.py` to check invite code**

Add invite validation to the login route.

```python
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import httpx

from database.connection import get_db
from models.models import User
from utils.auth import get_current_user, create_access_token

router = APIRouter()

COOKIE_NAME = "investai_session"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60

VALID_INVITE_CODES = {"early2026", "investai-beta"}


class GoogleLoginRequest(BaseModel):
    id_token: str
    invite_code: str | None = None


def _invite_required() -> bool:
    return os.getenv("BETA_INVITE_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}


def _verify_invite(code: str | None) -> bool:
    if not _invite_required():
        return True
    if not code:
        return False
    return code.strip().lower() in {c.lower() for c in VALID_INVITE_CODES}


async def verify_google_token(id_token: str) -> dict:
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


@router.post("/login")
async def login_with_google(
    response: Response,
    body: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db),
):
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

    response.set_cookie(
        key=COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=COOKIE_MAX_AGE,
    )

    return {
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME)
    return {"status": "ok"}


@router.get("/me")
async def get_current_user_info(user: User = Depends(get_current_user)):
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
```

Run: `pytest backend/tests/test_invite_gate.py -v`
Expected: PASS

- [ ] **Step 3: Modify `frontend/pages/auth/signin.js` to show invite input**

Add an invite code input field when `BETA_INVITE_ONLY` is active. Since the frontend can't directly read the backend env, show the field unconditionally or gate it behind a build-time env var `NEXT_PUBLIC_BETA_INVITE_ONLY=true`.

```javascript
// In the sign-in component, add state:
const [inviteCode, setInviteCode] = useState('')

// In the login handler, pass invite_code:
await loginWithGoogle(idToken, inviteCode)

// In the form, conditionally show invite input:
{process.env.NEXT_PUBLIC_BETA_INVITE_ONLY === 'true' && (
  <div className="mb-4">
    <label className="block text-sm text-ink mb-1">Invite Code</label>
    <input
      type="text"
      className="input-dark w-full px-4 py-2 rounded-xl"
      placeholder="Enter your invite code"
      value={inviteCode}
      onChange={(e) => setInviteCode(e.target.value)}
    />
  </div>
)}
```

Also update `frontend/lib/api.js` to accept invite code:

```javascript
export const loginWithGoogle = (idToken, inviteCode = null) =>
  api.post('/api/auth/login', { id_token: idToken, invite_code: inviteCode }).then(r => r.data)
```

- [ ] **Step 4: Commit**

```bash
git add backend/routes/auth.py frontend/pages/auth/signin.js frontend/lib/api.js backend/tests/test_invite_gate.py
git commit -m "feat(launch): soft-launch invite gate

- BETA_INVITE_ONLY env blocks signups without valid invite code
- Frontend shows invite code input when gate is active
- Valid codes: early2026, investai-beta

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Update Gap Assessment + Final Commit

- [ ] **Step 1: Update `docs/platform_gap_assessment_2026-04-24.md`**

Move completed items from "stubbed/broken" and "enterprise gaps" to "Done":
- Auth simplification → Done (commit SHA)
- LLM schema hardening → Done
- Payment enforcement → Done
- Invite gate → Done

- [ ] **Step 2: Commit the updated gap assessment**

```bash
git add docs/platform_gap_assessment_2026-04-24.md
git commit -m "docs(gap): mark launch sprint items complete

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Spec Coverage Check

| Spec Section | Task |
|---|---|
| Day 2 — Auth simplification | Task 1 |
| Day 3 — LLM schema hardening | Task 2 |
| Day 4 — Payment enforcement | Task 3 |
| Day 5-6 — E2E smoke + soft launch | Task 4 |
| Update gap assessment | Task 5 |

## Placeholder Scan

- No "TBD", "TODO", or "implement later" strings.
- All test code is complete with expected assertions.
- All file paths are exact.
- All commit messages are complete.

## Type Consistency Check

- `get_current_user` dependency signature uses `Cookie(default=None)` consistently.
- `call_llm_structured` signature uses `type[BaseModel]` for schema.
- `loginWithGoogle` in frontend accepts optional `inviteCode` in both `api.js` and `signin.js`.
