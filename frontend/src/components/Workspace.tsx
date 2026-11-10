import { type KeyboardEvent, useEffect, useId, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import type { Dataset } from '../api/datasets.ts'
import { useDatasets } from '../hooks/useDatasets.ts'
import { useDocuments } from '../hooks/useDocuments.ts'
import { useMediaQuery } from '../hooks/useMediaQuery.ts'
import { useQuestions } from '../hooks/useQuestions.ts'
import Datasets from './Datasets.tsx'
import Documents from './Documents.tsx'
import QuestionsColumn from './QuestionsColumn.tsx'
import Sidebar from './Sidebar.tsx'
import SourcePanel, { type OpenSource } from './SourcePanel.tsx'
import TopBar from './TopBar.tsx'

// A window this wide has room for the sidebar's column. On a narrower one the sidebar is a drawer, opened from the top
// bar. The stylesheet switches at the same width.
const WIDE_ENOUGH_FOR_SIDEBAR = '(min-width: 900px)'
// On a window this narrow the source panel has no room for a column, and lies over the questions. The stylesheet
// switches at the same width.
const PANEL_OVER_QUESTIONS = '(max-width: 1279px)'

// Whether an element can take the focus back: still on the page, and not hidden, as the chips in a collapsed card are.
// jsdom has no checkVisibility and no layout, so there only being inside a hidden element counts.
function canTakeFocus(element: HTMLElement | null): element is HTMLElement {
  if (!element?.isConnected) return false
  return element.checkVisibility ? element.checkVisibility() : !element.closest('[hidden]')
}

type Props = {
  loginRequired: boolean
  onLoggedOut: () => void
}

// Everything behind the login. App takes it off the page when the user logs out or the session ends, so the next
// login starts it over: the datasets load again, and nothing picked, typed or answered before is left.
export default function Workspace({ loginRequired, onLoggedOut }: Props) {
  const { datasets, error, add, remove } = useDatasets()
  // Only what the user picked. The selected dataset is worked out from it on every render, so a
  // reloaded list needs no syncing: no choice, or a choice that's gone, means the newest dataset.
  const [chosenId, setChosenId] = useState<string | null>(null)
  // True while a dataset is being created or deleted or files are uploading, and each waits for the others: a new
  // dataset gets selected when it's ready, leaving the dataset mid-run would take its rows off the page, and a
  // dataset being deleted mustn't get new files or be left for another one halfway through.
  const [busy, setBusy] = useState(false)

  const selected = datasets?.find((dataset) => dataset.id === chosenId) ?? datasets?.at(-1)
  // Here because both columns need them: the sidebar lists them, and the questions column only offers to ask once
  // there's something to search. They go as soon as another dataset is selected.
  const documents = useDocuments(selected?.id)
  // The cards of every dataset asked about since the login. Only the selected dataset's show.
  const questions = useQuestions()
  const asked = selected && questions.byDataset[selected.id]
  // One source at a time, in the panel beside the cards.
  const [openSource, setOpenSource] = useState<OpenSource | null>(null)
  // Where the focus goes back to when it closes, the first that can take it, and the panel's heading, to give it to.
  const returnFocusTo = useRef<() => (HTMLElement | null)[]>(() => [])
  const panelHeading = useRef<HTMLHeadingElement>(null)
  // The question box, where the focus goes when the panel closes and nothing in the card that opened it can take it.
  const askBox = useRef<HTMLTextAreaElement>(null)
  // Lying over the questions, the panel is a modal sheet: the rest of the page is inert, under a backdrop that closes
  // the panel on a click. Otherwise the controls it half covers would still take clicks and the focus.
  const panelOverQuestions = useMediaQuery(PANEL_OVER_QUESTIONS)
  const sheet = openSource !== null && panelOverQuestions
  // The sidebar as a drawer over the page, on a narrow window. The Menu button opens it and takes the focus back.
  // Choosing a dataset leaves it open: on Windows and Linux every arrow key on the select chooses one.
  const [drawerOpen, setDrawerOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const sidebar = useRef<HTMLElement>(null)
  const sidebarId = useId()
  // The controls in the sidebar that get the user started, which the empty questions column points to.
  const nameInput = useRef<HTMLInputElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  // The dataset the open source belongs to. When another one is selected, however that happens, the panel closes
  // during this very render, so it never shows beside the other dataset's cards, and doesn't open again on return.
  const [sourceDatasetId, setSourceDatasetId] = useState(selected?.id)
  if (sourceDatasetId !== selected?.id) {
    setSourceDatasetId(selected?.id)
    setOpenSource(null)
  }

  // When the window grows wide enough for the sidebar's column, as when a tablet turns, the drawer closes: the page
  // behind it would stay inert otherwise, and it would open again by itself when the window got narrow.
  useEffect(() => {
    if (!drawerOpen) return
    const wide = window.matchMedia?.(WIDE_ENOUGH_FOR_SIDEBAR)
    if (!wide) return
    const closeWhenWide = () => {
      if (wide.matches) setDrawerOpen(false)
    }
    wide.addEventListener('change', closeWhenWide)
    return () => wide.removeEventListener('change', closeWhenWide)
  }, [drawerOpen])

  function handleCreated(dataset: Dataset) {
    add(dataset)
    setChosenId(dataset.id)
  }

  function handleDeleted(id: string) {
    remove(id)
    questions.forget(id)
  }

  // Each of these renders at once with flushSync, so the element that should get the focus can take it: the drawer,
  // which a screen reader then names, or the Menu button, since whatever had the focus slides out of view.
  function openDrawer() {
    flushSync(() => setDrawerOpen(true))
    sidebar.current?.focus()
  }

  function closeDrawer() {
    flushSync(() => setDrawerOpen(false))
    menuButton.current?.focus()
  }

  // The empty questions column has a button for the control in the sidebar that gets the user started: the new
  // dataset's name, or the files to add. On a narrow window the sidebar is a drawer, which opens first. The control
  // shows its focus ring even after a click, since the file input is hidden and only its zone's ring says where the
  // focus went. If the control can't take the focus, as the file input can't while files upload, the drawer takes it,
  // as when Menu opens it.
  function showInSidebar(control: HTMLElement | null) {
    const narrow = window.matchMedia?.(WIDE_ENOUGH_FOR_SIDEBAR).matches === false
    if (narrow) flushSync(() => setDrawerOpen(true))
    control?.focus({ focusVisible: true })
    if (narrow && document.activeElement !== control) sidebar.current?.focus()
  }

  // Escape closes the drawer, unless something inside it has used the key already, as the new dataset form does.
  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape' && drawerOpen && !event.defaultPrevented) {
      event.preventDefault()
      closeDrawer()
    }
  }

  // Each of these renders at once with flushSync, so the element that should get the focus is already there, and no
  // longer inert under the panel.
  function openSourceFrom(source: OpenSource, button: HTMLButtonElement, fallbacks?: () => (HTMLElement | null)[]) {
    returnFocusTo.current = () => [button, ...(fallbacks?.() ?? []), askBox.current]
    flushSync(() => setOpenSource(source))
    panelHeading.current?.focus()
  }

  // The chip that opened it may be gone or hidden by now, as when its card's reply has been answered or the card has
  // been collapsed, and then its card says where the focus goes instead, so it isn't left on the page's body.
  function closeSource() {
    flushSync(() => setOpenSource(null))
    returnFocusTo.current().find(canTakeFocus)?.focus()
    returnFocusTo.current = () => []
  }

  // A chip opens its source, or closes it when it's the one open.
  function toggleSource(source: OpenSource, button: HTMLButtonElement, fallbacks?: () => (HTMLElement | null)[]) {
    if (source.key === openSource?.key) closeSource()
    else openSourceFrom(source, button, fallbacks)
  }

  const className = ['workspace', openSource && 'with-source', drawerOpen && 'drawer-open'].filter(Boolean).join(' ')

  return (
    <div className={className} onKeyDown={handleKeyDown}>
      <TopBar
        datasetName={selected?.name}
        sidebarId={sidebarId}
        drawerOpen={drawerOpen}
        menuRef={menuButton}
        onMenu={drawerOpen ? closeDrawer : openDrawer}
        inert={sheet}
      />
      <Sidebar
        id={sidebarId}
        ref={sidebar}
        drawerOpen={drawerOpen}
        inert={sheet}
        loginRequired={loginRequired}
        onLoggedOut={onLoggedOut}
      >
        <Datasets
          datasets={datasets}
          error={error}
          selected={selected}
          documentCount={documents.documents?.length ?? null}
          busy={busy}
          nameInputRef={nameInput}
          onBusyChange={setBusy}
          onChoose={setChosenId}
          onCreated={handleCreated}
          onDeleted={handleDeleted}
        />
        {selected && (
          // Keyed by the dataset, so the results of an upload and any open question about a document stay with it.
          <Documents
            key={selected.id}
            datasetId={selected.id}
            documents={documents.documents}
            error={documents.error}
            busy={busy}
            fileInputRef={fileInput}
            onBusyChange={setBusy}
            onUploaded={documents.reload}
            onDeleted={documents.remove}
          />
        )}
      </Sidebar>
      {/* Only for the pointer: a tap beside the drawer closes it. The keyboard has Escape, and the Menu button. */}
      {drawerOpen && <div className="drawer-backdrop" aria-hidden="true" onClick={closeDrawer} />}
      <QuestionsColumn
        dataset={selected}
        noDatasets={datasets?.length === 0}
        documentCount={documents.documents?.length ?? null}
        questions={asked?.questions ?? []}
        failedAsk={asked?.failedAsk ?? null}
        askBoxRef={askBox}
        onAsk={questions.ask}
        onReply={questions.reply}
        onCreateDataset={() => showInSidebar(nameInput.current)}
        onAddFiles={() => showInSidebar(fileInput.current)}
        openSource={openSource?.key ?? null}
        onToggleSource={toggleSource}
        inert={drawerOpen || sheet}
      />
      {/* Only for the pointer, like the drawer's. The keyboard has Escape, and the close button. */}
      {sheet && <div className="sheet-backdrop" aria-hidden="true" onClick={closeSource} />}
      {openSource && (
        <SourcePanel source={openSource} headingRef={panelHeading} inert={drawerOpen} onClose={closeSource} />
      )}
    </div>
  )
}
