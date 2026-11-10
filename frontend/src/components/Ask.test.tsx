import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'

// These tests render the whole page, so the list reaches the ask box through the real hook and only fetch is faked.

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

const notes = { id: '1', filename: 'notes.txt', line_count: 9, page_count: null }
const report = { id: '2', filename: 'report.md', line_count: 9, page_count: null }
const latest = { id: '3', filename: 'latest.txt', line_count: 9, page_count: null }

const answered = {
  status: 'answered',
  answer: 'The answer.',
  citations: [
    {
      document_id: '1',
      filename: 'notes.txt',
      start_line: 3,
      end_line: 3,
      start_page: null,
      end_page: null,
      quote: 'the third line',
    },
    {
      document_id: '1',
      filename: 'notes.txt',
      start_line: 4,
      end_line: 6,
      start_page: null,
      end_page: null,
      quote: 'three more lines',
    },
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
    {
      document_id: '1',
      filename: 'notes.txt',
      start_line: 2,
      end_line: 2,
      start_page: null,
      end_page: null,
      quote: 'a lost laptop',
    },
    {
      document_id: '1',
      filename: 'notes.txt',
      start_line: 7,
      end_line: 8,
      start_page: null,
      end_page: null,
      quote: 'a lost phone',
    },
  ],
}

// The page with one dataset, Reports, holding these documents and, by default, an API that answers.
function stubPage(documents: (typeof notes)[], routes: Record<string, Route> = {}) {
  return stubRoutes({
    'GET /api/health': () => Response.json({ status: 'ok' }),
    'GET /api/session': () => Response.json({ login_required: false, logged_in: true }),
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

const prompt = 'Add files to Reports to ask about them.'
const questionBox = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Question' })
const askButton = () => screen.getByRole('button', { name: 'Ask' })

// A card by its number and question, as its heading names it.
const card = (number: number, question: string) => screen.getByRole('article', { name: `Q${number} ${question}` })
const findCard = (number: number, question: string) =>
  screen.findByRole('article', { name: `Q${number} ${question}` })
const cards = () => screen.queryAllByRole('article')
const cardHeadings = () => screen.queryAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)

const askRequests = (fetchStub: ReturnType<typeof stubRoutes>) =>
  fetchStub.mock.calls.filter(([url]) => url === '/api/ask')
const askBodies = (fetchStub: ReturnType<typeof stubRoutes>) =>
  askRequests(fetchStub).map(([, init]) => JSON.parse(init?.body as string))

const panel = () => screen.queryByRole('complementary', { name: 'Source' })

const replyBox = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Your reply' })
const replyButton = () => screen.getByRole('button', { name: 'Reply' })
const replyForm = () => within(replyBox().form!)

// What was asked back and what was replied, as the rows of a card show them.
const exchangeIn = (element: HTMLElement) =>
  within(element)
    .queryAllByRole('term')
    .map((term) => `${term.textContent}: ${term.nextElementSibling?.textContent}`)

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
  await user.upload(screen.getByLabelText('Add files'), new File(['text'], filename))
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
  vi.restoreAllMocks()
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
    await screen.findByText(prompt)

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

describe('before the first question', () => {
  it('says what can come back', async () => {
    stubPage([notes])

    await renderPage()

    const heading = screen.getByRole('heading', { name: 'Ask your first question about Reports' })
    const lines = within(heading.nextElementSibling as HTMLElement).getAllByRole('listitem')
    expect(lines.map((line) => line.textContent)).toEqual([
      'An answer, with the exact lines it comes from.',
      '“Not found”, when the documents don’t say.',
      'A question back, when the answer depends on your situation.',
    ])
    expect(cards()).toHaveLength(0)
  })

  it('wraps a long dataset name instead of widening the page', async () => {
    const name = 'x'.repeat(100)
    stubPage([notes], { [GET_DATASETS]: () => Response.json([{ ...reports, name }]) })

    await renderPage()

    expect(screen.getByRole('heading', { name: `Ask your first question about ${name}` })).toHaveStyle({
      overflowWrap: 'anywhere',
    })
  })

  it('goes once the first question is sent', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await ask(user)

    expect(screen.queryByRole('heading', { name: /^Ask your first question/ })).not.toBeInTheDocument()
    expect(await findCard(1, 'Why?')).toBeInTheDocument()
  })
})

describe('the ask box', () => {
  it('names the dataset it asks, and offers no choice of document', async () => {
    stubPage([notes, report])

    await renderPage()

    expect(questionBox()).toHaveAttribute('placeholder', 'Ask a question about Reports')
    expect(within(screen.getByRole('main')).getByText('Reports')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Document' })).not.toBeInTheDocument()
  })

  it('describes the box by its hint, and counts the characters against the limit', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()

    expect(questionBox()).toHaveAccessibleDescription(
      'Include everything the question needs. Answers cite the exact lines.',
    )
    expect(screen.getByText('0 / 2,000')).toBeInTheDocument()

    await user.type(questionBox(), 'Why?')

    expect(screen.getByText('4 / 2,000')).toBeInTheDocument()

    await user.clear(questionBox())
    await user.click(questionBox())
    await user.paste('x'.repeat(1234))

    expect(screen.getByText('1,234 / 2,000')).toBeInTheDocument()
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

  it('is empty again once a question is sent', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await ask(user, 'Why?')

    expect(questionBox()).toHaveValue('')
    expect(screen.getByText('0 / 2,000')).toBeInTheDocument()
    await findCard(1, 'Why?')
  })
})

describe('the keys of the ask box', () => {
  it('sends the question with Enter', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes])

    await renderPage()
    await user.type(questionBox(), 'Why?{Enter}')

    expect(await findCard(1, 'Why?')).toBeInTheDocument()
    expect(askBodies(fetchStub)).toEqual([{ dataset_id: reports.id, question: 'Why?' }])
    expect(questionBox()).toHaveValue('')
  })

  it('starts a new line with Shift+Enter, and sends nothing', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes])

    await renderPage()
    await user.type(questionBox(), 'first{Shift>}{Enter}{/Shift}second')

    expect(questionBox()).toHaveValue('first\nsecond')
    expect(askRequests(fetchStub)).toHaveLength(0)

    await user.keyboard('{Enter}')

    expect(await findCard(1, 'first\nsecond')).toBeInTheDocument()
  })

  it('leaves Enter to an input method while it is composing', async () => {
    const fetchStub = stubPage([notes])

    await renderPage()
    fireEvent.change(questionBox(), { target: { value: 'にほん' } })
    const composing = fireEvent.keyDown(questionBox(), { key: 'Enter', isComposing: true })
    // Safari: the composition has ended, but the keydown still carries the code 229.
    const justComposed = fireEvent.keyDown(questionBox(), { key: 'Enter', keyCode: 229 })

    expect(composing).toBe(true)
    expect(justComposed).toBe(true)
    expect(askRequests(fetchStub)).toHaveLength(0)
    expect(questionBox()).toHaveValue('にほん')
    expect(cards()).toHaveLength(0)
  })

  it('shows the alert for an empty question on Enter, as the button does', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes])

    await renderPage()
    await user.type(questionBox(), '{Enter}')

    expect(screen.getByRole('alert')).toHaveTextContent('Type a question first.')
    expect(askRequests(fetchStub)).toHaveLength(0)
  })
})

describe('asking', () => {
  it('posts the dataset and the trimmed question as JSON', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes, report])

    await renderPage()
    await ask(user, '  \n first line\nsecond line \t ')
    await screen.findByText('The answer.')

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

  it('shows the answer in the card of its question, with its citations, and lets the user ask again', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await ask(user, '  Why?  ')

    const answer = within(await findCard(1, 'Why?'))
    expect(await answer.findByText('The answer.')).toBeInTheDocument()
    expect(answer.getByText('Answered')).toBeInTheDocument()
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

    const answer = within(await findCard(1, 'Why?'))
    expect(await answer.findByText(notFound.answer)).toBeInTheDocument()
    expect(answer.getByText('Not found')).toBeInTheDocument()
    expect(answer.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
    expect(answer.queryByRole('list')).not.toBeInTheDocument()
    expect(answer.queryByRole('blockquote')).not.toBeInTheDocument()
  })

  it('shows a clarifying question with the lines it asks about, and not as a missing answer', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => Response.json(clarifying) })

    await renderPage()
    await ask(user, 'What do I do?')

    const answer = within(await findCard(1, 'What do I do?'))
    expect(await answer.findByText(clarifying.answer)).toBeInTheDocument()
    expect(answer.getByText('Needs your reply')).toBeInTheDocument()
    expect(answer.getByText(clarifying.answer).querySelector('svg')).toBeNull()
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
    const citation = {
      document_id: '1',
      filename,
      start_line: 1,
      end_line: 1,
      start_page: null,
      end_page: null,
      quote: `${html} quote`,
    }
    stubPage([{ ...notes, filename }], {
      [GET_DATASETS]: () => Response.json([{ ...reports, name: html }]),
      'POST /api/ask': () =>
        Response.json({ status: 'answered', answer: `${html} answer`, citations: [citation] }),
    })

    const { container } = render(<App />)
    await screen.findByRole('button', { name: 'Ask' })
    expect(screen.getByRole('heading', { name: `Ask your first question about ${html}` })).toBeInTheDocument()
    await ask(user, `${html} question`)

    const answer = within(await findCard(1, `${html} question`))
    expect(await answer.findByText(`${html} answer`)).toBeInTheDocument()
    expect(questionBox()).toHaveAttribute('placeholder', `Ask a question about ${html}`)
    expect(answer.getByText(`${html} question`)).toBeInTheDocument()
    expect(answer.getByText(filename)).toBeInTheDocument()
    expect(answer.getByRole('blockquote').textContent).toBe(`${html} quote`)
    expect(container.querySelector('img')).toBeNull()
  })

  it('keeps the question in its card while the next one is typed', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByText('The answer.')
    await user.type(questionBox(), 'And how?')

    expect(card(1, 'Why?')).toBeInTheDocument()
    expect(questionBox()).toHaveValue('And how?')
  })

  it('stops the browser from submitting the form itself', async () => {
    stubPage([notes])

    await renderPage()

    // fireEvent returns false when the handler called preventDefault.
    expect(fireEvent.submit(questionBox().form!)).toBe(false)
  })
})

describe('the cards of the session', () => {
  it('keeps every question as a card, numbered in the order asked, the newest last', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': answersInTurn(answered, notFound, clarifying) })

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByText('The answer.')
    await ask(user, 'How?')
    await screen.findByText(notFound.answer)
    await ask(user, 'When?')
    await screen.findByText(clarifying.answer)

    expect(cardHeadings()).toEqual(['Q1 Why?', 'Q2 How?', 'Q3 When?'])
    expect(within(card(1, 'Why?')).getByText('Answered')).toBeInTheDocument()
    expect(within(card(2, 'How?')).getByText('Not found')).toBeInTheDocument()
    expect(within(card(3, 'When?')).getByText('Needs your reply')).toBeInTheDocument()
    expect(within(card(1, 'Why?')).getByText('The answer.')).toBeInTheDocument()
  })

  it('shows the time each question was asked', async () => {
    const user = userEvent.setup()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 10, 14, 8))
    stubPage([notes])

    try {
      await renderPage()
      await ask(user)

      expect(within(await findCard(1, 'Why?')).getByText('14:08')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('scrolls to the newest card when it is added and again when its answer comes', async () => {
    const user = userEvent.setup()
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    const { route, answer } = waitingRoute()
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await ask(user)
    const newest = card(1, 'Why?')

    expect(scroll).toHaveBeenCalledTimes(1)
    expect(scroll.mock.contexts[0]).toBe(newest)
    expect(scroll).toHaveBeenCalledWith({ block: 'start' })

    answer(Response.json(answered))
    await screen.findByText('The answer.')

    expect(scroll).toHaveBeenCalledTimes(2)
    expect(scroll.mock.contexts[1]).toBe(newest)
  })

  it('does not scroll when an older card changes', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': answersInTurn(answered, answered) })

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByText('The answer.')
    await ask(user, 'How?')
    await within(await findCard(2, 'How?')).findByText('The answer.')
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')

    await user.click(screen.getByRole('button', { name: 'Collapse Q1' }))

    expect(scroll).not.toHaveBeenCalled()
  })
})

describe('an answer that cites two files', () => {
  const fromTwoFiles = {
    status: 'answered',
    answer: 'The answer.',
    citations: [
      {
        document_id: '1',
        filename: 'notes.txt',
        start_line: 3,
        end_line: 3,
        start_page: null,
        end_page: null,
        quote: 'notes line 3',
      },
      {
        document_id: '2',
        filename: 'report.md',
        start_line: 2,
        end_line: 2,
        start_page: null,
        end_page: null,
        quote: 'report line 2',
      },
    ],
  }
  // Each document's lines say which document they're from, so a viewer showing the wrong one can't pass.
  function documentRoute(doc: typeof notes, prefix: string): Route {
    const lines = Array.from({ length: 9 }, (_, index) => `${prefix} line ${index + 1}`)
    return () => Response.json({ ...doc, lines, page_starts: null })
  }

  function stubTwoFiles() {
    return stubPage([notes, report], {
      'POST /api/ask': () => Response.json(fromTwoFiles),
      'GET /api/documents/1': documentRoute(notes, 'notes'),
      'GET /api/documents/2': documentRoute(report, 'report'),
    })
  }

  it('shows each citation with the file it comes from', async () => {
    const user = userEvent.setup()
    stubTwoFiles()

    await renderPage()
    await ask(user)
    await screen.findByText('The answer.')

    const [first, second] = within(card(1, 'Why?')).getAllByRole('listitem')
    expect(within(first).getByText('notes.txt')).toBeInTheDocument()
    expect(within(first).getByRole('button', { name: 'Line 3' })).toHaveAccessibleDescription('notes.txt')
    expect(within(first).getByRole('blockquote')).toHaveTextContent('notes line 3')
    expect(within(second).getByText('report.md')).toBeInTheDocument()
    expect(within(second).getByRole('button', { name: 'Line 2' })).toHaveAccessibleDescription('report.md')
    expect(within(second).getByRole('blockquote')).toHaveTextContent('report line 2')
  })

  it("opens each citation's lines in its own document, in the panel", async () => {
    const user = userEvent.setup()
    const fetchStub = stubTwoFiles()

    await renderPage()
    await ask(user)
    const notesButton = await screen.findByRole('button', { name: 'Line 3' })
    const reportButton = screen.getByRole('button', { name: 'Line 2' })

    await user.click(notesButton)
    const notesViewer = await within(panel()!).findByRole('list', { name: 'Lines of notes.txt' })
    expect(within(notesViewer).getByText('notes line 3').closest('li')).toHaveAttribute('aria-current', 'true')

    await user.click(reportButton)
    const reportViewer = await within(panel()!).findByRole('list', { name: 'Lines of report.md' })
    expect(within(reportViewer).getByText('report line 2').closest('li')).toHaveAttribute('aria-current', 'true')
    expect(screen.queryByRole('list', { name: 'Lines of notes.txt' })).not.toBeInTheDocument()

    const documentRequests = fetchStub.mock.calls.filter(([url]) => String(url).startsWith('/api/documents/'))
    expect(documentRequests.map(([url]) => url)).toEqual(['/api/documents/1', '/api/documents/2'])
  })
})

describe('an open citation', () => {
  const lines = Array.from({ length: 9 }, (_, index) => `line ${index + 1}`)
  const documentRoute: Route = () => Response.json({ ...notes, lines, page_starts: null })

  const openViewers = () => screen.queryAllByRole('list', { name: /^Lines of/ })
  const documentRequests = (fetchStub: ReturnType<typeof stubRoutes>) =>
    fetchStub.mock.calls.filter(([url]) => url === '/api/documents/1')

  async function openFirstCitation(user: UserEvent) {
    await user.click(await screen.findByRole('button', { name: 'Line 3' }))
    await screen.findByRole('list', { name: 'Lines of notes.txt' })
  }

  it('stays open when another question is answered, whose chips start unpressed', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes], { 'GET /api/documents/1': documentRoute })

    await renderPage()
    await ask(user, 'Why?')
    await openFirstCitation(user)

    await ask(user, 'How?')
    const second = within(await findCard(2, 'How?'))
    await second.findByText('The answer.')

    expect(second.getByRole('button', { name: 'Line 3' })).toHaveAttribute('aria-pressed', 'false')
    expect(second.getByRole('button', { name: 'Lines 4–6' })).toHaveAttribute('aria-pressed', 'false')
    expect(within(card(1, 'Why?')).getByRole('button', { name: 'Line 3' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(panel()!).getByText('Quote found on line 3 · cited in Q1')).toBeInTheDocument()
    expect(openViewers()).toHaveLength(1)
    expect(documentRequests(fetchStub)).toHaveLength(1)
  })

  it('keeps loading, with no error, while a new question is on its way', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json(answered))
    const fetchStub = stubPage([notes], { 'POST /api/ask': route, 'GET /api/documents/1': rejectsOnAbort })

    await renderPage()
    await ask(user, 'Why?')
    await user.click(await screen.findByRole('button', { name: 'Line 3' }))
    await ask(user, 'How?')

    expect(documentRequests(fetchStub)[0][1]?.signal?.aborted).toBe(false)
    expect(within(panel()!).getByRole('status')).toHaveTextContent('Loading the document…')

    answer(Response.json(answered))
    await within(await findCard(2, 'How?')).findByText('The answer.')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(documentRequests(fetchStub)).toHaveLength(1)
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
    expect(cards()).toHaveLength(0)
  })

  it('clears the alert when a real question is sent', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await user.click(askButton())
    await screen.findByRole('alert')
    await ask(user)
    await screen.findByText('The answer.')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('leaves the cards as they were, since nothing was sent', async () => {
    const user = userEvent.setup()
    stubPage([notes])

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByText('The answer.')
    await user.click(askButton())

    expect(screen.getByRole('alert')).toHaveTextContent('Type a question first.')
    expect(cardHeadings()).toEqual(['Q1 Why?'])
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

  it('shows the question at once in a card that waits for its answer', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubPage([notes, report], { 'POST /api/ask': route })

    await renderPage()
    await ask(user)

    const waiting = card(1, 'Why?')
    expect(waiting).toHaveAttribute('aria-busy', 'true')
    expect(within(waiting).getByText('Asking…')).toBeInTheDocument()
    expect(
      within(waiting).getByText('Searching 2 documents and checking every quote. This usually takes 3–20 seconds.'),
    ).toBeInTheDocument()

    answer(Response.json(answered))

    expect(await within(waiting).findByText('The answer.')).toBeInTheDocument()
    expect(waiting).not.toHaveAttribute('aria-busy')
  })

  it('adds the new question under the previous one, and puts its answer in its own card', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json(answered))
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByText('The answer.')
    await ask(user, 'How?')

    expect(cardHeadings()).toEqual(['Q1 Why?', 'Q2 How?'])
    expect(within(card(1, 'Why?')).getByText('The answer.')).toBeInTheDocument()
    expect(within(card(2, 'How?')).getByText('Asking…')).toBeInTheDocument()

    answer(Response.json(notFound))

    expect(await within(card(2, 'How?')).findByText(notFound.answer)).toBeInTheDocument()
    expect(within(card(1, 'Why?')).getByText('The answer.')).toBeInTheDocument()
    expect(within(card(1, 'Why?')).queryByText(notFound.answer)).not.toBeInTheDocument()
  })

  it('sends nothing more on Enter, and keeps what is typed', async () => {
    const user = userEvent.setup()
    const { route } = waitingRoute()
    const fetchStub = stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await ask(user, 'Why?')
    await user.type(questionBox(), 'How?{Enter}')

    expect(askRequests(fetchStub)).toHaveLength(1)
    expect(questionBox()).toHaveValue('How?')
    expect(cardHeadings()).toEqual(['Q1 Why?'])
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

    await screen.findByText('The answer.')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('when asking fails', () => {
  it.each([
    [502, 'Gemini could not answer this question.'],
    [503, 'Gemini is unavailable right now. Please try again.'],
    [404, 'Dataset not found.'],
  ])('shows the message from the backend on a %i, leaves no card and puts the question back', async (status, detail) => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => Response.json({ detail }, { status }) })

    await renderPage()
    await ask(user, 'Why?')

    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
    expect(questionBox()).toHaveValue('Why?')
    expect(cards()).toHaveLength(0)
  })

  it.each<[string, Route]>([
    ['a 502 with no JSON', () => new Response('Bad Gateway', { status: 502 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['a validation error whose detail is an array', () => Response.json({ detail: [{ msg: 'x' }] }, { status: 422 })],
  ])('shows the fallback on %s and puts the question back', async (_name, post) => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': post })

    await renderPage()
    await ask(user, 'Why?')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not get an answer.')
    expect(questionBox()).toHaveValue('Why?')
  })

  it('puts the question back as it was typed, spaces and all', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => new Response('Bad Gateway', { status: 502 }) })

    await renderPage()
    await ask(user, '  Why?\n')

    await screen.findByRole('alert')
    expect(questionBox()).toHaveValue('  Why?\n')
  })

  it('does not overwrite a question typed while it was on its way', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await ask(user, 'Why?')
    await user.type(questionBox(), 'How?')
    answer(new Response('Bad Gateway', { status: 502 }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not get an answer.')
    expect(questionBox()).toHaveValue('How?')
  })

  it('takes away only the failed card, and the next question gets its number', async () => {
    const user = userEvent.setup()
    const post = vi
      .fn<Route>()
      .mockResolvedValueOnce(Response.json(answered))
      .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
      .mockResolvedValueOnce(Response.json(notFound))
    stubPage([notes], { 'POST /api/ask': post })

    await renderPage()
    await ask(user, 'Why?')
    await screen.findByText('The answer.')
    await ask(user, 'How?')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not get an answer.')
    expect(cardHeadings()).toEqual(['Q1 Why?'])
    expect(within(card(1, 'Why?')).getByText('The answer.')).toBeInTheDocument()

    await user.click(askButton())

    expect(await findCard(2, 'How?')).toBeInTheDocument()
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

  it('keeps the cards when the last one goes, and says in place of the box why it is gone', async () => {
    const user = userEvent.setup()
    stubPage([], { [GET_LIST]: listThatChanges([notes], []), 'DELETE /api/documents/1': deleted })

    await renderPage()
    await ask(user)
    await screen.findByText('The answer.')
    await deleteFromTheList(user, 'notes.txt')

    expect(await screen.findByText(prompt)).toBeInTheDocument()
    expect(cardHeadings()).toEqual(['Q1 Why?'])
    expect(screen.queryByRole('textbox', { name: 'Question' })).not.toBeInTheDocument()
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
    expect(card(1, 'Why?')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Line 3' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Document not found.')
    expect(screen.getByText('The answer.')).toBeInTheDocument()
  })
})

describe('a clarifying question', () => {
  it('has a reply box below its sources, inside its card, limited like the question', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': () => Response.json(clarifying) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)

    const asked = card(1, 'What do I do?')
    expect(asked).toContainElement(replyBox())
    expect(within(asked).getByRole('list').nextElementSibling).toBe(replyBox().form)
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
    await user.type(questionBox(), 'And when?')
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

  it('is followed by the answer in the same card, with the exchange above it and no reply box', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': answersInTurn(clarifying, answered) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)
    await screen.findByText('The answer.')

    const asked = card(1, 'What do I do?')
    const answer = within(asked)
    expect(exchangeIn(asked)).toEqual([`I asked: ${clarifying.answer}`, 'You replied: A laptop.'])
    expect(answer.getByText('Clarified, then answered')).toBeInTheDocument()
    expect(answer.getByRole('heading', { name: 'Sources' })).toBeInTheDocument()
    expect(answer.queryByRole('heading', { name: "Why I'm asking" })).not.toBeInTheDocument()
    expect(answer.getAllByRole('blockquote').map((quote) => quote.textContent)).toEqual([
      'the third line',
      'three more lines',
    ])
    expect(cards()).toHaveLength(1)
    expect(screen.queryByRole('textbox', { name: 'Your reply' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Repl/ })).not.toBeInTheDocument()
    expect(askButton()).toBeEnabled()
  })

  it('keeps the lines it asked about behind Why I asked', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': answersInTurn(clarifying, answered) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)
    await screen.findByText('The answer.')
    const why = screen.getByRole('button', { name: 'Why I asked (2)' })
    expect(why).toHaveAttribute('aria-expanded', 'false')

    await user.click(why)

    expect(why).toHaveAttribute('aria-expanded', 'true')
    expect(within(card(1, 'What do I do?')).getAllByRole('blockquote').map((quote) => quote.textContent)).toEqual([
      'the third line',
      'three more lines',
      'a lost laptop',
      'a lost phone',
    ])
  })

  it('gets no second reply box, even when the answer to the reply asks again', async () => {
    const user = userEvent.setup()
    const again = { ...clarifying, answer: 'Which laptop?' }
    const fetchStub = stubPage([notes], { 'POST /api/ask': answersInTurn(clarifying, again) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)

    expect(await screen.findByText('Which laptop?')).toBeInTheDocument()
    expect(exchangeIn(card(1, 'What do I do?'))).toContain('You replied: A laptop.')
    expect(screen.queryByRole('textbox', { name: 'Your reply' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Repl/ })).not.toBeInTheDocument()
    expect(askRequests(fetchStub)).toHaveLength(2)
  })

  it('keeps its open source in the panel after the reply, behind Why I asked, and the new chips start unpressed', async () => {
    const user = userEvent.setup()
    const lines = Array.from({ length: 9 }, (_, index) => `line ${index + 1}`)
    const fetchStub = stubPage([notes], {
      'POST /api/ask': answersInTurn(clarifying, answered),
      'GET /api/documents/1': () => Response.json({ ...notes, lines, page_starts: null }),
    })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await user.click(screen.getByRole('button', { name: 'Line 2' }))
    await screen.findByRole('list', { name: 'Lines of notes.txt' })
    expect(within(panel()!).getByText('Quote found on line 2 · cited in Q1 · why I asked')).toBeInTheDocument()
    await reply(user)
    await screen.findByText('The answer.')

    expect(screen.getByRole('button', { name: 'Line 3' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Lines 4–6' })).toHaveAttribute('aria-pressed', 'false')
    expect(within(panel()!).getByText('Quote found on line 2 · cited in Q1 · why I asked')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Why I asked (2)' }))

    expect(screen.getByRole('button', { name: 'Line 2' })).toHaveAttribute('aria-pressed', 'true')
    expect(fetchStub.mock.calls.filter(([url]) => url === '/api/documents/1')).toHaveLength(1)
  })

  it('keeps its reply box while other questions are asked, and puts the answer to the reply in its card', async () => {
    const user = userEvent.setup()
    stubPage([notes], { 'POST /api/ask': answersInTurn(clarifying, notFound, answered) })

    await renderPage()
    await askAndGetClarifyingQuestion(user, 'What do I do?')
    await ask(user, 'How?')
    await screen.findByText(notFound.answer)

    expect(card(1, 'What do I do?')).toContainElement(replyBox())

    await reply(user)
    await screen.findByText('The answer.')

    expect(within(card(1, 'What do I do?')).getByText('The answer.')).toBeInTheDocument()
    expect(within(card(2, 'How?')).queryByText('The answer.')).not.toBeInTheDocument()
    expect(cardHeadings()).toEqual(['Q1 What do I do?', 'Q2 How?'])
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
    expect(within(card(1, 'What do I do?')).getByText('Asking…')).toBeInTheDocument()
    expect(screen.getByText(clarifying.answer)).toBeInTheDocument()
    await user.type(questionBox(), 'And when?')
    expect(questionBox()).toHaveValue('And when?')

    answer(Response.json(answered))

    expect(await screen.findByText('You replied')).toBeInTheDocument()
    expect(askButton()).toBeEnabled()
  })

  it('disables the Reply of every other card too', async () => {
    const user = userEvent.setup()
    const { route } = waitingRoute(Response.json(clarifying), Response.json(clarifying))
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await askAndGetClarifyingQuestion(user, 'What do I do?')
    await ask(user, 'How?')
    await within(await findCard(2, 'How?')).findByRole('textbox', { name: 'Your reply' })
    const [first, second] = screen.getAllByRole<HTMLTextAreaElement>('textbox', { name: 'Your reply' })
    await user.type(first, 'A laptop.')
    await user.click(within(first.form!).getByRole('button', { name: 'Reply' }))

    expect(within(first.form!).getByRole('button', { name: 'Replying…' })).toBeDisabled()
    expect(within(second.form!).getByRole('button', { name: 'Reply' })).toBeDisabled()
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
    expect(within(card(1, 'What do I do?')).getByText('Needs your reply')).toBeInTheDocument()
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
    expect(screen.queryByText('You replied')).not.toBeInTheDocument()
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

    expect(await screen.findByText('You replied')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    const [, failed, retried] = askBodies(fetchStub)
    expect(retried).toEqual(failed)
    expect(retried.clarification).toEqual({ question: clarifying.answer, reply: 'A laptop.' })
  })
})

describe('a new question after a clarifying question', () => {
  it('gets a card of its own, and is sent with no clarification', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([notes], { 'POST /api/ask': answersInTurn(clarifying, answered) })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await reply(user)
    await screen.findByText('You replied')
    await ask(user, 'How?')
    const next = await findCard(2, 'How?')
    await within(next).findByText('The answer.')

    expect(exchangeIn(next)).toEqual([])
    expect(exchangeIn(card(1, 'What do I do?'))).toEqual([`I asked: ${clarifying.answer}`, 'You replied: A laptop.'])
    const bodies = askBodies(fetchStub)
    expect(bodies).toHaveLength(3)
    expect(bodies[2]).toEqual({ dataset_id: reports.id, question: 'How?' })
    expect(bodies[2]).not.toHaveProperty('clarification')
  })

  it('leaves the clarifying question and its typed reply in their card', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute(Response.json(clarifying))
    stubPage([notes], { 'POST /api/ask': route })

    await renderPage()
    await askAndGetClarifyingQuestion(user)
    await user.type(replyBox(), 'A laptop.')
    await ask(user, 'How?')

    expect(card(1, 'What do I do?')).toContainElement(replyBox())
    expect(replyBox()).toHaveValue('A laptop.')
    expect(replyButton()).toBeDisabled()

    answer(Response.json(clarifying))
    const next = await findCard(2, 'How?')
    await within(next).findByRole('textbox', { name: 'Your reply' })

    expect(within(card(1, 'What do I do?')).getByRole('textbox', { name: 'Your reply' })).toHaveValue('A laptop.')
    expect(within(next).getByRole('textbox', { name: 'Your reply' })).toHaveValue('')
  })
})
