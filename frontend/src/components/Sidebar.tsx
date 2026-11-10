import type { ReactNode } from 'react'
import ApiStatus from './ApiStatus.tsx'
import { LensIcon, LockIcon } from './icons.tsx'
import LogOutButton from './LogOutButton.tsx'
import ThemeSwitch from './ThemeSwitch.tsx'

type Props = {
  // False when the backend has no password: nobody is signed in, so there's nothing to log out of.
  loginRequired: boolean
  onLoggedOut: () => void
  // The datasets and the documents, which Workspace holds.
  children: ReactNode
}

// The left column: the app's name at the top, the datasets and documents in the middle, which scroll when they're
// longer than the window, and the theme and the account at the bottom.
export default function Sidebar({ loginRequired, onLoggedOut, children }: Props) {
  return (
    <aside className="sidebar" aria-label="Datasets and documents">
      <div className="sidebar-head">
        <div className="brand">
          <span className="logo" aria-hidden="true">
            <LensIcon />
          </span>
          <h1 className="app-name">Context-Lens</h1>
          <ApiStatus />
        </div>
        <p className="tagline">Ask questions about your documents and get answers you can check.</p>
      </div>
      <div className="sidebar-body">{children}</div>
      <footer className="sidebar-foot">
        <ThemeSwitch />
        {loginRequired && (
          <div className="account">
            <span className="avatar" aria-hidden="true">
              <LockIcon className="icon-sm" />
            </span>
            <p className="account-text">
              <span className="account-title">Signed in</span>
              <span className="account-sub">Password access</span>
            </p>
            <LogOutButton onLoggedOut={onLoggedOut} />
          </div>
        )}
      </footer>
    </aside>
  )
}
