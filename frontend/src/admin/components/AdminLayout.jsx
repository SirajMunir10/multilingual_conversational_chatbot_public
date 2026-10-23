'use client'
import { useEffect, useState } from 'react'
import { visibleGroups } from '../navigation'
import CommandPalette from './CommandPalette'
import Icon from './Icon'
import { initials } from './ui'

export default function AdminLayout({ me, page, onNavigate, theme, onToggleTheme, onSignOut, children }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const groups = visibleGroups(me.permissions)

  // Closing the drawer after navigating keeps phone and tablet use one-handed.
  useEffect(() => { setMenuOpen(false) }, [page?.id])

  // "/" or Ctrl/⌘+K opens quick search, unless the person is typing in a field.
  useEffect(() => {
    const onKey = (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault()
        setSearching(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const go = (id) => (e) => {
    e.preventDefault()
    onNavigate(id)
  }

  return (
    <div className={`xa-shell${menuOpen ? ' menu-open' : ''}`}>
      <aside className="xa-side" aria-label="Admin sections">
        <div className="xa-side-brand">
          <img src="/xo-mascot.png" alt="" width="32" height="32" />
          <strong>XO Admin<small>XOTO back office</small></strong>
          <button type="button" className="xa-icon-btn xa-side-close" onClick={() => setMenuOpen(false)} aria-label="Close menu"><Icon name="close" /></button>
        </div>
        <a href="#/account" onClick={go('account')} className="xa-side-me" aria-label={`My account: ${me.user.name}, ${me.role_label}`}>
          <span className="xa-avatar is-online" aria-hidden="true">{initials(me.user.name)}</span>
          <span><strong>{me.user.name}</strong><small>{me.role_label}</small></span>
        </a>
        <nav>
          {groups.map((group) => (
            <div className="xa-nav-group" key={group.label || 'main'}>
              {group.label && <p className="xa-nav-label">{group.label}</p>}
              <ul>
                {group.items.map((item) => (
                  <li key={item.id}>
                    <a href={`#/${item.id}`} onClick={go(item.id)}
                      className={`xa-nav-item${page?.id === item.id ? ' active' : ''}${item.soon ? ' is-soon' : ''}`}
                      aria-current={page?.id === item.id ? 'page' : undefined}>
                      <Icon name={item.icon} />
                      <span>{item.label}</span>
                      {item.soon && <span className="xa-tag">{item.soon}</span>}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="xa-side-foot"><span className="xa-dot" aria-hidden="true" />Changes apply to XO when published</div>
      </aside>
      <button type="button" className="xa-scrim" aria-label="Close menu" tabIndex={-1} onClick={() => setMenuOpen(false)} />

      <div className="xa-main">
        <header className="xa-top">
          <button type="button" className="xa-icon-btn xa-menu-btn" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Icon name="menu" /></button>
          <button type="button" className="xa-search-trigger" onClick={() => setSearching(true)} aria-label="Quick search">
            <Icon name="search" size={16} /><span>Search pages and conversations</span><span className="xa-kbd">/</span>
          </button>
          <div className="xa-top-actions">
            <button type="button" className="xa-icon-btn" onClick={onToggleTheme} aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            </button>
            <span className="xa-top-sep" aria-hidden="true" />
            <button type="button" className="xa-btn xa-btn-quiet" onClick={onSignOut}><Icon name="logout" size={16} /><span>Sign out</span></button>
          </div>
        </header>
        <main className="xa-content" id="xa-content" tabIndex={-1}>{children}</main>
      </div>
      {searching && <CommandPalette me={me} onNavigate={onNavigate} onClose={() => setSearching(false)} />}
    </div>
  )
}
