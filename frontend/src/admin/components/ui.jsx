'use client'
import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import Icon from './Icon'

export function Button({ variant = 'primary', size, icon, busy, children, className = '', ...props }) {
  return (
    <button type="button" className={`xa-btn xa-btn-${variant}${size === 'sm' ? ' xa-btn-sm' : ''} ${className}`}
      disabled={busy || props.disabled} aria-busy={busy || undefined} {...props}>
      {busy ? <span className="xa-spinner" aria-hidden="true" /> : icon && <Icon name={icon} size={size === 'sm' ? 14 : 16} />}
      {children && <span>{children}</span>}
    </button>
  )
}

export function Field({ label, hint, error, changed, children, className = '' }) {
  const id = useId()
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined
  return (
    <div className={`xa-field${error ? ' has-error' : ''}${changed ? ' is-changed' : ''} ${className}`}>
      <label htmlFor={id}>{label}</label>
      {children({ id, 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })}
      {hint && <p id={`${id}-hint`} className="xa-field-hint">{hint}</p>}
      {error && <p id={`${id}-error`} className="xa-field-error" role="alert">{error}</p>}
    </div>
  )
}

/** A number field with a unit (%, AED, years). `scale` converts stored values (e.g. 0.5) to shown values (50%). */
export function UnitInput({ value, onChange, unit, prefix, scale = 1, step = 'any', min, max, disabled, ...a }) {
  const shown = value === null || value === undefined || value === '' ? '' : +(Number(value) * scale).toFixed(6)
  return (
    <div className={`xa-unit${prefix ? ' is-prefix' : ''}`}>
      <input {...a} type="number" inputMode="decimal" step={step} min={min} max={max} value={shown} disabled={disabled}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value) / scale)} />
      <span>{prefix || unit}</span>
    </div>
  )
}

export function Switch({ checked, onChange, label, disabled, hint, showLabel }) {
  return (
    <label className={`xa-switch${showLabel ? ' has-text' : ''}`}>
      <input type="checkbox" role="switch" checked={!!checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)}
        aria-label={typeof label === 'string' ? label : undefined} />
      <i aria-hidden="true" />
      {showLabel
        ? <span className="xa-switch-text"><strong>{label}</strong>{hint && <small>{hint}</small>}</span>
        : <>{label && <span className="xa-sr">{label}</span>}{hint && <span className="xa-small xa-muted">{hint}</span>}</>}
    </label>
  )
}

/** Words or phrases as removable chips; Enter or comma adds. */
export function TagInput({ value = [], onChange, placeholder, id, ...a }) {
  const [draft, setDraft] = useState('')
  const add = (text) => {
    const words = text.split(',').map((w) => w.trim()).filter(Boolean)
    if (words.length) onChange([...value, ...words.filter((w) => !value.includes(w))])
    setDraft('')
  }
  return (
    <div className="xa-taginput" onClick={(e) => e.currentTarget.querySelector('input')?.focus()}>
      {value.map((w) => (
        <span className="xa-chip" key={w}>
          {w}
          <button type="button" aria-label={`Remove ${w}`} onClick={() => onChange(value.filter((x) => x !== w))}><Icon name="close" size={12} /></button>
        </span>
      ))}
      <input id={id} {...a} value={draft} placeholder={value.length ? '' : placeholder}
        onChange={(e) => (e.target.value.endsWith(',') ? add(e.target.value) : setDraft(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); add(draft) }
          if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1))
        }}
        onBlur={() => draft && add(draft)} />
    </div>
  )
}

export function Badge({ tone = 'neutral', icon, children }) {
  return <span className={`xa-badge xa-badge-${tone}`}>{icon && <Icon name={icon} size={12} />}{children}</span>
}

export function Notice({ tone = 'info', children, onDismiss }) {
  const icon = { error: 'alert', warning: 'alert', success: 'checkCircle' }[tone] || 'info'
  return (
    <div className={`xa-notice xa-notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon name={icon} size={16} />
      <div className="xa-notice-body">{children}</div>
      {onDismiss && <button type="button" className="xa-icon-btn" onClick={onDismiss} aria-label="Dismiss"><Icon name="close" size={14} /></button>}
    </div>
  )
}

export function Card({ title, subtitle, actions, children, className = '', flush }) {
  return (
    <section className={`xa-card${flush ? ' xa-card-flush' : ''} ${className}`}>
      {(title || actions) && (
        <header className="xa-card-head">
          <div>{title && <h2>{title}</h2>}{subtitle && <p>{subtitle}</p>}</div>
          {actions && <div className="xa-card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function PageHeader({ title, subtitle, actions, crumb }) {
  return (
    <div className="xa-page-head">
      <div>
        {crumb && <div className="xa-crumb">{crumb}</div>}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="xa-page-actions">{actions}</div>}
    </div>
  )
}

export function Tabs({ tabs, value, onChange, label }) {
  return (
    <div className="xa-tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.id} type="button" role="tab" aria-selected={value === t.id} className={value === t.id ? 'is-active' : ''} onClick={() => onChange(t.id)}>
          {t.label}{t.changed && <i className="xa-dot-change" title="Unpublished changes" />}
        </button>
      ))}
    </div>
  )
}

export function EmptyState({ icon = 'sparkle', title, children, action }) {
  return (
    <div className="xa-empty">
      <span className="xa-empty-icon"><Icon name={icon} size={22} /></span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

function useOverlay(onClose, ref) {
  useEffect(() => {
    const opener = document.activeElement
    const first = ref.current?.querySelector('input:not([type="checkbox"]), select, textarea, button:not(.xa-overlay-close)')
    first?.focus()
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      opener?.focus?.()
    }
  }, [onClose, ref])
}

/** Accessible dialog: focus moves in, Escape closes, focus returns to the opener. */
export function Modal({ title, subtitle, onClose, children, footer, wide }) {
  const ref = useRef(null)
  const titleId = useId()
  useOverlay(onClose, ref)
  return (
    <div className="xa-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`xa-modal${wide ? ' is-wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref}>
        <header className="xa-modal-head">
          <div><h2 id={titleId}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button type="button" className="xa-icon-btn xa-overlay-close" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        </header>
        <div className="xa-modal-body">{children}</div>
        {footer && <footer className="xa-modal-foot">{footer}</footer>}
      </div>
    </div>
  )
}

export function Drawer({ title, onClose, children }) {
  const ref = useRef(null)
  const titleId = useId()
  useOverlay(onClose, ref)
  return (
    <>
      <div className="xa-drawer-backdrop" onMouseDown={onClose} />
      <aside className="xa-drawer" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref}>
        <header className="xa-drawer-head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="xa-icon-btn xa-overlay-close" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        </header>
        <div className="xa-drawer-body">{children}</div>
      </aside>
    </>
  )
}

// ---- Toasts: short confirmations after an action ----
const ToastContext = createContext(() => {})
export const useToast = () => useContext(ToastContext)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const push = useCallback((text, tone = 'success') => {
    const id = Math.random().toString(36).slice(2)
    setToasts((t) => [...t, { id, text, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="xa-toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`xa-toast${t.tone === 'error' ? ' is-error' : ''}`}>
            <Icon name={t.tone === 'error' ? 'alert' : 'checkCircle'} size={16} />{t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function formatDateTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function timeAgo(value) {
  if (!value) return ''
  const s = Math.round((Date.now() - new Date(value).getTime()) / 1000)
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return formatDateTime(value)
}

/** A readable random password for "set a temporary password" flows (not stored anywhere by the page). */
export function generatePassword() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
  const out = []
  while (out.length < 16) {
    const [b] = crypto.getRandomValues(new Uint8Array(1))
    if (b < 224) out.push(alphabet[b % alphabet.length]) // 224 = 4 × 56: no bias towards early letters
  }
  return out.join('').replace(/(.{4})(?=.)/g, '$1-')
}

export function initials(name) {
  return (name || '?').split(' ').filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('')
}
