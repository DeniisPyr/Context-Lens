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

// Matches the limit on AskRequest in the backend.
export const MAX_QUESTION_LENGTH = 2000

// The backend searches every document of the dataset, so one answer can cite several files.
export function askQuestion(datasetId: string, question: string): Promise<Answer> {
  return send(
    '/api/ask',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dataset_id: datasetId, question }),
    },
    'Could not get an answer.',
  )
}
