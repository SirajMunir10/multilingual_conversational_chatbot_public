'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { adminApi, errorMessage } from '../lib/api'
import Icon from './Icon'
import { Badge, Button, Drawer, Field, Modal, Notice, formatDateTime, timeAgo, useToast } from './ui'

const clone = (v) => JSON.parse(JSON.stringify(v))
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

/**
 * One editable configuration item (draft → review → publish, with history). Edits are saved as a draft as you type,
 * so nothing is lost on reload, and nothing reaches visitors until it is published.
 */
export function useConfigItem(name) {
  const toast = useToast()
  const [state, setState] = useState({ loading: true })
  const [working, setWorking] = useState(null)
  const [saving, setSaving] = useState(false)
  const pending = useRef(null)
  const latest = useRef(null)

  const load = useCallback(async () => {
    try {
      const r = await adminApi(`/config/${name}`)
      setState({ loading: false, published: r.published, draft: r.draft, errors: r.draft_errors, stale: r.stale,
        base: r.draft ? r.draft.base_version : r.published.version, savedAt: r.draft?.updated_at, savedBy: r.draft?.updated_by })
      setWorking(clone(r.draft ? r.draft.data : r.published.data))
    } catch (e) {
      setState({ loading: false, error: errorMessage(e) })
    }
  }, [name])

  useEffect(() => { load() }, [load])

  const save = useCallback(async (data, base) => {
    setSaving(true)
    try {
      const r = await adminApi(`/config/${name}/draft`, { method: 'PUT', body: { data, base_version: base } })
      setState((s) => ({ ...s, draft: r.draft, errors: r.draft_errors, savedAt: r.draft.updated_at, savedBy: r.draft.updated_by }))
    } catch (e) {
      toast(errorMessage(e), 'error')
    } finally {
      setSaving(false)
    }
  }, [name, toast])

  /** Changes the working copy (`fn` receives a deep copy) and saves it as a draft shortly after typing stops. */
  const update = useCallback((fn) => {
    setWorking((current) => {
      const next = clone(current)
      fn(next)
      latest.current = next
      clearTimeout(pending.current)
      pending.current = setTimeout(() => { pending.current = null; save(latest.current, state.base) }, 700)
      return next
    })
  }, [save, state.base])

  const flush = useCallback(async () => {
    if (pending.current) {
      clearTimeout(pending.current)
      pending.current = null
      await save(latest.current, state.base)
    }
  }, [save, state.base])

  const publish = useCallback(async (note) => {
    await flush()
    const r = await adminApi(`/config/${name}/publish`, { method: 'POST', body: { note } })
    toast(`Published version ${r.version}. XO uses it from the next message.`)
    await load()
    return r.version
  }, [flush, load, name, toast])

  const discard = useCallback(async () => {
    clearTimeout(pending.current)
    pending.current = null
    await adminApi(`/config/${name}/draft`, { method: 'DELETE' })
    toast('Draft discarded.')
    await load()
  }, [load, name, toast])

  const restore = useCallback(async (version, note) => {
    const r = await adminApi(`/config/${name}/rollback`, { method: 'POST', body: { version, note } })
    toast(`Version ${version} restored as version ${r.version}.`)
    await load()
  }, [load, name, toast])

  const changed = working && state.published ? !same(working, state.published.data) : false
  return { ...state, working, update, saving, changed, publish, discard, restore, reload: load, flush, name }
}

/** Sticky bar shown while there are unpublished changes. */
export function PublishBar({ item, onReview, label = 'changes' }) {
  if (!item.changed && !item.draft) return null
  const problems = item.errors?.length || 0
  return (
    <div className="xa-publishbar" role="region" aria-label="Unpublished changes">
      <div className="xa-publishbar-text">
        <strong>{item.changed ? `Unpublished ${label}` : 'Draft matches the live version'}</strong>
        <small>
          {item.saving ? 'Saving draft…' : item.savedAt ? `Draft saved ${timeAgo(item.savedAt)}${item.savedBy ? ` by ${item.savedBy}` : ''}` : 'Not saved yet'}
          {problems ? ` · ${problems} ${problems === 1 ? 'problem' : 'problems'} to fix before publishing` : ''}
          {item.stale ? ' · someone published a newer version since this draft started' : ''}
        </small>
      </div>
      <Button variant="ghost" size="sm" onClick={item.discard}>Discard</Button>
      <Button size="sm" onClick={onReview} disabled={!item.changed}>Review &amp; publish</Button>
    </div>
  )
}

/** The last step before publishing: problems, what changes, and a note for the history. */
export function PublishDialog({ item, title, onClose, children, extraBlock }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const problems = item.errors || []
  const blocked = problems.length > 0 || item.stale || !!extraBlock

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await item.publish(note.trim())
      onClose()
    } catch (err) {
      const detail = err.code === 'stale_draft' ? 'Someone published a newer version while you were editing. Discard this draft and start again from the live version.'
        : err.code === 'invalid' ? 'This draft has problems that block publishing.' : errorMessage(err)
      setError(detail)
      setBusy(false)
    }
  }

  return (
    <Modal wide title={title} subtitle="Check what changes. Publishing applies it to XO from the next message; you can restore an earlier version at any time."
      onClose={onClose}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Keep editing</Button>
        <Button type="submit" form="xa-publish-form" busy={busy} disabled={blocked || !note.trim()}>Publish</Button>
      </>}>
      <form id="xa-publish-form" className="xa-form" onSubmit={submit}>
        {error && <Notice tone="error">{error}</Notice>}
        {item.stale && <Notice tone="warning">Someone published a newer version since this draft was started. Discard the draft and redo the change on the live version.</Notice>}
        {problems.length > 0 && (
          <Notice tone="error">
            Fix these before publishing:
            <ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul>
          </Notice>
        )}
        {extraBlock && <Notice tone="warning">{extraBlock}</Notice>}
        {children}
        <Field label="What changed and why" hint="Shown in the version history and the activity log.">
          {(a) => <input {...a} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="e.g. Agreed in the weekly sales review" required />}
        </Field>
      </form>
    </Modal>
  )
}

/** Published versions, newest first, with one-click restore. */
export function HistoryDrawer({ item, onClose, describe }) {
  const [versions, setVersions] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  useEffect(() => {
    adminApi(`/config/${item.name}/versions`).then(setVersions).catch((e) => toast(errorMessage(e), 'error'))
  }, [item.name, item.published?.version, toast])

  const live = item.published?.version
  return (
    <Drawer title="Version history" onClose={onClose}>
      {!versions && <p className="xa-muted">Loading…</p>}
      {versions && (
        <ul className="xa-history">
          {versions.map((v) => (
            <li key={v.version} className={v.version === live ? 'is-live' : ''}>
              <span className="xa-history-v">v{v.version}</span>
              <div className="xa-history-body">
                <p>{v.note || (v.version === 0 ? 'Built-in' : 'No note')}</p>
                <span className="xa-muted xa-small">{v.version === 0 ? 'Shipped with XO' : `${v.published_by} · ${formatDateTime(v.published_at)}`}</span>
                {describe && v.version !== live && describe(v)}
              </div>
              {v.version === live ? <Badge tone="ok" icon="check">Live</Badge>
                : <Button variant="ghost" size="sm" onClick={() => setConfirm(v)}>Restore</Button>}
            </li>
          ))}
        </ul>
      )}
      {confirm && (
        <Modal title={`Restore version ${confirm.version}?`} onClose={() => setConfirm(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
            <Button busy={busy} onClick={async () => {
              setBusy(true)
              try { await item.restore(confirm.version, `Restored version ${confirm.version}`); setConfirm(null); onClose() } catch (e) { toast(errorMessage(e), 'error') }
              setBusy(false)
            }}>Restore</Button>
          </>}>
          <p>Version {confirm.version} becomes live again as a new version. Nothing is deleted; you can restore any version later.
            {item.draft ? ' Your unpublished draft stays as it is.' : ''}</p>
        </Modal>
      )}
    </Drawer>
  )
}

/** Live version line for a page header. */
export function VersionLine({ item, onHistory }) {
  const p = item.published
  if (!p) return null
  return (
    <span className="xa-version">
      <Icon name="checkCircle" size={14} />
      <span>Live: <strong>{p.version === 0 ? 'built-in' : `version ${p.version}`}</strong>{p.published_at ? ` · ${timeAgo(p.published_at)} by ${p.published_by}` : ''}</span>
      {onHistory && <Button variant="quiet" size="sm" icon="history" onClick={onHistory}>History</Button>}
    </span>
  )
}

/** Line-by-line comparison (longest common subsequence), with unchanged stretches folded. */
export function DiffView({ before, after }) {
  const a = before.split('\n')
  const b = after.split('\n')
  const n = a.length
  const m = b.length
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1))
  for (let i = n - 1; i >= 0; i -= 1) for (let j = m - 1; j >= 0; j -= 1) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
  const rows = []
  let i = 0
  let j = 0
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) { rows.push(['same', a[i]]); i += 1; j += 1 } else if (j < m && (i === n || dp[i][j + 1] >= dp[i + 1][j])) { rows.push(['add', b[j]]); j += 1 } else { rows.push(['del', a[i]]); i += 1 }
  }
  const out = []
  rows.forEach((r, k) => {
    const near = rows.slice(Math.max(0, k - 2), k + 3).some((x) => x[0] !== 'same')
    if (r[0] !== 'same' || near) out.push(r)
    else if (out.length && out[out.length - 1][0] !== 'gap') out.push(['gap', ''])
  })
  if (!rows.some((r) => r[0] !== 'same')) return <p className="xa-muted">No differences.</p>
  return (
    <div className="xa-diff" aria-label="Changes">
      {out.map((r, k) => (
        <div key={k} className={r[0] === 'add' ? 'is-add' : r[0] === 'del' ? 'is-del' : r[0] === 'gap' ? 'is-gap' : ''}>
          {r[0] === 'gap' ? '…' : `${r[0] === 'add' ? '+ ' : r[0] === 'del' ? '− ' : '  '}${r[1] || ' '}`}
        </div>
      ))}
    </div>
  )
}
