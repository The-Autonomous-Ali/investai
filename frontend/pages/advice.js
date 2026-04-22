import Head from 'next/head'
import { useState } from 'react'
import { motion } from 'framer-motion'
import Link from 'next/link'
import {
  Brain,
  ArrowLeft,
  ChevronRight,
  AlertTriangle,
  Loader2,
  Send,
} from 'lucide-react'
import CompanyPicks from '../components/dashboard/CompanyPicks'
import InvestmentStrategy from '../components/dashboard/InvestmentStrategy'
import { getAdvice } from '../lib/api'

const HORIZONS = ['3 months', '6 months', '1 year', '2 years', '5 years']

const TABS = [
  { id: 'strategy',   label: 'Signal Chain' },
  { id: 'companies',  label: 'Stock Picks' },
  { id: 'playbook',   label: 'Investment Playbook' },
]

function mapRecommendation(rec) {
  if (!rec) return null
  const analysis = rec.analysis || {}
  return {
    confidence_score: typeof rec.confidence === 'number' ? rec.confidence : null,
    narrative: analysis.narrative || rec.thesis || rec.summary || '',
    what_could_go_wrong: rec.key_risks || analysis.what_could_go_wrong || [],
    reasoning_chain: analysis.reasoning_chain || [],
    company_picks: analysis.company_picks || [],
    portfolio_construction_note: analysis.portfolio_construction_note || '',
    investment_strategy: analysis.investment_strategy || null,
    action: rec.action,
    action_strength: rec.action_strength,
    policy_version: rec.policy_version,
    review_date: rec.review_date,
    known_limits: rec.known_limits || [],
  }
}

function friendlyError(err) {
  const status = err?.response?.status
  const detail = err?.response?.data?.detail
  if (status === 401) return 'You need to sign in before requesting analysis.'
  if (status === 403) {
    const message = typeof detail === 'object' ? detail?.message : detail
    return message || 'Your plan quota has been used for this billing period.'
  }
  if (status === 429) {
    const retry = typeof detail === 'object' ? detail?.retry_after_seconds : null
    return retry
      ? `Too many requests. Please wait ~${retry}s and try again.`
      : 'Too many requests. Please slow down and try again in a minute.'
  }
  if (status >= 500) {
    return 'The analysis pipeline is temporarily unavailable. This usually means an LLM provider is rate-limiting or down. Try again in a few minutes.'
  }
  return err?.message || 'Something went wrong while running the analysis.'
}

export default function AdvicePage() {
  const [activeTab, setActiveTab] = useState('strategy')

  const [query, setQuery] = useState('')
  const [amount, setAmount] = useState(100000)
  const [horizon, setHorizon] = useState('1 year')

  const [advice, setAdvice] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e?.preventDefault()
    if (!query.trim() || loading) return
    setLoading(true)
    setError(null)
    try {
      const res = await getAdvice({
        query: query.trim(),
        amount: Number(amount) || 0,
        horizon,
        country: 'India',
      })
      if (!res?.success || !res?.recommendation) {
        throw new Error(res?.error || 'The analysis pipeline returned no recommendation.')
      }
      setAdvice(mapRecommendation(res.recommendation))
      setActiveTab('strategy')
    } catch (err) {
      setError(friendlyError(err))
      setAdvice(null)
    } finally {
      setLoading(false)
    }
  }

  const hasAnalysis = !loading && !error && advice

  return (
    <>
      <Head><title>Investment Analysis — InvestAI</title></Head>
      <div className="min-h-screen bg-surface">

        {/* Nav */}
        <div className="sticky top-0 z-50 border-b border-white/5 bg-surface/90 backdrop-blur-md">
          <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link href="/dashboard" className="text-ink hover:text-white flex items-center gap-1 text-sm">
                <ArrowLeft size={14} /> Dashboard
              </Link>
              <span className="text-ink/30">/</span>
              <span className="text-white font-medium text-sm">Investment Analysis</span>
            </div>
            {hasAnalysis && advice.confidence_score != null && (
              <div className="flex items-center gap-2 text-xs text-ink">
                <Brain size={13} className="text-gold" />
                <span>live pipeline</span>
                <span className="px-2 py-0.5 rounded-full bg-jade/10 text-jade border border-jade/20">
                  {Math.round(advice.confidence_score * 100)}% confidence
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="max-w-6xl mx-auto px-6 py-8">

          {/* Query form */}
          <motion.form
            onSubmit={handleSubmit}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="card p-5 mb-8"
          >
            <label className="block text-ink text-xs font-mono mb-2">YOUR QUESTION</label>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={2}
              maxLength={500}
              placeholder="e.g., Where should I invest ₹1,00,000 for 1 year given current oil and INR signals?"
              className="w-full bg-surface-2 border border-white/5 rounded-lg px-3 py-2 text-white text-sm focus:border-gold/40 focus:outline-none resize-none"
              disabled={loading}
            />
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <div>
                <label className="block text-ink text-xs font-mono mb-1">AMOUNT (₹)</label>
                <input
                  type="number"
                  min={0}
                  max={100000000}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="bg-surface-2 border border-white/5 rounded-lg px-3 py-2 text-white text-sm w-36 focus:border-gold/40 focus:outline-none"
                  disabled={loading}
                />
              </div>
              <div>
                <label className="block text-ink text-xs font-mono mb-1">HORIZON</label>
                <select
                  value={horizon}
                  onChange={(e) => setHorizon(e.target.value)}
                  className="bg-surface-2 border border-white/5 rounded-lg px-3 py-2 text-white text-sm focus:border-gold/40 focus:outline-none"
                  disabled={loading}
                >
                  {HORIZONS.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
              <button
                type="submit"
                disabled={loading || !query.trim()}
                className="ml-auto flex items-center gap-2 bg-gold text-surface font-semibold px-5 py-2 rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Running…
                  </>
                ) : (
                  <>
                    <Send size={14} />
                    {advice ? 'Re-run Analysis' : 'Run Analysis'}
                  </>
                )}
              </button>
            </div>
            {loading && (
              <div className="mt-3 text-xs text-ink">
                Running the full agent pipeline. This usually takes 20–40 seconds.
              </div>
            )}
          </motion.form>

          {/* Error */}
          {error && (
            <div className="card border-ruby/30 bg-ruby/5 p-4 mb-8 flex items-start gap-3">
              <AlertTriangle size={16} className="text-ruby flex-shrink-0 mt-0.5" />
              <div className="text-ruby text-sm">{error}</div>
            </div>
          )}

          {/* Empty state */}
          {!loading && !error && !advice && (
            <div className="card p-10 text-center">
              <Brain size={28} className="text-gold mx-auto mb-3" />
              <div className="text-white font-medium mb-1">No analysis yet</div>
              <div className="text-ink text-sm">
                Ask a question above to run the live multi-agent pipeline.
                Nothing on this page is precomputed — each answer is generated
                fresh from your current signal graph.
              </div>
            </div>
          )}

          {/* Analysis view */}
          {hasAnalysis && (
            <>
              {/* Summary header */}
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
                <div className="card-gold p-6">
                  <div className="flex items-start justify-between gap-6">
                    <div className="flex-1">
                      <div className="text-gold text-xs font-mono mb-2">
                        ANALYSIS COMPLETE · ₹{Number(amount).toLocaleString('en-IN')} · {horizon.toUpperCase()} HORIZON
                      </div>
                      {advice.narrative ? (
                        <p className="text-ink-light leading-relaxed whitespace-pre-line">{advice.narrative}</p>
                      ) : (
                        <p className="text-ink text-sm italic">The pipeline returned a recommendation without a narrative summary.</p>
                      )}
                      {advice.action && (
                        <div className="mt-3 text-xs text-ink">
                          Policy action: <span className="text-white font-medium uppercase">{advice.action}</span>
                          {advice.action_strength && <> ({advice.action_strength})</>}
                        </div>
                      )}
                    </div>
                    {advice.what_could_go_wrong?.length > 0 && (
                      <div className="flex-shrink-0 space-y-2">
                        {advice.what_could_go_wrong.slice(0, 2).map((risk, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs text-ruby max-w-xs">
                            <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
                            {risk}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Signal chain preview */}
                  {advice.reasoning_chain.length > 0 && (
                    <div className="mt-4 flex items-center gap-2 overflow-x-auto pb-1">
                      {advice.reasoning_chain.slice(0, 4).map((step, i) => (
                        <div key={i} className="flex items-center gap-2 flex-shrink-0">
                          <div className="text-xs bg-surface-3 border border-white/8 rounded-lg px-2 py-1 max-w-40">
                            <div className="text-gold text-xs">→ {step.effect}</div>
                            {typeof step.confidence === 'number' && (
                              <div className="text-ink text-xs">{Math.round(step.confidence * 100)}% conf</div>
                            )}
                          </div>
                          {i < Math.min(3, advice.reasoning_chain.length - 1) && (
                            <ChevronRight size={12} className="text-ink" />
                          )}
                        </div>
                      ))}
                      {advice.reasoning_chain.length > 4 && (
                        <span className="text-ink text-xs flex-shrink-0">+{advice.reasoning_chain.length - 4} more steps</span>
                      )}
                    </div>
                  )}
                </div>
              </motion.div>

              {/* Known limits */}
              {advice.known_limits.length > 0 && (
                <div className="card border-gold/20 bg-gold/5 p-4 mb-8 text-xs text-ink-light space-y-1">
                  {advice.known_limits.map((limit, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="text-gold">•</span>
                      {limit}
                    </div>
                  ))}
                </div>
              )}

              {/* Tab nav */}
              <div className="flex gap-1 mb-8 bg-surface-2 border border-white/5 p-1 rounded-xl w-fit">
                {TABS.map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`px-6 py-2.5 rounded-lg text-sm font-medium transition-all ${
                      activeTab === tab.id
                        ? 'bg-gold text-surface font-semibold'
                        : 'text-ink hover:text-white'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <motion.div key={activeTab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>

                {/* Signal Chain tab */}
                {activeTab === 'strategy' && (
                  <div className="space-y-4">
                    <h2 className="font-display font-bold text-xl text-white mb-5">How We Got Here — The Signal Chain</h2>
                    {advice.reasoning_chain.length === 0 ? (
                      <div className="text-ink text-sm italic">
                        The pipeline did not return a step-by-step signal chain for this query.
                      </div>
                    ) : (
                      advice.reasoning_chain.map((step, i) => (
                        <div key={i} className="flex items-start gap-4">
                          <div className="w-8 h-8 rounded-full bg-gold/10 border border-gold/20 flex items-center justify-center text-gold text-xs font-bold flex-shrink-0">
                            {step.step ?? i + 1}
                          </div>
                          <div className="card p-4 flex-1">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                {step.cause && <div className="text-ink text-xs mb-1">Cause: <span className="text-ink-light">{step.cause}</span></div>}
                                {step.effect && <div className="text-white font-medium">→ {step.effect}</div>}
                              </div>
                              {typeof step.confidence === 'number' && (
                                <div className="text-right flex-shrink-0">
                                  <div className="text-gold text-sm font-mono">{Math.round(step.confidence * 100)}%</div>
                                  <div className="text-ink text-xs">confidence</div>
                                </div>
                              )}
                            </div>
                            {typeof step.confidence === 'number' && (
                              <div className="mt-2 h-1 bg-surface-3 rounded-full overflow-hidden">
                                <div className="h-full bg-gradient-to-r from-gold to-jade rounded-full" style={{ width: `${step.confidence * 100}%` }} />
                              </div>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {/* Company Picks tab */}
                {activeTab === 'companies' && (
                  advice.company_picks?.length > 0 ? (
                    <CompanyPicks
                      sectorPicks={advice.company_picks}
                      constructionNote={advice.portfolio_construction_note}
                    />
                  ) : (
                    <div className="card p-6 text-ink text-sm italic">
                      The pipeline did not return company-level picks for this query. The analysis above is based on sector and signal evidence only.
                    </div>
                  )
                )}

                {/* Investment Playbook tab */}
                {activeTab === 'playbook' && (
                  advice.investment_strategy ? (
                    <InvestmentStrategy
                      strategy={advice.investment_strategy}
                      amount={Number(amount) || 0}
                    />
                  ) : (
                    <div className="card p-6 text-ink text-sm italic">
                      The pipeline did not return a structured playbook for this query.
                    </div>
                  )
                )}
              </motion.div>

              {/* Footer meta */}
              {(advice.policy_version || advice.review_date) && (
                <div className="mt-10 text-xs text-ink space-x-4">
                  {advice.policy_version && <span>policy: {advice.policy_version}</span>}
                  {advice.review_date && <span>next review: {advice.review_date}</span>}
                </div>
              )}
            </>
          )}

          {/* Disclaimer */}
          <div className="mt-12 flex items-start gap-2 text-xs text-ink border-t border-white/5 pt-6">
            <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
            <p>
              This analysis is generated by AI agents for educational purposes only. InvestAI is not a SEBI-registered
              investment advisor. All recommendations should be verified independently. Past signal performance does not
              guarantee future results. Please consult a qualified financial advisor before investing.
            </p>
          </div>
        </div>
      </div>
    </>
  )
}
