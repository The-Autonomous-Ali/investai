import Head from 'next/head'
import Link from 'next/link'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { TrendingUp, Brain, Shield, Zap, ChevronRight, ArrowRight, Activity, Globe, Lock } from 'lucide-react'

const TICKER_ITEMS = [
  { symbol: 'NIFTY 50', value: '22,450.20', change: '-0.42%', negative: true },
  { symbol: 'SENSEX',   value: '73,912.45', change: '-0.38%', negative: true },
  { symbol: 'GOLD MCX', value: '₹63,450',   change: '+0.82%', negative: false },
  { symbol: 'USD/INR',  value: '83.45',      change: '+0.12%', negative: true },
  { symbol: 'BRENT',    value: '$84.20',      change: '+1.24%', negative: false },
  { symbol: 'INDIA VIX','value': '14.2',      change: '+3.6%',  negative: true },
]

const FEATURES = [
  {
    icon: Brain,
    title: 'Multi-Agent Intelligence',
    desc: 'A team of 9 specialized AI agents — Signal Watcher, Research Analyst, Pattern Matcher, Portfolio Builder, Tax Optimizer — all working in parallel, checking each other\'s work.',
  },
  {
    icon: Globe,
    title: 'Signal Chaining',
    desc: 'From a LinkedIn post by the RBI Governor → geopolitical analysis → India sector impact → your portfolio action. The system follows the chain so you don\'t have to.',
  },
  {
    icon: Activity,
    title: 'Temporal Intelligence',
    desc: 'Every event is classified by duration — micro (days) to long-term (years). The system tells you what to do today, this week, and this month — with declining confidence disclosed.',
  },
  {
    icon: Shield,
    title: 'Memory & Accountability',
    desc: 'Every recommendation is stored. In 90 days, the system scores how well its advice aged. You can see our track record. No hiding.',
  },
  {
    icon: TrendingUp,
    title: 'India Tax Intelligence',
    desc: 'Not just what to buy — but how to hold it. ELSS vs regular equity, SGB vs Gold ETF, LTCG vs STCG timing. CA-level tax optimization built in.',
  },
  {
    icon: Zap,
    title: 'Real-Time Alerts',
    desc: 'When a trigger you set fires — Brent crosses $105, India VIX spikes above 20, RBI makes an emergency announcement — you get an alert with the action to take.',
  },
]

const SIGNAL_CHAIN_STEPS = [
  { label: 'LinkedIn Signal',  desc: 'RBI Governor posts about "vigilance on inflation"', color: 'from-blue-500 to-blue-700' },
  { label: 'Geo Context',      desc: 'Iran-Israel escalation → Hormuz risk rises',         color: 'from-orange-500 to-orange-700' },
  { label: 'Commodity Impact', desc: 'Oil supply cut → Brent spikes to $96',               color: 'from-red-500 to-red-700' },
  { label: 'India Impact',     desc: 'India imports 85% oil → CAD widens → INR weakens',   color: 'from-yellow-500 to-yellow-700' },
  { label: 'Sector Analysis',  desc: 'Avoid: Aviation, Paints. Buy: ONGC, Gold, IT',       color: 'from-green-500 to-green-700' },
  { label: 'Your Action Plan', desc: '₹10L allocation with tax optimization & exit triggers', color: 'from-gold-500 to-gold-700' },
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
    cta: 'Start Starter',
    highlight: false,
  },
  {
    name: 'Pro',
    price: '₹2,099',
    period: '/month',
    features: ['Unlimited queries', 'All sources + Twitter', '12 month memory', 'Full tax optimization', 'Real-time alerts', 'Event predictions'],
    cta: 'Start Pro',
    highlight: true,
    badge: 'Most Popular',
  },
  {
    name: 'Elite',
    price: '₹4,199',
    period: '/month',
    features: ['Everything in Pro', 'LinkedIn signals', 'Unlimited memory', 'API access', 'Priority support'],
    cta: 'Start Elite',
    highlight: false,
  },
]

function TickerBar() {
  const doubled = [...TICKER_ITEMS, ...TICKER_ITEMS]
  return (
    <div className="border-b border-white/5 bg-surface-2 py-2 ticker-wrap">
      <div className="ticker-content">
        {doubled.map((item, i) => (
          <span key={i} className="inline-flex items-center gap-2 mx-8 text-sm font-mono">
            <span className="text-ink-light">{item.symbol}</span>
            <span className="text-white">{item.value}</span>
            <span className={item.negative ? 'text-ruby' : 'text-jade'}>{item.change}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

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
        {/* Navigation */}
        <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-surface/90 backdrop-blur-md">
          <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
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
              <Link href="/auth/signin" className="btn-ghost px-4 py-2 rounded-lg text-sm">Sign In</Link>
              <Link href="/auth/signin" className="btn-gold px-4 py-2 rounded-lg text-sm">Get Started Free</Link>
            </div>
          </div>
        </nav>

        {/* Ticker */}
        <div className="pt-16">
          <TickerBar />
        </div>

        {/* Hero */}
        <section className="relative pt-24 pb-32 px-6 overflow-hidden">
          {/* Background orbs */}
          <div className="absolute top-20 left-1/4 w-96 h-96 bg-gold/5 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute top-40 right-1/4 w-80 h-80 bg-blue-500/5 rounded-full blur-3xl pointer-events-none" />

          <div className="max-w-5xl mx-auto text-center relative z-10">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: mounted ? 1 : 0, y: mounted ? 0 : 20 }}
              transition={{ duration: 0.6 }}
            >
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-gold/30 bg-gold/5 text-gold text-sm mb-8">
                <Zap size={14} />
                <span>9 Specialized AI Agents Working Together</span>
              </div>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: mounted ? 1 : 0, y: mounted ? 0 : 30 }}
              transition={{ duration: 0.7, delay: 0.1 }}
              className="font-display text-6xl md:text-7xl font-bold leading-tight mb-6"
            >
              Your money. <br />
              <span className="text-gold-gradient">Smarter decisions.</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: mounted ? 1 : 0, y: mounted ? 0 : 20 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="text-xl text-ink-light max-w-2xl mx-auto mb-10 leading-relaxed"
            >
              InvestAI chains global signals — from LinkedIn posts by the RBI Governor to 
              geopolitical events to sector impacts — and turns them into a specific, 
              tax-optimized investment plan for your ₹.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: mounted ? 1 : 0, y: mounted ? 0 : 20 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="flex flex-col sm:flex-row items-center justify-center gap-4"
            >
              <Link href="/auth/signin" className="btn-gold px-8 py-4 rounded-xl text-lg flex items-center gap-2">
                Start Free <ArrowRight size={18} />
              </Link>
              <Link href="#how-it-works" className="btn-ghost px-8 py-4 rounded-xl text-lg">
                See How It Works
              </Link>
            </motion.div>

            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: mounted ? 1 : 0 }}
              transition={{ delay: 0.5 }}
              className="mt-4 text-xs text-ink"
            >
              Free forever plan available • No credit card required • SEBI disclaimer applies
            </motion.p>
          </div>
        </section>

        {/* Signal Chain Visualization */}
        <section id="how-it-works" className="py-24 px-6 bg-surface-2">
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="font-display text-4xl font-bold mb-4">Signal Chaining in Action</h2>
              <p className="text-ink-light text-lg max-w-2xl mx-auto">
                One LinkedIn post from the RBI Governor becomes a full portfolio action plan in under 30 seconds.
              </p>
            </div>

            <div className="relative">
              {/* Chain line */}
              <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gradient-to-b from-blue-500/50 via-gold/50 to-jade/50 hidden md:block" />

              <div className="space-y-6">
                {SIGNAL_CHAIN_STEPS.map((step, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: i % 2 === 0 ? -30 : 30 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.1 }}
                    className={`flex items-center gap-6 ${i % 2 === 0 ? 'md:flex-row' : 'md:flex-row-reverse'}`}
                  >
                    <div className={`flex-1 card p-5 ${i % 2 === 0 ? 'md:text-right' : ''}`}>
                      <div className="text-gold text-xs font-mono mb-1">STEP {i + 1}</div>
                      <div className="font-display font-semibold text-white mb-1">{step.label}</div>
                      <div className="text-ink text-sm">{step.desc}</div>
                    </div>
                    <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${step.color} flex-shrink-0 flex items-center justify-center text-white font-bold text-sm z-10`}>
                      {i + 1}
                    </div>
                    <div className="flex-1 hidden md:block" />
                  </motion.div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="py-24 px-6">
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="font-display text-4xl font-bold mb-4">Built Different</h2>
              <p className="text-ink-light text-lg">Not a chatbot. Not a robo-advisor. A full intelligence system.</p>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
              {FEATURES.map((f, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.08 }}
                  className="card p-6 hover:border-gold/30 transition-colors group"
                >
                  <div className="w-10 h-10 rounded-lg bg-gold/10 flex items-center justify-center mb-4 group-hover:bg-gold/20 transition-colors">
                    <f.icon size={20} className="text-gold" />
                  </div>
                  <h3 className="font-display font-semibold text-white mb-2">{f.title}</h3>
                  <p className="text-ink text-sm leading-relaxed">{f.desc}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="py-24 px-6 bg-surface-2">
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="font-display text-4xl font-bold mb-4">Simple Pricing</h2>
              <p className="text-ink-light text-lg">Start free. Upgrade when you need more signals.</p>
            </div>
            <div className="grid md:grid-cols-4 gap-6">
              {PLANS.map((plan, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                  className={`relative rounded-xl p-6 flex flex-col ${
                    plan.highlight
                      ? 'card-gold bg-gradient-to-b from-surface-3 to-surface-2'
                      : 'card'
                  }`}
                >
                  {plan.badge && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-gold rounded-full text-surface text-xs font-bold">
                      {plan.badge}
                    </div>
                  )}
                  <div className="mb-6">
                    <div className="font-display font-bold text-white text-lg mb-1">{plan.name}</div>
                    <div className="flex items-end gap-1">
                      <span className="font-display font-bold text-3xl text-gold">{plan.price}</span>
                      <span className="text-ink text-sm mb-1">{plan.period}</span>
                    </div>
                  </div>
                  <ul className="space-y-2 mb-8 flex-1">
                    {plan.features.map((feat, j) => (
                      <li key={j} className="flex items-start gap-2 text-sm text-ink-light">
                        <span className="text-jade mt-0.5">✓</span>
                        {feat}
                      </li>
                    ))}
                  </ul>
                  <Link
                    href="/auth/signin"
                    className={`w-full py-3 rounded-lg text-center text-sm font-semibold font-display transition-all ${
                      plan.highlight ? 'btn-gold' : 'btn-ghost'
                    }`}
                  >
                    {plan.cta}
                  </Link>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Disclaimer & Footer */}
        <footer className="py-12 px-6 border-t border-white/5">
          <div className="max-w-6xl mx-auto">
            <div className="flex items-center gap-2 mb-6">
              <Lock size={14} className="text-ink" />
              <p className="text-ink text-xs leading-relaxed">
                <strong className="text-ink-light">Disclaimer:</strong> InvestAI provides financial information for educational purposes only. 
                It is not a SEBI-registered investment advisor. All information should be independently verified. 
                Past signal performance does not guarantee future results. Please consult a qualified financial advisor.
              </p>
            </div>
            <div className="flex items-center justify-between text-ink text-sm">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
                  <TrendingUp size={12} className="text-surface" />
                </div>
                <span className="font-display font-bold text-white">InvestAI</span>
              </div>
              <div>© 2024 InvestAI. Made for Indian investors.</div>
            </div>
          </div>
        </footer>
      </div>
    </>
  )
}
