import { act, render, screen } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'

const neverResponds = () => new Promise<Response>(() => {})

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows online when the health check succeeds', async () => {
    const fetchStub = vi.fn<typeof fetch>().mockResolvedValue(new Response('{"status":"ok"}'))
    vi.stubGlobal('fetch', fetchStub)

    render(<App />)

    expect(await screen.findByText('API: online')).toBeInTheDocument()
    expect(fetchStub.mock.calls[0][0]).toBe('/api/health')
  })

  it('shows offline when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch')))

    render(<App />)

    expect(await screen.findByText('API: offline')).toBeInTheDocument()
  })

  it('shows offline on a non-OK response', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 502 })))

    render(<App />)

    expect(await screen.findByText('API: offline')).toBeInTheDocument()
  })

  it('shows checking while the request is pending', () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>(neverResponds))

    render(<App />)

    expect(screen.getByText('API: checking')).toBeInTheDocument()
  })

  it('does not show offline when strict mode cancels the first request', async () => {
    const rejectsOnAbort: typeof fetch = (_input, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      })
    const fetchStub = vi.fn<typeof fetch>(rejectsOnAbort)
    vi.stubGlobal('fetch', fetchStub)

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
    await act(async () => {})

    expect(fetchStub).toHaveBeenCalledTimes(2)
    expect(screen.getByText('API: checking')).toBeInTheDocument()
  })

  it('aborts the request on unmount', () => {
    const fetchStub = vi.fn<typeof fetch>(neverResponds)
    vi.stubGlobal('fetch', fetchStub)

    const { unmount } = render(<App />)
    const signal = fetchStub.mock.calls[0][1]?.signal
    expect(signal?.aborted).toBe(false)

    unmount()

    expect(signal?.aborted).toBe(true)
  })
})
