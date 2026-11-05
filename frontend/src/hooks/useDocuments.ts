import { useEffect, useState } from 'react'
import { type DocumentSummary, listDocuments } from '../api/documents.ts'

export function useDocuments(datasetId: string) {
  // null until the first load finishes, so "No documents yet." can't show before we know.
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Adding 1 re-runs the effect below: it aborts any request still running and loads the list again.
  const [reloadCount, setReloadCount] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    listDocuments(datasetId, controller.signal)
      .then((loaded) => {
        setDocuments(loaded)
        setError(null)
      })
      .catch((err: Error) => {
        if (!controller.signal.aborted) setError(err.message)
      })
    return () => controller.abort()
  }, [datasetId, reloadCount])

  function reload() {
    setReloadCount((count) => count + 1)
  }

  // Takes a deleted document off the list at once, so it can't be chosen while the list reloads from the server.
  function remove(id: string) {
    setDocuments((current) => current?.filter((doc) => doc.id !== id) ?? null)
    reload()
  }

  return { documents, error, reload, remove }
}
