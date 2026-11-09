import { useState } from 'react'
import type { Dataset } from '../api/datasets.ts'
import { useDatasets } from '../hooks/useDatasets.ts'
import DatasetContents from './DatasetContents.tsx'
import Datasets from './Datasets.tsx'

// Everything behind the login. App takes it off the page when the user logs out, so the next login starts it over:
// the datasets load again, and nothing picked, typed or answered before is left.
export default function Workspace() {
  const { datasets, error, add, remove } = useDatasets()
  // Only what the user picked. The selected dataset is worked out from it on every render, so a
  // reloaded list needs no syncing: no choice, or a choice that's gone, means the newest dataset.
  const [chosenId, setChosenId] = useState<string | null>(null)
  // True while a dataset is being created or deleted or files are uploading, and each waits for the others: a new
  // dataset gets selected when it's ready, leaving the dataset mid-run would take its rows off the page, and a
  // dataset being deleted mustn't get new files or be left for another one halfway through.
  const [busy, setBusy] = useState(false)

  const selected = datasets?.find((dataset) => dataset.id === chosenId) ?? datasets?.at(-1)

  function handleCreated(dataset: Dataset) {
    add(dataset)
    setChosenId(dataset.id)
  }

  return (
    <>
      <Datasets
        datasets={datasets}
        error={error}
        selected={selected}
        busy={busy}
        onBusyChange={setBusy}
        onChoose={setChosenId}
        onCreated={handleCreated}
        onDeleted={remove}
      />
      {selected && (
        <DatasetContents
          key={selected.id}
          datasetId={selected.id}
          datasetName={selected.name}
          busy={busy}
          onBusyChange={setBusy}
        />
      )}
    </>
  )
}
