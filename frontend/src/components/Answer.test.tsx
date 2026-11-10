import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Answer as AnswerResult, Citation } from '../api/ask.ts'
import Answer from './Answer.tsx'

const oneLine: Citation = {
  document_id: '1',
  filename: 'notes.txt',
  start_line: 3,
  end_line: 3,
  start_page: null,
  end_page: null,
  quote: 'the third line',
}
const threeLines: Citation = {
  document_id: '1',
  filename: 'notes.txt',
  start_line: 3,
  end_line: 5,
  start_page: null,
  end_page: null,
  quote: 'three whole lines',
}

function answered(...citations: Citation[]): AnswerResult {
  return { status: 'answered', answer: 'The answer.', citations }
}

const notFound: AnswerResult = {
  status: 'not_found',
  answer: "Sorry, I can't find anything related to your question in the documents you provided.",
  citations: [],
}

const other: Citation = { ...oneLine, document_id: '2', filename: 'other.md', start_line: 2, end_line: 2 }

// A PDF of four pages of two lines each, whose line N of page P says "page P line N".
const report = {
  id: '3',
  filename: 'report.pdf',
  line_count: 8,
  page_count: 4,
  lines: [1, 2, 3, 4].flatMap((page) => [`page ${page} line 1`, `page ${page} line 2`]),
  page_starts: [1, 3, 5, 7],
}
const onePage: Citation = {
  document_id: '3',
  filename: 'report.pdf',
  start_line: 5,
  end_line: 6,
  start_page: 3,
  end_page: 3,
  quote: 'all of page 3',
}
const twoPages: Citation = { ...onePage, start_line: 6, end_line: 7, end_page: 4, quote: 'pages 3 and 4' }

const clarifying: AnswerResult = {
  status: 'needs_clarification',
  answer: 'Did you lose a company laptop or a phone?',
  citations: [oneLine, { ...threeLines, document_id: '2', filename: 'other.md' }],
}

const lines = Array.from({ length: 30 }, (_, index) => `line ${index + 1}`)

// A text file holding those lines, as the backend sends it.
function textFile(id: string, filename: string) {
  return { id, filename, line_count: lines.length, page_count: null, lines, page_starts: null }
}

function stubFetch(respond: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fetchStub = vi.fn<typeof fetch>(async (url, init) => respond(String(url), init))
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

function stubDocuments() {
  return stubFetch(() => Response.json(textFile('1', 'notes.txt')))
}

// Like the real fetch: never answers by itself, and rejects once aborted.
function rejectsOnAbort(_url: string, init?: RequestInit) {
  return new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })
}

function renderCitations(...citations: Citation[]) {
  render(<Answer result={answered(...citations)} />)
}

const lineButton = (name = 'Line 3') => screen.getByRole('button', { name })
const lineButtons = () => screen.getAllByRole('button', { name: 'Line 3' })
const citationOf = (button: HTMLElement) => button.closest('li') as HTMLElement
const VIEWER = { name: /^Lines of/ }
const findViewer = () => screen.findByRole('list', VIEWER)
const findViewerIn = (item: HTMLElement) => within(item).findByRole('list', VIEWER)
const viewerIn = (item: HTMLElement) => within(item).queryByRole('list', VIEWER)
const openViewers = () => screen.queryAllByRole('list', VIEWER)

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('an answer', () => {
  // First in the file: React warns about a missing key only once per component.
  it('shows two identical citations without a key warning', () => {
    const consoleError = vi.spyOn(console, 'error')

    render(<Answer result={answered(oneLine, oneLine)} />)

    expect(screen.getAllByRole('blockquote')).toHaveLength(2)
    expect(consoleError).not.toHaveBeenCalled()
  })

  it('shows the answer text', () => {
    render(<Answer result={answered(oneLine)} />)

    expect(screen.getByText('The answer.')).toBeInTheDocument()
  })

  it('leaves out the Sources heading when it cites nothing', () => {
    render(<Answer result={answered()} />)

    expect(screen.getByText('The answer.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows the filename, the lines and the quote of each citation, in order', () => {
    const other = { ...threeLines, filename: 'other.md' }

    render(<Answer result={answered(oneLine, other)} />)

    expect(screen.getByRole('heading', { name: 'Sources' })).toBeInTheDocument()
    const [first, second] = screen.getAllByRole('listitem')
    expect(within(first).getByText('notes.txt')).toBeInTheDocument()
    expect(within(first).getByText('Line 3')).toBeInTheDocument()
    expect(within(first).getByRole('blockquote')).toHaveTextContent('the third line')
    expect(within(second).getByText('other.md')).toBeInTheDocument()
    expect(within(second).getByText('Lines 3–5')).toBeInTheDocument()
    expect(within(second).getByRole('blockquote')).toHaveTextContent('three whole lines')
  })

  it('describes each lines button by its file, since buttons for two files can say the same lines', () => {
    renderCitations(oneLine, { ...other, start_line: 3, end_line: 3 })

    const [first, second] = lineButtons()
    expect(first).toHaveAccessibleName('Line 3')
    expect(first).toHaveAccessibleDescription('notes.txt')
    expect(second).toHaveAccessibleName('Line 3')
    expect(second).toHaveAccessibleDescription('other.md')
  })

  it('labels a citation in a PDF by its pages, and one in a text file by its lines', () => {
    renderCitations(onePage, twoPages, oneLine, threeLines)

    const labels = screen.getAllByRole('button').map((button) => button.textContent)
    expect(labels).toEqual(['Page 3', 'Pages 3–4', 'Line 3', 'Lines 3–5'])
  })

  it('describes a pages button by its file, as it does a lines button', () => {
    renderCitations(onePage, twoPages)

    expect(lineButton('Page 3')).toHaveAccessibleDescription('report.pdf')
    expect(lineButton('Pages 3–4')).toHaveAccessibleDescription('report.pdf')
  })

  it('shows HTML as plain text', () => {
    const html = '<img src=x onerror=alert(1)>'
    const citation = { ...oneLine, filename: `${html}.txt`, quote: `${html} quote` }
    const result = { ...answered(citation), answer: `${html} answer` }

    const { container } = render(<Answer result={result} />)

    expect(screen.getByText(`${html} answer`)).toBeInTheDocument()
    expect(screen.getByText(`${html}.txt`)).toBeInTheDocument()
    expect(screen.getByRole('blockquote').textContent).toBe(`${html} quote`)
    expect(container.querySelector('img')).toBeNull()
  })

  it('keeps line breaks in the answer and the quotes', () => {
    const result = { ...answered({ ...oneLine, quote: 'one\ntwo' }), answer: 'first\nsecond' }

    render(<Answer result={result} />)

    const quote = screen.getByRole('blockquote')
    const answerText = screen.getByText(/first/)
    expect(quote.textContent).toBe('one\ntwo')
    expect(answerText.textContent).toBe('first\nsecond')
    for (const element of [quote, answerText]) {
      expect(element).toHaveStyle({ whiteSpace: 'pre-wrap' })
    }
  })

  it('marks a citation in a PDF with the PDF icon, and one in a text file with the file icon', () => {
    renderCitations(onePage, oneLine)

    const [pdfIcon, fileIcon] = screen.getAllByRole('listitem').map((item) => item.querySelector('svg'))
    expect(pdfIcon).toHaveClass('pdf')
    expect(fileIcon).not.toHaveClass('pdf')
    expect(pdfIcon).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('opening a citation', () => {
  it('starts with every citation closed and asks for nothing', () => {
    const fetchStub = stubDocuments()

    renderCitations(oneLine, threeLines)

    expect(lineButton()).toHaveAttribute('aria-expanded', 'false')
    expect(lineButton('Lines 3–5')).toHaveAttribute('aria-expanded', 'false')
    expect(openViewers()).toHaveLength(0)
    expect(fetchStub).not.toHaveBeenCalled()
  })

  it('opens the viewer under the quote, inside that citation', async () => {
    const user = userEvent.setup()
    const fetchStub = stubDocuments()
    renderCitations(oneLine, other)

    await user.click(lineButton())

    expect(lineButton()).toHaveAttribute('aria-expanded', 'true')
    const item = citationOf(lineButton())
    const viewer = await within(item).findByRole('list', { name: 'Lines of notes.txt' })
    expect(within(viewer).getByText('line 3').closest('li')).toHaveAttribute('aria-current', 'true')
    expect(within(item).getByRole('blockquote').nextElementSibling).toContainElement(viewer)
    expect(fetchStub).toHaveBeenCalledTimes(1)
    expect(fetchStub.mock.calls[0][0]).toBe('/api/documents/1')
  })

  it('opens a citation in a PDF at its lines, under the rows of their pages', async () => {
    const user = userEvent.setup()
    const fetchStub = stubFetch(() => Response.json(report))
    renderCitations(twoPages)

    await user.click(lineButton('Pages 3–4'))

    const item = citationOf(lineButton('Pages 3–4'))
    const viewer = await within(item).findByRole('list', { name: 'Lines of report.pdf' })
    const headings = within(viewer).getAllByRole('heading').map((heading) => heading.textContent)
    expect(headings).toEqual(['Page 1', 'Page 2', 'Page 3', 'Page 4'])
    const cited = within(viewer)
      .getAllByRole('listitem')
      .filter((row) => row.getAttribute('aria-current') === 'true')
      .map((row) => Array.from(row.children, (child) => child.textContent))
    expect(cited).toEqual([
      ['2', 'page 3 line 2'],
      ['1', 'page 4 line 1'],
    ])
    expect(fetchStub.mock.calls[0][0]).toBe('/api/documents/3')
  })

  it('closes the viewer when clicked again', async () => {
    const user = userEvent.setup()
    stubDocuments()
    renderCitations(oneLine)

    await user.click(lineButton())
    await findViewer()
    await user.click(lineButton())

    expect(lineButton()).toHaveAttribute('aria-expanded', 'false')
    expect(openViewers()).toHaveLength(0)
  })

  it('closes the first citation when another one opens', async () => {
    const user = userEvent.setup()
    const fetchStub = stubDocuments()
    renderCitations(oneLine, other)

    await user.click(lineButton())
    await findViewer()
    await user.click(lineButton('Line 2'))
    await findViewerIn(citationOf(lineButton('Line 2')))

    expect(lineButton()).toHaveAttribute('aria-expanded', 'false')
    expect(lineButton('Line 2')).toHaveAttribute('aria-expanded', 'true')
    expect(viewerIn(citationOf(lineButton()))).not.toBeInTheDocument()
    expect(openViewers()).toHaveLength(1)
    expect(fetchStub.mock.calls.map(([url]) => url)).toEqual(['/api/documents/1', '/api/documents/2'])
  })

  it('opens two identical citations separately', async () => {
    const user = userEvent.setup()
    stubDocuments()
    renderCitations(oneLine, oneLine)
    const [first, second] = lineButtons()

    await user.click(first)
    await findViewerIn(citationOf(first))

    expect(first).toHaveAttribute('aria-expanded', 'true')
    expect(second).toHaveAttribute('aria-expanded', 'false')
    expect(viewerIn(citationOf(second))).not.toBeInTheDocument()

    await user.click(second)
    await findViewerIn(citationOf(second))

    expect(first).toHaveAttribute('aria-expanded', 'false')
    expect(second).toHaveAttribute('aria-expanded', 'true')
    expect(viewerIn(citationOf(first))).not.toBeInTheDocument()
  })

  it('starts fresh when reopened: the first window, a new request and a new scroll', async () => {
    const user = userEvent.setup()
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    const fetchStub = stubDocuments()
    renderCitations({ ...oneLine, start_line: 15, end_line: 15 })
    const rowsShown = () => within(openViewers()[0]).getAllByRole('listitem')

    await user.click(lineButton('Line 15'))
    await findViewer()
    await user.click(screen.getByRole('button', { name: 'Show earlier lines' }))
    expect(rowsShown()).toHaveLength(25)

    await user.click(lineButton('Line 15'))
    await user.click(lineButton('Line 15'))
    await findViewer()

    expect(rowsShown()).toHaveLength(21)
    expect(fetchStub).toHaveBeenCalledTimes(2)
    expect(scroll).toHaveBeenCalledTimes(2)
  })

  it('works by keyboard and keeps the focus on the button', async () => {
    const user = userEvent.setup()
    stubDocuments()
    renderCitations(oneLine)

    await user.tab()
    expect(lineButton()).toHaveFocus()

    await user.keyboard('{Enter}')
    expect(lineButton()).toHaveAttribute('aria-expanded', 'true')
    await findViewer()
    expect(lineButton()).toHaveFocus()

    await user.keyboard(' ')
    expect(lineButton()).toHaveAttribute('aria-expanded', 'false')
    expect(openViewers()).toHaveLength(0)
    expect(lineButton()).toHaveFocus()
  })

  it('has no citation buttons when the dataset does not hold the answer', () => {
    render(<Answer result={notFound} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('the citation button', () => {
  it('looks like a chip, and does not shrink or wrap next to a long filename', () => {
    renderCitations(oneLine)

    expect(lineButton()).toHaveStyle({ borderTopStyle: 'solid', flexShrink: '0', whiteSpace: 'nowrap' })
    expect(lineButton()).toHaveAttribute('type', 'button')
  })

  it('shows clearly when it has the keyboard focus', async () => {
    const user = userEvent.setup()
    renderCitations(oneLine)
    expect(window.getComputedStyle(lineButton()).outline).not.toContain('solid')

    await user.tab()

    expect(window.getComputedStyle(lineButton()).outline).toContain('solid')
  })

  it('keeps the rules for a citation off the lines inside it', async () => {
    const user = userEvent.setup()
    stubDocuments()
    renderCitations(oneLine)

    expect(citationOf(lineButton())).toHaveStyle({ borderTopStyle: 'solid' })

    await user.click(lineButton())
    const viewer = await findViewer()

    const row = within(viewer).getAllByRole('listitem')[0]
    expect(row).not.toHaveStyle({ borderTopStyle: 'solid' })
    expect(row).not.toHaveStyle({ paddingTop: '9px' })
  })
})

describe('when a citation cannot be opened', () => {
  it.each<[string, () => Response | Promise<Response>, string]>([
    [
      'a 404 with a detail',
      () => Response.json({ detail: 'Document not found.' }, { status: 404 }),
      'Document not found.',
    ],
    ['a 502 that is not JSON', () => new Response('Bad Gateway', { status: 502 }), 'Could not load the document.'],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch')), 'Could not load the document.'],
  ])('shows the message under it after %s and the rest of the answer stays usable', async (_name, failure, message) => {
    const user = userEvent.setup()
    stubFetch((url) => (url === '/api/documents/1' ? failure() : Response.json(textFile('2', 'other.md'))))
    renderCitations(oneLine, other)

    await user.click(lineButton())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(message)
    expect(citationOf(lineButton())).toContainElement(alert)
    expect(screen.getByText('The answer.')).toBeInTheDocument()
    expect(screen.getAllByRole('blockquote')).toHaveLength(2)
    expect(lineButton()).toHaveAttribute('aria-expanded', 'true')

    await user.click(lineButton('Line 2'))

    expect(await findViewerIn(citationOf(lineButton('Line 2')))).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    await user.click(lineButton())
    expect(await screen.findByRole('alert')).toHaveTextContent(message)

    await user.click(lineButton())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('cancelling the request of an open citation', () => {
  it('aborts when the citation is closed, and shows no error', async () => {
    const user = userEvent.setup()
    const fetchStub = stubFetch(rejectsOnAbort)
    renderCitations(oneLine)

    await user.click(lineButton())
    const signal = fetchStub.mock.calls[0][1]?.signal
    expect(signal?.aborted).toBe(false)
    await user.click(lineButton())

    expect(signal?.aborted).toBe(true)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('aborts when another citation opens', async () => {
    const user = userEvent.setup()
    const fetchStub = stubFetch(rejectsOnAbort)
    renderCitations(oneLine, other)

    await user.click(lineButton())
    await user.click(lineButton('Line 2'))

    const [first, second] = fetchStub.mock.calls.map(([, init]) => init?.signal)
    expect(first?.aborted).toBe(true)
    expect(second?.aborted).toBe(false)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getAllByRole('status')).toHaveLength(1)
  })

  it('aborts when the answer goes away', async () => {
    const user = userEvent.setup()
    const fetchStub = stubFetch(rejectsOnAbort)
    const { unmount } = render(<Answer result={answered(oneLine)} />)

    await user.click(lineButton())
    unmount()

    expect(fetchStub.mock.calls[0][1]?.signal?.aborted).toBe(true)
  })
})

describe('when the dataset does not hold the answer', () => {
  it('shows the message, with no sources', () => {
    render(<Answer result={notFound} />)

    expect(screen.getByText(notFound.answer)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows HTML in the message as plain text', () => {
    const html = '<img src=x onerror=alert(1)>'

    const { container } = render(<Answer result={{ ...notFound, answer: html }} />)

    expect(screen.getByText(html)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('looks different from an answer: muted, with a search icon', () => {
    const { unmount } = render(<Answer result={answered(oneLine)} />)
    const answerColour = window.getComputedStyle(screen.getByText('The answer.')).color
    unmount()

    render(<Answer result={notFound} />)

    const message = screen.getByText(notFound.answer)
    expect(window.getComputedStyle(message).color).not.toBe(answerColour)
    expect(message.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(message).toHaveStyle({ whiteSpace: 'pre-wrap' })
  })
})

describe('a clarifying question', () => {
  it("shows the question with the lines that answer differently, under Why I'm asking", () => {
    render(<Answer result={clarifying} />)

    expect(screen.getByText(clarifying.answer)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: "Why I'm asking" })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
    const [first, second] = screen.getAllByRole('listitem')
    expect(within(first).getByText('notes.txt')).toBeInTheDocument()
    expect(within(first).getByRole('button', { name: 'Line 3' })).toHaveAccessibleDescription('notes.txt')
    expect(within(first).getByRole('blockquote')).toHaveTextContent('the third line')
    expect(within(second).getByText('other.md')).toBeInTheDocument()
    expect(within(second).getByRole('button', { name: 'Lines 3–5' })).toHaveAccessibleDescription('other.md')
    expect(within(second).getByRole('blockquote')).toHaveTextContent('three whole lines')
  })

  it('looks like an answer, not like a missing one', () => {
    const { unmount } = render(<Answer result={notFound} />)
    const notFoundColour = window.getComputedStyle(screen.getByText(notFound.answer)).color
    unmount()

    render(<Answer result={clarifying} />)

    const text = screen.getByText(clarifying.answer)
    expect(window.getComputedStyle(text).color).not.toBe(notFoundColour)
    expect(text.querySelector('svg')).toBeNull()
    expect(text).toHaveStyle({ whiteSpace: 'pre-wrap' })
  })

  it('opens the lines of a source in the viewer, as an answer does', async () => {
    const user = userEvent.setup()
    const fetchStub = stubDocuments()
    render(<Answer result={clarifying} />)

    await user.click(lineButton())

    const viewer = await findViewerIn(citationOf(lineButton()))
    expect(within(viewer).getByText('line 3').closest('li')).toHaveAttribute('aria-current', 'true')
    expect(fetchStub.mock.calls.map(([url]) => url)).toEqual(['/api/documents/1'])
  })

  it('shows HTML as plain text', () => {
    const html = '<img src=x onerror=alert(1)>'

    const { container } = render(<Answer result={{ ...clarifying, answer: `${html} question` }} />)

    expect(screen.getByText(`${html} question`)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })
})
