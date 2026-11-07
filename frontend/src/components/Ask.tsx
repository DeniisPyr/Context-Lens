import { type SubmitEvent, useState } from 'react'
import { type Answer as AnswerResult, askQuestion, MAX_QUESTION_LENGTH } from '../api/ask.ts'
import Answer from './Answer.tsx'

type Props = {
  datasetId: string
  datasetName: string
  // Also false while the list is still loading, so the form only shows once there's something to search.
  hasDocuments: boolean
}

// Asks the whole dataset: the backend searches all its documents for the passages that answer the question.
export default function Ask({ datasetId, datasetName, hasDocuments }: Props) {
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The question is kept with the answer because the form stays editable. The dataset can't change under it:
  // App starts this section over for another dataset.
  const [result, setResult] = useState<{ question: string; answer: AnswerResult } | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const asked = question.trim()
    if (!asked) {
      setError('Type a question first.')
      return
    }

    setAsking(true)
    setError(null)
    setResult(null)
    try {
      setResult({ question: asked, answer: await askQuestion(datasetId, asked) })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setAsking(false)
    }
  }

  return (
    <section>
      <h2 className="ask-heading">Ask a question about {datasetName}</h2>
      {hasDocuments ? (
        <form className="ask-form" onSubmit={handleSubmit}>
          <label>
            Question
            <textarea
              rows={3}
              maxLength={MAX_QUESTION_LENGTH}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
          </label>
          <button type="submit" disabled={asking}>
            {asking ? 'Asking…' : 'Ask'}
          </button>
          {error && <p role="alert">{error}</p>}
        </form>
      ) : (
        <p>Upload a document to ask about it.</p>
      )}
      {result && <Answer datasetName={datasetName} question={result.question} result={result.answer} />}
    </section>
  )
}
