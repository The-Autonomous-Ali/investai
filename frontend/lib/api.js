import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// Handle 401 responses — redirect to sign-in
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      if (!window.location.pathname.startsWith('/auth')) {
        window.location.href = '/auth/signin'
      }
    }
    return Promise.reject(error)
  }
)

// ── Auth ─────────────────────────────────────────────────────────────────────
export const loginWithGoogle = (idToken, inviteCode = null) =>
  api.post('/api/auth/login', { id_token: idToken, invite_code: inviteCode }).then(r => r.data)

export const logout = () =>
  api.post('/api/auth/logout').then(r => r.data)

export const getCurrentUser = () =>
  api.get('/api/auth/me').then(r => r.data)

// ── Signals ──────────────────────────────────────────────────────────────────
export const getSignals = (params = {}) =>
  api.get('/api/signals/', { params }).then(r => r.data)

export const getActiveSignals = () =>
  api.get('/api/signals/active').then(r => r.data)

export const getSignalDetail = (id) =>
  api.get(`/api/signals/${id}`).then(r => r.data)

export const getSignalTimeline = (id) =>
  api.get(`/api/signals/${id}/timeline`).then(r => r.data)

// ── AI Advice ────────────────────────────────────────────────────────────────
export const getAdvice = ({ query, amount, horizon, country }) =>
  api.post('/api/agents/advice', { query, amount, horizon, country }).then(r => r.data)

// ── What If ──────────────────────────────────────────────────────────────────
export const runWhatIf = (scenario) =>
  api.post('/api/whatif', scenario).then(r => r.data)

export const getWhatIfExamples = () =>
  api.get('/api/whatif/examples').then(r => r.data)

// ── Portfolio ────────────────────────────────────────────────────────────────
export const getPortfolio = (activeOnly = true) =>
  api.get('/api/portfolio/', { params: { active_only: activeOnly } }).then(r => r.data)

export const addHolding = (data) =>
  api.post('/api/portfolio/', data).then(r => r.data)

export const updateHolding = (id, data) =>
  api.patch(`/api/portfolio/${id}`, data).then(r => r.data)

export const removeHolding = (id) =>
  api.delete(`/api/portfolio/${id}`).then(r => r.data)

// ── User ─────────────────────────────────────────────────────────────────────
export const getUserProfile = () =>
  api.get('/api/users/profile').then(r => r.data)

export const updateUserProfile = (data) =>
  api.patch('/api/users/profile', data).then(r => r.data)

export const getUserUsage = () =>
  api.get('/api/users/usage').then(r => r.data)

// ── Alerts ───────────────────────────────────────────────────────────────────
export const getAlerts = (params = {}) =>
  api.get('/api/alerts/', { params }).then(r => r.data)

export const markAlertRead = (id) =>
  api.patch(`/api/alerts/${id}/read`).then(r => r.data)

export const markAllAlertsRead = () =>
  api.post('/api/alerts/read-all').then(r => r.data)

// ── Subscriptions ────────────────────────────────────────────────────────────
export const getCurrentSubscription = () =>
  api.get('/api/subscriptions/current').then(r => r.data)

export const getPlans = () =>
  api.get('/api/subscriptions/plans').then(r => r.data)

export const createSubscription = (tier) =>
  api.post('/api/subscriptions/create', { tier }).then(r => r.data)

export default api
