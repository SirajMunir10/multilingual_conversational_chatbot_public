'use client'
import { useCallback, useEffect, useState } from 'react'
import { languages } from '@/xo/i18n'
import { adminApi, errorMessage } from '../lib/api'
import Icon from '../components/Icon'
import { Badge, Button, Card, EmptyState, Notice, PageHeader, Tabs, formatDateTime } from '../components/ui'
import ConversationDetail from './ConversationDetail'

const ENDINGS = {
  lead: ['Callback saved', 'ok'], error: ['Ended on an error', 'warning'], first_reply: ['Left after first reply', 'muted'],
  property: ['After property results', 'neutral'], mortgage: ['After a mortgage result', 'neutral'],
  knowledge: ['After a knowledge answer', 'neutral'], advisor: ['During an advisor request', 'neutral'], other: ['After general chat', 'neutral']
}
const EMPTY_FILTERS = { days: 30, language: '', channel: '', outcome: '', rating: '', review: '', q: '' }
const languageName = (code) => languages.find((l) => l.code === code)?.name || code

export default function Conversations({ me, param, onNavigate }) {
  const canReview = me.permissions.includes('conversations.review')
  const canSeeDrafts = canReview || me.permissions.includes('kb.edit')
  const [tab, setTab] = useState('all')

  if (param) return <ConversationDetail me={me} sessionId={decodeURIComponent(param)} onBack={() => onNavigate('conversations')} />

  const tabs = [['all', 'All conversations'], ['queue', 'Review queue'], ...(canSeeDrafts ? [['drafts', 'Knowledge drafts']] : [])]
  return (
    <div className="xa-stack-sm">
      <PageHeader title="Conversations" subtitle="Read what visitors asked and how XO answered, review replies, and turn corrected answers into knowledge." />
      <Tabs label="Conversation views" value={tab} onChange={setTab} tabs={tabs.map(([id, label]) => ({ id, label }))} />
      {tab === 'all' && <ConversationList onOpen={(sid) => onNavigate(`conversations/${encodeURIComponent(sid)}`)} />}
      {tab === 'queue' && <ReviewQueue onOpen={(sid) => onNavigate(`conversations/${encodeURIComponent(sid)}`)} />}
      {tab === 'drafts' && <Drafts />}
    </div>
  )
}

function ConversationList({ onOpen }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    const qs = new URLSearchParams({ page: String(page), page_size: '25' })
    Object.entries(filters).forEach(([k, v]) => { if (v !== '' && v !== null) qs.set(k, String(v)) })
    try {
      setData(await adminApi(`/conversations?${qs}`))
      setError(null)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }, [filters, page])

  useEffect(() => { load() }, [load])

  const set = (key) => (e) => { setPage(1); setFilters((f) => ({ ...f, [key]: e.target.value })) }
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  const filtered = Object.entries(filters).some(([k, v]) => v !== EMPTY_FILTERS[k])

  return (
    <>
      <form className="xa-filterbar" role="search" onSubmit={(e) => { e.preventDefault(); setPage(1); setFilters((f) => ({ ...f, q: search.trim() })) }}>
        <label className="xa-sr" htmlFor="xa-conv-search">Search messages</label>
        <input id="xa-conv-search" type="search" placeholder="Search messages or a session id" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select label="Period" value={filters.days} onChange={set('days')} options={[[7, 'Last 7 days'], [30, 'Last 30 days'], [90, 'Last 90 days']]} />
        <Select label="Language" value={filters.language} onChange={set('language')}
          options={[['', 'All languages'], ...languages.map((l) => [l.code, l.name])]} />
        <Select label="Channel" value={filters.channel} onChange={set('channel')} options={[['', 'Text and voice'], ['text', 'Text'], ['voice', 'Voice']]} />
        <Select label="Outcome" value={filters.outcome} onChange={set('outcome')}
          options={[['', 'Any outcome'], ['handled', 'Handled by XO'], ['lead', 'Callback saved'], ['failed', 'Had a failed reply']]} />
        <Select label="Visitor rating" value={filters.rating} onChange={set('rating')} options={[['', 'Any rating'], ['up', 'Rated helpful'], ['down', 'Rated not helpful']]} />
        <Select label="Review" value={filters.review} onChange={set('review')}
          options={[['', 'Any review'], ['flagged', 'Flagged'], ['bad', 'Marked bad'], ['good', 'Marked good'], ['unreviewed', 'Not reviewed']]} />
        <Button type="submit" variant="ghost" icon="refresh" busy={busy}>Search</Button>
        {filtered && <Button variant="ghost" onClick={() => { setSearch(''); setPage(1); setFilters(EMPTY_FILTERS) }}>Clear</Button>}
      </form>

      {error && <Notice tone="error">{error}</Notice>}
      <Card title={data ? `${data.total.toLocaleString()} conversation${data.total === 1 ? '' : 's'}` : 'Conversations'}>
        {data && data.items.length === 0 && (
          <EmptyState icon="chat" title={filtered ? 'No conversation matches these filters' : 'No conversations yet'}>
            {filtered ? 'Try a longer period or fewer filters.' : 'Conversations appear here as soon as visitors chat with XO.'}
          </EmptyState>
        )}
        {data && data.items.length > 0 && (
          <>
            <div className="xa-table-wrap">
              <table className="xa-table xa-table-click">
                <thead>
                  <tr><th scope="col">Started</th><th scope="col">First question</th><th scope="col">Language</th>
                    <th scope="col">Messages</th><th scope="col">Topics</th><th scope="col">Outcome</th><th scope="col">Feedback</th></tr>
                </thead>
                <tbody>
                  {data.items.map((c) => {
                    const [ending, tone] = ENDINGS[c.ending] || ENDINGS.other
                    return (
                      <tr key={c.session_id} onClick={() => onOpen(c.session_id)}>
                        <td className="xa-small xa-nowrap">{formatDateTime(c.started_at)}</td>
                        <td className="xa-question">
                          <a href={`#/conversations/${encodeURIComponent(c.session_id)}`} onClick={(e) => { e.preventDefault(); onOpen(c.session_id) }}>
                            {c.first_question || <span className="xa-muted">(no message)</span>}
                          </a>
                          {c.channels.includes('voice') && <Badge>Voice</Badge>}
                        </td>
                        <td className="xa-small">{languageName(c.language)}</td>
                        <td className="xa-small">{c.user_turns}</td>
                        <td>{c.topics.map((t) => <Badge key={t}>{t}</Badge>)}</td>
                        <td><Badge tone={tone}>{ending}</Badge></td>
                        <td className="xa-small xa-nowrap">
                          {c.thumbs_up > 0 && <Badge tone="ok" icon="thumbUp">{c.thumbs_up}</Badge>}
                          {c.thumbs_down > 0 && <Badge tone="bad" icon="thumbDown">{c.thumbs_down}</Badge>}
                          {c.flagged > 0 && <Badge tone="warning">Flagged</Badge>}
                          {c.reviewed_bad > 0 && <Badge tone="warning">Bad</Badge>}
                          {c.reviewed_good > 0 && !c.reviewed_bad && <Badge tone="ok">Good</Badge>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {pages > 1 && (
              <nav className="xa-pager" aria-label="Pages">
                <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                <span className="xa-small">Page {page} of {pages}</span>
                <Button variant="ghost" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
              </nav>
            )}
          </>
        )}
      </Card>
    </>
  )
}

function ReviewQueue({ onOpen }) {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    adminApi('/review-queue').then(setItems).catch((e) => setError(errorMessage(e)))
  }, [])

  return (
    <>
      <p className="xa-lead">Replies that need a look: every reply a reviewer flagged, and every reply a visitor rated not helpful that nobody has reviewed yet.</p>
      {error && <Notice tone="error">{error}</Notice>}
      {items && items.length === 0 && <EmptyState icon="check" title="Nothing to review">New “not helpful” ratings and flagged replies will appear here.</EmptyState>}
      {items && items.length > 0 && (
        <ul className="xa-queue">
          {items.map((item) => (
            <li key={item.message_id} className="xa-card">
              <div className="xa-queue-head">
                {item.rating === -1 && <Badge tone="bad" icon="thumbDown">Visitor: not helpful</Badge>}
                {item.flagged && <Badge tone="warning">Flagged</Badge>}
                {item.verdict && <Badge tone={item.verdict === 'good' ? 'ok' : 'warning'}>Marked {item.verdict}</Badge>}
                <span className="xa-muted xa-small">{formatDateTime(item.created_at)} · {languageName(item.language)}</span>
              </div>
              {item.question && <p className="xa-queue-q"><strong>Visitor:</strong> {item.question}</p>}
              <p className="xa-queue-a"><strong>XO:</strong> {item.reply}</p>
              {item.note && <p className="xa-small xa-muted"><Icon name="list" size={14} /> {item.note} — {item.reviewed_by}</p>}
              <div><Button variant="ghost" onClick={() => onOpen(item.session_id)}>Open conversation</Button></div>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function Drafts() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    adminApi('/kb-drafts').then(setItems).catch((e) => setError(errorMessage(e)))
  }, [])

  return (
    <>
      <p className="xa-lead">Corrected answers saved from conversations. They are not live until they are published from the Knowledge base.</p>
      {error && <Notice tone="error">{error}</Notice>}
      {items && items.length === 0 && <EmptyState icon="book" title="No drafts yet">Open a conversation and use “Save as knowledge draft” on a reply.</EmptyState>}
      {items && items.length > 0 && (
        <ul className="xa-queue">
          {items.map((d) => (
            <li key={d.id} className="xa-card">
              <div className="xa-queue-head">
                <strong>{d.title}</strong><Badge tone="soon">Draft</Badge>
                <span className="xa-muted xa-small">{languageName(d.language)} · {d.created_by} · {formatDateTime(d.created_at)}</span>
              </div>
              <p className="xa-queue-q"><strong>Question:</strong> {d.question}</p>
              <p className="xa-queue-a"><strong>Answer:</strong> {d.answer}</p>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function Select({ label, value, onChange, options }) {
  const id = `xa-filter-${label.toLowerCase().replace(/\W+/g, '-')}`
  return (
    <>
      <label className="xa-sr" htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={onChange}>
        {options.map(([v, text]) => <option key={v} value={v}>{text}</option>)}
      </select>
    </>
  )
}
