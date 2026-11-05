import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'

// These tests render the whole page, so the list reaches Ask through the real hook and only fetch is faked.

type Route = (init?: RequestInit) => Response | Promise<Response>

// Stubs fetch and answers each request from the route named "METHOD url".
function stubRoutes(routes: Record<string, Route>) {
  const fetchStub = vi.fn<typeof fetch>(async (url, init) =>
    routes[`${init?.method ?? 'GET'} ${url}`](init),
  )
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

const GET_LIST = 'GET /api/datasets/d1/documents'
const POST_FILE = 'POST /api/datasets/d1/documents'

const notes = { id: '1', filename: 'notes.txt', line_count: 9 }
const report = { id: '2', filename: 'report.md', line_count: 9 }
const latest = { id: '3', filename: 'latest.txt', line_count: 9 }

const answered = {
  status: 'answered',
  answer: 'The answer.',
  citations: [
    { document_id: '1', filename: 'notes.txt', start_line: 3, end_line: 3, quote: 'the third line' },
    { document_id: '1', filename: 'notes.txt', start_line: 4, end_line: 6, quote: 'three more lines' },
  ],
}
const notFound = {
  status: 'not_found',
  answer: "Sorry, I can't find anything related to your question in the documents you provided.",
  citations: [],
}

// The page with these documents and, by default, an API that answers.
function stubPage(documents: (typeof notes)[], routes: Record<string, Route> = {}) {
  return stubRoutes({
    'GET /api/health': () => Response.json({ status: 'ok' }),
    'GET /api/datasets': () => Response.json([{ id: 'd1', name: 'Reports' }]),
    [GET_LIST]: () => Response.json(documents),
    'POST /api/ask': () => Response.json(answered),
    ...routes,
  })
}

// Like the real fetch: never answers by itself, and rejects once aborted.
const rejectsOnAbort: Route = (init) =>
  new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })

const documentSelect = () => screen.getByRole<HTMLSelectElement>('combobox', { name: 'Document' })
const questionBox = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Question' })
const askButton = () => screen.getByRole('button', { name: 'Ask' })

const askRequests = (fetchStub: ReturnType<typeof stubRoutes>) =>
  fetchStub.mock.calls.filter(([url]) => url === '/api/ask')

async function renderPage() {
  render(<App />)
  await screen.findByRole('button', { name: 'Ask' })
}

async function ask(user: UserEvent, question = 'Why?') {
  await user.clear(questionBox())
  await user.click(questionBox())
  await user.paste(question)
  await user.click(askButton())
}

async function sendFile(user: UserEvent, filename: string) {
  await user.upload(screen.getByLabelText('Choose a .txt or .md file'), new File(['text'], filename))
  await user.click(screen.getByRole('button', { name: 'Upload' }))
}

// Uploads a file and waits for the reloaded list to reach the select.
async function upload(user: UserEvent, filename: string) {
  await sendFile(user, filename)
  await screen.findByRole('option', { name: filename })
}

// The GET route for a list that changes: each load gets the next list, and the last one stays.
function listThatChanges(...lists: (typeof notes)[][]): Route {
  let load = 0
  return () => Response.json(lists[Math.min(load++, lists.length - 1)])
}

const postUpload: Route = () => Response.json(latest, { status: 201 })

// A route that gives these responses first, then waits until the test calls answer().
function waitingRoute(...first: Response[]) {
  let resolve!: (response: Response) => void
  const route = vi.fn<Route>().mockImplementation(() => new Promise((r) => (resolve = r)))
  for (const response of first) route.mockResolvedValueOnce(response)
  return { route, answer: (response: Response) => resolve(response) }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('without a document to ask about', () => {
  function expectPromptAndNoForm() {
    expect(screen.getByText('Upload a document to ask about it.')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Document' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Question' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ask' })).not.toBeInTheDocument()
  }

  it('shows the prompt when there are no documents', async () => {
    stubPage([])

    render(<App />)
    await screen.findByText('No documents yet.')

    expectPromptAndNoForm()
  })

  it('shows the prompt before the first load finishes', async () => {
    stubPage([], { [GET_LIST]: rejectsOnAbort })

    render(<App />)
    await screen.findByRole('heading', { name: 'Ask a question' })

    expectPromptAndNoForm()
  })

  it('shows the prompt when the first load fails', async () => {
    stubPage([], { [GET_LIST]: () => new Response('Bad Gateway', { status: 502 }) })

    render(<App />)
    await screen.findByRole('alert')

    expectPromptAndNoForm()
  })

  it('shows the form once the first document is uploaded', async () => {
    const user = userEvent.setup()
    stubPage([], {
      [GET_LIST]: listThatChanges([], [latest]),
      [POST_FILE]: postUpload,
    })

    render(<App />)
    await screen.findByText('No documents yet.')
    await upload(user, latest.filename)

    expect(documentSelect()).toHaveValue(latest.id)
    expect(screen.queryByText('Upload a document to ask about it.')).not.toBeInTheDocument()
  })
})

describe('choosing a document', () => {
  it('offers every document by filename and selects the newest', async () => {
    stubPage([notes, report])

    await renderPage()

    const options = within(documentSelect()).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual(['notes.txt', 'report.md'])
    expect(documentSelect()).toHaveValue(report.id)
  })

  it('keeps an explicit choice when the list reloads', async () => {
    const user = userEvent.setup()
    stubPage([], {
      [GET_LIST]: listThatChanges([notes, report], [notes, report, latest]),
      [POST_FILE]: postUpload,
    })

    await renderPage()
    await user.selectOptions(documentSelect(), notes.id)
    await upload(user, latest.filename)

    expect(documentSelect()).toHaveValue(notes.id)
  })

  it('goes back to the newest when the chosen document is gone', async () => {
    const user = userEvent.setup()
    stubPage([], {
      [GET_LIST]: listThatChanges([notes, report], [report, latest]),
      [POST_FILE]: postUpload,
    })

    await renderPage()
    await user.selectOptions(documentSelect(), notes.id)
    await upload(user, latest.filename)

    expect(documentSelect()).toHaveValue(latest.id)
  })

  it('moves to the newest after an upload when nothing was chosen', async () => {
    const user = userEvent.setup()
    stubPage([], {
      [GET_LIST]: listThatChanges([notes, report], [notes, report, latest]),
      [POST_FILE]: postUpload,
    })

    await renderPage()
    await upload(user, latest.filename)

    expect(documentSelect()).toHaveValue(latest.id)
  })

  it('keeps the form and the choice when a reload fails', async () => {
    const user = userEvent.setup()
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([notes, report]))
      .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
    stubPage([], { [GET_LIST]: get, [POST_FILE]: postUpload })

    await renderPage()
    await user.selectOptions(documentSelect(), notes.id)
    await sendFile(user, latest.filename)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the documents.')
    expect(documentSelect()).toHaveValue(notes.id)
  })

  it('moves to the newest again after a removed choice fell back', async () => {
    const user = userEvent.setup()
    const newer = { id: '4', filename: 'newer.txt', line_count: 9 }
    stubPage([], {
      [GET_LIST]: listThatChanges([notes, report], [report, latest], [report, latest, newer]),
      [POST_FILE]: postUpload,
    })

    await renderPage()
    await user.selectOptions(documentSelect(), notes.id)
    await upload(user, latest.filename)
    await upload(user, newer.filename)

    expect(documentSelect()).toHaveValue(newer.id)
  })
})

describe('the form', () => {
  it('limits the question to what the backend accepts', async () => {
    stubPage([notes])

    await renderPage()

    expect(questionBox()).toHaveAttribute('maxlength', '2000')
  })

  it('keeps the select and the question box inside the page width', async () => {
    stubPage([notes])

    await renderPage()

    for (const control of [documentSelect(), questionBox()]) {
      expect(control).toHaveStyle({ width: '100%', boxSizing: 'border-box' })
    }
  })
})

describe('asking', () => {
  it('posts the newest document and the trimmed question as JSON', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes, report])

    await renderPage()
    await ask(user, '  \n first line\nsecond line \t ')
    await screen.findByRole('article')

    const requests = askRequests(fetchStub)
    expect(requests).toHaveLength(1)
    const [url, init = {}] = requests[0]
    expect(url).toBe('/api/ask')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({
      document_id: report.id,
      question: 'first line\nsecond line',
    })
  })

  it('posts the document the user chose', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes, report])

    await renderPage()
    await user.selectOptions(documentSelect(), notes.id)
    await ask(user)
    await screen.findByRole('article')

    expect(JSON.parse(askRequests(fetchStub)[0][1]?.body as string).document_id).toBe(notes.id)
  })

  it('shows the answer with its citations and lets the user ask again', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await ask(user, '  Why?  ')

    const answer = within(await screen.findByRole('article'))
    // textContent, because getByText would hide spaces around the question.
    expect(answer.getByText(/You asked/).textContent).toBe('You asked about notes.txt: Why?')
    expect(answer.getByText('The answer.')).toBeInTheDocument()
    expect(answer.getByRole('heading', { name: 'Sources' })).toBeInTheDocument()
    expect(answer.getByText('Line 3')).toBeInTheDocument()
    expect(answer.getByText('Lines 4–6')).toBeInTheDocument()
    expect(answer.getAllByText('notes.txt')).toHaveLength(2)
    expect(answer.getAllByRole('blockquote').map((quote) => quote.textContent)).toEqual([
      'the third line',
      'three more lines',
    ])
    expect(askButton()).toBeEnabled()
  })

  it('shows the message and no citations when the document does not hold the answer', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => Response.json(notFound) })

    await renderPage()
    await ask(user)

    const answer = within(await screen.findByRole('article'))
    expect(answer.getByText(notFound.answer)).toBeInTheDocument()
    expect(answer.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
    expect(answer.queryByRole('list')).not.toBeInTheDocument()
    expect(answer.queryByRole('blockquote')).not.toBeInTheDocument()
  })

  it('shows HTML in the question, answer, filename and quote as plain text', async () => {
    const user = userEvent.setup()
    const html = '<img src=x onerror=alert(1)>'
    const filename = `${html}.txt`
    const citation = { document_id: '1', filename, start_line: 1, end_line: 1, quote: `${html} quote` }
    stubPage([{ ...notes, filename }], {
      'POST /api/ask': () =>
        Response.json({ status: 'answered', answer: `${html} answer`, citations: [citation] }),
    })

    const { container } = render(<App />)
    await screen.findByRole('button', { name: 'Ask' })
    await ask(user, `${html} question`)

    const answer = within(await screen.findByRole('article'))
    expect(screen.getByRole('option', { name: filename })).toBeInTheDocument()
    expect(answer.getByText(`You asked about ${filename}: ${html} question`)).toBeInTheDocument()
    expect(answer.getByText(`${html} answer`)).toBeInTheDocument()
    expect(answer.getByText(filename)).toBeInTheDocument()
    expect(answer.getByRole('blockquote').textContent).toBe(`${html} quote`)
    expect(container.querySelector('img')).toBeNull()
  })

  it('still says which question an answer is for after the box is edited', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByRole('article')
    await user.type(questionBox(), ' And how?')

    expect(screen.getByText('You asked about notes.txt: Why?')).toBeInTheDocument()
    expect(questionBox()).toHaveValue('Why? And how?')
  })

  it('still says which document an answer is for after another one is chosen', async () => {
    const user = userEvent.setup()
    stubPage([notes, report], { 'POST /api/ask': () => Response.json(notFound) })

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByRole('article')
    await user.selectOptions(documentSelect(), notes.id)

    expect(screen.getByText('You asked about report.md: Why?')).toBeInTheDocument()
  })

  it('stops the browser from submitting the form itself', async () => {
    stubPage([notes])

    await renderPage()

    // fireEvent returns false when the handler called preventDefault.
    expect(fireEvent.submit(questionBox().form!)).toBe(false)
  })
})

describe('an open citation', () => {
  const lines = Array.from({ length: 9 }, (_, index) => `line ${index + 1}`)
  const documentRoute: Route = () => Response.json({ ...notes, lines })

  const openViewers = () => screen.queryAllByRole('list', { name: /^Lines of/ })
  const expanded = () => screen.getAllByRole('button', { expanded: true })
  const documentRequests = (fetchStub: ReturnType<typeof stubRoutes>) =>
    fetchStub.mock.calls.filter(([url]) => url === '/api/documents/1')

  async function openFirstCitation(user: UserEvent) {
    await user.click(await screen.findByRole('button', { name: 'Line 3' }))
    await screen.findByRole('list', { name: 'Lines of notes.txt' })
  }

  it('is closed in the next answer, even when that answer has the same citations', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes], { 'GET /api/documents/1': documentRoute })

    await renderPage()
    await ask(user, 'Why?')
    await openFirstCitation(user)
    expect(expanded()).toHaveLength(1)

    await ask(user, 'How?')
    await screen.findByText('You asked about notes.txt: How?')

    expect(screen.getByRole('button', { name: 'Line 3' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: 'Lines 4–6' })).toHaveAttribute('aria-expanded', 'false')
    expect(openViewers()).toHaveLength(0)
    expect(documentRequests(fetchStub)).toHaveLength(1)
  })

  it('is cancelled and removed as soon as a new question is sent', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json(answered))
    const fetchStub = stubPage([notes], { 'POST /api/ask': route, 'GET /api/documents/1': rejectsOnAbort })

    await renderPage()
    await ask(user, 'Why?')
    await user.click(await screen.findByRole('button', { name: 'Line 3' }))
    await ask(user, 'How?')

    expect(documentRequests(fetchStub)[0][1]?.signal?.aborted).toBe(true)
    expect(screen.queryByRole('article')).not.toBeInTheDocument()

    answer(Response.json(answered))
    await screen.findByText('You asked about notes.txt: How?')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(openViewers()).toHaveLength(0)
  })

  it('stays open, without a new request, when the list reloads or an empty question is sent', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([], {
      [GET_LIST]: listThatChanges([notes], [notes, latest]),
      [POST_FILE]: postUpload,
      'GET /api/documents/1': documentRoute,
    })

    await renderPage()
    await ask(user, 'Why?')
    await openFirstCitation(user)
    await upload(user, latest.filename)

    expect(openViewers()).toHaveLength(1)

    await user.clear(questionBox())
    await user.click(askButton())

    expect(openViewers()).toHaveLength(1)
    expect(documentRequests(fetchStub)).toHaveLength(1)
  })
})

describe('a question with no text', () => {
  it.each([
    ['empty', ''],
    ['only whitespace', '  \n\t '],
  ])('shows an alert and sends nothing when it is %s', async (_name, question) => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes])

    await renderPage()
    await user.click(questionBox())
    if (question) await user.paste(question)
    await user.click(askButton())

    expect(screen.getByRole('alert')).toHaveTextContent('Type a question first.')
    expect(askRequests(fetchStub)).toHaveLength(0)
    expect(askButton()).toBeEnabled()
  })

  it('clears the alert when a real question is sent', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await user.click(askButton())
    await screen.findByRole('alert')
    await ask(user)
    await screen.findByRole('article')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('leaves the previous answer showing, since nothing was sent', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByRole('article')
    await user.clear(questionBox())
    await user.click(askButton())

    expect(screen.getByRole('alert')).toHaveTextContent('Type a question first.')
    expect(screen.getByText('You asked about notes.txt: Why?')).toBeInTheDocument()
  })
})

describe('while waiting for an answer', () => {
  it('disables the button and says so, then enables it again after a failure', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await ask(user)

    expect(screen.getByRole('button', { name: 'Asking…' })).toBeDisabled()

    answer(new Response('Bad Gateway', { status: 502 }))

    await screen.findByRole('alert')
    expect(askButton()).toBeEnabled()
  })

  it('removes the previous answer as soon as a new question is sent', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json(answered))
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByRole('article')
    await ask(user, 'How?')

    expect(screen.queryByRole('article')).not.toBeInTheDocument()

    answer(Response.json(notFound))

    expect(await screen.findByText('You asked about notes.txt: How?')).toBeInTheDocument()
    expect(screen.queryByText('You asked about notes.txt: Why?')).not.toBeInTheDocument()
  })

  it('removes the previous error as soon as a new question is sent', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json({ detail: 'Document not found.' }, { status: 404 }))
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await ask(user)
    await screen.findByRole('alert')
    await ask(user)

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    answer(Response.json(answered))

    await screen.findByRole('article')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('when asking fails', () => {
  it.each([
    [502, 'Gemini could not answer this question.'],
    [503, 'Gemini is unavailable right now. Please try again.'],
    [404, 'Document not found.'],
  ])('shows the message from the backend on a %i and keeps the question', async (status, detail) => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => Response.json({ detail }, { status }) })

    await renderPage()
    await ask(user, 'Why?')

    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
    expect(questionBox()).toHaveValue('Why?')
  })

  it.each<[string, Route]>([
    ['a 502 with no JSON', () => new Response('Bad Gateway', { status: 502 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['a validation error whose detail is an array', () => Response.json({ detail: [{ msg: 'x' }] }, { status: 422 })],
  ])('shows the fallback on %s and keeps the question', async (_name, post) => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': post })

    await renderPage()
    await ask(user, 'Why?')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not get an answer.')
    expect(questionBox()).toHaveValue('Why?')
  })

  it('does not leave the old answer showing', async () => {
    const user = userEvent.setup()
    const post = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json(answered))
      .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
    stubPage([notes], { 'POST /api/ask': post })

    await renderPage()
    await ask(user)
    await screen.findByRole('article')
    await ask(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not get an answer.')
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })
})
