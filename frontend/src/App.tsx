import { useState } from 'react'
import type { Dataset } from './api/datasets.ts'
import ApiStatus from './components/ApiStatus.tsx'
import DatasetContents from './components/DatasetContents.tsx'
import Datasets from './components/Datasets.tsx'
import { useDatasets } from './hooks/useDatasets.ts'

export default function App() {
  const { datasets, error, add } = useDatasets()
  // Only what the user picked. The selected dataset is worked out from it on every render, so a
  // reloaded list needs no syncing: no choice, or a choice that's gone, means the newest dataset.
  const [chosenId, setChosenId] = useState<string | null>(null)

  const selected = datasets?.find((dataset) => dataset.id === chosenId) ?? datasets?.at(-1)

  function handleCreated(dataset: Dataset) {
    add(dataset)
    setChosenId(dataset.id)
  }

  return (
    <main>
      <h1>Context-Lens</h1>
      <p>Ask questions about your documents and get answers you can check.</p>
      <ApiStatus />
      <Datasets
        datasets={datasets}
        error={error}
        selectedId={selected?.id}
        onChoose={setChosenId}
        onCreated={handleCreated}
      />
      {selected && <DatasetContents key={selected.id} datasetId={selected.id} />}
    </main>
  )
}
