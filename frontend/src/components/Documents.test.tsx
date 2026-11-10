import { act, fireEvent, render, renderHook, screen, within } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
import { StrictMode, useRef, useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDocuments } from '../hooks/useDocuments.ts'
import Documents from './Documents.tsx'

type Route = (init?: RequestInit) => Response | Promise<Response>

// Stubs fetch and answers each request from the route named "METHOD url".
function stubRoutes(routes: Record<string, Route>) {
  const fetchStub = vi.fn<typeof fetch>(async (url, init) => routes[`${init?.method ?? 'GET'} ${url}`](init))
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

// Documents gets its list as props, so this loads it with the real hook, the way Workspace does.
function LoadedDocuments() {
  const { documents, error, reload, remove } = useDocuments('d1')
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  return (
    <Documents
      datasetId="d1"
      documents={documents}
      error={error}
      busy={busy}
      fileInputRef={input}
      onBusyChange={setBusy}
      onUploaded={reload}
      onDeleted={remove}
    />
  )
}

const GET_LIST = 'GET /api/datasets/d1/documents'
const POST_FILE = 'POST /api/datasets/d1/documents'

const notes = { id: '1', filename: 'notes.txt', line_count: 2, page_count: null }

// Like the real fetch: never answers by itself, and rejects once aborted.
const rejectsOnAbort: Route = (init) =>
  new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })

const fileInput = () => screen.getByLabelText<HTMLInputElement>('Add files')
// The zone is the input's label, so dragging and dropping happen on it.
const dropZone = () => fileInput().closest('label')!
const summary = () => screen.getByRole('status')
const documentList = () => within(screen.getByRole('list', { name: 'Documents' }))
const resultRows = () => within(screen.getByRole('list', { name: 'Upload results' })).getAllByRole('listitem')
const clearButton = () => screen.queryByRole('button', { name: 'Clear upload results' })

// Choosing files is all it takes: the upload starts at once.
async function upload(user: UserEvent, ...files: File[]) {
  await user.upload(fileInput(), files.length > 0 ? files : new File(['one\ntwo\n'], 'notes.txt'))
}

// Drags files over the zone and drops them, as from the desktop. fireEvent returns false when the page called
// preventDefault, which keeps the browser from opening a dropped file in place of the app.
function drop(...files: File[]) {
  const dataTransfer = { files, types: ['Files'], dropEffect: 'none' }
  const draggedOver = fireEvent.dragOver(dropZone(), { dataTransfer })
  const dropped = fireEvent.drop(dropZone(), { dataTransfer })
  return { draggedOver, dropped, dataTransfer }
}

const named = (...filenames: string[]) => filenames.map((filename) => new File(['text'], filename))

const requestsTo = (fetchStub: ReturnType<typeof stubRoutes>, method: string) =>
  fetchStub.mock.calls.filter((call) => (call[1]?.method ?? 'GET') === method)

const sentFile = ([, init = {}]: Parameters<typeof fetch>) => (init.body as FormData).get('file')

// A POST route that answers each file only when the test says so, and remembers the order they came in.
function postsAnsweredByTheTest() {
  const pending: ((response: Response) => void)[] = []
  const route: Route = () => new Promise((resolve) => pending.push(resolve))
  return {
    route,
    started: () => pending.length,
    answer: (position: number, response: Response) => act(async () => pending[position](response)),
  }
}

// Lets anything that was going to start, start.
const settle = () => act(async () => new Promise((resolve) => setTimeout(resolve)))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the document list', () => {
  it('says so when there are no documents', async () => {
    stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)

    expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
  })

  it('does not say it is empty while still loading', () => {
    stubRoutes({ [GET_LIST]: rejectsOnAbort })

    render(<LoadedDocuments />)

    expect(screen.queryByText('No documents yet.')).not.toBeInTheDocument()
  })

  it('shows the filename and line count of each document, in order', async () => {
    const short = { id: '2', filename: 'short.md', line_count: 1, page_count: null }
    stubRoutes({ [GET_LIST]: () => Response.json([notes, short]) })

    render(<LoadedDocuments />)

    const rows = await screen.findAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('notes.txt')
    expect(rows[0]).toHaveTextContent('2 lines')
    expect(rows[1]).toHaveTextContent('short.md')
    expect(within(rows[1]).getByText('1 line')).toBeInTheDocument()
    expect(screen.queryByText('No documents yet.')).not.toBeInTheDocument()
  })

  it('counts a PDF in pages instead of lines', async () => {
    const report = { id: '2', filename: 'report.pdf', line_count: 120, page_count: 3 }
    const leaflet = { id: '3', filename: 'leaflet.pdf', line_count: 1, page_count: 1 }
    stubRoutes({ [GET_LIST]: () => Response.json([notes, report, leaflet]) })

    render(<LoadedDocuments />)

    const rows = await screen.findAllByRole('listitem')
    expect(within(rows[0]).getByText('2 lines')).toBeInTheDocument()
    expect(within(rows[1]).getByText('3 pages')).toBeInTheDocument()
    expect(within(rows[2]).getByText('1 page')).toBeInTheDocument()
    expect(rows[1]).not.toHaveTextContent(/line|120/)
    expect(rows[2]).not.toHaveTextContent(/line/)
  })

  it('asks for the documents of the dataset it was given', async () => {
    const fetchStub = stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')

    expect(fetchStub.mock.calls[0][0]).toBe('/api/datasets/d1/documents')
  })

  it('loads the list of the new dataset when the id changes', async () => {
    const fetchStub = stubRoutes({
      [GET_LIST]: () => Response.json([]),
      'GET /api/datasets/d2/documents': () => Response.json([notes]),
    })

    const { result, rerender } = renderHook(({ id }) => useDocuments(id), { initialProps: { id: 'd1' } })
    await vi.waitFor(() => expect(result.current.documents).toEqual([]))
    rerender({ id: 'd2' })

    await vi.waitFor(() => expect(result.current.documents).toEqual([notes]))
    expect(fetchStub).toHaveBeenCalledTimes(2)
  })

  it('drops the old list and its error as soon as the id changes, before the new list arrives', async () => {
    stubRoutes({
      [GET_LIST]: () => new Response('Bad Gateway', { status: 502 }),
      'GET /api/datasets/d2/documents': rejectsOnAbort,
    })

    const { result, rerender } = renderHook(({ id }) => useDocuments(id), { initialProps: { id: 'd1' } })
    await vi.waitFor(() => expect(result.current.error).toBe('Could not load the documents.'))
    rerender({ id: 'd2' })

    expect(result.current.documents).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('loads nothing while no dataset is selected', async () => {
    const fetchStub = stubRoutes({})

    const { result } = renderHook(() => useDocuments(undefined))
    await act(async () => {})

    expect(fetchStub).not.toHaveBeenCalled()
    expect(result.current.documents).toBeNull()
  })

  it('says how many documents there are beside the heading, once they have loaded', async () => {
    const short = { id: '2', filename: 'short.md', line_count: 1, page_count: null }
    stubRoutes({ [GET_LIST]: () => Response.json([notes, short]) })

    render(<LoadedDocuments />)
    const head = screen.getByRole('heading', { name: 'Documents' }).parentElement!
    expect(head).toHaveTextContent(/^Documents$/)

    await screen.findByRole('list', { name: 'Documents' })
    expect(head).toHaveTextContent(/^Documents2$/)
  })

  it('cuts a long filename short with an ellipsis, and keeps the whole name as its title', async () => {
    const long = `${'long'.repeat(100)}.txt`
    stubRoutes({ [GET_LIST]: () => Response.json([{ ...notes, filename: long }]) })

    render(<LoadedDocuments />)
    await screen.findByRole('list', { name: 'Documents' })
    const name = documentList().getByText(long)

    expect(name).toHaveAttribute('title', long)
    expect(name).toHaveStyle({ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: '0px' })
    expect(name.parentElement).toHaveStyle({ minWidth: '0px' })
  })

  it('shows two documents with the same filename without a key warning', async () => {
    const consoleError = vi.spyOn(console, 'error')
    stubRoutes({ [GET_LIST]: () => Response.json([notes, { ...notes, id: '2' }]) })

    render(<LoadedDocuments />)

    expect(await screen.findAllByText('notes.txt')).toHaveLength(2)
    expect(consoleError).not.toHaveBeenCalled()
  })

  it('shows an alert when loading fails', async () => {
    stubRoutes({ [GET_LIST]: () => new Response('Bad Gateway', { status: 502 }) })

    render(<LoadedDocuments />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the documents.')
    expect(screen.queryByText('No documents yet.')).not.toBeInTheDocument()
  })

  it('aborts the request on unmount', () => {
    const fetchStub = stubRoutes({ [GET_LIST]: rejectsOnAbort })

    const { unmount } = render(<LoadedDocuments />)
    const signal = fetchStub.mock.calls[0][1]?.signal
    expect(signal?.aborted).toBe(false)

    unmount()

    expect(signal?.aborted).toBe(true)
  })

  it('does not show an error when strict mode cancels the first request', async () => {
    const fetchStub = stubRoutes({ [GET_LIST]: rejectsOnAbort })

    render(
      <StrictMode>
        <LoadedDocuments />
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
    const other = { id: '2', filename: 'other.txt', line_count: 5, page_count: null }
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([]))
      .mockResolvedValueOnce(Response.json([other, notes]))
    stubRoutes({
      [GET_LIST]: get,
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    await upload(user)

    await screen.findByRole('list', { name: 'Documents' })
    expect(documentList().getByText('notes.txt')).toBeInTheDocument()
    expect(documentList().getByText('other.txt')).toBeInTheDocument()
    await vi.waitFor(() => expect(fileInput().files).toHaveLength(0))
  })

  it('shows the message from the backend in the row of the file', async () => {
    const user = userEvent.setup({ applyAccept: false })
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json({ detail: 'Only .txt, .md and .pdf files are accepted.' }, { status: 415 }),
    })

    render(<LoadedDocuments />)
    await upload(user, new File(['PK'], 'report.docx'))

    await screen.findByText('Only .txt, .md and .pdf files are accepted.')
    expect(resultRows()[0]).toHaveTextContent('report.docx')
    expect(screen.getByText('No documents yet.')).toBeInTheDocument()
  })

  it.each<[string, Route]>([
    ['a 502 with no JSON', () => new Response('Bad Gateway', { status: 502 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['a validation error whose detail is an array', () => Response.json({ detail: [{ msg: 'x' }] }, { status: 422 })],
  ])('shows the fallback on %s', async (_name, post) => {
    const user = userEvent.setup()
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: post })

    render(<LoadedDocuments />)
    await upload(user)

    expect(await screen.findByText('Could not upload the file.')).toBeInTheDocument()
  })

  it('removes the rows of a failed run once a later run starts', async () => {
    const user = userEvent.setup()
    const post = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json({ detail: 'Too large.' }, { status: 413 }))
      .mockResolvedValueOnce(Response.json(notes, { status: 201 }))
    const get = vi.fn<Route>().mockResolvedValueOnce(Response.json([])).mockResolvedValueOnce(Response.json([notes]))
    stubRoutes({ [GET_LIST]: get, [POST_FILE]: post })

    render(<LoadedDocuments />)
    await upload(user)
    await screen.findByText('Too large.')
    await upload(user)

    await screen.findByRole('list', { name: 'Documents' })
    expect(screen.queryByText('Too large.')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('clears a load error once a reload works', async () => {
    const user = userEvent.setup()
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
      .mockResolvedValueOnce(Response.json([notes]))
    stubRoutes({
      [GET_LIST]: get,
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await screen.findByRole('alert')
    await upload(user)

    await screen.findByRole('list', { name: 'Documents' })
    expect(documentList().getByText('notes.txt')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('starts as soon as files are chosen, with no button to press', async () => {
    const user = userEvent.setup()
    const fetchStub = stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')

    expect(screen.queryByRole('button', { name: /^Upload/ })).not.toBeInTheDocument()

    await user.upload(fileInput(), new File(['one\ntwo\n'], 'notes.txt'))

    await vi.waitFor(() => expect(requestsTo(fetchStub, 'POST')).toHaveLength(1))
  })

  it('starts nothing and sends nothing when the chooser is closed with no file chosen', async () => {
    const fetchStub = stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    fireEvent.change(fileInput(), { target: { files: [] } })

    expect(requestsTo(fetchStub, 'POST')).toHaveLength(0)
    expect(screen.queryByRole('list', { name: 'Upload results' })).not.toBeInTheDocument()
    expect(fileInput()).toBeEnabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the rows of the last run when the chooser is closed with nothing chosen, as nothing started', async () => {
    const user = userEvent.setup()
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await upload(user)
    await screen.findByText('Uploaded')
    fireEvent.change(fileInput(), { target: { files: [] } })

    expect(screen.getByText('Uploaded')).toBeInTheDocument()
    expect(summary()).toHaveTextContent('1 uploaded, 0 failed.')
  })

  it('does not accept other file types in the file chooser', async () => {
    const user = userEvent.setup()
    const fetchStub = stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    await user.upload(fileInput(), new File(['PK'], 'report.docx'))

    expect(fileInput().files).toHaveLength(0)
    expect(requestsTo(fetchStub, 'POST')).toHaveLength(0)
  })

  it('accepts a PDF in the file chooser and uploads it like a text file', async () => {
    const user = userEvent.setup()
    const report = { id: '2', filename: 'report.pdf', line_count: 120, page_count: 3 }
    const get = vi.fn<Route>().mockResolvedValueOnce(Response.json([])).mockResolvedValueOnce(Response.json([report]))
    const fetchStub = stubRoutes({
      [GET_LIST]: get,
      [POST_FILE]: () => Response.json(report, { status: 201 }),
    })
    const pdf = new File(['%PDF-1.7'], 'report.pdf', { type: 'application/pdf' })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    await upload(user, pdf)

    await screen.findByRole('list', { name: 'Documents' })
    expect(documentList().getByText('report.pdf')).toBeInTheDocument()
    expect(documentList().getByText('3 pages')).toBeInTheDocument()
    expect(requestsTo(fetchStub, 'POST').map(sentFile)).toEqual([pdf])
    expect(summary()).toHaveTextContent('1 uploaded, 0 failed.')
  })

  it('disables the file input while uploading and enables it after a failure', async () => {
    const user = userEvent.setup()
    let answer!: (response: Response) => void
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => new Promise((resolve) => (answer = resolve)),
    })

    render(<LoadedDocuments />)
    await upload(user)

    expect(screen.getByText('Uploading 1 of 1…')).toBeInTheDocument()
    expect(fileInput()).toBeDisabled()

    answer(new Response('Bad Gateway', { status: 502 }))

    await screen.findByText('Could not upload the file.')
    expect(fileInput()).toBeEnabled()
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
      [GET_LIST]: get,
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await upload(user)

    await screen.findByRole('list', { name: 'Documents' })
    expect(fetchStub.mock.calls[0][1]?.signal?.aborted).toBe(true)

    // The old, empty list arrives late.
    await act(async () => answerFirstLoad(Response.json([])))

    expect(documentList().getByText('notes.txt')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('uploading several files', () => {
  const answers = postsAnsweredByTheTest
  const uploaded = (filename: string) =>
    Response.json({ id: filename, filename, line_count: 1, page_count: null }, { status: 201 })

  it('lets the user choose several text or PDF files', async () => {
    stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')

    expect(fileInput()).toHaveAccessibleName('Add files')
    expect(fileInput()).toHaveAccessibleDescription('.txt, .md, .pdf · up to 1\u00a0MB each')
    expect(fileInput()).toHaveAttribute('multiple')
    expect(fileInput()).toHaveAttribute('accept', '.txt,.md,.pdf')
  })

  it('sends one request per file, each with its own file, in the chosen order', async () => {
    const user = userEvent.setup()
    const fetchStub = stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })
    const files = named('c.txt', 'a.md', 'b.txt')

    render(<LoadedDocuments />)
    await upload(user, ...files)
    await vi.waitFor(() => expect(summary()).toHaveTextContent('3 uploaded, 0 failed.'))

    const posts = requestsTo(fetchStub, 'POST')
    expect(posts.map(([url]) => url)).toEqual(Array(3).fill('/api/datasets/d1/documents'))
    expect(posts.map(sentFile)).toEqual(files)
  })

  it('does not start a request until the one before it has finished', async () => {
    const user = userEvent.setup()
    const { route, started, answer } = answers()
    const fetchStub = stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: route })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'b.txt', 'c.txt'))

    await settle()
    expect(started()).toBe(1)

    await answer(0, uploaded('a.txt'))
    await settle()
    expect(started()).toBe(2)
    expect(sentFile(requestsTo(fetchStub, 'POST')[1])).toHaveProperty('name', 'b.txt')

    // A failure moves on too, and still only after the request has finished.
    await answer(1, new Response('Bad Gateway', { status: 502 }))
    await settle()
    expect(started()).toBe(3)

    await answer(2, uploaded('c.txt'))
    await settle()
    expect(started()).toBe(3)
  })

  it('says which file it is on and stays disabled for the whole run', async () => {
    const user = userEvent.setup()
    const { route, answer } = answers()
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: route })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'b.txt', 'c.txt'))

    const bar = () => screen.getByRole('progressbar', { name: /^Uploading/ })
    expect(screen.getByText('Uploading 1 of 3…')).toBeInTheDocument()
    expect(bar()).toHaveAttribute('max', '3')
    expect(bar()).toHaveAttribute('value', '0')
    expect(fileInput()).toBeDisabled()

    await answer(0, uploaded('a.txt'))
    expect(screen.getByText('Uploading 2 of 3…')).toBeInTheDocument()
    expect(bar()).toHaveAttribute('value', '1')

    await answer(1, new Response('Bad Gateway', { status: 502 }))
    expect(screen.getByText('Uploading 3 of 3…')).toBeInTheDocument()
    expect(bar()).toHaveAttribute('value', '2')
    expect(fileInput()).toBeDisabled()

    await answer(2, uploaded('c.txt'))
    expect(screen.queryByText(/^Uploading \d/)).not.toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(fileInput()).toBeEnabled()
  })

  it('carries on after a failed file and shows a row for every file, in order', async () => {
    const user = userEvent.setup()
    const post = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json(notes, { status: 201 }))
      .mockResolvedValueOnce(Response.json({ detail: 'b.txt is already in this dataset.' }, { status: 409 }))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(Response.json(notes, { status: 201 }))
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: post })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'b.txt', 'c.txt', 'd.txt'))
    await vi.waitFor(() => expect(summary()).toHaveTextContent('2 uploaded, 2 failed.'))

    expect(post).toHaveBeenCalledTimes(4)
    expect(resultRows().map((row) => row.textContent)).toEqual([
      'a.txtUploaded',
      'b.txtb.txt is already in this dataset.',
      'c.txtCould not upload the file.',
      'd.txtUploaded',
    ])
  })

  it('marks failed rows with the alert colour and only those', async () => {
    const user = userEvent.setup()
    const post = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json(notes, { status: 201 }))
      .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
    // The list never loads, which puts a real alert on the page to compare with.
    stubRoutes({ [GET_LIST]: () => new Response('Bad Gateway', { status: 502 }), [POST_FILE]: post })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'b.txt'))
    await vi.waitFor(() => expect(summary()).toHaveTextContent('1 uploaded, 1 failed.'))

    const alertColour = getComputedStyle(screen.getByRole('alert')).color
    const [good, bad] = resultRows()
    expect(getComputedStyle(bad).color).toBe(alertColour)
    expect(getComputedStyle(good).color).not.toBe(alertColour)
  })

  it('has no alert for failed rows and one status for the whole run', async () => {
    const user = userEvent.setup()
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json({ detail: 'Too large.' }, { status: 413 }),
    })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'b.txt', 'c.txt'))
    await vi.waitFor(() => expect(summary()).toHaveTextContent('0 uploaded, 3 failed.'))

    expect(screen.queryAllByRole('alert')).toHaveLength(0)
    expect(screen.getAllByRole('status')).toHaveLength(1)
  })

  it('keeps the status on the page but says nothing in it until the run ends', async () => {
    const user = userEvent.setup()
    const { route, answer } = answers()
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: route })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    const status = summary()
    expect(status).toBeEmptyDOMElement()

    await upload(user, ...named('a.txt', 'b.txt'))
    await answer(0, uploaded('a.txt'))
    expect(screen.getByText('Uploaded')).toBeInTheDocument()
    expect(status).toBeEmptyDOMElement()

    await answer(1, uploaded('b.txt'))
    expect(summary()).toBe(status)
    expect(status).toHaveTextContent('2 uploaded, 0 failed.')
  })

  it('empties the status again as soon as the next run starts', async () => {
    const user = userEvent.setup()
    const { route, answer } = answers()
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: route })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt'))
    await answer(0, uploaded('a.txt'))
    expect(summary()).toHaveTextContent('1 uploaded, 0 failed.')

    await upload(user, ...named('b.txt'))

    expect(summary()).toBeEmptyDOMElement()
    expect(screen.queryByText('Uploaded')).not.toBeInTheDocument()
  })

  it('reloads the list after each successful file, so it grows during the run', async () => {
    const user = userEvent.setup()
    const first = { id: '1', filename: 'a.txt', line_count: 1, page_count: null }
    const second = { id: '2', filename: 'c.txt', line_count: 1, page_count: null }
    const { route, answer } = answers()
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([]))
      .mockResolvedValueOnce(Response.json([first]))
      .mockResolvedValueOnce(Response.json([first, second]))
    stubRoutes({ [GET_LIST]: get, [POST_FILE]: route })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    await upload(user, ...named('a.txt', 'b.txt', 'c.txt'))

    await answer(0, uploaded('a.txt'))
    await settle()
    expect(get).toHaveBeenCalledTimes(2)
    expect(documentList().getByText('a.txt')).toBeInTheDocument()

    // A failed file changed nothing, so there's nothing to reload.
    await answer(1, new Response('Bad Gateway', { status: 502 }))
    await settle()
    expect(get).toHaveBeenCalledTimes(2)

    await answer(2, uploaded('c.txt'))
    await settle()
    expect(get).toHaveBeenCalledTimes(3)
    expect(documentList().getByText('c.txt')).toBeInTheDocument()
  })

  it('lists every file of the run at once, and shows each result as its file finishes', async () => {
    const user = userEvent.setup()
    const { route, answer } = answers()
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: route })
    const texts = () => resultRows().map((row) => row.textContent)

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'b.txt', 'c.txt'))

    expect(texts()).toEqual(['a.txtUploading…', 'b.txtWaiting', 'c.txtWaiting'])

    await answer(0, uploaded('a.txt'))
    expect(texts()).toEqual(['a.txtUploaded', 'b.txtUploading…', 'c.txtWaiting'])

    await answer(1, new Response('Bad Gateway', { status: 502 }))
    expect(texts()).toEqual(['a.txtUploaded', 'b.txtCould not upload the file.', 'c.txtUploading…'])

    await answer(2, uploaded('c.txt'))
    expect(texts()).toEqual(['a.txtUploaded', 'b.txtCould not upload the file.', 'c.txtUploaded'])
  })

  it.each<[string, Route]>([
    ['every file worked', () => Response.json(notes, { status: 201 })],
    ['every file failed', () => new Response('Bad Gateway', { status: 502 })],
  ])('empties the input once it has the files, so when %s, the same files can go again', async (_name, post) => {
    const user = userEvent.setup()
    const fetchStub = stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: post })
    const files = named('a.txt', 'b.txt')

    render(<LoadedDocuments />)
    await upload(user, ...files)

    expect(fileInput().files).toHaveLength(0)
    expect(fileInput().value).toBe('')

    await vi.waitFor(() => expect(summary()).not.toBeEmptyDOMElement())
    await upload(user, ...files)

    await vi.waitFor(() => expect(requestsTo(fetchStub, 'POST')).toHaveLength(4))
    expect(requestsTo(fetchStub, 'POST').map(sentFile)).toEqual([...files, ...files])
  })

  it('still sends every chosen file, although the input is emptied at once', async () => {
    const user = userEvent.setup()
    const fetchStub = stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })
    const files = named('a.txt', 'b.txt')

    render(<LoadedDocuments />)
    await upload(user, ...files)
    await vi.waitFor(() => expect(summary()).toHaveTextContent('2 uploaded, 0 failed.'))

    expect(requestsTo(fetchStub, 'POST').map(sentFile)).toEqual(files)
  })

  it('offers to clear the results once the run has ended, which hides the card and empties the status', async () => {
    const user = userEvent.setup()
    const { route, answer } = answers()
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: route })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt'))

    expect(clearButton()).not.toBeInTheDocument()

    await answer(0, uploaded('a.txt'))
    const status = summary()
    await user.click(clearButton()!)

    expect(screen.queryByRole('list', { name: 'Upload results' })).not.toBeInTheDocument()
    expect(clearButton()).not.toBeInTheDocument()
    // Still on the page, so it can announce the next run.
    expect(summary()).toBe(status)
    expect(status).toBeEmptyDOMElement()
  })

  it('shows two files with the same name in a run without a key warning', async () => {
    const user = userEvent.setup()
    const consoleError = vi.spyOn(console, 'error')
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json({ detail: 'Too large.' }, { status: 413 }),
    })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'a.txt'))
    await vi.waitFor(() => expect(summary()).toHaveTextContent('0 uploaded, 2 failed.'))

    expect(consoleError).not.toHaveBeenCalled()
  })

  it('shows HTML in a filename or a message as plain text', async () => {
    const user = userEvent.setup({ applyAccept: false })
    const html = '<img src=x onerror=alert(1)>'
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json({ detail: `${html} is too large.` }, { status: 413 }),
    })

    const { container } = render(<LoadedDocuments />)
    await upload(user, ...named(`${html}.txt`))

    // The row is there from the start, so it's the message that says the file has finished.
    expect(await screen.findByText(`${html} is too large.`)).toBeInTheDocument()
    expect(screen.getByText(`${html}.txt`)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('cuts a long filename short instead of widening the page, and wraps a long message', async () => {
    const user = userEvent.setup()
    const long = `${'long'.repeat(100)}.txt`
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await upload(user, ...named(long))
    await vi.waitFor(() => expect(summary()).toHaveTextContent('1 uploaded, 0 failed.'))

    expect(resultRows()[0]).toHaveStyle({ overflowWrap: 'anywhere', flexWrap: 'wrap' })
    const name = within(resultRows()[0]).getByText(long)
    expect(name).toHaveAttribute('title', long)
    expect(name).toHaveStyle({ minWidth: '0px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' })
  })

  it('keeps the drop zone inside the sidebar, with the input hidden in it', async () => {
    stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')

    expect(fileInput()).toHaveStyle({ position: 'absolute', width: '1px', height: '1px' })
    expect(dropZone()).toHaveStyle({ minWidth: '0px' })
    expect(within(dropZone()).getByText('or drop them here', { exact: false })).toHaveStyle({ minWidth: '0px' })
  })
})

describe('dropping files', () => {
  const answers = postsAnsweredByTheTest
  const uploaded = (filename: string) =>
    Response.json({ id: filename, filename, line_count: 1, page_count: null }, { status: 201 })

  it('uploads files dropped on the zone like chosen ones, one by one, in order', async () => {
    const { route, started, answer } = answers()
    const fetchStub = stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: route })
    const files = named('b.md', 'a.txt')

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    const { draggedOver, dropped } = drop(...files)

    // Both prevented, or the browser would refuse the drop or open the file in place of the app.
    expect(draggedOver).toBe(false)
    expect(dropped).toBe(false)
    await settle()
    expect(started()).toBe(1)
    expect(fileInput()).toBeDisabled()

    await answer(0, uploaded('b.md'))
    await answer(1, uploaded('a.txt'))

    await vi.waitFor(() => expect(summary()).toHaveTextContent('2 uploaded, 0 failed.'))
    expect(requestsTo(fetchStub, 'POST').map(sentFile)).toEqual(files)
  })

  it('leaves it to the backend to turn away a file of another type', async () => {
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json({ detail: 'Only .txt, .md and .pdf files are accepted.' }, { status: 415 }),
    })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    drop(new File(['PK'], 'report.docx'))

    expect(await screen.findByText('Only .txt, .md and .pdf files are accepted.')).toBeInTheDocument()
    expect(resultRows()[0]).toHaveTextContent('report.docx')
  })

  it('shows that the zone will take the files while they are dragged over it', async () => {
    stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')

    fireEvent.dragOver(dropZone(), { dataTransfer: { files: [], types: ['Files'] } })
    expect(dropZone()).toHaveClass('dragging')

    // Moving onto the text inside the zone doesn't count as leaving it. jsdom has no DragEvent to carry
    // relatedTarget, so these are mouse events of the same type.
    const leaveFor = (relatedTarget: Element) => new MouseEvent('dragleave', { bubbles: true, relatedTarget })
    fireEvent(dropZone(), leaveFor(within(dropZone()).getByText('Add files')))
    expect(dropZone()).toHaveClass('dragging')

    fireEvent(dropZone(), leaveFor(document.body))
    expect(dropZone()).not.toHaveClass('dragging')

    fireEvent.dragOver(dropZone(), { dataTransfer: { files: [], types: ['Files'] } })
    fireEvent.drop(dropZone(), { dataTransfer: { files: [], types: ['Files'] } })
    expect(dropZone()).not.toHaveClass('dragging')
  })

  it('turns away files dropped while a run goes on, still keeping the browser from opening them', async () => {
    const user = userEvent.setup()
    const { route, answer } = answers()
    const fetchStub = stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: route })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt'))
    const { draggedOver, dropped, dataTransfer } = drop(...named('b.txt'))

    expect(draggedOver).toBe(false)
    expect(dropped).toBe(false)
    expect(dataTransfer.dropEffect).toBe('none')
    expect(dropZone()).not.toHaveClass('dragging')

    await answer(0, uploaded('a.txt'))
    await settle()

    expect(requestsTo(fetchStub, 'POST')).toHaveLength(1)
    expect(resultRows()).toHaveLength(1)
  })
})

describe('deleting a document', () => {
  const short = { id: '2', filename: 'short.md', line_count: 1, page_count: null }
  const DELETE_NOTES = 'DELETE /api/documents/1'
  const DELETE_SHORT = 'DELETE /api/documents/2'

  const deleteButton = (filename: string) => screen.getByRole('button', { name: `Delete ${filename}` })
  const question = (filename: string) => screen.queryByRole('group', { name: `Delete ${filename}?` })
  const askedRow = (filename: string) => within(question(filename)!)
  const confirmIn = (filename: string) => askedRow(filename).getByRole('button', { name: 'Delete' })
  const cancelIn = (filename: string) => askedRow(filename).getByRole('button', { name: 'Cancel' })
  const rowOf = (filename: string) => within(documentList().getByText(filename).closest('li')!)
  const deletes = (fetchStub: ReturnType<typeof stubRoutes>) => requestsTo(fetchStub, 'DELETE').map(([url]) => url)
  const gets = (fetchStub: ReturnType<typeof stubRoutes>) => requestsTo(fetchStub, 'GET')

  // Answers one request only when the test says so.
  function waitingRoute() {
    let resolve: ((response: Response) => void) | undefined
    const route: Route = () => new Promise((res) => (resolve = res))
    return {
      route,
      answer: async (response: Response) => {
        await vi.waitFor(() => expect(resolve).toBeDefined())
        await act(async () => resolve!(response))
      },
    }
  }

  async function renderList(routes: Record<string, Route> = {}) {
    const fetchStub = stubRoutes({ [GET_LIST]: () => Response.json([notes, short]), ...routes })
    render(<LoadedDocuments />)
    await screen.findByRole('list', { name: 'Documents' })
    return fetchStub
  }

  it('gives each row a Delete button whose name says which file it deletes', async () => {
    await renderList()

    expect(rowOf('notes.txt').getByRole('button', { name: 'Delete notes.txt' })).toHaveTextContent('Delete')
    expect(rowOf('short.md').getByRole('button', { name: 'Delete short.md' })).toBeEnabled()
  })

  // jsdom can't hover, and ignores the media query that shows it on touch screens, so only the focus is checked.
  it('shows the Delete button of a row when the row holds the focus, and keeps it reachable when hidden', async () => {
    await renderList()

    expect(deleteButton('notes.txt')).toHaveStyle({ opacity: '0', width: '0px' })
    expect(deleteButton('notes.txt')).not.toHaveStyle({ display: 'none' })
    expect(deleteButton('notes.txt')).not.toHaveStyle({ visibility: 'hidden' })

    deleteButton('notes.txt').focus()

    expect(deleteButton('notes.txt')).toHaveStyle({ opacity: '1', width: '28px' })
    expect(deleteButton('short.md')).toHaveStyle({ opacity: '0', width: '0px' })
  })

  it('asks in the row first and sends nothing until the user confirms', async () => {
    const user = userEvent.setup()
    const confirmDialog = vi.spyOn(window, 'confirm')
    const fetchStub = await renderList()

    await user.click(deleteButton('notes.txt'))

    expect(question('notes.txt')).toBeInTheDocument()
    expect(rowOf('notes.txt').getByRole('group')).toBe(question('notes.txt'))
    expect(askedRow('notes.txt').getByText('Delete notes.txt?')).toBeInTheDocument()
    expect(cancelIn('notes.txt')).toBeEnabled()
    expect(question('short.md')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(confirmDialog).not.toHaveBeenCalled()
    expect(deletes(fetchStub)).toEqual([])
  })

  it('moves the focus to the confirm button when it asks', async () => {
    const user = userEvent.setup()
    await renderList()

    await user.click(deleteButton('notes.txt'))

    expect(confirmIn('notes.txt')).toHaveFocus()
  })

  it('closes the question on Cancel, sends nothing and puts the focus back on the row button', async () => {
    const user = userEvent.setup()
    const fetchStub = await renderList()

    await user.click(deleteButton('notes.txt'))
    await user.click(cancelIn('notes.txt'))

    expect(question('notes.txt')).not.toBeInTheDocument()
    expect(deleteButton('notes.txt')).toHaveFocus()
    expect(documentList().getByText('notes.txt')).toBeInTheDocument()
    expect(deletes(fetchStub)).toEqual([])
  })

  it('works from the keyboard', async () => {
    const user = userEvent.setup()
    const fetchStub = await renderList({ [DELETE_NOTES]: () => new Response(null, { status: 204 }) })

    deleteButton('notes.txt').focus()
    await user.keyboard('{Enter}')
    expect(confirmIn('notes.txt')).toHaveFocus()
    await user.keyboard('{Enter}')

    await vi.waitFor(() => expect(deletes(fetchStub)).toEqual(['/api/documents/1']))
  })

  it('sends a DELETE for that document once confirmed, then removes the row and reloads the list', async () => {
    const user = userEvent.setup()
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([notes, short]))
      .mockResolvedValueOnce(Response.json([short]))
    const fetchStub = await renderList({ [GET_LIST]: get, [DELETE_NOTES]: () => new Response(null, { status: 204 }) })

    await user.click(deleteButton('notes.txt'))
    await user.click(confirmIn('notes.txt'))

    await vi.waitFor(() => expect(get).toHaveBeenCalledTimes(2))
    expect(deletes(fetchStub)).toEqual(['/api/documents/1'])
    expect(documentList().queryByText('notes.txt')).not.toBeInTheDocument()
    expect(documentList().getByText('short.md')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('takes the row away as soon as the delete has worked, without waiting for the reload', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const get = vi.fn<Route>().mockResolvedValueOnce(Response.json([notes, short])).mockImplementation(route)
    const fetchStub = await renderList({ [GET_LIST]: get, [DELETE_NOTES]: () => new Response(null, { status: 204 }) })

    await user.click(deleteButton('notes.txt'))
    await user.click(confirmIn('notes.txt'))

    await vi.waitFor(() => expect(gets(fetchStub)).toHaveLength(2))
    expect(documentList().queryByText('notes.txt')).not.toBeInTheDocument()

    await answer(Response.json([short]))

    expect(documentList().queryByText('notes.txt')).not.toBeInTheDocument()
    expect(documentList().getByText('short.md')).toBeInTheDocument()
  })

  it('treats a 404 as done, since the document is gone either way', async () => {
    const user = userEvent.setup()
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([notes, short]))
      .mockResolvedValueOnce(Response.json([short]))
    await renderList({
      [GET_LIST]: get,
      [DELETE_NOTES]: () => Response.json({ detail: 'Document not found.' }, { status: 404 }),
    })

    await user.click(deleteButton('notes.txt'))
    await user.click(confirmIn('notes.txt'))

    await vi.waitFor(() => expect(get).toHaveBeenCalledTimes(2))
    expect(documentList().queryByText('notes.txt')).not.toBeInTheDocument()
    expect(screen.queryByText('Document not found.')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the row and shows the message from the backend when deleting fails', async () => {
    const user = userEvent.setup()
    const detail = 'The database is unavailable right now. Please try again.'
    const fetchStub = await renderList({ [DELETE_NOTES]: () => Response.json({ detail }, { status: 503 }) })

    await user.click(deleteButton('notes.txt'))
    await user.click(confirmIn('notes.txt'))

    expect(await rowOf('notes.txt').findByRole('alert')).toHaveTextContent(detail)
    expect(question('notes.txt')).not.toBeInTheDocument()
    expect(deleteButton('notes.txt')).toBeEnabled()
    expect(deleteButton('notes.txt')).toHaveFocus()
    // Nothing changed, so there's nothing to reload.
    expect(gets(fetchStub)).toHaveLength(1)
  })

  it.each<[string, Route]>([
    ['a 502 with no JSON', () => new Response('Bad Gateway', { status: 502 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('shows the fallback on %s', async (_name, route) => {
    const user = userEvent.setup()
    await renderList({ [DELETE_NOTES]: route })

    await user.click(deleteButton('notes.txt'))
    await user.click(confirmIn('notes.txt'))

    expect(await rowOf('notes.txt').findByRole('alert')).toHaveTextContent('Could not delete the document.')
  })

  it('removes the error when the user asks again', async () => {
    const user = userEvent.setup()
    await renderList({ [DELETE_NOTES]: () => new Response('Bad Gateway', { status: 502 }) })

    await user.click(deleteButton('notes.txt'))
    await user.click(confirmIn('notes.txt'))
    await rowOf('notes.txt').findByRole('alert')
    await user.click(deleteButton('notes.txt'))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(question('notes.txt')).toBeInTheDocument()
  })

  it('disables only the buttons of that row while its request runs', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    await renderList({ [DELETE_NOTES]: route })

    await user.click(deleteButton('notes.txt'))
    await user.click(confirmIn('notes.txt'))

    expect(confirmIn('notes.txt')).toBeDisabled()
    expect(cancelIn('notes.txt')).toBeDisabled()
    expect(deleteButton('short.md')).toBeEnabled()
    expect(fileInput()).toBeEnabled()

    await user.click(confirmIn('notes.txt'))
    await answer(new Response('Bad Gateway', { status: 502 }))

    expect(deleteButton('notes.txt')).toBeEnabled()
  })

  it('sends one request however often the confirm button is clicked', async () => {
    const user = userEvent.setup()
    const { route } = waitingRoute()
    const fetchStub = await renderList({ [DELETE_NOTES]: route })

    await user.click(deleteButton('notes.txt'))
    await user.dblClick(confirmIn('notes.txt'))
    await user.click(confirmIn('notes.txt'))

    expect(deletes(fetchStub)).toEqual(['/api/documents/1'])
  })

  it('disables every Delete button during an upload run, and enables them once it ends', async () => {
    const user = userEvent.setup()
    const { route, answer } = postsAnsweredByTheTest()
    const fetchStub = await renderList({ [POST_FILE]: route })

    await user.click(deleteButton('short.md'))
    await upload(user)

    expect(deleteButton('notes.txt')).toBeDisabled()
    expect(confirmIn('short.md')).toBeDisabled()
    expect(cancelIn('short.md')).toBeEnabled()
    await user.click(confirmIn('short.md'))
    expect(deletes(fetchStub)).toEqual([])

    await answer(0, new Response('Bad Gateway', { status: 502 }))

    expect(deleteButton('notes.txt')).toBeEnabled()
    expect(confirmIn('short.md')).toBeEnabled()
  })

  it('keeps an open question with its own document when a reload moves the rows', async () => {
    const user = userEvent.setup()
    const another = { id: '3', filename: 'another.txt', line_count: 1, page_count: null }
    // notes.txt was deleted somewhere else, so short.md moves up to where notes.txt was.
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([notes, short]))
      .mockResolvedValueOnce(Response.json([short, another]))
    const fetchStub = await renderList({
      [GET_LIST]: get,
      [POST_FILE]: () => Response.json(another, { status: 201 }),
      [DELETE_SHORT]: () => new Response(null, { status: 204 }),
    })

    await user.click(deleteButton('short.md'))
    await upload(user, new File(['text'], 'another.txt'))
    await documentList().findByText('another.txt')

    expect(question('short.md')).toBeInTheDocument()
    expect(rowOf('short.md').getByRole('group')).toBe(question('short.md'))
    expect(question('another.txt')).not.toBeInTheDocument()

    await user.click(confirmIn('short.md'))

    await vi.waitFor(() => expect(deletes(fetchStub)).toEqual(['/api/documents/2']))
  })

  it('keeps an open question with its own document when another row is deleted', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([notes, short]))
      .mockResolvedValueOnce(Response.json([short]))
    const fetchStub = await renderList({
      [GET_LIST]: get,
      [DELETE_NOTES]: route,
      [DELETE_SHORT]: () => new Response(null, { status: 204 }),
    })

    await user.click(deleteButton('notes.txt'))
    await user.click(confirmIn('notes.txt'))
    await user.click(deleteButton('short.md'))
    await answer(new Response(null, { status: 204 }))
    await vi.waitFor(() => expect(get).toHaveBeenCalledTimes(2))

    expect(documentList().queryByText('notes.txt')).not.toBeInTheDocument()
    expect(question('short.md')).toBeInTheDocument()
    expect(confirmIn('short.md')).toBeEnabled()

    await user.click(confirmIn('short.md'))

    await vi.waitFor(() => expect(deletes(fetchStub)).toEqual(['/api/documents/1', '/api/documents/2']))
  })

  it('closes an open question when its row leaves the list', async () => {
    const user = userEvent.setup()
    const another = { id: '3', filename: 'another.txt', line_count: 1, page_count: null }
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([notes, short]))
      .mockResolvedValueOnce(Response.json([short, another]))
    const fetchStub = await renderList({
      [GET_LIST]: get,
      [POST_FILE]: () => Response.json(another, { status: 201 }),
    })

    await user.click(deleteButton('notes.txt'))
    await upload(user, new File(['text'], 'another.txt'))
    await documentList().findByText('another.txt')

    expect(question('notes.txt')).not.toBeInTheDocument()
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
    expect(deletes(fetchStub)).toEqual([])
  })

  it('shows HTML in a filename as plain text in the question', async () => {
    const user = userEvent.setup()
    const html = '<img src=x onerror=alert(1)>.txt'
    stubRoutes({ [GET_LIST]: () => Response.json([{ ...notes, filename: html }]) })

    const { container } = render(<LoadedDocuments />)
    await user.click(await screen.findByRole('button', { name: `Delete ${html}` }))

    expect(question(html)).toHaveTextContent(`Delete ${html}?`)
    expect(container.querySelector('img')).toBeNull()
  })

  it('wraps a long filename in the question instead of widening the page', async () => {
    const user = userEvent.setup()
    const long = `${'long'.repeat(100)}.txt`
    stubRoutes({ [GET_LIST]: () => Response.json([{ ...notes, filename: long }]) })

    render(<LoadedDocuments />)
    await user.click(await screen.findByRole('button', { name: `Delete ${long}` }))

    expect(question(long)).toHaveStyle({ overflowWrap: 'anywhere', flexWrap: 'wrap', minWidth: '0px' })
    expect(question(long)?.closest('li')).toHaveStyle({ flexWrap: 'wrap' })
    expect(documentList().getByText(long)).toHaveStyle({ minWidth: '0px' })
  })

  it('marks the confirm button with the alert colour, and only that button', async () => {
    const user = userEvent.setup()
    await renderList({ [DELETE_NOTES]: () => new Response('Bad Gateway', { status: 502 }) })

    await user.click(deleteButton('notes.txt'))
    await user.click(confirmIn('notes.txt'))
    const alertColour = getComputedStyle(await screen.findByRole('alert')).color
    await user.click(deleteButton('notes.txt'))

    expect(getComputedStyle(confirmIn('notes.txt')).backgroundColor).toBe(alertColour)
    expect(getComputedStyle(cancelIn('notes.txt')).backgroundColor).not.toBe(alertColour)
    expect(getComputedStyle(deleteButton('short.md')).backgroundColor).not.toBe(alertColour)
  })
})
