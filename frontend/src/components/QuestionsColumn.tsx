import { type RefObject, useLayoutEffect, useRef } from 'react'
import type { Dataset } from '../api/datasets.ts'
import { type Failure, isWaiting, type Question } from '../hooks/useQuestions.ts'
import Ask from './Ask.tsx'
import {
  CheckCircleIcon,
  HelpIcon,
  InfoIcon,
  LensIcon,
  PlusIcon,
  SearchOffIcon,
  StackIcon,
  UploadIcon,
} from './icons.tsx'
import QuestionCard from './QuestionCard.tsx'
import type { SourceProps } from './Sources.tsx'

type Props = SourceProps & {
  // undefined while the datasets load, or when there are none.
  dataset: Dataset | undefined
  // True once the list has loaded and is empty, so the start prompt can't show before we know.
  noDatasets: boolean
  // null while the documents load, so the ask box only shows once there's something to search.
  documentCount: number | null
  // The cards of the selected dataset, oldest first, and the last question about it that couldn't be asked.
  questions: Question[]
  failedAsk: Failure | null
  // The question box, which Workspace gives the focus to when nothing better can take it.
  askBoxRef: RefObject<HTMLTextAreaElement | null>
  onAsk: (datasetId: string, question: string, documentCount: number) => void
  onReply: (datasetId: string, question: Question, reply: string) => void
  // Take the user to the control in the sidebar that starts them off, opening it first on a narrow window, where
  // nothing else on the screen says where that is.
  onCreateDataset: () => void
  onAddFiles: () => void
  // True while the sidebar is open over it as a drawer, or the source panel as a modal sheet, so neither the keyboard
  // nor a screen reader wanders in.
  inert: boolean
}

// The middle of the page: a header naming the dataset, the cards of the questions asked about it, which scroll on
// their own, and the box to ask the next one, pinned at the bottom.
export default function QuestionsColumn({
  dataset,
  noDatasets,
  documentCount,
  questions,
  failedAsk,
  askBoxRef,
  onAsk,
  onReply,
  onCreateDataset,
  onAddFiles,
  inert,
  ...sourceProps
}: Props) {
  const newestCard = useRef<HTMLElement>(null)
  const hasDocuments = documentCount !== null && documentCount > 0
  const waiting = isWaiting(questions)
  const newest = questions.at(-1)

  // Brings the newest card into view when it's added, when its answer comes, and on switching to a dataset with
  // cards. Its top, so a long answer is read from the start. A layout effect, so the list never shows elsewhere first.
  const newestState = newest && `${newest.id} ${newest.answer !== null} ${newest.reply?.answer != null}`
  useLayoutEffect(() => {
    newestCard.current?.scrollIntoView({ block: 'start' })
  }, [newestState])

  return (
    <main className="questions" inert={inert}>
      <header className="questions-header">
        <div className="questions-title">
          {dataset && (
            <p className="crumb">
              <StackIcon className="icon-sm" />
              <span className="crumb-name">{dataset.name}</span>
            </p>
          )}
          <h2>Questions in this session</h2>
        </div>
        <p className="questions-note">
          <InfoIcon className="icon-sm" />
          Each question is answered on its own. Earlier ones aren&rsquo;t remembered.
        </p>
      </header>
      <div className="questions-body">
        {noDatasets && (
          <div className="empty-state">
            <p>Create a dataset to get started.</p>
            <button type="button" onClick={onCreateDataset}>
              <PlusIcon className="icon-sm" />
              Create a dataset
            </button>
          </div>
        )}
        {dataset && questions.length === 0 && !hasDocuments && (
          <div className="empty-state">
            <p>Add files to {dataset.name} to ask about them.</p>
            <button type="button" onClick={onAddFiles}>
              <UploadIcon className="icon-sm" />
              Add files
            </button>
          </div>
        )}
        {dataset && questions.length === 0 && hasDocuments && (
          <div className="first-question">
            <span className="first-question-icon" aria-hidden="true">
              <LensIcon />
            </span>
            <h3>Ask your first question about {dataset.name}</h3>
            <ul>
              <li>
                <CheckCircleIcon />
                An answer, with the exact lines it comes from.
              </li>
              <li>
                <SearchOffIcon />
                &ldquo;Not found&rdquo;, when the documents don&rsquo;t say.
              </li>
              <li>
                <HelpIcon />
                A question back, when the answer depends on your situation.
              </li>
            </ul>
          </div>
        )}
        {dataset && questions.length > 0 && (
          <div className="question-cards">
            {questions.map((question) => (
              <QuestionCard
                key={question.id}
                ref={question === newest ? newestCard : undefined}
                question={question}
                waiting={waiting}
                onReply={(reply) => onReply(dataset.id, question, reply)}
                {...sourceProps}
              />
            ))}
          </div>
        )}
      </div>
      {dataset && hasDocuments && (
        // Keyed by the dataset, so a question typed about one dataset is never sent to another.
        <Ask
          key={dataset.id}
          datasetName={dataset.name}
          asking={questions.some((question) => question.answer === null)}
          waiting={waiting}
          failure={failedAsk}
          boxRef={askBoxRef}
          onAsk={(question) => onAsk(dataset.id, question, documentCount)}
        />
      )}
      {dataset && !hasDocuments && questions.length > 0 && (
        <p className="ask-bar ask-unavailable">Add files to {dataset.name} to ask about them.</p>
      )}
    </main>
  )
}
