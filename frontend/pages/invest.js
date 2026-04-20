import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { motion, AnimatePresence } from 'framer-motion'
import {
  TrendingUp,
  Brain,
  Globe,
  Shield,
  Zap,
  ChevronRight,
  RefreshCw,
  BarChart2,
  Activity,
  AlertCircle,
  DollarSign,
  Clock,
  MapPin,
} from 'lucide-react'

import { getAdvice, getCurrentUser, loginWithGoogle } from '../lib/api'

const COUNTRIES = [
  { code: 'IN', name: 'India' },
  { code: 'US', name: 'United States' },
  { code: 'GB', name: 'United Kingdom' },
  { code: 'AE', name: 'UAE' },
  { code: 'DE', name: 'Germany' },
  { code: 'SG', name: 'Singapore' },
  { code: 'AU', name: 'Australia' },
  { code: 'JP', name: 'Japan' },
]

const CASH_DEPLOY_TERMS = ['invest', 'deploy', 'allocate', 'put money', 'where should i invest']

const ACTION_STYLES = {
  deploy: 'bg-jade/10 text-jade border border-jade/20',
  add: 'bg-jade/10 text-jade border border-jade/20',
  hold: 'bg-gold/10 text-gold border border-gold/20',
  trim: 'bg-ruby/10 text-ruby border border-ruby/20',
  exit: 'bg-ruby/10 text-ruby border border-ruby/20',
  watch: 'bg-blue-400/10 text-blue-300 border border-blue-400/20',
}

function queryNeedsAmount(query) {
  const normalized = (query || '').toLowerCase()
  return CASH_DEPLOY_TERMS.some((term) => normalized.includes(term))
}

function formatMoney(value, country) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return 'Not available'
  }

  const currency = country === 'India' ? 'INR' : 'USD'
  return new Intl.NumberFormat(country === 'India' ? 'en-IN' : 'en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(Number(value))
}

function formatSignal(signal) {
  if (!signal) return 'Signal'
  if (typeof signal === 'string') return signal
  return signal.title || signal.signal_title || signal.id || 'Signal'
}

function capitalize(value) {
  if (!value) return 'Unknown'
  return value.charAt(0).toUpperCase() + value.slice(1)
}

export default function InvestPage() {
  const router = useRouter()
  const { data: session, status } = useSession()

  const [query, setQuery] = useState('')
  const [amount, setAmount] = useState('')
  const [horizon, setHorizon] = useState('1 year')
  const [country, setCountry] = useState('India')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [error, setError] = useState('')
  const [userName, setUserName] = useState('')
  const [demoMode, setDemoMode] = useState(false)
  const [accountReady, setAccountReady] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      if (typeof window === 'undefined') return

      const isDemo = sessionStorage.getItem('demo_mode') === 'true'
      const storedName = sessionStorage.getItem('investai_user_name')

      if (!cancelled) {
        setDemoMode(isDemo)
        if (storedName) {
          setUserName(storedName)
        }
      }

      if (isDemo) {
        if (!storedName) {
          router.push('/onboarding')
          return
        }
        setAccountReady(false)
        return
      }

      if (status === 'loading') {
        return
      }

      if (status === 'unauthenticated') {
        router.push('/auth/signin')
        return
      }

      try {
        const existingToken = localStorage.getItem('investai_token')
        if (!existingToken) {
          if (!session?.idToken) {
            throw new Error('Missing Google ID token for backend login.')
          }
          await loginWithGoogle(session.idToken)
        }

        const currentUser = await getCurrentUser()
        if (cancelled) return

        const displayName =
          currentUser?.name || session?.user?.name || storedName || 'Investor'

        setUserName(displayName)
        if (currentUser?.country) {
          setCountry(currentUser.country)
        }
        setAccountReady(true)
        sessionStorage.setItem('investai_user_name', displayName)
      } catch (bootstrapError) {
        if (cancelled) return
        console.error('Failed to connect authenticated account:', bootstrapError)
        setAccountReady(false)
        setError('Failed to connect your authenticated account to the backend.')
      }
    }

    bootstrap()

    return () => {
      cancelled = true
    }
  }, [router, session, status])

  const handleAnalyze = async () => {
    const requiresAmount = queryNeedsAmount(query)

    if (!query) return
    if (requiresAmount && !amount) {
      setError('Investment amount is required when the query asks where fresh capital should be deployed.')
      return
    }
    if (demoMode) {
      setError('Demo mode shows the interface only. Live personalized recommendations require an authenticated account and stored portfolio data.')
      return
    }
    if (!accountReady) {
      setError('Your account is still being connected. Retry after authentication completes.')
      return
    }

    setLoading(true)
    setResponse(null)
    setError('')

    try {
      const data = await getAdvice({
        query,
        amount: amount ? Number(amount) : 0,
        horizon,
        country,
      })

      if (data.success && data.recommendation) {
        setResponse(data.recommendation)
        return
      }

      setError(data.error || 'The platform could not produce a recommendation for this query.')
    } catch (requestError) {
      console.error('Failed to get advice:', requestError)
      const detail = requestError.response?.data?.detail
      setError(detail || 'Failed to fetch a recommendation. Check backend auth, market data services, and worker health.')
    } finally {
      setLoading(false)
    }
  }

  const recommendation = response || {}
  const confidencePct = Math.round((recommendation.confidence || 0) * 100)
  const actionStyle = ACTION_STYLES[recommendation.action] || ACTION_STYLES.watch
  const activeDisclaimer =
    recommendation.disclaimer ||
    'Recommendations are generated from stored portfolio context, active signals, and deterministic policy rules. If portfolio data is incomplete, suitability checks are limited.'

  return (
    <div className="min-h-screen bg-surface text-white">
      <Head>
        <title>Investment Advisor - InvestAI</title>
      </Head>

      <nav className="border-b border-white/5 bg-surface-2/50 backdrop-blur-md px-8 py-4 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gold flex items-center justify-center">
              <TrendingUp size={16} className="text-surface" />
            </div>
            <span className="font-display font-bold text-xl">InvestAI</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right hidden sm:block">
              <div className="text-white text-sm font-medium">{userName || 'Investor'}</div>
              <div className="text-ink text-xs">{demoMode ? 'Demo Interface' : 'Connected Account'}</div>
            </div>
            <div className="w-10 h-10 rounded-full bg-gold/20 flex items-center justify-center text-gold font-bold border border-gold/30">
              {(userName || 'I').charAt(0)}
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="grid lg:grid-cols-12 gap-12">
          <div className="lg:col-span-5 space-y-8">
            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}>
              <h1 className="font-display text-4xl font-bold mb-4 leading-tight">
                Evidence First,
                <br />
                <span className="text-gold-gradient">Decision Second.</span>
              </h1>
              <p className="text-ink-light text-lg">
                Ask for capital deployment or a position review. The platform returns a deterministic action with evidence, risks, and invalidation triggers.
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="card p-8 border-gold/20 bg-surface-2/80 shadow-2xl"
            >
              <div className="space-y-6">
                <div>
                  <label className="block text-ink text-sm font-medium mb-3 flex items-center gap-2">
                    <Globe size={14} className="text-gold" /> Country of Residence
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {COUNTRIES.map((option) => (
                      <button
                        key={option.code}
                        onClick={() => setCountry(option.name)}
                        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm border transition-all ${
                          country === option.name
                            ? 'bg-gold/10 border-gold/40 text-gold shadow-lg shadow-gold/5'
                            : 'bg-surface-3 border-white/5 text-ink hover:border-white/20'
                        }`}
                      >
                        <span className="font-mono text-xs">{option.code}</span>
                        <span>{option.name}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-ink text-sm font-medium mb-3 flex items-center gap-2">
                    <Brain size={14} className="text-gold" /> Investment Query
                  </label>
                  <textarea
                    className="input-dark w-full px-4 py-3 rounded-xl min-h-[120px] resize-none"
                    placeholder="Examples: I have 20 Adani Power shares. Should I add more or trim? | I have 50000 to invest over 1 year. Where should I deploy it?"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-ink text-sm font-medium mb-2 flex items-center gap-2">
                      <DollarSign size={14} className="text-gold" /> Amount
                    </label>
                    <input
                      type="number"
                      className="input-dark w-full px-4 py-3 rounded-xl"
                      placeholder="Optional for hold or sell reviews"
                      value={amount}
                      onChange={(event) => setAmount(event.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-ink text-sm font-medium mb-2 flex items-center gap-2">
                      <Clock size={14} className="text-gold" /> Horizon
                    </label>
                    <select
                      className="input-dark w-full px-4 py-3 rounded-xl bg-surface-3"
                      value={horizon}
                      onChange={(event) => setHorizon(event.target.value)}
                    >
                      <option>6 months</option>
                      <option>1 year</option>
                      <option>2 years</option>
                      <option>5 years</option>
                    </select>
                  </div>
                </div>

                {demoMode && (
                  <div className="rounded-xl border border-blue-400/20 bg-blue-400/5 p-4 text-sm text-blue-100">
                    Demo mode is UI-only. Personalized recommendations are disabled until the user is authenticated and the backend portfolio context is available.
                  </div>
                )}

                {error && (
                  <div className="rounded-xl border border-ruby/20 bg-ruby/5 p-4 text-sm text-ruby flex gap-3">
                    <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                <button
                  onClick={handleAnalyze}
                  disabled={loading || !query || (queryNeedsAmount(query) && !amount)}
                  className="btn-gold w-full py-4 rounded-xl flex items-center justify-center gap-3 font-display font-bold text-lg disabled:opacity-50 transition-all shadow-xl shadow-gold/20"
                >
                  {loading ? (
                    <>
                      <RefreshCw size={20} className="animate-spin" />
                      Building Recommendation...
                    </>
                  ) : (
                    <>
                      Analyze Query <ChevronRight size={20} />
                    </>
                  )}
                </button>

                {loading && (
                  <div className="space-y-2 mt-4 text-xs text-ink font-mono bg-surface-3/50 p-4 rounded-xl border border-white/5">
                    <div className="flex items-center gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-jade animate-pulse" />
                      <span>Collecting active market and macro signals...</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse" />
                      <span>Matching portfolio state against sector and company evidence...</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                      <span>Applying deterministic policy rules and suitability checks...</span>
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          </div>

          <div className="lg:col-span-7">
            <AnimatePresence mode="wait">
              {!response && !loading ? (
                <motion.div
                  key="empty"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="h-full flex flex-col items-center justify-center text-center p-12 border-2 border-dashed border-white/10 rounded-3xl"
                >
                  <div className="w-20 h-20 rounded-full bg-surface-2 flex items-center justify-center mb-6">
                    <Zap size={32} className="text-ink-light opacity-30" />
                  </div>
                  <h3 className="text-xl font-semibold mb-2 text-ink-light">Recommendation Workspace</h3>
                  <p className="text-ink max-w-sm">
                    The result will show a final action, evidence, risks, and explicit limits. If the system lacks enough verified context, it will say so instead of forcing a decision.
                  </p>
                </motion.div>
              ) : loading ? (
                <motion.div
                  key="loading"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="h-full flex flex-col items-center justify-center p-12 space-y-8"
                >
                  <div className="relative">
                    <div className="w-24 h-24 border-4 border-gold/10 border-t-gold rounded-full animate-spin" />
                    <Brain className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-gold" size={32} />
                  </div>
                  <div className="text-center space-y-2">
                    <h3 className="text-xl font-bold">Evaluating Position and Market State</h3>
                    <p className="text-ink italic">The platform is checking active signals, portfolio fit, and deterministic policy rules.</p>
                  </div>
                </motion.div>
              ) : (
                <motion.div
                  key="response"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-6"
                >
                  <div className="card p-6 border-gold/10 bg-surface-2">
                    <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                      <div className="flex items-center gap-2">
                        <Activity size={18} className="text-gold" />
                        <h3 className="font-display font-semibold text-lg text-white">Deterministic Recommendation</h3>
                      </div>
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wide ${actionStyle}`}>
                        {recommendation.action || 'watch'}
                      </span>
                    </div>
                    <p className="text-ink-light leading-relaxed">{recommendation.summary}</p>
                    <div className="grid sm:grid-cols-3 gap-4 mt-6">
                      <div className="rounded-xl bg-surface-3/60 p-4 border border-white/5">
                        <div className="text-xs uppercase tracking-wide text-ink mb-1">Confidence</div>
                        <div className="text-2xl font-display font-bold text-white">{confidencePct}%</div>
                      </div>
                      <div className="rounded-xl bg-surface-3/60 p-4 border border-white/5">
                        <div className="text-xs uppercase tracking-wide text-ink mb-1">Action Strength</div>
                        <div className="text-2xl font-display font-bold text-white">{capitalize(recommendation.action_strength)}</div>
                      </div>
                      <div className="rounded-xl bg-surface-3/60 p-4 border border-white/5">
                        <div className="text-xs uppercase tracking-wide text-ink mb-1">Review Date</div>
                        <div className="text-lg font-display font-bold text-white">{recommendation.review_date || 'Pending'}</div>
                      </div>
                    </div>
                  </div>

                  <div className="card p-6 bg-surface-2 border-white/5">
                    <div className="flex items-center gap-2 mb-4">
                      <Brain size={18} className="text-gold" />
                      <h3 className="font-display font-semibold text-white">Thesis</h3>
                    </div>
                    <p className="text-ink-light leading-relaxed whitespace-pre-line">{recommendation.thesis || 'No thesis text returned.'}</p>
                  </div>

                  {recommendation.current_position && (
                    <div className="card p-6 bg-surface-2 border-white/5">
                      <div className="flex items-center gap-2 mb-4">
                        <BarChart2 size={18} className="text-gold" />
                        <h3 className="font-display font-semibold text-white">Tracked Position</h3>
                      </div>
                      <div className="grid sm:grid-cols-4 gap-4 text-sm">
                        <div className="rounded-xl bg-surface-3/60 p-4 border border-white/5">
                          <div className="text-ink text-xs uppercase tracking-wide mb-1">Instrument</div>
                          <div className="text-white font-semibold">{recommendation.current_position.name || recommendation.current_position.symbol}</div>
                        </div>
                        <div className="rounded-xl bg-surface-3/60 p-4 border border-white/5">
                          <div className="text-ink text-xs uppercase tracking-wide mb-1">Quantity</div>
                          <div className="text-white font-semibold">{recommendation.current_position.quantity || 'Not available'}</div>
                        </div>
                        <div className="rounded-xl bg-surface-3/60 p-4 border border-white/5">
                          <div className="text-ink text-xs uppercase tracking-wide mb-1">Current Value</div>
                          <div className="text-white font-semibold">{formatMoney(recommendation.current_position.current_value, country)}</div>
                        </div>
                        <div className="rounded-xl bg-surface-3/60 p-4 border border-white/5">
                          <div className="text-ink text-xs uppercase tracking-wide mb-1">Portfolio Weight</div>
                          <div className="text-white font-semibold">
                            {recommendation.current_position.weight_pct !== null && recommendation.current_position.weight_pct !== undefined
                              ? `${recommendation.current_position.weight_pct}%`
                              : 'Not available'}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="card p-6 bg-surface-2 border-white/5">
                    <div className="flex items-center gap-2 mb-4">
                      <TrendingUp size={18} className="text-gold" />
                      <h3 className="font-display font-semibold text-white">Recommended Moves</h3>
                    </div>
                    <div className="space-y-4">
                      {(recommendation.recommended_moves || []).length === 0 && (
                        <div className="rounded-xl bg-surface-3/60 p-4 border border-white/5 text-ink-light text-sm">
                          No deployable move was returned. This usually means the platform does not yet have enough verified evidence to force an action.
                        </div>
                      )}
                      {(recommendation.recommended_moves || []).map((move, index) => (
                        <div key={`${move.instrument || 'move'}-${index}`} className="rounded-xl bg-surface-3/60 p-4 border border-white/5">
                          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                            <div>
                              <div className="text-white font-semibold">{move.instrument || 'Instrument'}</div>
                              <div className="text-xs text-ink">
                                {(move.instrument_type || 'instrument').toUpperCase()}
                                {move.sector ? ` | ${move.sector}` : ''}
                              </div>
                            </div>
                            <div className="text-right">
                              <div className={`inline-flex px-3 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wide ${ACTION_STYLES[move.action] || ACTION_STYLES.watch}`}>
                                {move.action || 'watch'}
                              </div>
                              <div className="text-xs text-ink mt-1">
                                {move.amount ? formatMoney(move.amount, country) : move.weight_pct ? `${move.weight_pct}%` : 'No sizing'}
                              </div>
                            </div>
                          </div>
                          <p className="text-sm text-ink-light leading-relaxed">{move.rationale}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="grid md:grid-cols-2 gap-6">
                    <div className="card p-6 border-jade/20 bg-jade/5">
                      <div className="flex items-center gap-2 mb-4">
                        <Shield size={18} className="text-jade" />
                        <h3 className="font-display font-semibold text-white">Suitability Checks</h3>
                      </div>
                      <div className="space-y-3 text-sm">
                        <div className="flex items-start justify-between gap-4">
                          <span className="text-ink">Risk profile alignment</span>
                          <span className="text-white font-medium">{capitalize(recommendation.suitability_checks?.risk_profile_alignment)}</span>
                        </div>
                        <div className="flex items-start justify-between gap-4">
                          <span className="text-ink">Concentration</span>
                          <span className="text-white font-medium">{capitalize(recommendation.suitability_checks?.concentration)}</span>
                        </div>
                        <div className="flex items-start justify-between gap-4">
                          <span className="text-ink">Portfolio data</span>
                          <span className="text-white font-medium">{capitalize(recommendation.suitability_checks?.portfolio_data_completeness)}</span>
                        </div>
                        {(recommendation.suitability_checks?.notes || []).map((note, index) => (
                          <div key={`note-${index}`} className="rounded-lg bg-surface-2/70 p-3 border border-white/5 text-ink-light">
                            {note}
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="card p-6 border-ruby/20 bg-ruby/5">
                      <div className="flex items-center gap-2 mb-4">
                        <AlertCircle size={18} className="text-ruby" />
                        <h3 className="font-display font-semibold text-white">Key Risks</h3>
                      </div>
                      <div className="space-y-3 text-sm">
                        {(recommendation.key_risks || []).length === 0 && (
                          <div className="rounded-lg bg-surface-2/70 p-3 border border-white/5 text-ink-light">
                            No explicit risk list was returned for this query.
                          </div>
                        )}
                        {(recommendation.key_risks || []).map((risk, index) => (
                          <div key={`risk-${index}`} className="rounded-lg bg-surface-2/70 p-3 border border-white/5 text-ink-light">
                            {risk}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid md:grid-cols-2 gap-6">
                    <div className="card p-6 bg-surface-2 border-white/5">
                      <div className="flex items-center gap-2 mb-4">
                        <MapPin size={18} className="text-gold" />
                        <h3 className="font-display font-semibold text-white">Evidence</h3>
                      </div>
                      <div className="space-y-3 text-sm">
                        {(recommendation.evidence?.signals || []).map((signal, index) => (
                          <div key={`signal-${index}`} className="rounded-lg bg-surface-3/60 p-3 border border-white/5 text-ink-light">
                            {formatSignal(signal)}
                          </div>
                        ))}
                        {recommendation.evidence?.macro_summary && (
                          <div className="rounded-lg bg-surface-3/60 p-3 border border-white/5 text-ink-light">
                            {recommendation.evidence.macro_summary}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="card p-6 bg-surface-2 border-white/5">
                      <div className="flex items-center gap-2 mb-4">
                        <Clock size={18} className="text-gold" />
                        <h3 className="font-display font-semibold text-white">Watch Items</h3>
                      </div>
                      <div className="space-y-3 text-sm">
                        {(recommendation.watch_items || []).length === 0 && (
                          <div className="rounded-lg bg-surface-3/60 p-3 border border-white/5 text-ink-light">
                            No follow-up triggers were returned for this query.
                          </div>
                        )}
                        {(recommendation.watch_items || []).map((item, index) => (
                          <div key={`watch-${index}`} className="rounded-lg bg-surface-3/60 p-3 border border-white/5">
                            <div className="text-white font-medium">{item.trigger || 'Monitor condition'}</div>
                            <div className="text-ink-light mt-1">{item.implication || 'No implication text returned.'}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {(recommendation.invalidation_triggers || []).length > 0 && (
                    <div className="card p-6 border-gold/10 bg-surface-2">
                      <div className="flex items-center gap-2 mb-4">
                        <Activity size={18} className="text-gold" />
                        <h3 className="font-display font-semibold text-white">Invalidation Triggers</h3>
                      </div>
                      <div className="space-y-3">
                        {(recommendation.invalidation_triggers || []).map((trigger, index) => (
                          <div key={`trigger-${index}`} className="rounded-lg bg-surface-3/60 p-3 border border-white/5 text-ink-light text-sm">
                            {trigger}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {(recommendation.known_limits || []).length > 0 && (
                    <div className="card p-6 border-blue-400/20 bg-blue-400/5">
                      <div className="flex items-center gap-2 mb-4">
                        <AlertCircle size={18} className="text-blue-300" />
                        <h3 className="font-display font-semibold text-white">Known Limits</h3>
                      </div>
                      <div className="space-y-3">
                        {(recommendation.known_limits || []).map((limit, index) => (
                          <div key={`limit-${index}`} className="rounded-lg bg-surface-2/70 p-3 border border-white/5 text-blue-100 text-sm">
                            {limit}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-between px-2 text-xs text-ink font-mono">
                    <div className="flex items-center gap-4">
                      <span>Policy: <span className="text-gold">{recommendation.policy_version || 'pending'}</span></span>
                      <span>Query Type: <span className="text-white">{recommendation.query_type || 'unknown'}</span></span>
                    </div>
                    <button
                      onClick={() => {
                        setResponse(null)
                        setError('')
                      }}
                      className="text-ink hover:text-white underline underline-offset-4"
                    >
                      Start New Analysis
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>

      <footer className="max-w-7xl mx-auto px-6 py-12 border-t border-white/5 mt-12">
        <div className="flex items-start gap-4 text-ink text-[11px] leading-relaxed max-w-4xl opacity-60">
          <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
          <p>{activeDisclaimer}</p>
        </div>
      </footer>
    </div>
  )
}
