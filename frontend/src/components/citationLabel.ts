import type { Citation } from '../api/ask.ts'

// A PDF's reader finds a place in it by its page. A text file has only lines.
export function citationLabel({ start_line, end_line, start_page, end_page }: Citation) {
  if (start_page === null) return start_line === end_line ? `Line ${start_line}` : `Lines ${start_line}–${end_line}`
  return start_page === end_page ? `Page ${start_page}` : `Pages ${start_page}–${end_page}`
}
