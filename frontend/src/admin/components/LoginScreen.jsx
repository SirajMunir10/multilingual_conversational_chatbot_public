'use client'
import { useState } from 'react'
import { adminApi, errorMessage } from '../lib/api'
import Icon from './Icon'
import { Button, Field, Notice } from './ui'

export default function LoginScreen({ onSignedIn, notice }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSignedIn(await adminApi('/auth/login', { method: 'POST', body: { email, password } }))
    } catch (err) {
      setError(errorMessage(err))
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="xa-login">
      <section className="xa-login-aside" aria-hidden="true">
        <div className="xa-login-mark"><img src="/xo-mascot.png" alt="" width="40" height="40" /><strong>XO Admin</strong></div>
        <div className="xa-login-pitch">
          <h2>Run XO without waiting on a developer.</h2>
          <p>XOTO&apos;s back office for the assistant that answers buyers in 15 languages.</p>
          <ul>
            <li><Icon name="chart" size={16} />See what visitors ask and where they leave</li>
            <li><Icon name="chat" size={16} />Review replies and fix the ones that missed</li>
            <li><Icon name="calculator" size={16} />Update rates, fees and rules with a preview first</li>
            <li><Icon name="history" size={16} />Every change is versioned and can be undone</li>
          </ul>
        </div>
        <p className="xa-login-foot-note">Access is limited to XOTO staff. Activity is recorded.</p>
      </section>
      <section className="xa-login-main">
        <form className="xa-login-card" onSubmit={submit} noValidate>
          <h1>Sign in</h1>
          <p className="xa-login-sub">Use the work email an XO admin set up for you.</p>
          {notice && !error && <Notice>{notice}</Notice>}
          {error && <Notice tone="error">{error}</Notice>}
          <Field label="Work email">
            {(a) => <input {...a} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />}
          </Field>
          <Field label="Password">
            {(a) => <input {...a} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />}
          </Field>
          <Button type="submit" busy={busy} disabled={!email || !password} className="xa-btn-block">Sign in</Button>
          <p className="xa-login-foot">Forgot your password? An admin can reset it under Users &amp; roles.</p>
          <a className="xa-login-back" href="/">Back to XO chat</a>
        </form>
      </section>
    </main>
  )
}
