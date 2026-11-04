import { type SubmitEvent, useState } from 'react'
import { type Answer as AnswerResult, askQuestion, MAX_QUESTION_LENGTH } from '../api/ask.ts'
import type { DocumentSummary } from '../api/documents.ts'
import Answer from './Answer.tsx'

export default function Ask({ documents }: { documents: DocumentSummary[] | null }) {
  // Only what the user picked. The selected document is worked out from it on every render, so a
  // reloaded list needs no syncing: no choice, or a choice that's gone, means the newest document.
  const [chosenId, setChosenId] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The document and question are kept with the answer because the form stays editable.
  const [result, setResult] = useState<{ filename: string; question: string; answer: AnswerResult } | null>(null)

  const selected = documents?.find((doc) => doc.id === chosenId) ?? documents?.at(-1)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>, doc: DocumentSummary) {
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
      setResult({ filename: doc.filename, question: asked, answer: await askQuestion(doc.id, asked) })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setAsking(false)
    }
  }

  return (
    <section>
      <h2>Ask a question</h2>
      {selected ? (
        <form className="ask-form" onSubmit={(event) => handleSubmit(event, selected)}>
          <label>
            Document
            <select value={selected.id} onChange={(event) => setChosenId(event.target.value)}>
              {documents?.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.filename}
                </option>
              ))}
            </select>
          </label>
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
      {result && <Answer filename={result.filename} question={result.question} result={result.answer} />}
    </section>
  )
}
