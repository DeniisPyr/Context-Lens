import { afterEach, describe, expect, it, vi } from 'vitest'
import { listDocuments, uploadDocument } from './documents.ts'

const summary = { id: '1', filename: 'notes.txt', line_count: 2 }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('uploadDocument', () => {
  it('posts the file as multipart form data and returns the summary', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => Response.json(summary, { status: 201 }))
    vi.stubGlobal('fetch', fetchStub)
    const file = new File(['one\ntwo\n'], 'notes.txt', { type: 'text/plain' })

    await expect(uploadDocument(file)).resolves.toEqual(summary)

    const [url, init = {}] = fetchStub.mock.calls[0]
    expect(url).toBe('/api/documents')
    expect(init.method).toBe('POST')
    expect((init.body as FormData).get('file')).toBe(file)
    expect(new Headers(init.headers).has('Content-Type')).toBe(false)
  })

  it('falls back when a successful response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('<html>')))

    await expect(uploadDocument(new File(['x'], 'notes.txt'))).rejects.toThrow('Could not upload the file.')
  })
})

describe('listDocuments', () => {
  it('passes the signal on and returns the list', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => Response.json([summary]))
    vi.stubGlobal('fetch', fetchStub)
    const { signal } = new AbortController()

    await expect(listDocuments(signal)).resolves.toEqual([summary])

    expect(fetchStub).toHaveBeenCalledWith('/api/documents', { signal })
  })
})
