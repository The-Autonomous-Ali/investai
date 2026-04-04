import { useState, useEffect } from 'react'
import { getSignals } from '../lib/api'

// Mock data — used when backend is not running
const MOCK_SIGNALS = [
  {
    id: 'mock-1', title: 'Brent Crude Approaches $96 on Middle East Tensions',
    source: 'Reuters', source_tier: 2, urgency: 'breaking', importance_score: 9.1,
    sentiment: 'negative', signal_type: 'geopolitical', geography: 'global',
    sectors_affected: { Aviation: 'negative', 'Oil & Gas': 'positive', Paints: 'negative', Tyres: 'negative' },
    chain_effects: ['Oil spike → CAD widening', 'INR depreciation → FII outflows', 'Inflation pressure → RBI caution'],
    stage: 'ESCALATING', detected_at: new Date(Date.now() - 45 * 60000).toISOString(), confidence: 0.82,
    corroborated_by: ['Economic Times', 'Mint'],
  },
  {
    id: 'mock-2', title: 'RBI Governor: "Vigilant on inflation, committed to 4% target"',
    source: 'RBI', source_tier: 1, urgency: 'developing', importance_score: 8.8,
    sentiment: 'neutral', signal_type: 'monetary', geography: 'india',
    sectors_affected: { Banking: 'positive', 'Real Estate': 'neutral', 'Small Cap': 'negative' },
    chain_effects: ['Rate hold likely → Banking NIM stable', 'Tight liquidity continues → NBFC stress', 'Bond yields stay elevated'],
    stage: 'ACTIVE', detected_at: new Date(Date.now() - 2 * 3600000).toISOString(), confidence: 0.91,
    corroborated_by: ['Economic Times', 'Business Standard', 'Mint'],
  },
  {
    id: 'mock-3', title: 'US Fed Signals Only 2 Rate Cuts in 2024 (vs 3 expected)',
    source: 'Bloomberg', source_tier: 2, urgency: 'developing', importance_score: 7.8,
    sentiment: 'negative', signal_type: 'monetary', geography: 'global',
    sectors_affected: { IT: 'positive', Banking: 'neutral', 'Real Estate': 'negative' },
    chain_effects: ['Dollar strengthens → INR pressure', 'FII outflows from emerging markets', 'IT revenues boost in INR terms'],
    stage: 'DEVELOPING', detected_at: new Date(Date.now() - 3 * 3600000).toISOString(), confidence: 0.76,
    corroborated_by: ['Reuters'],
  },
  {
    id: 'mock-4', title: 'India Q3 GDP 7.2% Beats 6.8% Estimate',
    source: 'MoSPI', source_tier: 1, urgency: 'long_term', importance_score: 8.5,
    sentiment: 'positive', signal_type: 'fiscal', geography: 'india',
    sectors_affected: { Infrastructure: 'positive', FMCG: 'positive', Banking: 'positive', Auto: 'positive' },
    chain_effects: ['Strong GDP → higher capex cycle', 'Government spending continues → infra boom', 'Consumer spending up → FMCG tailwind'],
    stage: 'ACTIVE', detected_at: new Date(Date.now() - 5 * 3600000).toISOString(), confidence: 0.95,
    corroborated_by: ['Economic Times', 'Mint', 'Business Standard'],
  },
]

export function useSignals() {
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [isLive, setIsLive] = useState(false)

  useEffect(() => {
    async function fetchSignals() {
      try {
        const data = await getSignals({ limit: 20 })
        if (data.signals && data.signals.length > 0) {
          setSignals(data.signals)
          setIsLive(true)
        } else {
          setSignals(MOCK_SIGNALS)
        }
      } catch {
        // Backend not running — use mock data
        setSignals(MOCK_SIGNALS)
        setIsLive(false)
      } finally {
        setLoading(false)
      }
    }
    fetchSignals()
  }, [])

  return { signals, loading, isLive }
}
