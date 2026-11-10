import { type SubmitEvent, useState } from 'react'
import { MAX_REPLY_LENGTH } from '../api/ask.ts'

type Props = {
  // True while this reply is on its way.
  replying: boolean
  // True while any question or reply of the dataset is on its way, this one included.
  disabled: boolean
  // Sends the reply with the question it clarifies, and throws an Error with a readable message when it can't. After
  // it works, the card shows the answer in place of this form.
  onReply: (reply: string) => Promise<void>
}

// Replies to a card's clarifying question, inside the card, and gets the answer to the question it was asked about.
export default function ReplyForm({ replying, disabled, onReply }: Props) {
  const [reply, setReply] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const replied = reply.trim()
    if (!replied) {
      setError('Type a reply first.')
      return
    }

    setError(null)
    try {
      await onReply(replied)
    } catch (err) {
      // The typed reply stays, so it can be sent again.
      setError((err as Error).message)
    }
  }

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
