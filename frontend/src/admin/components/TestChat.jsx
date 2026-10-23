'use client'
import { useEffect, useRef, useState } from 'react'
import { languages } from '@/xo/i18n'
import { adminApi, errorMessage } from '../lib/api'
import Icon from './Icon'
import { Badge, Button, Card } from './ui'

/** Talk to XO with unpublished drafts (FR-25). Uses the real model; nothing is saved for review or analytics. */
export default function TestChat({ drafts, note }) {
  const [language, setLanguage] = useState('en')
  const [log, setLog] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const end = useRef(null)

  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }) }, [log])

  const send = async (e) => {
    e.preventDefault()
    const message = text.trim()
    if (!message || busy) return
    setText('')
    setLog((l) => [...l, { from: 'user', text: message }])
    setBusy(true)
    try {
      const r = await adminApi('/config/test-chat', { method: 'POST', body: { message, language, session_id: sessionId, ...drafts } })
      setSessionId(r.session_id)
      setLog((l) => [...l, { from: 'xo', text: r.reply, blocked: r.blocked_topic, card: r.callback_card,
        escalations: (r.tools || []).filter((t) => t.startsWith('escalation:')).map((t) => t.slice(11)), error: r.error }])
    } catch (err) {
      setLog((l) => [...l, { from: 'xo', text: err.status === 422 ? 'Fix the problems in your draft first.' : errorMessage(err), error: true }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Test chat" subtitle={note || 'Try your draft with the real model. Visitors are not affected and nothing is saved.'}
      actions={<Button variant="quiet" size="sm" icon="refresh" onClick={() => { setLog([]); setSessionId(null) }} disabled={!log.length}>Reset</Button>}>
      <div className="xa-chat">
        <div className="xa-chat-log" aria-live="polite">
          {log.length === 0 && <p className="xa-muted xa-small">Ask what a visitor would ask, for example “What are the fees on a 2M flat in Dubai?”.</p>}
          {log.map((m, i) => (
            <div key={i} className={`xa-chat-msg ${m.from === 'user' ? 'is-user' : 'is-xo'}`}>
              {m.text}
              {(m.blocked || m.card || m.escalations?.length > 0) && (
                <small className="xa-row" style={{ gap: 4 }}>
                  {m.blocked && <Badge tone="warning" icon="shield">Blocked topic: {m.blocked}</Badge>}
                  {m.escalations?.map((x) => <Badge key={x} tone="info" icon="route">Escalation rule: {x.replace('_', ' ')}</Badge>)}
                  {m.card && <Badge tone="info" icon="user">Callback card shown</Badge>}
                </small>
              )}
            </div>
          ))}
          {busy && <div className="xa-chat-msg is-xo"><span className="xa-spinner" aria-label="XO is replying" /></div>}
          <div ref={end} />
        </div>
        <form className="xa-chat-form" onSubmit={send}>
          <label className="xa-sr" htmlFor="xa-test-lang">Language</label>
          <select id="xa-test-lang" value={language} onChange={(e) => { setLanguage(e.target.value); setLog([]); setSessionId(null) }}>
            {languages.map((l) => <option key={l.code} value={l.code}>{l.code.toUpperCase()}</option>)}
          </select>
          <label className="xa-sr" htmlFor="xa-test-msg">Message</label>
          <input id="xa-test-msg" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type as a visitor…" />
          <Button type="submit" icon="arrowRight" busy={busy} disabled={!text.trim()} aria-label="Send" />
        </form>
      </div>
      <p className="xa-small xa-muted" style={{ marginBlockStart: 10 }}><Icon name="info" size={13} /> Uses OpenAI like a real conversation, so each message has a small cost.</p>
    </Card>
  )
}
