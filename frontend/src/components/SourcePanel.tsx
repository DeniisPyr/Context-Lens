import type { KeyboardEvent, RefObject } from 'react'
import type { Citation } from '../api/ask.ts'
import { citationLabel } from './citationLabel.ts'
import { FileIcon, PdfIcon, ShieldCheckIcon, XIcon } from './icons.tsx'
import LineViewer from './LineViewer.tsx'

// The source open in the panel: one citation of one card.
export type OpenSource = {
  // Which citation of which card, unique on the page, so its chip can show that it's the open one.
  key: string
  citation: Citation
  // The number of its card, and whether it's one of the lines a clarifying question cites as the reason it asks.
  number: number
  why: boolean
}

type Props = {
  source: OpenSource
  // Workspace moves the focus here when a source opens.
  headingRef: RefObject<HTMLHeadingElement | null>
  onClose: () => void
}

// The column on the right that shows a cited document around its citation: which file, where the quote was found and
// which question cites it, then the lines themselves.
export default function SourcePanel({ source, headingRef, onClose }: Props) {
  const { citation, number, why } = source
  const label = citationLabel(citation)

  // Escape closes it from anywhere inside, as the close button does.
  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
    }
  }

  return (
    <aside className="source-panel" aria-label="Source" onKeyDown={handleKeyDown}>
      <header className="source-panel-head">
        <div className="source-panel-top">
          {citation.start_page === null ? <FileIcon className="source-icon" /> : <PdfIcon className="source-icon pdf" />}
          {/* Takes the focus when the panel opens, so a screen reader starts with the file's name. */}
          <h2 ref={headingRef} tabIndex={-1} title={citation.filename}>
            {citation.filename}
          </h2>
          <span className="source-chip">{label}</span>
          <button type="button" className="icon-button source-panel-close" onClick={onClose}>
            <XIcon />
            <span className="visually-hidden">Close source</span>
          </button>
        </div>
        {/* The backend only returns a quote it found in the lines it cites. */}
        <p className="source-panel-meta">
          <ShieldCheckIcon className="icon-sm" />
          Quote found on {label.toLowerCase()} · cited in Q{number}
          {why && ' · why I asked'}
        </p>
      </header>
      {/* Keyed by the source, so another one starts over: its own request, its first window and its own scroll. */}
      <LineViewer key={source.key} citation={citation} />
    </aside>
  )
}
