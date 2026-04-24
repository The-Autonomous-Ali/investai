import Head from 'next/head'
import Link from 'next/link'
import { useEffect } from 'react'
import { useRouter } from 'next/router'
import { useSession } from 'next-auth/react'
import { TrendingUp, ArrowRight, Activity, Brain } from 'lucide-react'

export default function DashboardPlaceholder() {
  const router = useRouter()
  const { data: session, status } = useSession()

  useEffect(() => {
    if (status === 'authenticated') {
      const t = setTimeout(() => router.replace('/invest'), 1200)
      return () => clearTimeout(t)
    }
  }, [status, router])

  return (
    <>
      <Head><title>Dashboard — InvestAI</title></Head>
      <div className="min-h-screen bg-surface flex flex-col">
        <div className="sticky top-0 z-50 border-b border-white/5 bg-surface/90 backdrop-blur-md">
          <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-3">
            <Link href="/" className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
                <TrendingUp size={14} className="text-surface" />
              </div>
              <span className="font-display font-bold text-white">InvestAI</span>
            </Link>
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center px-6">
          <div className="max-w-xl text-center">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-gold/10 border border-gold/20 text-gold text-xs font-mono mb-5">
              <Activity size={12} /> REAL-DATA DASHBOARD COMING POST-LAUNCH
            </div>
            <h1 className="font-display text-3xl font-bold text-white mb-3">
              This dashboard is being rebuilt on live data.
            </h1>
            <p className="text-ink text-base mb-6">
              During Beta, the primary experience is Investment Advice — a live, evidence-backed
              analysis of your question. A real-data dashboard and portfolio view will arrive in
              the next release.
            </p>
            <div className="flex items-center justify-center gap-3">
              <Link
                href="/invest"
                className="btn-gold px-5 py-2.5 rounded-lg text-sm font-semibold inline-flex items-center gap-2"
              >
                Go to Investment Advice <ArrowRight size={14} />
              </Link>
              <Link
                href="/signals"
                className="btn-ghost px-5 py-2.5 rounded-lg text-sm inline-flex items-center gap-2"
              >
                <Brain size={14} /> Live Signals
              </Link>
            </div>
            {status === 'authenticated' && (
              <div className="mt-6 text-ink text-xs">Redirecting you to Advice…</div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
