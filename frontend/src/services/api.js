// Backend locations come from build-time env (Vite), never from hardcoded hosts.
// VITE_API_BASE: '' (same origin, proxied by Vite/nginx/Vercel) or a full URL.
// VITE_API_WS_BASE: WebSocket origin for live voice (Vercel rewrites cannot proxy WebSockets,
// so production sets this to the backend's wss:// origin).
const apiBase = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

function wsBase() {
  const configured = (import.meta.env.VITE_API_WS_BASE || '').replace(/\/$/, '')
  if (configured) return configured
  if (apiBase.startsWith('http')) return apiBase.replace(/^http/, 'ws')
  const { protocol, host } = window.location
  return `${protocol === 'https:' ? 'wss' : 'ws'}://${host}`
}

export const apiUrl = (path) => `${apiBase}${path}`
export const wsUrl = (path) => `${wsBase()}${path}`

export async function fetchClientConfig() {
  try {
    const res = await fetch(apiUrl('/api/config'))
    if (res.ok) return await res.json()
  } catch (e) {
    // Widget keeps working with defaults if the config endpoint is unreachable.
  }
  return null
}
