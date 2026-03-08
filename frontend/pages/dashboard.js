import Head from 'next/head'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { TrendingUp, Bell, Settings, LogOut, Activity, Brain, Shield, ChevronRight, RefreshCw, Zap } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

// ── Mock Data ──────────────────────────────────────────────────────────────
const MOCK_SIGNALS = [
  { id: 1, title: 'RBI MPC Meeting Minutes Signal Rate Hold Likely', source: 'RBI', urgency: 'developing', importance: 8.2, sentiment: 'neutral',  sectors: { Banking: 'positive', 'Real Estate': 'positive' }, detected: '2h ago' },
  { id: 2, title: 'Brent Crude Approaches $96 on Middle East Tensions', source: 'Reuters', urgency: 'breaking',   importance: 9.1, sentiment: 'negative', sectors: { Aviation: 'negative', 'Oil & Gas': 'positive' }, detected: '45m ago' },
  { id: 3, title: 'US Fed Signals Fewer Rate Cuts in 2024', source: 'Bloomberg', urgency: 'developing', importance: 7.8, sentiment: 'negative', sectors: { IT: 'positive', Banking: 'neutral' }, detected: '3h ago' },
  { id: 4, title: 'India Q3 GDP Growth at 7.2% Beats Estimates', source: 'MoSPI', urgency: 'long_term', importance: 8.5, sentiment: 'positive',  sectors: { Infrastructure: 'positive', FMCG: 'positive' }, detected: '5h ago' },
]

const MOCK_PORTFOLIO_ALLOCATION = [
  { name: 'Nifty 50 Index Fund', value: 25, amount: 25000, color: '#D4A843' },
  { name: 'Gold ETF',            value: 20, amount: 20000, color: '#F0C866' },
  { name: 'ONGC',                value: 15, amount: 15000, color: '#3DD68C' },
  { name: 'IT Sector Fund',      value: 15, amount: 15000, color: '#4A9EFF' },
  { name: 'Liquid Fund',         value: 25, amount: 25000, color: '#8892A4' },
]

const MOCK_PORTFOLIO_PERFORMANCE = [
  { month: 'Aug', value: 100000 },
  { month: 'Sep', value: 103200 },
  { month: 'Oct', value: 101800 },
  { month: 'Nov', value: 107400 },
  { month: 'Dec', value: 110200 },
  { month: 'Jan', value: 108900 },
  { month: 'Feb', value: 113600 },
]

const MOCK_ACTIVE_EVENTS = [
  { title: 'Iran-Israel Conflict', stage: 'ESCALATING', days: 12, probability_worst: 20, prediction: 'Oil likely stays elevated this week' },
  { title: 'US Fed Rate Decision', stage: 'WATCH',      days: 3,  probability_worst: 10, prediction: 'Rate hold expected March 20' },
  { title: 'India Elections',      stage: 'DEVELOPING', days: 45, probability_worst: 5,  prediction: 'Market volatility likely pre-election' },
]

const STAGE_COLORS = {
  WATCH:         'text-ink bg-ink/10',
  DEVELOPING:    'text-gold bg-gold/10',
  ALERT:         'text-orange-400 bg-orange-400/10',
  ACTIVE:        'text-jade bg-jade/10',
  ESCALATING:    'text-ruby bg-ruby/10',
  DE_ESCALATING: 'text-blue-400 bg-blue-400/10',
  RESOLVED:      'text-ink bg-ink/10',
}

// ── Components ──────────────────────────────────────────────────────────────

function DemoBanner({ onExit }) {
  return (
    <div className="bg-gold/10 border-b border-gold/20 px-8 py-2 flex items-center justify-between">
      <div className="flex items-center gap-2 text-sm">
        <Zap size={14} className="text-gold fill-gold" />
        <span className="text-gold font-medium">Demo Mode</span>
        <span className="text-ink">— You're viewing InvestAI with mock data. Sign in to connect live agents.</span>
      </div>
      <div className="flex items-center gap-3">
        <Link href="/auth/signin" className="text-xs btn-gold px-3 py-1 rounded-lg">
          Sign In with Google
        </Link>
        <button onClick={onExit} className="text-xs text-ink hover:text-white transition-colors">
          Exit Demo
        </button>
      </div>
    </div>
  )
}

function SideNav({ activeTab, setActiveTab, userName }) {
  const items = [
    { id: 'dashboard',  label: 'Dashboard',       icon: Activity },
    { id: 'signals',    label: 'Signal Tracker',  icon: Brain,      href: '/signals' },
    { id: 'portfolio',  label: 'Portfolio',        icon: TrendingUp, href: '/portfolio' },
    { id: 'settings',   label: 'Settings',         icon: Settings,   href: '/settings' },
  ]

  const initials = userName ? userName.charAt(0).toUpperCase() : 'D'

  return (
    <div className="w-64 bg-surface-2 border-r border-white/5 flex flex-col h-screen fixed left-0 top-0">
      <div className="p-6 border-b border-white/5">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
            <TrendingUp size={16} className="text-surface" />
          </div>
          <span className="font-display font-bold text-xl text-white">InvestAI</span>
        </div>
      </div>

      <nav className="flex-1 p-4 space-y-1">
        {items.map(item => (
          <Link
            key={item.id}
            href={item.href || '#'}
            className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all text-sm ${
              activeTab === item.id
                ? 'bg-gold/10 text-gold border border-gold/20'
                : 'text-ink hover:text-white hover:bg-white/5'
            }`}
            onClick={() => setActiveTab(item.id)}
          >
            <item.icon size={16} />
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="p-4 border-t border-white/5">
        <div className="flex items-center gap-3 px-4 py-3">
          <div className="w-8 h-8 rounded-full bg-gold/20 flex items-center justify-center text-gold text-sm font-bold">
            {initials}
          </div>
          <div>
            <div className="text-white text-sm font-medium">{userName || 'Demo User'}</div>
            <div className="text-ink text-xs">Pro Plan</div>
          </div>
        </div>
      </div>
    </div>
  )
}

function MarketBar() {
  const items = [
    { label: 'NIFTY', value: '22,450', change: '-0.42%', neg: true },
    { label: 'GOLD',  value: '₹63,450', change: '+0.82%', neg: false },
    { label: 'INR',   value: '83.45',  change: '+0.12%', neg: true },
    { label: 'VIX',   value: '14.2',   change: '+3.6%',  neg: true },
    { label: 'BRENT', value: '$84.2',  change: '+1.24%', neg: false },
  ]
  return (
    <div className="flex items-center gap-6 overflow-x-auto pb-1">
      {items.map((item, i) => (
        <div key={i} className="flex-shrink-0 flex items-center gap-2">
          <span className="text-ink text-xs">{item.label}</span>
          <span className="text-white text-sm font-mono">{item.value}</span>
          <span className={`text-xs font-mono ${item.neg ? 'text-ruby' : 'text-jade'}`}>{item.change}</span>
        </div>
      ))}
    </div>
  )
}

function SignalCard({ signal }) {
  const urgencyStyles = {
    breaking:   'bg-ruby/10 text-ruby border-ruby/20',
    developing: 'bg-gold/10 text-gold border-gold/20',
    long_term:  'bg-ink/10 text-ink border-ink/20',
  }
  return (
    <div className="card p-4 hover:border-white/15 transition-colors">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <p className="text-white text-sm font-medium leading-snug line-clamp-2">{signal.title}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-ink text-xs">{signal.source}</span>
            <span className="text-ink/50 text-xs">·</span>
            <span className="text-ink text-xs">{signal.detected}</span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <span className={`px-2 py-0.5 rounded-full text-xs border ${urgencyStyles[signal.urgency] || urgencyStyles.long_term}`}>
            {signal.urgency}
          </span>
          <span className="text-xs font-mono text-gold">{signal.importance}/10</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-1">
        {Object.entries(signal.sectors).map(([sector, sentiment]) => (
          <span key={sector} className={`text-xs px-2 py-0.5 rounded-full ${
            sentiment === 'positive' ? 'bg-jade/10 text-jade' :
            sentiment === 'negative' ? 'bg-ruby/10 text-ruby' :
            'bg-ink/10 text-ink'
          }`}>
            {sector} {sentiment === 'positive' ? '↑' : sentiment === 'negative' ? '↓' : '→'}
          </span>
        ))}
      </div>
    </div>
  )
}

function AskAI() {
  const [query, setQuery]       = useState('')
  const [amount, setAmount]     = useState('')
  const [loading, setLoading]   = useState(false)
  const [response, setResponse] = useState(null)

  const handleSubmit = async () => {
    if (!query || !amount) return
    setLoading(true)
    await new Promise(r => setTimeout(r, 3000))
    setResponse({
      narrative: `Based on current signals — particularly the Brent crude spike and RBI's cautious stance — here is your personalized plan for ₹${Number(amount).toLocaleString('en-IN')}.

The system detected a medium-term geopolitical signal (Iran-Israel conflict, stage: Escalating) that has elevated oil prices. India imports ~85% of its oil, creating pressure on the current account deficit and INR. Simultaneously, Q3 GDP at 7.2% shows underlying resilience.

For your 1-year horizon with moderate risk tolerance, the allocation balances oil beneficiaries, defensive assets, and a liquid buffer for better entry points.`,
      allocation: [
        { name: 'Nifty 50 Index Fund', pct: 25, reason: 'Core equity, GDP resilience play' },
        { name: 'Gold ETF / SGB',      pct: 20, reason: 'Inflation hedge + INR weakness protection' },
        { name: 'ONGC / Oil India ETF',pct: 15, reason: 'Direct oil price beneficiary' },
        { name: 'IT Sector Fund',      pct: 15, reason: 'INR weakness boosts USD revenue' },
        { name: 'Liquid Fund',         pct: 25, reason: 'Buffer + await better equity entry' },
      ],
      tax_tip: 'Replace Gold ETF with Sovereign Gold Bonds for tax-free maturity redemption under Section 47. Add ₹50,000 ELSS for Section 80C benefit.',
      confidence: 0.74,
      review_date: '3 months',
    })
    setLoading(false)
  }

  return (
    <div className="card-gold p-6">
      <h3 className="font-display font-semibold text-white mb-4 flex items-center gap-2">
        <Brain size={18} className="text-gold" />
        Ask InvestAI
      </h3>
      {!response ? (
        <div className="space-y-3">
          <input
            className="input-dark w-full px-4 py-3 rounded-lg text-sm"
            placeholder="What should I do with my money right now given current market signals?"
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <div className="flex gap-3">
            <div className="relative flex-1">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ink text-sm">₹</span>
              <input
                type="number"
                className="input-dark w-full pl-8 pr-4 py-3 rounded-lg text-sm"
                placeholder="Investment amount"
                value={amount}
                onChange={e => setAmount(e.target.value)}
              />
            </div>
            <select className="input-dark px-4 py-3 rounded-lg text-sm bg-surface-3">
              <option>1 year</option>
              <option>6 months</option>
              <option>2 years</option>
              <option>5 years</option>
            </select>
          </div>
          <button
            onClick={handleSubmit}
            disabled={loading || !query || !amount}
            className="w-full btn-gold py-3 rounded-lg flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {loading ? (
              <>
                <RefreshCw size={16} className="animate-spin" />
                Running 9 agents in parallel...
              </>
            ) : (
              <>Analyze & Build Plan <ChevronRight size={16} /></>
            )}
          </button>
          {loading && (
            <div className="space-y-1 text-xs text-ink font-mono">
              <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-jade animate-pulse" />Signal Watcher scanning 12 sources...</div>
              <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-gold animate-pulse" />Research Agent analyzing India impact chain...</div>
              <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />Pattern Matcher finding historical analogues...</div>
              <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-ink animate-pulse" />Tax Agent optimizing for 30% bracket...</div>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-5">
          <p className="text-ink-light text-sm leading-relaxed">{response.narrative}</p>
          <div>
            <h4 className="text-white text-sm font-semibold mb-3">Recommended Allocation</h4>
            <div className="space-y-2">
              {response.allocation.map((item, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="w-8 text-right text-gold text-sm font-mono">{item.pct}%</div>
                  <div className="flex-1 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-gold to-gold-light rounded-full" style={{ width: `${item.pct}%` }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-white text-xs font-medium">{item.name}</div>
                    <div className="text-ink text-xs">{item.reason}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-jade/5 border border-jade/20 rounded-lg p-3">
            <div className="text-jade text-xs font-semibold mb-1">💰 Tax Optimization</div>
            <p className="text-ink text-xs">{response.tax_tip}</p>
          </div>
          <div className="flex items-center justify-between text-xs text-ink">
            <span>Confidence: <span className="text-gold">{(response.confidence * 100).toFixed(0)}%</span></span>
            <span>Review in: <span className="text-white">{response.review_date}</span></span>
          </div>
          <button onClick={() => setResponse(null)} className="w-full btn-ghost py-2 rounded-lg text-sm">
            Ask another question
          </button>
        </div>
      )}
    </div>
  )
}

// ── Main Dashboard ──────────────────────────────────────────────────────────

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [demoMode, setDemoMode]   = useState(false)
  const [userName, setUserName]   = useState('Sameer')
  const router = useRouter()

  useEffect(() => {
    const isDemo = sessionStorage.getItem('demo_mode')
    if (isDemo === 'true') {
      setDemoMode(true)
      try {
        const user = JSON.parse(sessionStorage.getItem('demo_user') || '{}')
        if (user.name) setUserName(user.name)
      } catch {}
    }
  }, [])

  const handleExitDemo = () => {
    sessionStorage.removeItem('demo_mode')
    sessionStorage.removeItem('demo_user')
    router.push('/')
  }

  const greeting = () => {
    const h = new Date().getHours()
    if (h < 12) return 'Good morning'
    if (h < 17) return 'Good afternoon'
    return 'Good evening'
  }

  return (
    <>
      <Head><title>Dashboard — InvestAI</title></Head>
      <div className="flex min-h-screen bg-surface">
        <SideNav activeTab={activeTab} setActiveTab={setActiveTab} userName={demoMode ? 'Demo User' : userName} />

        <div className="ml-64 flex-1 min-w-0">
          {/* Demo banner */}
          {demoMode && <DemoBanner onExit={handleExitDemo} />}

          {/* Top bar */}
          <div className="sticky top-0 z-40 bg-surface/90 backdrop-blur-md border-b border-white/5 px-8 py-3">
            <div className="flex items-center justify-between">
              <MarketBar />
              <div className="flex items-center gap-3">
                <button className="relative p-2 text-ink hover:text-white transition-colors">
                  <Bell size={18} />
                  <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-ruby" />
                </button>
                <div className="w-8 h-8 rounded-full bg-gold/20 flex items-center justify-center text-gold text-sm font-bold">
                  {demoMode ? 'D' : userName.charAt(0)}
                </div>
              </div>
            </div>
          </div>

          <div className="p-8 space-y-8">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
              <h1 className="font-display text-3xl font-bold text-white mb-1">
                {greeting()}, {demoMode ? 'Demo User' : userName}
              </h1>
              <p className="text-ink">4 new signals detected overnight. 1 requires your attention.</p>
            </motion.div>

            {/* Key metrics */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
              className="grid grid-cols-4 gap-4">
              {[
                { label: 'Portfolio Value', value: '₹1,13,600', change: '+13.6%', pos: true },
                { label: 'Active Signals',  value: '4',         change: '2 high priority', pos: null },
                { label: 'Signal Coverage', value: '67%',       change: 'Connect LinkedIn for 89%', pos: null },
                { label: 'Advice Accuracy', value: '74.8%',     change: 'Last 90 days', pos: true },
              ].map((m, i) => (
                <div key={i} className="card p-5">
                  <div className="text-ink text-xs mb-2">{m.label}</div>
                  <div className="font-display text-2xl font-bold text-white mb-1">{m.value}</div>
                  <div className={`text-xs ${m.pos === true ? 'text-jade' : m.pos === false ? 'text-ruby' : 'text-ink'}`}>{m.change}</div>
                </div>
              ))}
            </motion.div>

            <div className="grid grid-cols-3 gap-6">
              {/* Portfolio chart */}
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
                className="col-span-2 card p-6">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h3 className="font-display font-semibold text-white">Portfolio Performance</h3>
                    <p className="text-ink text-xs">vs Nifty 50 (6 months)</p>
                  </div>
                  <span className="text-jade text-sm font-mono">+13.6%</span>
                </div>
                <ResponsiveContainer width="100%" height={180}>
                  <AreaChart data={MOCK_PORTFOLIO_PERFORMANCE}>
                    <defs>
                      <linearGradient id="goldGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#D4A843" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#D4A843" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="month" tick={{ fill: '#8892A4', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#8892A4', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `₹${(v/1000).toFixed(0)}K`} />
                    <Tooltip formatter={v => [`₹${v.toLocaleString('en-IN')}`, 'Value']} contentStyle={{ background: '#1A1E2A', border: '1px solid rgba(212,168,67,0.3)', borderRadius: 8 }} />
                    <Area type="monotone" dataKey="value" stroke="#D4A843" strokeWidth={2} fill="url(#goldGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              </motion.div>

              {/* Allocation donut */}
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
                className="card p-6">
                <h3 className="font-display font-semibold text-white mb-4">Current Allocation</h3>
                <ResponsiveContainer width="100%" height={140}>
                  <PieChart>
                    <Pie data={MOCK_PORTFOLIO_ALLOCATION} cx="50%" cy="50%" innerRadius={45} outerRadius={65} paddingAngle={3} dataKey="value">
                      {MOCK_PORTFOLIO_ALLOCATION.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v, n) => [`${v}%`, n]} contentStyle={{ background: '#1A1E2A', border: '1px solid rgba(212,168,67,0.3)', borderRadius: 8 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-2 mt-3">
                  {MOCK_PORTFOLIO_ALLOCATION.map((item, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: item.color }} />
                      <span className="text-ink text-xs flex-1 truncate">{item.name}</span>
                      <span className="text-white text-xs font-mono">{item.value}%</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            </div>

            {/* Signals + Ask AI + Active Events */}
            <div className="grid grid-cols-3 gap-6">
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-display font-semibold text-white">Latest Signals</h3>
                  <Link href="/signals" className="text-gold text-xs hover:underline flex items-center gap-1">View all <ChevronRight size={12} /></Link>
                </div>
                <div className="space-y-3">
                  {MOCK_SIGNALS.map(s => <SignalCard key={s.id} signal={s} />)}
                </div>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
                <h3 className="font-display font-semibold text-white mb-4">Get Advice</h3>
                <AskAI />
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-display font-semibold text-white">Active Events</h3>
                  <Link href="/signals" className="text-gold text-xs hover:underline flex items-center gap-1">View all <ChevronRight size={12} /></Link>
                </div>
                <div className="space-y-3">
                  {MOCK_ACTIVE_EVENTS.map((event, i) => (
                    <div key={i} className="card p-4 hover:border-white/15 transition-colors">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <p className="text-white text-sm font-medium leading-tight">{event.title}</p>
                        <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${STAGE_COLORS[event.stage] || STAGE_COLORS.WATCH}`}>
                          {event.stage}
                        </span>
                      </div>
                      <p className="text-ink text-xs mb-3">{event.prediction}</p>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-ink">Day {event.days}</span>
                        <div className="flex items-center gap-1 text-ink">
                          Worst case: <span className="text-ruby">{event.probability_worst}%</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}