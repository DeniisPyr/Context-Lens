import { errorMessage } from './errors.ts'

// A failed response, with its status, so that sendDelete can tell "already gone" from other failures.
class ResponseError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// Every failure becomes an Error whose message is what the user should read.
export async function send<T>(url: string, init: RequestInit, fallback: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
    // A 204 has no body to parse. Only requests that expect nothing back get one, so T is void for them.
    if (response.status === 204) return undefined as T
    if (response.ok) return await response.json()
  } catch {
    // The connection dropped, the request was aborted, or the response body wasn't JSON.
    throw new Error(fallback)
  }
  throw new ResponseError(await errorMessage(response, fallback), response.status)
}

// Something that's already gone is what a delete asks for, so a 404 counts as done too.
export async function sendDelete(url: string, fallback: string): Promise<void> {
  try {
    await send<void>(url, { method: 'DELETE' }, fallback)
  } catch (err) {
    if (!(err instanceof ResponseError && err.status === 404)) throw err
  }
}
