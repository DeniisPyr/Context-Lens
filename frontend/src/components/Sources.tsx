import { useId } from 'react'
import type { Citation } from '../api/ask.ts'
import { citationLabel } from './citationLabel.ts'
import { FileIcon, PanelIcon, PdfIcon } from './icons.tsx'
import type { OpenSource } from './SourcePanel.tsx'

// Where a list of citations comes from, so each can be told apart in the panel: its card's answer or reply, the
// card's number, and whether they're the lines a clarifying question cites as the reason it asks.
export type SourceGroup = {
  key: string
  number: number
  why: boolean
}

export type SourceProps = {
  // The key of the source open in the panel, if any.
  openSource: string | null
  // Opens a source in the panel, or closes it when it's the open one. The button is where the focus goes back to.
  onToggleSource: (source: OpenSource, button: HTMLButtonElement) => void
}

type Props = SourceProps & {
  citations: Citation[]
  group: SourceGroup
}

// A card for each citation: the file, a chip with its lines or pages that shows them in the panel, and the exact quote.
export default function Sources({ citations, group, openSource, onToggleSource }: Props) {
  // One answer can cite several files, and a chip alone doesn't say which, so each is described by its filename for
  // a screen reader moving from button to button.
  const filenameId = useId()

  return (
    <ul className="source-list">
      {/* Keyed by position: two citations can be identical, and this list never reorders. Their keys in the panel are
          by position too, so two identical citations are still two sources. */}
      {citations.map((citation, index) => {
        const key = `${group.key}:${index}`
        const open = key === openSource
        return (
          <li key={index} className={open ? 'source-card showing' : 'source-card'}>
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
                aria-pressed={open}
                aria-describedby={`${filenameId}-${index}`}
                onClick={(event) =>
                  onToggleSource({ key, citation, number: group.number, why: group.why }, event.currentTarget)
                }
              >
                {citationLabel(citation)}
              </button>
              {open && (
                <span className="source-showing">
                  <PanelIcon className="icon-sm" />
                  Showing in viewer
                </span>
              )}
            </div>
            <blockquote>{citation.quote}</blockquote>
          </li>
        )
      })}
    </ul>
  )
}
