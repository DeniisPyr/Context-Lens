import type { Dataset } from '../api/datasets.ts'
import CreateDatasetForm from './CreateDatasetForm.tsx'

type Props = {
  datasets: Dataset[] | null
  error: string | null
  selectedId: string | undefined
  onChoose: (id: string) => void
  onCreated: (dataset: Dataset) => void
}

export default function Datasets({ datasets, error, selectedId, onChoose, onCreated }: Props) {
  return (
    <section>
      <h2>Datasets</h2>
      {error && <p role="alert">{error}</p>}
      {datasets?.length === 0 && <p>Create a dataset to get started.</p>}
      {selectedId && (
        <label className="dataset-choice">
          Dataset
          <select value={selectedId} onChange={(event) => onChoose(event.target.value)}>
            {datasets?.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <CreateDatasetForm onCreated={onCreated} />
    </section>
  )
}
