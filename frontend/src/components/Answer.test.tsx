import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Answer as AnswerResult, Citation } from '../api/ask.ts'
import Answer from './Answer.tsx'

// The panel and its lines are Workspace's: these tests check what the answer shows, and what its chips ask for.
// SourcePanel.test.tsx opens them in the real page.

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

// The first answer of card 7, which is Q3.
function renderAnswer(result: AnswerResult, openSource: string | null = null) {
  const onToggleSource = vi.fn()
  const view = render(
    <Answer result={result} sourceKey="7:first" number={3} openSource={openSource} onToggleSource={onToggleSource} />,
  )
  return { ...view, onToggleSource }
}

function renderCitations(...citations: Citation[]) {
  return renderAnswer(answered(...citations))
}

const lineButton = (name = 'Line 3') => screen.getByRole('button', { name })
const lineButtons = () => screen.getAllByRole('button', { name: 'Line 3' })
const citationOf = (button: HTMLElement) => button.closest('li') as HTMLElement

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('an answer', () => {
  // First in the file: React warns about a missing key only once per component.
  it('shows two identical citations without a key warning', () => {
    const consoleError = vi.spyOn(console, 'error')

    renderCitations(oneLine, oneLine)

    expect(screen.getAllByRole('blockquote')).toHaveLength(2)
    expect(consoleError).not.toHaveBeenCalled()
  })

  it('shows the answer text', () => {
    renderCitations(oneLine)

    expect(screen.getByText('The answer.')).toBeInTheDocument()
  })

  it('leaves out the Sources heading when it cites nothing', () => {
    renderCitations()

    expect(screen.getByText('The answer.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows the filename, the lines and the quote of each citation, in order', () => {
    renderCitations(oneLine, { ...threeLines, filename: 'other.md' })

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

    const { container } = renderAnswer({ ...answered(citation), answer: `${html} answer` })

    expect(screen.getByText(`${html} answer`)).toBeInTheDocument()
    expect(screen.getByText(`${html}.txt`)).toBeInTheDocument()
    expect(screen.getByRole('blockquote').textContent).toBe(`${html} quote`)
    expect(container.querySelector('img')).toBeNull()
  })

  it('keeps line breaks in the answer and the quotes', () => {
    renderAnswer({ ...answered({ ...oneLine, quote: 'one\ntwo' }), answer: 'first\nsecond' })

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

describe('the chip of a citation', () => {
  // Before any other test that tabs: jsdom remembers the last element it showed the focus on, even once that's gone,
  // and then doesn't show it on the next one.
  it('shows clearly when it has the keyboard focus', async () => {
    const user = userEvent.setup()
    renderCitations(oneLine)
    expect(window.getComputedStyle(lineButton()).outline).not.toContain('solid')

    await user.tab()

    expect(window.getComputedStyle(lineButton()).outline).toContain('solid')
  })

  it('starts unpressed, and asks for nothing', () => {
    const fetchStub = vi.fn<typeof fetch>()
    vi.stubGlobal('fetch', fetchStub)

    renderCitations(oneLine, threeLines)

    expect(lineButton()).toHaveAttribute('aria-pressed', 'false')
    expect(lineButton('Lines 3–5')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByText('Showing in viewer')).not.toBeInTheDocument()
    expect(fetchStub).not.toHaveBeenCalled()
  })

  it('asks for its source, named by its card and its place, with itself to give the focus back to', async () => {
    const user = userEvent.setup()
    const { onToggleSource } = renderCitations(oneLine, other)

    await user.click(lineButton('Line 2'))

    expect(onToggleSource).toHaveBeenCalledTimes(1)
    expect(onToggleSource).toHaveBeenCalledWith(
      { key: '7:first:1', citation: other, number: 3, why: false },
      lineButton('Line 2'),
    )
  })

  it('gives two identical citations their own sources', async () => {
    const user = userEvent.setup()
    const { onToggleSource } = renderCitations(oneLine, oneLine)
    const [first, second] = lineButtons()

    await user.click(first)
    await user.click(second)

    expect(onToggleSource.mock.calls.map(([source]) => source.key)).toEqual(['7:first:0', '7:first:1'])
  })

  it('shows which one is open: pressed, its card marked, and a note that the viewer shows it', () => {
    renderAnswer(answered(oneLine, other), '7:first:1')

    expect(lineButton()).toHaveAttribute('aria-pressed', 'false')
    expect(lineButton('Line 2')).toHaveAttribute('aria-pressed', 'true')
    expect(citationOf(lineButton('Line 2'))).toHaveClass('showing')
    expect(citationOf(lineButton())).not.toHaveClass('showing')
    expect(within(citationOf(lineButton('Line 2'))).getByText('Showing in viewer')).toBeInTheDocument()
    expect(screen.getAllByText('Showing in viewer')).toHaveLength(1)
  })

  it('shows none open when the open source is of another answer', () => {
    renderAnswer(answered(oneLine, other), '8:first:1')

    expect(screen.queryAllByRole('button', { pressed: true })).toHaveLength(0)
    expect(screen.queryByText('Showing in viewer')).not.toBeInTheDocument()
  })

  it('works by keyboard, and keeps the focus', async () => {
    const user = userEvent.setup()
    const { onToggleSource } = renderCitations(oneLine)

    await user.tab()
    expect(lineButton()).toHaveFocus()

    await user.keyboard('{Enter}')
    await user.keyboard(' ')

    expect(onToggleSource).toHaveBeenCalledTimes(2)
    expect(lineButton()).toHaveFocus()
  })

  it('looks like a chip, and does not shrink or wrap next to a long filename', () => {
    renderCitations(oneLine)

    expect(lineButton()).toHaveStyle({ borderTopStyle: 'solid', flexShrink: '0', whiteSpace: 'nowrap' })
    expect(lineButton()).toHaveAttribute('type', 'button')
  })
})

describe('when the dataset does not hold the answer', () => {
  it('shows the message, with no sources and no chips', () => {
    renderAnswer(notFound)

    expect(screen.getByText(notFound.answer)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows HTML in the message as plain text', () => {
    const html = '<img src=x onerror=alert(1)>'

    const { container } = renderAnswer({ ...notFound, answer: html })

    expect(screen.getByText(html)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('looks different from an answer: muted, with a search icon', () => {
    const { unmount } = renderCitations(oneLine)
    const answerColour = window.getComputedStyle(screen.getByText('The answer.')).color
    unmount()

    renderAnswer(notFound)

    const message = screen.getByText(notFound.answer)
    expect(window.getComputedStyle(message).color).not.toBe(answerColour)
    expect(message.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(message).toHaveStyle({ whiteSpace: 'pre-wrap' })
  })
})

describe('a clarifying question', () => {
  it("shows the question with the lines that answer differently, under Why I'm asking", () => {
    renderAnswer(clarifying)

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
    const { unmount } = renderAnswer(notFound)
    const notFoundColour = window.getComputedStyle(screen.getByText(notFound.answer)).color
    unmount()

    renderAnswer(clarifying)

    const text = screen.getByText(clarifying.answer)
    expect(window.getComputedStyle(text).color).not.toBe(notFoundColour)
    expect(text.querySelector('svg')).toBeNull()
    expect(text).toHaveStyle({ whiteSpace: 'pre-wrap' })
  })

  it('opens its sources as the reasons it asks', async () => {
    const user = userEvent.setup()
    const { onToggleSource } = renderAnswer(clarifying)

    await user.click(lineButton())

    expect(onToggleSource).toHaveBeenCalledWith(
      { key: '7:first:0', citation: oneLine, number: 3, why: true },
      lineButton(),
    )
  })

  it('shows HTML as plain text', () => {
    const html = '<img src=x onerror=alert(1)>'

    const { container } = renderAnswer({ ...clarifying, answer: `${html} question` })

    expect(screen.getByText(`${html} question`)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })
})
