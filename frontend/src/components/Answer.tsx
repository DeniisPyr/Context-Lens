import type { Answer as AnswerResult } from '../api/ask.ts'
import { SearchOffIcon } from './icons.tsx'
import Sources, { type SourceProps } from './Sources.tsx'

type Props = SourceProps & {
  result: AnswerResult
  // The card's key for this answer, and the card's number, which name its sources in the panel.
  sourceKey: string
  number: number
}

// What came back for a question or a reply, inside its card: the answer and its sources, a clarifying question and
// the lines that make it ask, or the message that the documents don't say.
export default function Answer({ result, sourceKey, number, ...sourceProps }: Props) {
  const why = result.status === 'needs_clarification'

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
          <h4 className="sources-title">{why ? "Why I'm asking" : 'Sources'}</h4>
          <Sources citations={result.citations} group={{ key: sourceKey, number, why }} {...sourceProps} />
        </>
      )}
    </>
  )
}
