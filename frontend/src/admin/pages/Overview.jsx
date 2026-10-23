'use client'
import { useEffect, useState } from 'react'
import { adminApi } from '../lib/api'
import { visibleGroups } from '../navigation'
import { StatCard } from '../components/charts'
import Icon from '../components/Icon'
import { Badge, Card, Notice, PageHeader } from '../components/ui'

const PERMISSION_LABELS = {
  'analytics.view': 'View analytics, usage and cost',
  'conversations.view': 'Read conversation transcripts',
  'conversations.review': 'Review replies and save corrected answers',
  'kb.edit': 'Edit the knowledge base',
  'translations.edit': 'Manage translations',
  'prompts.edit': 'Tune XO’s instructions, persona and guardrails',
  'escalation.edit': 'Decide when conversations go to a person',
  'experiments.edit': 'Run A/B tests',
  'rules.edit': 'Change rates, lending rules and fees',
  'budget.edit': 'Set the monthly AI budget',
  'integrations.manage': 'Manage integrations and models',
  'leads.view': 'See advisor leads and personal data',
  'users.manage': 'Add people and assign roles',
  'activity.view': 'Read the activity log',
  'config.reload': 'Apply configuration changes'
}

// Editable items whose unpublished drafts are worth a reminder, with the page that edits them.
const DRAFTABLE = [
  ['mortgage_rules', 'Lending rules', 'rules'], ['fees', 'Fees', 'rules'], ['bank_products', 'Bank products', 'rules'],
  ['prompt_profile', 'XO’s instructions', 'tuning'], ['messages', 'Canned replies', 'tuning'], ['escalation', 'Escalation rules', 'escalation']
]
const DRAFT_PERMISSION = { rules: 'rules.edit', tuning: 'prompts.edit', escalation: 'escalation.edit' }

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

export default function Overview({ me, onNavigate }) {
  const can = (p) => me.permissions.includes(p)
  const [status, setStatus] = useState(null)
  const [report, setReport] = useState(null)
  const [queue, setQueue] = useState(null)
  const [drafts, setDrafts] = useState([])
  const [kb, setKb] = useState(null)

  useEffect(() => {
    adminApi('/status').then(setStatus).catch(() => {})
    if (can('analytics.view')) adminApi('/analytics?days=7').then(setReport).catch(() => {})
    if (can('conversations.view')) adminApi('/review-queue?limit=200').then(setQueue).catch(() => {})
    if (can('kb.edit')) {
      Promise.all([adminApi('/kb/articles?status=due'), adminApi('/kb/drafts')])
        .then(([due, kbDrafts]) => setKb({ overdue: due.counts.overdue, due: due.counts.due, drafts: kbDrafts.length })).catch(() => {})
    }
    Promise.all(DRAFTABLE.filter(([, , page]) => can(DRAFT_PERMISSION[page])).map(([item, label, page]) =>
      adminApi(`/config/${item}`).then((r) => (r.draft ? { item, label, page, at: r.draft.updated_at, by: r.draft.updated_by } : null)).catch(() => null)))
      .then((list) => setDrafts(list.filter(Boolean)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const t = report?.totals
  const daily = report?.daily || []
  const shortcuts = visibleGroups(me.permissions).flatMap((g) => g.items).filter((i) => i.id !== 'overview' && !i.soon).slice(0, 6)
  const attention = [
    ...(queue && queue.length ? [{ icon: 'thumbDown', text: `${queue.length} ${queue.length === 1 ? 'reply needs' : 'replies need'} review`, go: 'conversations' }] : []),
    ...drafts.map((d) => ({ icon: 'history', text: `${d.label}: unpublished changes by ${d.by}`, go: d.page })),
    ...(kb?.drafts ? [{ icon: 'message', text: `${kb.drafts} corrected ${kb.drafts === 1 ? 'answer waits' : 'answers wait'} to be published as knowledge`, go: 'knowledge' }] : []),
    ...(kb?.due ? [{ icon: 'book', text: kb.overdue ? `${kb.overdue} knowledge ${kb.overdue === 1 ? 'entry is' : 'entries are'} past the review date` : `${kb.due} knowledge ${kb.due === 1 ? 'entry is' : 'entries are'} due for review soon`, go: 'knowledge' }] : []),
    ...(report?.budget.alert ? [{ icon: 'coins', text: `AI spend is at ${report.budget.used_pct}% of the monthly budget`, go: 'analytics' }] : []),
  ]

  return (
    <div className="xa-stack">
      <PageHeader title={`${greeting()}, ${me.user.name.split(' ')[0]}`}
        subtitle={`Signed in as ${me.role_label}. Everything you change here is recorded with your name.`} />

      {me.storage === 'memory' && (
        <Notice tone="warning">
          No database is connected, so accounts, versions and conversations are lost when the server restarts. Set <code>DATABASE_URL</code> on the backend.
        </Notice>
      )}

      {t && (
        <div className="xa-stats">
          <StatCard tone="c1" icon="chat" label="Conversations, last 7 days" value={t.conversations.toLocaleString()} series={daily.map((d) => d.conversations)} />
          <StatCard tone="c4" icon="checkCircle" label="Handled by XO" value={t.handled_by_xo_pct === null ? '—' : `${t.handled_by_xo_pct}%`}
            series={daily.map((d) => (d.conversations ? (100 * d.handled_by_xo) / d.conversations : 0))} />
          <StatCard tone="c2" icon="target" label="Advisor callbacks" value={t.leads.toLocaleString()} series={daily.map((d) => d.leads)} />
          <StatCard tone="c3" icon="smile" label="Satisfaction" value={t.satisfaction_pct === null ? '—' : `${t.satisfaction_pct}%`}
            hint={`${t.thumbs_up} helpful · ${t.thumbs_down} not helpful`} />
        </div>
      )}

      <div className="xa-grid-3">
        <Card title="Needs your attention" subtitle={attention.length ? undefined : 'Nothing waiting on you right now.'}>
          {attention.length > 0 && (
            <ul className="xa-linklist">
              {attention.map((a, i) => (
                <li key={i}>
                  <a href={`#/${a.go}`} onClick={(e) => { e.preventDefault(); onNavigate(a.go) }}>
                    <Icon name={a.icon} size={16} /><span>{a.text}</span><Icon name="chevronRight" size={16} />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="System">
          {!status && <p className="xa-muted">Loading…</p>}
          {status && (
            <dl className="xa-facts">
              <div><dt>Language model</dt><dd>{status.models.llm}</dd></div>
              <div><dt>Speech</dt><dd>{status.models.stt} · {status.models.tts}</dd></div>
              <div><dt>Voice</dt><dd>{status.models.voice}</dd></div>
              <div><dt>Data storage</dt><dd>{status.storage === 'postgres' ? <Badge tone="ok" icon="check">PostgreSQL</Badge> : <Badge tone="warning" icon="alert">Memory only</Badge>}</dd></div>
              <div><dt>Environment</dt><dd>{status.environment}</dd></div>
            </dl>
          )}
        </Card>
      </div>

      <div className="xa-grid-2">
        <Card title="Shortcuts">
          <ul className="xa-module-grid">
            {shortcuts.map((m) => (
              <li key={m.id}>
                <a href={`#/${m.id}`} onClick={(e) => { e.preventDefault(); onNavigate(m.id) }} className="xa-module">
                  <span className="xa-module-icon"><Icon name={m.icon} /></span>
                  <span className="xa-module-text"><strong>{m.label}</strong><small>{m.prd}</small></span>
                </a>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="What your role can do">
          <ul className="xa-check-list">
            {me.permissions.map((p) => <li key={p}><Icon name="check" size={16} />{PERMISSION_LABELS[p] || p}</li>)}
          </ul>
        </Card>
      </div>
    </div>
  )
}
