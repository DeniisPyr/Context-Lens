import type { Answer as AnswerResult, Citation } from '../api/ask.ts'

function lineLabel({ start_line, end_line }: Citation) {
  return start_line === end_line ? `Line ${start_line}` : `Lines ${start_line}–${end_line}`
}

export default function Answer({ question, result }: { question: string; result: AnswerResult }) {
  return (
    <article className="answer">
      <p className="answer-asked">You asked: {question}</p>
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
                  <span>{citation.filename}</span>
                  <span className="line-count">{lineLabel(citation)}</span>
                </div>
                <blockquote>{citation.quote}</blockquote>
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  )
}
