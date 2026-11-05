import { afterEach, describe, expect, it, vi } from 'vitest'
import { send, sendDelete } from './request.ts'

afterEach(() => {
  vi.unstubAllGlobals()
})

const respondWith = (response: Response | (() => Promise<Response>)) => {
  const fetchStub = vi.fn<typeof fetch>(async () => (typeof response === 'function' ? response() : response))
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

describe('send', () => {
  it('returns the parsed body of a successful response', async () => {
    respondWith(Response.json({ id: '1' }))

    await expect(send('/api/x', {}, 'fallback')).resolves.toEqual({ id: '1' })
  })

  it('returns nothing for a 204, without reading a body it does not have', async () => {
    const noContent = new Response(null, { status: 204 })
    const json = vi.spyOn(noContent, 'json')
    respondWith(noContent)

    await expect(send('/api/x', { method: 'DELETE' }, 'fallback')).resolves.toBeUndefined()
    expect(json).not.toHaveBeenCalled()
  })

  it('still falls back when another successful response has no JSON body', async () => {
    respondWith(new Response(null, { status: 200 }))

    await expect(send('/api/x', {}, 'fallback')).rejects.toThrow('fallback')
  })

  it('rejects with the message from the backend', async () => {
    respondWith(Response.json({ detail: 'Document not found.' }, { status: 404 }))

    const failure = send('/api/x', {}, 'fallback')

    await expect(failure).rejects.toBeInstanceOf(Error)
    await expect(failure).rejects.toThrow('Document not found.')
  })

  it.each<[string, () => Promise<Response>]>([
    ['a 502 with no JSON', async () => new Response('Bad Gateway', { status: 502 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('rejects with the fallback on %s', async (_name, response) => {
    respondWith(response)

    await expect(send('/api/x', {}, 'fallback')).rejects.toThrow('fallback')
  })
})

describe('sendDelete', () => {
  it('sends a DELETE and resolves on a 204', async () => {
    const fetchStub = respondWith(new Response(null, { status: 204 }))

    await expect(sendDelete('/api/x/1', 'fallback')).resolves.toBeUndefined()

    expect(fetchStub).toHaveBeenCalledWith('/api/x/1', { method: 'DELETE' })
  })

  it('resolves on a 404, since what it deletes is gone either way', async () => {
    respondWith(Response.json({ detail: 'Document not found.' }, { status: 404 }))

    await expect(sendDelete('/api/x/1', 'fallback')).resolves.toBeUndefined()
  })

  it('rejects with the message from the backend on other failures', async () => {
    const detail = 'The database is unavailable right now. Please try again.'
    respondWith(Response.json({ detail }, { status: 503 }))

    await expect(sendDelete('/api/x/1', 'fallback')).rejects.toThrow(detail)
  })

  it.each<[string, () => Promise<Response>]>([
    ['a 500 with no JSON', async () => new Response('Internal Server Error', { status: 500 })],
    ['a 405 from a backend without the route', async () => Response.json({ detail: 'Nope' }, { status: 405 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('does not take %s for done', async (_name, response) => {
    respondWith(response)

    await expect(sendDelete('/api/x/1', 'fallback')).rejects.toBeInstanceOf(Error)
  })
})
