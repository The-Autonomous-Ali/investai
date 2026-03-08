import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
})

// ── Signals ──────────────────────────────────────────────────────────────────
export const getSignals = () =>
  api.get('/api/agents/signals/current').then(r => r.data)

export const getSignalTimeline = (id) =>
  api.get(`/api/agents/signals/${id}/timeline`).then(r => r.data)

// ── AI Advice ────────────────────────────────────────────────────────────────
export const getAdvice = ({ query, amount, horizon, country }) =>
  api.post('/api/agents/advice', { query, amount, horizon, country }).then(r => r.data)

// ── Portfolio ────────────────────────────────────────────────────────────────
export const getPortfolio = (userId) =>
  api.get(`/api/portfolio/${userId}`).then(r => r.data)

export const addPortfolioItem = (data) =>
  api.post('/api/portfolio/items', data).then(r => r.data)

export const deletePortfolioItem = (id) =>
  api.delete(`/api/portfolio/items/${id}`).then(r => r.data)

// ── Agent Performance ────────────────────────────────────────────────────────
export const getAgentPerformance = () =>
  api.get('/api/agents/performance').then(r => r.data)

// ── User ─────────────────────────────────────────────────────────────────────
export const updateUserProfile = (data) =>
  api.put('/api/users/profile', data).then(r => r.data)

export const getUserAlerts = () =>
  api.get('/api/alerts').then(r => r.data)

export default api
