'use client'
import { useEffect, useMemo, useRef, useState } from 'react'
import { adminApi } from '../lib/api'
import { visibleGroups } from '../navigation'
import Icon from './Icon'

/** Quick search ("/" or Ctrl/⌘+K): jump to a page, or find a conversation by what was said. */
export default function CommandPalette({ me, onNavigate, onClose }) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [conversations, setConversations] = useState([])
  const input = useRef(null)
  const canSearchChats = me.permissions.includes('conversations.view')

  useEffect(() => { input.current?.focus() }, [])

  useEffect(() => {
    if (!canSearchChats || query.trim().length < 3) { setConversations([]); return undefined }
    const t = setTimeout(() => {
      adminApi(`/conversations?days=90&page_size=6&q=${encodeURIComponent(query.trim())}`)
        .then((r) => setConversations(r.items)).catch(() => setConversations([]))
    }, 250)
    return () => clearTimeout(t)
  }, [query, canSearchChats])

  const pages = useMemo(() => {
    const all = visibleGroups(me.permissions).flatMap((g) => g.items.map((i) => ({ ...i, group: g.label || 'General' })))
      .concat([{ id: 'account', label: 'My account', icon: 'user', group: 'General' }])
    const q = query.trim().toLowerCase()
    return q ? all.filter((p) => p.label.toLowerCase().includes(q) || (p.group || '').toLowerCase().includes(q)) : all
  }, [me.permissions, query])

  const items = [
    ...pages.map((p) => ({ key: `p-${p.id}`, group: 'Pages', icon: p.icon, label: p.label, hint: p.soon ? `Coming in ${p.soon}` : p.group, go: p.id })),
    ...conversations.map((c) => ({ key: `c-${c.session_id}`, group: 'Conversations', icon: 'chat', label: c.first_question || c.session_id,
      hint: new Date(c.started_at).toLocaleDateString(), go: `conversations/${encodeURIComponent(c.session_id)}` })),
  ]

  useEffect(() => { setActive(0) }, [query, conversations.length])

  const choose = (item) => { if (item) { onNavigate(item.go); onClose() } }

  const onKey = (e) => {
    if (e.key === 'Escape') onClose()
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    if (e.key === 'Enter') { e.preventDefault(); choose(items[active]) }
  }

  let lastGroup = null
  return (
    <div className="xa-palette-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="xa-palette" role="dialog" aria-modal="true" aria-label="Quick search">
        <div className="xa-palette-input">
          <Icon name="search" />
          <input ref={input} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey}
            placeholder={canSearchChats ? 'Go to a page, or search conversations…' : 'Go to a page…'}
            role="combobox" aria-expanded="true" aria-controls="xa-palette-list" aria-activedescendant={items[active] ? `xa-pi-${active}` : undefined} />
          <span className="xa-kbd">Esc</span>
        </div>
        <div className="xa-palette-list" id="xa-palette-list" role="listbox">
          {items.length === 0 && <p className="xa-muted xa-small" style={{ padding: 14 }}>No matches. Try fewer words.</p>}
          {items.map((item, i) => {
            const header = item.group !== lastGroup ? <div className="xa-palette-group" key={`g-${item.group}`}>{item.group}</div> : null
            lastGroup = item.group
            return [header, (
              <div key={item.key} id={`xa-pi-${i}`} role="option" aria-selected={i === active}
                className={`xa-palette-item${i === active ? ' is-active' : ''}`} onMouseEnter={() => setActive(i)} onClick={() => choose(item)}>
                <Icon name={item.icon} size={16} /><span>{item.label}</span><small>{item.hint}</small>
              </div>
            )]
          })}
        </div>
        <div className="xa-palette-foot"><span><span className="xa-kbd">↑</span> <span className="xa-kbd">↓</span> move</span><span><span className="xa-kbd">Enter</span> open</span></div>
      </div>
    </div>
  )
}
