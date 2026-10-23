'use client'
import { useState } from 'react'
import { adminApi, errorMessage } from '../lib/api'
import { Button, Card, Field, Notice, PageHeader } from '../components/ui'

export default function Account({ me }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const mismatch = confirm && next !== confirm

  const submit = async (e) => {
    e.preventDefault()
    if (mismatch) return
    setBusy(true)
    setResult(null)
    try {
      await adminApi('/auth/password', { method: 'POST', body: { current_password: current, new_password: next } })
      setResult({ tone: 'success', text: 'Password changed. You stay signed in here; other sessions were signed out.' })
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch (err) {
      setResult({ tone: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="xa-stack xa-narrow">
      <PageHeader title="My account" subtitle="Your profile and password." />
      <Card title="Profile">
        <dl className="xa-facts">
          <div><dt>Name</dt><dd>{me.user.name}</dd></div>
          <div><dt>Email</dt><dd>{me.user.email}</dd></div>
          <div><dt>Role</dt><dd>{me.role_label}</dd></div>
        </dl>
        <p className="xa-muted xa-small">Your name and role are managed by an admin.</p>
      </Card>

      <Card title="Change password">
        <form className="xa-form" onSubmit={submit}>
          {result && <Notice tone={result.tone} onDismiss={() => setResult(null)}>{result.text}</Notice>}
          <Field label="Current password">
            {(a) => <input {...a} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />}
          </Field>
          <Field label="New password" hint="At least 12 characters. A short sentence is easy to remember and hard to guess.">
            {(a) => <input {...a} type="password" autoComplete="new-password" minLength={12} value={next} onChange={(e) => setNext(e.target.value)} required />}
          </Field>
          <Field label="Repeat new password" error={mismatch ? 'The two passwords do not match.' : null}>
            {(a) => <input {...a} type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />}
          </Field>
          <div><Button type="submit" busy={busy} disabled={!current || next.length < 12 || mismatch || !confirm}>Change password</Button></div>
        </form>
      </Card>
    </div>
  )
}
