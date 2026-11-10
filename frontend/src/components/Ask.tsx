import { type KeyboardEvent, type RefObject, type SubmitEvent, useId, useState } from 'react'
import { MAX_QUESTION_LENGTH } from '../api/ask.ts'
import type { Failure } from '../hooks/useQuestions.ts'
import { ArrowUpIcon } from './icons.tsx'

type Props = {
  datasetName: string
  // True while a question of this dataset is on its way.
  asking: boolean
  // True while a question or a reply of this dataset is on its way: the next question waits for it.
  waiting: boolean
  // The last question about this dataset that couldn't be asked, until the next one is sent.
  failure: Failure | null
  // The question box, which Workspace gives the focus to when nothing better can take it.
  boxRef: RefObject<HTMLTextAreaElement | null>
  // Adds the question's card and asks the whole dataset, with the question as typed: the backend searches all its
  // documents for the passages that answer it. A question that can't be asked comes back as the failure.
  onAsk: (question: string) => void
}

const counted = (count: number) => count.toLocaleString('en-US')

// The box at the bottom of the questions column, which starts it over for another dataset, so nothing typed
// about one dataset is sent to another.
export default function Ask({ datasetName, asking, waiting, failure, boxRef, onAsk }: Props) {
  // A question that couldn't be asked is back in the box as it was typed, also when the user comes back to the
  // dataset, so it can be sent again.
  const [question, setQuestion] = useState(failure?.draft ?? '')
  const [empty, setEmpty] = useState(false)
  // The failure the box has seen. One that comes while the box is on the page puts its question back too, unless
  // something new was typed meanwhile.
  const [seenFailure, setSeenFailure] = useState(failure)
  const questionId = useId()
  const hintId = useId()

  if (failure !== seenFailure) {
    setSeenFailure(failure)
    if (failure) {
      setEmpty(false)
      if (question === '') setQuestion(failure.draft)
    }
  }

  function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    // Enter sends without the button, so it's checked here too.
    if (waiting) return
    if (!question.trim()) {
      setEmpty(true)
      return
    }

    // The question has its card now, so the box is free for the next one.
    setEmpty(false)
    setQuestion('')
    onAsk(question)
  }

  // Enter sends, and Shift+Enter starts a new line. While an input method is composing, Enter picks the characters
  // instead. Safari ends the composition before the keydown, but still marks that keydown with the code 229.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229) return
    event.preventDefault()
    event.currentTarget.form?.requestSubmit()
  }

  const error = empty ? 'Type a question first.' : failure?.error

  return (
    <div className="ask-bar">
      <form className="ask-form" onSubmit={handleSubmit}>
        <label className="visually-hidden" htmlFor={questionId}>
          Question
        </label>
        <textarea
          ref={boxRef}
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
