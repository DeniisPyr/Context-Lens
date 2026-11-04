import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Answer as AnswerResult, Citation } from '../api/ask.ts'
import Answer from './Answer.tsx'

const oneLine: Citation = {
  document_id: '1',
  filename: 'notes.txt',
  start_line: 3,
  end_line: 3,
  quote: 'the third line',
}
const threeLines: Citation = {
  document_id: '1',
  filename: 'notes.txt',
  start_line: 3,
  end_line: 5,
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

afterEach(() => {
  vi.restoreAllMocks()
})

describe('an answer', () => {
  // First in the file: React warns about a missing key only once per component.
  it('shows two identical citations without a key warning', () => {
    const consoleError = vi.spyOn(console, 'error')

    render(<Answer question="Why?" result={answered(oneLine, oneLine)} />)

    expect(screen.getAllByRole('blockquote')).toHaveLength(2)
    expect(consoleError).not.toHaveBeenCalled()
  })

  it('shows the question it answers and the answer text', () => {
    render(<Answer question="Why?" result={answered(oneLine)} />)

    expect(screen.getByText('You asked: Why?')).toBeInTheDocument()
    expect(screen.getByText('The answer.')).toBeInTheDocument()
  })

  it('shows the filename, the lines and the quote of each citation, in order', () => {
    const other = { ...threeLines, filename: 'other.md' }

    render(<Answer question="Why?" result={answered(oneLine, other)} />)

    expect(screen.getByRole('heading', { name: 'Sources' })).toBeInTheDocument()
    const [first, second] = screen.getAllByRole('listitem')
    expect(within(first).getByText('notes.txt')).toBeInTheDocument()
    expect(within(first).getByText('Line 3')).toBeInTheDocument()
    expect(within(first).getByRole('blockquote')).toHaveTextContent('the third line')
    expect(within(second).getByText('other.md')).toBeInTheDocument()
    expect(within(second).getByText('Lines 3–5')).toBeInTheDocument()
    expect(within(second).getByRole('blockquote')).toHaveTextContent('three whole lines')
  })

  it('shows HTML as plain text', () => {
    const html = '<img src=x onerror=alert(1)>'
    const citation = { ...oneLine, filename: `${html}.txt`, quote: `${html} quote` }
    const result = { ...answered(citation), answer: `${html} answer` }

    const { container } = render(<Answer question={`${html} question`} result={result} />)

    expect(screen.getByText(`You asked: ${html} question`)).toBeInTheDocument()
    expect(screen.getByText(`${html} answer`)).toBeInTheDocument()
    expect(screen.getByText(`${html}.txt`)).toBeInTheDocument()
    expect(screen.getByRole('blockquote').textContent).toBe(`${html} quote`)
    expect(container.querySelector('img')).toBeNull()
  })

  it('keeps line breaks in the question, the answer and the quotes, and wraps long text', () => {
    const result = { ...answered({ ...oneLine, quote: 'one\ntwo' }), answer: 'first\nsecond' }

    render(<Answer question={'line one\nline two'} result={result} />)

    const quote = screen.getByRole('blockquote')
    const answerText = screen.getByText(/first/)
    const asked = screen.getByText(/line one/)
    expect(quote.textContent).toBe('one\ntwo')
    expect(answerText.textContent).toBe('first\nsecond')
    expect(asked.textContent).toBe('You asked: line one\nline two')
    for (const element of [quote, answerText, asked]) {
      expect(element).toHaveStyle({ whiteSpace: 'pre-wrap' })
    }
    expect(screen.getByRole('article')).toHaveStyle({ overflowWrap: 'anywhere' })
  })
})

describe('when the document does not hold the answer', () => {
  it('shows the question and the message, with no sources', () => {
    render(<Answer question="Why?" result={notFound} />)

    expect(screen.getByText('You asked: Why?')).toBeInTheDocument()
    expect(screen.getByText(notFound.answer)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Sources' })).not.toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows HTML in the message as plain text', () => {
    const html = '<img src=x onerror=alert(1)>'

    const { container } = render(<Answer question="Why?" result={{ ...notFound, answer: html }} />)

    expect(screen.getByText(html)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('looks different from an answer', () => {
    const { unmount } = render(<Answer question="Why?" result={answered(oneLine)} />)
    expect(screen.getByText('The answer.')).not.toHaveStyle({ fontStyle: 'italic' })
    unmount()

    render(<Answer question="Why?" result={notFound} />)

    expect(screen.getByText(notFound.answer)).toHaveStyle({ fontStyle: 'italic' })
  })
})
