import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
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
  expect(within(questionsColumn()).getByText('Add files to Reports to ask about them.')).toBeInTheDocument()
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
  expect(screen.queryByText(/^Add files to/)).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: 'Question' })).not.toBeInTheDocument()
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

describe('files dragged over the page', () => {
  const notes = { id: '1', filename: 'notes.txt', line_count: 1, page_count: null }
  // What a browser's drag carries, as jsdom has no DataTransfer: files, or text, as from the question box.
  const carrying = (types: string[]) => ({ files: [new File(['text'], 'notes.txt')], types, dropEffect: 'copy' })
  const dropZone = () => screen.getByLabelText('Add files').closest('label')!

  // One empty dataset, which an upload fills.
  async function renderPage() {
    const fetchStub = vi.fn<typeof fetch>(async (url, init) => {
      if (init?.method === 'POST') return Response.json(notes, { status: 201 })
      const answers: Record<string, unknown> = {
        '/api/health': { status: 'ok' },
        '/api/session': { login_required: false, logged_in: true },
        '/api/datasets': [{ id: 'r', name: 'Reports' }],
        '/api/datasets/r/documents': [],
      }
      return Response.json(answers[String(url)])
    })
    vi.stubGlobal('fetch', fetchStub)
    const view = render(<App />)
    await screen.findByText('No documents yet.')
    const uploads = () => fetchStub.mock.calls.filter(([, init]) => init?.method === 'POST')
    return { ...view, uploads }
  }

  it('are turned away outside the drop zone, so the browser cannot open a file in place of the app', async () => {
    const { uploads } = await renderPage()
    const dataTransfer = carrying(['Files'])

    // fireEvent returns false when the default was prevented: the browser would otherwise open the file.
    expect(fireEvent.dragOver(questionsColumn(), { dataTransfer })).toBe(false)
    expect(dataTransfer.dropEffect).toBe('none')
    expect(fireEvent.drop(questionsColumn(), { dataTransfer })).toBe(false)
    expect(fireEvent.dragOver(document.body, { dataTransfer })).toBe(false)
    expect(uploads()).toHaveLength(0)
  })

  it('are left to the drop zone over it, which uploads them', async () => {
    const { uploads } = await renderPage()
    const dataTransfer = carrying(['Files'])

    expect(fireEvent.dragOver(dropZone(), { dataTransfer })).toBe(false)
    expect(dataTransfer.dropEffect).toBe('copy')
    fireEvent.drop(dropZone(), { dataTransfer })

    expect(await screen.findByText('1 uploaded, 0 failed.')).toBeInTheDocument()
    expect(uploads()).toHaveLength(1)
  })

  it('are left alone when they carry no files, as text dragged into the question box does', async () => {
    await renderPage()
    const dataTransfer = carrying(['text/plain'])

    expect(fireEvent.dragOver(questionsColumn(), { dataTransfer })).toBe(true)
    expect(dataTransfer.dropEffect).toBe('copy')
  })

  it('are no longer turned away once the workspace has left the page', async () => {
    const { unmount } = await renderPage()

    unmount()

    expect(fireEvent.dragOver(document.body, { dataTransfer: carrying(['Files']) })).toBe(true)
  })
})
