import { send } from './request.ts'

export type DocumentSummary = {
  id: string
  filename: string
  line_count: number
}

export type DocumentDetail = DocumentSummary & {
  lines: string[]
}

export function listDocuments(datasetId: string, signal: AbortSignal): Promise<DocumentSummary[]> {
  return send(`/api/datasets/${datasetId}/documents`, { signal }, 'Could not load the documents.')
}

export function getDocument(id: string, signal: AbortSignal): Promise<DocumentDetail> {
  return send(`/api/documents/${id}`, { signal }, 'Could not load the document.')
}

export function uploadDocument(datasetId: string, file: File): Promise<DocumentSummary> {
  const body = new FormData()
  body.append('file', file)
  // No Content-Type header: the browser adds its own, with the multipart boundary.
  return send(`/api/datasets/${datasetId}/documents`, { method: 'POST', body }, 'Could not upload the file.')
}
