import { errorMessage } from './errors.ts'

// Every failure becomes an Error whose message is what the user should read.
export async function send<T>(url: string, init: RequestInit, fallback: string): Promise<T> {
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
