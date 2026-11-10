import { useId, useState } from 'react'
import type { Citation } from '../api/ask.ts'
import { FileIcon, PdfIcon } from './icons.tsx'
import LineViewer from './LineViewer.tsx'

// A PDF's reader finds a place in it by its page. A text file has only lines.
function citationLabel({ start_line, end_line, start_page, end_page }: Citation) {
  if (start_page === null) return start_line === end_line ? `Line ${start_line}` : `Lines ${start_line}–${end_line}`
  return start_page === end_page ? `Page ${start_page}` : `Pages ${start_page}–${end_page}`
}

type Props = {
  citations: Citation[]
}

// A card for each citation: the file, a chip with its lines or pages that shows them, and the exact quote.
export default function Sources({ citations }: Props) {
  // One at a time. A new answer gets its own list, so it starts closed.
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  // One answer can cite several files, and a chip alone doesn't say which, so each is described by its filename for
  // a screen reader moving from button to button.
  const filenameId = useId()

  return (
    <ul className="source-list">
      {/* Keyed by position: two citations can be identical, and this list never reorders. */}
      {citations.map((citation, index) => (
        <li key={index} className="source-card">
          <div className="source-top">
            {/* Only a PDF's citation has pages, so that's what tells it from a text file's. */}
            {citation.start_page === null ? (
              <FileIcon className="source-icon" />
            ) : (
              <PdfIcon className="source-icon pdf" />
            )}
            <span className="source-name" id={`${filenameId}-${index}`}>
              {citation.filename}
            </span>
            <button
              type="button"
              className="source-chip"
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
  )
}
