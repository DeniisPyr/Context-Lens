import { deleteDocument, type DocumentSummary } from '../api/documents.ts'
import ConfirmDelete from './ConfirmDelete.tsx'
import UploadForm from './UploadForm.tsx'

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
    <section>
      <h2>Documents</h2>
      <UploadForm datasetId={datasetId} busy={busy} onBusyChange={onBusyChange} onUploaded={onUploaded} />
      {error && <p role="alert">{error}</p>}
      {documents?.length === 0 && <p>No documents yet.</p>}
      {documents && documents.length > 0 && (
        <ul className="document-list" aria-label="Documents">
          {/* Keyed by id, so an open question stays with its document when the list reloads, and goes with it. */}
          {documents.map((doc) => (
            <li key={doc.id}>
              <span className="document-name">{doc.filename}</span>
              <span className="line-count">
                {doc.line_count} {doc.line_count === 1 ? 'line' : 'lines'}
              </span>
              {/* Only this row waits for its delete. The page isn't busy, so other rows and uploads still work. */}
              <ConfirmDelete
                label="Delete"
                accessibleLabel={`Delete ${doc.filename}`}
                question={`Delete ${doc.filename}?`}
                disabled={busy}
                onConfirm={() => handleDelete(doc)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
