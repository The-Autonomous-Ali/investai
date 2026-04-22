import Head from 'next/head'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Filter, TrendingUp, Activity, Globe, AlertTriangle, Clock, ChevronDown, ChevronUp } from 'lucide-react'
import Link from 'next/link'
import { useSignals } from '../hooks/useSignals'

// Helper: format relative time from ISO date string
function timeAgo(isoDate) {
  if (!isoDate) return ''
  const diff = Date.now() - new Date(isoDate).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs} hrs ago`
  return `${Math.floor(hrs / 24)}d ago`
}

const URGENCY_CONFIG = {
  breaking:   { label: 'BREAKING',    color: 'bg-ruby/10 text-ruby border border-ruby/20' },
  developing: { label: 'DEVELOPING',  color: 'bg-gold/10 text-gold border border-gold/20' },
  long_term:  { label: 'LONG TERM',   color: 'bg-ink/10 text-ink border border-ink/20' },
}

const STAGE_CONFIG = {
  WATCH:         { color: 'text-ink',       bg: 'bg-ink/10' },
  DEVELOPING:    { color: 'text-gold',      bg: 'bg-gold/10' },
  ACTIVE:        { color: 'text-jade',      bg: 'bg-jade/10' },
  ESCALATING:    { color: 'text-ruby',      bg: 'bg-ruby/10' },
  DE_ESCALATING: { color: 'text-blue-400',  bg: 'bg-blue-400/10' },
  RESOLVED:      { color: 'text-ink',       bg: 'bg-ink/10' },
}

function SignalDetail({ signal, onClose }) {
  return (
    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="card-gold p-6 sticky top-24">
      <div className="flex items-start justify-between gap-3 mb-4">
        <h3 className="font-display font-semibold text-white text-lg leading-tight">{signal.title}</h3>
        <button onClick={onClose} className="text-ink hover:text-white flex-shrink-0">✕</button>
      </div>

      <div className="flex items-center gap-2 mb-6">
        <span className={`text-xs px-2 py-0.5 rounded-full ${URGENCY_CONFIG[signal.urgency]?.color}`}>
          {URGENCY_CONFIG[signal.urgency]?.label}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full ${STAGE_CONFIG[signal.stage]?.bg} ${STAGE_CONFIG[signal.stage]?.color}`}>
          {signal.stage}
        </span>
        <span className="text-ink text-xs">{signal.source} · Tier {signal.sourceTier}</span>
      </div>

      <div className="space-y-5">
        {/* Confidence */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-ink">Signal Confidence</span>
            <span className="text-gold">{(signal.confidence * 100).toFixed(0)}%</span>
          </div>
          <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-gold to-jade rounded-full" style={{ width: `${signal.confidence * 100}%` }} />
          </div>
          <p className="text-ink text-xs mt-1">Corroborated by: {signal.corroborated_by.join(', ')}</p>
        </div>

        {/* Chain effects */}
        <div>
          <h4 className="text-white text-sm font-semibold mb-3">Impact Chain</h4>
          <div className="space-y-2">
            {signal.chain_effects.map((effect, i) => (
              <div key={i} className="flex items-start gap-2">
                <div className="w-4 h-4 rounded-full bg-gold/20 text-gold text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                  {i + 1}
                </div>
                <span className="text-ink-light text-xs">{effect}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Sector impacts */}
        <div>
          <h4 className="text-white text-sm font-semibold mb-3">Sector Impacts</h4>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(signal.sectors).map(([sector, sentiment]) => (
              <div key={sector} className={`px-3 py-2 rounded-lg text-xs flex items-center justify-between ${
                sentiment === 'positive' ? 'bg-jade/10 border border-jade/20' :
                sentiment === 'negative' ? 'bg-ruby/10 border border-ruby/20' :
                'bg-ink/10 border border-ink/20'
              }`}>
                <span className="text-white">{sector}</span>
                <span className={sentiment === 'positive' ? 'text-jade' : sentiment === 'negative' ? 'text-ruby' : 'text-ink'}>
                  {sentiment === 'positive' ? '↑' : sentiment === 'negative' ? '↓' : '→'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Predictions */}
        <div>
          <h4 className="text-white text-sm font-semibold mb-3">Temporal Forecast</h4>
          <div className="space-y-2">
            <div className="bg-surface-3 rounded-lg p-3">
              <div className="text-gold text-xs font-mono mb-1">TOMORROW (85% confidence)</div>
              <p className="text-ink-light text-xs">{signal.tomorrow_prediction}</p>
            </div>
            <div className="bg-surface-3 rounded-lg p-3">
              <div className="text-gold/70 text-xs font-mono mb-1">THIS WEEK (58% confidence)</div>
              <p className="text-ink-light text-xs">{signal.week_prediction}</p>
            </div>
          </div>
          <p className="text-ink text-xs mt-2 italic">Confidence decays further into future. Updated daily at 6am.</p>
        </div>

        <button className="w-full btn-gold py-3 rounded-lg text-sm">
          Build portfolio plan for this signal →
        </button>
      </div>
    </motion.div>
  )
}

export default function SignalsPage() {
  const { signals: SIGNALS, loading, isLive, degradedReason } = useSignals()
  const [selected, setSelected]   = useState(null)
  const [filter, setFilter]       = useState('all')
  const [expanded, setExpanded]   = useState({})

  const filters = [
    { id: 'all',          label: 'All Signals' },
    { id: 'breaking',     label: 'Breaking' },
    { id: 'geopolitical', label: 'Geopolitical' },
    { id: 'monetary',     label: 'Monetary' },
    { id: 'fiscal',       label: 'Fiscal' },
  ]

  // Normalize field names (API uses snake_case, mock used camelCase)
  const normalizedSignals = SIGNALS.map(s => ({
    ...s,
    sourceTier: s.source_tier ?? s.sourceTier,
    importance: s.importance_score ?? s.importance,
    type: s.signal_type ?? s.type,
    sectors: s.sectors_affected ?? s.sectors ?? {},
    detected: s.detected_at ? timeAgo(s.detected_at) : (s.detected || ''),
    chain_effects: s.chain_effects || [],
    corroborated_by: s.corroborated_by || [],
    confidence: s.confidence ?? 0,
    stage: (s.stage || 'WATCH').toUpperCase(),
    urgency: s.urgency || 'developing',
  }))

  const filtered = normalizedSignals.filter(s =>
    filter === 'all' || s.urgency === filter || s.type === filter
  )

  return (
    <>
      <Head><title>Signal Tracker — InvestAI</title></Head>
      <div className="min-h-screen bg-surface">
        {/* Top nav */}
        <div className="sticky top-0 z-50 border-b border-white/5 bg-surface/90 backdrop-blur-md">
          <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/dashboard" className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
                  <TrendingUp size={14} className="text-surface" />
                </div>
                <span className="font-display font-bold text-white">InvestAI</span>
              </Link>
              <span className="text-ink/50">/</span>
              <span className="text-white font-medium">Signal Tracker</span>
            </div>
            <div className="flex items-center gap-2">
              <Activity size={14} className={isLive ? "text-jade" : "text-gold"} />
              <span className={`text-xs font-mono ${isLive ? "text-jade" : "text-gold"}`}>
                {isLive ? "LIVE" : "DEMO"}
              </span>
              <span className="text-ink text-xs">
                {isLive ? "· Real-time signals" : "· Connect backend for live data"}
              </span>
            </div>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 py-8">
          {!isLive && degradedReason && (
            <div className="mb-6 rounded-2xl border border-gold/20 bg-gold/10 px-4 py-3 text-sm text-gold">
              {degradedReason}
            </div>
          )}

          {/* Filters */}
          <div className="flex items-center gap-2 mb-8">
            <Filter size={14} className="text-ink" />
            {filters.map(f => (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                className={`px-4 py-2 rounded-lg text-sm transition-all ${
                  filter === f.id
                    ? 'bg-gold/10 text-gold border border-gold/20'
                    : 'text-ink hover:text-white hover:bg-white/5 border border-transparent'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className={`grid gap-8 ${selected ? 'grid-cols-5' : 'grid-cols-1'}`}>
            {/* Signal list */}
            <div className={selected ? 'col-span-3' : 'col-span-1'}>
              {loading ? (
                <div className="card p-6 text-sm text-ink">Loading signals...</div>
              ) : filtered.length === 0 ? (
                <div className="card p-6 text-sm text-ink">
                  No live signals are available for the current filter.
                </div>
              ) : (
                <div className="space-y-4">
                {filtered.map((signal, i) => {
                  const urgency = URGENCY_CONFIG[signal.urgency]
                  const stage   = STAGE_CONFIG[signal.stage]
                  const isOpen  = expanded[signal.id]

                  return (
                    <motion.div
                      key={signal.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.05 }}
                      className={`card p-5 cursor-pointer hover:border-white/15 transition-all ${
                        selected?.id === signal.id ? 'border-gold/30' : ''
                      }`}
                      onClick={() => setSelected(selected?.id === signal.id ? null : signal)}
                    >
                      <div className="flex items-start gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-2">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${urgency?.color}`}>{urgency?.label}</span>
                            <span className={`text-xs px-2 py-0.5 rounded-full ${stage?.bg} ${stage?.color}`}>{signal.stage}</span>
                            <span className="text-ink text-xs">{signal.source}</span>
                            <span className="text-ink text-xs">· {signal.detected}</span>
                          </div>
                          <h3 className="text-white font-medium mb-2 leading-snug">{signal.title}</h3>
                          <div className="flex flex-wrap gap-1 mb-3">
                            {Object.entries(signal.sectors).slice(0, 4).map(([sector, sentiment]) => (
                              <span key={sector} className={`text-xs px-2 py-0.5 rounded-full ${
                                sentiment === 'positive' ? 'bg-jade/10 text-jade' :
                                sentiment === 'negative' ? 'bg-ruby/10 text-ruby' :
                                'bg-ink/10 text-ink'
                              }`}>
                                {sector}
                              </span>
                            ))}
                          </div>
                          {isOpen && (
                            <div className="mt-3 pt-3 border-t border-white/5">
                              <p className="text-ink text-xs mb-2">Impact chain:</p>
                              {signal.chain_effects.map((e, j) => (
                                <div key={j} className="flex items-center gap-2 text-xs text-ink-light mb-1">
                                  <span className="text-gold">→</span> {e}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="flex flex-col items-end gap-3 flex-shrink-0">
                          <div className="text-center">
                            <div className="font-mono text-xl font-bold text-gold">{signal.importance}</div>
                            <div className="text-ink text-xs">score</div>
                          </div>
                          <button
                            onClick={e => { e.stopPropagation(); setExpanded(prev => ({...prev, [signal.id]: !prev[signal.id]})) }}
                            className="text-ink hover:text-white p-1"
                          >
                            {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )
                })}
                </div>
              )}
            </div>

            {/* Signal detail panel */}
            {selected && (
              <div className="col-span-2">
                <SignalDetail signal={selected} onClose={() => setSelected(null)} />
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
