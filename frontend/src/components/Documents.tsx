import { useEffect, useState } from 'react'
import { type DocumentSummary, listDocuments } from '../api/documents.ts'

export default function Documents() {
  // null until the first load finishes, so "No documents yet." can't show before we know.
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

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
  }, [])

  return (
    <section>
      <h2>Documents</h2>
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
