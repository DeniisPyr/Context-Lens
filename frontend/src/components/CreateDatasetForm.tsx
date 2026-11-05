import { type SubmitEvent, useState } from 'react'
import { createDataset, type Dataset, MAX_DATASET_NAME_LENGTH } from '../api/datasets.ts'

export default function CreateDatasetForm({ onCreated }: { onCreated: (dataset: Dataset) => void }) {
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Type a name first.')
      return
    }

    setCreating(true)
    setError(null)
    try {
      onCreated(await createDataset(trimmed))
      setName('')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setCreating(false)
    }
  }

  return (
    <form className="dataset-form" onSubmit={handleSubmit}>
      <label>
        New dataset name
        <input
          type="text"
          maxLength={MAX_DATASET_NAME_LENGTH}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <button type="submit" disabled={creating}>
        Create
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}
