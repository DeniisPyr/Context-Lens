import { useEffect, useState } from 'react'
import { type DocumentSummary, listDocuments } from '../api/documents.ts'
import UploadForm from './UploadForm.tsx'

export default function Documents() {
  // null until the first load finishes, so "No documents yet." can't show before we know.
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Adding 1 re-runs the effect below: it aborts any request still running and loads the list again.
  const [reloadCount, setReloadCount] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    listDocuments(controller.signal)
      .then((loaded) => {
        setDocuments(loaded)
        setError(null)
      })
      .catch((err: Error) => {
        if (!controller.signal.aborted) setError(err.message)
      })
    return () => controller.abort()
  }, [reloadCount])

  return (
    <section>
      <h2>Documents</h2>
      <UploadForm onUploaded={() => setReloadCount((count) => count + 1)} />
      {error && <p role="alert">{error}</p>}
      {documents?.length === 0 && <p>No documents yet.</p>}
      {documents && documents.length > 0 && (
        <ul className="document-list">
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
