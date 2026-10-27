'use client'
import { useCallback, useEffect, useState } from 'react'
import { adminApi, errorMessage } from '../lib/api'
import { Badge, Button, Card, EmptyState, Field, Modal, Notice, PageHeader, formatDateTime, generatePassword } from '../components/ui'

export default function Users({ me }) {
  const [users, setUsers] = useState(null)
  const [roles, setRoles] = useState([])
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [dialog, setDialog] = useState(null) // { type: 'add' } | { type: 'password', user }
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(async () => {
    try {
      const [u, r] = await Promise.all([adminApi('/users'), adminApi('/roles')])
      setUsers(u)
      setRoles(r)
      setError(null)
    } catch (e) {
      setError(errorMessage(e))
    }
  }, [])

  useEffect(() => { load() }, [load])

  const roleLabel = (role) => roles.find((r) => r.role === role)?.label || role

  const change = async (user, body, message) => {
    setBusyId(user.id)
    setNotice(null)
    try {
      const updated = await adminApi(`/users/${user.id}`, { method: 'PATCH', body })
      setUsers((list) => list.map((u) => (u.id === updated.id ? updated : u)))
      setNotice({ tone: 'success', text: message(updated) })
    } catch (e) {
      setNotice({ tone: 'error', text: errorMessage(e) })
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="xa-stack">
      <PageHeader title="Users & roles" subtitle="Add the people who run XO and give each one a role. A role change or deactivation signs the person out at once."
        actions={<Button icon="plus" onClick={() => setDialog({ type: 'add' })}>Add person</Button>} />
      {notice && <Notice tone={notice.tone} onDismiss={() => setNotice(null)}>{notice.text}</Notice>}
      {error && <Notice tone="error">{error}</Notice>}

      <Card title="People" flush>
        {!users && !error && <p className="xa-muted">Loading…</p>}
        {users && users.length === 0 && <EmptyState icon="users" title="No accounts yet" />}
        {users && users.length > 0 && (
          <div className="xa-table-wrap">
            <table className="xa-table">
              <thead>
                <tr><th scope="col">Name</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Last sign-in</th><th scope="col"><span className="xa-sr">Actions</span></th></tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const self = u.id === me.user.id
                  return (
                    <tr key={u.id} className={u.active ? '' : 'is-inactive'}>
                      <td>
                        <strong>{u.name}</strong>{self && <Badge>You</Badge>}
                        <div className="xa-muted xa-small">{u.email}</div>
                      </td>
                      <td>
                        <label className="xa-sr" htmlFor={`role-${u.id}`}>Role for {u.name}</label>
                        <select id={`role-${u.id}`} value={u.role} disabled={self || busyId === u.id}
                          title={self ? 'Another admin can change your role' : undefined}
                          onChange={(e) => change(u, { role: e.target.value }, (x) => `${x.name} is now ${roleLabel(x.role)}.`)}>
                          {roles.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
                        </select>
                      </td>
                      <td>{u.active ? <Badge tone="ok">Active</Badge> : <Badge tone="muted">Deactivated</Badge>}</td>
                      <td className="xa-small">{formatDateTime(u.last_login_at)}</td>
                      <td className="xa-row-actions">
                        <Button variant="ghost" onClick={() => setDialog({ type: 'password', user: u })}>Reset password</Button>
                        {!self && (
                          <Button variant={u.active ? 'danger-ghost' : 'ghost'} busy={busyId === u.id}
                            onClick={() => change(u, { active: !u.active }, (x) => `${x.name} is ${x.active ? 'active again' : 'deactivated and signed out'}.`)}>
                            {u.active ? 'Deactivate' : 'Reactivate'}
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Roles">
        <ul className="xa-role-list">
          {roles.map((r) => (
            <li key={r.role}><strong>{r.label}</strong><span className="xa-muted">{r.permissions.length} permissions</span></li>
          ))}
        </ul>
      </Card>

      {dialog?.type === 'add' && (
        <AddUserDialog roles={roles} onClose={() => setDialog(null)}
          onCreated={(user, password) => {
            setUsers((list) => [...list, user])
            setDialog(null)
            setNotice({ tone: 'success', text: `${user.name} can now sign in with ${user.email}. Share the temporary password privately: ${password}` })
          }} />
      )}
      {dialog?.type === 'password' && (
        <ResetPasswordDialog user={dialog.user} onClose={() => setDialog(null)}
          onDone={(password) => {
            setDialog(null)
            setNotice({ tone: 'success', text: `New password for ${dialog.user.name}: ${password}. Their other sessions were signed out.` })
          }} />
      )}
    </div>
  )
}

function AddUserDialog({ roles, onClose, onCreated }) {
  const [form, setForm] = useState({ name: '', email: '', role: 'read_only_analyst', password: generatePassword() })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onCreated(await adminApi('/users', { method: 'POST', body: form }), form.password)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Modal title="Add a person" onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" form="xa-add-user" busy={busy}>Add person</Button></>}>
      <form id="xa-add-user" onSubmit={submit} className="xa-form">
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Full name">{(a) => <input {...a} value={form.name} onChange={set('name')} required maxLength={100} />}</Field>
        <Field label="Work email">{(a) => <input {...a} type="email" value={form.email} onChange={set('email')} required />}</Field>
        <Field label="Role" hint="Start with the least access the person needs; you can change it later.">
          {(a) => (
            <select {...a} value={form.role} onChange={set('role')}>
              {roles.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
            </select>
          )}
        </Field>
        <Field label="Temporary password" hint="At least 12 characters. Share it privately; they can change it under My account.">
          {(a) => (
            <div className="xa-input-row">
              <input {...a} value={form.password} onChange={set('password')} required minLength={12} autoComplete="new-password" spellCheck={false} />
              <Button variant="ghost" icon="refresh" aria-label="Generate another password" onClick={() => setForm((f) => ({ ...f, password: generatePassword() }))} />
            </div>
          )}
        </Field>
      </form>
    </Modal>
  )
}

function ResetPasswordDialog({ user, onClose, onDone }) {
  const [password, setPassword] = useState(generatePassword())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await adminApi(`/users/${user.id}/password`, { method: 'POST', body: { password } })
      onDone(password)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Modal title={`Reset password for ${user.name}`} onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" form="xa-reset-password" busy={busy}>Set password</Button></>}>
      <form id="xa-reset-password" onSubmit={submit} className="xa-form">
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="New temporary password" hint="Setting it signs this person out everywhere.">
          {(a) => (
            <div className="xa-input-row">
              <input {...a} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={12} autoComplete="new-password" spellCheck={false} />
              <Button variant="ghost" icon="refresh" aria-label="Generate another password" onClick={() => setPassword(generatePassword())} />
            </div>
          )}
        </Field>
      </form>
    </Modal>
  )
}
