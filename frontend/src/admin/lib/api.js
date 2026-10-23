// Admin API client. Sign-in lives in an HttpOnly cookie the page never sees; every change request carries
// the X-Requested-With header the backend requires (protection against cross-site requests).
const apiBase = (process.env.NEXT_PUBLIC_API_BASE || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(status, code, errors = []) {
    super(code || `HTTP ${status}`)
    this.status = status
    this.code = code
    this.errors = errors // readable problems sent by the server, e.g. for a rejected edit
  }
}

let onSignedOut = null
/** Called when any request finds the session has ended (signed out elsewhere, role changed, expired). */
export function setSignedOutHandler(handler) {
  onSignedOut = handler
}

export async function adminApi(path, { method = 'GET', body } = {}) {
  let res
  try {
    res = await fetch(`${apiBase}/api/admin${path}`, {
      method,
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'xo-admin',
        ...(body !== undefined && { 'Content-Type': 'application/json' })
      },
      body: body !== undefined ? JSON.stringify(body) : undefined
    })
  } catch (e) {
    throw new ApiError(0, 'network_error')
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) {
    const detail = data?.detail
    const code = typeof detail === 'string' ? detail : detail?.code || null
    if (res.status === 401 && path !== '/auth/login' && onSignedOut) onSignedOut()
    throw new ApiError(res.status, code, Array.isArray(detail?.errors) ? detail.errors : [])
  }
  return data
}

const MESSAGES = {
  invalid_credentials: 'That email and password do not match an active account.',
  too_many_attempts: 'Too many sign-in attempts. Please wait 15 minutes and try again.',
  admin_login_unavailable: 'Admin sign-in is not configured on the server yet (JWT_SECRET is missing).',
  network_error: 'Could not reach the server. Check your connection and try again.',
  email_taken: 'An account with this email already exists.',
  invalid_email: 'Enter a valid email address.',
  invalid_name: 'Enter a name.',
  invalid_role: 'Choose a role.',
  password_too_short: 'Use at least 12 characters for the password.',
  wrong_current_password: 'Your current password is not correct.',
  cannot_change_own_access: 'You cannot change your own role or deactivate yourself. Ask another admin.',
  last_admin: 'At least one active Admin must remain.',
  not_found: 'This account no longer exists.'
}

export function errorMessage(error) {
  if (error?.code && MESSAGES[error.code]) return MESSAGES[error.code]
  if (error?.errors?.length) return error.errors.join(' ')
  if (error?.status === 403) return 'Your role does not allow this.'
  return 'Something went wrong. Please try again.'
}
