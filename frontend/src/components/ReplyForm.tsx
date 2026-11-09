import { type SubmitEvent, useState } from 'react'
import { type Answer, askQuestion, type Clarification, MAX_REPLY_LENGTH } from '../api/ask.ts'

type Props = {
  datasetId: string
  // The question as it was asked, which the reply is sent with.
  question: string
  clarifyingQuestion: string
  // Ask holds this, because the question can't be sent again while a reply is on its way.
  replying: boolean
  onReplyingChange: (replying: boolean) => void
  onAnswered: (answer: Answer, clarification: Clarification) => void
}

// Replies to a clarifying question, and gets the answer to the question it was asked about.
export default function ReplyForm({
  datasetId,
  question,
  clarifyingQuestion,
  replying,
  onReplyingChange,
  onAnswered,
}: Props) {
  const [reply, setReply] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const replied = reply.trim()
    if (!replied) {
      setError('Type a reply first.')
      return
    }

    const clarification = { question: clarifyingQuestion, reply: replied }
    onReplyingChange(true)
    setError(null)
    try {
      onAnswered(await askQuestion(datasetId, question, clarification), clarification)
    } catch (err) {
      // The typed reply stays, so it can be sent again.
      setError((err as Error).message)
    } finally {
      onReplyingChange(false)
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
      <button type="submit" disabled={replying}>
        {replying ? 'Replying…' : 'Reply'}
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}
