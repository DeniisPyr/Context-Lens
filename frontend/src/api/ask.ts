import { send } from './request.ts'

export type Citation = {
  document_id: string
  filename: string
  start_line: number
  end_line: number
  quote: string
}

export type Answer = {
  status: 'answered' | 'not_found'
  answer: string
  citations: Citation[]
}

// Matches the limit on AskRequest in the backend.
export const MAX_QUESTION_LENGTH = 2000

export function askQuestion(documentId: string, question: string): Promise<Answer> {
  return send(
    '/api/ask',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_id: documentId, question }),
    },
    'Could not get an answer.',
  )
}
