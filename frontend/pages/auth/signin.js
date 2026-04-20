import Head from "next/head"
import { signIn, getSession } from "next-auth/react"
import { useRouter } from "next/router"
import { useState, useEffect } from "react"
import { Zap } from "lucide-react"

export async function getServerSideProps(ctx) {
  const session = await getSession(ctx)
  if (session) return { redirect: { destination: "/invest", permanent: false } }
  return { props: {} }
}

export default function SignIn() {
  const [loading, setLoading] = useState(false)
  const [demoLoading, setDemoLoading] = useState(false)
  const [mounted, setMounted] = useState(false)
  const router = useRouter()
  useEffect(() => { setMounted(true) }, [])
  const handleGoogleSignIn = async () => { setLoading(true); await signIn("google", { callbackUrl: "/onboarding" }) }
  const handleDemoSignIn = () => { 
    setDemoLoading(true); 
    sessionStorage.setItem("demo_mode","true"); 
    sessionStorage.setItem("demo_user", JSON.stringify({name:"Demo User",email:"demo@investai.in",plan:"pro"})); 
    router.push("/onboarding") 
  }
  if (!mounted) return null
  return (
    <>
      <Head><title>Sign In - InvestAI</title></Head>
      <div className="min-h-screen bg-surface flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="text-center mb-10">
            <h1 className="font-display font-bold text-3xl text-white mb-2">Welcome back</h1>
            <p className="text-ink">Sign in to your investment intelligence dashboard</p>
          </div>
          <button onClick={handleDemoSignIn} disabled={demoLoading} className="w-full flex items-center justify-center gap-3 py-4 rounded-xl border-2 border-gold/40 bg-gold/10 text-gold font-semibold hover:bg-gold/20 transition-all mb-3">
            <Zap size={18} />{demoLoading ? "Loading..." : "Continue as Demo UI Only"}
          </button>
          <p className="text-center text-xs text-ink mb-6">Demo mode shows the product surface but does not unlock authenticated personalized recommendations.</p>
          <div className="relative mb-6"><div className="absolute inset-0 flex items-center"><div className="w-full border-t border-white/10"/></div><div className="relative flex justify-center text-xs text-ink bg-surface px-3">OR</div></div>
          <button onClick={handleGoogleSignIn} disabled={loading} className="w-full flex items-center justify-center gap-3 py-4 rounded-xl bg-white text-gray-800 font-semibold hover:bg-gray-100 transition-colors mb-6">
            {loading ? "Signing in..." : "Continue with Google"}
          </button>
        </div>
      </div>
    </>
  )
}
