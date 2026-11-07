import { useId, useState } from 'react'
import type { Answer as AnswerResult, Citation } from '../api/ask.ts'
import LineViewer from './LineViewer.tsx'

function lineLabel({ start_line, end_line }: Citation) {
  return start_line === end_line ? `Line ${start_line}` : `Lines ${start_line}–${end_line}`
}

type Props = {
  datasetName: string
  question: string
  result: AnswerResult
}

export default function Answer({ datasetName, question, result }: Props) {
  // One at a time. Ask removes this component while a new question is sent, so a new answer starts closed.
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  // One answer can cite several files, and a lines button alone doesn't say which, so each is described by its
  // filename for a screen reader moving from button to button.
  const filenameId = useId()

  return (
    <article className="answer">
      <p className="answer-asked">
        You asked about {datasetName}: {question}
      </p>
      {result.status === 'not_found' ? (
        <p className="answer-not-found">{result.answer}</p>
      ) : (
        <>
          <p className="answer-text">{result.answer}</p>
          <h3>Sources</h3>
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
                    {lineLabel(citation)}
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
