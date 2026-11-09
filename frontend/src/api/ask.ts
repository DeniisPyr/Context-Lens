import { send } from './request.ts'

export type Citation = {
  document_id: string
  filename: string
  start_line: number
  end_line: number
  quote: string
}

export type Answer = {
  // needs_clarification: the documents answer the question differently depending on something it doesn't say. The
  // answer is then a question back to the user, and the citations are the lines that differ.
  status: 'answered' | 'not_found' | 'needs_clarification'
  answer: string
  citations: Citation[]
}

// A reply to a clarifying question. The question goes back exactly as it came, so the backend knows what was asked.
export type Clarification = {
  question: string
  reply: string
}

// Matches the limit on AskRequest in the backend.
export const MAX_QUESTION_LENGTH = 2000
// The backend limits a reply like a question.
export const MAX_REPLY_LENGTH = 2000

// The backend searches every document of the dataset, so one answer can cite several files. A reply goes with the
// question it clarifies, and its answer is never another clarifying question: the backend asks only once.
export function askQuestion(datasetId: string, question: string, clarification?: Clarification): Promise<Answer> {
  return send(
    '/api/ask',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // JSON.stringify leaves out an undefined clarification, so a new question has no clarification key at all.
      body: JSON.stringify({ dataset_id: datasetId, question, clarification }),
    },
    'Could not get an answer.',
  )
}
