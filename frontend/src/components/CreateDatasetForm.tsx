import { type KeyboardEvent, type RefObject, type SubmitEvent, useState } from 'react'
import { MAX_DATASET_NAME_LENGTH } from '../api/datasets.ts'

type Props = {
  // Datasets puts the focus in the field when the user opens the form.
  inputRef: RefObject<HTMLInputElement | null>
  busy: boolean
  // Creates the dataset, and throws an Error with a readable message when it can't. After it works, Datasets
  // closes this form, so nothing here needs resetting.
  onCreate: (name: string) => Promise<void>
  // Closes the form. Left out while there's no dataset yet, since creating one is then the only thing to do.
  onCancel?: () => void
}

export default function CreateDatasetForm({ inputRef, busy, onCreate, onCancel }: Props) {
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Type a name first.')
      return
    }

    setError(null)
    try {
      await onCreate(trimmed)
    } catch (err) {
      // The typed name stays, so it can be fixed and sent again.
      setError((err as Error).message)
    }
  }

  // Escape closes the form, as Cancel does.
  function handleKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === 'Escape' && onCancel) {
      event.preventDefault()
      onCancel()
    }
  }

  return (
    <form className="dataset-form" onSubmit={handleSubmit} onKeyDown={handleKeyDown}>
      <label>
        New dataset name
        <input
          ref={inputRef}
          type="text"
          maxLength={MAX_DATASET_NAME_LENGTH}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <div className="dataset-form-actions">
        <button type="submit" disabled={busy}>
          Create
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}
