import { useRef, useState } from 'react'
import { type Answer, askQuestion } from '../api/ask.ts'

// A question or a reply that couldn't be sent: why, and the text as the user typed it, to go back in its box.
export type Failure = {
  error: string
  draft: string
}

// One question of the session, shown as a card.
export type Question = {
  // Unique for as long as the page is open, so a card keeps its key and its state when others come and go.
  id: number
  // Counted per dataset, from 1: Q1, Q2, …
  number: number
  // Trimmed, as it was sent.
  question: string
  askedAt: Date
  // How many documents the dataset held when it was asked, which is what the backend searches.
  documentCount: number
  // null while the question is on its way.
  answer: Answer | null
  // Only after a reply to a clarifying question: what was replied, and the answer to it, null while that's on its way.
  reply: { text: string; answer: Answer | null } | null
  // The last reply that couldn't be sent, until the next one is. Kept with the card rather than in its reply form,
  // which goes when another dataset is selected, so it's still there on the way back.
  failedReply: Failure | null
}

// What the session holds about one dataset.
export type DatasetQuestions = {
  // Its cards, oldest first.
  questions: Question[]
  // The last question about it that couldn't be asked, until the next one is sent. Kept here rather than in the ask
  // box, which starts over for each dataset, so it's still there on the way back.
  failedAsk: Failure | null
}

// The cards of each dataset, and what couldn't be sent about it, kept for as long as Workspace is on the page:
// switching to another dataset and back shows them again, and logging out takes them away with Workspace. The backend
// remembers none of them: each question is answered on its own.
export function useQuestions() {
  // By dataset id. A dataset gets its entry with its first question, and loses it when it's deleted.
  const [byDataset, setByDataset] = useState<Record<string, DatasetQuestions>>({})
  const lastId = useRef(0)

  // Changes what's held about a dataset that's still here. An answer or an error that arrives after its dataset was
  // deleted finds no entry, and goes nowhere.
  function update(datasetId: string, change: (dataset: DatasetQuestions) => DatasetQuestions) {
    setByDataset((current) =>
      datasetId in current ? { ...current, [datasetId]: change(current[datasetId]) } : current,
    )
  }

  function updateQuestion(datasetId: string, id: number, change: (question: Question) => Question) {
    update(datasetId, (dataset) => ({
      ...dataset,
      questions: dataset.questions.map((question) => (question.id === id ? change(question) : question)),
    }))
  }

  // Adds a card at once, while the question is on its way, and gives it the answer when it comes. The question is
  // sent trimmed. A failed question leaves no card: it goes again, and the error and the text as typed stay with the
  // dataset for the ask box. Both belong to the dataset it was asked about, wherever the user is when they come.
  async function ask(datasetId: string, typed: string, documentCount: number) {
    const id = ++lastId.current
    const question = typed.trim()
    const askedAt = new Date()
    setByDataset((current) => {
      const questions = current[datasetId]?.questions ?? []
      const added = {
        id,
        number: questions.length + 1,
        question,
        askedAt,
        documentCount,
        answer: null,
        reply: null,
        failedReply: null,
      }
      return { ...current, [datasetId]: { questions: [...questions, added], failedAsk: null } }
    })
    try {
      const answer = await askQuestion(datasetId, question)
      updateQuestion(datasetId, id, (asked) => ({ ...asked, answer }))
    } catch (err) {
      const failedAsk = { error: (err as Error).message, draft: typed }
      update(datasetId, ({ questions }) => ({ questions: questions.filter((asked) => asked.id !== id), failedAsk }))
    }
  }

  // Sends the reply to a card's clarifying question, trimmed, with the question it clarifies, and puts the answer in
  // the same card. A failed reply takes the card back to its clarifying question, with the error and the reply as
  // typed for its reply form.
  async function reply(datasetId: string, asked: Question, typed: string) {
    if (asked.answer === null) return
    const text = typed.trim()
    const clarification = { question: asked.answer.answer, reply: text }
    updateQuestion(datasetId, asked.id, (question) => ({
      ...question,
      reply: { text, answer: null },
      failedReply: null,
    }))
    try {
      const answer = await askQuestion(datasetId, asked.question, clarification)
      updateQuestion(datasetId, asked.id, (question) => ({ ...question, reply: { text, answer } }))
    } catch (err) {
      const failedReply = { error: (err as Error).message, draft: typed }
      updateQuestion(datasetId, asked.id, (question) => ({ ...question, reply: null, failedReply }))
    }
  }

  // The cards of a deleted dataset go with it, and so does a question about it that couldn't be asked.
  function forget(datasetId: string) {
    setByDataset((current) => {
      const rest = { ...current }
      delete rest[datasetId]
      return rest
    })
  }

  return { byDataset, ask, reply, forget }
}

// True while a question or a reply of these cards is on its way. A dataset's questions go one at a time, so its
// cards are answered in the order they were asked.
export function isWaiting(questions: Question[]) {
  return questions.some((question) => question.answer === null || question.reply?.answer === null)
}
