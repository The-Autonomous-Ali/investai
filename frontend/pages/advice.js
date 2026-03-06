import Head from 'next/head'
import { useState } from 'react'
import { motion } from 'framer-motion'
import Link from 'next/link'
import { TrendingUp, Brain, ArrowLeft, RefreshCw, ChevronRight, AlertTriangle, CheckCircle2, Clock } from 'lucide-react'
import CompanyPicks from '../components/dashboard/CompanyPicks'
import InvestmentStrategy from '../components/dashboard/InvestmentStrategy'

// ── Mock full advice response ──────────────────────────────────────────────
const MOCK_ADVICE = {
  narrative: `Based on current signals — Brent crude approaching $96 driven by Middle East tensions, RBI's hawkish stance, and USD strengthening — the system has identified a clear medium-term opportunity set for your ₹1,00,000 over 12 months.

The primary thesis: India imports ~85% of its oil, creating direct pressure on the current account deficit and INR. This makes oil producers the clearest beneficiaries. Simultaneously, INR weakness boosts IT sector USD revenues in rupee terms — making IT a natural hedge within the same portfolio.

Gold serves as the inflation hedge and portfolio anchor during geopolitical uncertainty. The liquid fund buffer allows opportunistic deployment if markets correct.`,

  reasoning_chain: [
    { step: 1, cause: 'Iran-Israel conflict escalating', effect: 'Strait of Hormuz risk rises', confidence: 0.72 },
    { step: 2, cause: 'Hormuz risk + OPEC supply tightness', effect: 'Brent crude spikes to $96', confidence: 0.84 },
    { step: 3, cause: 'India imports 85% of oil', effect: 'Current account deficit widens', confidence: 0.91 },
    { step: 4, cause: 'CAD widening + US Fed hawkish', effect: 'INR depreciates toward 84.5', confidence: 0.78 },
    { step: 5, cause: 'INR depreciation', effect: 'IT sector gets USD revenue boost in INR terms', confidence: 0.82 },
    { step: 6, cause: 'Global uncertainty + inflation', effect: 'Gold safe-haven demand rises', confidence: 0.75 },
  ],

  company_picks: [
    {
      sector: 'Oil & Gas',
      signal_fit_score: 9.2,
      signal_fit_reason: 'Direct beneficiary of oil price spike. Every $10 rise in Brent adds ~₹2000 crore to ONGC\'s EBITDA.',
      companies: [
        {
          name: 'ONGC', nse_symbol: 'ONGC', type: 'established', category: 'large_cap',
          why_chosen: [
            "India's largest oil producer — direct oil price beneficiary",
            'Every $1 rise in Brent = ~₹400 crore additional profit',
            'Government backing reduces bankruptcy risk',
            'Current valuation at 6x P/E — historically cheap',
          ],
          current_price_approx: '₹265', target_price_1yr: '₹320', upside_potential: '20%',
          risk_level: 'medium', key_risk: 'Government may cap fuel prices, limiting upside',
          signal_alignment: 'high',
          fundamentals: { 'P/E Ratio': '6.2x', 'Debt/Equity': '0.3x', '3yr Rev Growth': '18%', 'Dividend Yield': '4.2%' },
          best_for: 'Moderate risk investors wanting oil exposure with safety',
          investment_mode: 'Lumpsum or SIP both work',
          entry_strategy: 'Buy in 2 tranches — 60% now, 40% on any 5% dip',
        },
        {
          name: 'Oil India Ltd', nse_symbol: 'OIL', type: 'established', category: 'mid_cap',
          why_chosen: [
            'Smaller than ONGC but growing faster',
            'Northeast India gas fields are undervalued asset',
            'Dividend yield of 5.8% provides income floor',
          ],
          current_price_approx: '₹580', target_price_1yr: '₹720', upside_potential: '24%',
          risk_level: 'medium', key_risk: 'Lower liquidity than ONGC — harder to exit quickly',
          signal_alignment: 'high',
          fundamentals: { 'P/E Ratio': '8.1x', 'Debt/Equity': '0.4x', '3yr Rev Growth': '22%', 'Dividend Yield': '5.8%' },
          best_for: 'Investors comfortable with mid-cap, want higher growth',
          investment_mode: 'Lumpsum preferred',
          entry_strategy: 'Single tranche buy — liquidity risk means don\'t average down aggressively',
        },
        {
          name: 'Selan Exploration', nse_symbol: 'SELAN', type: 'emerging', category: 'small_cap',
          why_chosen: [
            'Small upstream oil company with Gujarat assets',
            'Revenue up 85% in 2 years on oil price tailwind',
            'Only 3 analyst reports — under the radar',
            'Net cash positive balance sheet — zero debt risk',
          ],
          current_price_approx: '₹410', target_price_1yr: '₹680', upside_potential: '65%',
          risk_level: 'high', key_risk: 'Small cap illiquidity + single geography concentration',
          signal_alignment: 'medium',
          fundamentals: { 'P/E Ratio': '12x', 'Debt/Equity': '0x', '3yr Rev Growth': '58%', 'Dividend Yield': '1.2%' },
          best_for: 'Aggressive investors with 2+ year horizon',
          investment_mode: 'Small SIP only — max 3% of portfolio',
          entry_strategy: 'SIP over 3 months. Never put more than 3% of total portfolio here.',
        },
      ],
      etf_alternative: {
        name: 'CPSE ETF', symbol: 'CPSEETF', expense_ratio: 0.01,
        why_chosen: 'Captures ONGC, Coal India, Power Finance — all oil/energy PSUs in one safe instrument',
        best_for: 'Beginners or risk-averse investors who want sector exposure without stock picking',
      },
    },
    {
      sector: 'IT',
      signal_fit_score: 7.8,
      signal_fit_reason: 'INR depreciation boosts USD revenue in rupee terms. Indirect but reliable beneficiary of current currency dynamics.',
      companies: [
        {
          name: 'TCS', nse_symbol: 'TCS', type: 'established', category: 'large_cap',
          why_chosen: [
            '60% revenue in USD — every 1% INR fall adds ~₹900 crore to revenue',
            'Largest IT company = most liquid, easiest to enter/exit',
            'Strong order book of $38B — revenue visibility for 2+ years',
          ],
          current_price_approx: '₹3,890', target_price_1yr: '₹4,400', upside_potential: '13%',
          risk_level: 'low', key_risk: 'US recession would hurt IT spending budgets significantly',
          signal_alignment: 'high',
          fundamentals: { 'P/E Ratio': '28x', 'Debt/Equity': '0x', '3yr Rev Growth': '14%', 'Dividend Yield': '1.5%' },
          best_for: 'Conservative investors wanting safe IT exposure',
          investment_mode: 'SIP preferred for averaging',
          entry_strategy: 'Start SIP immediately. Core allocation — never time this one.',
        },
      ],
      etf_alternative: {
        name: 'Nifty IT ETF', symbol: 'ITBEES', expense_ratio: 0.15,
        why_chosen: 'Captures all large IT names (TCS, Infosys, HCL, Wipro) without concentration risk',
        best_for: 'Anyone who doesn\'t want to pick individual IT stocks',
      },
    },
  ],

  portfolio_construction_note: 'Never put more than 20% in a single company. The emerging picks (Selan) should never exceed 3-5% of total portfolio. ETF alternatives are always the safer choice for beginners.',

  investment_strategy: {
    strategy_name: 'Oil Cycle + IT Currency Hedge — Defensive Growth',
    strategy_rationale: 'The current geopolitical environment creates a clear investment thesis: oil producers benefit from elevated prices while IT companies benefit from INR weakness. Gold anchors the portfolio against tail risks. This is not a speculative bet — it is a signal-aligned positioning.',
    deployment_plan: {
      approach: 'phased',
      reasoning: 'Market uncertainty from geopolitical signals — deploying in phases reduces timing risk',
      phases: [
        {
          phase: 1, label: 'Immediate Deployment', timing: 'This week',
          amount: 50000, percentage_of_total: 50,
          what_to_buy: [
            { instrument: 'ONGC', amount: 20000, reason: 'High conviction, oil signal peaking — don\'t wait' },
            { instrument: 'Nifty 50 Index Fund', amount: 20000, reason: 'Core equity exposure, always deploy early' },
            { instrument: 'Liquid Fund', amount: 10000, reason: 'Dry powder for Phase 2 opportunities' },
          ],
          trigger: 'Deploy immediately — signals are active now',
        },
        {
          phase: 2, label: 'Opportunistic Buy', timing: 'On Nifty 3-5% dip OR in 3 weeks',
          amount: 30000, percentage_of_total: 30,
          what_to_buy: [
            { instrument: 'Sovereign Gold Bond', amount: 20000, reason: 'Better tax treatment than Gold ETF. Tax-free on maturity.' },
            { instrument: 'Nifty IT ETF (ITBEES)', amount: 10000, reason: 'INR weakness play — safer than individual IT stocks' },
          ],
          trigger: 'Nifty below 21,800 OR 21 days elapsed — whichever comes first',
        },
        {
          phase: 3, label: 'Reserve Deployment', timing: 'Month 2-3',
          amount: 20000, percentage_of_total: 20,
          what_to_buy: [
            { instrument: 'Top up best performers', amount: 20000, reason: 'Add to winners after 8-week review confirms thesis' },
          ],
          trigger: '8-week portfolio review shows thesis intact',
        },
      ],
    },
    sip_vs_lumpsum: {
      recommendation: 'phased_lumpsum',
      reasoning: 'SIP is ideal for long-term wealth building (5+ years). For a 1-year signal-based strategy, phased lumpsum captures the thesis better. SIP averaging works against you when you have high-conviction entry points.',
      if_sip_preferred: {
        monthly_amount: 8500,
        duration_months: 12,
        instruments: [
          { name: 'Nifty 50 Index Fund', monthly: 4000 },
          { name: 'Sovereign Gold Bond', monthly: 2500 },
          { name: 'ONGC', monthly: 2000 },
        ],
        note: 'If market falls >10% in any month, increase SIP by 50% for that month. Buy more on fear.',
      },
    },
    rebalancing_schedule: [
      {
        at: '8 weeks',
        action: 'First review — check if signals have changed',
        what_to_check: ['Brent crude price vs $95 threshold', 'INR level vs 84.5', 'Iran-Israel conflict status'],
        if_signals_unchanged: 'Hold all positions — no action needed',
        if_de_escalation: 'Start reducing ONGC from 20% to 10% over 4 weeks',
      },
      {
        at: '6 months',
        action: 'Major rebalancing checkpoint',
        what_to_check: ['Portfolio vs Nifty 50 performance', 'Is original thesis still valid?', 'Tax position (STCG vs LTCG)'],
        rebalance_rule: 'Trim any position that has grown to >25% of portfolio. Don\'t add to losers unless thesis is unchanged.',
      },
    ],
    exit_strategy: {
      planned_exit: {
        date: '12 months from purchase date',
        method: 'Gradual exit — sell 25% per month over final 4 months to avoid timing risk',
        tax_note: 'Hold equity positions >12 months for LTCG benefit at 10% vs STCG at 15%. Don\'t sell at 11.5 months.',
      },
      emergency_exits: [
        {
          trigger: 'Portfolio falls more than 15% from peak',
          action: 'Exit all small caps immediately, reduce equity to 30%, shift to liquid funds',
          reason: 'Capital preservation takes priority over returns',
        },
        {
          trigger: 'Iran-Israel ceasefire officially confirmed',
          action: 'Sell ONGC within 48 hours — oil will reverse fast',
          reason: 'The core thesis for holding ONGC disappears instantly on ceasefire',
        },
        {
          trigger: 'India VIX crosses 22',
          action: 'Sell 30% of equity holdings, move to liquid/gold',
          reason: 'Systemic fear entering market — protect capital first',
        },
      ],
      profit_booking: [
        {
          trigger: 'Any single stock up 30% in < 3 months',
          action: 'Book 50% profit — let the rest run with a trailing stop loss',
          reason: 'Capture gains while staying in for further upside',
        },
      ],
    },
    monthly_monitoring: {
      weekly_checks: ['India VIX level (alert if >18)', 'Brent crude vs $95 threshold', 'FII/DII daily flows'],
      monthly_checks: ['Portfolio vs Nifty 50 return', 'Signal status update from InvestAI', 'Tax position review'],
      dont_check_daily: 'Avoid checking your portfolio price every day — it leads to emotional decisions that hurt returns.',
    },
    behavioral_guardrails: [
      'Never add more than planned if a stock is falling — only add if the THESIS is unchanged, not just because price is lower',
      'Never sell in panic on a single bad news day — check first if the core signal (oil, INR) has fundamentally changed',
      'Set price alerts for all exit triggers in Zerodha/Groww — don\'t rely on memory or willpower',
      'Don\'t add new stocks outside this plan without running the full InvestAI analysis again',
      'If you feel the urge to do something during high VIX periods — do nothing. Inaction is often the right action.',
    ],
    expected_outcome: {
      base_case_return: '12-16%',
      best_case_return: '22-28%',
      worst_case_return: '-8% to -12%',
      probability_of_positive_return: '71%',
      vs_fixed_deposit: 'FD gives ~7% — this targets 12-16% with moderate higher risk',
      vs_nifty: 'Strategy targets Nifty +4-6% outperformance if oil thesis plays out',
    },
    manager_note: 'One honest note: this strategy is built entirely on the oil/geopolitical signal. If that signal reverses — ceasefire, OPEC supply increase, oil demand destruction — you MUST act on the exit triggers. The biggest mistake investors make is staying in a position after the original thesis has changed. The signal watcher will alert you. Trust it.',
  },

  confidence_score: 0.74,
  what_could_go_wrong: [
    'If ceasefire happens next week, oil reversal would hurt ONGC position',
    'US recession could hurt both IT spending and oil demand simultaneously',
    'India VIX spike on domestic political event could trigger across-the-board selling',
  ],
}

// ── Main Page ───────────────────────────────────────────────────────────────

const TABS = [
  { id: 'strategy',   label: 'Signal Chain' },
  { id: 'companies',  label: 'Stock Picks' },
  { id: 'playbook',   label: 'Investment Playbook' },
]

export default function AdvicePage() {
  const [activeTab, setActiveTab] = useState('strategy')
  const advice = MOCK_ADVICE

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
            <div className="flex items-center gap-2 text-xs text-ink">
              <Brain size={13} className="text-gold" />
              <span>11 agents · 24s</span>
              <span className="px-2 py-0.5 rounded-full bg-jade/10 text-jade border border-jade/20">
                {Math.round(advice.confidence_score * 100)}% confidence
              </span>
            </div>
          </div>
        </div>

        <div className="max-w-6xl mx-auto px-6 py-8">

          {/* Summary header */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
            <div className="card-gold p-6">
              <div className="flex items-start justify-between gap-6">
                <div className="flex-1">
                  <div className="text-gold text-xs font-mono mb-2">ANALYSIS COMPLETE · ₹1,00,000 · 1 YEAR HORIZON</div>
                  <p className="text-ink-light leading-relaxed">{advice.narrative}</p>
                </div>
                <div className="flex-shrink-0 space-y-2">
                  {advice.what_could_go_wrong?.slice(0, 2).map((risk, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-ruby max-w-xs">
                      <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
                      {risk}
                    </div>
                  ))}
                </div>
              </div>

              {/* Signal chain preview */}
              <div className="mt-4 flex items-center gap-2 overflow-x-auto pb-1">
                {advice.reasoning_chain.slice(0, 4).map((step, i) => (
                  <div key={i} className="flex items-center gap-2 flex-shrink-0">
                    <div className="text-xs bg-surface-3 border border-white/8 rounded-lg px-2 py-1 max-w-40">
                      <div className="text-gold text-xs">→ {step.effect}</div>
                      <div className="text-ink text-xs">{Math.round(step.confidence * 100)}% conf</div>
                    </div>
                    {i < 3 && <ChevronRight size={12} className="text-ink" />}
                  </div>
                ))}
                <span className="text-ink text-xs flex-shrink-0">+{advice.reasoning_chain.length - 4} more steps</span>
              </div>
            </div>
          </motion.div>

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
                {advice.reasoning_chain.map((step, i) => (
                  <div key={i} className="flex items-start gap-4">
                    <div className="w-8 h-8 rounded-full bg-gold/10 border border-gold/20 flex items-center justify-center text-gold text-xs font-bold flex-shrink-0">
                      {step.step}
                    </div>
                    <div className="card p-4 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-ink text-xs mb-1">Cause: <span className="text-ink-light">{step.cause}</span></div>
                          <div className="text-white font-medium">→ {step.effect}</div>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <div className="text-gold text-sm font-mono">{Math.round(step.confidence * 100)}%</div>
                          <div className="text-ink text-xs">confidence</div>
                        </div>
                      </div>
                      <div className="mt-2 h-1 bg-surface-3 rounded-full overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-gold to-jade rounded-full" style={{ width: `${step.confidence * 100}%` }} />
                      </div>
                    </div>
                    {i < advice.reasoning_chain.length - 1 && (
                      <div className="absolute left-[1.75rem] mt-8 h-4 w-px bg-gold/20 ml-[3.5rem]" />
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Company Picks tab */}
            {activeTab === 'companies' && (
              <CompanyPicks
                sectorPicks={advice.company_picks}
                constructionNote={advice.portfolio_construction_note}
              />
            )}

            {/* Investment Playbook tab */}
            {activeTab === 'playbook' && (
              <InvestmentStrategy
                strategy={advice.investment_strategy}
                amount={100000}
              />
            )}
          </motion.div>

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
