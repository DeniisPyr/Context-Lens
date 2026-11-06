import { useEffect, useState } from 'react'
import { type Dataset, listDatasets } from '../api/datasets.ts'

export function useDatasets() {
  // null until the first load finishes, so "Create a dataset to get started." can't show before we know.
  const [datasets, setDatasets] = useState<Dataset[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Adding 1 re-runs the effect below: it aborts any request still running and loads the list again.
  const [reloadCount, setReloadCount] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    listDatasets(controller.signal)
      .then((loaded) => {
        setDatasets(loaded)
        setError(null)
      })
      .catch((err: Error) => {
        if (!controller.signal.aborted) setError(err.message)
      })
    return () => controller.abort()
  }, [reloadCount])

  // Lists a new dataset at once, so the page can select it without waiting, and then reloads from the server.
  function add(dataset: Dataset) {
    setDatasets((current) => [...(current ?? []), dataset])
    setReloadCount((count) => count + 1)
  }

  // Takes a deleted dataset off the list at once, so the page moves away from it without waiting, and then reloads.
  function remove(id: string) {
    setDatasets((current) => current?.filter((dataset) => dataset.id !== id) ?? null)
    setReloadCount((count) => count + 1)
  }

  return { datasets, error, add, remove }
}
