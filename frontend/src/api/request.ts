import { errorMessage } from './errors.ts'

// A failed response, with its status, so that sendDelete can tell "already gone" from other failures.
class ResponseError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// The one listener told when the backend turns a request away with a 401 because there's no valid session: it expired,
// the password changed, or the user logged out in another tab. A listener rather than an error for App to catch,
// because each component catches its errors to show them, so App would never see one. This way components know
// nothing about sessions: App listens and puts the login form in place of the app, and the component that failed goes
// with it.
let sessionEndListener: (() => void) | null = null

// Sets the one listener, and returns a function that removes it again.
export function onSessionEnd(listener: () => void): () => void {
  sessionEndListener = listener
  return () => {
    if (sessionEndListener === listener) sessionEndListener = null
  }
}

type Options = {
  // True for the request that logs in: its 401 means a wrong password, not that a session ended.
  loggingIn?: boolean
}

// Every failure becomes an Error whose message is what the user should read.
export async function send<T>(
  url: string,
  init: RequestInit,
  fallback: string,
  { loggingIn = false }: Options = {},
): Promise<T> {
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
  if (response.status === 401 && !loggingIn) sessionEndListener?.()
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
