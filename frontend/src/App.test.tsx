import { render, screen, within } from '@testing-library/react'
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

const sidebar = () => screen.getByRole('complementary', { name: 'Datasets and documents' })
const questionsColumn = () => screen.getByRole('main')

it('shows the title, the API status, the dataset and its documents in the sidebar, and the questions beside it', async () => {
  stubFetch({
    '/api/health': { status: 'ok' },
    '/api/session': { login_required: false, logged_in: true },
    '/api/datasets': [{ id: 'r', name: 'Reports' }],
    '/api/datasets/r/documents': [],
  })

  render(<App />)

  expect(screen.getByRole('heading', { name: 'Context-Lens' })).toBeInTheDocument()
  expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
  expect(within(sidebar()).getByText('No documents yet.')).toBeInTheDocument()
  expect(within(sidebar()).getByRole('heading', { level: 1, name: 'Context-Lens' })).toBeInTheDocument()
  expect(await within(sidebar()).findByText('API online')).toBeInTheDocument()
  expect(within(sidebar()).getByRole('combobox', { name: 'Dataset' })).toHaveValue('r')
  expect(within(sidebar()).getByRole('heading', { name: 'Documents' })).toBeInTheDocument()
  expect(within(questionsColumn()).getByRole('heading', { name: 'Questions in this session' })).toBeInTheDocument()
  expect(within(questionsColumn()).getByText('Reports')).toBeInTheDocument()
  expect(within(questionsColumn()).getByRole('heading', { name: 'Ask a question about Reports' })).toBeInTheDocument()
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

it('ends the sidebar with the theme switch, and with Log out when a login is required', async () => {
  stubFetch({
    '/api/health': { status: 'ok' },
    '/api/session': { login_required: true, logged_in: true },
    '/api/datasets': [],
  })

  render(<App />)
  await screen.findByText('Create a dataset to get started.')

  expect(within(sidebar()).getByRole('group', { name: 'Theme' })).toBeInTheDocument()
  expect(within(sidebar()).getByText('Signed in')).toBeInTheDocument()
  expect(within(sidebar()).getByText('Password access')).toBeInTheDocument()
  expect(within(sidebar()).getByRole('button', { name: 'Log out' })).toBeEnabled()
})

it('leaves the account out of the sidebar when no login is required', async () => {
  stubFetch({
    '/api/health': { status: 'ok' },
    '/api/session': { login_required: false, logged_in: true },
    '/api/datasets': [],
  })

  render(<App />)
  await screen.findByText('Create a dataset to get started.')

  expect(within(sidebar()).getByRole('group', { name: 'Theme' })).toBeInTheDocument()
  expect(screen.queryByText('Signed in')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Log out' })).not.toBeInTheDocument()
})
