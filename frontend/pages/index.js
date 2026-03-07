import Head from 'next/head'
import Link from 'next/link'
import { useState, useEffect, useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import {
  TrendingUp, Brain, Shield, Zap, ArrowRight, Activity,
  Globe, Lock, BarChart2, AlertCircle, ChevronDown, Star,
  Target, Clock, CheckCircle
} from 'lucide-react'

// ─── Data ────────────────────────────────────────────────────────────────────

const TICKER_ITEMS = [
  { symbol: 'NIFTY 50',  value: '22,450.20', change: '-0.42%', negative: true  },
  { symbol: 'SENSEX',    value: '73,912.45', change: '-0.38%', negative: true  },
  { symbol: 'GOLD MCX',  value: '₹63,450',   change: '+0.82%', negative: false },
  { symbol: 'USD/INR',   value: '83.45',     change: '+0.12%', negative: true  },
  { symbol: 'BRENT',     value: '$84.20',    change: '+1.24%', negative: false },
  { symbol: 'INDIA VIX', value: '14.2',      change: '+3.6%',  negative: true  },
  { symbol: 'RELIANCE',  value: '₹2,892',    change: '+0.54%', negative: false },
  { symbol: 'HDFC BANK', value: '₹1,620',    change: '-0.21%', negative: true  },
]

const STATS = [
  { value: '9',     suffix: '',    label: 'Specialized AI Agents'    },
  { value: '30',    suffix: 's',   label: 'Signal-to-Action Time'    },
  { value: '90',    suffix: 'd',   label: 'Advice Accountability'    },
  { value: '100',   suffix: '%',   label: 'India-Focused Intelligence'},
]

const SIGNAL_CHAIN_STEPS = [
  {
    icon: '📡',
    label: 'LinkedIn Signal',
    desc: 'RBI Governor posts about "vigilance on inflation"',
    color: 'from-blue-500/20 to-blue-600/10',
    border: 'border-blue-500/30',
    dot: 'bg-blue-500',
  },
  {
    icon: '🌐',
    label: 'Geo Context',
    desc: 'Iran-Israel escalation → Hormuz risk rises to Level 4',
    color: 'from-orange-500/20 to-orange-600/10',
    border: 'border-orange-500/30',
    dot: 'bg-orange-500',
  },
  {
    icon: '🛢️',
    label: 'Commodity Impact',
    desc: 'Oil supply cut modeled → Brent projected at $96',
    color: 'from-red-500/20 to-red-600/10',
    border: 'border-red-500/30',
    dot: 'bg-red-500',
  },
  {
    icon: '🇮🇳',
    label: 'India Macro Impact',
    desc: 'India imports 85% oil → CAD widens → INR weakens to 85.2',
    color: 'from-yellow-500/20 to-yellow-600/10',
    border: 'border-yellow-500/30',
    dot: 'bg-yellow-500',
  },
  {
    icon: '📊',
    label: 'Sector Rotation',
    desc: 'Avoid: Aviation, Paints. Accumulate: ONGC, Gold, IT exports',
    color: 'from-green-500/20 to-green-600/10',
    border: 'border-green-500/30',
    dot: 'bg-green-500',
  },
  {
    icon: '📋',
    label: 'Your Action Plan',
    desc: '₹10L allocation with tax optimization & exit triggers generated',
    color: 'from-yellow-400/20 to-yellow-600/10',
    border: 'border-yellow-400/40',
    dot: 'bg-yellow-400',
  },
]

const FEATURES = [
  {
    icon: Brain,
    title: 'Multi-Agent Intelligence',
    desc: '9 specialized AI agents — Signal Watcher, Research Analyst, Pattern Matcher, Portfolio Builder, Tax Optimizer — working in parallel and cross-checking each other.',
    tag: 'CORE',
  },
  {
    icon: Globe,
    title: 'Signal Chaining',
    desc: 'From a LinkedIn post by the RBI Governor → geopolitical analysis → India sector impact → your portfolio action. The system follows the chain so you don\'t have to.',
    tag: 'UNIQUE',
  },
  {
    icon: Clock,
    title: 'Temporal Intelligence',
    desc: 'Every event is classified by duration — micro (days) to long-term (years). The system tells you what to do today, this week, and this month — with declining confidence disclosed.',
    tag: 'UNIQUE',
  },
  {
    icon: Target,
    title: 'Memory & Accountability',
    desc: 'Every recommendation is stored. In 90 days, the system scores how well its advice aged. You can see our track record. No hiding.',
    tag: 'TRUST',
  },
  {
    icon: TrendingUp,
    title: 'India Tax Intelligence',
    desc: 'Not just what to buy — but how to hold it. ELSS vs regular equity, SGB vs Gold ETF, LTCG vs STCG timing. CA-level tax optimization built in.',
    tag: 'INDIA',
  },
  {
    icon: Zap,
    title: 'Real-Time Alerts',
    desc: 'When a trigger fires — Brent crosses $105, India VIX spikes above 20, RBI makes an emergency announcement — you get an alert with the exact action to take.',
    tag: 'LIVE',
  },
]

const PLANS = [
  {
    name: 'Free',
    price: '₹0',
    period: 'forever',
    features: ['3 queries/month', 'News signals only', 'Basic allocation', 'No memory'],
    cta: 'Start Free',
    highlight: false,
  },
  {
    name: 'Starter',
    price: '₹999',
    period: '/month',
    features: ['30 queries/month', 'News + Market data', '3 month memory', 'Basic tax tips', 'Portfolio tracking'],
    cta: 'Get Starter',
    highlight: false,
  },
  {
    name: 'Pro',
    price: '₹2,099',
    period: '/month',
    features: ['Unlimited queries', 'All sources + Twitter', '12 month memory', 'Full tax optimization', 'Real-time alerts', 'Event predictions'],
    cta: 'Get Pro',
    highlight: true,
    badge: 'Most Popular',
  },
  {
    name: 'Elite',
    price: '₹4,199',
    period: '/month',
    features: ['Everything in Pro', 'LinkedIn signals', 'Unlimited memory', 'API access', 'Priority support'],
    cta: 'Get Elite',
    highlight: false,
  },
]

// ─── Animated Counter ────────────────────────────────────────────────────────

function AnimatedCounter({ value, suffix }) {
  const [count, setCount] = useState(0)
  const ref = useRef(null)
  const inView = useInView(ref, { once: true })

  useEffect(() => {
    if (!inView) return
    const target = parseInt(value)
    const duration = 1500
    const step = target / (duration / 16)
    let current = 0
    const timer = setInterval(() => {
      current = Math.min(current + step, target)
      setCount(Math.floor(current))
      if (current >= target) clearInterval(timer)
    }, 16)
    return () => clearInterval(timer)
  }, [inView, value])

  return (
    <span ref={ref} className="tabular-nums">
      {count}{suffix}
    </span>
  )
}

// ─── Ticker ──────────────────────────────────────────────────────────────────

function TickerBar() {
  const doubled = [...TICKER_ITEMS, ...TICKER_ITEMS, ...TICKER_ITEMS]
  return (
    <div className="border-b border-white/5 bg-surface-2 py-2 ticker-wrap overflow-hidden">
      <div className="ticker-content flex">
        {doubled.map((item, i) => (
          <span key={i} className="inline-flex items-center gap-2 mx-8 text-sm font-mono whitespace-nowrap flex-shrink-0">
            <span className="text-ink-light">{item.symbol}</span>
            <span className="text-white font-medium">{item.value}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded ${item.negative ? 'text-ruby bg-ruby/10' : 'text-jade bg-jade/10'}`}>
              {item.change}
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}

// ─── Mock Terminal Card ───────────────────────────────────────────────────────

function LiveSignalCard() {
  const [step, setStep] = useState(0)
  const steps = [
    '🔍 Scanning 47 signal sources...',
    '📡 RBI Governor LinkedIn post detected',
    '🧠 Orchestrator activating 9 agents...',
    '🌐 Geo-political context: Hormuz risk ↑',
    '📊 Sector rotation model running...',
    '✅ Action plan ready in 28s',
  ]

  useEffect(() => {
    const t = setInterval(() => setStep(s => (s + 1) % steps.length), 1800)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="card rounded-2xl p-5 border border-white/10 bg-surface-2/80 backdrop-blur-sm">
      <div className="flex items-center gap-2 mb-4 border-b border-white/5 pb-3">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500/80" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
          <div className="w-3 h-3 rounded-full bg-green-500/80" />
        </div>
        <span className="text-xs text-ink font-mono ml-2">investai — live signal processing</span>
        <div className="ml-auto flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-jade animate-pulse" />
          <span className="text-xs text-jade font-mono">LIVE</span>
        </div>
      </div>
      <div className="space-y-2 font-mono text-sm min-h-[160px]">
        {steps.slice(0, step + 1).map((s, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            className={`flex items-center gap-2 ${i === step ? 'text-white' : 'text-ink'}`}
          >
            <span className="text-gold/60 select-none">{'>'}</span>
            <span>{s}</span>
            {i === step && <span className="inline-block w-2 h-4 bg-gold/80 animate-pulse ml-1" />}
          </motion.div>
        ))}
      </div>
      <div className="mt-4 pt-3 border-t border-white/5">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-ink">Recommended Action:</span>
          <span className="text-jade">+12.4% potential return</span>
        </div>
        <div className="mt-2 p-2 rounded-lg bg-jade/10 border border-jade/20 text-xs font-mono text-jade">
          BUY ONGC 40% • GOLD ETF 30% • IT Index 30%
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  return (
    <>
      <Head>
        <title>InvestAI — AI-Powered Investment Intelligence for India</title>
        <meta name="description" content="Multi-agent AI that chains global signals to predict India market impact. Not just a chatbot — a full intelligence system." />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <div className="min-h-screen bg-surface">

        {/* ── Navigation ─────────────────────────────────────────────── */}
        <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-surface/90 backdrop-blur-md">
          <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center shadow-lg shadow-gold/20">
                <TrendingUp size={16} className="text-surface" />
              </div>
              <span className="font-display font-bold text-xl text-white">InvestAI</span>
            </div>
            <div className="hidden md:flex items-center gap-8 text-sm text-ink">
              <Link href="#how-it-works" className="hover:text-gold transition-colors">How It Works</Link>
              <Link href="#features"     className="hover:text-gold transition-colors">Features</Link>
              <Link href="#pricing"      className="hover:text-gold transition-colors">Pricing</Link>
            </div>
            <div className="flex items-center gap-3">
              <Link href="/auth/signin" className="btn-ghost px-4 py-2 rounded-lg text-sm font-medium">Sign In</Link>
              <Link href="/auth/signin" className="btn-gold px-4 py-2 rounded-lg text-sm font-semibold shadow-lg shadow-gold/20">
                Get Started Free
              </Link>
            </div>
          </div>
        </nav>

        {/* ── Ticker ─────────────────────────────────────────────────── */}
        <div className="pt-16">
          <TickerBar />
        </div>

        {/* ── Hero ───────────────────────────────────────────────────── */}
        <section className="relative pt-20 pb-28 px-6 overflow-hidden">
          {/* Layered background effects */}
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute top-10 left-1/3 w-[500px] h-[500px] bg-gold/4 rounded-full blur-[120px]" />
            <div className="absolute top-32 right-1/4 w-[400px] h-[400px] bg-blue-500/4 rounded-full blur-[100px]" />
            <div className="absolute bottom-0 left-1/2 w-[600px] h-[200px] -translate-x-1/2 bg-gold/3 rounded-full blur-[80px]" />
            {/* Grid lines */}
            <div className="absolute inset-0 opacity-[0.03]"
              style={{ backgroundImage: 'linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)', backgroundSize: '80px 80px' }}
            />
          </div>

          <div className="max-w-7xl mx-auto relative z-10">
            <div className="grid lg:grid-cols-2 gap-16 items-center">

              {/* Left — copy */}
              <div>
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: mounted ? 1 : 0, y: mounted ? 0 : 16 }}
                  transition={{ duration: 0.5 }}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-gold/30 bg-gold/5 text-gold text-sm mb-8"
                >
                  <Zap size={13} className="fill-gold" />
                  <span>9 Specialized AI Agents Working Together</span>
                </motion.div>

                <motion.h1
                  initial={{ opacity: 0, y: 24 }}
                  animate={{ opacity: mounted ? 1 : 0, y: mounted ? 0 : 24 }}
                  transition={{ duration: 0.6, delay: 0.1 }}
                  className="font-display text-5xl md:text-6xl lg:text-7xl font-bold leading-[1.08] mb-6 tracking-tight"
                >
                  Your money.<br />
                  <span className="text-gold-gradient">Smarter</span><br />
                  decisions.
                </motion.h1>

                <motion.p
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: mounted ? 1 : 0, y: mounted ? 0 : 16 }}
                  transition={{ duration: 0.6, delay: 0.2 }}
                  className="text-lg text-ink-light max-w-xl mb-10 leading-relaxed"
                >
                  InvestAI chains global signals — from LinkedIn posts by the RBI Governor
                  to geopolitical events to sector impacts — and turns them into a specific,
                  tax-optimized investment plan for your ₹.
                </motion.p>

                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: mounted ? 1 : 0, y: mounted ? 0 : 16 }}
                  transition={{ duration: 0.6, delay: 0.3 }}
                  className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-8"
                >
                  <Link href="/auth/signin" className="btn-gold px-8 py-4 rounded-xl text-base flex items-center gap-2 shadow-xl shadow-gold/20 hover:shadow-gold/30 transition-shadow">
                    Start Free <ArrowRight size={17} />
                  </Link>
                  <Link href="#how-it-works" className="btn-ghost px-8 py-4 rounded-xl text-base flex items-center gap-2 group">
                    See How It Works
                    <ChevronDown size={16} className="group-hover:translate-y-1 transition-transform" />
                  </Link>
                </motion.div>

                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: mounted ? 1 : 0 }}
                  transition={{ delay: 0.5 }}
                  className="flex flex-wrap items-center gap-4 text-xs text-ink"
                >
                  {['Free forever plan', 'No credit card needed', 'SEBI disclaimer applies'].map((t, i) => (
                    <span key={i} className="flex items-center gap-1.5">
                      <CheckCircle size={12} className="text-jade" />
                      {t}
                    </span>
                  ))}
                </motion.div>
              </div>

              {/* Right — live terminal */}
              <motion.div
                initial={{ opacity: 0, x: 30 }}
                animate={{ opacity: mounted ? 1 : 0, x: mounted ? 0 : 30 }}
                transition={{ duration: 0.8, delay: 0.3 }}
                className="hidden lg:block"
              >
                <LiveSignalCard />

                {/* Floating mini-cards */}
                <motion.div
                  animate={{ y: [0, -8, 0] }}
                  transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                  className="absolute -left-8 top-1/2 card rounded-xl p-3 border border-jade/20 bg-surface-2/90 backdrop-blur-sm shadow-xl"
                >
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-jade/10 flex items-center justify-center">
                      <TrendingUp size={14} className="text-jade" />
                    </div>
                    <div>
                      <div className="text-xs text-ink-light">ONGC Signal</div>
                      <div className="text-sm font-bold text-jade">+12.4%</div>
                    </div>
                  </div>
                </motion.div>

                <motion.div
                  animate={{ y: [0, 6, 0] }}
                  transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut', delay: 1 }}
                  className="absolute -right-6 bottom-12 card rounded-xl p-3 border border-gold/20 bg-surface-2/90 backdrop-blur-sm shadow-xl"
                >
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-gold/10 flex items-center justify-center">
                      <AlertCircle size={14} className="text-gold" />
                    </div>
                    <div>
                      <div className="text-xs text-ink-light">Alert Fired</div>
                      <div className="text-sm font-bold text-gold">VIX &gt; 20</div>
                    </div>
                  </div>
                </motion.div>
              </motion.div>

            </div>
          </div>
        </section>

        {/* ── Stats Bar ───────────────────────────────────────────────── */}
        <section className="py-12 px-6 border-y border-white/5 bg-surface-2/50">
          <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8">
            {STATS.map((s, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="text-center"
              >
                <div className="font-display text-4xl font-bold text-gold mb-1">
                  <AnimatedCounter value={s.value} suffix={s.suffix} />
                </div>
                <div className="text-sm text-ink">{s.label}</div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── Signal Chain ────────────────────────────────────────────── */}
        <section id="how-it-works" className="py-24 px-6">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-16">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 text-ink text-xs mb-4 font-mono uppercase tracking-widest">
                How It Works
              </div>
              <h2 className="font-display text-4xl md:text-5xl font-bold mb-4">Signal Chaining in Action</h2>
              <p className="text-ink-light text-lg max-w-2xl mx-auto">
                One LinkedIn post from the RBI Governor becomes a full portfolio action plan in under 30 seconds.
              </p>
            </div>

            <div className="relative">
              {/* Vertical connector line */}
              <div className="absolute left-5 top-5 bottom-5 w-px bg-gradient-to-b from-blue-500/60 via-yellow-500/60 to-jade/60 md:left-1/2" />

              <div className="space-y-4">
                {SIGNAL_CHAIN_STEPS.map((step, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1 }}
                    className={`relative flex gap-6 items-start md:items-center ${i % 2 === 0 ? 'md:flex-row' : 'md:flex-row-reverse'}`}
                  >
                    {/* Content card */}
                    <div className={`flex-1 rounded-xl p-4 border bg-gradient-to-br ${step.color} ${step.border} ml-12 md:ml-0`}>
                      <div className="flex items-start gap-3">
                        <span className="text-2xl">{step.icon}</span>
                        <div>
                          <div className="text-gold text-xs font-mono mb-0.5">STEP {i + 1}</div>
                          <div className="font-display font-semibold text-white text-sm mb-1">{step.label}</div>
                          <div className="text-ink text-sm leading-relaxed">{step.desc}</div>
                        </div>
                      </div>
                    </div>

                    {/* Center dot */}
                    <div className={`absolute left-5 md:left-1/2 md:-translate-x-1/2 w-3 h-3 rounded-full ${step.dot} ring-4 ring-surface z-10`} />

                    {/* Spacer for alternating layout */}
                    <div className="flex-1 hidden md:block" />
                  </motion.div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── Features ────────────────────────────────────────────────── */}
        <section id="features" className="py-24 px-6 bg-surface-2">
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-16">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 text-ink text-xs mb-4 font-mono uppercase tracking-widest">
                Why InvestAI
              </div>
              <h2 className="font-display text-4xl md:text-5xl font-bold mb-4">Built Different</h2>
              <p className="text-ink-light text-lg">Not a chatbot. Not a robo-advisor. A full intelligence system.</p>
            </div>

            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
              {FEATURES.map((f, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.08 }}
                  className="card p-6 hover:border-gold/30 transition-all hover:-translate-y-1 group cursor-default"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="w-11 h-11 rounded-xl bg-gold/10 flex items-center justify-center group-hover:bg-gold/20 transition-colors">
                      <f.icon size={20} className="text-gold" />
                    </div>
                    <span className="text-xs font-mono px-2 py-0.5 rounded border border-white/10 text-ink">
                      {f.tag}
                    </span>
                  </div>
                  <h3 className="font-display font-semibold text-white mb-2 text-base">{f.title}</h3>
                  <p className="text-ink text-sm leading-relaxed">{f.desc}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Pricing ─────────────────────────────────────────────────── */}
        <section id="pricing" className="py-24 px-6">
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-16">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 text-ink text-xs mb-4 font-mono uppercase tracking-widest">
                Pricing
              </div>
              <h2 className="font-display text-4xl md:text-5xl font-bold mb-4">Simple Pricing</h2>
              <p className="text-ink-light text-lg">Start free. Upgrade when you need more signals.</p>
            </div>

            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
              {PLANS.map((plan, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className={`relative rounded-2xl p-6 flex flex-col transition-all ${
                    plan.highlight
                      ? 'bg-gradient-to-b from-gold/10 to-surface-2 border-2 border-gold/40 shadow-xl shadow-gold/10 scale-[1.02]'
                      : 'card hover:border-white/20'
                  }`}
                >
                  {plan.badge && (
                    <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-3 py-1 bg-gold rounded-full text-surface text-xs font-bold whitespace-nowrap shadow-lg">
                      ⭐ {plan.badge}
                    </div>
                  )}

                  <div className="mb-5 pt-1">
                    <div className="font-display font-bold text-white text-lg mb-3">{plan.name}</div>
                    <div className="flex items-end gap-1">
                      <span className={`font-display font-bold text-4xl ${plan.highlight ? 'text-gold' : 'text-white'}`}>
                        {plan.price}
                      </span>
                      <span className="text-ink text-sm mb-1.5">{plan.period}</span>
                    </div>
                  </div>

                  <ul className="space-y-2.5 mb-8 flex-1">
                    {plan.features.map((feat, j) => (
                      <li key={j} className="flex items-start gap-2 text-sm text-ink-light">
                        <CheckCircle size={14} className="text-jade mt-0.5 flex-shrink-0" />
                        {feat}
                      </li>
                    ))}
                  </ul>

                  <Link
                    href="/auth/signin"
                    className={`w-full py-3 rounded-xl text-center text-sm font-semibold font-display transition-all ${
                      plan.highlight
                        ? 'btn-gold shadow-lg shadow-gold/20'
                        : 'btn-ghost hover:border-white/30'
                    }`}
                  >
                    {plan.cta}
                  </Link>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ── CTA Banner ──────────────────────────────────────────────── */}
        <section className="py-20 px-6 bg-surface-2 border-y border-white/5">
          <div className="max-w-3xl mx-auto text-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
            >
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center mx-auto mb-6 shadow-xl shadow-gold/30">
                <Brain size={28} className="text-surface" />
              </div>
              <h2 className="font-display text-4xl md:text-5xl font-bold mb-4">
                Ready to invest smarter?
              </h2>
              <p className="text-ink-light text-lg mb-8">
                Join thousands of Indian investors who let AI do the signal chaining.
              </p>
              <Link href="/auth/signin" className="btn-gold px-10 py-4 rounded-xl text-lg inline-flex items-center gap-2 shadow-xl shadow-gold/20">
                Start Free Today <ArrowRight size={20} />
              </Link>
              <p className="mt-4 text-xs text-ink">No credit card required • Cancel anytime</p>
            </motion.div>
          </div>
        </section>

        {/* ── Footer ──────────────────────────────────────────────────── */}
        <footer className="py-10 px-6">
          <div className="max-w-6xl mx-auto">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 mb-6">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
                  <TrendingUp size={13} className="text-surface" />
                </div>
                <span className="font-display font-bold text-white">InvestAI</span>
              </div>
              <div className="flex items-center gap-1.5 text-ink text-xs max-w-xl">
                <Lock size={12} className="flex-shrink-0 mt-0.5" />
                <p>
                  <strong className="text-ink-light">Disclaimer:</strong> InvestAI provides financial information for educational purposes only.
                  Not a SEBI-registered investment advisor. All information should be independently verified.
                  Past signal performance does not guarantee future results.
                </p>
              </div>
            </div>
            <div className="border-t border-white/5 pt-6 flex items-center justify-between text-ink text-xs">
              <span>© 2024 InvestAI. Made for Indian investors.</span>
              <div className="flex gap-6">
                <Link href="#" className="hover:text-white transition-colors">Privacy</Link>
                <Link href="#" className="hover:text-white transition-colors">Terms</Link>
                <Link href="#" className="hover:text-white transition-colors">Contact</Link>
              </div>
            </div>
          </div>
        </footer>

      </div>
    </>
  )
}