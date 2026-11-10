import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { Citation } from '../api/ask.ts'
import { type DocumentDetail, getDocument } from '../api/documents.ts'
import { ChevronDownIcon, ChevronUpIcon } from './icons.tsx'
import { pageOfLine } from './pageOfLine.ts'

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

  // A layout effect, so the reader never sees the top of the list before it jumps to the citation.
  // Depends only on the document, so showing more lines later doesn't scroll again.
  useLayoutEffect(() => {
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
  const pageStarts = doc.page_starts

  // A PDF numbers its lines from 1 on each page, as its reader counts them.
  const numberOnPage = (number: number) =>
    pageStarts === null ? number : number - pageStarts[pageOfLine(pageStarts, number) - 1] + 1

  // The page rows of a PDF that go right before a line: one for each page that starts on it, among them any pages with
  // no text, which start where the next page does. The first line shown also gets the row of its own page when it's
  // further down that page. Pages with no text at the end start on the line after the last.
  const pageRows = (number: number) => {
    if (pageStarts === null) return null
    const page = pageOfLine(pageStarts, number)
    const startingHere = page - pageOfLine(pageStarts, number - 1)
    const firstPage = startingHere === 0 && number === first ? page : page - startingHere + 1
    return Array.from({ length: page - firstPage + 1 }, (_, index) => {
      const rowPage = firstPage + index
      const empty = pageStarts[rowPage - 1] === (pageStarts[rowPage] ?? doc.lines.length + 1)
      return (
        <li key={rowPage} className="page-start">
          <h4>Page {rowPage}</h4>
          {empty && <p>No text on this page</p>}
        </li>
      )
    })
  }

  return (
    <div className="line-viewer">
      {first > 1 && (
        <button type="button" className="more-lines" onClick={() => setLinesBefore(linesBefore + CONTEXT_LINES)}>
          <ChevronUpIcon className="icon-sm" />
          Show earlier lines
        </button>
      )}
      {/* Focusable so a keyboard can scroll it: the buttons around it aren't inside the box. */}
      <ol className="line-list" tabIndex={0} aria-label={`Lines of ${doc.filename}`}>
        {doc.lines.slice(first - 1, last).map((text, index) => {
          const number = first + index
          const cited = number >= start_line && number <= end_line
          return (
            <Fragment key={number}>
              {pageRows(number)}
              <li ref={number === start_line ? firstCitedLine : undefined} aria-current={cited ? 'true' : undefined}>
                <span className="line-number">{numberOnPage(number)}</span>
                <span className="line-text">{text}</span>
              </li>
            </Fragment>
          )
        })}
        {last === doc.lines.length && pageRows(doc.lines.length + 1)}
      </ol>
      {last < doc.lines.length && (
        <button type="button" className="more-lines" onClick={() => setLinesAfter(linesAfter + CONTEXT_LINES)}>
          <ChevronDownIcon className="icon-sm" />
          Show later lines
        </button>
      )}
    </div>
  )
}
