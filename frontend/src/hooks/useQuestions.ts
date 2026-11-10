import { useRef, useState } from 'react'
import { type Answer, askQuestion } from '../api/ask.ts'

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
}

// The cards of each dataset, kept for as long as Workspace is on the page: switching to another dataset and back shows
// them again, and logging out takes them away with Workspace. The backend remembers none of them: each question is
// answered on its own.
export function useQuestions() {
  // By dataset id. A dataset gets its entry with its first question, and loses it when it's deleted.
  const [byDataset, setByDataset] = useState<Record<string, Question[]>>({})
  const lastId = useRef(0)

  // Changes the cards of a dataset that's still here. An answer that arrives after its dataset was deleted finds no
  // entry, and goes nowhere.
  function update(datasetId: string, change: (questions: Question[]) => Question[]) {
    setByDataset((current) =>
      datasetId in current ? { ...current, [datasetId]: change(current[datasetId]) } : current,
    )
  }

  function updateQuestion(datasetId: string, id: number, change: (question: Question) => Question) {
    update(datasetId, (questions) => questions.map((question) => (question.id === id ? change(question) : question)))
  }

  // Adds a card at once, while the question is on its way, and gives it the answer when it comes. A failed question
  // leaves no card: it goes again, and the error is thrown for the ask box to show. The card belongs to the dataset it
  // was asked about, wherever the user is when the answer comes.
  async function ask(datasetId: string, question: string, documentCount: number) {
    const id = ++lastId.current
    const askedAt = new Date()
    setByDataset((current) => {
      const questions = current[datasetId] ?? []
      const added = { id, number: questions.length + 1, question, askedAt, documentCount, answer: null, reply: null }
      return { ...current, [datasetId]: [...questions, added] }
    })
    try {
      const answer = await askQuestion(datasetId, question)
      updateQuestion(datasetId, id, (asked) => ({ ...asked, answer }))
    } catch (err) {
      update(datasetId, (questions) => questions.filter((asked) => asked.id !== id))
      throw err
    }
  }

  // Sends the reply to a card's clarifying question with the question it clarifies, and puts the answer in the same
  // card. A failed reply takes the card back to its clarifying question, and the error is thrown for the reply form.
  async function reply(datasetId: string, asked: Question, text: string) {
    if (asked.answer === null) return
    const clarification = { question: asked.answer.answer, reply: text }
    updateQuestion(datasetId, asked.id, (question) => ({ ...question, reply: { text, answer: null } }))
    try {
      const answer = await askQuestion(datasetId, asked.question, clarification)
      updateQuestion(datasetId, asked.id, (question) => ({ ...question, reply: { text, answer } }))
    } catch (err) {
      updateQuestion(datasetId, asked.id, (question) => ({ ...question, reply: null }))
      throw err
    }
  }

  // The cards of a deleted dataset go with it.
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
