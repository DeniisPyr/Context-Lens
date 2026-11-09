import { useId, useState } from 'react'
import type { Answer as AnswerResult, Citation, Clarification } from '../api/ask.ts'
import LineViewer from './LineViewer.tsx'

// A PDF's reader finds a place in it by its page. A text file has only lines.
function citationLabel({ start_line, end_line, start_page, end_page }: Citation) {
  if (start_page === null) return start_line === end_line ? `Line ${start_line}` : `Lines ${start_line}–${end_line}`
  return start_page === end_page ? `Page ${start_page}` : `Pages ${start_page}–${end_page}`
}

type Props = {
  datasetName: string
  question: string
  // Only on the answer to a reply: the clarifying question and the reply, shown between the question and its answer.
  clarification?: Clarification
  result: AnswerResult
}

export default function Answer({ datasetName, question, clarification, result }: Props) {
  // One at a time. Ask removes this component while a new question is sent, and gives the answer to a reply a new
  // key, so a new answer starts closed.
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  // One answer can cite several files, and a lines or pages button alone doesn't say which, so each is described by
  // its filename for a screen reader moving from button to button.
  const filenameId = useId()

  return (
    <article className="answer">
      <p className="answer-asked">
        You asked about {datasetName}: {question}
      </p>
      {clarification && (
        <>
          <p className="answer-asked">I asked: {clarification.question}</p>
          <p className="answer-asked">You replied: {clarification.reply}</p>
        </>
      )}
      {result.status === 'not_found' ? (
        <p className="answer-not-found">{result.answer}</p>
      ) : (
        <>
          <p className="answer-text">{result.answer}</p>
          {/* A clarifying question cites the lines that give different answers: they're why it asks. */}
          <h3>{result.status === 'needs_clarification' ? "Why I'm asking" : 'Sources'}</h3>
          <ul className="citation-list">
            {/* Keyed by position: two citations can be identical, and this list never reorders. */}
            {result.citations.map((citation, index) => (
              <li key={index}>
                <div className="citation-source">
                  <span id={`${filenameId}-${index}`}>{citation.filename}</span>
                  <button
                    type="button"
                    className="link-button citation-lines"
                    aria-expanded={openIndex === index}
                    aria-describedby={`${filenameId}-${index}`}
                    onClick={() => setOpenIndex(openIndex === index ? null : index)}
                  >
                    {citationLabel(citation)}
                  </button>
                </div>
                <blockquote>{citation.quote}</blockquote>
                {openIndex === index && <LineViewer citation={citation} />}
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  )
}
