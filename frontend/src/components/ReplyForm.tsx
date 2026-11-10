import { type SubmitEvent, useState } from 'react'
import { MAX_REPLY_LENGTH } from '../api/ask.ts'
import type { Failure } from '../hooks/useQuestions.ts'

type Props = {
  // True while this reply is on its way.
  replying: boolean
  // True while any question or reply of the dataset is on its way, this one included.
  disabled: boolean
  // The last reply to this card that couldn't be sent, until the next one is.
  failure: Failure | null
  // Sends the reply, as typed, with the question it clarifies. After it works, the card shows the answer in place of
  // this form. A reply that can't be sent comes back as the failure.
  onReply: (reply: string) => void
}

// Replies to a card's clarifying question, inside the card, and gets the answer to the question it was asked about.
export default function ReplyForm({ replying, disabled, failure, onReply }: Props) {
  // The typed reply stays in the box while it's sent, so it can be sent again if it fails. A reply that failed is
  // back in it when the card comes back with its dataset.
  const [reply, setReply] = useState(failure?.draft ?? '')
  const [empty, setEmpty] = useState(false)
  // The failure the form has seen. One that comes while the form is on the page puts the reply back too, unless
  // something new was typed meanwhile.
  const [seenFailure, setSeenFailure] = useState(failure)

  if (failure !== seenFailure) {
    setSeenFailure(failure)
    if (failure) {
      setEmpty(false)
      if (reply === '') setReply(failure.draft)
    }
  }

  function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!reply.trim()) {
      setEmpty(true)
      return
    }

    setEmpty(false)
    onReply(reply)
  }

  const error = empty ? 'Type a reply first.' : failure?.error

  return (
    <form className="reply-form" onSubmit={handleSubmit}>
      <label>
        Your reply
        <textarea
          rows={2}
          maxLength={MAX_REPLY_LENGTH}
          value={reply}
          onChange={(event) => setReply(event.target.value)}
        />
      </label>
      <div className="reply-actions">
        <button type="submit" disabled={disabled}>
          {replying ? 'Replying…' : 'Reply'}
        </button>
        {error && <p role="alert">{error}</p>}
      </div>
    </form>
  )
}
