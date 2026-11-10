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
  // While the dataset is being created, the form can't be closed: an error would have nowhere to show, and the
  // dataset would be selected all the same.
  const [creating, setCreating] = useState(false)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Type a name first.')
      return
    }

    setError(null)
    setCreating(true)
    try {
      await onCreate(trimmed)
    } catch (err) {
      // The typed name stays, so it can be fixed and sent again.
      setError((err as Error).message)
    } finally {
      setCreating(false)
    }
  }

  // Escape closes the form, as Cancel does. While the dataset is being created it does nothing, and the drawer the
  // form may be in stays open too, so what comes of it stays in view.
  function handleKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key !== 'Escape' || !onCancel) return
    event.preventDefault()
    if (!creating) onCancel()
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
          <button type="button" disabled={creating} onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}
