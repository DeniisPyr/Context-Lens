import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App.tsx'

afterEach(() => {
  vi.unstubAllGlobals()
})

// Answers each request by its url, and fails on any other, so an old address can't go unnoticed.
function stubFetch(answers: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (url) => {
      if (String(url) in answers) return Response.json(answers[String(url)])
      throw new Error(`Unexpected request: ${url}`)
    }),
  )
}

it('shows the title, the API status, the datasets, the documents and the ask section', async () => {
  stubFetch({
    '/api/health': { status: 'ok' },
    '/api/session': { login_required: false, logged_in: true },
    '/api/datasets': [{ id: 'r', name: 'Reports' }],
    '/api/datasets/r/documents': [],
  })

  render(<App />)

  expect(screen.getByRole('heading', { name: 'Context-Lens' })).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: 'Datasets' })).toBeInTheDocument()
  expect(await screen.findByText('API: online')).toBeInTheDocument()
  expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Ask a question about Reports' })).toBeInTheDocument()
})

it('shows only the datasets section before any dataset exists', async () => {
  stubFetch({
    '/api/health': { status: 'ok' },
    '/api/session': { login_required: false, logged_in: true },
    '/api/datasets': [],
  })

  render(<App />)

  expect(await screen.findByText('Create a dataset to get started.')).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Documents' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: /^Ask a question/ })).not.toBeInTheDocument()
})
