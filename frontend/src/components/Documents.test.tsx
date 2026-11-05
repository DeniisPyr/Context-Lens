import { act, fireEvent, render, renderHook, screen, within } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
import { StrictMode, useState } from 'react'
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

// Documents gets its list as props, so this loads it with the real hook, the way DatasetContents does.
function LoadedDocuments() {
  const { documents, error, reload, remove } = useDocuments('d1')
  const [busy, setBusy] = useState(false)
  return (
    <Documents
      datasetId="d1"
      documents={documents}
      error={error}
      busy={busy}
      onBusyChange={setBusy}
      onUploaded={reload}
      onDeleted={remove}
    />
  )
}

const GET_LIST = 'GET /api/datasets/d1/documents'
const POST_FILE = 'POST /api/datasets/d1/documents'

const notes = { id: '1', filename: 'notes.txt', line_count: 2 }

// Like the real fetch: never answers by itself, and rejects once aborted.
const rejectsOnAbort: Route = (init) =>
  new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })

const fileInput = () => screen.getByLabelText<HTMLInputElement>('Choose .txt or .md files')
const uploadButton = () => screen.getByRole('button', { name: 'Upload' })
const summary = () => screen.getByRole('status')
const documentList = () => within(screen.getByRole('list', { name: 'Documents' }))
const resultRows = () => within(screen.getByRole('list', { name: 'Upload results' })).getAllByRole('listitem')

async function upload(user: UserEvent, ...files: File[]) {
  await user.upload(fileInput(), files.length > 0 ? files : new File(['one\ntwo\n'], 'notes.txt'))
  await user.click(uploadButton())
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
    const short = { id: '2', filename: 'short.md', line_count: 1 }
    stubRoutes({ [GET_LIST]: () => Response.json([notes, short]) })

    render(<LoadedDocuments />)

    const rows = await screen.findAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('notes.txt')
    expect(rows[0]).toHaveTextContent('2 lines')
    expect(rows[1]).toHaveTextContent('short.md')
    expect(within(rows[1]).getByText('1 line')).toBeInTheDocument()
    expect(screen.queryByText('No documents yet.')).not.toBeInTheDocument()
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
    const other = { id: '2', filename: 'other.txt', line_count: 5 }
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
      [POST_FILE]: () => Response.json({ detail: 'Only .txt and .md are allowed.' }, { status: 415 }),
    })

    render(<LoadedDocuments />)
    await upload(user, new File(['%PDF'], 'report.pdf'))

    await screen.findByText('Only .txt and .md are allowed.')
    expect(resultRows()[0]).toHaveTextContent('report.pdf')
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

  it('asks for a file and sends nothing when no file is chosen', async () => {
    const user = userEvent.setup()
    const fetchStub = stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    await user.click(uploadButton())

    expect(screen.getByRole('alert')).toHaveTextContent('Choose a file first.')
    expect(fetchStub).toHaveBeenCalledTimes(1)
  })

  it('removes the alert about choosing a file when a run starts', async () => {
    const user = userEvent.setup()
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    await user.click(uploadButton())
    await screen.findByRole('alert')
    await upload(user)
    await screen.findByText('Uploaded')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the rows of the last run when no file is chosen, since nothing started', async () => {
    const user = userEvent.setup()
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await upload(user)
    await screen.findByText('Uploaded')
    await user.click(uploadButton())

    expect(screen.getByRole('alert')).toHaveTextContent('Choose a file first.')
    expect(screen.getByText('Uploaded')).toBeInTheDocument()
    expect(summary()).toHaveTextContent('1 uploaded, 0 failed.')
  })

  it('stops the browser from submitting the form itself', async () => {
    stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')

    // fireEvent returns false when the handler called preventDefault.
    expect(fireEvent.submit(fileInput().form!)).toBe(false)
  })

  it('does not accept other file types in the file chooser', async () => {
    const user = userEvent.setup()
    stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')
    await user.upload(fileInput(), new File(['%PDF'], 'report.pdf'))

    expect(fileInput().files).toHaveLength(0)
  })

  it('disables the button while uploading and enables it after a failure', async () => {
    const user = userEvent.setup()
    let answer!: (response: Response) => void
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => new Promise((resolve) => (answer = resolve)),
    })

    render(<LoadedDocuments />)
    await upload(user)

    expect(screen.getByRole('button', { name: 'Uploading 1 of 1…' })).toBeDisabled()

    answer(new Response('Bad Gateway', { status: 502 }))

    await screen.findByText('Could not upload the file.')
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
  const uploaded = (filename: string) => Response.json({ id: filename, filename, line_count: 1 }, { status: 201 })

  it('lets the user choose several text files', async () => {
    stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')

    expect(fileInput()).toHaveAttribute('multiple')
    expect(fileInput()).toHaveAttribute('accept', '.txt,.md')
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

    expect(screen.getByRole('button', { name: 'Uploading 1 of 3…' })).toBeDisabled()
    expect(fileInput()).toBeDisabled()

    await answer(0, uploaded('a.txt'))
    expect(screen.getByRole('button', { name: 'Uploading 2 of 3…' })).toBeDisabled()

    await answer(1, new Response('Bad Gateway', { status: 502 }))
    expect(screen.getByRole('button', { name: 'Uploading 3 of 3…' })).toBeDisabled()
    expect(fileInput()).toBeDisabled()

    await answer(2, uploaded('c.txt'))
    expect(uploadButton()).toBeEnabled()
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
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: post })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'b.txt'))
    await vi.waitFor(() => expect(summary()).toHaveTextContent('1 uploaded, 1 failed.'))

    // Clicking with no file chosen puts a real alert on the page to compare with.
    await user.click(uploadButton())
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
    const first = { id: '1', filename: 'a.txt', line_count: 1 }
    const second = { id: '2', filename: 'c.txt', line_count: 1 }
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

  it('shows each row as its file finishes', async () => {
    const user = userEvent.setup()
    const { route, answer } = answers()
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: route })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'b.txt'))
    expect(screen.queryByRole('list', { name: 'Upload results' })).not.toBeInTheDocument()

    await answer(0, uploaded('a.txt'))
    expect(resultRows()).toHaveLength(1)

    await answer(1, uploaded('b.txt'))
    expect(resultRows()).toHaveLength(2)
  })

  it.each<[string, Route]>([
    ['every file worked', () => Response.json(notes, { status: 201 })],
    ['every file failed', () => new Response('Bad Gateway', { status: 502 })],
  ])('empties the input when the run ends and %s, so the same files can be chosen again', async (_name, post) => {
    const user = userEvent.setup()
    stubRoutes({ [GET_LIST]: () => Response.json([]), [POST_FILE]: post })
    const files = named('a.txt', 'b.txt')

    render(<LoadedDocuments />)
    await upload(user, ...files)
    await vi.waitFor(() => expect(resultRows()).toHaveLength(2))
    await vi.waitFor(() => expect(uploadButton()).toBeEnabled())

    expect(fileInput().files).toHaveLength(0)
    expect(fileInput().value).toBe('')

    await user.upload(fileInput(), files)

    expect(fileInput().files).toHaveLength(2)
  })

  it('still sends every chosen file, although the input is emptied afterwards', async () => {
    const user = userEvent.setup()
    const fetchStub = stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await upload(user, ...named('a.txt', 'b.txt'))
    await vi.waitFor(() => expect(uploadButton()).toBeEnabled())
    await user.click(uploadButton())

    expect(requestsTo(fetchStub, 'POST')).toHaveLength(2)
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a file first.')
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
    await vi.waitFor(() => expect(resultRows()).toHaveLength(2))

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

    expect(await screen.findByText(`${html}.txt`)).toBeInTheDocument()
    expect(screen.getByText(`${html} is too large.`)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('wraps a long filename instead of widening the page', async () => {
    const user = userEvent.setup()
    stubRoutes({
      [GET_LIST]: () => Response.json([]),
      [POST_FILE]: () => Response.json(notes, { status: 201 }),
    })

    render(<LoadedDocuments />)
    await upload(user, ...named(`${'long'.repeat(100)}.txt`))
    await vi.waitFor(() => expect(resultRows()).toHaveLength(1))

    expect(resultRows()[0]).toHaveStyle({ overflowWrap: 'anywhere', flexWrap: 'wrap' })
  })

  it('lets the file input shrink to the width of a phone', async () => {
    stubRoutes({ [GET_LIST]: () => Response.json([]) })

    render(<LoadedDocuments />)
    await screen.findByText('No documents yet.')

    expect(fileInput()).toHaveStyle({ minWidth: '0px', maxWidth: '100%' })
    expect(fileInput().closest('label')).toHaveStyle({ minWidth: '0px' })
  })
})

describe('deleting a document', () => {
  const short = { id: '2', filename: 'short.md', line_count: 1 }
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
    expect(uploadButton()).toBeEnabled()
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
    const another = { id: '3', filename: 'another.txt', line_count: 1 }
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
    const another = { id: '3', filename: 'another.txt', line_count: 1 }
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
