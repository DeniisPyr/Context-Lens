import { deleteDocument, type DocumentSummary } from '../api/documents.ts'
import ConfirmDelete from './ConfirmDelete.tsx'
import { FileIcon, PdfIcon, TrashIcon } from './icons.tsx'
import Upload from './Upload.tsx'

// A PDF is counted in pages, the way its reader knows it. A text file has only lines.
function lengthOf({ line_count, page_count }: DocumentSummary) {
  if (page_count === null) return line_count === 1 ? '1 line' : `${line_count} lines`
  return page_count === 1 ? '1 page' : `${page_count} pages`
}

type Props = {
  datasetId: string
  documents: DocumentSummary[] | null
  error: string | null
  busy: boolean
  onBusyChange: (busy: boolean) => void
  onUploaded: () => void
  onDeleted: (id: string) => void
}

export default function Documents({ datasetId, documents, error, busy, onBusyChange, onUploaded, onDeleted }: Props) {
  async function handleDelete(doc: DocumentSummary) {
    await deleteDocument(doc.id)
    onDeleted(doc.id)
  }

  return (
    <section className="documents">
      <div className="section-head">
        <h2>Documents</h2>
        {documents && <span className="count">{documents.length}</span>}
      </div>
      {error && <p role="alert">{error}</p>}
      {documents?.length === 0 && <p className="documents-empty">No documents yet.</p>}
      {documents && documents.length > 0 && (
        <ul className="document-list" aria-label="Documents">
          {/* Keyed by id, so an open question stays with its document when the list reloads, and goes with it. */}
          {documents.map((doc) => (
            <li key={doc.id} className="document-row">
              {/* Only a PDF has pages, so that's what tells it from a text file. */}
              <span className={doc.page_count === null ? 'file-tile' : 'file-tile pdf'} aria-hidden="true">
                {doc.page_count === null ? <FileIcon /> : <PdfIcon />}
              </span>
              <span className="document-meta">
                {/* Cut short with an ellipsis when it's too long for the sidebar, so the whole name is its title. */}
                <span className="document-name" title={doc.filename}>
                  {doc.filename}
                </span>
                <span className="document-length">{lengthOf(doc)}</span>
              </span>
              {/* Only this row waits for its delete. The page isn't busy, so other rows and uploads still work. */}
              <ConfirmDelete
                label="Delete"
                accessibleLabel={`Delete ${doc.filename}`}
                icon={<TrashIcon className="icon-sm" />}
                iconOnly
                className="row-delete"
                question={`Delete ${doc.filename}?`}
                disabled={busy}
                onConfirm={() => handleDelete(doc)}
              />
            </li>
          ))}
        </ul>
      )}
      <Upload datasetId={datasetId} busy={busy} onBusyChange={onBusyChange} onUploaded={onUploaded} />
    </section>
  )
}
