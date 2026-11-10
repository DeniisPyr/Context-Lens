import ApiStatus from './components/ApiStatus.tsx'
import LoginForm from './components/LoginForm.tsx'
import Workspace from './components/Workspace.tsx'
import { useSession } from './hooks/useSession.ts'

export default function App() {
  const { session, retry, loggedIn, loggedOut } = useSession()

  // The app fills the window with its own columns, and the sidebar carries the title, the API status and Log out.
  if (session.status === 'loggedIn') {
    return <Workspace loginRequired={session.loginRequired} onLoggedOut={loggedOut} />
  }

  // Before that, a narrow page under the title: nothing while the session is checked, the error, or the login form.
  return (
    <main className="gate">
      <h1>Context-Lens</h1>
      <p className="tagline">Ask questions about your documents and get answers you can check.</p>
      <ApiStatus />
      {session.status === 'failed' && (
        <>
          <p role="alert">{session.error}</p>
          <button type="button" onClick={retry}>
            Try again
          </button>
        </>
      )}
      {session.status === 'loggedOut' && <LoginForm notice={session.notice} onLoggedIn={loggedIn} />}
    </main>
  )
}
