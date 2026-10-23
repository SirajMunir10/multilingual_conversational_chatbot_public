'use client'
import { useCallback, useEffect, useState } from 'react'
import { adminApi, setSignedOutHandler } from './lib/api'
import { canSee, findPage } from './navigation'
import AdminLayout from './components/AdminLayout'
import LoginScreen from './components/LoginScreen'
import { ToastProvider } from './components/ui'
import Account from './pages/Account'
import Activity from './pages/Activity'
import Analytics from './pages/Analytics'
import ComingSoon from './pages/ComingSoon'
import Conversations from './pages/Conversations'
import Escalation from './pages/Escalation'
import Knowledge from './pages/Knowledge'
import Overview from './pages/Overview'
import Rules from './pages/Rules'
import Tuning from './pages/Tuning'
import Users from './pages/Users'
import './styles/admin.css'

const PAGES = { overview: Overview, analytics: Analytics, conversations: Conversations, rules: Rules, tuning: Tuning, escalation: Escalation, knowledge: Knowledge,
  users: Users, activity: Activity, account: Account }

const readHash = () => (typeof window === 'undefined' ? '' : window.location.hash.replace(/^#\/?/, '').split('?')[0])

// Same storage key as the widget, so the admin opens in the theme the person last used.
const readTheme = () => {
  try { return window.localStorage.getItem('xo_theme') === 'dark' ? 'dark' : 'light' } catch (e) { return 'light' }
}

export default function AdminApp() {
  const [me, setMe] = useState(undefined) // undefined: checking, null: signed out
  const [notice, setNotice] = useState(null)
  const [route, setRoute] = useState(readHash)
  const [theme, setTheme] = useState(readTheme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try { window.localStorage.setItem('xo_theme', theme) } catch (e) {}
  }, [theme])

  useEffect(() => {
    const onHash = () => setRoute(readHash())
    window.addEventListener('hashchange', onHash)
    adminApi('/auth/me').then(setMe).catch(() => setMe(null))
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // Only while signed in: a request that finds the session gone (signed out elsewhere, role changed) returns to sign-in.
  const signedIn = Boolean(me)
  useEffect(() => {
    if (!signedIn) return undefined
    setSignedOutHandler(() => {
      setMe(null)
      setNotice('Your session ended. Please sign in again.')
    })
    return () => setSignedOutHandler(null)
  }, [signedIn])

  const navigate = useCallback((id) => {
    window.location.hash = `/${id}`
    // Moves keyboard and screen-reader focus to the new page.
    requestAnimationFrame(() => document.getElementById('xa-content')?.focus())
  }, [])

  const signOut = async () => {
    try { await adminApi('/auth/logout', { method: 'POST' }) } catch (e) {}
    setNotice('You have signed out.')
    setMe(null)
  }

  if (me === undefined) return <div className="xa-boot" aria-busy="true"><span className="xa-spinner" /></div>
  if (me === null) return <LoginScreen notice={notice} onSignedIn={(data) => { setNotice(null); setMe(data) }} />

  // Routes look like #/conversations or #/conversations/<session id>.
  const [routeId, ...rest] = route.split('/')
  const requested = findPage(routeId)
  const page = requested && canSee(requested, me.permissions) ? requested : findPage('overview')
  const Page = page.soon ? ComingSoon : PAGES[page.id]
  const param = page.id === routeId ? rest.join('/') || null : null

  return (
    <ToastProvider>
      <AdminLayout me={me} page={page} onNavigate={navigate} theme={theme} onSignOut={signOut}
        onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}>
        <Page key={page.id} me={me} page={page} param={param} onNavigate={navigate} />
      </AdminLayout>
    </ToastProvider>
  )
}
