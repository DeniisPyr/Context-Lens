import { type Dataset, deleteDataset } from '../api/datasets.ts'
import ConfirmDelete from './ConfirmDelete.tsx'
import CreateDatasetForm from './CreateDatasetForm.tsx'

type Props = {
  datasets: Dataset[] | null
  error: string | null
  selected: Dataset | undefined
  busy: boolean
  onBusyChange: (busy: boolean) => void
  onChoose: (id: string) => void
  onCreated: (dataset: Dataset) => void
  onDeleted: (id: string) => void
}

export default function Datasets({
  datasets,
  error,
  selected,
  busy,
  onBusyChange,
  onChoose,
  onCreated,
  onDeleted,
}: Props) {
  // The page is busy meanwhile, so nobody can switch to another dataset, upload or create one halfway through.
  async function handleDelete(dataset: Dataset) {
    onBusyChange(true)
    try {
      await deleteDataset(dataset.id)
      onDeleted(dataset.id)
    } finally {
      onBusyChange(false)
    }
  }

  return (
    <section>
      <h2>Datasets</h2>
      {error && <p role="alert">{error}</p>}
      {datasets?.length === 0 && <p>Create a dataset to get started.</p>}
      {selected && (
        <div className="dataset-choice">
          <label>
            Dataset
            <select value={selected.id} disabled={busy} onChange={(event) => onChoose(event.target.value)}>
              {datasets?.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {dataset.name}
                </option>
              ))}
            </select>
          </label>
          {/* Keyed by the dataset, so an open question closes when another one is selected, whatever selects it. */}
          <ConfirmDelete
            key={selected.id}
            label="Delete dataset"
            question={`Delete ${selected.name} and all its documents? This can't be undone.`}
            disabled={busy}
            onConfirm={() => handleDelete(selected)}
          />
        </div>
      )}
      <CreateDatasetForm busy={busy} onBusyChange={onBusyChange} onCreated={onCreated} />
    </section>
  )
}
