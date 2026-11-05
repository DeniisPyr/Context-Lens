import { afterEach, describe, expect, it, vi } from 'vitest'
import { createDataset, deleteDataset, listDatasets, MAX_DATASET_NAME_LENGTH } from './datasets.ts'

const reports = { id: 'r', name: 'Reports' }

afterEach(() => {
  vi.unstubAllGlobals()
})

it('allows the same name length as the backend', () => {
  expect(MAX_DATASET_NAME_LENGTH).toBe(100)
})

describe('listDatasets', () => {
  const { signal } = new AbortController()

  it('passes the signal on and returns the list', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => Response.json([reports]))
    vi.stubGlobal('fetch', fetchStub)

    await expect(listDatasets(signal)).resolves.toEqual([reports])

    expect(fetchStub).toHaveBeenCalledWith('/api/datasets', { signal })
  })

  it('falls back when a failed response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('Bad Gateway', { status: 502 })))

    await expect(listDatasets(signal)).rejects.toThrow('Could not load the datasets.')
  })
})

describe('createDataset', () => {
  it('posts the name as JSON and returns the dataset', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => Response.json(reports, { status: 201 }))
    vi.stubGlobal('fetch', fetchStub)

    await expect(createDataset('Reports')).resolves.toEqual(reports)

    const [url, init = {}] = fetchStub.mock.calls[0]
    expect(url).toBe('/api/datasets')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ name: 'Reports' })
  })

  it('uses the message from the backend when there is one', async () => {
    const taken = Response.json({ detail: 'A dataset with this name already exists.' }, { status: 409 })
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => taken))

    await expect(createDataset('Reports')).rejects.toThrow('A dataset with this name already exists.')
  })

  it('falls back when a failed response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('Bad Gateway', { status: 502 })))

    await expect(createDataset('Reports')).rejects.toThrow('Could not create the dataset.')
  })
})

describe('deleteDataset', () => {
  it('sends a DELETE for the dataset and resolves on a 204', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchStub)

    await expect(deleteDataset('r')).resolves.toBeUndefined()

    expect(fetchStub).toHaveBeenCalledWith('/api/datasets/r', { method: 'DELETE' })
  })

  it('resolves when the dataset is already gone', async () => {
    const notFound = Response.json({ detail: 'Dataset not found.' }, { status: 404 })
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => notFound))

    await expect(deleteDataset('r')).resolves.toBeUndefined()
  })

  it('uses the message from the backend when there is one', async () => {
    const detail = 'The database is unavailable right now. Please try again.'
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => Response.json({ detail }, { status: 503 })))

    await expect(deleteDataset('r')).rejects.toThrow(detail)
  })

  it('falls back when a failed response is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => new Response('Bad Gateway', { status: 502 })))

    await expect(deleteDataset('r')).rejects.toThrow('Could not delete the dataset.')
  })
})
