// Backend locations come from build-time env (Next.js), never from hardcoded hosts.
// NEXT_PUBLIC_API_BASE: '' (same origin, proxied by Next dev/nginx/Vercel) or a full URL.
// NEXT_PUBLIC_API_WS_BASE: WebSocket origin for live voice (Vercel rewrites cannot proxy WebSockets,
// so production sets this to the backend's wss:// origin).
const apiBase = (process.env.NEXT_PUBLIC_API_BASE || '').replace(/\/$/, '')

function wsBase() {
  const configured = (process.env.NEXT_PUBLIC_API_WS_BASE || '').replace(/\/$/, '')
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
