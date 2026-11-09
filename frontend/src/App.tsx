import ApiStatus from './components/ApiStatus.tsx'
import LoginForm from './components/LoginForm.tsx'
import LogOutButton from './components/LogOutButton.tsx'
import Workspace from './components/Workspace.tsx'
import { useSession } from './hooks/useSession.ts'

export default function App() {
  const { session, retry, loggedIn, loggedOut } = useSession()

  return (
    <main>
      <header className="page-header">
        <h1>Context-Lens</h1>
        {session.status === 'loggedIn' && session.loginRequired && <LogOutButton onLoggedOut={loggedOut} />}
      </header>
      <p>Ask questions about your documents and get answers you can check.</p>
      <ApiStatus />
      {session.status === 'failed' && (
        <>
          <p role="alert">{session.error}</p>
          <button type="button" onClick={retry}>
            Try again
          </button>
        </>
      )}
      {session.status === 'loggedOut' && <LoginForm onLoggedIn={loggedIn} />}
      {session.status === 'loggedIn' && <Workspace />}
    </main>
  )
}
