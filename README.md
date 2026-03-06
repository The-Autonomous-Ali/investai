# 🧠 InvestAI — AI-Powered Investment Intelligence Platform

An intelligent investment advisory platform for Indian markets that:
- Aggregates signals from LinkedIn, Twitter, news, government sources & market data
- Chains signals to predict 2nd/3rd order impacts on Indian sectors
- Adapts predictions in real-time as events evolve
- Remembers every strategy given to every user
- Uses a multi-agent architecture with checks & balances

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, Tailwind CSS, Recharts |
| Backend | FastAPI (Python 3.11) |
| AI Agents | Claude API (Anthropic), LangGraph |
| Primary DB | PostgreSQL 15 |
| Cache / Queue | Redis 7 |
| Knowledge Graph | Neo4j 5 |
| Scraping | Playwright, Feedparser |
| Auth | Google OAuth 2.0 + NextAuth.js |
| Containerization | Docker + Docker Compose |

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+
- Python 3.11+
- Anthropic API Key
- Google OAuth credentials

### 1. Clone & Configure

```bash
git clone <repo>
cd investai
cp .env.example .env
```

Edit `.env` with your credentials:
```env
ANTHROPIC_API_KEY=your_key_here
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
NEXTAUTH_SECRET=random_32_char_string
PROXYCURL_API_KEY=your_proxycurl_key  # for LinkedIn
```

### 2. Start with Docker

```bash
docker-compose up --build
```

This starts:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Neo4j Browser: http://localhost:7474
- Redis: localhost:6379

### 3. Manual Setup (Development)

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # run DB migrations
python seed_knowledge_graph.py # seed initial relationships
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

---

## 📁 Project Structure

```
investai/
├── frontend/                    # Next.js app
│   ├── pages/
│   │   ├── index.js             # Landing page
│   │   ├── auth/signin.js       # Login page
│   │   ├── dashboard.js         # Main dashboard
│   │   ├── signals.js           # Live signal tracker
│   │   ├── portfolio.js         # Portfolio manager
│   │   └── settings.js          # Account settings
│   ├── components/
│   │   ├── ui/                  # Reusable UI components
│   │   ├── dashboard/           # Dashboard-specific components
│   │   ├── signals/             # Signal tracker components
│   │   └── portfolio/           # Portfolio components
│   └── lib/
│       ├── api.js               # API client
│       └── auth.js              # Auth config
│
├── backend/
│   ├── main.py                  # FastAPI app entry
│   ├── agents/
│   │   ├── orchestrator.py      # Master coordinator
│   │   ├── signal_watcher.py    # Signal detection
│   │   ├── research_agent.py    # Deep analysis
│   │   ├── pattern_matcher.py   # Historical patterns
│   │   ├── portfolio_agent.py   # Allocation builder
│   │   ├── tax_agent.py         # Tax optimization
│   │   ├── memory_agent.py      # User memory
│   │   ├── critic_agent.py      # Output validator
│   │   ├── watchdog_agent.py    # Conflict detector
│   │   └── temporal_agent.py    # Event lifecycle
│   ├── scrapers/
│   │   ├── news_scraper.py      # RSS + web scraping
│   │   ├── market_data.py       # NSE/BSE data
│   │   ├── linkedin_scraper.py  # LinkedIn via Proxycurl
│   │   └── twitter_scraper.py   # Twitter/X API
│   ├── models/                  # SQLAlchemy models
│   ├── routes/                  # API route handlers
│   ├── database/                # DB connection + migrations
│   └── utils/                   # Helpers
│
├── infra/
│   ├── neo4j/seed.cypher        # Knowledge graph seed data
│   └── postgres/init.sql        # DB initialization
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🤖 Agent Architecture

```
User Query
    │
    ▼
Orchestrator Agent
    ├── Signal Watcher Agent    (24/7 background monitoring)
    ├── Research Agent          (deep signal analysis)
    ├── Pattern Matcher Agent   (historical analogues)
    ├── Portfolio Agent         (allocation building)
    ├── Tax Agent               (India tax optimization)
    ├── Memory Agent            (user history)
    ├── Temporal Agent          (event lifecycle)
    ├── Critic Agent            (output validation)
    └── Watchdog Agent          (conflict detection)
```

---

## 📊 Subscription Tiers

| Feature | Free | Starter (₹999/mo) | Pro (₹2099/mo) | Elite (₹4199/mo) |
|---|---|---|---|---|
| Queries/month | 3 | 30 | Unlimited | Unlimited |
| Memory | None | 3 months | 12 months | Unlimited |
| Signal sources | News only | News + Market | + Twitter | All + LinkedIn |
| Tax optimization | ❌ | Basic | Full | Full + CA review |
| Real-time alerts | ❌ | ❌ | ✅ | ✅ |
| Portfolio tracking | ❌ | ✅ | ✅ | ✅ |
| Event predictions | ❌ | Basic | Full | Full + API access |

---

## ⚠️ Legal Disclaimer

This platform provides financial information for educational purposes only. It is NOT a registered investment advisor under SEBI regulations. All information provided should be independently verified. Past performance does not guarantee future results. Always consult a qualified financial advisor before making investment decisions.
