import { afterEach, describe, expect, it, vi } from 'vitest'
import { getDocument, listDocuments, uploadDocument } from './documents.ts'

const summary = { id: '1', filename: 'notes.txt', line_count: 2 }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('uploadDocument', () => {
  it('posts the file as multipart form data and returns the summary', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => Response.json(summary, { status: 201 }))
    vi.stubGlobal('fetch', fetchStub)
    const file = new File(['one\ntwo\n'], 'notes.txt', { type: 'text/plain' })

    await expect(uploadDocument('d1', file)).resolves.toEqual(summary)

    const [url, init = {}] = fetchStub.mock.calls[0]
    expect(url).toBe('/api/datasets/d1/documents')
    expect(init.method).toBe('POST')
    expect((init.body as FormData).get('file')).toBe(file)
    expect(new Headers(init.headers).has('Content-Type')).toBe(false)
  })

  it('falls back when a successful response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('<html>')))

    await expect(uploadDocument('d1', new File(['x'], 'notes.txt'))).rejects.toThrow('Could not upload the file.')
  })
})

describe('listDocuments', () => {
  it('passes the signal on and returns the list', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => Response.json([summary]))
    vi.stubGlobal('fetch', fetchStub)
    const { signal } = new AbortController()

    await expect(listDocuments('d1', signal)).resolves.toEqual([summary])

    expect(fetchStub).toHaveBeenCalledWith('/api/datasets/d1/documents', { signal })
  })

  it('falls back when a failed response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('Bad Gateway', { status: 502 })))

    await expect(listDocuments('d1', new AbortController().signal)).rejects.toThrow('Could not load the documents.')
  })
})

describe('getDocument', () => {
  const detail = { ...summary, lines: ['one', 'two'] }
  const { signal } = new AbortController()

  it('asks for the document by id, passes the signal on and returns its lines', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => Response.json(detail))
    vi.stubGlobal('fetch', fetchStub)

    await expect(getDocument('1', signal)).resolves.toEqual(detail)

    expect(fetchStub).toHaveBeenCalledWith('/api/documents/1', { signal })
  })

  it('uses the message from the backend when there is one', async () => {
    const notFound = Response.json({ detail: 'Document not found.' }, { status: 404 })
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => notFound))

    await expect(getDocument('1', signal)).rejects.toThrow('Document not found.')
  })

  it('falls back when a failed response is not JSON', async () => {
    const badGateway = new Response('Bad Gateway', { status: 502 })
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => badGateway))

    await expect(getDocument('1', signal)).rejects.toThrow('Could not load the document.')
  })
})
