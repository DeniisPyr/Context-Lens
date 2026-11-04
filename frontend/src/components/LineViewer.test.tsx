import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Citation } from '../api/ask.ts'
import LineViewer from './LineViewer.tsx'

const citation: Citation = {
  document_id: '1',
  filename: 'notes.txt',
  start_line: 50,
  end_line: 50,
  quote: 'line 50',
}

const citing = (start_line: number, end_line = start_line): Citation => ({ ...citation, start_line, end_line })

function detail(lines: string[]) {
  return { id: '1', filename: 'notes.txt', line_count: lines.length, lines }
}

const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, index) => from + index)

// A document whose line N says "line N", so a row's number can be checked against its text.
const numberedLines = (count: number) => range(1, count).map((number) => `line ${number}`)

function stubFetch(respond: (init?: RequestInit) => Response | Promise<Response>) {
  const fetchStub = vi.fn<typeof fetch>(async (_url, init) => respond(init))
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

function stubDocument(lines: string[]) {
  return stubFetch(() => Response.json(detail(lines)))
}

// Like the real fetch: never answers by itself, and rejects once aborted.
function rejectsOnAbort(init?: RequestInit) {
  return new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })
}

async function renderLoaded(cited: Citation, lines: string[]) {
  stubDocument(lines)
  const result = render(<LineViewer citation={cited} />)
  await screen.findByRole('list')
  return result
}

const rows = () => screen.getAllByRole('listitem')

// Each row as its number and its text, both exactly as they are in the page.
const shownRows = () =>
  rows().map((row) => {
    const [number, text] = row.children
    return [number.textContent, text.textContent]
  })

const rowsOfNumberedLines = (from: number, to: number) =>
  range(from, to).map((number) => [String(number), `line ${number}`])

const rowOfLine = (number: number) => rows().find((row) => row.children[0].textContent === String(number))!

const citedNumbers = () =>
  rows()
    .filter((row) => row.getAttribute('aria-current') === 'true')
    .map((row) => row.children[0].textContent)

const earlierButton = () => screen.queryByRole('button', { name: 'Show earlier lines' })
const laterButton = () => screen.queryByRole('button', { name: 'Show later lines' })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('loading the document', () => {
  // First in the file: React warns about a missing key only once per component.
  it('shows the rows without a key warning', async () => {
    const consoleError = vi.spyOn(console, 'error')

    await renderLoaded(citation, numberedLines(100))

    expect(consoleError).not.toHaveBeenCalled()
  })

  it('asks for the cited document and shows the loading state until it comes', async () => {
    let answer!: (response: Response) => void
    const fetchStub = stubFetch(() => new Promise((resolve) => (answer = resolve)))

    render(<LineViewer citation={{ ...citation, document_id: 'abc-123' }} />)

    expect(screen.getByRole('status')).toHaveTextContent('Loading the document…')
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    expect(fetchStub).toHaveBeenCalledTimes(1)
    const [url, init] = fetchStub.mock.calls[0]
    expect(url).toBe('/api/documents/abc-123')
    expect(init?.signal).toBeInstanceOf(AbortSignal)

    answer(Response.json(detail(numberedLines(100))))

    expect(await screen.findByRole('list')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('the window around a citation', () => {
  it('shows ten lines either side, with their real line numbers', async () => {
    await renderLoaded(citation, numberedLines(100))

    expect(shownRows()).toEqual(rowsOfNumberedLines(40, 60))
  })

  it('counts the context from both ends of a citation of several lines', async () => {
    await renderLoaded(citing(50, 52), numberedLines(100))

    expect(shownRows()).toEqual(rowsOfNumberedLines(40, 62))
  })

  it('stops at the start of the document', async () => {
    await renderLoaded(citing(3), numberedLines(100))

    expect(shownRows()).toEqual(rowsOfNumberedLines(1, 13))
  })

  it('stops at the end of the document', async () => {
    await renderLoaded(citing(98), numberedLines(100))

    expect(shownRows()).toEqual(rowsOfNumberedLines(88, 100))
  })

  it('shows the whole of a short document', async () => {
    await renderLoaded(citing(2), numberedLines(3))

    expect(shownRows()).toEqual(rowsOfNumberedLines(1, 3))
  })

  it('marks the cited line and no other', async () => {
    await renderLoaded(citation, numberedLines(100))

    expect(citedNumbers()).toEqual(['50'])
  })

  it('marks every line of a citation of several lines and no other', async () => {
    await renderLoaded(citing(50, 52), numberedLines(100))

    expect(citedNumbers()).toEqual(['50', '51', '52'])
  })

  it('highlights only the marked lines, as whole rows', async () => {
    await renderLoaded(citation, numberedLines(100))

    const backgroundOf = (number: number) => window.getComputedStyle(rowOfLine(number)).backgroundColor
    expect(backgroundOf(49)).toBe('rgba(0, 0, 0, 0)')
    expect(backgroundOf(50)).not.toBe(backgroundOf(49))
    expect(backgroundOf(51)).toBe(backgroundOf(49))
  })
})

describe('showing more lines', () => {
  it('adds ten earlier lines each time, then removes the button at the start', async () => {
    const user = userEvent.setup()
    await renderLoaded(citing(25), numberedLines(100))
    expect(shownRows()).toEqual(rowsOfNumberedLines(15, 35))

    await user.click(earlierButton()!)
    expect(shownRows()).toEqual(rowsOfNumberedLines(5, 35))

    await user.click(earlierButton()!)
    expect(shownRows()).toEqual(rowsOfNumberedLines(1, 35))
    expect(earlierButton()).not.toBeInTheDocument()
    expect(laterButton()).toBeInTheDocument()
  })

  it('adds ten later lines each time, then removes the button at the end', async () => {
    const user = userEvent.setup()
    await renderLoaded(citing(75), numberedLines(100))
    expect(shownRows()).toEqual(rowsOfNumberedLines(65, 85))

    await user.click(laterButton()!)
    expect(shownRows()).toEqual(rowsOfNumberedLines(65, 95))

    await user.click(laterButton()!)
    expect(shownRows()).toEqual(rowsOfNumberedLines(65, 100))
    expect(laterButton()).not.toBeInTheDocument()
    expect(earlierButton()).toBeInTheDocument()
  })

  it('shows no button when the first window just reaches both ends', async () => {
    await renderLoaded(citing(11, 90), numberedLines(100))

    expect(shownRows()).toEqual(rowsOfNumberedLines(1, 100))
    expect(earlierButton()).not.toBeInTheDocument()
    expect(laterButton()).not.toBeInTheDocument()
  })

  it('shows both buttons one line short of each end, and removes them after the last line', async () => {
    const user = userEvent.setup()
    await renderLoaded(citing(12, 89), numberedLines(100))
    expect(shownRows()).toEqual(rowsOfNumberedLines(2, 99))

    await user.click(earlierButton()!)
    await user.click(laterButton()!)

    expect(shownRows()).toEqual(rowsOfNumberedLines(1, 100))
    expect(earlierButton()).not.toBeInTheDocument()
    expect(laterButton()).not.toBeInTheDocument()
  })

  it('shows neither button for a short document', async () => {
    await renderLoaded(citing(2), numberedLines(3))

    expect(earlierButton()).not.toBeInTheDocument()
    expect(laterButton()).not.toBeInTheDocument()
  })

  it('puts the earlier button above the list and the later button below it', async () => {
    await renderLoaded(citation, numberedLines(100))

    const list = screen.getByRole('list')
    expect(list.previousElementSibling).toBe(earlierButton())
    expect(list.nextElementSibling).toBe(laterButton())
  })

  it('keeps the cited lines marked as the window grows', async () => {
    const user = userEvent.setup()
    await renderLoaded(citing(50, 51), numberedLines(100))

    await user.click(earlierButton()!)
    await user.click(laterButton()!)

    expect(citedNumbers()).toEqual(['50', '51'])
  })

  it('does not ask for the document again', async () => {
    const user = userEvent.setup()
    const fetchStub = stubDocument(numberedLines(100))
    render(<LineViewer citation={citation} />)
    await screen.findByRole('list')

    await user.click(earlierButton()!)
    await user.click(laterButton()!)

    expect(fetchStub).toHaveBeenCalledTimes(1)
  })
})

describe('scrolling to the citation', () => {
  it('centres the first cited line once when the document loads', async () => {
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')

    await renderLoaded(citing(50, 52), numberedLines(100))

    expect(scroll).toHaveBeenCalledTimes(1)
    expect(scroll).toHaveBeenCalledWith({ block: 'center' })
    expect(scroll.mock.contexts[0]).toBe(rowOfLine(50))
  })

  it('does not scroll before the document has loaded', () => {
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    stubFetch(rejectsOnAbort)

    render(<LineViewer citation={citation} />)

    expect(scroll).not.toHaveBeenCalled()
  })

  it('does not scroll when the load fails', async () => {
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    stubFetch(() => new Response('Bad Gateway', { status: 502 }))

    render(<LineViewer citation={citation} />)
    await screen.findByRole('alert')

    expect(scroll).not.toHaveBeenCalled()
  })

  it('does not scroll again when the window grows', async () => {
    const user = userEvent.setup()
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    await renderLoaded(citation, numberedLines(100))

    await user.click(earlierButton()!)
    await user.click(laterButton()!)

    expect(scroll).toHaveBeenCalledTimes(1)
  })

  it('scrolls once under StrictMode', async () => {
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
    let requests = 0
    stubFetch((init) => (++requests === 1 ? rejectsOnAbort(init) : Response.json(detail(numberedLines(100)))))

    render(
      <StrictMode>
        <LineViewer citation={citation} />
      </StrictMode>,
    )
    await screen.findByRole('list')

    expect(scroll).toHaveBeenCalledTimes(1)
  })
})

describe('the text of a line', () => {
  it('keeps blank lines, leading spaces, tabs and Czech text exactly', async () => {
    const lines = ['první', '', '    čtyři mezery', '\ttabulátor', '   ', 'žluťoučký kůň  ']

    await renderLoaded(citing(1), lines)

    expect(shownRows()).toEqual(lines.map((line, index) => [String(index + 1), line]))
  })

  it('counts blank lines in the numbering and the window', async () => {
    await renderLoaded(citing(14), ['first', ...Array<string>(12).fill(''), 'cited', '', 'last'])

    expect(shownRows()[0]).toEqual(['4', ''])
    expect(citedNumbers()).toEqual(['14'])
    expect(rowOfLine(14).children[1].textContent).toBe('cited')
    expect(shownRows().at(-1)).toEqual(['16', 'last'])
  })

  it('shows HTML as plain text', async () => {
    const html = '<img src=x onerror=alert(1)> <b>bold</b>'

    const { container } = await renderLoaded(citing(1), [html])

    expect(rowOfLine(1).children[1].textContent).toBe(html)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
  })

  it('keeps spaces, wraps long text and leaves the number out of a copy', async () => {
    await renderLoaded(citing(1), ['text'])

    const [number, text] = rowOfLine(1).children
    expect(text).toHaveStyle({ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' })
    expect(number).toHaveStyle({ userSelect: 'none' })
    expect(number).not.toHaveStyle({ whiteSpace: 'pre-wrap' })
  })

  it('lists the lines without markers in a box that scrolls and a keyboard can reach', async () => {
    await renderLoaded(citing(1), ['text'])

    const list = screen.getByRole('list', { name: 'Lines of notes.txt' })
    expect(list.tagName).toBe('OL')
    expect(list).toHaveStyle({ listStyle: 'none', overflowY: 'auto' })
    expect(list).toHaveAttribute('tabindex', '0')
    const { maxHeight, fontFamily } = window.getComputedStyle(list)
    expect(maxHeight).not.toBe('none')
    expect(fontFamily).toContain('monospace')
  })
})

describe('when the document cannot be loaded', () => {
  it.each<[string, () => Response | Promise<Response>, string]>([
    [
      'a 404 with a detail',
      () => Response.json({ detail: 'Document not found.' }, { status: 404 }),
      'Document not found.',
    ],
    ['a 502 that is not JSON', () => new Response('Bad Gateway', { status: 502 }), 'Could not load the document.'],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch')), 'Could not load the document.'],
  ])('shows the message after %s', async (_name, respond, message) => {
    stubFetch(respond)

    render(<LineViewer citation={citation} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })
})

describe('cancelling the request', () => {
  it('aborts on unmount', () => {
    const fetchStub = stubFetch(rejectsOnAbort)

    const { unmount } = render(<LineViewer citation={citation} />)
    const signal = fetchStub.mock.calls[0][1]?.signal
    expect(signal?.aborted).toBe(false)

    unmount()

    expect(signal?.aborted).toBe(true)
  })

  it('shows no error when StrictMode cancels the first request', async () => {
    let requests = 0
    const fetchStub = stubFetch((init) =>
      ++requests === 1 ? rejectsOnAbort(init) : Response.json(detail(numberedLines(100))),
    )

    render(
      <StrictMode>
        <LineViewer citation={citation} />
      </StrictMode>,
    )
    await screen.findByRole('list')

    expect(fetchStub).toHaveBeenCalledTimes(2)
    expect(fetchStub.mock.calls[0][1]?.signal?.aborted).toBe(true)
    expect(fetchStub.mock.calls[1][1]?.signal?.aborted).toBe(false)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(shownRows()).toEqual(rowsOfNumberedLines(40, 60))
  })
})
