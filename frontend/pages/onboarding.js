import { useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { motion } from 'framer-motion'
import { TrendingUp, User, Shield, ArrowRight, CheckCircle } from 'lucide-react'

export default function Onboarding() {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  const handleCreateAccount = async (e) => {
    e.preventDefault()
    if (!name) return
    
    setLoading(true)
    // Simulate account creation
    setTimeout(() => {
      sessionStorage.setItem('investai_user_name', name)
      router.push('/invest')
    }, 1500)
  }

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center p-6">
      <Head>
        <title>Create Your Account — InvestAI</title>
      </Head>

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        <div className="flex items-center gap-2 justify-center mb-12">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center shadow-lg shadow-gold/20">
            <TrendingUp size={20} className="text-surface" />
          </div>
          <span className="font-display font-bold text-2xl text-white">InvestAI</span>
        </div>

        <div className="card p-8 border-gold/20 shadow-xl shadow-gold/5">
          <h1 className="font-display text-2xl font-bold text-white mb-2 text-center">
            Welcome to InvestAI
          </h1>
          <p className="text-ink text-center mb-8">
            Let's start by setting up your profile.
          </p>

          <form onSubmit={handleCreateAccount} className="space-y-6">
            <div>
              <label className="block text-ink text-sm font-medium mb-2">Your Full Name</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-light" size={18} />
                <input
                  required
                  type="text"
                  className="input-dark w-full pl-10 pr-4 py-3 rounded-xl"
                  placeholder="e.g. Sameer Kashyap"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-start gap-3 text-xs text-ink-light">
                <CheckCircle size={14} className="text-jade mt-0.5 flex-shrink-0" />
                <span>No credit card required for the free forever plan.</span>
              </div>
              <div className="flex items-start gap-3 text-xs text-ink-light">
                <Shield size={14} className="text-gold mt-0.5 flex-shrink-0" />
                <span>Your data is encrypted and never shared with third parties.</span>
              </div>
            </div>

            <button
              disabled={!name || loading}
              className="btn-gold w-full py-4 rounded-xl flex items-center justify-center gap-2 font-display font-bold text-lg disabled:opacity-50 transition-all shadow-lg shadow-gold/20"
            >
              {loading ? (
                <div className="w-6 h-6 border-2 border-surface border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  Create Account <ArrowRight size={20} />
                </>
              )}
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  )
}
