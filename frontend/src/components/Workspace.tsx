import { useState } from 'react'
import type { Dataset } from '../api/datasets.ts'
import { useDatasets } from '../hooks/useDatasets.ts'
import { useDocuments } from '../hooks/useDocuments.ts'
import Datasets from './Datasets.tsx'
import Documents from './Documents.tsx'
import QuestionsColumn from './QuestionsColumn.tsx'
import Sidebar from './Sidebar.tsx'

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

  function handleCreated(dataset: Dataset) {
    add(dataset)
    setChosenId(dataset.id)
  }

  return (
    <div className="workspace">
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
          onDeleted={remove}
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
        hasDocuments={documents.documents !== null && documents.documents.length > 0}
      />
    </div>
  )
}
