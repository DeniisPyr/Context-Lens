// Turns a failed response into a message for the user. FastAPI's `detail` is a readable string for
// our own errors but an array for its validation errors, and the dev proxy's 502 isn't JSON at all.
export async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const { detail } = await response.json()
    if (typeof detail === 'string') return detail
  } catch {
    // Not JSON: use the fallback below.
  }
  return fallback
}
