'use client'
import { useState } from 'react'
import { HistoryDrawer, PublishBar, PublishDialog, VersionLine, useConfigItem } from '../components/config'
import Icon from '../components/Icon'
import TestChat from '../components/TestChat'
import { Badge, Card, Field, Notice, PageHeader, Switch, TagInput, UnitInput } from '../components/ui'

// The teams visitors choose from on the callback card (their labels are translated in the widget).
const TEAMS = { mortgage: 'Mortgage advisor', sales: 'Property advisor', support: 'Customer support' }
const ROUTES = [['auto', 'Most suitable team'], ['mortgage', 'Mortgage advisor'], ['sales', 'Property advisor'], ['support', 'Customer support']]

const RULE_TEXT = {
  explicit_request: ['The visitor asks for a person', 'Always on: visitors can ask for an advisor at any point (PRD FR-5).', 'user'],
  low_confidence: ['XO cannot answer', 'When the knowledge base has no reliable answer, XO says so and offers an advisor instead of guessing.', 'info'],
  keywords: ['Sensitive words', 'When a message contains one of these words or phrases, XO offers a callback.', 'tag'],
  high_value: ['High-value enquiry', 'When a property price or loan reaches these amounts, XO offers the chosen team.', 'coins'],
  frustration: ['The visitor sounds frustrated', 'XO judges the tone of the conversation; when a visitor sounds upset it apologises and offers a callback.', 'alert'],
}

export default function Escalation() {
  const item = useConfigItem('escalation')
  const [history, setHistory] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const data = item.working
  const live = item.published?.data

  const editRule = (type, fn) => item.update((d) => fn(d.rules.find((r) => r.type === type)))

  return (
    <div className="xa-stack-sm">
      <PageHeader title="Escalation rules" subtitle="When XO offers a call back from a person, and which team receives it. XO only offers; nothing is saved until the visitor confirms."
        actions={item.published && <VersionLine item={item} onHistory={() => setHistory(true)} />} />
      {item.error && <Notice tone="error">{item.error}</Notice>}

      {data && (
        <div className="xa-editor">
          <div className="xa-stack">
            <Card title="Rules" subtitle="Each rule offers a callback at most once per conversation.">
              {Object.keys(RULE_TEXT).map((type) => {
                const rule = data.rules.find((r) => r.type === type)
                const before = live.rules.find((r) => r.type === type)
                const [title, text, icon] = RULE_TEXT[type]
                const locked = type === 'explicit_request'
                return (
                  <div key={type} className="xa-rulecard">
                    <Switch checked={rule.enabled} disabled={locked} label={`${title}: ${rule.enabled ? 'on' : 'off'}`}
                      onChange={(v) => editRule(type, (r) => { r.enabled = v })} />
                    <div>
                      <div className="xa-row" style={{ gap: 8 }}>
                        <Icon name={icon} size={16} /><h3>{title}</h3>
                        {locked && <Badge tone="brand" icon="lock">Always on</Badge>}
                        {JSON.stringify(rule) !== JSON.stringify(before) && <Badge tone="warning">Changed</Badge>}
                      </div>
                      <p>{text}</p>
                      {(rule.enabled || locked) && (
                        <div className="xa-rule-settings">
                          {type === 'low_confidence' && (
                            <Field label="After unanswered questions">
                              {(a) => <UnitInput {...a} value={rule.after_misses} unit={rule.after_misses === 1 ? 'question' : 'questions'} step={1} min={1} max={10}
                                onChange={(v) => editRule(type, (r) => { r.after_misses = v === null ? 1 : Math.round(v) })} />}
                            </Field>
                          )}
                          {type === 'keywords' && (
                            <Field label="Words and phrases" className="is-wide" hint="Any language. Whole words for English. Press Enter after each one.">
                              {(a) => <TagInput {...a} value={rule.keywords} placeholder="complaint, lawyer, شكوى" onChange={(v) => editRule(type, (r) => { r.keywords = v })} />}
                            </Field>
                          )}
                          {type === 'high_value' && (
                            <>
                              <Field label="Property price from">
                                {(a) => <UnitInput {...a} value={rule.min_property_aed} prefix="AED" onChange={(v) => editRule(type, (r) => { r.min_property_aed = v })} />}
                              </Field>
                              <Field label="Or loan from">
                                {(a) => <UnitInput {...a} value={rule.min_loan_aed} prefix="AED" onChange={(v) => editRule(type, (r) => { r.min_loan_aed = v })} />}
                              </Field>
                            </>
                          )}
                          <Field label="Send to">
                            {(a) => (
                              <select {...a} value={rule.team} onChange={(e) => editRule(type, (r) => { r.team = e.target.value })}>
                                {ROUTES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                              </select>
                            )}
                          </Field>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </Card>

            <Card title="Teams and queues" subtitle="Visitors pick from these three teams on the callback card. The queue name is what your staff see on each lead."
              flush>
              <div className="xa-table-wrap">
                <table className="xa-table">
                  <thead><tr><th scope="col">Team (visitor sees)</th><th scope="col">Queue name on leads</th><th scope="col">Lead goes to</th></tr></thead>
                  <tbody>
                    {data.teams.map((t, i) => (
                      <tr key={t.key}>
                        <td><strong>{TEAMS[t.key]}</strong></td>
                        <td>
                          <div className={t.queue !== live.teams[i].queue ? 'xa-field is-changed' : 'xa-field'}>
                            <label className="xa-sr" htmlFor={`queue-${t.key}`}>Queue name for {TEAMS[t.key]}</label>
                            <input id={`queue-${t.key}`} value={t.queue} maxLength={60} onChange={(e) => item.update((d) => { d.teams[i].queue = e.target.value })} />
                          </div>
                        </td>
                        <td className="xa-small xa-muted">{t.key === 'mortgage' ? 'Vault (mortgage CRM)' : 'GRID (real-estate CRM)'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
          <aside className="xa-editor-side">
            <TestChat drafts={{ escalation: data }} note="Try a message that should trigger a rule, for example one with your keywords." />
          </aside>
        </div>
      )}

      {data && <PublishBar item={item} label="rule changes" onReview={() => setReviewing(true)} />}
      {reviewing && (
        <PublishDialog item={item} title="Publish escalation rules" onClose={() => setReviewing(false)}>
          <RuleChanges before={live} after={data} />
        </PublishDialog>
      )}
      {history && <HistoryDrawer item={item} onClose={() => setHistory(false)} />}
    </div>
  )
}

function RuleChanges({ before, after }) {
  const lines = []
  after.rules.forEach((r) => {
    const b = before.rules.find((x) => x.type === r.type)
    const name = RULE_TEXT[r.type][0]
    if (b.enabled !== r.enabled) lines.push(`${name}: switched ${r.enabled ? 'on' : 'off'}`)
    if (b.team !== r.team) lines.push(`${name}: now sent to ${ROUTES.find(([v]) => v === r.team)?.[1]}`)
    if (JSON.stringify(b.keywords) !== JSON.stringify(r.keywords)) lines.push(`${name}: words are now ${r.keywords.join(', ') || 'none'}`)
    if (b.after_misses !== r.after_misses) lines.push(`${name}: after ${r.after_misses} unanswered ${r.after_misses === 1 ? 'question' : 'questions'}`)
    if (b.min_property_aed !== r.min_property_aed || b.min_loan_aed !== r.min_loan_aed) {
      lines.push(`${name}: from AED ${Number(r.min_property_aed).toLocaleString()} price or AED ${Number(r.min_loan_aed).toLocaleString()} loan`)
    }
  })
  after.teams.forEach((t, i) => { if (before.teams[i].queue !== t.queue) lines.push(`${TEAMS[t.key]} queue: “${before.teams[i].queue}” → “${t.queue}”`) })
  return lines.length
    ? <div><p className="xa-field-label">What changes</p><ul className="xa-check-list" style={{ marginBlockStart: 8 }}>{lines.map((l) => <li key={l}><Icon name="arrowRight" size={14} />{l}</li>)}</ul></div>
    : <p className="xa-muted">No changes.</p>
}
