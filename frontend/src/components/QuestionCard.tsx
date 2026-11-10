import { type ReactNode, type Ref, useId, useState } from 'react'
import type { Question } from '../hooks/useQuestions.ts'
import Answer from './Answer.tsx'
import { ChevronDownIcon, ChevronUpIcon, SpinnerIcon } from './icons.tsx'
import ReplyForm from './ReplyForm.tsx'
import Sources from './Sources.tsx'

type Props = {
  question: Question
  // True while any question or reply of the dataset is on its way: a reply then waits its turn.
  waiting: boolean
  onReply: (reply: string) => Promise<void>
  // On the newest card, which the column scrolls to.
  ref?: Ref<HTMLElement>
}

// The local time it was asked, as hours and minutes on a 24-hour clock.
function timeOf(date: Date) {
  const pad = (number: number) => String(number).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}

// The chip in the card's header: where the question is, at a glance, even with the card collapsed.
function statusOf({ answer, reply }: Question): { label: string; tone: string } {
  if (answer === null || (reply !== null && reply.answer === null)) return { label: 'Asking…', tone: 'busy' }
  if (reply !== null && reply.answer !== null) {
    return reply.answer.status === 'not_found'
      ? { label: 'Clarified, not found', tone: 'none' }
      : { label: 'Clarified, then answered', tone: 'clarified' }
  }
  if (answer.status === 'needs_clarification') return { label: 'Needs your reply', tone: 'needs-reply' }
  return answer.status === 'answered' ? { label: 'Answered', tone: 'answered' } : { label: 'Not found', tone: 'none' }
}

// One question of the session: its number, the question, where it is, and below that what came back.
export default function QuestionCard({ question, waiting, onReply, ref }: Props) {
  const { number, answer, reply } = question
  const [collapsed, setCollapsed] = useState(false)
  // The clarifying question's sources, once the reply is answered. They start hidden: the answer comes first.
  const [whyOpen, setWhyOpen] = useState(false)
  const headingId = useId()
  const bodyId = useId()
  const whyId = useId()
  const status = statusOf(question)

  let body: ReactNode
  if (answer === null) {
    const documents = question.documentCount === 1 ? '1 document' : `${question.documentCount} documents`
    body = (
      <>
        <div className="skeleton" aria-hidden="true" />
        <p className="pending-note">
          Searching {documents} and checking every quote. This usually takes 3–20 seconds.
        </p>
      </>
    )
  } else if (reply?.answer) {
    // One round only: the answer to a reply gets no reply form, even if it asks again.
    body = (
      <>
        <dl className="exchange">
          <div>
            <dt>I asked</dt>
            <dd>{answer.answer}</dd>
          </div>
          <div>
            <dt>You replied</dt>
            <dd>{reply.text}</dd>
          </div>
        </dl>
        <Answer result={reply.answer} />
        <button
          type="button"
          className="why-toggle"
          aria-expanded={whyOpen}
          aria-controls={whyId}
          onClick={() => setWhyOpen(!whyOpen)}
        >
          Why I asked ({answer.citations.length})
          {whyOpen ? <ChevronUpIcon className="icon-sm" /> : <ChevronDownIcon className="icon-sm" />}
        </button>
        <div id={whyId} hidden={!whyOpen}>
          <Sources citations={answer.citations} />
        </div>
      </>
    )
  } else {
    body = (
      <>
        <Answer result={answer} />
        {answer.status === 'needs_clarification' && (
          <ReplyForm replying={reply !== null} disabled={waiting} onReply={onReply} />
        )}
      </>
    )
  }

  return (
    <article
      ref={ref}
      className={answer === null ? 'question-card pending' : 'question-card'}
      aria-labelledby={headingId}
      aria-busy={status.tone === 'busy' || undefined}
    >
      <header className="card-head">
        {/* The number is part of the heading, so a screen reader moving by headings hears which question it is. */}
        <h3 id={headingId} className="card-title">
          <span className="q-tag">Q{number}</span> <span className="q-text">{question.question}</span>
        </h3>
        <span className={`status-chip ${status.tone}`}>
          {status.tone === 'busy' ? <SpinnerIcon className="icon-sm spinner" /> : <span className="chip-dot" />}
          {status.label}
        </span>
        <time dateTime={question.askedAt.toISOString()}>{timeOf(question.askedAt)}</time>
        <button
          type="button"
          className="icon-button collapse-button"
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? <ChevronDownIcon className="icon-sm" /> : <ChevronUpIcon className="icon-sm" />}
          <span className="visually-hidden">{collapsed ? `Expand Q${number}` : `Collapse Q${number}`}</span>
        </button>
      </header>
      {/* Hidden rather than removed, so a reply being typed or a source being read is still there when it opens. */}
      <div id={bodyId} className="card-body" hidden={collapsed}>
        {body}
      </div>
    </article>
  )
}
