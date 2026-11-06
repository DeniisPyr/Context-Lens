import { useId, useRef, useState } from 'react'
import { flushSync } from 'react-dom'

type Props = {
  // The button's text, and its accessible name when the text alone wouldn't say what goes, as in a list.
  label: string
  accessibleLabel?: string
  question: string
  // While the page is busy, nothing can be deleted. Cancel still works.
  disabled: boolean
  // Deletes, and throws an Error with a readable message when it can't. After it works, the parent takes
  // whatever was deleted, and this with it, off the page.
  onConfirm: () => Promise<void>
}

// A Delete button that asks first, inline, and only deletes once the user confirms.
export default function ConfirmDelete({ label, accessibleLabel, question, disabled, onConfirm }: Props) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const deleteButton = useRef<HTMLButtonElement>(null)
  const confirmButton = useRef<HTMLButtonElement>(null)
  const questionId = useId()

  // Each of these renders at once with flushSync, so the button that should get the focus is already there.
  function handleAsk() {
    flushSync(() => {
      setConfirming(true)
      setError(null)
    })
    confirmButton.current?.focus()
  }

  function handleCancel() {
    flushSync(() => setConfirming(false))
    deleteButton.current?.focus()
  }

  async function handleConfirm() {
    setDeleting(true)
    try {
      await onConfirm()
    } catch (err) {
      flushSync(() => {
        setDeleting(false)
        setConfirming(false)
        setError((err as Error).message)
      })
      deleteButton.current?.focus()
    }
  }

  return (
    <>
      {confirming ? (
        // A group named by the question, so a screen reader says what the focused Delete button deletes.
        <div className="confirm-delete" role="group" aria-labelledby={questionId}>
          <span id={questionId}>{question}</span>
          <button
            ref={confirmButton}
            type="button"
            className="danger-button"
            disabled={disabled || deleting}
            onClick={handleConfirm}
          >
            Delete
          </button>
          <button type="button" disabled={deleting} onClick={handleCancel}>
            Cancel
          </button>
        </div>
      ) : (
        <button ref={deleteButton} type="button" aria-label={accessibleLabel} disabled={disabled} onClick={handleAsk}>
          {label}
        </button>
      )}
      {error && (
        <p className="delete-error" role="alert">
          {error}
        </p>
      )}
    </>
  )
}
