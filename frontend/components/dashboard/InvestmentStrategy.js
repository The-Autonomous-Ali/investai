import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  Target, Calendar, TrendingUp, TrendingDown, AlertTriangle,
  Clock, CheckCircle2, XCircle, ChevronDown, ChevronUp,
  DollarSign, BarChart2, Shield, Zap, ArrowRight
} from 'lucide-react'

function PhaseCard({ phase, totalAmount }) {
  const [open, setOpen] = useState(phase.phase === 1)
  const pct = Math.round((phase.amount / totalAmount) * 100)

  return (
    <div className={`rounded-xl border transition-all ${
      open ? 'border-gold/30 bg-surface-3' : 'border-white/8 bg-surface-2'
    }`}>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full p-4 flex items-center gap-4 text-left"
      >
        {/* Phase number */}
        <div className={`w-10 h-10 rounded-full flex-shrink-0 flex items-center justify-center font-display font-bold ${
          phase.phase === 1 ? 'bg-gold text-surface' : 'bg-surface-3 border border-white/10 text-ink'
        }`}>
          {phase.phase}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-white font-semibold text-sm">{phase.label}</span>
            {phase.phase === 1 && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-jade/10 border border-jade/20 text-jade">Act Now</span>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-ink">
            <span className="flex items-center gap-1"><Clock size={11} /> {phase.timing}</span>
            <span className="flex items-center gap-1 text-gold"><DollarSign size={11} /> ₹{phase.amount?.toLocaleString('en-IN')} ({pct}%)</span>
          </div>
        </div>

        {open ? <ChevronUp size={14} className="text-ink flex-shrink-0" /> : <ChevronDown size={14} className="text-ink flex-shrink-0" />}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-0 border-t border-white/5 space-y-3">
          <div className="space-y-2">
            {(phase.what_to_buy || []).map((item, i) => (
              <div key={i} className="flex items-start gap-3 bg-surface-2 rounded-lg p-3">
                <ArrowRight size={13} className="text-gold flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-white text-sm font-medium">{item.instrument}</span>
                    <span className="text-gold font-mono text-sm">₹{item.amount?.toLocaleString('en-IN')}</span>
                  </div>
                  <p className="text-ink text-xs mt-0.5">{item.reason}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 text-xs">
            <Zap size={12} className="text-gold" />
            <span className="text-ink">Trigger: <span className="text-white">{phase.trigger}</span></span>
          </div>
        </div>
      )}
    </div>
  )
}

function ExitTriggerCard({ trigger, type }) {
  const config = {
    emergency: { icon: AlertTriangle, color: 'text-ruby', bg: 'bg-ruby/5 border-ruby/15' },
    profit:    { icon: TrendingUp,    color: 'text-jade', bg: 'bg-jade/5 border-jade/15' },
    planned:   { icon: Calendar,      color: 'text-gold', bg: 'bg-gold/5 border-gold/15' },
  }[type] || { icon: AlertTriangle, color: 'text-ink', bg: 'bg-surface-3 border-white/8' }

  const Icon = config.icon

  return (
    <div className={`rounded-lg border p-3 ${config.bg}`}>
      <div className="flex items-start gap-2">
        <Icon size={13} className={`${config.color} flex-shrink-0 mt-0.5`} />
        <div>
          <p className="text-white text-xs font-semibold mb-0.5">{trigger.trigger || trigger.condition}</p>
          <p className="text-ink text-xs">{trigger.action}</p>
          {trigger.reason && <p className="text-ink/70 text-xs mt-0.5 italic">{trigger.reason}</p>}
        </div>
      </div>
    </div>
  )
}

export default function InvestmentStrategy({ strategy, amount }) {
  const [activeTab, setActiveTab] = useState('deployment')

  if (!strategy || !strategy.strategy_name) return null

  const tabs = [
    { id: 'deployment', label: 'Deployment Plan' },
    { id: 'sip',        label: 'SIP vs Lumpsum' },
    { id: 'exits',      label: 'Exit Strategy' },
    { id: 'guardrails', label: 'Guardrails' },
  ]

  const outcome = strategy.expected_outcome

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-display font-bold text-xl text-white mb-1">
              {strategy.strategy_name}
            </h2>
            <p className="text-ink text-sm leading-relaxed max-w-2xl">
              {typeof strategy.strategy_rationale === 'string'
                ? strategy.strategy_rationale.slice(0, 300) + '...'
                : 'Complete investment playbook built by the Investment Manager agent.'}
            </p>
          </div>

          {/* Expected return badge */}
          {outcome && (
            <div className="card-gold p-4 text-center flex-shrink-0 min-w-36">
              <div className="text-ink text-xs mb-1">Base Case Return</div>
              <div className="font-display font-bold text-2xl text-gold">{outcome.base_case_return}</div>
              <div className="text-ink text-xs mt-1">vs FD: {outcome.vs_fixed_deposit?.split('—')[0]?.trim()}</div>
            </div>
          )}
        </div>

        {/* Outcome bar */}
        {outcome && (
          <div className="mt-4 grid grid-cols-3 gap-3">
            {[
              { label: 'Worst Case',  value: outcome.worst_case_return,  color: 'text-ruby' },
              { label: 'Base Case',   value: outcome.base_case_return,   color: 'text-gold' },
              { label: 'Best Case',   value: outcome.best_case_return,   color: 'text-jade' },
            ].map((item, i) => (
              <div key={i} className="bg-surface-3 rounded-lg p-3 text-center">
                <div className="text-ink text-xs mb-1">{item.label}</div>
                <div className={`font-mono font-bold text-lg ${item.color}`}>{item.value}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 bg-surface-3 p-1 rounded-lg">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 py-2 px-3 rounded-md text-xs font-medium transition-all ${
              activeTab === tab.id
                ? 'bg-gold text-surface font-semibold'
                : 'text-ink hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <motion.div key={activeTab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>

        {/* Deployment Plan */}
        {activeTab === 'deployment' && strategy.deployment_plan && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 mb-3">
              <div className={`px-3 py-1 rounded-full text-xs border ${
                strategy.deployment_plan.approach === 'phased'
                  ? 'bg-gold/10 border-gold/20 text-gold'
                  : 'bg-jade/10 border-jade/20 text-jade'
              }`}>
                {strategy.deployment_plan.approach?.toUpperCase()} DEPLOYMENT
              </div>
              <p className="text-ink text-xs">{strategy.deployment_plan.reasoning}</p>
            </div>

            {(strategy.deployment_plan.phases || []).map(phase => (
              <PhaseCard key={phase.phase} phase={phase} totalAmount={amount} />
            ))}
          </div>
        )}

        {/* SIP vs Lumpsum */}
        {activeTab === 'sip' && strategy.sip_vs_lumpsum && (
          <div className="space-y-4">
            <div className="card-gold p-4">
              <div className="flex items-center gap-2 mb-2">
                <Target size={16} className="text-gold" />
                <span className="text-white font-semibold">Recommendation: {strategy.sip_vs_lumpsum.recommendation?.toUpperCase().replace('_', ' ')}</span>
              </div>
              <p className="text-ink-light text-sm">{strategy.sip_vs_lumpsum.reasoning}</p>
            </div>

            {strategy.sip_vs_lumpsum.if_sip_preferred && (
              <div className="card p-4">
                <h4 className="text-white text-sm font-semibold mb-3">If You Prefer SIP</h4>
                <div className="flex items-center gap-3 mb-4">
                  <div className="text-center">
                    <div className="font-display font-bold text-2xl text-gold">
                      ₹{strategy.sip_vs_lumpsum.if_sip_preferred.monthly_amount?.toLocaleString('en-IN')}
                    </div>
                    <div className="text-ink text-xs">per month</div>
                  </div>
                  <div className="text-ink">×</div>
                  <div className="text-center">
                    <div className="font-display font-bold text-2xl text-white">
                      {strategy.sip_vs_lumpsum.if_sip_preferred.duration_months}
                    </div>
                    <div className="text-ink text-xs">months</div>
                  </div>
                </div>
                <div className="space-y-2">
                  {(strategy.sip_vs_lumpsum.if_sip_preferred.instruments || []).map((inst, i) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <span className="text-ink-light">{inst.name}</span>
                      <span className="text-gold font-mono">₹{inst.monthly?.toLocaleString('en-IN')}/mo</span>
                    </div>
                  ))}
                </div>
                {strategy.sip_vs_lumpsum.if_sip_preferred.note && (
                  <p className="text-ink text-xs mt-3 border-t border-white/5 pt-3">
                    💡 {strategy.sip_vs_lumpsum.if_sip_preferred.note}
                  </p>
                )}
              </div>
            )}

            {/* Rebalancing schedule */}
            {strategy.rebalancing_schedule && (
              <div>
                <h4 className="text-white text-sm font-semibold mb-3">Rebalancing Schedule</h4>
                <div className="space-y-3">
                  {strategy.rebalancing_schedule.map((rb, i) => (
                    <div key={i} className="card p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Calendar size={13} className="text-gold" />
                        <span className="text-gold text-xs font-semibold">At {rb.at}</span>
                        <span className="text-white text-xs">— {rb.action}</span>
                      </div>
                      {rb.what_to_check && (
                        <div className="flex flex-wrap gap-1">
                          {rb.what_to_check.map((check, j) => (
                            <span key={j} className="text-xs px-2 py-0.5 rounded-full bg-surface-3 text-ink">{check}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Exit Strategy */}
        {activeTab === 'exits' && strategy.exit_strategy && (
          <div className="space-y-5">
            {/* Planned exit */}
            {strategy.exit_strategy.planned_exit && (
              <div>
                <h4 className="text-white text-sm font-semibold mb-3 flex items-center gap-2">
                  <Calendar size={14} className="text-gold" /> Planned Exit
                </h4>
                <div className="card-gold p-4">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="text-center">
                      <div className="text-gold font-mono text-sm">{strategy.exit_strategy.planned_exit.date}</div>
                      <div className="text-ink text-xs">target date</div>
                    </div>
                  </div>
                  <p className="text-ink-light text-sm mb-2">{strategy.exit_strategy.planned_exit.method}</p>
                  <p className="text-ink text-xs border-t border-white/5 pt-2">
                    📋 {strategy.exit_strategy.planned_exit.tax_note}
                  </p>
                </div>
              </div>
            )}

            {/* Emergency exits */}
            {strategy.exit_strategy.emergency_exits?.length > 0 && (
              <div>
                <h4 className="text-white text-sm font-semibold mb-3 flex items-center gap-2">
                  <AlertTriangle size={14} className="text-ruby" /> Emergency Exit Triggers
                </h4>
                <div className="space-y-2">
                  {strategy.exit_strategy.emergency_exits.map((ex, i) => (
                    <ExitTriggerCard key={i} trigger={ex} type="emergency" />
                  ))}
                </div>
              </div>
            )}

            {/* Profit booking */}
            {strategy.exit_strategy.profit_booking?.length > 0 && (
              <div>
                <h4 className="text-white text-sm font-semibold mb-3 flex items-center gap-2">
                  <TrendingUp size={14} className="text-jade" /> Profit Booking Rules
                </h4>
                <div className="space-y-2">
                  {strategy.exit_strategy.profit_booking.map((pb, i) => (
                    <ExitTriggerCard key={i} trigger={pb} type="profit" />
                  ))}
                </div>
              </div>
            )}

            {/* Weekly/monthly monitoring */}
            {strategy.monthly_monitoring && (
              <div>
                <h4 className="text-white text-sm font-semibold mb-3 flex items-center gap-2">
                  <BarChart2 size={14} className="text-gold" /> What to Monitor
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  {strategy.monthly_monitoring.weekly_checks && (
                    <div className="card p-3">
                      <div className="text-gold text-xs font-semibold mb-2">Weekly</div>
                      <ul className="space-y-1">
                        {strategy.monthly_monitoring.weekly_checks.map((check, i) => (
                          <li key={i} className="text-ink text-xs flex items-center gap-1.5">
                            <span className="w-1 h-1 rounded-full bg-gold flex-shrink-0" />
                            {check}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {strategy.monthly_monitoring.monthly_checks && (
                    <div className="card p-3">
                      <div className="text-gold text-xs font-semibold mb-2">Monthly</div>
                      <ul className="space-y-1">
                        {strategy.monthly_monitoring.monthly_checks.map((check, i) => (
                          <li key={i} className="text-ink text-xs flex items-center gap-1.5">
                            <span className="w-1 h-1 rounded-full bg-gold flex-shrink-0" />
                            {check}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                {strategy.monthly_monitoring.dont_check_daily && (
                  <div className="mt-3 flex items-center gap-2 text-xs text-ink">
                    <XCircle size={12} className="text-ruby" />
                    <span>{strategy.monthly_monitoring.dont_check_daily}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Behavioral Guardrails */}
        {activeTab === 'guardrails' && (
          <div className="space-y-4">
            <p className="text-ink text-sm">
              Rules to protect you from your own emotions. The Investment Manager's most important advice is not what to buy — it's how to behave.
            </p>
            <div className="space-y-3">
              {(strategy.behavioral_guardrails || []).map((rule, i) => (
                <div key={i} className="flex items-start gap-3 bg-surface-3 border border-white/8 rounded-lg p-4">
                  <Shield size={16} className="text-gold flex-shrink-0 mt-0.5" />
                  <p className="text-ink-light text-sm">{rule}</p>
                </div>
              ))}
            </div>
            {strategy.manager_note && (
              <div className="bg-gold/5 border border-gold/20 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-gold font-semibold text-sm">Manager's Note</span>
                </div>
                <p className="text-ink-light text-sm italic">{strategy.manager_note}</p>
              </div>
            )}
          </div>
        )}
      </motion.div>
    </div>
  )
}
