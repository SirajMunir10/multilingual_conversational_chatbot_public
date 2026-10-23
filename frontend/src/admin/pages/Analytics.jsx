'use client'
import { useCallback, useEffect, useState } from 'react'
import { languages } from '@/xo/i18n'
import { adminApi, errorMessage } from '../lib/api'
import { BarList, ColumnChart, StatCard } from '../components/charts'
import { Badge, Button, Card, Field, Modal, Notice, PageHeader } from '../components/ui'

const RANGES = [7, 30, 90]
const pct = (v) => (v === null || v === undefined ? '—' : `${v}%`)
// Small AI costs (fractions of a cent) keep enough digits to be meaningful.
const usd = (v, digits) => {
  if (v === null || v === undefined) return '—'
  const n = Number(v)
  return `$${n.toFixed(digits ?? (n !== 0 && Math.abs(n) < 1 ? 4 : 2))}`
}
const languageName = (code) => languages.find((l) => l.code === code)?.name || code

// Change against the previous period: a relative % for counts and costs, percentage points for rates.
const relative = (now, before) => (before ? { value: (100 * (now - before)) / before, unit: '%' } : null)
const points = (now, before) => (now !== null && before !== null && before !== undefined ? { value: now - before, unit: ' pt' } : null)

export default function Analytics({ me }) {
  const [days, setDays] = useState(30)
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [editBudget, setEditBudget] = useState(false)
  const canEditBudget = me.permissions.includes('budget.edit')

  const load = useCallback(async () => {
    setBusy(true)
    try {
      setReport(await adminApi(`/analytics?days=${days}`))
      setError(null)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }, [days])

  useEffect(() => { load() }, [load])

  const t = report?.totals
  const prev = report?.previous
  const last14 = (report?.daily || []).slice(-14)
  const dayLabel = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
  const dailyRate = (num, den) => last14.map((d) => (d[den] ? (100 * d[num]) / d[den] : 0))

  return (
    <div className="xa-stack">
      <PageHeader title="Analytics" subtitle="How visitors use XO, how often it helps without a person, and what it costs. Days follow Dubai time."
        actions={(
          <>
            <div className="xa-segmented" role="radiogroup" aria-label="Date range">
              {RANGES.map((d) => (
                <button key={d} type="button" role="radio" aria-checked={days === d} className={days === d ? 'is-active' : ''} onClick={() => setDays(d)}>
                  {d} days
                </button>
              ))}
            </div>
            <Button variant="ghost" icon="refresh" busy={busy} onClick={load} aria-label="Refresh" />
          </>
        )} />

      {error && <Notice tone="error">{error}</Notice>}
      {report?.budget.alert && (
        <Notice tone="warning">
          AI spend this month is {usd(report.budget.month_cost_usd)}, {report.budget.used_pct}% of the {usd(report.budget.monthly_usd, 0)} budget
          (alert at {report.budget.alert_pct}%).
        </Notice>
      )}

      {t && (
        <>
          <div className="xa-stats">
            <StatCard tone="c1" icon="chat" label="Conversations" value={t.conversations.toLocaleString()}
              delta={prev && relative(t.conversations, prev.conversations)} hint={`${t.user_messages.toLocaleString()} visitor messages`}
              series={last14.map((d) => d.conversations)} />
            <StatCard tone="c4" icon="checkCircle" label="Handled by XO" value={pct(t.handled_by_xo_pct)}
              delta={prev && points(t.handled_by_xo_pct, prev.handled_by_xo_pct)} hint="No advisor needed · PRD goal 40% or more"
              series={dailyRate('handled_by_xo', 'conversations')} />
            <StatCard tone="c2" icon="target" label="Lead conversion" value={pct(t.lead_conversion_pct)}
              delta={prev && points(t.lead_conversion_pct, prev.lead_conversion_pct)} hint={`${t.leads} advisor callbacks saved`}
              series={last14.map((d) => d.leads)} />
            <StatCard tone="c3" icon="smile" label="Satisfaction" value={pct(t.satisfaction_pct)}
              delta={prev && points(t.satisfaction_pct, prev.satisfaction_pct)} hint={`${t.thumbs_up} helpful · ${t.thumbs_down} not helpful`}
              series={last14.map((d) => d.thumbs_up - d.thumbs_down)} />
            <StatCard tone="c5" icon="coins" label="Cost per conversation" value={usd(t.cost_per_conversation_usd)} deltaGood="down"
              delta={prev && relative(t.cost_per_conversation_usd, prev.cost_per_conversation_usd)} hint={`${usd(t.cost_usd)} in this period`}
              series={last14.map((d) => d.cost_usd)} />
          </div>

          <div className="xa-grid-3">
            <Card title="Conversations per day" subtitle={`Last ${days} days`}>
              {t.conversations === 0
                ? <p className="xa-muted">No conversations in this period yet.</p>
                : <ColumnChart valueLabel="Conversations"
                    data={report.daily.map((d) => ({ label: dayLabel(d.date), value: d.conversations, title: `${dayLabel(d.date)}: ${d.conversations} conversations` }))} />}
            </Card>
            <Card title="Where conversations end" subtitle="The last thing before the visitor left">
              <BarList valueLabel="conversations" total={t.conversations} data={report.endings.map((x) => ({ label: x.label, value: x.conversations }))} />
            </Card>
          </div>

          <div className="xa-grid-2">
            <Card title="What people asked about" subtitle="From what XO did; one conversation can cover several topics">
              <BarList valueLabel="conversations" total={t.conversations} data={report.topics.map((x) => ({ label: x.label, value: x.conversations }))} />
            </Card>
            <Card title="Languages and channels" subtitle="A conversation that used text and voice counts in both">
              <BarList valueLabel="conversations" total={t.conversations}
                data={[...report.languages.map((x) => ({ label: languageName(x.language), value: x.conversations })),
                  ...[{ label: 'Text', value: report.channels.text }, { label: 'Voice', value: report.channels.voice }].filter((x) => x.value)]} />
            </Card>
          </div>

          <div className="xa-grid-2">
            <Card title="Most common first questions">
              {report.top_questions.length === 0
                ? <p className="xa-muted">No questions yet.</p>
                : (
                  <ol className="xa-ranked">
                    {report.top_questions.map((q, i) => <li key={i}><span>{q.question}</span><Badge>{q.conversations}×</Badge></li>)}
                  </ol>
                )}
            </Card>
            <BudgetCard budget={report.budget} canEdit={canEditBudget} onEdit={() => setEditBudget(true)} />
          </div>
        </>
      )}

      {editBudget && (
        <BudgetDialog budget={report.budget} onClose={() => setEditBudget(false)} onSaved={() => { setEditBudget(false); load() }} />
      )}
    </div>
  )
}

function BudgetCard({ budget, canEdit, onEdit }) {
  const used = budget.used_pct
  return (
    <Card title="AI budget this month" subtitle="Language model, speech and search"
      actions={canEdit && <Button variant="ghost" size="sm" onClick={onEdit}>{budget.monthly_usd ? 'Change budget' : 'Set a budget'}</Button>}>
      {budget.monthly_usd ? (
        <div className="xa-budget">
          <div className="xa-budget-figures">
            <strong>{usd(budget.month_cost_usd)}</strong>
            <span className="xa-muted">of {usd(budget.monthly_usd, 0)} · alert at {budget.alert_pct}%</span>
            {budget.alert ? <Badge tone="warning" icon="alert">Over the alert level</Badge> : <Badge tone="ok" icon="check">Within budget</Badge>}
          </div>
          <div className="xa-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(100, Math.round(used || 0))}
            aria-label="Share of the monthly budget used">
            <span className={budget.alert ? 'is-alert' : ''} style={{ width: `${Math.min(100, used || 0)}%` }} />
            <i style={{ insetInlineStart: `${budget.alert_pct}%` }} aria-hidden="true" />
          </div>
        </div>
      ) : (
        <p className="xa-muted">
          {usd(budget.month_cost_usd)} spent so far this month. No budget is set
          {canEdit ? '; set one to get an alert before costs run high.' : '. An admin can set one.'}
        </p>
      )}
      <p className="xa-muted xa-small xa-card-note">Estimated from token, audio and character usage at the prices in the server’s pricing table.</p>
    </Card>
  )
}

function BudgetDialog({ budget, onClose, onSaved }) {
  const [amount, setAmount] = useState(budget.monthly_usd ?? '')
  const [alertPct, setAlertPct] = useState(budget.alert_pct ?? 80)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await adminApi('/budget', { method: 'PUT', body: { monthly_usd: amount === '' ? null : Number(amount), alert_pct: Number(alertPct) } })
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Modal title="Monthly AI budget" subtitle="An alert shows on Analytics when spending reaches the level you set." onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" form="xa-budget-form" busy={busy}>Save</Button></>}>
      <form id="xa-budget-form" className="xa-form" onSubmit={submit}>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Budget per month (USD)" hint="Leave empty to switch the budget off.">
          {(a) => <input {...a} type="number" min="0" step="any" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />}
        </Field>
        <Field label="Alert when spending reaches (%)">
          {(a) => <input {...a} type="number" min="1" max="100" step="1" value={alertPct} onChange={(e) => setAlertPct(e.target.value)} required />}
        </Field>
      </form>
    </Modal>
  )
}
