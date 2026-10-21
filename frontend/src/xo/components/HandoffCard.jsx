'use client'
// Advisor callback review card (PRD FR-5): nothing is saved until the user taps Confirm (or edits and submits).
// The card's state is kept on the message (draft object, updated through `onUpdate`), so it survives a page refresh.
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import XoIcon from './XoIcon'
import { languages, languageInfo, t } from '../i18n'

const TEAMS = ['mortgage', 'sales', 'support']
const ERRORS = { invalid_phone: 'handoff_err_phone', invalid_name: 'handoff_err_name', save_failed: 'handoff_err_save' }

/** Provided by the chat widget: saves the confirmed (or edited) details. */
export const SubmitHandoffContext = createContext(null)

export default function HandoffCard({ draft, language = 'en', onUpdate }) {
  const submitHandoff = useContext(SubmitHandoffContext)
  const tr = (key, vars) => t(language, key, vars)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [errorField, setErrorField] = useState('')
  const [form, setForm] = useState({ name: '', phone: '', preferred_language: '', team: '' })
  const [focusField, setFocusField] = useState(null)
  const nameInput = useRef(null)
  const phoneInput = useRef(null)

  const state = draft.status || 'review'
  const languageLabel = (code) => languageInfo(code)?.native || code
  const teamLabel = (team) => (TEAMS.includes(team) ? tr('team_' + team) : team)
  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  // Focus the requested field once the form has rendered (Vue: nextTick after editing = true).
  useEffect(() => {
    if (!editing || !focusField) return
    const target = focusField === 'phone' ? phoneInput.current : nameInput.current
    if (target) target.focus()
    setFocusField(null)
  }, [editing, focusField])

  function startEdit(field) {
    setForm({
      name: draft.name || '',
      phone: draft.phone || '',
      preferred_language: draft.preferred_language || language,
      team: TEAMS.includes(draft.team) ? draft.team : 'support'
    })
    setEditing(true)
    setFocusField(field === 'phone' ? 'phone' : 'name')
  }

  function cancelEdit() {
    setEditing(false)
    setError('')
    setErrorField('')
  }

  function showError(code, field) {
    setError(tr(ERRORS[code] || 'handoff_err_save'))
    setErrorField(field || '')
    if (field && !editing) startEdit(field)
  }

  async function submit(e) {
    if (e && e.preventDefault) e.preventDefault()
    if (saving || !submitHandoff) return
    const values = editing ? { ...form } : {
      name: draft.name, phone: draft.phone, preferred_language: draft.preferred_language, team: draft.team
    }
    if (!values.name.trim()) return showError('invalid_name', 'name')
    if ((values.phone.match(/\d/g) || []).length < 7) return showError('invalid_phone', 'phone')

    setSaving(true)
    setError('')
    const result = await submitHandoff({
      draft_id: draft.draft_id, full_name: values.name, phone: values.phone,
      preferred_language: values.preferred_language, team: values.team
    })
    setSaving(false)
    if (result.lead_saved) {
      onUpdate?.({
        status: 'saved', ticket_id: result.ticket_id, name: result.name, phone: result.phone,
        preferred_language: result.preferred_language, team: result.team
      })
      setEditing(false)
      return
    }
    if (result.error === 'draft_expired') {
      onUpdate?.({ status: 'expired' })
      setEditing(false)
      return
    }
    showError(result.error, result.field)
  }

  return (
    <div className={'handoff-card is-' + state}>
      <div className="hc-head">
        <span className="hc-icon"><XoIcon name={state === 'saved' ? 'check' : 'headset'} size={18} /></span>
        <div className="hc-title">
          <strong>{state === 'saved' ? tr('handoff_saved') : tr('handoff_review_title')}</strong>
          {state === 'saved' && draft.ticket_id && <small>{tr('ticket')}: {draft.ticket_id}</small>}
        </div>
      </div>

      {!editing ? (
        <dl className="hc-rows">
          <div><dt>{tr('handoff_name')}</dt><dd>{draft.name}</dd></div>
          <div><dt>{tr('handoff_phone')}</dt><dd dir="ltr">{draft.phone}</dd></div>
          {draft.preferred_language && <div><dt>{tr('handoff_language')}</dt><dd>{languageLabel(draft.preferred_language)}</dd></div>}
          <div><dt>{tr('handoff_team')}</dt><dd>{teamLabel(draft.team)}</dd></div>
        </dl>
      ) : (
        <form className="hc-form" onSubmit={submit} noValidate>
          <label>
            <span>{tr('handoff_name')}</span>
            <input value={form.name} onChange={setField('name')} type="text" autoComplete="name" maxLength={120} dir="auto"
                   aria-invalid={errorField === 'name'} ref={nameInput} />
          </label>
          <label>
            <span>{tr('handoff_phone')}</span>
            <input value={form.phone} onChange={setField('phone')} type="tel" inputMode="tel" autoComplete="tel" dir="ltr" maxLength={24}
                   placeholder="+971 50 123 4567" aria-invalid={errorField === 'phone'} ref={phoneInput} />
            <small>{tr('handoff_phone_hint')}</small>
          </label>
          <div className="hc-form-row">
            <label>
              <span>{tr('handoff_language')}</span>
              <select value={form.preferred_language} onChange={setField('preferred_language')}>
                {languages.map((lang) => <option key={lang.code} value={lang.code}>{lang.native}</option>)}
              </select>
            </label>
            <label>
              <span>{tr('handoff_team')}</span>
              <select value={form.team} onChange={setField('team')}>
                {TEAMS.map((team) => <option key={team} value={team}>{tr('team_' + team)}</option>)}
              </select>
            </label>
          </div>
          <button type="submit" className="visually-hidden" tabIndex={-1}>{tr('handoff_submit')}</button>
        </form>
      )}

      {error && <p className="hc-error" role="alert">{error}</p>}
      {state === 'review'
        ? <p className="hc-note">{tr('handoff_consent_note')}</p>
        : state === 'saved'
          ? <p className="hc-note">{tr('handoff_saved_note')}</p>
          : state === 'expired'
            ? <p className="hc-note">{tr('handoff_err_expired')}</p>
            : null}

      {state === 'review' && (
        <div className="hc-actions">
          {!editing ? (
            <>
              <button type="button" className="hc-btn ghost" onClick={() => startEdit()} disabled={saving}>
                <XoIcon name="edit" size={15} />{tr('handoff_edit')}
              </button>
              <button type="button" className="hc-btn primary" onClick={() => submit()} disabled={saving}>
                <XoIcon name="check" size={15} />{saving ? tr('handoff_saving') : tr('handoff_confirm')}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="hc-btn ghost" onClick={cancelEdit} disabled={saving}>{tr('cancel')}</button>
              <button type="button" className="hc-btn primary" onClick={() => submit()} disabled={saving}>
                {saving ? tr('handoff_saving') : tr('handoff_submit')}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
