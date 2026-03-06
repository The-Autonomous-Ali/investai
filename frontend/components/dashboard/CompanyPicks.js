import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { TrendingUp, TrendingDown, Zap, ChevronDown, ChevronUp, Star, AlertTriangle, BarChart2, Shield } from 'lucide-react'

const RISK_CONFIG = {
  low:    { label: 'Low Risk',    color: 'text-jade  bg-jade/10  border-jade/20' },
  medium: { label: 'Med Risk',   color: 'text-gold  bg-gold/10  border-gold/20' },
  high:   { label: 'High Risk',  color: 'text-ruby  bg-ruby/10  border-ruby/20' },
}

const TYPE_CONFIG = {
  established: { label: 'Established',  icon: Shield, color: 'text-jade' },
  emerging:    { label: 'Emerging Gem', icon: Zap,    color: 'text-gold' },
}

function CompanyCard({ company, isExpanded, onToggle }) {
  const risk    = RISK_CONFIG[company.risk_level] || RISK_CONFIG.medium
  const typeConf = TYPE_CONFIG[company.type]     || TYPE_CONFIG.established
  const TypeIcon = typeConf.icon

  return (
    <div
      className={`rounded-xl border transition-all cursor-pointer ${
        isExpanded
          ? 'border-gold/30 bg-surface-3'
          : 'border-white/8 bg-surface-2 hover:border-white/15'
      }`}
      onClick={onToggle}
    >
      {/* Header row */}
      <div className="p-4 flex items-start gap-4">
        {/* Symbol badge */}
        <div className="w-12 h-12 rounded-xl bg-surface-3 border border-white/8 flex flex-col items-center justify-center flex-shrink-0">
          <span className="text-gold font-mono font-bold text-xs leading-tight text-center px-1">
            {company.nse_symbol?.slice(0, 6)}
          </span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-white font-semibold">{company.name}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full border flex items-center gap-1 ${risk.color}`}>
              {risk.label}
            </span>
            {company.type === 'emerging' && (
              <span className="text-xs px-2 py-0.5 rounded-full border border-gold/30 bg-gold/10 text-gold flex items-center gap-1">
                <Zap size={10} /> Hidden Gem
              </span>
            )}
          </div>

          {/* Quick stats */}
          <div className="flex items-center gap-4 text-xs text-ink">
            <span>~{company.current_price_approx}</span>
            {company.upside_potential && (
              <span className="flex items-center gap-1 text-jade">
                <TrendingUp size={11} />
                {company.upside_potential} upside
              </span>
            )}
            {company.fundamentals?.dividend_yield > 0 && (
              <span>{company.fundamentals.dividend_yield}% div</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-xs ${typeConf.color} flex items-center gap-1`}>
            <TypeIcon size={12} />
            {typeConf.label}
          </span>
          {isExpanded ? <ChevronUp size={14} className="text-ink" /> : <ChevronDown size={14} className="text-ink" />}
        </div>
      </div>

      {/* Expanded detail */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-0 border-t border-white/5 mt-0 space-y-4">

              {/* Why chosen */}
              <div>
                <p className="text-xs text-ink font-semibold uppercase tracking-wide mb-2">Why We Chose This</p>
                <ul className="space-y-1.5">
                  {(company.why_chosen || []).map((reason, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-ink-light">
                      <span className="text-jade mt-0.5 flex-shrink-0">✓</span>
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Fundamentals grid */}
              {company.fundamentals && (
                <div>
                  <p className="text-xs text-ink font-semibold uppercase tracking-wide mb-2">Key Fundamentals</p>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(company.fundamentals).map(([key, val]) => (
                      <div key={key} className="bg-surface-2 rounded-lg px-3 py-2">
                        <div className="text-ink text-xs capitalize">{key.replace(/_/g, ' ')}</div>
                        <div className="text-white text-sm font-mono font-medium">{val}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Entry strategy */}
              <div className="bg-gold/5 border border-gold/15 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <BarChart2 size={12} className="text-gold" />
                  <span className="text-gold text-xs font-semibold">Entry Strategy</span>
                </div>
                <p className="text-ink-light text-xs">{company.entry_strategy}</p>
              </div>

              {/* Key risk */}
              <div className="bg-ruby/5 border border-ruby/15 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <AlertTriangle size={12} className="text-ruby" />
                  <span className="text-ruby text-xs font-semibold">Key Risk</span>
                </div>
                <p className="text-ink-light text-xs">{company.key_risk}</p>
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-ink">Best for: <span className="text-white">{company.best_for}</span></span>
                <span className="text-ink">Mode: <span className="text-gold">{company.investment_mode}</span></span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function SectorGroup({ sectorPick }) {
  const [expandedCompany, setExpandedCompany] = useState(null)
  const [showEtf, setShowEtf] = useState(false)

  const toggle = (name) => setExpandedCompany(prev => prev === name ? null : name)

  return (
    <div className="card p-5">
      {/* Sector header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <h3 className="font-display font-semibold text-white text-lg">{sectorPick.sector}</h3>
            <div className="px-2 py-0.5 rounded-full bg-jade/10 border border-jade/20">
              <span className="text-jade text-xs font-mono">{sectorPick.signal_fit_score}/10 fit</span>
            </div>
          </div>
          <p className="text-ink text-xs">{sectorPick.signal_fit_reason}</p>
        </div>
      </div>

      {/* Companies */}
      <div className="space-y-3 mb-4">
        {(sectorPick.companies || []).map(company => (
          <CompanyCard
            key={company.nse_symbol}
            company={company}
            isExpanded={expandedCompany === company.nse_symbol}
            onToggle={() => toggle(company.nse_symbol)}
          />
        ))}
      </div>

      {/* ETF alternative */}
      {sectorPick.etf_alternative && (
        <div>
          <button
            onClick={() => setShowEtf(v => !v)}
            className="flex items-center gap-2 text-xs text-ink hover:text-white transition-colors mb-2"
          >
            <Shield size={12} />
            Safer Alternative: ETF Option
            {showEtf ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          {showEtf && (
            <div className="bg-surface-3 border border-white/8 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-white text-sm font-medium">{sectorPick.etf_alternative.name}</span>
                <span className="text-gold font-mono text-xs">{sectorPick.etf_alternative.symbol}</span>
              </div>
              <p className="text-ink text-xs mb-1">{sectorPick.etf_alternative.why_chosen}</p>
              <div className="flex items-center gap-4 text-xs text-ink">
                <span>Expense ratio: <span className="text-white">{sectorPick.etf_alternative.expense_ratio}%</span></span>
                <span>Best for: <span className="text-white">{sectorPick.etf_alternative.best_for}</span></span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function CompanyPicks({ sectorPicks = [], constructionNote }) {
  if (!sectorPicks || sectorPicks.length === 0) return null

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="font-display font-bold text-xl text-white">Stock Picks by Sector</h2>
          <p className="text-ink text-sm">Based on current signal analysis — established leaders + emerging opportunities</p>
        </div>
        <div className="text-xs text-ink px-3 py-1.5 rounded-full bg-surface-3 border border-white/8">
          {sectorPicks.reduce((acc, s) => acc + (s.companies?.length || 0), 0)} companies analyzed
        </div>
      </div>

      <div className="space-y-5">
        {sectorPicks.map((sectorPick, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08 }}
          >
            <SectorGroup sectorPick={sectorPick} />
          </motion.div>
        ))}
      </div>

      {constructionNote && (
        <div className="mt-5 flex items-start gap-2 px-4 py-3 rounded-lg bg-surface-3 border border-white/8">
          <AlertTriangle size={14} className="text-gold flex-shrink-0 mt-0.5" />
          <p className="text-ink text-xs">{constructionNote}</p>
        </div>
      )}
    </div>
  )
}
