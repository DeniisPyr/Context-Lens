import { send, sendDelete } from './request.ts'

export type DocumentSummary = {
  id: string
  filename: string
  line_count: number
  // Only a PDF has pages. A text file's is null.
  page_count: number | null
}

export type DocumentDetail = DocumentSummary & {
  lines: string[]
  // Only a PDF's: page_starts[i] is the line that page i + 1 starts on, counted from 1 through the whole document. A
  // page with no text starts where the next one does, and one at the end starts after the last line.
  page_starts: number[] | null
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

// Resolves when the document is gone, including when it was gone already.
export function deleteDocument(id: string): Promise<void> {
  return sendDelete(`/api/documents/${id}`, 'Could not delete the document.')
}
