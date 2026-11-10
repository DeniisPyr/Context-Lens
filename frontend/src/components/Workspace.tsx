import { useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import type { Dataset } from '../api/datasets.ts'
import { useDatasets } from '../hooks/useDatasets.ts'
import { useDocuments } from '../hooks/useDocuments.ts'
import { useQuestions } from '../hooks/useQuestions.ts'
import Datasets from './Datasets.tsx'
import Documents from './Documents.tsx'
import QuestionsColumn from './QuestionsColumn.tsx'
import Sidebar from './Sidebar.tsx'
import SourcePanel, { type OpenSource } from './SourcePanel.tsx'

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
  // One source at a time, in the panel beside the cards.
  const [openSource, setOpenSource] = useState<OpenSource | null>(null)
  // The chip that opened it, to give the focus back to when it closes, and the panel's heading, to give it to.
  const opener = useRef<HTMLButtonElement | null>(null)
  const panelHeading = useRef<HTMLHeadingElement>(null)

  // The dataset the open source belongs to. When another one is selected, however that happens, the panel closes
  // during this very render, so it never shows beside the other dataset's cards, and doesn't open again on return.
  const [sourceDatasetId, setSourceDatasetId] = useState(selected?.id)
  if (sourceDatasetId !== selected?.id) {
    setSourceDatasetId(selected?.id)
    setOpenSource(null)
  }

  function handleCreated(dataset: Dataset) {
    add(dataset)
    setChosenId(dataset.id)
  }

  function handleDeleted(id: string) {
    remove(id)
    questions.forget(id)
  }

  // Each of these renders at once with flushSync, so the element that should get the focus is already there.
  function openSourceFrom(source: OpenSource, button: HTMLButtonElement) {
    opener.current = button
    flushSync(() => setOpenSource(source))
    panelHeading.current?.focus()
  }

  // The chip may be gone by now, as when its card's reply has been answered, and then there's no chip to go back to.
  function closeSource() {
    flushSync(() => setOpenSource(null))
    if (opener.current?.isConnected) opener.current.focus()
    opener.current = null
  }

  // A chip opens its source, or closes it when it's the one open.
  function toggleSource(source: OpenSource, button: HTMLButtonElement) {
    if (source.key === openSource?.key) closeSource()
    else openSourceFrom(source, button)
  }

  return (
    <div className={openSource ? 'workspace with-source' : 'workspace'}>
      <Sidebar loginRequired={loginRequired} onLoggedOut={onLoggedOut}>
        <Datasets
          datasets={datasets}
          error={error}
          selected={selected}
          documentCount={documents.documents?.length ?? null}
          busy={busy}
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
            onBusyChange={setBusy}
            onUploaded={documents.reload}
            onDeleted={documents.remove}
          />
        )}
      </Sidebar>
      <QuestionsColumn
        dataset={selected}
        noDatasets={datasets?.length === 0}
        documentCount={documents.documents?.length ?? null}
        questions={(selected && questions.byDataset[selected.id]) ?? []}
        onAsk={questions.ask}
        onReply={questions.reply}
        openSource={openSource?.key ?? null}
        onToggleSource={toggleSource}
      />
      {openSource && <SourcePanel source={openSource} headingRef={panelHeading} onClose={closeSource} />}
    </div>
  )
}
