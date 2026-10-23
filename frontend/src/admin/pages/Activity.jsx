'use client'
import { useCallback, useEffect, useState } from 'react'
import { adminApi, errorMessage } from '../lib/api'
import { Button, Card, EmptyState, Notice, PageHeader, formatDateTime } from '../components/ui'

const ACTIONS = {
  signed_in: 'Signed in',
  signed_out: 'Signed out',
  password_changed: 'Changed own password',
  password_reset: 'Reset a password',
  user_created: 'Added a person',
  user_updated: 'Changed a person',
  config_published: 'Published a change',
  config_rolled_back: 'Restored an earlier version',
  reply_reviewed: 'Reviewed a reply',
  kb_draft_created: 'Saved a knowledge draft',
  kb_published: 'Published knowledge',
  kb_retired: 'Removed knowledge from XO',
  kb_source_added: 'Added a web page to knowledge',
  kb_source_refreshed: 'Refreshed a knowledge web page',
  kb_source_removed: 'Removed a knowledge web page',
  kb_restored: 'Restored a knowledge version',
  kb_reviewed: 'Confirmed knowledge is still correct',
  kb_uploaded: 'Imported knowledge from a file',
  kb_draft_dismissed: 'Dismissed a knowledge draft',
  kb_domains_updated: 'Changed the approved websites',
  budget_updated: 'Changed the AI budget',
  config_reloaded: 'Applied configuration'
}

function describe(details) {
  const entries = Object.entries(details || {})
  if (!entries.length) return '—'
  return entries.map(([key, value]) => (value && typeof value === 'object' && 'from' in value
    ? `${key}: ${String(value.from)} → ${String(value.to)}`
    : `${key}: ${String(value)}`)).join(', ')
}

export default function Activity() {
  const [items, setItems] = useState(null)
  const [action, setAction] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    try {
      setItems(await adminApi(`/activity?limit=200${action ? `&action=${encodeURIComponent(action)}` : ''}`))
      setError(null)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }, [action])

  useEffect(() => { load() }, [load])

  return (
    <div className="xa-stack">
      <PageHeader title="Activity log" subtitle="Every change made in the admin module, with who made it and when." />
      {error && <Notice tone="error">{error}</Notice>}
      <Card title="Recent activity" actions={(
        <>
          <label className="xa-sr" htmlFor="xa-activity-filter">Filter by action</label>
          <select id="xa-activity-filter" value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">All actions</option>
            {Object.entries(ACTIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <Button variant="ghost" icon="refresh" busy={busy} onClick={load}>Refresh</Button>
        </>
      )}>
        {items && items.length === 0 && <EmptyState icon="list" title="Nothing recorded yet" />}
        {items && items.length > 0 && (
          <div className="xa-table-wrap">
            <table className="xa-table">
              <thead><tr><th scope="col">When</th><th scope="col">Who</th><th scope="col">What</th><th scope="col">On</th><th scope="col">Details</th></tr></thead>
              <tbody>
                {items.map((e, i) => (
                  <tr key={`${e.created_at}-${i}`}>
                    <td className="xa-small xa-nowrap">{formatDateTime(e.created_at)}</td>
                    <td className="xa-small">{e.actor_email}</td>
                    <td>{ACTIONS[e.action] || e.action}</td>
                    <td className="xa-small">{e.resource}</td>
                    <td className="xa-small xa-muted">{describe(e.details)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
