import type { RefObject } from 'react'
import { LensIcon, MenuIcon, StackIcon, XIcon } from './icons.tsx'

type Props = {
  // The name of the selected dataset. undefined while the datasets load, or when there are none.
  datasetName: string | undefined
  // The sidebar, which the Menu button opens as a drawer.
  sidebarId: string
  drawerOpen: boolean
  // Workspace gives the focus back to the button when the drawer closes.
  menuRef: RefObject<HTMLButtonElement | null>
  onMenu: () => void
  // True while the source panel is open over the page as a modal sheet: the drawer waits until it closes.
  inert: boolean
}

// The bar across the top of a narrow window, where the sidebar has no room for its column: the button that opens it as
// a drawer, and what would show at its top, the app's name and the dataset the questions are about. The stylesheet
// hides the bar on a window wide enough for the sidebar.
export default function TopBar({ datasetName, sidebarId, drawerOpen, menuRef, onMenu, inert }: Props) {
  return (
    <header className="top-bar" inert={inert}>
      <button
        ref={menuRef}
        type="button"
        className="menu-button"
        aria-expanded={drawerOpen}
        aria-controls={sidebarId}
        onClick={onMenu}
      >
        {drawerOpen ? <XIcon /> : <MenuIcon />}
        Menu
      </button>
      <span className="logo" aria-hidden="true">
        <LensIcon />
      </span>
      <p className="top-bar-title">
        <span className="top-bar-name">Context-Lens</span>
        {datasetName && (
          <span className="top-bar-dataset">
            <StackIcon className="icon-sm" />
            <span className="top-bar-dataset-name">{datasetName}</span>
          </span>
        )}
      </p>
    </header>
  )
}
