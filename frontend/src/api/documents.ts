import { errorMessage } from './errors.ts'

export type DocumentSummary = {
  id: string
  filename: string
  line_count: number
}

// Every failure becomes an Error whose message is what the user should read.
async function send<T>(url: string, init: RequestInit, fallback: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
    if (response.ok) return await response.json()
  } catch {
    // The connection dropped, the request was aborted, or the response body wasn't JSON.
    throw new Error(fallback)
  }
  throw new Error(await errorMessage(response, fallback))
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
