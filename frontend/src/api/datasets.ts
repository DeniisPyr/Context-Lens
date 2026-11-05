import { send } from './request.ts'

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
