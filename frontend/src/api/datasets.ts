import { send, sendDelete } from './request.ts'

export type Dataset = {
  id: string
  name: string
}

// Matches the limit on DatasetCreate in the backend.
export const MAX_DATASET_NAME_LENGTH = 100

export function listDatasets(signal: AbortSignal): Promise<Dataset[]> {
  return send('/api/datasets', { signal }, 'Could not load the datasets.')
}

export function createDataset(name: string): Promise<Dataset> {
  return send(
    '/api/datasets',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    },
    'Could not create the dataset.',
  )
}

// Resolves when the dataset and its documents are gone, including when they were gone already.
export function deleteDataset(id: string): Promise<void> {
  return sendDelete(`/api/datasets/${id}`, 'Could not delete the dataset.')
}
