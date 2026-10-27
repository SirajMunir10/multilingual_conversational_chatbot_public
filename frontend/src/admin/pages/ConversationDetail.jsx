'use client'
import { useEffect, useState } from 'react'
import { languages } from '@/xo/i18n'
import { adminApi, errorMessage } from '../lib/api'
import Icon from '../components/Icon'
import { Badge, Button, Card, Field, Modal, Notice, PageHeader, formatDateTime } from '../components/ui'

const languageName = (code) => languages.find((l) => l.code === code)?.name || code

export default function ConversationDetail({ me, sessionId, onBack }) {
  const canReview = me.permissions.includes('conversations.review')
  const [conv, setConv] = useState(null)
  const [error, setError] = useState(null)
  const [draftFor, setDraftFor] = useState(null)
  const [notice, setNotice] = useState(null)

  useEffect(() => {
    adminApi(`/conversations/${encodeURIComponent(sessionId)}`).then(setConv)
      .catch((e) => setError(e.code === 'not_found' ? 'This conversation was not found.' : errorMessage(e)))
  }, [sessionId])

  const updateReview = (messageId, review) =>
    setConv((c) => ({ ...c, messages: c.messages.map((m) => (m.id === messageId ? { ...m, review } : m)) }))

  const questionBefore = (index) => {
    for (let i = index - 1; i >= 0; i -= 1) if (conv.messages[i].role === 'user') return conv.messages[i].content
    return ''
  }

  return (
    <div className="xa-stack">
      <PageHeader title="Conversation" crumb={<><a href="#/conversations" onClick={(e) => { e.preventDefault(); onBack() }}>Conversations</a><Icon name="chevronRight" size={12} /><span className="xa-mono">{sessionId.slice(0, 14)}…</span></>}
        actions={<Button variant="ghost" onClick={onBack}>All conversations</Button>} />
      {error && <Notice tone="error">{error}</Notice>}
      {notice && <Notice tone="success" onDismiss={() => setNotice(null)}>{notice}</Notice>}
      {conv && (
        <>
          <Card title="Conversation">
            <dl className="xa-facts xa-facts-grid">
              <div><dt>Started</dt><dd>{formatDateTime(conv.started_at)}</dd></div>
              <div><dt>Last activity</dt><dd>{formatDateTime(conv.updated_at)}</dd></div>
              <div><dt>Language</dt><dd>{languageName(conv.language)}</dd></div>
              <div><dt>Channel</dt><dd>{conv.channels.map((c) => (c === 'voice' ? 'Voice' : 'Text')).join(' and ') || 'Text'}</dd></div>
              <div><dt>Visitor messages</dt><dd>{conv.user_turns}{conv.failed_turns ? ` (${conv.failed_turns} failed)` : ''}</dd></div>
              <div><dt>Advisor callback</dt><dd>{conv.lead_saved ? <Badge tone="ok">{conv.handoff_ticket}</Badge> : 'No'}</dd></div>
              <div><dt>Estimated AI cost</dt><dd>${conv.cost_usd.toFixed(4)}</dd></div>
              <div><dt>Session</dt><dd className="xa-mono xa-small">{conv.session_id}</dd></div>
            </dl>
            {conv.personal_data_masked && (
              <p className="xa-muted xa-small xa-card-note"><Icon name="lock" size={14} /> Phone numbers and emails are hidden for your role.</p>
            )}
          </Card>

          <Card title="Transcript">
            <ol className="xa-transcript">
              {conv.messages.map((m, i) => (
                <li key={m.id} className={`xa-turn xa-turn-${m.role}`}>
                  <div className="xa-turn-meta">
                    <strong>{m.role === 'user' ? 'Visitor' : 'XO'}</strong>
                    <span className="xa-muted xa-small">{formatDateTime(m.created_at)}{m.channel === 'voice' ? ' · voice' : ''}
                      {m.latency_ms ? ` · ${(m.latency_ms / 1000).toFixed(1)} s` : ''}</span>
                    {m.topics.map((t) => <Badge key={t}>{t}</Badge>)}
                    {m.rating === 1 && <Badge tone="ok" icon="thumbUp">Visitor: helpful</Badge>}
                    {m.rating === -1 && <Badge tone="bad" icon="thumbDown">Visitor: not helpful</Badge>}
                  </div>
                  <p className="xa-turn-text" dir="auto">{m.content}</p>
                  {m.role === 'assistant' && (canReview
                    ? <ReviewControls message={m} onSaved={(review) => updateReview(m.id, review)} onDraft={() => setDraftFor({ message: m, question: questionBefore(i) })} />
                    : m.review && <ReviewSummary review={m.review} />)}
                </li>
              ))}
              {conv.messages.at(-1)?.role === 'user' && (
                <li className="xa-turn xa-turn-error"><Icon name="alert" size={16} /> XO could not answer this message (error).</li>
              )}
            </ol>
          </Card>
        </>
      )}

      {draftFor && (
        <DraftDialog language={conv.language} source={draftFor} onClose={() => setDraftFor(null)}
          onSaved={(draft) => { setDraftFor(null); setNotice(`Saved “${draft.title}” as a knowledge draft. It goes live once it is published in the Knowledge base (7C).`) }} />
      )}
    </div>
  )
}

function ReviewSummary({ review }) {
  return (
    <p className="xa-small xa-muted">
      {review.verdict && <Badge tone={review.verdict === 'good' ? 'ok' : 'warning'}>Marked {review.verdict}</Badge>}
      {review.flagged && <Badge tone="warning">Flagged</Badge>} {review.note} — {review.reviewed_by}
    </p>
  )
}

function ReviewControls({ message, onSaved, onDraft }) {
  const saved = message.review || { verdict: null, flagged: false, note: '' }
  const [verdict, setVerdict] = useState(saved.verdict)
  const [flagged, setFlagged] = useState(saved.flagged)
  const [note, setNote] = useState(saved.note || '')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null)
  const changed = verdict !== saved.verdict || flagged !== saved.flagged || note !== (saved.note || '')

  const save = async () => {
    setBusy(true)
    setStatus(null)
    try {
      const review = await adminApi(`/messages/${message.id}/review`, { method: 'PUT', body: { verdict, flagged, note } })
      onSaved(review)
      setStatus({ tone: 'ok', text: 'Saved' })
    } catch (e) {
      setStatus({ tone: 'warning', text: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="xa-review">
      <div className="xa-segmented xa-segmented-sm" role="radiogroup" aria-label="Verdict on this reply">
        {[['good', 'Good'], ['bad', 'Bad']].map(([v, label]) => (
          <button key={v} type="button" role="radio" aria-checked={verdict === v} className={verdict === v ? `is-active is-${v}` : ''}
            onClick={() => setVerdict(verdict === v ? null : v)}>{label}</button>
        ))}
      </div>
      <label className="xa-check">
        <input type="checkbox" checked={flagged} onChange={(e) => setFlagged(e.target.checked)} /> Flag for review
      </label>
      <label className="xa-sr" htmlFor={`note-${message.id}`}>Note on this reply</label>
      <input id={`note-${message.id}`} className="xa-review-note" placeholder="Note (what was wrong, what it should say)" value={note}
        maxLength={2000} onChange={(e) => setNote(e.target.value)} />
      <Button variant="ghost" busy={busy} disabled={!changed} onClick={save}>Save review</Button>
      <Button variant="ghost" icon="book" onClick={onDraft}>Save as knowledge draft</Button>
      {status && <Badge tone={status.tone}>{status.text}</Badge>}
      {message.review?.reviewed_by && !changed && <span className="xa-muted xa-small">by {message.review.reviewed_by}</span>}
    </div>
  )
}

function DraftDialog({ source, language, onClose, onSaved }) {
  const [form, setForm] = useState({ title: '', question: source.question, answer: source.message.content, language })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSaved(await adminApi('/kb-drafts', { method: 'POST', body: { ...form, source_message_id: source.message.id } }))
    } catch (err) {
      setError(err.code === 'title_required' ? 'Give the entry a short title.'
        : err.code === 'question_and_answer_required' ? 'Both the question and the answer are needed.' : errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Modal title="Save as knowledge draft" onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" form="xa-draft-form" busy={busy}>Save draft</Button></>}>
      <form id="xa-draft-form" className="xa-form" onSubmit={submit}>
        <p className="xa-muted xa-small">Correct the answer below. The draft is not live until it is published in the Knowledge base.</p>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Title">{(a) => <input {...a} value={form.title} onChange={set('title')} maxLength={255} required />}</Field>
        <Field label="Question">{(a) => <textarea {...a} rows={2} value={form.question} onChange={set('question')} maxLength={2000} required />}</Field>
        <Field label="Correct answer">{(a) => <textarea {...a} rows={6} value={form.answer} onChange={set('answer')} maxLength={8000} required />}</Field>
        <Field label="Language">
          {(a) => (
            <select {...a} value={form.language} onChange={set('language')}>
              {languages.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select>
          )}
        </Field>
      </form>
    </Modal>
  )
}
