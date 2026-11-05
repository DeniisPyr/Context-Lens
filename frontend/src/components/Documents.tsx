import type { DocumentSummary } from '../api/documents.ts'
import UploadForm from './UploadForm.tsx'

type Props = {
  datasetId: string
  documents: DocumentSummary[] | null
  error: string | null
  busy: boolean
  onBusyChange: (busy: boolean) => void
  onUploaded: () => void
}

export default function Documents({ datasetId, documents, error, busy, onBusyChange, onUploaded }: Props) {
  return (
    <section>
      <h2>Documents</h2>
      <UploadForm datasetId={datasetId} busy={busy} onBusyChange={onBusyChange} onUploaded={onUploaded} />
      {error && <p role="alert">{error}</p>}
      {documents?.length === 0 && <p>No documents yet.</p>}
      {documents && documents.length > 0 && (
        <ul className="document-list" aria-label="Documents">
          {documents.map((doc) => (
            <li key={doc.id}>
              <span>{doc.filename}</span>
              <span className="line-count">
                {doc.line_count} {doc.line_count === 1 ? 'line' : 'lines'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
