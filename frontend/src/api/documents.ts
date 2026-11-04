import { send } from './request.ts'

export type DocumentSummary = {
  id: string
  filename: string
  line_count: number
}

export function listDocuments(signal: AbortSignal): Promise<DocumentSummary[]> {
  return send('/api/documents', { signal }, 'Could not load the documents.')
}

export function uploadDocument(file: File): Promise<DocumentSummary> {
  const body = new FormData()
  body.append('file', file)
  // No Content-Type header: the browser adds its own, with the multipart boundary.
  return send('/api/documents', { method: 'POST', body }, 'Could not upload the file.')
}
