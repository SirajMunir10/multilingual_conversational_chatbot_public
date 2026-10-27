'use client'
import { useState } from 'react'
import { languages } from '@/xo/i18n'
import { DiffView, HistoryDrawer, PublishBar, PublishDialog, VersionLine, useConfigItem } from '../components/config'
import Icon from '../components/Icon'
import TestChat from '../components/TestChat'
import { Badge, Button, Card, EmptyState, Field, Notice, PageHeader, Tabs, TagInput } from '../components/ui'

const JOURNEY_TEMPLATES = [
  { title: 'Property search', steps: ['Ask whether they want to buy or rent.', 'Ask which area or community they prefer.', 'Ask their budget.',
    'Ask how many bedrooms and their timeline.', 'Search, show 3 to 5 matches, then offer to check what mortgage they would qualify for.'] },
  { title: 'Mortgage affordability', steps: ['Ask their monthly income.', 'Ask their monthly debts and card limits.', 'Ask the down payment they have.',
    'Ask the target area or price range.', 'Calculate, give the affordable price range and the estimated monthly payment, then offer matching properties.'] },
]

const MESSAGE_LABELS = {
  error_generic: 'When something goes wrong', voice_unavailable: 'When voice is unavailable',
  button_confirm: 'Callback card: confirm button', button_edit: 'Callback card: edit button'
}

/** XO's instructions as the model reads them (same layout as the server, for the before/after comparison). */
function renderInstructions(p, language = 'en') {
  let text = p.persona + p.sections.map((s) => `## ${s.title}\n${s.body}`).join('')
  const extras = []
  const journeys = (p.journeys || []).filter((j) => j.steps?.length)
  if (journeys.length) {
    const lines = ['## Guided journeys', 'When a conversation matches one of these journeys, follow its steps in order. Ask one question at a time and skip any step the visitor has already answered.']
    journeys.forEach((j) => { lines.push(`### ${j.title}`); j.steps.forEach((s, i) => lines.push(`${i + 1}. ${s}`)) })
    extras.push(lines.join('\n'))
  }
  if (p.tone_by_language?.[language]) extras.push(`## Tone in this language\n${p.tone_by_language[language]}`)
  const banned = (p.banned_topics || []).map((t) => t.name).filter(Boolean)
  if (banned.length) extras.push(`## Topics you never discuss\nPolitely decline and steer back to UAE property, mortgages or XOTO services if the visitor asks about: ${banned.join('; ')}.`)
  if (extras.length) text = `${text.replace(/\n+$/, '')}\n\n${extras.join('\n\n')}\n`
  return text
}

export default function Tuning() {
  const profile = useConfigItem('prompt_profile')
  const messages = useConfigItem('messages')
  const [tab, setTab] = useState('instructions')
  const [history, setHistory] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const item = tab === 'replies' ? messages : profile
  const ready = profile.working && messages.working
  const p = profile.working

  return (
    <div className="xa-stack-sm">
      <PageHeader title="Bot tuning" subtitle="How XO talks: its instructions, guided journeys, tone, the topics it refuses and its fixed replies. Sections required by the PRD are locked."
        actions={item?.published && <VersionLine item={item} onHistory={() => setHistory(true)} />} />
      {(profile.error || messages.error) && <Notice tone="error">{profile.error || messages.error}</Notice>}
      <Tabs label="Tuning sections" value={tab} onChange={setTab} tabs={[
        { id: 'instructions', label: 'Instructions', changed: profile.changed }, { id: 'journeys', label: 'Guided journeys' },
        { id: 'tone', label: 'Tone by language' }, { id: 'banned', label: 'Banned topics' },
        { id: 'replies', label: 'Canned replies', changed: messages.changed }]} />

      {ready && (
        <div className="xa-editor">
          <div className="xa-stack">
            {tab === 'instructions' && <Instructions item={profile} />}
            {tab === 'journeys' && <Journeys item={profile} />}
            {tab === 'tone' && <Tone item={profile} />}
            {tab === 'banned' && <Banned item={profile} />}
            {tab === 'replies' && <Replies item={messages} />}
          </div>
          <aside className="xa-editor-side">
            <TestChat drafts={{ prompt_profile: p, messages: messages.working }} />
          </aside>
        </div>
      )}

      {item?.working && <PublishBar item={item} onReview={() => setReviewing(true)} />}
      {reviewing && (
        <PublishDialog item={item} title={item === profile ? 'Publish XO’s instructions' : 'Publish canned replies'} onClose={() => setReviewing(false)}>
          {item === profile
            ? <div><p className="xa-field-label" style={{ marginBlockEnd: 8 }}>Changes to the instructions (English)</p>
                <DiffView before={renderInstructions(profile.published.data)} after={renderInstructions(p)} /></div>
            : <ReplyChanges item={messages} />}
        </PublishDialog>
      )}
      {history && <HistoryDrawer item={item} onClose={() => setHistory(false)} />}
    </div>
  )
}

function Instructions({ item }) {
  const p = item.working
  const live = item.published.data
  const addSection = () => item.update((d) => {
    const at = d.sections.findIndex((s) => s.locked)
    d.sections.splice(at === -1 ? d.sections.length : at, 0, { id: `custom_${Date.now().toString(36)}`, title: 'New section', body: '\n', locked: false })
  })
  return (
    <>
      <Card title="Persona" subtitle="The opening of XO’s instructions: who it is and who it talks to.">
        <Field label="Persona" changed={p.persona !== live.persona}>
          {(a) => <textarea {...a} rows={7} value={p.persona} onChange={(e) => item.update((d) => { d.persona = e.target.value })} />}
        </Field>
      </Card>
      <Card title="Sections" subtitle="Edit the open sections. Locked sections carry PRD rules and stay exactly as they are."
        actions={<Button variant="ghost" size="sm" icon="plus" onClick={addSection}>Add section</Button>}>
        <div className="xa-stack">
          {p.sections.map((s, i) => {
            const before = live.sections.find((x) => x.id === s.id)
            if (s.locked) {
              return (
                <div key={s.id}>
                  <div className="xa-row" style={{ justifyContent: 'space-between', marginBlockEnd: 6 }}>
                    <strong>{s.title}</strong><span className="xa-lock"><Icon name="lock" size={13} />Locked by the PRD</span>
                  </div>
                  <div className="xa-locked-body">{s.body.trim()}</div>
                </div>
              )
            }
            return (
              <div key={s.id} className="xa-stack-sm">
                <div className="xa-row" style={{ flexWrap: 'nowrap' }}>
                  <div style={{ flex: 1 }}>
                    <Field label="Section title" changed={!before || before.title !== s.title}>
                      {(a) => <input {...a} value={s.title} onChange={(e) => item.update((d) => { d.sections[i].title = e.target.value.replace(/\n/g, ' ') })} />}
                    </Field>
                  </div>
                  <button type="button" className="xa-icon-btn" style={{ alignSelf: 'flex-end' }} aria-label={`Remove section ${s.title}`}
                    onClick={() => item.update((d) => { d.sections.splice(i, 1) })}><Icon name="trash" size={16} /></button>
                </div>
                <Field label="Text" changed={!before || before.body !== s.body}
                  hint={/\{[a-z_]+\}/.test(s.body) ? 'Words in curly brackets, like {language_name}, are filled in by XO for each visitor. Keep them.' : undefined}>
                  {(a) => <textarea {...a} rows={Math.min(14, Math.max(4, s.body.split('\n').length + 1))} value={s.body}
                    onChange={(e) => item.update((d) => { d.sections[i].body = e.target.value })} />}
                </Field>
              </div>
            )
          })}
        </div>
      </Card>
    </>
  )
}

function Journeys({ item }) {
  const journeys = item.working.journeys || []
  const edit = (fn) => item.update((d) => { d.journeys = d.journeys || []; fn(d.journeys) })
  return (
    <Card title="Guided journeys" subtitle="Step-by-step flows XO follows for common goals, asking one question at a time (PRD §8)."
      actions={journeys.length > 0 && <Button variant="ghost" size="sm" icon="plus" onClick={() => edit((j) => j.push({ title: 'New journey', steps: [''] }))}>Add journey</Button>}>
      {journeys.length === 0 ? (
        <EmptyState icon="compass" title="No guided journeys yet" action={(
          <div className="xa-row" style={{ justifyContent: 'center' }}>
            {JOURNEY_TEMPLATES.map((t) => <Button key={t.title} variant="ghost" size="sm" onClick={() => edit((j) => j.push(JSON.parse(JSON.stringify(t))))}>Start from “{t.title}”</Button>)}
            <Button size="sm" icon="plus" onClick={() => edit((j) => j.push({ title: 'New journey', steps: [''] }))}>Blank journey</Button>
          </div>
        )}>XO currently follows the property and mortgage guidance in its instructions. Add a journey to spell out the exact steps.</EmptyState>
      ) : (
        <div className="xa-stack">
          {journeys.map((j, ji) => (
            <div key={ji} className="xa-card" style={{ boxShadow: 'none', background: 'var(--xa-surface-2)' }}>
              <div className="xa-row" style={{ flexWrap: 'nowrap', marginBlockEnd: 12 }}>
                <div style={{ flex: 1 }}>
                  <Field label="Journey">{(a) => <input {...a} value={j.title} onChange={(e) => edit((js) => { js[ji].title = e.target.value })} />}</Field>
                </div>
                <button type="button" className="xa-icon-btn" style={{ alignSelf: 'flex-end' }} aria-label={`Remove journey ${j.title}`}
                  onClick={() => edit((js) => { js.splice(ji, 1) })}><Icon name="trash" size={16} /></button>
              </div>
              <ol className="xa-stack-sm" style={{ listStyle: 'none' }}>
                {j.steps.map((step, si) => (
                  <li key={si} className="xa-row" style={{ flexWrap: 'nowrap' }}>
                    <span className="xa-history-v" aria-hidden="true">{si + 1}</span>
                    <label className="xa-sr" htmlFor={`j${ji}s${si}`}>Step {si + 1}</label>
                    <input id={`j${ji}s${si}`} value={step} onChange={(e) => edit((js) => { js[ji].steps[si] = e.target.value })} />
                    <button type="button" className="xa-icon-btn" aria-label={`Move step ${si + 1} up`} disabled={si === 0}
                      onClick={() => edit((js) => { const s = js[ji].steps; [s[si - 1], s[si]] = [s[si], s[si - 1]] })}><span style={{ display: 'inline-flex', transform: 'rotate(180deg)' }}><Icon name="chevronDown" size={15} /></span></button>
                    <button type="button" className="xa-icon-btn" aria-label={`Remove step ${si + 1}`}
                      onClick={() => edit((js) => { js[ji].steps.splice(si, 1) })}><Icon name="close" size={15} /></button>
                  </li>
                ))}
              </ol>
              <Button variant="quiet" size="sm" icon="plus" onClick={() => edit((js) => { js[ji].steps.push('') })}>Add step</Button>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function Tone({ item }) {
  const tones = item.working.tone_by_language || {}
  return (
    <Card title="Tone by language" subtitle="Optional guidance used only when XO talks in that language, for example how formal to be. Leave empty to keep the default." flush>
      <div className="xa-table-wrap">
        <table className="xa-table">
          <thead><tr><th scope="col">Language</th><th scope="col">Tone guidance</th></tr></thead>
          <tbody>
            {languages.map((l) => (
              <tr key={l.code}>
                <td style={{ width: 180 }}><strong>{l.name}</strong><div className="xa-small xa-muted">{l.native}</div></td>
                <td>
                  <label className="xa-sr" htmlFor={`tone-${l.code}`}>Tone for {l.name}</label>
                  <input id={`tone-${l.code}`} value={tones[l.code] || ''} placeholder="Default tone"
                    onChange={(e) => item.update((d) => {
                      d.tone_by_language = { ...(d.tone_by_language || {}) }
                      if (e.target.value) d.tone_by_language[l.code] = e.target.value
                      else delete d.tone_by_language[l.code]
                    })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function Banned({ item }) {
  const topics = item.working.banned_topics || []
  const edit = (fn) => item.update((d) => { d.banned_topics = d.banned_topics || []; fn(d.banned_topics) })
  const add = () => edit((t) => t.push({ name: '', keywords: [], reply: { en: 'I can’t help with that. I can help with UAE property, mortgages or XOTO services.' } }))
  return (
    <Card title="Banned topics" subtitle="Messages that mention a keyword get your fixed reply. XO checks this before the AI runs, so it is a firm block."
      actions={topics.length > 0 && <Button variant="ghost" size="sm" icon="plus" onClick={add}>Add topic</Button>}>
      {topics.length === 0 ? (
        <EmptyState icon="shield" title="No banned topics" action={<Button size="sm" icon="plus" onClick={add}>Add a topic</Button>}>
          XO already declines anything outside UAE property, mortgages and XOTO services. Add a topic to block it completely, with your own reply.
        </EmptyState>
      ) : (
        <div className="xa-stack">
          {topics.map((t, i) => (
            <div key={i} className="xa-card" style={{ boxShadow: 'none', background: 'var(--xa-surface-2)' }}>
              <div className="xa-fields">
                <Field label="Topic">{(a) => <input {...a} value={t.name} placeholder="e.g. Cryptocurrency" onChange={(e) => edit((x) => { x[i].name = e.target.value })} />}</Field>
              </div>
              <div className="xa-stack-sm" style={{ marginBlockStart: 14 }}>
                <Field label="Keywords" hint="Whole words, any language. Press Enter after each one.">
                  {(a) => <TagInput {...a} value={t.keywords} placeholder="bitcoin, crypto, عملة رقمية" onChange={(v) => edit((x) => { x[i].keywords = v })} />}
                </Field>
                <Field label="Reply in English" hint="Used for every language without its own reply.">
                  {(a) => <textarea {...a} rows={2} value={t.reply?.en || ''} onChange={(e) => edit((x) => { x[i].reply = { ...x[i].reply, en: e.target.value } })} />}
                </Field>
                <details>
                  <summary className="xa-small" style={{ cursor: 'pointer' }}>Replies in other languages ({Object.keys(t.reply || {}).filter((k) => k !== 'en').length} set)</summary>
                  <div className="xa-fields" style={{ marginBlockStart: 12 }}>
                    {languages.filter((l) => l.code !== 'en').map((l) => (
                      <Field key={l.code} label={l.name}>
                        {(a) => <input {...a} dir={l.dir} value={t.reply?.[l.code] || ''} placeholder="Uses the English reply"
                          onChange={(e) => edit((x) => { const r = { ...(x[i].reply || {}) }; if (e.target.value) r[l.code] = e.target.value; else delete r[l.code]; x[i].reply = r })} />}
                      </Field>
                    ))}
                  </div>
                </details>
              </div>
              <div style={{ marginBlockStart: 12 }}>
                <Button variant="danger-ghost" size="sm" icon="trash" onClick={() => edit((x) => { x.splice(i, 1) })}>Remove topic</Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function Replies({ item }) {
  const [code, setCode] = useState('en')
  const lang = languages.find((l) => l.code === code)
  const msgs = item.working[code]
  const live = item.published.data[code]
  const english = item.published.data.en
  return (
    <Card title="Canned replies" subtitle="Fixed texts XO shows without the AI. Each language has its own."
      actions={(
        <>
          <label className="xa-sr" htmlFor="reply-lang">Language</label>
          <select id="reply-lang" value={code} onChange={(e) => setCode(e.target.value)}>
            {languages.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
          </select>
        </>
      )}>
      <div className="xa-stack-sm">
        {Object.keys(msgs).map((key) => (
          <Field key={key} label={MESSAGE_LABELS[key] || key} changed={msgs[key] !== live[key]}
            hint={code !== 'en' ? `English: ${english[key]}` : undefined}>
            {(a) => <input {...a} dir={lang?.dir} value={msgs[key]} maxLength={500} onChange={(e) => item.update((d) => { d[code][key] = e.target.value })} />}
          </Field>
        ))}
      </div>
    </Card>
  )
}

function ReplyChanges({ item }) {
  const changes = []
  Object.entries(item.working).forEach(([code, msgs]) => Object.entries(msgs).forEach(([key, text]) => {
    const before = item.published.data[code]?.[key]
    if (before !== text) changes.push({ code, key, before, text })
  }))
  if (!changes.length) return <p className="xa-muted">No changes.</p>
  return (
    <div className="xa-stack-sm">
      <p className="xa-field-label">Changed replies</p>
      {changes.map((c) => (
        <div key={`${c.code}-${c.key}`} className="xa-small">
          <Badge>{c.code.toUpperCase()}</Badge> <strong>{MESSAGE_LABELS[c.key] || c.key}</strong>
          <div className="xa-diff" style={{ marginBlockStart: 6 }}><div className="is-del">− {c.before}</div><div className="is-add">+ {c.text}</div></div>
        </div>
      ))}
    </div>
  )
}
