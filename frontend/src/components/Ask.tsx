import { type KeyboardEvent, type SubmitEvent, useId, useState } from 'react'
import { MAX_QUESTION_LENGTH } from '../api/ask.ts'
import { ArrowUpIcon } from './icons.tsx'

type Props = {
  datasetName: string
  // True while a question of this dataset is on its way.
  asking: boolean
  // True while a question or a reply of this dataset is on its way: the next question waits for it.
  waiting: boolean
  // Adds the question's card and asks the whole dataset: the backend searches all its documents for the passages that
  // answer it. Throws an Error with a readable message when it can't.
  onAsk: (question: string) => Promise<void>
}

const counted = (count: number) => count.toLocaleString('en-US')

// The box at the bottom of the questions column, which starts it over for another dataset, so nothing typed
// about one dataset is sent to another.
export default function Ask({ datasetName, asking, waiting, onAsk }: Props) {
  const [question, setQuestion] = useState('')
  const [error, setError] = useState<string | null>(null)
  const questionId = useId()
  const hintId = useId()

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    // Enter sends without the button, so it's checked here too.
    if (waiting) return
    const typed = question
    const asked = typed.trim()
    if (!asked) {
      setError('Type a question first.')
      return
    }

    // The question has its card now, so the box is free for the next one.
    setError(null)
    setQuestion('')
    try {
      await onAsk(asked)
    } catch (err) {
      setError((err as Error).message)
      // Back in the box as typed, so it can be sent again, unless something new was typed meanwhile.
      setQuestion((current) => (current === '' ? typed : current))
    }
  }

  // Enter sends, and Shift+Enter starts a new line. While an input method is composing, Enter picks the characters
  // instead. Safari ends the composition before the keydown, but still marks that keydown with the code 229.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229) return
    event.preventDefault()
    event.currentTarget.form?.requestSubmit()
  }

  return (
    <div className="ask-bar">
      <form className="ask-form" onSubmit={handleSubmit}>
        <label className="visually-hidden" htmlFor={questionId}>
          Question
        </label>
        <textarea
          id={questionId}
          rows={2}
          maxLength={MAX_QUESTION_LENGTH}
          placeholder={`Ask a question about ${datasetName}`}
          aria-describedby={hintId}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="ask-foot">
          <span className="ask-hint" id={hintId}>
            Include everything the question needs. Answers cite the exact lines.
          </span>
          <span className="ask-counter">
            {counted(question.length)} / {counted(MAX_QUESTION_LENGTH)}
          </span>
          <button type="submit" disabled={waiting}>
            {asking ? (
              'Asking…'
            ) : (
              <>
                Ask
                <ArrowUpIcon className="icon-sm" />
              </>
            )}
          </button>
        </div>
      </form>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
