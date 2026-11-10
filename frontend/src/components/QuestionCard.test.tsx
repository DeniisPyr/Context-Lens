import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Answer, Citation } from '../api/ask.ts'
import type { Question } from '../hooks/useQuestions.ts'
import QuestionCard from './QuestionCard.tsx'

const citation: Citation = {
  document_id: '1',
  filename: 'notes.txt',
  start_line: 3,
  end_line: 3,
  start_page: null,
  end_page: null,
  quote: 'the third line',
}

const answered: Answer = { status: 'answered', answer: 'The answer.', citations: [citation] }
const notFound: Answer = {
  status: 'not_found',
  answer: "Sorry, I can't find anything related to your question in the documents you provided.",
  citations: [],
}
const clarifying: Answer = {
  status: 'needs_clarification',
  answer: 'Did you lose a company laptop or a phone?',
  citations: [
    { ...citation, start_line: 2, end_line: 2, quote: 'a lost laptop' },
    { ...citation, start_line: 7, end_line: 8, quote: 'a lost phone' },
  ],
}

// Asked at 14:08 local time, about a dataset of 7 documents.
function question(changes: Partial<Question> = {}): Question {
  return {
    id: 1,
    number: 3,
    question: 'Why?',
    askedAt: new Date(2026, 10, 10, 14, 8, 30),
    documentCount: 7,
    answer: answered,
    reply: null,
    ...changes,
  }
}

const replied = (answer: Answer | null, text = 'A laptop.') =>
  question({ answer: clarifying, reply: { text, answer } })

function renderCard(
  asked: Question,
  { waiting = false, onReply = vi.fn(async () => {}), openSource = null as string | null } = {},
) {
  const onToggleSource = vi.fn()
  const view = render(
    <QuestionCard
      question={asked}
      waiting={waiting}
      onReply={onReply}
      openSource={openSource}
      onToggleSource={onToggleSource}
    />,
  )
  return { ...view, onToggleSource }
}

const card = () => screen.getByRole('article')
const header = () => card().querySelector('header')!
const collapseButton = () => screen.getByRole('button', { name: /^(Collapse|Expand) Q3$/ })
const whyButton = () => screen.getByRole('button', { name: /^Why I asked/ })

afterEach(() => {
  vi.restoreAllMocks()
})

describe('the header of a card', () => {
  it('numbers the question in its heading, and names the card by it', () => {
    renderCard(question())

    const heading = screen.getByRole('heading', { level: 3 })
    expect(heading).toHaveTextContent('Q3 Why?')
    expect(card()).toHaveAccessibleName('Q3 Why?')
  })

  it('shows the local time it was asked, in hours and minutes', () => {
    renderCard(question())

    const time = within(card()).getByText('14:08')
    expect(time.tagName).toBe('TIME')
    expect(time).toHaveAttribute('datetime', new Date(2026, 10, 10, 14, 8, 30).toISOString())
  })

  it('pads the hours and minutes to two digits', () => {
    renderCard(question({ askedAt: new Date(2026, 0, 2, 9, 5) }))

    expect(within(card()).getByText('09:05')).toBeInTheDocument()
  })

  it.each<[string, Question, string]>([
    ['asking', question({ answer: null }), 'Asking…'],
    ['answered', question(), 'Answered'],
    ['not found', question({ answer: notFound }), 'Not found'],
    ['waiting for a reply', question({ answer: clarifying }), 'Needs your reply'],
    ['sending a reply', replied(null), 'Asking…'],
    ['answered after a reply', replied(answered), 'Clarified, then answered'],
    ['not found after a reply', replied(notFound), 'Clarified, not found'],
  ])('says where the question is when %s', (_name, asked, status) => {
    renderCard(asked)

    expect(within(header()).getByText(status)).toBeInTheDocument()
  })

  it('marks the card busy, with a spinner, only while something is on its way', () => {
    const { unmount } = renderCard(question({ answer: null }))
    expect(card()).toHaveAttribute('aria-busy', 'true')
    expect(within(card()).getByText('Asking…').querySelector('svg')).toHaveClass('spinner')
    unmount()

    renderCard(question())

    expect(card()).not.toHaveAttribute('aria-busy')
  })

  it('keeps line breaks in the question, wraps long words, and shows HTML as plain text', () => {
    const html = '<img src=x onerror=alert(1)>'

    const { container } = renderCard(question({ question: `${html}\nsecond line` }))

    const text = screen.getByText(/second line/)
    expect(text.textContent).toBe(`${html}\nsecond line`)
    expect(text).toHaveStyle({ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', minWidth: '0px' })
    expect(card()).toHaveStyle({ overflowWrap: 'anywhere' })
    expect(container.querySelector('img')).toBeNull()
  })
})

describe('collapsing a card', () => {
  it('hides the body and keeps the header, then shows it again', async () => {
    const user = userEvent.setup()
    renderCard(question())
    expect(collapseButton()).toHaveAccessibleName('Collapse Q3')
    expect(collapseButton()).toHaveAttribute('aria-expanded', 'true')

    await user.click(collapseButton())

    expect(collapseButton()).toHaveAccessibleName('Expand Q3')
    expect(collapseButton()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('The answer.')).not.toBeVisible()
    expect(screen.getByText('Why?')).toBeVisible()
    expect(within(header()).getByText('Answered')).toBeVisible()

    await user.click(collapseButton())

    expect(collapseButton()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('The answer.')).toBeVisible()
  })

  it('controls the body, and keeps a reply being typed while it is closed', async () => {
    const user = userEvent.setup()
    renderCard(question({ answer: clarifying }))
    const replyBox = screen.getByRole('textbox', { name: 'Your reply' })
    await user.type(replyBox, 'A laptop.')

    await user.click(collapseButton())
    await user.click(collapseButton())

    const body = document.getElementById(collapseButton().getAttribute('aria-controls')!)
    expect(body).toContainElement(screen.getByRole('textbox', { name: 'Your reply' }))
    expect(screen.getByRole('textbox', { name: 'Your reply' })).toHaveValue('A laptop.')
  })
})

describe('while the question is on its way', () => {
  it('shows a placeholder and how many documents are searched', () => {
    renderCard(question({ answer: null }))

    expect(
      within(card()).getByText(
        'Searching 7 documents and checking every quote. This usually takes 3–20 seconds.',
      ),
    ).toBeInTheDocument()
    expect(card().querySelector('.skeleton')).toHaveAttribute('aria-hidden', 'true')
    expect(card()).toHaveStyle({ borderTopStyle: 'dashed' })
  })

  it('counts one document as one', () => {
    renderCard(question({ answer: null, documentCount: 1 }))

    expect(within(card()).getByText(/^Searching 1 document and/)).toBeInTheDocument()
  })

  it('has a solid outline once answered', () => {
    renderCard(question())

    expect(card()).toHaveStyle({ borderTopStyle: 'solid' })
  })
})

describe('a clarifying question in a card', () => {
  it('has the reply form inside the card, after the lines it asks about', () => {
    renderCard(question({ answer: clarifying }))

    const form = screen.getByRole('textbox', { name: 'Your reply' }).closest('form')!
    expect(card()).toContainElement(form)
    expect(screen.getByRole('heading', { name: "Why I'm asking" })).toBeInTheDocument()
    expect(within(card()).getAllByRole('blockquote').at(-1)!.compareDocumentPosition(form)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
    expect(screen.getByRole('button', { name: 'Reply' })).toBeEnabled()
  })

  it('says Replying… and disables the button while its reply is on its way', () => {
    renderCard(replied(null), { waiting: true })

    expect(screen.getByRole('button', { name: 'Replying…' })).toBeDisabled()
    expect(screen.getByText(clarifying.answer)).toBeInTheDocument()
    expect(screen.queryByText('You replied')).not.toBeInTheDocument()
  })

  it('disables Reply, without saying Replying…, while another request of the dataset is on its way', () => {
    renderCard(question({ answer: clarifying }), { waiting: true })

    expect(screen.getByRole('button', { name: 'Reply' })).toBeDisabled()
  })

  it('sends the trimmed reply', async () => {
    const user = userEvent.setup()
    const onReply = vi.fn(async () => {})
    renderCard(question({ answer: clarifying }), { onReply })

    await user.type(screen.getByRole('textbox', { name: 'Your reply' }), '  A laptop. ')
    await user.click(screen.getByRole('button', { name: 'Reply' }))

    expect(onReply).toHaveBeenCalledWith('A laptop.')
  })
})

describe('the answer to a reply', () => {
  const exchange = () =>
    within(card())
      .getAllByRole('term')
      .map((term) => [term.textContent, term.nextElementSibling?.textContent])

  it('shows what was asked back and the reply above the answer, and no reply form', () => {
    renderCard(replied(answered))

    expect(exchange()).toEqual([
      ['I asked', clarifying.answer],
      ['You replied', 'A laptop.'],
    ])
    const answer = screen.getByText('The answer.')
    expect(within(card()).getAllByRole('definition').at(-1)!.compareDocumentPosition(answer)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
    expect(screen.getByRole('heading', { name: 'Sources' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Your reply' })).not.toBeInTheDocument()
  })

  it('shows the exchange above a missing answer too', () => {
    renderCard(replied(notFound))

    expect(exchange()).toEqual([
      ['I asked', clarifying.answer],
      ['You replied', 'A laptop.'],
    ])
    expect(screen.getByText(notFound.answer)).toBeInTheDocument()
  })

  it('shows no exchange on the answer to a question', () => {
    renderCard(question())

    expect(screen.queryByText('I asked')).not.toBeInTheDocument()
    expect(screen.queryByText('You replied')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Why I asked/ })).not.toBeInTheDocument()
  })

  it('keeps line breaks in the exchange, and shows HTML in it as plain text', () => {
    const html = '<img src=x onerror=alert(1)>'

    const { container } = renderCard(
      question({ answer: { ...clarifying, answer: `${html}\nquestion` }, reply: { text: `${html}\nreply`, answer: answered } }),
    )

    const [asked, reply] = within(card()).getAllByRole('definition')
    expect(asked.textContent).toBe(`${html}\nquestion`)
    expect(reply.textContent).toBe(`${html}\nreply`)
    expect(asked).toHaveStyle({ whiteSpace: 'pre-wrap' })
    expect(reply).toHaveStyle({ whiteSpace: 'pre-wrap' })
    expect(container.querySelector('img')).toBeNull()
  })
})

describe('Why I asked', () => {
  it("counts the clarifying question's sources, and starts with them hidden", () => {
    renderCard(replied(answered))

    expect(whyButton()).toHaveAccessibleName('Why I asked (2)')
    expect(whyButton()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('a lost laptop')).not.toBeVisible()
    expect(screen.getByText('the third line')).toBeVisible()
  })

  it('shows and hides them, and controls the part that holds them', async () => {
    const user = userEvent.setup()
    renderCard(replied(answered))

    await user.click(whyButton())

    expect(whyButton()).toHaveAttribute('aria-expanded', 'true')
    const why = document.getElementById(whyButton().getAttribute('aria-controls')!)!
    expect(within(why).getAllByRole('blockquote').map((quote) => quote.textContent)).toEqual([
      'a lost laptop',
      'a lost phone',
    ])
    expect(within(why).getByRole('button', { name: 'Line 2' })).toBeVisible()
    expect(within(why).getByRole('button', { name: 'Lines 7–8' })).toBeVisible()

    await user.click(whyButton())

    expect(whyButton()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('a lost laptop')).not.toBeVisible()
  })
})

describe('the sources of a card', () => {
  it('tells the answer to the reply from the lines the clarifying question cited', async () => {
    const user = userEvent.setup()
    const { onToggleSource } = renderCard(replied(answered))

    await user.click(screen.getByRole('button', { name: 'Line 3' }))
    await user.click(whyButton())
    await user.click(screen.getByRole('button', { name: 'Line 2' }))

    expect(onToggleSource.mock.calls.map(([source]) => [source.key, source.number, source.why])).toEqual([
      ['1:reply:0', 3, false],
      ['1:first:0', 3, true],
    ])
  })

  it('stands out while one of its sources is open, and only then', () => {
    const { unmount } = renderCard(question(), { openSource: '1:first:0' })
    expect(card()).toHaveClass('showing')
    expect(screen.getByRole('button', { name: 'Line 3' })).toHaveAttribute('aria-pressed', 'true')
    unmount()

    renderCard(question(), { openSource: '2:first:0' })

    expect(card()).not.toHaveClass('showing')
    expect(screen.getByRole('button', { name: 'Line 3' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('keeps a clarifying source pressed behind Why I asked once the reply is answered', async () => {
    const user = userEvent.setup()
    renderCard(replied(answered), { openSource: '1:first:1' })

    await user.click(whyButton())

    expect(screen.getByRole('button', { name: 'Lines 7–8' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Line 3' })).toHaveAttribute('aria-pressed', 'false')
  })
})
