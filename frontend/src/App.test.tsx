import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App.tsx'

afterEach(() => {
  vi.unstubAllGlobals()
})

it('shows the title, the API status, the documents and the ask section', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (url) => Response.json(url === '/api/documents' ? [] : { status: 'ok' })),
  )

  render(<App />)

  expect(screen.getByRole('heading', { name: 'Context-Lens' })).toBeInTheDocument()
  expect(await screen.findByText('API: online')).toBeInTheDocument()
  expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Ask a question' })).toBeInTheDocument()
})
