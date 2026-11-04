import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
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

const fileInput = () => screen.getByLabelText<HTMLInputElement>('Choose a .txt or .md file')
const uploadButton = () => screen.getByRole('button', { name: 'Upload' })

async function upload(user: UserEvent, file = new File(['one\ntwo\n'], 'notes.txt')) {
  await user.upload(fileInput(), file)
  await user.click(uploadButton())
}

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

describe('uploading', () => {
  it('reloads the list from the server and clears the input', async () => {
    const user = userEvent.setup()
    // The reloaded list also holds a document this page didn't upload: appending the POST response can't show it.
    const other = { id: '2', filename: 'other.txt', line_count: 5 }
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([]))
      .mockResolvedValueOnce(Response.json([other, notes]))
    stubRoutes({
      'GET /api/documents': get,
      'POST /api/documents': () => Response.json(notes, { status: 201 }),
    })

    render(<Documents />)
    await screen.findByText('No documents yet.')
    await upload(user)

    expect(await screen.findByText('notes.txt')).toBeInTheDocument()
    expect(screen.getByText('other.txt')).toBeInTheDocument()
    expect(fileInput().files).toHaveLength(0)
  })

  it('shows the message from the backend and keeps the chosen file', async () => {
    const user = userEvent.setup({ applyAccept: false })
    stubRoutes({
      'GET /api/documents': () => Response.json([]),
      'POST /api/documents': () => Response.json({ detail: 'Only .txt and .md are allowed.' }, { status: 415 }),
    })

    render(<Documents />)
    await upload(user, new File(['%PDF'], 'report.pdf'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Only .txt and .md are allowed.')
    expect(fileInput().files).toHaveLength(1)
    expect(screen.getByText('No documents yet.')).toBeInTheDocument()
  })

  it.each<[string, Route]>([
    ['a 502 with no JSON', () => new Response('Bad Gateway', { status: 502 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['a validation error whose detail is an array', () => Response.json({ detail: [{ msg: 'x' }] }, { status: 422 })],
  ])('shows the fallback on %s', async (_name, post) => {
    const user = userEvent.setup()
    stubRoutes({ 'GET /api/documents': () => Response.json([]), 'POST /api/documents': post })

    render(<Documents />)
    await upload(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not upload the file.')
  })

  it('clears the old error after a later success', async () => {
    const user = userEvent.setup()
    const post = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json({ detail: 'Too large.' }, { status: 413 }))
      .mockResolvedValueOnce(Response.json(notes, { status: 201 }))
    const get = vi.fn<Route>().mockResolvedValueOnce(Response.json([])).mockResolvedValueOnce(Response.json([notes]))
    stubRoutes({ 'GET /api/documents': get, 'POST /api/documents': post })

    render(<Documents />)
    await upload(user)
    await screen.findByRole('alert')
    await upload(user)

    expect(await screen.findByText('notes.txt')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('clears a load error once a reload works', async () => {
    const user = userEvent.setup()
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
      .mockResolvedValueOnce(Response.json([notes]))
    stubRoutes({
      'GET /api/documents': get,
      'POST /api/documents': () => Response.json(notes, { status: 201 }),
    })

    render(<Documents />)
    await screen.findByRole('alert')
    await upload(user)

    expect(await screen.findByText('notes.txt')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('asks for a file and sends nothing when no file is chosen', async () => {
    const user = userEvent.setup()
    const fetchStub = stubRoutes({ 'GET /api/documents': () => Response.json([]) })

    render(<Documents />)
    await screen.findByText('No documents yet.')
    await user.click(uploadButton())

    expect(screen.getByRole('alert')).toHaveTextContent('Choose a file first.')
    expect(fetchStub).toHaveBeenCalledTimes(1)
  })

  it('stops the browser from submitting the form itself', async () => {
    stubRoutes({ 'GET /api/documents': () => Response.json([]) })

    render(<Documents />)
    await screen.findByText('No documents yet.')

    // fireEvent returns false when the handler called preventDefault.
    expect(fireEvent.submit(fileInput().form!)).toBe(false)
  })

  it('does not accept other file types in the file chooser', async () => {
    const user = userEvent.setup()
    stubRoutes({ 'GET /api/documents': () => Response.json([]) })

    render(<Documents />)
    await screen.findByText('No documents yet.')
    await user.upload(fileInput(), new File(['%PDF'], 'report.pdf'))

    expect(fileInput().files).toHaveLength(0)
  })

  it('disables the button while uploading and enables it after a failure', async () => {
    const user = userEvent.setup()
    let answer!: (response: Response) => void
    stubRoutes({
      'GET /api/documents': () => Response.json([]),
      'POST /api/documents': () => new Promise((resolve) => (answer = resolve)),
    })

    render(<Documents />)
    await upload(user)

    expect(screen.getByRole('button', { name: 'Uploading…' })).toBeDisabled()

    answer(new Response('Bad Gateway', { status: 502 }))

    await screen.findByRole('alert')
    expect(uploadButton()).toBeEnabled()
  })

  it('aborts a slow first load when an upload finishes, so it cannot overwrite the result', async () => {
    const user = userEvent.setup()
    let answerFirstLoad!: (response: Response) => void
    const slowFirstLoad: Route = (init) =>
      new Promise((resolve, reject) => {
        answerFirstLoad = resolve
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      })
    const get = vi.fn<Route>().mockImplementationOnce(slowFirstLoad).mockImplementation(() => Response.json([notes]))
    const fetchStub = stubRoutes({
      'GET /api/documents': get,
      'POST /api/documents': () => Response.json(notes, { status: 201 }),
    })

    render(<Documents />)
    await upload(user)

    expect(await screen.findByText('notes.txt')).toBeInTheDocument()
    expect(fetchStub.mock.calls[0][1]?.signal?.aborted).toBe(true)

    // The old, empty list arrives late.
    await act(async () => answerFirstLoad(Response.json([])))

    expect(screen.getByText('notes.txt')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
