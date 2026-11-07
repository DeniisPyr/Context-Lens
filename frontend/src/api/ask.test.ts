import { afterEach, describe, expect, it, vi } from 'vitest'
import { askQuestion } from './ask.ts'

const answer = {
  status: 'answered',
  answer: 'Two lines.',
  citations: [{ document_id: '1', filename: 'notes.txt', start_line: 1, end_line: 2, quote: 'one two' }],
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('askQuestion', () => {
  it('posts the dataset id and the question as JSON and returns the answer', async () => {
    const fetchStub = vi.fn<typeof fetch>(async () => Response.json(answer))
    vi.stubGlobal('fetch', fetchStub)

    await expect(askQuestion('d1', 'How long is it?')).resolves.toEqual(answer)

    const [url, init = {}] = fetchStub.mock.calls[0]
    expect(url).toBe('/api/ask')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ dataset_id: 'd1', question: 'How long is it?' })
  })

  it('uses the message from the backend when detail is a string', async () => {
    const detail = 'Gemini could not answer this question.'
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => Response.json({ detail }, { status: 502 })))

    await expect(askQuestion('d1', 'Why?')).rejects.toThrow(detail)
  })

  it.each<[string, () => Promise<Response>]>([
    ['a 502 with no JSON', async () => new Response('Bad Gateway', { status: 502 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['a validation error whose detail is an array', async () => Response.json({ detail: [{ msg: 'x' }] }, { status: 422 })],
    ['a successful response that is not JSON', async () => new Response('<html>')],
  ])('falls back on %s', async (_name, respond) => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(respond))

    await expect(askQuestion('d1', 'Why?')).rejects.toThrow('Could not get an answer.')
  })
})
