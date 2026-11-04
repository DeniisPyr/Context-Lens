import { act, render, screen } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Documents from './Documents.tsx'

type Route = (init?: RequestInit) => Response | Promise<Response>

// Stubs fetch and answers each request from the route named "METHOD url".
function stubRoutes(routes: Record<string, Route>) {
  const fetchStub = vi.fn<typeof fetch>(async (url, init) => routes[`${init?.method ?? 'GET'} ${url}`](init))
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

const notes = { id: '1', filename: 'notes.txt', line_count: 2 }

// Like the real fetch: never answers by itself, and rejects once aborted.
const rejectsOnAbort: Route = (init) =>
  new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the document list', () => {
  it('says so when there are no documents', async () => {
    stubRoutes({ 'GET /api/documents': () => Response.json([]) })

    render(<Documents />)

    expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
  })

  it('does not say it is empty while still loading', () => {
    stubRoutes({ 'GET /api/documents': rejectsOnAbort })

    render(<Documents />)

    expect(screen.queryByText('No documents yet.')).not.toBeInTheDocument()
  })

  it('shows the filename and line count of each document, in order', async () => {
    const short = { id: '2', filename: 'short.md', line_count: 1 }
    stubRoutes({ 'GET /api/documents': () => Response.json([notes, short]) })

    render(<Documents />)

    const rows = await screen.findAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('notes.txt')
    expect(rows[0]).toHaveTextContent('2 lines')
    expect(rows[1]).toHaveTextContent('short.md')
    expect(rows[1]).toHaveTextContent(/1 line$/)
    expect(screen.queryByText('No documents yet.')).not.toBeInTheDocument()
  })

  it('shows two documents with the same filename without a key warning', async () => {
    const consoleError = vi.spyOn(console, 'error')
    stubRoutes({ 'GET /api/documents': () => Response.json([notes, { ...notes, id: '2' }]) })

    render(<Documents />)

    expect(await screen.findAllByText('notes.txt')).toHaveLength(2)
    expect(consoleError).not.toHaveBeenCalled()
  })

  it('shows an alert when loading fails', async () => {
    stubRoutes({ 'GET /api/documents': () => new Response('Bad Gateway', { status: 502 }) })

    render(<Documents />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the documents.')
    expect(screen.queryByText('No documents yet.')).not.toBeInTheDocument()
  })

  it('aborts the request on unmount', () => {
    const fetchStub = stubRoutes({ 'GET /api/documents': rejectsOnAbort })

    const { unmount } = render(<Documents />)
    const signal = fetchStub.mock.calls[0][1]?.signal
    expect(signal?.aborted).toBe(false)

    unmount()

    expect(signal?.aborted).toBe(true)
  })

  it('does not show an error when strict mode cancels the first request', async () => {
    const fetchStub = stubRoutes({ 'GET /api/documents': rejectsOnAbort })

    render(
      <StrictMode>
        <Documents />
      </StrictMode>,
    )
    await act(async () => {})

    expect(fetchStub).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
