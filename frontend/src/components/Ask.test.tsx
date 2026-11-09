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

const GET_DATASETS = 'GET /api/datasets'
const GET_LIST = 'GET /api/datasets/d1/documents'
const POST_FILE = 'POST /api/datasets/d1/documents'

const reports = { id: 'd1', name: 'Reports' }

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
const clarifying = {
  status: 'needs_clarification',
  answer: 'Did you lose a company laptop or a phone?',
  citations: [
    { document_id: '1', filename: 'notes.txt', start_line: 2, end_line: 2, quote: 'a lost laptop' },
    { document_id: '1', filename: 'notes.txt', start_line: 7, end_line: 8, quote: 'a lost phone' },
  ],
}

// The page with one dataset, Reports, holding these documents and, by default, an API that answers.
function stubPage(documents: (typeof notes)[], routes: Record<string, Route> = {}) {
  return stubRoutes({
    'GET /api/health': () => Response.json({ status: 'ok' }),
    [GET_DATASETS]: () => Response.json([reports]),
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

const prompt = 'Upload a document to ask about it.'
const questionBox = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Question' })
const askButton = () => screen.getByRole('button', { name: 'Ask' })

const askRequests = (fetchStub: ReturnType<typeof stubRoutes>) =>
  fetchStub.mock.calls.filter(([url]) => url === '/api/ask')
const askBodies = (fetchStub: ReturnType<typeof stubRoutes>) =>
  askRequests(fetchStub).map(([, init]) => JSON.parse(init?.body as string))

const replyBox = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Your reply' })
const replyButton = () => screen.getByRole('button', { name: 'Reply' })
const replyForm = () => within(replyBox().form!)

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

// Asks, and waits for the clarifying question by its reply box.
async function askAndGetClarifyingQuestion(user: UserEvent, question = 'What do I do?') {
  await ask(user, question)
  await screen.findByRole('textbox', { name: 'Your reply' })
}

async function reply(user: UserEvent, text = 'A laptop.') {
  await user.click(replyBox())
  await user.paste(text)
  await user.click(replyButton())
}

async function sendFile(user: UserEvent, filename: string) {
  await user.upload(screen.getByLabelText('Choose .txt or .md files'), new File(['text'], filename))
  await user.click(screen.getByRole('button', { name: 'Upload' }))
}

// Uploads a file and waits for the reloaded list to show it, by the Delete button in its row.
async function upload(user: UserEvent, filename: string) {
  await sendFile(user, filename)
  await screen.findByRole('button', { name: `Delete ${filename}` })
}

// The GET route for a list that changes: each load gets the next list, and the last one stays.
function listThatChanges(...lists: (typeof notes)[][]): Route {
  let load = 0
  return () => Response.json(lists[Math.min(load++, lists.length - 1)])
}

const postUpload: Route = () => Response.json(latest, { status: 201 })

// The POST route for answers that change: each question or reply gets the next answer, and the last one stays.
function answersInTurn(...answers: object[]): Route {
  let request = 0
  return () => Response.json(answers[Math.min(request++, answers.length - 1)])
}

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
    expect(screen.getByText(prompt)).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Question' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ask' })).not.toBeInTheDocument()
  }

  it('shows the prompt when the dataset has no documents', async () => {
    stubPage([])

    render(<App />)
    await screen.findByText('No documents yet.')

    expectPromptAndNoForm()
  })

  it('shows the prompt before the first load finishes', async () => {
    stubPage([], { [GET_LIST]: rejectsOnAbort })

    render(<App />)
    await screen.findByRole('heading', { name: 'Ask a question about Reports' })

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

    expect(questionBox()).toBeInTheDocument()
    expect(askButton()).toBeEnabled()
    expect(screen.queryByText(prompt)).not.toBeInTheDocument()
  })
})

describe('the section', () => {
  it('names the dataset it asks, and offers no choice of document', async () => {
    stubPage([notes, report])

    await renderPage()

    expect(screen.getByRole('heading', { name: 'Ask a question about Reports' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Document' })).not.toBeInTheDocument()
  })

  it('wraps a long dataset name in its heading instead of widening the page', async () => {
    const name = 'x'.repeat(100)
    stubPage([notes], { [GET_DATASETS]: () => Response.json([{ ...reports, name }]) })

    await renderPage()

    expect(screen.getByRole('heading', { name: `Ask a question about ${name}` })).toHaveStyle({
      overflowWrap: 'anywhere',
    })
  })

  it('limits the question to what the backend accepts', async () => {
    stubPage([notes])

    await renderPage()

    expect(questionBox()).toHaveAttribute('maxlength', '2000')
  })

  it('keeps the question box inside the page width', async () => {
    stubPage([notes])

    await renderPage()

    expect(questionBox()).toHaveStyle({ width: '100%', boxSizing: 'border-box' })
  })

  it('keeps the form and the typed question when a reload of the list fails', async () => {
    const user = userEvent.setup()
    const get = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json([notes, report]))
      .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
    stubPage([], { [GET_LIST]: get, [POST_FILE]: postUpload })

    await renderPage()
    await user.type(questionBox(), 'Why?')
    await sendFile(user, latest.filename)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the documents.')
    expect(questionBox()).toHaveValue('Why?')
    expect(askButton()).toBeEnabled()
  })
})

describe('asking', () => {
  it('posts the dataset and the trimmed question as JSON', async () => {
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
      dataset_id: reports.id,
      question: 'first line\nsecond line',
    })
    expect(JSON.parse(init.body as string)).not.toHaveProperty('clarification')
  })

  it('shows the answer with its citations and lets the user ask again', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await ask(user, '  Why?  ')

    const answer = within(await screen.findByRole('article'))
    // textContent, because getByText would hide spaces around the question.
    expect(answer.getByText(/You asked/).textContent).toBe('You asked about Reports: Why?')
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

  it('shows the message and no citations when the dataset does not hold the answer', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => Response.json(notFound) })

    await renderPage()
    await ask(user)

    const answer = within(await screen.findByRole('article'))
    expect(answer.getByText('You asked about Reports: Why?')).toBeInTheDocument()
    expect(answer.getByText(notFound.answer)).toBeInTheDocument()
    expect(answer.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
    expect(answer.queryByRole('list')).not.toBeInTheDocument()
    expect(answer.queryByRole('blockquote')).not.toBeInTheDocument()
  })

  it('shows a clarifying question with the lines it asks about, and not as a missing answer', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => Response.json(clarifying) })

    await renderPage()
    await ask(user, 'What do I do?')

    const answer = within(await screen.findByRole('article'))
    expect(answer.getByText('You asked about Reports: What do I do?')).toBeInTheDocument()
    expect(answer.getByText(clarifying.answer)).not.toHaveStyle({ fontStyle: 'italic' })
    expect(answer.getByRole('heading', { name: "Why I'm asking" })).toBeInTheDocument()
    expect(answer.getByText('Line 2')).toBeInTheDocument()
    expect(answer.getByText('Lines 7–8')).toBeInTheDocument()
    expect(answer.getAllByRole('blockquote').map((quote) => quote.textContent)).toEqual([
      'a lost laptop',
      'a lost phone',
    ])
    expect(askButton()).toBeEnabled()
  })

  it('shows HTML in the dataset name, question, answer, filename and quote as plain text', async () => {
    const user = userEvent.setup()
    const html = '<img src=x onerror=alert(1)>'
    const filename = `${html}.txt`
    const citation = { document_id: '1', filename, start_line: 1, end_line: 1, quote: `${html} quote` }
    stubPage([{ ...notes, filename }], {
      [GET_DATASETS]: () => Response.json([{ ...reports, name: html }]),
      'POST /api/ask': () =>
        Response.json({ status: 'answered', answer: `${html} answer`, citations: [citation] }),
    })

    const { container } = render(<App />)
    await screen.findByRole('button', { name: 'Ask' })
    await ask(user, `${html} question`)

    const answer = within(await screen.findByRole('article'))
    expect(screen.getByRole('heading', { name: `Ask a question about ${html}` })).toBeInTheDocument()
    expect(answer.getByText(`You asked about ${html}: ${html} question`)).toBeInTheDocument()
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

    expect(screen.getByText('You asked about Reports: Why?')).toBeInTheDocument()
    expect(questionBox()).toHaveValue('Why? And how?')
  })

  it('stops the browser from submitting the form itself', async () => {
    stubPage([notes])

    await renderPage()

    // fireEvent returns false when the handler called preventDefault.
    expect(fireEvent.submit(questionBox().form!)).toBe(false)
  })
})

describe('an answer that cites two files', () => {
  const fromTwoFiles = {
    status: 'answered',
    answer: 'The answer.',
    citations: [
      { document_id: '1', filename: 'notes.txt', start_line: 3, end_line: 3, quote: 'notes line 3' },
      { document_id: '2', filename: 'report.md', start_line: 2, end_line: 2, quote: 'report line 2' },
    ],
  }
  // Each document's lines say which document they're from, so a viewer showing the wrong one can't pass.
  function documentRoute(doc: typeof notes, prefix: string): Route {
    const lines = Array.from({ length: 9 }, (_, index) => `${prefix} line ${index + 1}`)
    return () => Response.json({ ...doc, lines })
  }

  function stubTwoFiles() {
    return stubPage([notes, report], {
      'POST /api/ask': () => Response.json(fromTwoFiles),
      'GET /api/documents/1': documentRoute(notes, 'notes'),
      'GET /api/documents/2': documentRoute(report, 'report'),
    })
  }

  const citationOf = (button: HTMLElement) => button.closest('li') as HTMLElement

  it('shows each citation with the file it comes from', async () => {
    const user = userEvent.setup()
    stubTwoFiles()

    await renderPage()
    await ask(user)

    const [first, second] = within(await screen.findByRole('article')).getAllByRole('listitem')
    expect(within(first).getByText('notes.txt')).toBeInTheDocument()
    expect(within(first).getByRole('button', { name: 'Line 3' })).toHaveAccessibleDescription('notes.txt')
    expect(within(first).getByRole('blockquote')).toHaveTextContent('notes line 3')
    expect(within(second).getByText('report.md')).toBeInTheDocument()
    expect(within(second).getByRole('button', { name: 'Line 2' })).toHaveAccessibleDescription('report.md')
    expect(within(second).getByRole('blockquote')).toHaveTextContent('report line 2')
  })

  it("opens each citation's lines in its own document", async () => {
    const user = userEvent.setup()
    const fetchStub = stubTwoFiles()

    await renderPage()
    await ask(user)
    const notesButton = await screen.findByRole('button', { name: 'Line 3' })
    const reportButton = screen.getByRole('button', { name: 'Line 2' })

    await user.click(notesButton)
    const notesViewer = await within(citationOf(notesButton)).findByRole('list', { name: 'Lines of notes.txt' })
    expect(within(notesViewer).getByText('notes line 3').closest('li')).toHaveAttribute('aria-current', 'true')

    await user.click(reportButton)
    const reportViewer = await within(citationOf(reportButton)).findByRole('list', { name: 'Lines of report.md' })
    expect(within(reportViewer).getByText('report line 2').closest('li')).toHaveAttribute('aria-current', 'true')
    expect(screen.queryByRole('list', { name: 'Lines of notes.txt' })).not.toBeInTheDocument()

    const documentRequests = fetchStub.mock.calls.filter(([url]) => String(url).startsWith('/api/documents/'))
    expect(documentRequests.map(([url]) => url)).toEqual(['/api/documents/1', '/api/documents/2'])
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
    await screen.findByText('You asked about Reports: How?')

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
    await screen.findByText('You asked about Reports: How?')

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
    expect(screen.getByText('You asked about Reports: Why?')).toBeInTheDocument()
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

    expect(await screen.findByText('You asked about Reports: How?')).toBeInTheDocument()
    expect(screen.queryByText('You asked about Reports: Why?')).not.toBeInTheDocument()
  })

  it('removes the previous error as soon as a new question is sent', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json({ detail: 'Dataset not found.' }, { status: 404 }))
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
    [404, 'Dataset not found.'],
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

describe('when a document is deleted', () => {
  const deleted: Route = () => new Response(null, { status: 204 })

  async function deleteFromTheList(user: UserEvent, filename: string) {
    await user.click(screen.getByRole('button', { name: `Delete ${filename}` }))
    const question = screen.getByRole('group', { name: `Delete ${filename}?` })
    await user.click(within(question).getByRole('button', { name: 'Delete' }))
  }

  it('keeps the form while other documents are left', async () => {
    const user = userEvent.setup()
    stubPage([], {
      [GET_LIST]: listThatChanges([notes, report], [report]),
      'DELETE /api/documents/1': deleted,
    })

    await renderPage()
    await user.type(questionBox(), 'Why?')
    await deleteFromTheList(user, 'notes.txt')
    await vi.waitFor(() => expect(screen.queryByRole('button', { name: 'Delete notes.txt' })).not.toBeInTheDocument())

    expect(questionBox()).toHaveValue('Why?')
    expect(askButton()).toBeEnabled()
  })

  it('shows the prompt again when the last document is deleted', async () => {
    const user = userEvent.setup()
    stubPage([], { [GET_LIST]: listThatChanges([notes], []), 'DELETE /api/documents/1': deleted })

    await renderPage()
    await deleteFromTheList(user, 'notes.txt')

    expect(await screen.findByText(prompt)).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Question' })).not.toBeInTheDocument()
  })

  it('takes the form away at once when the last one goes, while the reloaded list is on its way', async () => {
    const user = userEvent.setup()
    const { route } = waitingRoute(Response.json([notes]))
    stubPage([], { [GET_LIST]: route, 'DELETE /api/documents/1': deleted })

    await renderPage()
    await deleteFromTheList(user, 'notes.txt')

    await vi.waitFor(() => expect(route).toHaveBeenCalledTimes(2))
    expect(screen.getByText(prompt)).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Question' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ask' })).not.toBeInTheDocument()
  })

  it('keeps an answer about it, whose citations then say the document is gone', async () => {
    const user = userEvent.setup()
    stubPage([], {
      [GET_LIST]: listThatChanges([notes, report], [report]),
      'DELETE /api/documents/1': deleted,
      'GET /api/documents/1': () => Response.json({ detail: 'Document not found.' }, { status: 404 }),
    })

    await renderPage()
    await ask(user)
    await screen.findByText('The answer.')
    await deleteFromTheList(user, 'notes.txt')
    await vi.waitFor(() => expect(screen.queryByRole('button', { name: 'Delete notes.txt' })).not.toBeInTheDocument())

    expect(screen.getByText('The answer.')).toBeInTheDocument()
    expect(screen.getByText('You asked about Reports: Why?')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Line 3' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Document not found.')
    expect(screen.getByText('The answer.')).toBeInTheDocument()
  })
})

describe('a clarifying question', () => {
  it('has a reply box below its sources, limited like the question', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => Response.json(clarifying) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)

    expect(screen.getByRole('article').nextElementSibling).toBe(replyBox().form)
    expect(replyBox()).toHaveAttribute('maxlength', '2000')
    expect(replyBox()).toHaveValue('')
    expect(replyBox()).toHaveStyle({ width: '100%', boxSizing: 'border-box' })
    expect(replyButton()).toBeEnabled()
  })

  it('sends the reply with the question as asked and the clarifying question exactly as it came', async () => {
    const user = userEvent.setup()
    // Spaces and a line break around it, so trimming it on the way back can't pass.
    const asked = { ...clarifying, answer: ' Did you lose a company laptop\nor a phone? ' }
    const fetchStub = stubPage([notes], { 'POST /api/ask': answersInTurn(asked, answered) })

    await renderPage()
    await askAndGetClarifyingQuestion(user, '  What do I do?  ')
    // The reply goes with the question it clarifies, not with what's in the box now.
    await user.type(questionBox(), ' And when?')
    await reply(user, '  A laptop.\n ')
    await screen.findByText('The answer.')

    const requests = askRequests(fetchStub)
    expect(requests).toHaveLength(2)
    const [url, init = {}] = requests[1]
    expect(url).toBe('/api/ask')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({
      dataset_id: reports.id,
      question: 'What do I do?',
      clarification: { question: ' Did you lose a company laptop\nor a phone? ', reply: 'A laptop.' },
    })
  })

  it('is followed by the answer, with the whole exchange above it and no reply box', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': answersInTurn(clarifying, answered) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)
    await screen.findByText('The answer.')

    const answer = within(screen.getByRole('article'))
    expect(answer.getAllByRole('paragraph').map((paragraph) => paragraph.textContent)).toEqual([
      'You asked about Reports: What do I do?',
      'I asked: Did you lose a company laptop or a phone?',
      'You replied: A laptop.',
      'The answer.',
    ])
    expect(answer.getByRole('heading', { name: 'Sources' })).toBeInTheDocument()
    expect(answer.queryByRole('heading', { name: "Why I'm asking" })).not.toBeInTheDocument()
    expect(answer.getAllByRole('blockquote').map((quote) => quote.textContent)).toEqual([
      'the third line',
      'three more lines',
    ])
    expect(screen.queryByRole('textbox', { name: 'Your reply' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Repl/ })).not.toBeInTheDocument()
    expect(askButton()).toBeEnabled()
  })

  it('gets no second reply box, even when the answer to the reply asks again', async () => {
    const user = userEvent.setup()
    const again = { ...clarifying, answer: 'Which laptop?' }
    const fetchStub = stubPage([notes], { 'POST /api/ask': answersInTurn(clarifying, again) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)

    expect(await screen.findByText('Which laptop?')).toBeInTheDocument()
    expect(screen.getByText('You replied: A laptop.')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Your reply' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Repl/ })).not.toBeInTheDocument()
    expect(askRequests(fetchStub)).toHaveLength(2)
  })

  it('leaves its open citation behind: the answer to the reply starts with every citation closed', async () => {
    const user = userEvent.setup()
    const lines = Array.from({ length: 9 }, (_, index) => `line ${index + 1}`)
    stubPage([notes], {
      'POST /api/ask': answersInTurn(clarifying, answered),
      'GET /api/documents/1': () => Response.json({ ...notes, lines }),
    })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await user.click(screen.getByRole('button', { name: 'Line 2' }))
    await screen.findByRole('list', { name: 'Lines of notes.txt' })
    await reply(user)
    await screen.findByText('The answer.')

    expect(screen.getByRole('button', { name: 'Line 3' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: 'Lines 4–6' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryAllByRole('list', { name: /^Lines of/ })).toHaveLength(0)
  })

  it('stops the browser from submitting the reply form itself', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => Response.json(clarifying) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)

    // fireEvent returns false when the handler called preventDefault.
    expect(fireEvent.submit(replyBox().form!)).toBe(false)
  })
})

describe('a reply with no text', () => {
  it.each([
    ['empty', ''],
    ['only whitespace', '  \n\t '],
  ])('shows an alert and sends nothing when it is %s', async (_name, text) => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes], { 'POST /api/ask': () => Response.json(clarifying) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await user.click(replyBox())
    if (text) await user.paste(text)
    await user.click(replyButton())

    expect(replyForm().getByRole('alert')).toHaveTextContent('Type a reply first.')
    expect(askRequests(fetchStub)).toHaveLength(1)
    expect(replyButton()).toBeEnabled()
    expect(screen.getByText(clarifying.answer)).toBeInTheDocument()
  })

  it('clears the alert when a real reply is sent', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': answersInTurn(clarifying, answered) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await user.click(replyButton())
    await screen.findByRole('alert')
    await reply(user)
    await screen.findByText('The answer.')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('while waiting for the answer to a reply', () => {
  it('disables Reply and Ask and says so, and keeps the clarifying question and the question box', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json(clarifying))
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)

    expect(screen.getByRole('button', { name: 'Replying…' })).toBeDisabled()
    expect(askButton()).toBeDisabled()
    expect(screen.getByText(clarifying.answer)).toBeInTheDocument()
    await user.type(questionBox(), ' And when?')
    expect(questionBox()).toHaveValue('What do I do? And when?')

    answer(Response.json(answered))

    expect(await screen.findByText('You replied: A laptop.')).toBeInTheDocument()
    expect(askButton()).toBeEnabled()
  })

  it('enables Reply and Ask again after a failure', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json(clarifying))
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)
    answer(new Response('Bad Gateway', { status: 502 }))

    await screen.findByRole('alert')
    expect(replyButton()).toBeEnabled()
    expect(askButton()).toBeEnabled()
  })
})

describe('when a reply fails', () => {
  const detail = 'Gemini could not answer this question.'

  it.each<[string, Route, string]>([
    ['a 502 with a detail', () => Response.json({ detail }, { status: 502 }), detail],
    ['a 502 with no JSON', () => new Response('Bad Gateway', { status: 502 }), 'Could not get an answer.'],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch')), 'Could not get an answer.'],
  ])('shows the message by the reply box after %s, and keeps what was asked', async (_name, failure, message) => {
    const user = userEvent.setup()
    const post = vi.fn<Route>().mockResolvedValueOnce(Response.json(clarifying)).mockImplementationOnce(failure)
    stubPage([notes], { 'POST /api/ask': post })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user, ' A laptop.\n')

    expect(await replyForm().findByRole('alert')).toHaveTextContent(message)
    // As typed: only what's sent is trimmed.
    expect(replyBox()).toHaveValue(' A laptop.\n')
    expect(screen.getByText(clarifying.answer)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: "Why I'm asking" })).toBeInTheDocument()
    expect(screen.getAllByRole('blockquote')).toHaveLength(2)
    expect(screen.queryByText(/You replied/)).not.toBeInTheDocument()
  })

  it('sends the same reply again, and shows its answer without the error', async () => {
    const user = userEvent.setup()
    const post = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json(clarifying))
      .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
      .mockResolvedValueOnce(Response.json(answered))
    const fetchStub = stubPage([notes], { 'POST /api/ask': post })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)
    await screen.findByRole('alert')
    await user.click(replyButton())

    expect(await screen.findByText('You replied: A laptop.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    const [, failed, retried] = askBodies(fetchStub)
    expect(retried).toEqual(failed)
    expect(retried.clarification).toEqual({ question: clarifying.answer, reply: 'A laptop.' })
  })
})

describe('a new question after a clarifying question', () => {
  it('clears the exchange, and is sent with no clarification', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes], { 'POST /api/ask': answersInTurn(clarifying, answered) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)
    await screen.findByText('You replied: A laptop.')
    await ask(user, 'How?')
    await screen.findByText('You asked about Reports: How?')

    expect(screen.queryByText(/I asked/)).not.toBeInTheDocument()
    expect(screen.queryByText(/You replied/)).not.toBeInTheDocument()
    expect(screen.queryByText('You asked about Reports: What do I do?')).not.toBeInTheDocument()
    const bodies = askBodies(fetchStub)
    expect(bodies).toHaveLength(3)
    expect(bodies[2]).toEqual({ dataset_id: reports.id, question: 'How?' })
    expect(bodies[2]).not.toHaveProperty('clarification')
  })

  it('takes the clarifying question and the typed reply away as soon as it is sent', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json(clarifying))
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await user.type(replyBox(), 'A laptop.')
    await ask(user, 'How?')

    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Your reply' })).not.toBeInTheDocument()

    answer(Response.json(clarifying))

    expect(await screen.findByText('You asked about Reports: How?')).toBeInTheDocument()
    expect(replyBox()).toHaveValue('')
  })
})
