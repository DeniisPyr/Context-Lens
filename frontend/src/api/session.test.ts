import { afterEach, describe, expect, it, onTestFinished, vi } from 'vitest'
import { onSessionEnd } from './request.ts'
import { getSession, logIn, logOut, MAX_PASSWORD_LENGTH } from './session.ts'

afterEach(() => {
  vi.unstubAllGlobals()
})

it('allows the same password length as the backend', () => {
  expect(MAX_PASSWORD_LENGTH).toBe(1000)
})

describe('getSession', () => {
  const { signal } = new AbortController()

  it('passes the signal on and returns the session', async () => {
    const session = { login_required: true, logged_in: false }
    const fetchStub = vi.fn<typeof fetch>(async () => Response.json(session))
    vi.stubGlobal('fetch', fetchStub)

    await expect(getSession(signal)).resolves.toEqual(session)

    expect(fetchStub).toHaveBeenCalledWith('/api/session', { signal })
  })

  it('falls back when a failed response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('Bad Gateway', { status: 502 })))

    await expect(getSession(signal)).rejects.toThrow("Could not check whether you're logged in.")
  })
})

describe('logIn', () => {
  const wrongPassword = () => Response.json({ detail: 'Wrong password.' }, { status: 401 })

  it('posts the password as JSON and resolves on a 204', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchStub)

    await expect(logIn(' secret ')).resolves.toBeUndefined()

    const [url, init = {}] = fetchStub.mock.calls[0]
    expect(url).toBe('/api/session')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ password: ' secret ' })
    // The browser only keeps the session cookie when the request may carry credentials, which is its default.
    expect(init.credentials).not.toBe('omit')
  })

  it('uses the message from the backend for a wrong password', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => wrongPassword()))

    await expect(logIn('guess')).rejects.toThrow('Wrong password.')
  })

  it('does not take the 401 for a wrong password as the end of a session', async () => {
    const listener = vi.fn()
    onTestFinished(onSessionEnd(listener))
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => wrongPassword()))

    await expect(logIn('guess')).rejects.toThrow('Wrong password.')

    expect(listener).not.toHaveBeenCalled()
  })

  it('falls back when a failed response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('Bad Gateway', { status: 502 })))

    await expect(logIn('secret')).rejects.toThrow('Could not log in.')
  })
})

describe('logOut', () => {
  it('sends a DELETE and resolves on a 204', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchStub)

    await expect(logOut()).resolves.toBeUndefined()

    expect(fetchStub).toHaveBeenCalledWith('/api/session', { method: 'DELETE' })
  })

  it('falls back when a failed response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('Bad Gateway', { status: 502 })))

    await expect(logOut()).rejects.toThrow('Could not log out.')
  })
})
