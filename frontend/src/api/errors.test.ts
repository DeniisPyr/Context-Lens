import { describe, expect, it } from 'vitest'
import { errorMessage } from './errors.ts'

describe('errorMessage', () => {
  it('uses detail when it is a string', async () => {
    const response = Response.json({ detail: 'File is too large.' }, { status: 413 })

    expect(await errorMessage(response, 'fallback')).toBe('File is too large.')
  })

  it('falls back when detail is an array', async () => {
    const response = Response.json({ detail: [{ msg: 'Field required' }] }, { status: 422 })

    expect(await errorMessage(response, 'fallback')).toBe('fallback')
  })

  it('falls back when the body is not JSON', async () => {
    const response = new Response('Bad Gateway', { status: 502 })

    expect(await errorMessage(response, 'fallback')).toBe('fallback')
  })
})
