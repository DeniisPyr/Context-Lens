import ApiStatus from './components/ApiStatus.tsx'
import { LensIcon } from './components/icons.tsx'
import LoginForm from './components/LoginForm.tsx'
import Workspace from './components/Workspace.tsx'
import { useSession } from './hooks/useSession.ts'

export default function App() {
  const { session, retry, loggedIn, loggedOut } = useSession()

  // The app fills the window with its own columns, and the sidebar carries the title, the API status and Log out.
  if (session.status === 'loggedIn') {
    return <Workspace loginRequired={session.loginRequired} onLoggedOut={loggedOut} />
  }

  // Before that, one card in the middle of the window: the app's name on top, the API status at the bottom, and
  // between them nothing while the session is checked, the error, or the login form.
  return (
    <main className="gate">
      <div className="gate-card">
        <header className="gate-head">
          <span className="logo" aria-hidden="true">
            <LensIcon />
          </span>
          <h1 className="app-name">Context-Lens</h1>
          <p className="tagline">Ask questions about your documents and get answers you can check.</p>
        </header>
        {session.status === 'failed' && (
          <div className="gate-error">
            <p role="alert">{session.error}</p>
            <button type="button" onClick={retry}>
              Try again
            </button>
          </div>
        )}
        {session.status === 'loggedOut' && <LoginForm notice={session.notice} onLoggedIn={loggedIn} />}
        <footer className="gate-foot">
          <ApiStatus />
        </footer>
      </div>
    </main>
  )
}
