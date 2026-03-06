import Head from 'next/head'
import { signIn, getSession } from 'next-auth/react'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { TrendingUp, Linkedin, AlertCircle, CheckCircle2 } from 'lucide-react'

export async function getServerSideProps(ctx) {
  const session = await getSession(ctx)
  if (session) return { redirect: { destination: '/dashboard', permanent: false } }
  return { props: {} }
}

export default function SignIn() {
  const [loading, setLoading] = useState(false)

  const handleGoogleSignIn = async () => {
    setLoading(true)
    await signIn('google', { callbackUrl: '/onboarding' })
  }

  return (
    <>
      <Head>
        <title>Sign In — InvestAI</title>
      </Head>
      <div className="min-h-screen bg-surface flex">
        {/* Left: Branding */}
        <div className="hidden lg:flex flex-1 flex-col justify-between p-12 bg-surface-2 border-r border-white/5 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-gold/5 to-transparent pointer-events-none" />
          <div className="flex items-center gap-2 relative z-10">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
              <TrendingUp size={16} className="text-surface" />
            </div>
            <span className="font-display font-bold text-xl text-white">InvestAI</span>
          </div>
          <div className="relative z-10">
            <h2 className="font-display text-4xl font-bold text-white mb-6 leading-tight">
              Intelligence that <br />
              <span className="text-gold-gradient">compounds</span> over time.
            </h2>
            <div className="space-y-4">
              {[
                'Chains global events to India sector impacts',
                'Remembers your strategy history',
                'Tells you when to enter AND when to exit',
                'Tax-optimized for Indian investors',
              ].map((point, i) => (
                <div key={i} className="flex items-center gap-3 text-ink-light">
                  <CheckCircle2 size={16} className="text-jade flex-shrink-0" />
                  <span>{point}</span>
                </div>
              ))}
            </div>
          </div>
          <p className="text-ink text-xs relative z-10">
            Educational purposes only. Not SEBI-registered advice.
          </p>
        </div>

        {/* Right: Sign in form */}
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full max-w-md"
          >
            <div className="text-center mb-10">
              <h1 className="font-display font-bold text-3xl text-white mb-2">Welcome back</h1>
              <p className="text-ink">Sign in to your investment intelligence dashboard</p>
            </div>

            {/* Google Sign In */}
            <button
              onClick={handleGoogleSignIn}
              disabled={loading}
              className="w-full flex items-center justify-center gap-3 py-4 rounded-xl bg-white text-gray-800 font-semibold font-display hover:bg-gray-100 transition-colors disabled:opacity-50 mb-6"
            >
              <svg width="20" height="20" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              {loading ? 'Signing in...' : 'Continue with Google'}
            </button>

            <div className="relative mb-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/10" />
              </div>
              <div className="relative flex justify-center text-xs text-ink bg-surface px-3">
                THEN OPTIONALLY
              </div>
            </div>

            {/* LinkedIn nudge card */}
            <div className="card p-5 border-blue-500/20 bg-blue-500/5 mb-8">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
                  <Linkedin size={16} className="text-white" />
                </div>
                <div>
                  <div className="font-semibold text-white text-sm mb-1 flex items-center gap-2">
                    Connect LinkedIn
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gold/10 text-gold border border-gold/20">
                      Recommended
                    </span>
                  </div>
                  <p className="text-ink text-xs leading-relaxed mb-3">
                    Most people don't have LinkedIn — that's fine. But if you do, it unlocks early signals from 
                    the RBI Governor, SEBI Chairman, and top fund managers — <em>before</em> it hits the news.
                  </p>
                  <p className="text-ink text-xs">
                    3 days before the Feb 2024 rate hold, our system caught the Governor's post about 
                    "managing expectations." LinkedIn users got an early alert.
                  </p>
                </div>
              </div>
              <button className="w-full mt-4 py-2 rounded-lg border border-blue-500/40 text-blue-400 text-sm hover:bg-blue-500/10 transition-colors">
                Connect LinkedIn (Optional)
              </button>
              <p className="text-center text-ink text-xs mt-2">You can also connect this later in Settings →</p>
            </div>

            <div className="flex items-start gap-2 text-xs text-ink">
              <AlertCircle size={14} className="flex-shrink-0 mt-0.5 text-ink" />
              <p>
                By signing in you agree to our Terms of Service. InvestAI provides educational 
                information only and is not a SEBI-registered advisor.
              </p>
            </div>
          </motion.div>
        </div>
      </div>
    </>
  )
}
