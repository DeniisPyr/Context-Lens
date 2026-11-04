import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App.tsx'

afterEach(() => {
  vi.unstubAllGlobals()
})

it('shows the title and the API status', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => Response.json({ status: 'ok' })))

  render(<App />)

  expect(screen.getByRole('heading', { name: 'Context-Lens' })).toBeInTheDocument()
  expect(await screen.findByText('API: online')).toBeInTheDocument()
})
