import { type SubmitEvent, useState } from 'react'
import { createDataset, type Dataset, MAX_DATASET_NAME_LENGTH } from '../api/datasets.ts'

type Props = {
  busy: boolean
  onBusyChange: (busy: boolean) => void
  onCreated: (dataset: Dataset) => void
}

export default function CreateDatasetForm({ busy, onBusyChange, onCreated }: Props) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Type a name first.')
      return
    }

    onBusyChange(true)
    setError(null)
    try {
      onCreated(await createDataset(trimmed))
      setName('')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      onBusyChange(false)
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
      <button type="submit" disabled={busy}>
        Create
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}
