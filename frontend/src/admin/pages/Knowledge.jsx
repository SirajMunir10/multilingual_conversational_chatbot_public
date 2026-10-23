'use client'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { adminApi, errorMessage } from '../lib/api'
import Icon from '../components/Icon'
import { Badge, Button, Card, EmptyState, Field, Modal, Notice, PageHeader, Switch, TagInput, Tabs, formatDateTime, timeAgo, useToast } from '../components/ui'

const SOURCES = { builtin: 'Built-in', manual: 'Written here', review: 'From a review', upload: 'Uploaded file', web: 'Web page' }
const ACTIONS = { builtin: 'Built-in version', published: 'Published', retired: 'Removed from XO', restored: 'Restored', reviewed: 'Marked as reviewed' }
const BLANK = { type: 'article', title: '', short_answer: '', detail: '', tags: [], utterances: [], follow_up_prompts: [], status: 'ACTIVE', disclaimer_flag: 'NO', review_by: null }

const kbError = (e) => (e.code === 'not_found' ? 'This entry no longer exists.' : errorMessage(e))

export default function Knowledge({ param, onNavigate }) {
  const [tab, setTab] = useState('entries')
  const [drafts, setDrafts] = useState(null)
  const loadDrafts = useCallback(() => adminApi('/kb/drafts').then(setDrafts).catch(() => setDrafts([])), [])
  useEffect(() => { loadDrafts() }, [loadDrafts])

  if (param) return <EntryEditor key={param} id={decodeURIComponent(param)} onNavigate={onNavigate} onBack={() => onNavigate('knowledge')} />
  return (
    <div className="xa-stack-sm">
      <PageHeader title="Knowledge base" subtitle="What XO knows and answers from. Every change is live from the next question, with a version you can restore."
        actions={<Button icon="plus" onClick={() => onNavigate('knowledge/new')}>New entry</Button>} />
      <Tabs label="Knowledge base sections" value={tab} onChange={setTab} tabs={[
        { id: 'entries', label: 'Entries' }, { id: 'drafts', label: `Drafts${drafts?.length ? ` · ${drafts.length}` : ''}` },
        { id: 'upload', label: 'Upload' }, { id: 'web', label: 'Web pages' }]} />
      {tab === 'entries' && <EntryList onOpen={(id) => onNavigate(`knowledge/${encodeURIComponent(id)}`)} />}
      {tab === 'drafts' && <Drafts drafts={drafts} reload={loadDrafts} onUse={(id) => onNavigate(`knowledge/draft-${id}`)} />}
      {tab === 'upload' && <Upload onDone={() => setTab('entries')} />}
      {tab === 'web' && <WebPages />}
    </div>
  )
}

// ---- Entries ----

function EntryList({ onOpen }) {
  const [filters, setFilters] = useState({ q: '', type: '', status: 'live', tag: '' })
  const [search, setSearch] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const params = new URLSearchParams(Object.entries(filters).filter(([, v]) => v))
    adminApi(`/kb/articles?${params}`).then((d) => { setData(d); setError(null) }).catch((e) => setError(kbError(e)))
  }, [filters])

  const set = (key, value) => setFilters((f) => ({ ...f, [key]: value }))
  const counts = data?.counts
  const segments = [['live', 'Live', counts?.live], ['due', 'Due for review', counts?.due], ['retired', 'Removed', counts?.retired]]

  return (
    <div className="xa-editor">
      <div className="xa-stack-sm">
        <div className="xa-segmented" role="radiogroup" aria-label="Show">
          {segments.map(([id, label, n]) => (
            <button key={id} type="button" role="radio" aria-checked={filters.status === id} className={filters.status === id ? 'is-active' : ''}
              onClick={() => set('status', id)}>
              {label}{n !== undefined && <span className={`xa-count${id === 'due' && counts?.overdue ? ' is-alert' : ''}`}>{n}</span>}
            </button>
          ))}
        </div>
        <form className="xa-filterbar" role="search" onSubmit={(e) => { e.preventDefault(); set('q', search.trim()) }}>
          <label className="xa-sr" htmlFor="kb-search">Search entries</label>
          <input id="kb-search" type="search" placeholder="Search titles, answers and tags" value={search}
            onChange={(e) => { setSearch(e.target.value); if (!e.target.value) set('q', '') }} />
          <label className="xa-sr" htmlFor="kb-type">Type</label>
          <select id="kb-type" value={filters.type} onChange={(e) => set('type', e.target.value)}>
            <option value="">Articles and glossary</option><option value="article">Articles</option><option value="glossary">Glossary terms</option>
          </select>
          {data?.tags?.length > 0 && (
            <>
              <label className="xa-sr" htmlFor="kb-tag">Tag</label>
              <select id="kb-tag" value={filters.tag} onChange={(e) => set('tag', e.target.value)}>
                <option value="">Any tag</option>{data.tags.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </>
          )}
          <Button type="submit" variant="ghost" icon="search">Search</Button>
        </form>
        {error && <Notice tone="error">{error}</Notice>}
        {filters.status === 'due' && counts?.overdue > 0 && (
          <Notice tone="warning">{counts.overdue} {counts.overdue === 1 ? 'entry is' : 'entries are'} past the review date. Open each one, check it is still correct, and mark it reviewed or update it.</Notice>
        )}
        <Card flush title={data ? `${data.items.length} ${data.items.length === 1 ? 'entry' : 'entries'}` : 'Entries'}
          subtitle={counts && `${counts.indexed} entries are searchable by XO right now`}>
          {data && data.items.length === 0 && (
            <EmptyState icon="book" title="Nothing matches">Try other words, or clear the filters.</EmptyState>
          )}
          {data && data.items.length > 0 && (
            <div className="xa-table-wrap">
              <table className="xa-table xa-table-click">
                <thead><tr><th scope="col">Entry</th><th scope="col">Tags</th><th scope="col">Last change</th><th scope="col">Review</th></tr></thead>
                <tbody>
                  {data.items.map((a) => (
                    <tr key={a.id} onClick={() => onOpen(a.id)}>
                      <td className="xa-kb-entry">
                        <a href={`#/knowledge/${encodeURIComponent(a.id)}`} onClick={(e) => { e.preventDefault(); onOpen(a.id) }}>{a.title}</a>
                        {a.type === 'glossary' && <Badge>Glossary</Badge>}
                        {a.status === 'PARTIALLY_ACTIVE' && <Badge tone="info">Educational only</Badge>}
                        <p>{a.short_answer}</p>
                      </td>
                      <td>{a.tags.slice(0, 3).map((t) => <Badge key={t} tone="muted">{t}</Badge>)}</td>
                      <td className="xa-small xa-nowrap">
                        {a.version === 0 ? <span className="xa-muted">Built-in</span> : <>{timeAgo(a.published_at)}<div className="xa-muted">{a.published_by}</div></>}
                      </td>
                      <td className="xa-nowrap">
                        {a.status === 'RETIRED' ? <Badge tone="muted">Removed</Badge>
                          : a.overdue ? <Badge tone="warning" icon="history">Overdue</Badge>
                            : a.due ? <Badge tone="info">Due soon</Badge>
                              : <span className="xa-small xa-muted">{a.review_by ? `By ${a.review_by}` : 'No date'}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
      <aside className="xa-editor-side"><TryQuestion /></aside>
    </div>
  )
}

function TryQuestion() {
  const [q, setQ] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const ask = async (e) => {
    e.preventDefault()
    if (!q.trim()) return
    setBusy(true)
    try { setResult(await adminApi('/kb/test-question', { method: 'POST', body: { question: q.trim() } })) } catch (err) { setResult({ error: errorMessage(err) }) }
    setBusy(false)
  }
  return (
    <Card title="Try a question" subtitle="See which entries XO would answer from, and how close each match is.">
      <form className="xa-row" style={{ flexWrap: 'nowrap' }} onSubmit={ask}>
        <label className="xa-sr" htmlFor="kb-try">Question</label>
        <input id="kb-try" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Can I buy in Dubai as an expat?" />
        <Button type="submit" icon="arrowRight" busy={busy} disabled={!q.trim()} aria-label="Search" />
      </form>
      {result?.error && <Notice tone="error">{result.error}</Notice>}
      {result?.matches && (
        <div className="xa-stack-sm" style={{ marginBlockStart: 16 }}>
          {!result.answered && <Notice tone="warning">No entry is close enough. XO would say it does not know and offer an advisor.</Notice>}
          <ul className="xa-barlist">
            {result.matches.map((m) => (
              <li key={m.id}>
                <div className="xa-barlist-text">
                  <span>{m.title} {m.used && <Badge tone="ok">Used</Badge>}</span>
                  <span className="xa-barlist-value">{Math.round(m.score * 100)}</span>
                </div>
                <div className="xa-barlist-track"><span className={`xa-barlist-fill${m.used ? '' : ' is-faint'}`} style={{ width: `${Math.max(2, m.score * 100)}%` }} /></div>
              </li>
            ))}
          </ul>
          <p className="xa-small xa-muted">Entries scoring {Math.round(result.threshold * 100)} or more are used. Each try costs one small search.</p>
        </div>
      )}
    </Card>
  )
}

// ---- One entry ----

function EntryEditor({ id, onBack, onNavigate }) {
  const toast = useToast()
  const isNew = id === 'new' || id.startsWith('draft-')
  const draftId = id.startsWith('draft-') ? Number(id.slice(6)) : null
  const [entry, setEntry] = useState(null)
  const [form, setForm] = useState(null)
  const [base, setBase] = useState(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [confirm, setConfirm] = useState(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      if (id === 'new') { setEntry(null); setForm(BLANK); setBase(BLANK); return }
      if (draftId) {
        const draft = (await adminApi('/kb/drafts')).find((d) => d.id === draftId)
        if (!draft) { setError('This draft was already used or dismissed.'); return }
        const start = { ...BLANK, title: draft.title, short_answer: draft.answer, utterances: [draft.question] }
        setEntry(null); setForm(start); setBase(BLANK); setNote(`Corrected answer from a conversation review by ${draft.created_by}`)
        return
      }
      const e = await adminApi(`/kb/articles/${encodeURIComponent(id)}`)
      setEntry(e); setForm(e.data); setBase(e.data); setNote('')
    } catch (e) { setError(kbError(e)) }
  }, [id, draftId])
  useEffect(() => { load() }, [load])

  const changed = useMemo(() => form && base && JSON.stringify(form) !== JSON.stringify(base), [form, base])
  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }))
  const retired = entry?.status === 'RETIRED'

  const publish = async (e) => {
    e?.preventDefault()
    setBusy(true); setError(null)
    try {
      if (isNew) {
        const saved = await adminApi('/kb/articles', { method: 'POST', body: { data: form, note, draft_id: draftId } })
        toast(`Published. XO answers from “${saved.data.title}” from the next question.`)
        onNavigate(`knowledge/${encodeURIComponent(saved.article_id)}`)
      } else {
        await adminApi(`/kb/articles/${encodeURIComponent(id)}`, { method: 'PUT', body: { data: form, note, base_version: entry.version } })
        toast(`Published version ${entry.version + 1}.`)
        await load()
      }
    } catch (err) { setError(kbError(err)) }
    setBusy(false)
  }

  const act = async (path, body, message) => {
    setBusy(true); setError(null)
    try { await adminApi(`/kb/articles/${encodeURIComponent(id)}/${path}`, { method: 'POST', body }); toast(message); setConfirm(null); await load() } catch (err) { setError(kbError(err)); setConfirm(null) }
    setBusy(false)
  }

  if (!form || (!isNew && !entry)) return (
    <div className="xa-stack-sm">
      <PageHeader title="Knowledge entry" crumb={<a href="#/knowledge" onClick={(e) => { e.preventDefault(); onBack() }}><Icon name="chevronRight" size={13} />Knowledge base</a>} />
      {error ? <Notice tone="error">{error}</Notice> : <div className="xa-boot" aria-busy="true"><span className="xa-spinner" /></div>}
    </div>
  )

  const glossary = form.type === 'glossary'
  return (
    <div className="xa-stack-sm">
      <PageHeader crumb={<a href="#/knowledge" onClick={(e) => { e.preventDefault(); onBack() }}><Icon name="chevronRight" size={13} />Knowledge base</a>}
        title={isNew ? (draftId ? 'New entry from a review' : 'New entry') : base.title}
        subtitle={isNew ? 'Write the answer the way XO should give it. XO uses the short answer first and the detail when asked for more.'
          : `${SOURCES[entry.source] || 'Entry'} · version ${entry.version}${entry.version ? ` · ${timeAgo(entry.published_at)} by ${entry.published_by}` : ''}`}
        actions={retired && <Badge tone="muted">Removed from XO</Badge>} />
      {error && <Notice tone="error">{error}</Notice>}
      {retired && <Notice tone="warning">XO does not use this entry. Restore a version from the history to bring it back.</Notice>}

      <div className="xa-editor">
        <form className="xa-stack" onSubmit={publish} id="kb-entry-form">
          <Card title="Answer">
            <fieldset className="xa-stack-sm" disabled={retired} style={{ border: 0, padding: 0, margin: 0 }}>
              {isNew && (
                <Field label="Type">
                  {(a) => (
                    <select {...a} value={form.type} onChange={(e) => set('type')(e.target.value)}>
                      <option value="article">Article: a question XO answers</option>
                      <option value="glossary">Glossary term: a word XO explains</option>
                    </select>
                  )}
                </Field>
              )}
              <Field label={glossary ? 'Term' : 'Title'} changed={!isNew && form.title !== base.title} hint={glossary ? undefined : 'Phrase it like the question visitors ask.'}>
                {(a) => <input {...a} value={form.title} maxLength={200} onChange={(e) => set('title')(e.target.value)} placeholder={glossary ? 'e.g. Oqood' : 'e.g. Can I get a Golden Visa by buying property?'} />}
              </Field>
              <Field label={glossary ? 'Definition' : 'Short answer'} changed={!isNew && form.short_answer !== base.short_answer}>
                {(a) => <textarea {...a} rows={3} value={form.short_answer} maxLength={1500} onChange={(e) => set('short_answer')(e.target.value)} />}
              </Field>
              {!glossary && (
                <Field label="Detail" changed={!isNew && form.detail !== base.detail} hint="Facts, figures and steps XO can add when the visitor wants more.">
                  {(a) => <textarea {...a} rows={8} value={form.detail} maxLength={12000} onChange={(e) => set('detail')(e.target.value)} />}
                </Field>
              )}
            </fieldset>
          </Card>
          <Card title="Finding and follow-up" subtitle="Help XO match this entry to the way people really ask.">
            <fieldset className="xa-stack-sm" disabled={retired} style={{ border: 0, padding: 0, margin: 0 }}>
              <Field label="Example questions" changed={!isNew && JSON.stringify(form.utterances) !== JSON.stringify(base.utterances)} hint="Any language. Press Enter after each one.">
                {(a) => <TagInput {...a} value={form.utterances} onChange={set('utterances')} placeholder="How do I…" />}
              </Field>
              {!glossary && (
                <Field label="Follow-up suggestions" changed={!isNew && JSON.stringify(form.follow_up_prompts) !== JSON.stringify(base.follow_up_prompts)} hint="Up to 8.">
                  {(a) => <TagInput {...a} value={form.follow_up_prompts} onChange={set('follow_up_prompts')} placeholder="What fees should I budget for?" />}
                </Field>
              )}
              <Field label="Tags" changed={!isNew && JSON.stringify(form.tags) !== JSON.stringify(base.tags)}>
                {(a) => <TagInput {...a} value={form.tags} onChange={set('tags')} placeholder="fees, dubai, visa" />}
              </Field>
              {!glossary && (
                <div className="xa-fields">
                  <Switch showLabel checked={form.status === 'PARTIALLY_ACTIVE'} label="Educational only" hint="XO explains in general and uses the calculators for personal figures."
                    onChange={(v) => set('status')(v ? 'PARTIALLY_ACTIVE' : 'ACTIVE')} />
                  <Switch showLabel checked={form.disclaimer_flag === 'YES'} label="Add the legal disclaimer" hint="A short “general guidance, not advice” clause."
                    onChange={(v) => set('disclaimer_flag')(v ? 'YES' : 'NO')} />
                </div>
              )}
              <Field label="Review by" hint="You are reminded when the date is near. Six months from today if left empty.">
                {(a) => <input {...a} type="date" value={form.review_by || ''} onChange={(e) => set('review_by')(e.target.value || null)} style={{ maxWidth: 220 }} />}
              </Field>
            </fieldset>
          </Card>
        </form>

        <aside className="xa-editor-side">
          {!isNew && (
            <Card title="Status">
              <ul className="xa-check-list">
                <li><Icon name={retired ? 'close' : 'checkCircle'} size={16} />{retired ? 'Not used by XO' : 'Live: XO answers from it'}</li>
                <li><Icon name="history" size={16} />{entry.data.review_by ? `${entry.overdue ? 'Review was due' : 'Review by'} ${entry.data.review_by}` : 'No review date'}
                  {entry.data.last_reviewed && <span className="xa-muted"> (last {entry.data.last_reviewed})</span>}</li>
                {entry.data.source?.url && <li><Icon name="link" size={16} /><a href={entry.data.source.url} target="_blank" rel="noreferrer noopener">{entry.data.source.url}</a></li>}
                {entry.data.source?.file && <li><Icon name="file" size={16} />{entry.data.source.file}</li>}
              </ul>
              {!retired && (
                <div className="xa-row" style={{ marginBlockStart: 14 }}>
                  <Button variant="ghost" size="sm" icon="checkCircle" disabled={changed || busy} onClick={() => act('reviewed', undefined, 'Marked as reviewed. Next review in six months.')}>Still correct</Button>
                  <Button variant="danger-ghost" size="sm" icon="trash" disabled={busy} onClick={() => setConfirm({ kind: 'retire' })}>Remove from XO</Button>
                </div>
              )}
            </Card>
          )}
          {!isNew && (
            <Card title="History" subtitle="Restoring publishes that version again as a new one.">
              <ol className="xa-history">
                {entry.versions.map((v) => (
                  <li key={v.version} className={v.version === entry.version ? 'is-live' : ''}>
                    <span className="xa-history-v">{v.version}</span>
                    <div className="xa-history-body">
                      <strong>{ACTIONS[v.action] || v.action}</strong>
                      <div className="xa-small xa-muted">{v.published_at ? `${formatDateTime(v.published_at)} · ${v.published_by}` : 'From the original knowledge base'}</div>
                      {v.note && <div className="xa-small">{v.note}</div>}
                    </div>
                    {v.version !== entry.version && v.data?.status !== 'RETIRED' && (
                      <Button variant="quiet" size="sm" icon="undo" onClick={() => setConfirm({ kind: 'restore', version: v.version })}>Restore</Button>
                    )}
                  </li>
                ))}
              </ol>
            </Card>
          )}
          {isNew && (
            <Card title="Good entries">
              <ul className="xa-check-list">
                <li><Icon name="check" size={16} />One question per entry, answered in the first sentence.</li>
                <li><Icon name="check" size={16} />Figures with their unit and emirate, e.g. “4% DLD fee in Dubai”.</li>
                <li><Icon name="check" size={16} />Several example questions, including other languages.</li>
              </ul>
            </Card>
          )}
        </aside>
      </div>

      {(changed || (isNew && form.title)) && !retired && (
        <div className="xa-publishbar" role="region" aria-label="Unpublished changes">
          <div className="xa-publishbar-text">
            <strong>{isNew ? 'New entry, not published' : 'Unpublished changes'}</strong>
            <label className="xa-sr" htmlFor="kb-note">What changed and why</label>
            {error && <small className="xa-publishbar-error" role="alert">{error}</small>}
            <input id="kb-note" className="xa-publishbar-note" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="What changed and why (shown in the history)" />
          </div>
          {!isNew && <Button variant="ghost" size="sm" onClick={() => setForm(base)}>Discard</Button>}
          <Button size="sm" type="submit" form="kb-entry-form" busy={busy}>Publish</Button>
        </div>
      )}

      {confirm && (
        <Modal title={confirm.kind === 'retire' ? 'Remove this entry from XO?' : `Restore version ${confirm.version}?`}
          subtitle={confirm.kind === 'retire' ? 'XO stops answering from it at once. It stays in the history and can be restored.' : 'Its text becomes the live version from the next question.'}
          onClose={() => setConfirm(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
            {confirm.kind === 'retire'
              ? <Button variant="danger" busy={busy} onClick={() => act('retire', { note }, 'Removed. XO no longer answers from this entry.')}>Remove</Button>
              : <Button busy={busy} onClick={() => act('restore', { version: confirm.version, note: `Restored version ${confirm.version}` }, `Restored version ${confirm.version}.`)}>Restore</Button>}
          </>}>
          {confirm.kind === 'retire' && (
            <Field label="Reason (optional)">{(a) => <input {...a} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Replaced by the 2027 fee entry" />}</Field>
          )}
        </Modal>
      )}
    </div>
  )
}

// ---- Drafts from conversation review ----

function Drafts({ drafts, reload, onUse }) {
  const toast = useToast()
  const dismiss = async (d) => {
    try { await adminApi(`/kb/drafts/${d.id}/dismiss`, { method: 'POST' }); toast('Draft dismissed.'); reload() } catch (e) { toast(errorMessage(e), 'error') }
  }
  if (!drafts) return <div className="xa-boot" aria-busy="true"><span className="xa-spinner" /></div>
  if (!drafts.length) return (
    <Card><EmptyState icon="message" title="No drafts waiting">When a reviewer corrects one of XO’s replies under Conversations, the corrected answer arrives here to publish.</EmptyState></Card>
  )
  return (
    <div className="xa-stack-sm">
      {drafts.map((d) => (
        <Card key={d.id} title={d.title} subtitle={`${d.created_by} · ${timeAgo(d.created_at)}${d.language !== 'en' ? ` · ${d.language.toUpperCase()}` : ''}`}
          actions={<>
            <Button variant="quiet" size="sm" onClick={() => dismiss(d)}>Dismiss</Button>
            <Button size="sm" icon="arrowRight" onClick={() => onUse(d.id)}>Edit and publish</Button>
          </>}>
          <dl className="xa-kb-draft">
            <dt>Visitor asked</dt><dd>{d.question}</dd>
            <dt>Corrected answer</dt><dd>{d.answer}</dd>
          </dl>
        </Card>
      ))}
    </div>
  )
}

// ---- Upload ----

function readBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(new Error('read_failed'))
    reader.readAsDataURL(file)
  })
}

function Upload({ onDone }) {
  const toast = useToast()
  const input = useRef(null)
  const [result, setResult] = useState(null)
  const [picked, setPicked] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [drag, setDrag] = useState(false)

  const read = async (file) => {
    if (!file) return
    setError(null); setResult(null)
    if (file.size > 8 * 1024 * 1024) { setError('Files can be up to 8 MB.'); return }
    setBusy(true)
    try {
      const r = await adminApi('/kb/upload', { method: 'POST', body: { filename: file.name, content_base64: await readBase64(file) } })
      setResult(r)
      setPicked(Object.fromEntries(r.entries.map((_, i) => [i, true])))
    } catch (e) { setError(errorMessage(e)) }
    setBusy(false)
  }

  const chosen = result ? result.entries.filter((_, i) => picked[i]) : []
  const publish = async () => {
    setBusy(true); setError(null)
    try {
      const r = await adminApi('/kb/articles/bulk', { method: 'POST', body: { entries: chosen, filename: result.filename, note: `Imported from ${result.filename}` } })
      toast(`${r.saved} ${r.saved === 1 ? 'entry' : 'entries'} published from ${result.filename}.`)
      onDone()
    } catch (e) { setError(errorMessage(e)) }
    setBusy(false)
  }
  const editTitle = (i, title) => setResult((r) => ({ ...r, entries: r.entries.map((e, j) => (j === i ? { ...e, title } : e)) }))

  return (
    <div className="xa-stack-sm">
      {error && <Notice tone="error">{error}</Notice>}
      {!result && (
        <label className={`xa-dropzone${drag ? ' is-over' : ''}`} aria-busy={busy}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); read(e.dataTransfer.files?.[0]) }}>
          <input ref={input} type="file" accept=".pdf,.docx,.csv" className="xa-sr" onChange={(e) => { read(e.target.files?.[0]); e.target.value = '' }} />
          {busy ? <span className="xa-spinner" /> : <Icon name="upload" size={26} />}
          <strong>{busy ? 'Reading the file…' : 'Drop a PDF, Word or CSV file, or choose one'}</strong>
          <span>Up to 8 MB. You review every entry before anything is published.</span>
          <span className="xa-small xa-muted">CSV: columns “title” and “answer”, optional “detail”, “tags” and “type”.</span>
        </label>
      )}
      {result && (
        <>
          {result.removed > 0 && (
            <Notice tone="warning">{result.removed} {result.removed === 1 ? 'sentence was' : 'sentences were'} removed because {result.removed === 1 ? 'it reads' : 'they read'} like instructions to an AI.</Notice>
          )}
          {result.truncated && <Notice tone="info">Only the first 200 entries were read. Split the file to import the rest.</Notice>}
          <Card flush title={`${result.entries.length} ${result.entries.length === 1 ? 'entry' : 'entries'} found in ${result.filename}`}
            subtitle="Untick anything XO should not use, and fix titles so they read like questions."
            actions={<Button variant="quiet" size="sm" onClick={() => setResult(null)}>Choose another file</Button>}>
            <div className="xa-table-wrap">
              <table className="xa-table">
                <thead><tr><th scope="col" style={{ width: 44 }}><span className="xa-sr">Use</span></th><th scope="col">Title</th><th scope="col">Answer</th></tr></thead>
                <tbody>
                  {result.entries.map((e, i) => (
                    <tr key={i} className={picked[i] ? '' : 'is-off'}>
                      <td><input type="checkbox" checked={!!picked[i]} aria-label={`Use “${e.title}”`} onChange={(ev) => setPicked((p) => ({ ...p, [i]: ev.target.checked }))} /></td>
                      <td style={{ minWidth: 220 }}>
                        <label className="xa-sr" htmlFor={`up-${i}`}>Title</label>
                        <input id={`up-${i}`} value={e.title} onChange={(ev) => editTitle(i, ev.target.value)} />
                        {e.type === 'glossary' && <Badge>Glossary</Badge>}
                      </td>
                      <td className="xa-small xa-kb-preview">{e.short_answer}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="xa-row" style={{ justifyContent: 'flex-end' }}>
            <Button icon="upload" busy={busy} disabled={!chosen.length} onClick={publish}>Publish {chosen.length} {chosen.length === 1 ? 'entry' : 'entries'}</Button>
          </div>
        </>
      )}
    </div>
  )
}

// ---- Web pages ----

const SOURCE_STATUS = { new: ['Added', 'info'], updated: ['Updated', 'ok'], unchanged: ['No changes', 'muted'], failed: ['Last refresh failed', 'bad'] }

function WebPages() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [url, setUrl] = useState('')
  const [domains, setDomains] = useState([])
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [removing, setRemoving] = useState(null)

  const load = useCallback(() => adminApi('/kb/sources').then((d) => { setData(d); setDomains(d.allowed_domains) }).catch((e) => setError(errorMessage(e))), [])
  useEffect(() => { load() }, [load])

  const run = async (key, fn) => {
    setBusy(key); setError(null)
    try { await fn() } catch (e) { setError(errorMessage(e)) }
    setBusy(null)
  }
  const add = (e) => {
    e.preventDefault()
    run('add', async () => {
      const s = await adminApi('/kb/sources', { method: 'POST', body: { url: url.trim() } })
      toast(`Added ${s.article_ids.length} ${s.article_ids.length === 1 ? 'entry' : 'entries'} from ${s.title}.${s.removed ? ` ${s.removed} suspicious ${s.removed === 1 ? 'sentence' : 'sentences'} removed.` : ''}`)
      setUrl(''); await load()
    })
  }
  const refresh = (s) => run(`r${s.id}`, async () => {
    const r = await adminApi(`/kb/sources/${s.id}/refresh`, { method: 'POST' })
    toast(r.last_status === 'failed' ? `Could not refresh: ${r.last_error}` : r.last_status === 'updated' ? 'Updated from the website.' : 'No changes on the page.', r.last_status === 'failed' ? 'error' : undefined)
    await load()
  })
  const remove = (s) => run(`d${s.id}`, async () => {
    await adminApi(`/kb/sources/${s.id}`, { method: 'DELETE' })
    toast('Page removed. XO no longer answers from it.'); setRemoving(null); await load()
  })
  const saveDomains = () => run('domains', async () => {
    const r = await adminApi('/kb/sources/domains', { method: 'PUT', body: { domains } })
    setDomains(r.allowed_domains); toast('Approved websites saved.'); await load()
  })

  if (!data) return error ? <Notice tone="error">{error}</Notice> : <div className="xa-boot" aria-busy="true"><span className="xa-spinner" /></div>
  const domainsChanged = JSON.stringify(domains) !== JSON.stringify(data.allowed_domains)

  return (
    <div className="xa-editor">
      <div className="xa-stack-sm">
        {error && <Notice tone="error">{error}</Notice>}
        <Card title="Add a web page" subtitle="XO reads the page, splits it by headings and keeps it up to date every week.">
          <form className="xa-row" style={{ flexWrap: 'nowrap' }} onSubmit={add}>
            <label className="xa-sr" htmlFor="kb-url">Page address</label>
            <input id="kb-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder={`https://${data.allowed_domains[0] || 'xoto.ae'}/…`} />
            <Button type="submit" icon="plus" busy={busy === 'add'} disabled={!url.trim()}>Add page</Button>
          </form>
        </Card>
        <Card flush title="Pages" subtitle={data.sources.length ? 'Refreshed weekly. A failed refresh keeps the last good version live.' : undefined}>
          {data.sources.length === 0 ? (
            <EmptyState icon="globe" title="No web pages yet">Add a page from an approved website and XO will answer from it.</EmptyState>
          ) : (
            <div className="xa-table-wrap">
              <table className="xa-table">
                <thead><tr><th scope="col">Page</th><th scope="col">Entries</th><th scope="col">Last checked</th><th scope="col"><span className="xa-sr">Actions</span></th></tr></thead>
                <tbody>
                  {data.sources.map((s) => {
                    const [label, tone] = SOURCE_STATUS[s.last_status] || SOURCE_STATUS.new
                    return (
                      <tr key={s.id}>
                        <td className="xa-kb-entry">
                          <strong>{s.title || s.url}</strong>
                          <p><a href={s.url} target="_blank" rel="noreferrer noopener">{s.url}</a></p>
                          {s.last_status === 'failed' && <p className="xa-bad-text">{s.last_error}</p>}
                        </td>
                        <td className="xa-small">{s.article_ids.length}</td>
                        <td className="xa-small xa-nowrap">{s.last_fetched_at ? timeAgo(s.last_fetched_at) : 'Never'}<div><Badge tone={tone}>{label}</Badge></div></td>
                        <td className="xa-nowrap" style={{ textAlign: 'end' }}>
                          <Button variant="quiet" size="sm" icon="refresh" busy={busy === `r${s.id}`} onClick={() => refresh(s)}>Refresh</Button>
                          <button type="button" className="xa-icon-btn" aria-label={`Remove ${s.url}`} onClick={() => setRemoving(s)}><Icon name="trash" size={16} /></button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
      <aside className="xa-editor-side">
        <Card title="Approved websites" subtitle="Pages can only come from these sites and their subdomains.">
          {data.can_edit_domains ? (
            <div className="xa-stack-sm">
              <Field label="Websites" hint="Admins only. Press Enter after each one.">
                {(a) => <TagInput {...a} value={domains} onChange={setDomains} placeholder="dubailand.gov.ae" />}
              </Field>
              {domainsChanged && <Button size="sm" busy={busy === 'domains'} onClick={saveDomains}>Save websites</Button>}
            </div>
          ) : (
            <div className="xa-row" style={{ gap: 6 }}>{data.allowed_domains.map((d) => <Badge key={d} icon="globe">{d}</Badge>)}</div>
          )}
          <ul className="xa-check-list xa-small" style={{ marginBlockStart: 16 }}>
            <li><Icon name="shield" size={15} />Secure (https) addresses on public servers only.</li>
            <li><Icon name="shield" size={15} />Sentences that read like instructions to an AI are removed.</li>
          </ul>
        </Card>
      </aside>
      {removing && (
        <Modal title="Remove this page?" subtitle={`XO stops answering from its ${removing.article_ids.length} entries. They stay in the history.`} onClose={() => setRemoving(null)}
          footer={<><Button variant="ghost" onClick={() => setRemoving(null)}>Cancel</Button><Button variant="danger" busy={busy === `d${removing.id}`} onClick={() => remove(removing)}>Remove page</Button></>}>
          <p className="xa-small">{removing.url}</p>
        </Modal>
      )}
    </div>
  )
}
