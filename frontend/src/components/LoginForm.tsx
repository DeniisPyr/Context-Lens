import { type SubmitEvent, useState } from 'react'
import { logIn, MAX_PASSWORD_LENGTH } from '../api/session.ts'

type Props = {
  // Why the form is back, when the session ended by itself. It shows like an error until the user tries to log in.
  notice: string | null
  onLoggedIn: () => void
}

export default function LoginForm({ notice, onLoggedIn }: Props) {
  const [password, setPassword] = useState('')
  const [loggingIn, setLoggingIn] = useState(false)
  // Starts as the notice, which can't change while the form is here: App only ends a session that shows the app.
  const [error, setError] = useState<string | null>(notice)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    // Not trimmed: a space can be part of a password.
    if (!password) {
      setError('Type the password first.')
      return
    }

    setLoggingIn(true)
    setError(null)
    try {
      await logIn(password)
      // App puts the app in place of this form, so nothing here needs resetting.
      onLoggedIn()
    } catch (err) {
      // The password stays in the field, so a typo can be fixed without typing it all again.
      setError((err as Error).message)
      setLoggingIn(false)
    }
  }

  return (
    <section>
      <h2>Log in</h2>
      <form className="login-form" onSubmit={handleSubmit}>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            maxLength={MAX_PASSWORD_LENGTH}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button type="submit" disabled={loggingIn}>
          {loggingIn ? 'Logging in…' : 'Log in'}
        </button>
        {error && <p role="alert">{error}</p>}
      </form>
    </section>
  )
}
