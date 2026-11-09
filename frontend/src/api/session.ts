import { send } from './request.ts'

// login_required is false when the backend has no password set, as in local development, and logged_in is then true.
export type Session = {
  login_required: boolean
  logged_in: boolean
}

// Matches the limit on the login request in the backend.
export const MAX_PASSWORD_LENGTH = 1000

export function getSession(signal: AbortSignal): Promise<Session> {
  return send('/api/session', { signal }, "Could not check whether you're logged in.")
}

// The backend answers with a session cookie. It's HttpOnly, so this code never sees it, and the browser sends it with
// every later request by itself, because the page and the API share an origin.
export function logIn(password: string): Promise<void> {
  return send(
    '/api/session',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    },
    'Could not log in.',
  )
}

// Ends the session, and the backend clears its cookie.
export function logOut(): Promise<void> {
  return send('/api/session', { method: 'DELETE' }, 'Could not log out.')
}
