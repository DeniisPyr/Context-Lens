import { useEffect, useState } from 'react'
import { onSessionEnd } from '../api/request.ts'
import { getSession } from '../api/session.ts'

// What the page shows below its title: nothing while checking, the error when the check fails, the login form, or the
// app. loginRequired is false when the backend has no password, and then the app has no Log out button. notice says
// why the login form is back, when the session ended by itself.
export type SessionState =
  | { status: 'checking' }
  | { status: 'failed'; error: string }
  | { status: 'loggedOut'; notice: string | null }
  | { status: 'loggedIn'; loginRequired: boolean }

export function useSession() {
  const [session, setSession] = useState<SessionState>({ status: 'checking' })
  // Adding 1 re-runs the effect below: it aborts any check still running and checks again.
  const [checkCount, setCheckCount] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getSession(controller.signal)
      .then(({ login_required, logged_in }) =>
        setSession(
          logged_in ? { status: 'loggedIn', loginRequired: login_required } : { status: 'loggedOut', notice: null },
        ),
      )
      .catch((err: Error) => {
        if (!controller.signal.aborted) setSession({ status: 'failed', error: err.message })
      })
    return () => controller.abort()
  }, [checkCount])

  // A request the backend turned away for want of a session brings the login form back, but only from the app: the
  // app's other requests still on their way can fail the same way, or come back after the user logged out, and none
  // of them should put the notice on a form that's already there. Nothing here sends a request, so it can't loop.
  useEffect(
    () =>
      onSessionEnd(() =>
        setSession((current) =>
          current.status === 'loggedIn'
            ? { status: 'loggedOut', notice: 'Your session has ended. Log in again.' }
            : current,
        ),
      ),
    [],
  )

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
    setSession({ status: 'loggedOut', notice: null })
  }

  return { session, retry, loggedIn, loggedOut }
}
