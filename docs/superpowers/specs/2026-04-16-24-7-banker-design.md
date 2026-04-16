# InvestAI 24/7 Banker — Product & Architecture Spec

**Date:** 2026-04-16
**Status:** Brainstorm complete, awaiting user approval before implementation plan
**Supersedes:** ad-hoc product notes in `memory/project_brainstorm_insights.md`

---

## 1. Vision

A personal 24/7 investment banker for Indian retail investors. The platform watches what happens in the world, traces the implications down to the user's specific holdings, and gives the user an information edge over anyone using traditional approaches. The banker's sole job: help the user grow their portfolio.

Compliance posture: **SEBI Option 1 — analysis only, user decides.** The banker never executes trades, never recommends specific allocations in rupees, never holds custody. It surfaces what's happening, why it matters for the user, and lets the user choose.

## 2. Audience

Three concentric audiences served from one product via progressive disclosure (default = dense pro view, tap any term for plain-English explanation):

- **Complete beginners** (₹5k–₹10k, no idea where to start)
- **Active retail traders** (₹50k–₹5L, already trading on Groww/Zerodha)
- **Seasoned investors** (₹5L+, follow news/CNBC, want sharper signal)

Explicitly **NOT** in audience: mutual-fund-only users (their assets don't react to fast signals; the banker's edge is wasted on them).

## 3. Core User Loop

1. User onboards in ~60 seconds via chat (states either holdings or intent).
2. Banker confirms understanding and starts watching.
3. Every morning at 09:00 IST: email brief summarising overnight events that affect the user.
4. When something material breaks intraday: browser push notification + new message in the in-app feed.
5. User taps to read. Decides whether to act (banker never acts on user's behalf).
6. Banker remembers what was said and watches for thesis changes over time.

## 4. Asset Coverage

**v1 primary:** Indian listed equity (NSE/BSE single stocks).

**v1 supported but secondary:** Index/equity mutual funds — supported when the user lists them in their holdings (e.g., "₹50k in Nifty 50 index fund"). The banker treats these as broad-sector exposure (e.g., a Nifty 50 fund = exposure to top-50 large caps). Stock-by-stock decomposition of an active mutual fund is NOT attempted in v1.

**Out of scope for v1** (candidates for v2+): F&O, gold (digital), crypto, fixed deposits, sovereign bonds, broker integration.

Rationale: equity is where global signals matter most, and the v1 audience already trades equity.

## 5. Portfolio Input Model

Text-based, no broker integration. User states **either**:
- **Holdings:** "I have ₹10k in TCS, ₹15k in HDFC Bank, ₹5k in Nifty 50 index fund."
- **Intent:** "I want to invest ₹50k for 1 year."

User updates manually as they buy/sell. No connection to Zerodha/Groww/Upstox in v1.

## 6. Signal Feed (3-tier)

```
┌────────────────────┬────────────────────┬───────────────────┐
│ GLOBAL             │  INDIA — MACRO     │  INDIA — MARKET   │
│ Tier 1: US, China, │  RBI, SEBI, PIB,   │  NSE/BSE filings, │
│   OPEC             │  Budget, GST,      │  earnings,        │
│ Tier 2: EU/UK, JP, │  FII/DII flows,    │  dividends,       │
│   Russia           │  monsoon (IMD),    │  Nifty/Sensex,    │
│ Tier 3: SG, HK,    │  CPI, GDP          │  sector rotation  │
│   BD, VN, AU, CA   │                    │                   │
│ Tier 4: event-     │                    │                   │
│   driven only      │                    │                   │
└────────────────────┴────────────────────┴───────────────────┘
```

### Country tiering (Global)

| Tier | Countries | Why they matter to India |
|---|---|---|
| 1 — Heavy | USA | Fed rates → rupee, US tech earnings → Indian IT, trade policy |
| 1 — Heavy | China | Commodity demand, PBOC moves, border, manufacturing competition |
| 1 — Heavy | OPEC (Saudi, UAE) | Oil = India's biggest import = inflation, fuel, refiners |
| 2 — Moderate | EU + UK | ECB/BoE rates, energy, Indian pharma exports |
| 2 — Moderate | Japan | BoJ + yen carry trade = global liquidity flowing in/out of India |
| 2 — Moderate | Russia | Oil, gas, defense (India buys all three) |
| 3 — Targeted | Singapore, Hong Kong | Asia info hubs, capital flows, FII routing |
| 3 — Targeted | Bangladesh, Vietnam | Textile/manufacturing competition |
| 3 — Targeted | Australia, Canada | Commodities (coal, potash, metals) |
| 4 — Event-driven | All others | Tracked only when a specific event flags them (war, election, currency crisis) |

### Source list (all free)

| Source | Tier | Format |
|---|---|---|
| Fed FOMC, ECB, OPEC press releases | Global | Web/RSS |
| Trading Economics calendar | Global | Free tier API |
| Yahoo Finance, Google Finance | Global + India | API |
| RBI website + DBIE database | India macro | Web/RSS |
| SEBI announcements + filings | India macro | Web/RSS |
| Press Information Bureau (PIB) | India macro | RSS |
| IMD (monsoon, weather) | India macro | API |
| NSE/BSE corporate filings | India market | RSS |
| moneycontrol, livemint | India market | RSS |

**Total monthly source cost: ₹0.**

## 7. Cross-source Confirmation

The banker does **not** issue an alert from a single source. Rule: **two or more independent sources must agree** on the underlying event before it triggers a thesis-break alert. Single-source signals are logged silently for context but never push.

**Why:** kills hoaxes, fake news, and over-eager single-source noise. Equally important — sets honest expectations: the banker is not omniscient, but it is rigorous.

## 8. Root Cause Chain (existing)

Already built and merged 2026-04-11. Maps a global event → affected Indian sector → user's specific stock. This is InvestAI's wedge: the chain explains *why* something matters, not just *that* it matters.

Reused by this design as the reasoning engine behind every alert.

## 9. Per-user Thesis Matcher

Takes the output of the Root Cause Chain and asks: **does this affect any stock in the user's stated holdings, OR any sector implied by the user's stated intent?** If yes → goes to severity classifier. If no → logged for the morning brief context but no alert.

## 10. Severity Classifier

Two levels for v1:

- **🟢 Background** — context worth knowing but not urgent. Goes to morning brief only.
- **🔴 Thesis break** — the reasoning behind a prior piece of advice has materially changed. Push notification + in-app message.

A thesis break is defined as: the new event meaningfully changes the expected direction or magnitude of impact on the user's holdings vs. what was previously communicated.

**Initial threshold calibration:** the LLM's own judgment (with explicit prompt scaffolding) sets the bar in v1. Over time, user behaviour signals (which alerts they open vs. ignore vs. dismiss) feed back into the threshold so the banker learns each user's noise tolerance. No hand-tuned numerical cutoff in v1.

(Three-tier severity from earlier brainstorming was simplified to two; the missing 🟡 tier collapses into morning brief.)

## 11. Output Format

**Default:** dense Bloomberg-terminal-style. Tap any term, ticker, or abbreviation for plain-English explanation.

Example alert:
```
USD/INR  83.2 → 83.9  (+0.84%)
Trigger:  FOMC cut 25bps (consensus: 0bps)
Sectors:  IT (+) Pharma (+) Refiners (-)
Your TCS: ₹2L exposure — directional positive
Confidence: 78%  |  Source: Reuters 03:51 IST
[Full analysis chain]
```

Tap behaviour examples:
- Tap "FOMC" → "The US Federal Reserve's rate-setting committee. They control US interest rates."
- Tap "USD/INR" → "How many rupees one US dollar buys. Higher = weaker rupee."
- Tap "+0.84%" → "The rupee weakened by 0.84% in the last few hours."

## 12. Delivery Channels (v1)

| When | Channel | Cost |
|---|---|---|
| Morning brief (always, 09:00 IST) | Email | Free (Resend / Mailgun free tier) |
| Thesis break (rare, intraday) | Browser Web Push notification | Free |
| All alerts (history) | In-app feed | Free |

**WhatsApp: paused for v1.** Candidate for v2 once a paid tier exists to fund the per-message cost.

**Web Push notes:** works on desktop Chrome/Edge/Firefox and Android Chrome out of the box. iOS Safari requires the user to install the site as a PWA (one tap from Share menu). v1 will prompt iOS users to install on first visit.

## 13. Home Screen — WhatsApp-style single feed

App opens to a vertical timeline of banker messages. Newest at top. Morning brief, alerts, ad-hoc Q&A — all in one stream. Chat input always pinned to the bottom.

```
─── Today, Tue 21 Apr ───
🏦 Morning brief: 3 events overnight... [tap]
🏦 USD/INR alert (04:12) — your TCS... [tap]
─── Yesterday ───
🏦 Pharma sector summary [tap]
You: what about HDFC Bank?
🏦 HDFC trading at... [tap]

[ Type a message... ]
```

**Why:** matches the banker's mental model (the banker is *messaging* you), simplest UI to build, scales across all three audiences, mobile-first by default.

## 14. Onboarding (first 60 seconds)

Conversational, no forms. On first open:

```
🏦 Banker
Hi, I'm your 24/7 banker. To watch over your money, tell me one of two things:

(1) What you already own  — e.g., "₹10k TCS, ₹5k HDFC"
(2) How much you want to invest, and for how long  — e.g., "₹50k for 1 year"

[ Type your answer... ]
```

User types in plain words. Banker confirms understanding ("Got it — ₹10k TCS and ₹5k HDFC, mostly large-cap IT and banking. I'm watching now."), and explains the cadence ("I'll send you a morning brief tomorrow at 9am, and I'll only message you intraday if something material breaks. You can ask me anything any time.").

## 15. Memory (what the banker remembers per user)

1. Stated holdings + stated intent + stated time horizon
2. Every alert sent + the full reasoning chain behind it (already in `AdviceRecord` + `AdviceSignalLink`)
3. Which alerts the user opened vs. ignored (already in `UserAlert`)
4. Every prediction's eventual outcome — was the banker right? (NEW: outcome tracking)
5. User's stated risk tolerance, if volunteered

## 16. Trust Mechanics

Five free trust signals, all built in from day 1:

1. **Source citation on every claim** — "Reuters, 03:51 IST" attached to every alert.
2. **Confidence score on every prediction** — "Confidence: 78%" — the banker is honest when uncertain.
3. **Cross-source confirmation rule** — no alert from a single source (see §7).
4. **Track record log** — every past alert is timestamped and its outcome recorded; over weeks this becomes a verifiable history.
5. **Honest about misses** — when a prediction is wrong, the next morning's brief opens with "Yesterday I said X. The market did Y. Here's what I missed." Hiding misses destroys trust faster than the misses themselves.

## 17. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     SIGNAL FEED                              │
├────────────────────┬────────────────────┬───────────────────┤
│ GLOBAL             │  INDIA — MACRO     │  INDIA — MARKET   │
│ Tier 1: US, China, │  RBI, SEBI, PIB,   │  NSE/BSE filings, │
│   OPEC             │  Budget, GST,      │  earnings,        │
│ Tier 2: EU/UK, JP, │  FII/DII flows,    │  dividends,       │
│   Russia           │  monsoon (IMD),    │  Nifty/Sensex,    │
│ Tier 3: SG, HK,    │  CPI, GDP          │  sector rotation  │
│   BD, VN, AU, CA   │                    │                   │
│ Tier 4: event-     │                    │                   │
│   driven only      │                    │                   │
└──────────┬─────────┴──────────┬─────────┴─────────┬─────────┘
           └────────────────────┼───────────────────┘
                                ▼
                  ┌────────────────────────────┐
                  │  Cross-source confirmation │  (2+ sources)
                  └─────────────┬──────────────┘
                                ▼
                  ┌────────────────────────────┐
                  │  Root Cause Chain          │  ← already built
                  │  global event → India      │
                  │  sector → user's stock     │
                  └─────────────┬──────────────┘
                                ▼
                  ┌────────────────────────────┐
                  │  Per-user thesis matcher   │
                  └─────────────┬──────────────┘
                                ▼
                  ┌────────────────────────────┐
                  │  Severity classifier       │
                  └──┬──────────────────────┬──┘
                     ▼                      ▼
          ┌──────────────────┐    ┌────────────────────┐
          │ 🟢 Background    │    │ 🔴 Thesis break    │
          │ → Email          │    │ → Browser push     │
          │   (morning 9am)  │    │   + in-app feed    │
          └──────────────────┘    └────────────────────┘
                     │                      │
                     └──────────┬───────────┘
                                ▼
                  ┌────────────────────────────┐
                  │  In-app feed (chat-style)  │
                  │  + memory persistence      │
                  └────────────────────────────┘
```

## 18. Cost (monthly, v1)

| Item | Cost |
|---|---|
| Signal sources (all free APIs/RSS) | ₹0 |
| Email (Resend / Mailgun free tier — up to ~3k emails/month) | ₹0 |
| Browser Web Push | ₹0 |
| LLM (Groq + Kaggle Gemma already wired) | ₹0 |
| Hosting (existing Codespace / lightweight VPS) | already paid |
| **Total ongoing** | **~₹0** |

WhatsApp would add ~₹2,000/month at 1k users × 3 alerts/week. Deferred to v2.

## 19. Monetization

**v1: free for everyone**, with soft caps:
- 1 portfolio watched per user
- 5 ad-hoc questions per day
- Web Push only (no SMS / WhatsApp)

**v2: paid tier** once 100+ active users prove the banker works. Likely additions:
- Unlimited portfolios
- F&O / gold / crypto coverage
- WhatsApp / SMS push
- Faster alert SLA
- Custom watchlists

## 20. What's already built vs. what's new

### Already built (per existing code + memory)
- Backend signal pipeline (`scripts/phase1_ingest.py`)
- Root Cause Chain (merged 2026-04-11)
- `AdviceRecord`, `AdviceSignalLink`, `UserAlert` tables
- `services/signal_monitor.py`
- `worker.py` scheduler (scan_signals 15m, signal_monitor 30m, daily lifecycle, weekly scoring)
- `routes/alerts.py` with full GET/PATCH endpoints
- `ensure_demo_user()` seeding fix (committed 2026-04-16)
- Llama 3.3 70B via Groq for advice generation; Kaggle Gemma planned for ingestion

### New work this spec introduces
- **Signal feed expansion** — wire all 3 tiers (global / India macro / India market) with the source list in §6
- **Country tiering rules** — implement tier-based weighting in the per-user matcher
- **Cross-source confirmation gate** — require 2+ sources before alert push (§7)
- **Severity classifier** — separate background-vs-thesis-break logic (§10)
- **Email morning brief generator + 09:00 IST scheduler**
- **Web Push** — service worker, subscription management, PWA install prompt for iOS
- **WhatsApp-style home feed UI** — replace current form-first dashboard
- **Conversational onboarding flow** — replace any current sign-up form
- **Tap-to-explain plain-English mode** — glossary system + UI affordance for every term/ticker
- **Confidence scoring** on every output
- **Source citation** on every output
- **Track record logging + display** — outcome resolution + history view
- **Honest-miss handling** — automatic retrospective in next morning brief when a prediction goes wrong
- **Replace `MOCK_ADVICE` in `frontend/advice.js`** with real API responses (gap #2 from `project_24_7_banker_status.md`)

## 21. Out of scope for v1

- Broker integration (Zerodha / Groww / Upstox APIs)
- F&O / crypto / gold / FD coverage
- WhatsApp / SMS alerts
- Native mobile app
- Real broker execution
- Mutual-fund-focused audience
- Multi-portfolio per user
- Social / community features
- Backtesting UI for users (separate workstream — see PR #1)

## 22. Open questions deferred to implementation phase

These are concrete enough to defer to the implementation plan rather than block the design:

- Which exact email provider (Resend vs. Mailgun vs. SendGrid free tier) — pick when wiring §12
- Web Push library choice on the backend (`pywebpush` is the obvious default)
- VAPID key management for Web Push
- Specific RSS-to-DB ingestion cadence per source
- How to detect "user opened the alert" cleanly across email + push + in-app

These are NOT open product questions — they are implementation choices.

---

## Approval gate

This spec is the basis for the implementation plan that follows. Once the user approves, the next step is the `superpowers:writing-plans` skill, which will break this design into concrete sequenced tasks.
