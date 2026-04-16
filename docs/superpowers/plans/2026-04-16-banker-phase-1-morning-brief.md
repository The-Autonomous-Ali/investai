# 24/7 Banker — Phase 1: Email Morning Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working email morning brief that lands in the user's inbox at 09:00 IST every day, summarising overnight events that affect their stated holdings. Smallest end-to-end vertical slice that proves the 24/7 banker loop.

**Architecture:** Reuse existing `AdviceRecord` + `AdviceSignalLink` tables (already populated since the demo_user fix) → add a `MorningBriefBuilder` service that compiles a brief from recent records + changed signals → push through a thin `EmailSender` provider abstraction (Resend HTTP API, free tier) → schedule daily via existing `worker.py` APScheduler.

**Tech Stack:** FastAPI, SQLAlchemy async, APScheduler (already in worker.py), Resend HTTP API (free tier), pytest + pytest-asyncio (existing conftest.py).

**Spec reference:** `docs/superpowers/specs/2026-04-16-24-7-banker-design.md` §12 (delivery), §15 (memory), §17 (architecture), §20 (build state).

**Phasing context:** This is Phase 1 of 4 phases. Phase 2 = trust layer + signal feed expansion. Phase 3 = web push + thesis-break alerts. Phase 4 = frontend rebuild (WhatsApp-style feed + onboarding + tap-to-explain). Each phase ships independently usable software.

---

## File Structure

### New files
- `backend/services/morning_brief_builder.py` — assembles brief data for a user
- `backend/services/email_sender.py` — thin provider abstraction (Resend in v1)
- `backend/services/email_templates/morning_brief.py` — HTML+text template renderer
- `backend/tests/test_morning_brief_builder.py`
- `backend/tests/test_email_sender.py`
- `backend/tests/test_morning_brief_template.py`

### Modified files
- `backend/worker.py` — add `send_morning_briefs` job at 03:30 UTC (= 09:00 IST)
- `backend/requirements.txt` — add `resend`
- `backend/.env.example` — add `RESEND_API_KEY`, `MORNING_BRIEF_FROM_EMAIL`
- `frontend/pages/advice.js` — replace `MOCK_ADVICE` constant with real `/api/agents/advice` fetch
- `backend/models/models.py` — small addition to `User.notification_prefs` JSON shape (no migration; JSON is flexible)

### Untouched (re-used as-is)
- `backend/models/models.py` — `AdviceRecord`, `AdviceSignalLink`, `User`
- `backend/services/signal_monitor.py` — already updates `AdviceSignalLink.current_status`
- `backend/agents/agents_impl.py` — `store_advice` already persists records since the demo_user fix
- `backend/main.py` — `ensure_demo_user` already in lifespan

---

## Task 1: Sanity-check the demo_user fix actually persists advice

**Goal:** Before writing any new code, confirm the 2026-04-16 silent-skip fix actually lands rows in `advice_records`. Without this, every later task is built on quicksand.

**Files:** none modified (verification only)

- [ ] **Step 1: Start backend locally**

```bash
cd backend
docker compose up -d   # if using docker compose from repo root
# OR
uvicorn main:app --reload --port 8000
```

Expected: backend starts, log line `demo_user.seeded` appears (or no error if user already exists).

- [ ] **Step 2: Hit the advice endpoint with a minimal payload**

```bash
curl -s -X POST http://localhost:8000/api/agents/advice \
  -H "Content-Type: application/json" \
  -d '{"query":"I want to invest 50k for 1 year","amount":50000,"horizon":"1 year","country":"India"}' \
  | head -c 500
```

Expected: HTTP 200 with `"success": true` (or `"success": false` with a rate-limit error from Groq/OpenRouter — that's still acceptable for this verification because we're proving the pipeline runs and the user lookup works).

- [ ] **Step 3: Confirm at least one row landed in `advice_records`**

```bash
docker compose exec postgres psql -U investai -d investai \
  -c "SELECT id, user_id, LEFT(narrative, 80) FROM advice_records ORDER BY created_at DESC LIMIT 3;"
```

Expected: at least one row with `user_id = 'demo_user'`. If empty, the silent-skip is back — STOP and re-investigate `store_advice` in `backend/agents/agents_impl.py`.

- [ ] **Step 4: Commit a verification log so the next session knows this was checked**

No file change needed for this task. Continue to Task 2.

---

## Task 2: Replace `MOCK_ADVICE` in `advice.js` with a real API fetch

**Goal:** The advice page currently shows hardcoded mock data regardless of backend state — this masks broken UX. Wire it to the real `/api/agents/advice` endpoint.

**Files:**
- Modify: `frontend/pages/advice.js` — remove `const advice = MOCK_ADVICE` at line ~254, replace with a fetch + state. Mock object lines 10-242 can stay temporarily as a fallback shape reference.

- [ ] **Step 1: Add fetch state to the AdvicePage component**

Replace the existing component definition (around line 252) with:

```javascript
export default function AdvicePage() {
  const [activeTab, setActiveTab] = useState('strategy')
  const [advice, setAdvice] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/agents/advice`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      signal: controller.signal,
      body: JSON.stringify({
        query: 'I want to invest for 1 year',
        amount: 100000,
        horizon: '1 year',
        country: 'India',
      }),
    })
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || 'Advice failed')
        setAdvice(data.recommendation)
        setLoading(false)
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          setError(err.message)
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [])

  if (loading) return <div className="min-h-screen bg-surface flex items-center justify-center text-ink">Loading analysis...</div>
  if (error)   return <div className="min-h-screen bg-surface flex items-center justify-center text-red-400">Error: {error}</div>
  if (!advice) return null

  // ... rest of the existing return JSX unchanged ...
}
```

Add `useEffect` to the import on line 2: `import { useState, useEffect } from 'react'`.

- [ ] **Step 2: Manual smoke test in browser**

```bash
cd frontend && npm run dev
# Open http://localhost:3000/advice in a browser
```

Expected: spinner for ~5-30s while the orchestrator runs, then the real advice page renders. If you see "Loading analysis..." forever → backend not running or CORS issue. If "Error: ..." → check the error message and the backend logs.

- [ ] **Step 3: Delete the `MOCK_ADVICE` constant and unused imports**

Once Step 2 passes, remove `MOCK_ADVICE` (lines 9-242) entirely. Smaller file, no dead code.

- [ ] **Step 4: Commit**

```bash
git add frontend/pages/advice.js
git commit -m "feat(frontend): wire advice page to real /api/agents/advice endpoint"
```

---

## Task 3: Define `MorningBriefData` — the shape of one email

**Goal:** Lock down the data contract between the builder and the template. Explicit shape = easier tests + easier swap-in for future channels (web push card, in-app feed message).

**Files:**
- Create: `backend/services/morning_brief_builder.py` (data model only in this task)
- Create: `backend/tests/test_morning_brief_builder.py`

- [ ] **Step 1: Write the failing test for the data model**

`backend/tests/test_morning_brief_builder.py`:

```python
from datetime import datetime
from services.morning_brief_builder import MorningBriefData, ChangedSignal


def test_morning_brief_data_serialises_to_dict():
    brief = MorningBriefData(
        user_id="demo_user",
        user_name="Demo User",
        generated_at=datetime(2026, 4, 17, 3, 30, 0),
        portfolio_summary="₹2,15,340 (+0.18% vs yesterday)",
        changed_signals=[
            ChangedSignal(
                title="OPEC announces 1mbpd cut",
                old_status="active",
                new_status="strengthened",
                affected_sectors=["Oil & Gas", "Refiners"],
                why_it_matters="India imports 85% of oil — refiners face margin pressure.",
            )
        ],
        unchanged_thesis_count=2,
        no_alerts_today=False,
    )
    d = brief.model_dump()
    assert d["user_id"] == "demo_user"
    assert d["changed_signals"][0]["title"] == "OPEC announces 1mbpd cut"
    assert d["unchanged_thesis_count"] == 2
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd backend && pytest tests/test_morning_brief_builder.py::test_morning_brief_data_serialises_to_dict -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.morning_brief_builder'`.

- [ ] **Step 3: Implement the data model**

`backend/services/morning_brief_builder.py`:

```python
"""Morning Brief Builder — assembles the daily email summary for one user.

Pulls recent AdviceRecord + AdviceSignalLink rows and produces a
MorningBriefData object ready for template rendering.
"""
from datetime import datetime
from typing import List
from pydantic import BaseModel


class ChangedSignal(BaseModel):
    title: str
    old_status: str
    new_status: str
    affected_sectors: List[str]
    why_it_matters: str


class MorningBriefData(BaseModel):
    user_id: str
    user_name: str
    generated_at: datetime
    portfolio_summary: str
    changed_signals: List[ChangedSignal]
    unchanged_thesis_count: int
    no_alerts_today: bool
```

- [ ] **Step 4: Run the test, confirm it passes**

```bash
pytest tests/test_morning_brief_builder.py::test_morning_brief_data_serialises_to_dict -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/morning_brief_builder.py backend/tests/test_morning_brief_builder.py
git commit -m "feat(brief): add MorningBriefData + ChangedSignal pydantic models"
```

---

## Task 4: Implement `build_morning_brief(user_id, db)`

**Goal:** Given a user_id and a DB session, return a populated `MorningBriefData`.

**Files:**
- Modify: `backend/services/morning_brief_builder.py`
- Modify: `backend/tests/test_morning_brief_builder.py`

- [ ] **Step 1: Write the failing integration test**

Append to `backend/tests/test_morning_brief_builder.py`:

```python
import pytest
from datetime import datetime, timedelta
from services.morning_brief_builder import build_morning_brief
from models.models import User, AdviceRecord, AdviceSignalLink, RiskTolerance


@pytest.mark.asyncio
async def test_build_brief_returns_changed_signals_for_user(mock_db_session):
    """Given a user with one AdviceRecord whose linked signal has changed
    (current_status='weakened'), the brief lists that signal."""
    user = User(id="u1", email="u1@test", name="Test User",
                risk_tolerance=RiskTolerance.MODERATE)
    advice = AdviceRecord(
        id="a1", user_id="u1",
        narrative="Consider oil exposure...",
        confidence_score=0.78,
        created_at=datetime.utcnow() - timedelta(days=2),
    )
    link = AdviceSignalLink(
        id="l1", advice_id="a1",
        signal_title="OPEC supply cut announced",
        signal_type="macro",
        current_status="weakened",
        change_description="OPEC reversed the cut after pressure from US",
        sectors_affected={"Oil & Gas": 0.8, "Refiners": 0.6},
    )
    mock_db_session.add_all([user, advice, link])
    await mock_db_session.commit()

    brief = await build_morning_brief("u1", mock_db_session)

    assert brief.user_id == "u1"
    assert brief.user_name == "Test User"
    assert len(brief.changed_signals) == 1
    assert brief.changed_signals[0].title == "OPEC supply cut announced"
    assert brief.changed_signals[0].new_status == "weakened"
    assert "Oil & Gas" in brief.changed_signals[0].affected_sectors
    assert brief.no_alerts_today is False


@pytest.mark.asyncio
async def test_build_brief_no_changes_marks_quiet_day(mock_db_session):
    """Given a user with active (unchanged) signals only, brief flags it as a quiet day."""
    user = User(id="u2", email="u2@test", name="Quiet User")
    advice = AdviceRecord(id="a2", user_id="u2", narrative="...", confidence_score=0.7)
    link = AdviceSignalLink(
        id="l2", advice_id="a2", signal_title="Stable signal",
        current_status="active", sectors_affected={},
    )
    mock_db_session.add_all([user, advice, link])
    await mock_db_session.commit()

    brief = await build_morning_brief("u2", mock_db_session)

    assert brief.changed_signals == []
    assert brief.unchanged_thesis_count == 1
    assert brief.no_alerts_today is True
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
pytest tests/test_morning_brief_builder.py -v
```

Expected: FAIL with `ImportError: cannot import name 'build_morning_brief'`.

- [ ] **Step 3: Implement the builder function**

Append to `backend/services/morning_brief_builder.py`:

```python
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import User, AdviceRecord, AdviceSignalLink


async def build_morning_brief(user_id: str, db: AsyncSession) -> MorningBriefData:
    """Assemble the morning brief for one user.

    Pulls every AdviceRecord for the user with at least one AdviceSignalLink,
    classifies each link as 'changed' (current_status != 'active') or 'unchanged',
    and produces a MorningBriefData ready for template rendering.
    """
    user_row = await db.execute(select(User).where(User.id == user_id))
    user = user_row.scalar_one()

    advice_rows = await db.execute(
        select(AdviceRecord).where(AdviceRecord.user_id == user_id)
    )
    advice_ids = [a.id for a in advice_rows.scalars().all()]

    if not advice_ids:
        return MorningBriefData(
            user_id=user_id, user_name=user.name or "there",
            generated_at=datetime.utcnow(),
            portfolio_summary="No advice on file yet.",
            changed_signals=[], unchanged_thesis_count=0, no_alerts_today=True,
        )

    link_rows = await db.execute(
        select(AdviceSignalLink).where(AdviceSignalLink.advice_id.in_(advice_ids))
    )
    links = link_rows.scalars().all()

    changed = [
        ChangedSignal(
            title=l.signal_title,
            old_status="active",
            new_status=l.current_status,
            affected_sectors=list((l.sectors_affected or {}).keys()),
            why_it_matters=l.change_description or "Signal status changed.",
        )
        for l in links if l.current_status != "active"
    ]
    unchanged = sum(1 for l in links if l.current_status == "active")

    return MorningBriefData(
        user_id=user_id,
        user_name=user.name or "there",
        generated_at=datetime.utcnow(),
        portfolio_summary=f"{len(advice_ids)} advice on file, {unchanged} active thesis tracked.",
        changed_signals=changed,
        unchanged_thesis_count=unchanged,
        no_alerts_today=(len(changed) == 0),
    )
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
pytest tests/test_morning_brief_builder.py -v
```

Expected: 3 PASS (the original serialisation test + the two new tests). If `mock_db_session` fixture is async-incompatible, check `backend/tests/conftest.py` — it should already provide an in-memory SQLite async session per the existing test infrastructure.

- [ ] **Step 5: Commit**

```bash
git add backend/services/morning_brief_builder.py backend/tests/test_morning_brief_builder.py
git commit -m "feat(brief): build_morning_brief assembles brief from AdviceRecord + AdviceSignalLink"
```

---

## Task 5: Add Resend dependency + env vars

**Goal:** Resend offers a free tier (3000 emails/month, 100/day) with a clean Python SDK and HTTP API. Picked over Mailgun/SendGrid for simplest onboarding (one API key, no domain DNS required for sandbox sends).

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add resend to requirements**

Append to `backend/requirements.txt`:

```
resend>=2.0.0
```

- [ ] **Step 2: Add env vars to .env.example**

Append to `backend/.env.example`:

```
# Email (morning brief) — get free key at resend.com
RESEND_API_KEY=
MORNING_BRIEF_FROM_EMAIL=banker@investai.in
MORNING_BRIEF_FROM_NAME=InvestAI Banker
```

- [ ] **Step 3: Install in current env**

```bash
cd backend && pip install -r requirements.txt
```

- [ ] **Step 4: Verify the package imports cleanly**

```bash
python -c "import resend; print(resend.__version__)"
```

Expected: a version number prints (e.g., `2.0.0`). If error, check requirements pin and re-install.

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/.env.example
git commit -m "feat(brief): add resend SDK dependency + email env vars"
```

---

## Task 6: Implement `EmailSender` provider abstraction

**Goal:** A thin wrapper so the brief job calls `EmailSender.send(to, subject, html, text)` without knowing about Resend specifically. Lets us swap to Mailgun/SES later without touching the brief code, and lets us mock cleanly in tests.

**Files:**
- Create: `backend/services/email_sender.py`
- Create: `backend/tests/test_email_sender.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_email_sender.py`:

```python
from unittest.mock import patch, MagicMock
import pytest
from services.email_sender import EmailSender, EmailSendResult


def test_email_sender_calls_resend_with_correct_payload(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "fake_key_for_test")
    monkeypatch.setenv("MORNING_BRIEF_FROM_EMAIL", "from@test.com")
    monkeypatch.setenv("MORNING_BRIEF_FROM_NAME", "Tester")

    fake_response = {"id": "msg_123"}
    with patch("services.email_sender.resend.Emails.send", return_value=fake_response) as m:
        sender = EmailSender()
        result = sender.send(
            to="user@test.com",
            subject="Brief",
            html="<p>hi</p>",
            text="hi",
        )

    m.assert_called_once()
    payload = m.call_args[0][0]
    assert payload["to"] == ["user@test.com"]
    assert payload["from"] == "Tester <from@test.com>"
    assert payload["subject"] == "Brief"
    assert payload["html"] == "<p>hi</p>"
    assert payload["text"] == "hi"
    assert result == EmailSendResult(success=True, provider_id="msg_123", error=None)


def test_email_sender_returns_failure_on_exception(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "fake_key")
    monkeypatch.setenv("MORNING_BRIEF_FROM_EMAIL", "from@test.com")
    monkeypatch.setenv("MORNING_BRIEF_FROM_NAME", "Tester")

    with patch("services.email_sender.resend.Emails.send", side_effect=RuntimeError("boom")):
        sender = EmailSender()
        result = sender.send(to="u@t.com", subject="x", html="x", text="x")

    assert result.success is False
    assert "boom" in result.error
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_email_sender.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.email_sender'`.

- [ ] **Step 3: Implement EmailSender**

`backend/services/email_sender.py`:

```python
"""Email sender — thin wrapper around Resend's HTTP API.

Single concern: take a fully-rendered email and ship it. No template
rendering, no audience selection, no scheduling — those live elsewhere.
"""
import os
from typing import Optional
from pydantic import BaseModel
import resend
import structlog

logger = structlog.get_logger()


class EmailSendResult(BaseModel):
    success: bool
    provider_id: Optional[str] = None
    error: Optional[str] = None


class EmailSender:
    def __init__(self):
        api_key = os.getenv("RESEND_API_KEY")
        if not api_key:
            raise RuntimeError("RESEND_API_KEY not set")
        resend.api_key = api_key
        self.from_email = os.getenv("MORNING_BRIEF_FROM_EMAIL", "banker@investai.in")
        self.from_name  = os.getenv("MORNING_BRIEF_FROM_NAME",  "InvestAI Banker")

    def send(self, to: str, subject: str, html: str, text: str) -> EmailSendResult:
        payload = {
            "from": f"{self.from_name} <{self.from_email}>",
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
        try:
            resp = resend.Emails.send(payload)
            provider_id = resp.get("id") if isinstance(resp, dict) else None
            logger.info("email.sent", to=to, provider_id=provider_id)
            return EmailSendResult(success=True, provider_id=provider_id)
        except Exception as e:
            logger.error("email.send_failed", to=to, error=str(e))
            return EmailSendResult(success=False, error=str(e))
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_email_sender.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/email_sender.py backend/tests/test_email_sender.py
git commit -m "feat(brief): EmailSender wraps Resend HTTP API behind clean interface"
```

---

## Task 7: Render the morning brief to HTML + plaintext

**Goal:** Convert a `MorningBriefData` into the actual email body. Two outputs: HTML (for rich clients) and plaintext (fallback). Inline CSS for max email-client compatibility.

**Files:**
- Create: `backend/services/email_templates/__init__.py` (empty)
- Create: `backend/services/email_templates/morning_brief.py`
- Create: `backend/tests/test_morning_brief_template.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_morning_brief_template.py`:

```python
from datetime import datetime
from services.morning_brief_builder import MorningBriefData, ChangedSignal
from services.email_templates.morning_brief import render_morning_brief


def _sample_brief_with_changes():
    return MorningBriefData(
        user_id="u1", user_name="Sam",
        generated_at=datetime(2026, 4, 17, 3, 30, 0),
        portfolio_summary="3 advice on file, 2 active thesis tracked.",
        changed_signals=[
            ChangedSignal(
                title="OPEC supply cut reversed",
                old_status="active", new_status="weakened",
                affected_sectors=["Oil & Gas", "Refiners"],
                why_it_matters="Oil price expected to soften — refiners benefit.",
            )
        ],
        unchanged_thesis_count=2, no_alerts_today=False,
    )


def test_render_returns_html_and_text():
    brief = _sample_brief_with_changes()
    html, text = render_morning_brief(brief)

    assert "<html" in html.lower()
    assert "Sam" in html
    assert "OPEC supply cut reversed" in html
    assert "Oil & Gas" in html

    assert "Sam" in text
    assert "OPEC supply cut reversed" in text
    assert "<html" not in text.lower()  # plaintext should not contain HTML


def test_render_quiet_day_says_so():
    brief = MorningBriefData(
        user_id="u2", user_name="Quiet",
        generated_at=datetime(2026, 4, 17, 3, 30, 0),
        portfolio_summary="1 advice on file.",
        changed_signals=[], unchanged_thesis_count=1, no_alerts_today=True,
    )
    html, text = render_morning_brief(brief)
    assert "no material changes" in html.lower() or "all quiet" in html.lower()
    assert "no material changes" in text.lower() or "all quiet" in text.lower()
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_morning_brief_template.py -v
```

Expected: FAIL on import.

- [ ] **Step 3: Implement renderer**

`backend/services/email_templates/__init__.py`:

```python
```

`backend/services/email_templates/morning_brief.py`:

```python
"""Morning brief template — renders MorningBriefData into HTML + plaintext."""
from services.morning_brief_builder import MorningBriefData


def render_morning_brief(brief: MorningBriefData) -> tuple[str, str]:
    """Returns (html, text) tuple."""
    return _render_html(brief), _render_text(brief)


def _render_html(brief: MorningBriefData) -> str:
    date_str = brief.generated_at.strftime("%A, %d %b %Y")

    if brief.no_alerts_today:
        body = (
            '<p style="font-size:15px;color:#444;">'
            "All quiet on the signals front. No material changes overnight. "
            f"Tracking {brief.unchanged_thesis_count} active thesis on your behalf."
            "</p>"
        )
    else:
        rows = "".join(
            f'<tr><td style="padding:12px 0;border-bottom:1px solid #eee;">'
            f'<div style="font-weight:600;color:#111;">{cs.title}</div>'
            f'<div style="font-size:13px;color:#666;margin-top:4px;">'
            f'Status: <b>{cs.new_status}</b> &nbsp;|&nbsp; Sectors: {", ".join(cs.affected_sectors) or "—"}'
            f"</div>"
            f'<div style="font-size:14px;color:#333;margin-top:6px;">{cs.why_it_matters}</div>'
            f"</td></tr>"
            for cs in brief.changed_signals
        )
        body = (
            f'<p style="font-size:15px;color:#444;">'
            f"{len(brief.changed_signals)} signal(s) shifted overnight. "
            f"{brief.unchanged_thesis_count} other thesis still active."
            f"</p>"
            f'<table style="width:100%;border-collapse:collapse;margin-top:16px;">{rows}</table>'
        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:#fafafa;margin:0;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#fff;padding:24px;border-radius:8px;">
    <div style="font-size:13px;color:#888;">{date_str}</div>
    <h2 style="margin:8px 0 16px 0;color:#111;">Good morning, {brief.user_name}.</h2>
    <div style="font-size:13px;color:#666;margin-bottom:18px;">{brief.portfolio_summary}</div>
    {body}
    <div style="margin-top:32px;font-size:12px;color:#999;border-top:1px solid #eee;padding-top:12px;">
      Analysis only. You decide whether to act. — InvestAI 24/7 Banker
    </div>
  </div>
</body>
</html>"""


def _render_text(brief: MorningBriefData) -> str:
    date_str = brief.generated_at.strftime("%A, %d %b %Y")
    lines = [
        date_str,
        f"Good morning, {brief.user_name}.",
        "",
        brief.portfolio_summary,
        "",
    ]
    if brief.no_alerts_today:
        lines.append(
            "All quiet on the signals front. No material changes overnight. "
            f"Tracking {brief.unchanged_thesis_count} active thesis on your behalf."
        )
    else:
        lines.append(
            f"{len(brief.changed_signals)} signal(s) shifted overnight. "
            f"{brief.unchanged_thesis_count} other thesis still active."
        )
        lines.append("")
        for cs in brief.changed_signals:
            lines.append(f"- {cs.title}")
            lines.append(f"  Status: {cs.new_status} | Sectors: {', '.join(cs.affected_sectors) or '—'}")
            lines.append(f"  {cs.why_it_matters}")
            lines.append("")
    lines.append("--")
    lines.append("Analysis only. You decide whether to act. — InvestAI 24/7 Banker")
    return "\n".join(lines)
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_morning_brief_template.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/email_templates/__init__.py backend/services/email_templates/morning_brief.py backend/tests/test_morning_brief_template.py
git commit -m "feat(brief): HTML + plaintext renderer for morning brief"
```

---

## Task 8: Wire `send_morning_briefs` job into `worker.py`

**Goal:** Daily at 03:30 UTC (= 09:00 IST), iterate all users with email opt-in and send each their brief.

**Files:**
- Modify: `backend/worker.py`
- Modify: `backend/tests/test_morning_brief_builder.py` (add job-level test)

- [ ] **Step 1: Write the failing test for the job orchestration**

Append to `backend/tests/test_morning_brief_builder.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_send_morning_briefs_to_all_opted_in_users(mock_db_session):
    """Iterates users with notification_prefs.morning_brief != False and
    calls EmailSender.send once per user. Users opted out are skipped."""
    from services.morning_brief_builder import send_morning_briefs_to_all

    u1 = User(id="u1", email="u1@test", name="One",
              notification_prefs={"morning_brief": True})
    u2 = User(id="u2", email="u2@test", name="Two",
              notification_prefs={"morning_brief": False})
    u3 = User(id="u3", email="u3@test", name="Three",
              notification_prefs={})  # default = opted in
    mock_db_session.add_all([u1, u2, u3])
    await mock_db_session.commit()

    fake_sender = MagicMock()
    fake_sender.send = MagicMock(return_value=MagicMock(success=True))

    sent_count = await send_morning_briefs_to_all(mock_db_session, fake_sender)

    assert sent_count == 2  # u1 + u3, NOT u2
    assert fake_sender.send.call_count == 2
    sent_to = sorted(call.kwargs["to"] for call in fake_sender.send.call_args_list)
    assert sent_to == ["u1@test", "u3@test"]
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_morning_brief_builder.py::test_send_morning_briefs_to_all_opted_in_users -v
```

Expected: FAIL with `ImportError: cannot import name 'send_morning_briefs_to_all'`.

- [ ] **Step 3: Implement the orchestrator**

Append to `backend/services/morning_brief_builder.py`:

```python
from services.email_templates.morning_brief import render_morning_brief
from services.email_sender import EmailSender


async def send_morning_briefs_to_all(db: AsyncSession, sender: EmailSender) -> int:
    """Send the morning brief to every user opted in to morning_brief notifications.
    Returns the count of successful sends."""
    rows = await db.execute(select(User))
    users = rows.scalars().all()

    sent = 0
    for u in users:
        prefs = u.notification_prefs or {}
        if prefs.get("morning_brief") is False:
            continue
        if not u.email:
            continue
        brief = await build_morning_brief(u.id, db)
        html, text = render_morning_brief(brief)
        result = sender.send(
            to=u.email,
            subject=f"Morning brief — {brief.generated_at.strftime('%d %b')}",
            html=html,
            text=text,
        )
        if result.success:
            sent += 1
    return sent
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_morning_brief_builder.py -v
```

Expected: all PASS (4 tests total in the file now).

- [ ] **Step 5: Add the scheduler job to worker.py**

Modify `backend/worker.py`. Add a new function after `score_advice_performance`:

```python
async def send_morning_briefs_job():
    """Daily at 09:00 IST: send the morning brief email to every opted-in user."""
    logger.info("worker.morning_brief.start")
    try:
        from database.connection import AsyncSessionLocal
        from services.morning_brief_builder import send_morning_briefs_to_all
        from services.email_sender import EmailSender

        sender = EmailSender()
        async with AsyncSessionLocal() as db:
            sent = await send_morning_briefs_to_all(db, sender)
            logger.info("worker.morning_brief.complete", sent=sent)
    except Exception as e:
        logger.error("worker.morning_brief.error", error=str(e))
```

Then in the `start_scheduler` function, add this line BEFORE `scheduler.start()`:

```python
    scheduler.add_job(send_morning_briefs_job,  CronTrigger(hour=3, minute=30), id="morning_brief",   replace_existing=True)
```

(03:30 UTC = 09:00 IST. APScheduler defaults to UTC unless configured otherwise; the existing jobs in this file already assume UTC.)

Update the `logger.info("worker.scheduler.started", ...)` line's `jobs=` list to include `"morning_brief(3:30 UTC)"`.

- [ ] **Step 6: Verify worker imports cleanly**

```bash
cd backend && python -c "import worker; worker.start_scheduler(); print('OK'); worker.stop_scheduler()"
```

Expected: prints `OK` and a log line mentioning the new `morning_brief` job. No import errors.

- [ ] **Step 7: Commit**

```bash
git add backend/worker.py backend/services/morning_brief_builder.py backend/tests/test_morning_brief_builder.py
git commit -m "feat(brief): schedule daily 09:00 IST morning brief job in worker.py"
```

---

## Task 9: End-to-end smoke test against Resend sandbox

**Goal:** Prove an email actually arrives. No more mocking.

**Files:** none (manual test + one disposable script)

- [ ] **Step 1: Get a Resend API key**

Sign up at https://resend.com/, verify email, create an API key from the dashboard. Free tier is sufficient. For sending TO arbitrary addresses without DNS setup, you can only send to the email address you signed up with — that's fine for the smoke test.

- [ ] **Step 2: Set the env vars locally**

In `backend/.env` (NOT .env.example — real secrets go in .env which is gitignored):

```
RESEND_API_KEY=re_yourkeyhere
MORNING_BRIEF_FROM_EMAIL=onboarding@resend.dev
MORNING_BRIEF_FROM_NAME=InvestAI Banker
```

(Use `onboarding@resend.dev` as the FROM address until you verify your own domain — Resend allows this for sandbox sends.)

- [ ] **Step 3: Update demo_user's email to your real address temporarily**

```bash
docker compose exec postgres psql -U investai -d investai \
  -c "UPDATE users SET email = 'YOUR_REAL_EMAIL@example.com' WHERE id = 'demo_user';"
```

(Replace with the email you signed up to Resend with.)

- [ ] **Step 4: Trigger the brief job manually**

```bash
cd backend && python -c "
import asyncio
from database.connection import AsyncSessionLocal
from services.morning_brief_builder import send_morning_briefs_to_all
from services.email_sender import EmailSender

async def main():
    sender = EmailSender()
    async with AsyncSessionLocal() as db:
        sent = await send_morning_briefs_to_all(db, sender)
        print(f'Sent: {sent}')

asyncio.run(main())
"
```

Expected: prints `Sent: 1` and within ~30s an email arrives at your inbox titled "Morning brief — 17 Apr" (or today's date).

- [ ] **Step 5: Inspect the email**

Open the email. Confirm:
- Greeting uses your name
- Either the "all quiet" message OR a list of changed signals appears
- The footer says "Analysis only. You decide whether to act."

If anything looks broken in rendering, iterate on `services/email_templates/morning_brief.py` and re-run Step 4.

- [ ] **Step 6: Restore demo_user's email and remove the personal address**

```bash
docker compose exec postgres psql -U investai -d investai \
  -c "UPDATE users SET email = 'demo@investai.local' WHERE id = 'demo_user';"
```

- [ ] **Step 7: Final commit (if any tweaks were made in Step 5)**

```bash
git add -p   # review changes interactively
git commit -m "chore(brief): post-smoke-test polish"
```

---

## Self-Review Checklist (run after writing the plan)

- ✅ **Spec coverage:** Plan covers spec §12 (email channel), §15 (memory — re-uses AdviceRecord), §17 (architecture — uses existing Root Cause Chain + signal monitor as upstream). Spec §10 (severity classifier) and §16 (trust mechanics — confidence/sources) are out of scope for this phase by design — they go in Phase 2.
- ✅ **Placeholder scan:** No "TBD" / "TODO" / "implement later" anywhere. Every code block is complete.
- ✅ **Type consistency:** `MorningBriefData`, `ChangedSignal`, `EmailSendResult`, `EmailSender.send()` signatures used consistently across Tasks 3, 4, 6, 7, 8.
- ✅ **Scope check:** Single phase, single shippable capability (email at 9am). Phases 2-4 explicitly deferred.

---

## Out of scope for Phase 1 (intentionally deferred)

- Severity classifier and 🔴 thesis-break alerts — Phase 3
- Web Push notifications — Phase 3
- Cross-source confirmation gate — Phase 2
- Confidence scores on email output — Phase 2
- Source citations in email body — Phase 2
- Track record logging + display — Phase 2
- WhatsApp-style frontend feed — Phase 4
- Conversational onboarding flow — Phase 4
- Tap-to-explain glossary — Phase 4
- Honest-miss handling in next-day brief — Phase 4 (depends on track record from Phase 2)
- Replacing hardcoded `user_id = "demo_user"` with real auth — separate auth workstream
- Adding India-macro and India-market sources to the signal feed — Phase 2

## What ships at the end of Phase 1

A user with an email on file gets a real email at 09:00 IST every day summarising what changed in the signals tracked for them. Even if the "no material changes" path fires every day for a week, the loop is proven and the daily presence is established. This is the foundation everything else builds on.
