import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'

// These tests render the whole page, so a chip in a card opens the real panel beside it, and only fetch is faked.

type Route = (init?: RequestInit) => Response | Promise<Response>

function stubRoutes(routes: Record<string, Route>) {
  const fetchStub = vi.fn<typeof fetch>(async (url, init) => routes[`${init?.method ?? 'GET'} ${url}`](init))
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

const reports = { id: 'r', name: 'Reports' }
const invoices = { id: 'i', name: 'Invoices' }

const notes = { id: '1', filename: 'notes.txt', line_count: 30, page_count: null }
const other = { id: '2', filename: 'other.md', line_count: 30, page_count: null }

const citing = (doc: typeof notes, start_line: number, end_line = start_line, quote = `${doc.filename} quote`) => ({
  document_id: doc.id,
  filename: doc.filename,
  start_line,
  end_line,
  start_page: null,
  end_page: null,
  quote,
})

const answered = {
  status: 'answered',
  answer: 'The answer.',
  citations: [citing(notes, 3), citing(other, 2), citing(notes, 15)],
}
const clarifying = {
  status: 'needs_clarification',
  answer: 'Did you lose a company laptop or a phone?',
  citations: [citing(notes, 7, 8)],
}

// Each document's line N says which document it's from, so the panel showing the wrong one can't pass.
function textFile(doc: typeof notes) {
  const lines = Array.from({ length: doc.line_count }, (_, index) => `${doc.filename} line ${index + 1}`)
  return { ...doc, lines, page_starts: null }
}

// Reports, the only dataset at first, holds both documents. Invoices is there for switching.
function stubPage(routes: Record<string, Route> = {}) {
  return stubRoutes({
    'GET /api/health': () => Response.json({ status: 'ok' }),
    'GET /api/session': () => Response.json({ login_required: false, logged_in: true }),
    'GET /api/datasets': () => Response.json([reports]),
    'GET /api/datasets/r/documents': () => Response.json([notes, other]),
    'POST /api/ask': () => Response.json(answered),
    'GET /api/documents/1': () => Response.json(textFile(notes)),
    'GET /api/documents/2': () => Response.json(textFile(other)),
    ...routes,
  })
}

// Like the real fetch: never answers by itself, and rejects once aborted.
const rejectsOnAbort: Route = (init) =>
  new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })

// matchMedia for a window this many pixels wide, answering the queries the page asks it. resize() changes the width,
// and tells the listeners of each query whose answer changes, as a browser does.
function stubWindowWidth(initial: number) {
  let width = initial
  const queries: { matches: () => boolean; listeners: Set<() => void> }[] = []
  vi.stubGlobal('matchMedia', (query: string) => {
    const [, bound, pixels] = /^\((min|max)-width: (\d+)px\)$/.exec(query)!
    const matches = () => (bound === 'min' ? width >= Number(pixels) : width <= Number(pixels))
    const listeners = new Set<() => void>()
    queries.push({ matches, listeners })
    return {
      get matches() {
        return matches()
      },
      addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
    }
  })
  return {
    resize: (next: number) =>
      act(() => {
        const before = queries.map((query) => query.matches())
        width = next
        queries.forEach((query, index) => {
          if (query.matches() !== before[index]) query.listeners.forEach((listener) => listener())
        })
      }),
  }
}

const panel = () => screen.queryByRole('complementary', { name: 'Source' })
const inPanel = () => within(panel()!)
const panelHeading = () => inPanel().getByRole('heading', { level: 2 })
const closeButton = () => inPanel().getByRole('button', { name: 'Close source' })
const chip = (name: string) => screen.getByRole('button', { name })
const documentRequests = (fetchStub: ReturnType<typeof stubRoutes>) =>
  fetchStub.mock.calls.filter(([url]) => String(url).startsWith('/api/documents/'))

// Renders the page, asks, and waits for the answer's chips.
async function askAndWait(user: UserEvent, answer: object = answered) {
  render(<App />)
  await user.type(await screen.findByRole('textbox', { name: 'Question' }), 'Why?{Enter}')
  await screen.findByText((answer as typeof answered).answer)
}

async function open(user: UserEvent, name: string) {
  await user.click(chip(name))
  await inPanel().findByRole('list', { name: /^Lines of/ })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('opening a source', () => {
  it('starts with no panel and asks for no document', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage()

    await askAndWait(user)

    expect(panel()).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { pressed: false })).toHaveLength(3)
    expect(documentRequests(fetchStub)).toHaveLength(0)
  })

  it('shows the file, where the quote was found and which question cites it, then its lines', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage()

    await askAndWait(user)
    await open(user, 'Line 3')

    expect(panelHeading()).toHaveTextContent('notes.txt')
    expect(panelHeading()).toHaveAttribute('title', 'notes.txt')
    expect(inPanel().getByText('Line 3')).toBeInTheDocument()
    expect(inPanel().getByText('Quote found on line 3 · cited in Q1')).toBeInTheDocument()
    const lines = inPanel().getByRole('list', { name: 'Lines of notes.txt' })
    expect(within(lines).getByText('notes.txt line 3').closest('li')).toHaveAttribute('aria-current', 'true')
    expect(documentRequests(fetchStub).map(([url]) => url)).toEqual(['/api/documents/1'])
  })

  it('beside the cards, not inside them', async () => {
    const user = userEvent.setup()
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 3')

    expect(screen.getByRole('main')).not.toContainElement(panel())
    expect(screen.getByRole('main').nextElementSibling).toBe(panel())
  })

  it('presses its chip, marks its source card and says the viewer shows it', async () => {
    const user = userEvent.setup()
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 2')

    expect(chip('Line 2')).toHaveAttribute('aria-pressed', 'true')
    expect(chip('Line 3')).toHaveAttribute('aria-pressed', 'false')
    const source = chip('Line 2').closest('li')!
    expect(within(source).getByText('Showing in viewer')).toBeInTheDocument()
    expect(screen.getAllByText('Showing in viewer')).toHaveLength(1)
  })

  it('moves the focus to the heading of the panel', async () => {
    const user = userEvent.setup()
    stubPage()

    await askAndWait(user)
    await user.click(chip('Line 3'))

    expect(panelHeading()).toHaveFocus()
    expect(panelHeading()).toHaveAttribute('tabindex', '-1')
  })

  it('works by keyboard', async () => {
    const user = userEvent.setup()
    stubPage()

    await askAndWait(user)
    chip('Line 3').focus()
    await user.keyboard('{Enter}')

    expect(panel()).toBeInTheDocument()
    expect(panelHeading()).toHaveFocus()
  })

  it('names a source of a clarifying question as the reason it asks', async () => {
    const user = userEvent.setup()
    stubPage({ 'POST /api/ask': () => Response.json(clarifying) })

    await askAndWait(user, clarifying)
    await open(user, 'Lines 7–8')

    expect(inPanel().getByText('Quote found on lines 7–8 · cited in Q1 · why I asked')).toBeInTheDocument()
  })

  it('opens a citation in a PDF at its lines, under the rows of their pages, and says which pages', async () => {
    const user = userEvent.setup()
    // A PDF of four pages of two lines each, whose line N of page P says "page P line N".
    const report = {
      id: '3',
      filename: 'report.pdf',
      line_count: 8,
      page_count: 4,
      lines: [1, 2, 3, 4].flatMap((page) => [`page ${page} line 1`, `page ${page} line 2`]),
      page_starts: [1, 3, 5, 7],
    }
    const twoPages = { ...citing(notes, 6, 7), document_id: '3', filename: 'report.pdf', start_page: 3, end_page: 4 }
    const fetchStub = stubPage({
      'POST /api/ask': () => Response.json({ ...answered, citations: [twoPages] }),
      'GET /api/documents/3': () => Response.json(report),
    })

    await askAndWait(user)
    await open(user, 'Pages 3–4')

    expect(inPanel().getByText('Quote found on pages 3–4 · cited in Q1')).toBeInTheDocument()
    const lines = inPanel().getByRole('list', { name: 'Lines of report.pdf' })
    expect(within(lines).getAllByRole('heading').map((heading) => heading.textContent)).toEqual([
      'Page 1',
      'Page 2',
      'Page 3',
      'Page 4',
    ])
    const cited = within(lines)
      .getAllByRole('listitem')
      .filter((row) => row.getAttribute('aria-current') === 'true')
      .map((row) => Array.from(row.children, (child) => child.textContent))
    expect(cited).toEqual([
      ['2', 'page 3 line 2'],
      ['1', 'page 4 line 1'],
    ])
    expect(panel()!.querySelector('svg')).toHaveClass('pdf')
    expect(documentRequests(fetchStub).map(([url]) => url)).toEqual(['/api/documents/3'])
  })
})

describe('one source at a time', () => {
  it('shows another source in place of the first, pressing only its chip', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage()

    await askAndWait(user)
    await open(user, 'Line 3')
    await user.click(chip('Line 2'))

    const lines = await inPanel().findByRole('list', { name: 'Lines of other.md' })
    expect(within(lines).getByText('other.md line 2').closest('li')).toHaveAttribute('aria-current', 'true')
    expect(screen.queryByRole('list', { name: 'Lines of notes.txt' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('complementary', { name: 'Source' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { pressed: true })).toEqual([chip('Line 2')])
    expect(panelHeading()).toHaveFocus()
    expect(documentRequests(fetchStub).map(([url]) => url)).toEqual(['/api/documents/1', '/api/documents/2'])
  })

  it('starts fresh when reopened: the first window, a new request and a new scroll', async () => {
    const user = userEvent.setup()
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    const fetchStub = stubPage()
    const rowsShown = () => within(inPanel().getByRole('list', { name: /^Lines of/ })).getAllByRole('listitem')
    // Only the scrolls to a line: the questions column scrolls to its newest card too.
    const scrollsToLines = () => scroll.mock.contexts.filter((element) => (element as Element).closest('.line-list'))

    await askAndWait(user)
    await open(user, 'Line 15')
    await user.click(screen.getByRole('button', { name: 'Show earlier lines' }))
    expect(rowsShown()).toHaveLength(25)

    await user.click(chip('Line 15'))
    await open(user, 'Line 15')

    expect(rowsShown()).toHaveLength(21)
    expect(documentRequests(fetchStub)).toHaveLength(2)
    expect(scrollsToLines()).toHaveLength(2)
  })
})

describe('closing the panel', () => {
  it('closes with its chip, which keeps the focus', async () => {
    const user = userEvent.setup()
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 3')
    await user.click(chip('Line 3'))

    expect(panel()).not.toBeInTheDocument()
    expect(chip('Line 3')).toHaveAttribute('aria-pressed', 'false')
    expect(chip('Line 3')).toHaveFocus()
    expect(screen.queryByText('Showing in viewer')).not.toBeInTheDocument()
  })

  it('closes with the close button, and gives the focus back to the chip that opened it', async () => {
    const user = userEvent.setup()
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 2')
    await user.click(closeButton())

    expect(panel()).not.toBeInTheDocument()
    expect(chip('Line 2')).toHaveAttribute('aria-pressed', 'false')
    expect(chip('Line 2')).toHaveFocus()
  })

  it('closes with Escape from anywhere inside it, and gives the focus back', async () => {
    const user = userEvent.setup()
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 15')
    await user.keyboard('{Escape}')

    expect(panel()).not.toBeInTheDocument()
    expect(chip('Line 15')).toHaveFocus()

    await open(user, 'Line 15')
    screen.getByRole('button', { name: 'Show earlier lines' }).focus()
    await user.keyboard('{Escape}')

    expect(panel()).not.toBeInTheDocument()
    expect(chip('Line 15')).toHaveFocus()
  })

  it('ignores Escape outside it', async () => {
    const user = userEvent.setup()
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 3')
    screen.getByRole('textbox', { name: 'Question' }).focus()
    await user.keyboard('{Escape}')

    expect(panel()).toBeInTheDocument()
  })

  it('leaves the focus where it is when the chip that opened it is gone', async () => {
    const user = userEvent.setup()
    stubPage({ 'POST /api/ask': vi.fn<Route>().mockReturnValueOnce(Response.json(clarifying)).mockReturnValue(Response.json(answered)) })

    await askAndWait(user, clarifying)
    await open(user, 'Lines 7–8')
    const opener = chip('Lines 7–8')
    await user.type(screen.getByRole('textbox', { name: 'Your reply' }), 'A laptop.')
    await user.click(screen.getByRole('button', { name: 'Reply' }))
    await screen.findByText('The answer.')
    expect(opener).not.toBeInTheDocument()

    await user.click(closeButton())

    expect(panel()).not.toBeInTheDocument()
    expect(document.body).toHaveFocus()
  })
})

describe('on a window under 1280 px, where the panel lies over the questions', () => {
  const sidebar = () => screen.getByRole('complementary', { name: 'Datasets and documents' })
  const topBar = () => screen.getByRole('button', { name: 'Menu' }).closest('header')!
  // Only for the pointer, like the drawer's, so it has no role or name to find it by.
  const backdrop = () => document.querySelector<HTMLElement>('.sheet-backdrop')

  function expectModal() {
    expect(backdrop()).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveAttribute('inert')
    expect(sidebar()).toHaveAttribute('inert')
    expect(topBar()).toHaveAttribute('inert')
    expect(panel()).not.toHaveAttribute('inert')
  }

  function expectNothingInert() {
    expect(backdrop()).not.toBeInTheDocument()
    expect(document.querySelectorAll('[inert]')).toHaveLength(0)
  }

  it('makes the rest of the page inert behind a backdrop while it is open, Menu included', async () => {
    const user = userEvent.setup()
    stubWindowWidth(390)
    stubPage()

    await askAndWait(user)
    expectNothingInert()
    await open(user, 'Line 3')

    expectModal()
    expect(panelHeading()).toHaveFocus()

    await user.click(closeButton())

    expectNothingInert()
    expect(chip('Line 3')).toHaveFocus()
  })

  it('closes on a click on the backdrop, and gives the focus back to the chip', async () => {
    const user = userEvent.setup()
    stubWindowWidth(1100)
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 2')
    expectModal()
    await user.click(backdrop()!)

    expect(panel()).not.toBeInTheDocument()
    expectNothingInert()
    expect(chip('Line 2')).toHaveFocus()
  })

  it('still closes on Escape', async () => {
    const user = userEvent.setup()
    stubWindowWidth(1279)
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 15')
    expectModal()
    await user.keyboard('{Escape}')

    expect(panel()).not.toBeInTheDocument()
    expectNothingInert()
    expect(chip('Line 15')).toHaveFocus()
  })

  it('lets go of the page when the window grows to 1280 px, and takes it again when it narrows', async () => {
    const user = userEvent.setup()
    const { resize } = stubWindowWidth(1100)
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 3')
    expectModal()

    await resize(1280)

    expect(panel()).toBeInTheDocument()
    expectNothingInert()

    await resize(1279)

    expectModal()
  })

  it('stays a column beside the questions from 1280 px, with nothing made inert', async () => {
    const user = userEvent.setup()
    stubWindowWidth(1280)
    stubPage()

    await askAndWait(user)
    await open(user, 'Line 3')

    expectNothingInert()
    expect(screen.getByRole('main').nextElementSibling).toBe(panel())
  })
})

describe('when the document cannot be loaded', () => {
  it.each<[string, Route, string]>([
    ['a 404 with a detail', () => Response.json({ detail: 'Document not found.' }, { status: 404 }), 'Document not found.'],
    ['a 502 that is not JSON', () => new Response('Bad Gateway', { status: 502 }), 'Could not load the document.'],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch')), 'Could not load the document.'],
  ])('shows the message in the panel after %s, and the rest stays usable', async (_name, failure, message) => {
    const user = userEvent.setup()
    stubPage({ 'GET /api/documents/1': failure })

    await askAndWait(user)
    await user.click(chip('Line 3'))

    const alert = await inPanel().findByRole('alert')
    expect(alert).toHaveTextContent(message)
    expect(panelHeading()).toHaveTextContent('notes.txt')
    expect(screen.getByText('The answer.')).toBeInTheDocument()
    expect(chip('Line 3')).toHaveAttribute('aria-pressed', 'true')

    await user.click(chip('Line 2'))

    expect(await inPanel().findByRole('list', { name: 'Lines of other.md' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    await user.click(chip('Line 3'))
    expect(await inPanel().findByRole('alert')).toHaveTextContent(message)

    await user.click(chip('Line 3'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('cancelling the request of an open source', () => {
  it('aborts when the panel closes, and shows no error', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage({ 'GET /api/documents/1': rejectsOnAbort })

    await askAndWait(user)
    await user.click(chip('Line 3'))
    const signal = documentRequests(fetchStub)[0][1]?.signal
    expect(signal?.aborted).toBe(false)
    expect(inPanel().getByRole('status')).toHaveTextContent('Loading the document…')
    await user.click(closeButton())

    expect(signal?.aborted).toBe(true)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('aborts when another source opens', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage({ 'GET /api/documents/1': rejectsOnAbort, 'GET /api/documents/2': rejectsOnAbort })

    await askAndWait(user)
    await user.click(chip('Line 3'))
    await user.click(chip('Line 2'))

    const [first, second] = documentRequests(fetchStub).map(([, init]) => init?.signal)
    expect(first?.aborted).toBe(true)
    expect(second?.aborted).toBe(false)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(inPanel().getAllByRole('status')).toHaveLength(1)
  })
})

describe('switching to another dataset', () => {
  // Starts on Invoices, the newest, which holds the documents.
  function stubTwoDatasets(routes: Record<string, Route> = {}) {
    return stubPage({
      'GET /api/datasets': () => Response.json([reports, invoices]),
      'GET /api/datasets/i/documents': () => Response.json([notes, other]),
      ...routes,
    })
  }

  const datasetSelect = () => screen.getByRole('combobox', { name: 'Dataset' })

  it('closes the panel, and does not open it again on return', async () => {
    const user = userEvent.setup()
    stubTwoDatasets()

    await askAndWait(user)
    await open(user, 'Line 3')
    await user.selectOptions(datasetSelect(), reports.id)

    expect(panel()).not.toBeInTheDocument()

    await user.selectOptions(datasetSelect(), invoices.id)
    await screen.findByText('The answer.')

    expect(panel()).not.toBeInTheDocument()
    expect(chip('Line 3')).toHaveAttribute('aria-pressed', 'false')
  })

  it('aborts the request of the open source', async () => {
    const user = userEvent.setup()
    const fetchStub = stubTwoDatasets({ 'GET /api/documents/1': rejectsOnAbort })

    await askAndWait(user)
    await user.click(chip('Line 3'))
    await user.selectOptions(datasetSelect(), reports.id)

    expect(documentRequests(fetchStub)[0][1]?.signal?.aborted).toBe(true)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('closes the panel when the dataset is deleted', async () => {
    const user = userEvent.setup()
    const deleted = vi.fn<Route>(() => new Response(null, { status: 204 }))
    let lists = 0
    stubTwoDatasets({
      'GET /api/datasets': () => Response.json(++lists === 1 ? [reports, invoices] : [reports]),
      'DELETE /api/datasets/i': deleted,
    })

    await askAndWait(user)
    await open(user, 'Line 3')
    await user.click(screen.getByRole('button', { name: 'Delete dataset' }))
    const question = screen.getByRole('group', { name: /^Delete Invoices/ })
    await user.click(within(question).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(datasetSelect()).toHaveValue(reports.id))
    await act(async () => {})
    expect(panel()).not.toBeInTheDocument()
  })
})
