import { useState } from 'react'
import { logOut } from '../api/session.ts'
import { LogOutIcon } from './icons.tsx'

type Props = {
  onLoggedOut: () => void
}

export default function LogOutButton({ onLoggedOut }: Props) {
  const [loggingOut, setLoggingOut] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // When it fails, the session goes on, so the app stays: the login form would be a lie until the page reloads.
  async function handleClick() {
    setLoggingOut(true)
    setError(null)
    try {
      await logOut()
      // App puts the login form in place of the app and this button, so nothing here needs resetting.
      onLoggedOut()
    } catch (err) {
      setError((err as Error).message)
      setLoggingOut(false)
    }
  }

  return (
    <>
      <button type="button" className="logout-button" disabled={loggingOut} onClick={handleClick}>
        <LogOutIcon className="icon-sm" />
        {loggingOut ? 'Logging out…' : 'Log out'}
      </button>
      {error && <p role="alert">{error}</p>}
    </>
  )
}
