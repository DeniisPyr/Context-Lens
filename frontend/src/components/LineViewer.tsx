import { useEffect, useRef, useState } from 'react'
import type { Citation } from '../api/ask.ts'
import { type DocumentDetail, getDocument } from '../api/documents.ts'

// A 1 MB file can hold up to a million lines, so only this many around the citation are shown at first.
const CONTEXT_LINES = 10

export default function LineViewer({ citation }: { citation: Citation }) {
  const { document_id, start_line, end_line } = citation
  const [doc, setDoc] = useState<DocumentDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [linesBefore, setLinesBefore] = useState(CONTEXT_LINES)
  const [linesAfter, setLinesAfter] = useState(CONTEXT_LINES)
  const firstCitedLine = useRef<HTMLLIElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    getDocument(document_id, controller.signal)
      .then(setDoc)
      .catch((err: Error) => {
        if (!controller.signal.aborted) setError(err.message)
      })
    return () => controller.abort()
  }, [document_id])

  // Depends only on the document, so showing more lines later doesn't scroll again.
  useEffect(() => {
    firstCitedLine.current?.scrollIntoView({ block: 'center' })
  }, [doc])

  if (error) {
    return (
      <p className="line-viewer" role="alert">
        {error}
      </p>
    )
  }
  if (!doc) {
    return (
      <p className="line-viewer" role="status">
        Loading the document…
      </p>
    )
  }

  const first = Math.max(1, start_line - linesBefore)
  const last = Math.min(doc.lines.length, end_line + linesAfter)

  return (
    <div className="line-viewer">
      {first > 1 && (
        <button type="button" className="link-button" onClick={() => setLinesBefore(linesBefore + CONTEXT_LINES)}>
          Show earlier lines
        </button>
      )}
      {/* Focusable so a keyboard can scroll it: the buttons around it aren't inside the box. */}
      <ol className="line-list" tabIndex={0} aria-label={`Lines of ${doc.filename}`}>
        {doc.lines.slice(first - 1, last).map((text, index) => {
          const number = first + index
          const cited = number >= start_line && number <= end_line
          return (
            <li
              key={number}
              ref={number === start_line ? firstCitedLine : undefined}
              aria-current={cited ? 'true' : undefined}
            >
              <span className="line-number">{number}</span>
              <span className="line-text">{text}</span>
            </li>
          )
        })}
      </ol>
      {last < doc.lines.length && (
        <button type="button" className="link-button" onClick={() => setLinesAfter(linesAfter + CONTEXT_LINES)}>
          Show later lines
        </button>
      )}
    </div>
  )
}
