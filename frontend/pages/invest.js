import { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  TrendingUp, TrendingDown, Brain, Globe, Shield, Zap, 
  ChevronRight, RefreshCw, BarChart2, Activity,
  AlertCircle, DollarSign, Clock, MapPin
} from 'lucide-react'
import axios from 'axios'

// Use environment variable for API URL, fallback to localhost
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const COUNTRIES = [
  { code: 'IN', name: 'India', flag: '🇮🇳' },
  { code: 'US', name: 'United States', flag: '🇺🇸' },
  { code: 'GB', name: 'United Kingdom', flag: '🇬🇧' },
  { code: 'AE', name: 'UAE', flag: '🇦🇪' },
  { code: 'DE', name: 'Germany', flag: '🇩🇪' },
  { code: 'SG', name: 'Singapore', flag: '🇸🇬' },
  { code: 'AU', name: 'Australia', flag: '🇦🇺' },
  { code: 'JP', name: 'Japan', flag: '🇯🇵' },
]

export default function InvestPage() {
  const [query, setQuery] = useState('')
  const [amount, setAmount] = useState('')
  const [horizon, setHorizon] = useState('1 year')
  const [country, setCountry] = useState('India')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [userName, setUserName] = useState('')
  const router = useRouter()

  useEffect(() => {
    const name = sessionStorage.getItem('investai_user_name')
    if (!name) {
      router.push('/onboarding')
    } else {
      setUserName(name)
    }
  }, [])

  const handleAnalyze = async () => {
    if (!query || !amount) return
    setLoading(true)
    setResponse(null)
    try {
      // FIX: call backend directly using hardcoded IP
      const res = await axios.post(`${API_URL}/api/agents/advice`, {
        query,
        amount: Number(amount),
        horizon,
        country,
      })
      const data = res.data
      if (data.success && data.recommendation) {
        setResponse({
          ...data.recommendation,
          is_demo: data.meta?.is_mock || data.recommendation?.is_demo
        })
      } else {
        alert('Agents were unable to reach a consensus. Please try a more specific query.')
      }
    } catch (error) {
      console.error('Failed to get advice:', error)
      alert('Failed to connect to AI agents. Please ensure the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-surface text-white">
      <Head>
        <title>Investment Advisor — InvestAI</title>
      </Head>

      {/* Navigation */}
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
              <div className="text-white text-sm font-medium">{userName}</div>
              <div className="text-ink text-xs">Standard Account</div>
            </div>
            <div className="w-10 h-10 rounded-full bg-gold/20 flex items-center justify-center text-gold font-bold border border-gold/30">
              {userName?.charAt(0)}
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="grid lg:grid-cols-12 gap-12">
          
          {/* Left Column: Input Form */}
          <div className="lg:col-span-5 space-y-8">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
            >
              <h1 className="font-display text-4xl font-bold mb-4 leading-tight">
                Global Intelligence,<br />
                <span className="text-gold-gradient">Local Decisions.</span>
              </h1>
              <p className="text-ink-light text-lg">
                Tell us your goals. Our agents will chain global signals to build your plan.
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="card p-8 border-gold/20 bg-surface-2/80 shadow-2xl"
            >
              <div className="space-y-6">
                {/* Country Selection */}
                <div>
                  <label className="block text-ink text-sm font-medium mb-3 flex items-center gap-2">
                    <Globe size={14} className="text-gold" /> Country of Residence
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {COUNTRIES.map((c) => (
                      <button
                        key={c.code}
                        onClick={() => setCountry(c.name)}
                        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm border transition-all ${
                          country === c.name 
                            ? 'bg-gold/10 border-gold/40 text-gold shadow-lg shadow-gold/5' 
                            : 'bg-surface-3 border-white/5 text-ink hover:border-white/20'
                        }`}
                      >
                        <span>{c.flag}</span>
                        <span>{c.name}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Prompt Box */}
                <div>
                  <label className="block text-ink text-sm font-medium mb-3 flex items-center gap-2">
                    <Brain size={14} className="text-gold" /> Your Investment Goal
                  </label>
                  <textarea
                    className="input-dark w-full px-4 py-3 rounded-xl min-h-[120px] resize-none"
                    placeholder="e.g. I want to invest 10k for 1 yr and I'm concerned about rising oil prices and how they affect my local market."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>

                {/* Amount & Horizon */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-ink text-sm font-medium mb-2 flex items-center gap-2">
                      <DollarSign size={14} className="text-gold" /> Amount
                    </label>
                    <input
                      type="number"
                      className="input-dark w-full px-4 py-3 rounded-xl"
                      placeholder="10000"
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-ink text-sm font-medium mb-2 flex items-center gap-2">
                      <Clock size={14} className="text-gold" /> Horizon
                    </label>
                    <select
                      className="input-dark w-full px-4 py-3 rounded-xl bg-surface-3"
                      value={horizon}
                      onChange={(e) => setHorizon(e.target.value)}
                    >
                      <option>6 months</option>
                      <option>1 year</option>
                      <option>2 years</option>
                      <option>5 years</option>
                    </select>
                  </div>
                </div>

                <button
                  onClick={handleAnalyze}
                  disabled={loading || !query || !amount}
                  className="btn-gold w-full py-4 rounded-xl flex items-center justify-center gap-3 font-display font-bold text-lg disabled:opacity-50 transition-all shadow-xl shadow-gold/20"
                >
                  {loading ? (
                    <>
                      <RefreshCw size={20} className="animate-spin" />
                      Orchestrating Agents...
                    </>
                  ) : (
                    <>
                      Chain Signals & Analyze <ChevronRight size={20} />
                    </>
                  )}
                </button>

                {loading && (
                  <div className="space-y-2 mt-4 text-xs text-ink font-mono bg-surface-3/50 p-4 rounded-xl border border-white/5">
                    <div className="flex items-center gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-jade animate-pulse" />
                      <span>Signal Watcher scanning global economic data...</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse" />
                      <span>Research Agent analyzing {country} impact chain...</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                      <span>Comparing global patterns vs local outcomes...</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-ruby animate-pulse" />
                      <span>Identifying sectors facing the heat...</span>
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          </div>

          {/* Right Column: Results */}
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
                  <h3 className="text-xl font-semibold mb-2 text-ink-light">Ready to Analyze</h3>
                  <p className="text-ink max-w-sm">
                    Enter your investment goals and select your country to see how global events are impacting your local sectors.
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
                    <h3 className="text-xl font-bold">Agents at Work</h3>
                    <p className="text-ink italic">"Calculating causality between Brent crude and {country} inflation..."</p>
                  </div>
                </motion.div>
              ) : (
                <motion.div
                  key="response"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-6"
                >
                  {/* Narrative Section */}
                  <div className="card p-6 border-gold/10 bg-surface-2">
                    <div className="flex items-center gap-2 mb-4">
                      <Activity size={18} className="text-gold" />
                      <h3 className="font-display font-semibold text-lg text-white">AI Analysis: Global vs Local</h3>
                    </div>
                    <p className="text-ink-light leading-relaxed whitespace-pre-line">
                      {response.narrative}
                    </p>
                  </div>

                  {/* Sector Heatmap */}
                  <div className="grid md:grid-cols-2 gap-6">
                    {/* Facing the Heat */}
                    <div className="card p-6 border-ruby/20 bg-ruby/5">
                      <div className="flex items-center gap-2 mb-4">
                        <TrendingDown size={18} className="text-ruby" />
                        <h3 className="font-display font-semibold text-white">Facing the Heat</h3>
                      </div>
                      <div className="space-y-4">
                        {response.sectors_to_avoid?.map((s, i) => (
                          <div key={i} className="bg-surface-2/60 p-3 rounded-lg border border-ruby/10">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-white font-medium text-sm">{s.sector}</span>
                              <span className="text-ruby text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-ruby/10 uppercase tracking-wider">Avoid</span>
                            </div>
                            <p className="text-ink text-xs leading-tight">{s.reason}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Resilient / Opportunities */}
                    <div className="card p-6 border-jade/20 bg-jade/5">
                      <div className="flex items-center gap-2 mb-4">
                        <TrendingUp size={18} className="text-jade" />
                        <h3 className="font-display font-semibold text-white">Resilient Sectors</h3>
                      </div>
                      <div className="space-y-4">
                        {response.sectors_to_buy?.map((s, i) => (
                          <div key={i} className="bg-surface-2/60 p-3 rounded-lg border border-jade/10">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-white font-medium text-sm">{s.sector}</span>
                              <span className="text-jade text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-jade/10 uppercase tracking-wider">Strong</span>
                            </div>
                            <p className="text-ink text-xs leading-tight">{s.reason}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Allocation Plan */}
                  <div className="card p-6 bg-surface-2 border-white/5">
                    <h3 className="font-display font-semibold text-white mb-6">Personalized Allocation for {country}</h3>
                    <div className="space-y-5">
                      {Object.entries(response.allocation || {}).map(([name, data], i) => (
                        <div key={i} className="space-y-2">
                          <div className="flex items-center justify-between text-sm">
                            <div className="flex items-center gap-2">
                              <div className="w-2 h-2 rounded-full bg-gold" />
                              <span className="text-white font-medium">{name}</span>
                            </div>
                            <span className="text-gold font-mono font-bold">{data.percentage}%</span>
                          </div>
                          <div className="w-full h-1.5 bg-surface-3 rounded-full overflow-hidden">
                            <motion.div 
                              initial={{ width: 0 }}
                              animate={{ width: `${data.percentage}%` }}
                              transition={{ duration: 1, delay: i * 0.1 }}
                              className="h-full bg-gradient-to-r from-gold to-gold-dark" 
                            />
                          </div>
                          <p className="text-ink text-xs italic">{data.reason}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Insights Footer */}
                  <div className="flex items-center justify-between px-2 text-xs text-ink font-mono">
                    <div className="flex items-center gap-4">
                      <span>Confidence: <span className="text-gold">{(response.confidence_score * 100).toFixed(0)}%</span></span>
                      <span>Signals Used: <span className="text-white">{response.signals_used?.length || 0}</span></span>
                    </div>
                    <button 
                      onClick={() => setResponse(null)}
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

      {/* Footer Disclaimer */}
      <footer className="max-w-7xl mx-auto px-6 py-12 border-t border-white/5 mt-12">
        <div className="flex items-start gap-4 text-ink text-[11px] leading-relaxed max-w-4xl opacity-50">
          <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
          <p>
            DISCLAIMER: This analysis is for informational purposes only. InvestAI uses advanced LLMs to simulate financial logic and signal chaining. 
            All investment recommendations should be reviewed by a human financial advisor registered in your local jurisdiction. 
            Past results do not guarantee future performance. Your country selection affects the knowledge base used for analysis.
          </p>
        </div>
      </footer>
    </div>
  )
}