import { useEffect, useState } from 'react'
import { type DocumentSummary, listDocuments } from '../api/documents.ts'

// The documents of one dataset, or of none while no dataset is selected.
export function useDocuments(datasetId: string | undefined) {
  // null until the first load finishes, so "No documents yet." can't show before we know.
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Adding 1 re-runs the effect below: it aborts any request still running and loads the list again.
  const [reloadCount, setReloadCount] = useState(0)
  // The dataset the list and the error belong to. When another one is selected, both go during this very render, so
  // the old list never shows under the new dataset, not even until the new one has loaded.
  const [listedId, setListedId] = useState(datasetId)
  if (listedId !== datasetId) {
    setListedId(datasetId)
    setDocuments(null)
    setError(null)
  }

  useEffect(() => {
    if (datasetId === undefined) return
    const controller = new AbortController()
    listDocuments(datasetId, controller.signal)
      .then((loaded) => {
        // The hook stays when the dataset changes, so a list that arrives after its request was aborted is dropped.
        if (controller.signal.aborted) return
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

  // Takes a deleted document off the list at once, without waiting for the reload: its row goes, and when it was
  // the last one, so does the ask box, since the dataset has nothing left to search.
  function remove(id: string) {
    setDocuments((current) => current?.filter((doc) => doc.id !== id) ?? null)
    reload()
  }

  return { documents, error, reload, remove }
}
