import { Zap } from 'lucide-react'

export default function BetaBanner() {
  return (
    <div className="bg-gold/10 border-b border-gold/20 px-4 py-1.5 text-center text-xs">
      <div className="inline-flex items-center gap-2">
        <Zap size={12} className="text-gold fill-gold" />
        <span className="text-gold font-semibold">InvestAI Beta</span>
        <span className="text-ink">
          — AI-generated analysis, not financial advice. You decide what to act on.
        </span>
      </div>
    </div>
  )
}
