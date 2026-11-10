import type { Answer as AnswerResult } from '../api/ask.ts'
import { SearchOffIcon } from './icons.tsx'
import Sources from './Sources.tsx'

type Props = {
  result: AnswerResult
}

// What came back for a question or a reply, inside its card: the answer and its sources, a clarifying question and
// the lines that make it ask, or the message that the documents don't say.
export default function Answer({ result }: Props) {
  if (result.status === 'not_found') {
    return (
      <p className="answer-not-found">
        <SearchOffIcon />
        {result.answer}
      </p>
    )
  }

  return (
    <>
      <p className="answer-text">{result.answer}</p>
      {result.citations.length > 0 && (
        <>
          {/* A clarifying question cites the lines that give different answers: they're why it asks. */}
          <h4 className="sources-title">{result.status === 'needs_clarification' ? "Why I'm asking" : 'Sources'}</h4>
          <Sources citations={result.citations} />
        </>
      )}
    </>
  )
}
