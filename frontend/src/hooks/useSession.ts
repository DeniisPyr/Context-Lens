import { useEffect, useState } from 'react'
import { getSession } from '../api/session.ts'

// What the page shows below its title: nothing while checking, the error when the check fails, the login form, or the
// app. loginRequired is false when the backend has no password, and then the app has no Log out button.
export type SessionState =
  | { status: 'checking' }
  | { status: 'failed'; error: string }
  | { status: 'loggedOut' }
  | { status: 'loggedIn'; loginRequired: boolean }

export function useSession() {
  const [session, setSession] = useState<SessionState>({ status: 'checking' })
  // Adding 1 re-runs the effect below: it aborts any check still running and checks again.
  const [checkCount, setCheckCount] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getSession(controller.signal)
      .then(({ login_required, logged_in }) =>
        setSession(logged_in ? { status: 'loggedIn', loginRequired: login_required } : { status: 'loggedOut' }),
      )
      .catch((err: Error) => {
        if (!controller.signal.aborted) setSession({ status: 'failed', error: err.message })
      })
    return () => controller.abort()
  }, [checkCount])

  // The error goes while the new check runs, so the user sees that something happened.
  function retry() {
    setSession({ status: 'checking' })
    setCheckCount((count) => count + 1)
  }

  // Only the login form logs in, and it only shows when a login is required.
  function loggedIn() {
    setSession({ status: 'loggedIn', loginRequired: true })
  }

  function loggedOut() {
    setSession({ status: 'loggedOut' })
  }

  return { session, retry, loggedIn, loggedOut }
}
