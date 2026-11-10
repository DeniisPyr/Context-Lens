import { act, render, screen, within } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'

// These tests render the whole page, and only fetch is faked. jsdom applies no media queries, so the top bar and the
// sidebar both show at any width: what they check is the state the stylesheet draws from, not the layout.

type Route = (init?: RequestInit) => Response | Promise<Response>

function stubRoutes(routes: Record<string, Route>) {
  const fetchStub = vi.fn<typeof fetch>(async (url, init) => routes[`${init?.method ?? 'GET'} ${url}`](init))
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

const reports = { id: 'r', name: 'Reports' }
const invoices = { id: 'i', name: 'Invoices' }
const contracts = { id: 'c', name: 'Contracts' }
const notes = { id: '1', filename: 'notes.txt', line_count: 30, page_count: null }

const answered = {
  status: 'answered',
  answer: 'The answer.',
  citations: [
    { document_id: '1', filename: 'notes.txt', start_line: 3, end_line: 3, start_page: null, end_page: null, quote: 'q' },
  ],
}
const lines = Array.from({ length: notes.line_count }, (_, index) => `notes line ${index + 1}`)

// Two datasets, each holding notes.txt. Invoices is the newest, so it's the one selected at first.
function stubPage(routes: Record<string, Route> = {}) {
  return stubRoutes({
    'GET /api/health': () => Response.json({ status: 'ok' }),
    'GET /api/session': () => Response.json({ login_required: true, logged_in: true }),
    'GET /api/datasets': () => Response.json([reports, invoices]),
    'GET /api/datasets/r/documents': () => Response.json([notes]),
    'GET /api/datasets/i/documents': () => Response.json([notes]),
    'GET /api/datasets/c/documents': () => Response.json([]),
    'POST /api/ask': () => Response.json(answered),
    'GET /api/documents/1': () => Response.json({ ...notes, lines, page_starts: null }),
    ...routes,
  })
}

// matchMedia for a window this many pixels wide, answering the queries the page asks it.
function stubWindowWidth(width: number) {
  const matchMedia = vi.fn((query: string) => {
    const [, bound, pixels] = /^\((min|max)-width: (\d+)px\)$/.exec(query)!
    const matches = bound === 'min' ? width >= Number(pixels) : width <= Number(pixels)
    return { matches, addEventListener: vi.fn(), removeEventListener: vi.fn() }
  })
  vi.stubGlobal('matchMedia', matchMedia)
  return matchMedia
}

const menuButton = () => screen.getByRole('button', { name: 'Menu' })
// Found from its button: Testing Library takes every header on the page for a banner, the cards' too.
const topBar = () => menuButton().closest('header')!
const sidebar = () => screen.getByRole('complementary', { name: 'Datasets and documents' })
const questionsColumn = () => screen.getByRole('main')
const sourcePanel = () => screen.getByRole('complementary', { name: 'Source' })
const datasetSelect = () => screen.getByRole<HTMLSelectElement>('combobox', { name: 'Dataset' })
const newDatasetButton = () => screen.getByRole('button', { name: 'New dataset' })
// The shade beside the drawer is only for the pointer, so it has no role or name to find it by: the keyboard closes
// the drawer with Escape or the Menu button.
const backdrop = () => document.querySelector<HTMLElement>('.drawer-backdrop')

// The page, once the selected dataset's documents have loaded.
async function renderPage() {
  render(<App />)
  await screen.findByText('notes.txt')
}

function expectOpen() {
  expect(menuButton()).toHaveAttribute('aria-expanded', 'true')
  expect(backdrop()).toBeInTheDocument()
  expect(questionsColumn()).toHaveAttribute('inert')
}

function expectClosed() {
  expect(menuButton()).toHaveAttribute('aria-expanded', 'false')
  expect(backdrop()).not.toBeInTheDocument()
  expect(questionsColumn()).not.toHaveAttribute('inert')
}

async function openDrawer(user: UserEvent) {
  await user.click(menuButton())
  expectOpen()
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the top bar', () => {
  it("shows the Menu button, the app's name and the selected dataset", async () => {
    stubPage()

    await renderPage()

    expect(menuButton()).toHaveAttribute('aria-expanded', 'false')
    expect(sidebar().id).not.toBe('')
    expect(menuButton()).toHaveAttribute('aria-controls', sidebar().id)
    expect(within(topBar()).getByText('Context-Lens')).toBeInTheDocument()
    expect(within(topBar()).getByText('Invoices')).toBeInTheDocument()
  })

  it('names the dataset chosen in the sidebar', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    await user.selectOptions(datasetSelect(), reports.id)

    expect(within(topBar()).getByText('Reports')).toBeInTheDocument()
    expect(within(topBar()).queryByText('Invoices')).not.toBeInTheDocument()
  })

  it('names no dataset while there is none', async () => {
    stubPage({ 'GET /api/datasets': () => Response.json([]) })

    render(<App />)
    await screen.findByText('Create a dataset to get started.')

    expect(topBar()).toHaveTextContent(/^MenuContext-Lens$/)
  })

  it('leaves the page with one top heading, the one in the sidebar', async () => {
    stubPage()

    await renderPage()

    expect(screen.getAllByRole('heading', { level: 1 })).toEqual([
      within(sidebar()).getByRole('heading', { level: 1, name: 'Context-Lens' }),
    ])
  })
})

describe('opening the sidebar as a drawer', () => {
  it('starts closed, with nothing behind it made inert', async () => {
    stubPage()

    await renderPage()

    expectClosed()
    expect(sidebar()).not.toHaveAttribute('tabindex')
  })

  it('opens from Menu, which says so, and moves the focus into the sidebar', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    await openDrawer(user)

    expect(sidebar()).toHaveFocus()
    expect(sidebar()).toHaveAttribute('tabindex', '-1')
  })

  it('works by keyboard, and Tab goes on to the controls inside', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    act(() => menuButton().focus())
    await user.keyboard('{Enter}')

    expectOpen()
    expect(sidebar()).toHaveFocus()
    await user.tab()
    expect(newDatasetButton()).toHaveFocus()
  })

  it('makes the questions and the open source inert behind it, but not the top bar', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    await user.type(screen.getByRole('textbox', { name: 'Question' }), 'Why?{Enter}')
    await user.click(await screen.findByRole('button', { name: 'Line 3' }))
    await openDrawer(user)

    expect(sourcePanel()).toHaveAttribute('inert')
    expect(topBar()).not.toHaveAttribute('inert')
    expect(sidebar()).not.toHaveAttribute('inert')

    await user.click(menuButton())

    expect(questionsColumn()).not.toHaveAttribute('inert')
    expect(sourcePanel()).not.toHaveAttribute('inert')
  })
})

describe('closing the drawer', () => {
  it('closes from Menu again, which keeps the focus', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    await openDrawer(user)
    await user.click(menuButton())

    expectClosed()
    expect(menuButton()).toHaveFocus()
    expect(sidebar()).not.toHaveAttribute('tabindex')
  })

  it('closes on Escape from a control inside, and gives the focus back to Menu', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    await openDrawer(user)
    await user.tab()
    await user.keyboard('{Escape}')

    expectClosed()
    expect(menuButton()).toHaveFocus()
  })

  it('closes on Escape from the drawer itself and from Menu', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    await openDrawer(user)
    await user.keyboard('{Escape}')
    expectClosed()

    await openDrawer(user)
    act(() => menuButton().focus())
    await user.keyboard('{Escape}')
    expectClosed()
    expect(menuButton()).toHaveFocus()
  })

  it('lets the new dataset form take the first Escape, and closes on the next', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    await openDrawer(user)
    await user.click(newDatasetButton())
    await user.keyboard('{Escape}')

    expect(screen.queryByRole('textbox', { name: 'New dataset name' })).not.toBeInTheDocument()
    expectOpen()
    expect(newDatasetButton()).toHaveFocus()

    await user.keyboard('{Escape}')

    expectClosed()
    expect(menuButton()).toHaveFocus()
  })

  it('closes on a click beside it, and gives the focus back to Menu', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    await openDrawer(user)
    await user.click(backdrop()!)

    expectClosed()
    expect(menuButton()).toHaveFocus()
  })

  it('stays open when a dataset is chosen, which shows its questions behind it', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    await openDrawer(user)
    act(() => datasetSelect().focus())
    await user.selectOptions(datasetSelect(), reports.id)

    // On Windows and Linux every arrow key on the select chooses a dataset, so closing would take the list away.
    expectOpen()
    expect(datasetSelect()).toHaveFocus()
    expect(datasetSelect()).toHaveValue(reports.id)
    expect(within(questionsColumn()).getByText('Reports')).toBeInTheDocument()

    await user.selectOptions(datasetSelect(), invoices.id)

    expectOpen()
    expect(datasetSelect()).toHaveValue(invoices.id)
  })

  it('stays open when a dataset is created, so files can go into it next', async () => {
    const user = userEvent.setup()
    // The list the page reloads after creating it has the new dataset too.
    const datasets = [reports, invoices]
    stubPage({
      'GET /api/datasets': () => Response.json(datasets),
      'POST /api/datasets': () => {
        datasets.push(contracts)
        return Response.json(contracts, { status: 201 })
      },
    })

    await renderPage()
    await openDrawer(user)
    await user.click(newDatasetButton())
    await user.type(screen.getByRole('textbox', { name: 'New dataset name' }), 'Contracts')
    await user.click(screen.getByRole('button', { name: 'Create' }))
    await screen.findByText('No documents yet.')

    expect(datasetSelect()).toHaveValue(contracts.id)
    expectOpen()
    expect(newDatasetButton()).toHaveFocus()
  })

  it('closes by itself when the window grows wide enough for the sidebar', async () => {
    const user = userEvent.setup()
    let onChange: (() => void) | undefined
    const wide = {
      matches: false,
      addEventListener: vi.fn((_type: string, listener: () => void) => (onChange = listener)),
      removeEventListener: vi.fn(),
    }
    const matchMedia = vi.fn(() => wide)
    vi.stubGlobal('matchMedia', matchMedia)
    stubPage()

    await renderPage()
    await openDrawer(user)

    expect(matchMedia).toHaveBeenCalledWith('(min-width: 900px)')
    // Still narrow: nothing changes.
    act(() => onChange?.())
    expectOpen()

    wide.matches = true
    act(() => onChange?.())

    expectClosed()
    expect(wide.removeEventListener).toHaveBeenCalledWith('change', onChange)
  })
})

describe('with the drawer closed', () => {
  it('leaves the focus on the select when a dataset is chosen', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    act(() => datasetSelect().focus())
    await user.selectOptions(datasetSelect(), reports.id)

    expect(datasetSelect()).toHaveValue(reports.id)
    expect(datasetSelect()).toHaveFocus()
    expectClosed()
  })

  it('leaves Escape alone', async () => {
    const user = userEvent.setup()
    stubPage()

    await renderPage()
    act(() => newDatasetButton().focus())
    await user.keyboard('{Escape}')

    expect(newDatasetButton()).toHaveFocus()
    expectClosed()
  })
})

describe('the buttons of the empty questions column, on a narrow window', () => {
  it('opens the drawer from Create a dataset, with the focus in the name field', async () => {
    const user = userEvent.setup()
    const matchMedia = stubWindowWidth(390)
    stubPage({ 'GET /api/datasets': () => Response.json([]) })

    render(<App />)
    await screen.findByText('Create a dataset to get started.')
    await user.click(screen.getByRole('button', { name: 'Create a dataset' }))

    expect(matchMedia).toHaveBeenCalledWith('(min-width: 900px)')
    expectOpen()
    expect(screen.getByRole('textbox', { name: 'New dataset name' })).toHaveFocus()
  })

  it('opens the drawer from Add files, with the focus on the file input', async () => {
    const user = userEvent.setup()
    stubWindowWidth(390)
    stubPage({ 'GET /api/datasets/i/documents': () => Response.json([]) })

    render(<App />)
    await screen.findByText('Add files to Invoices to ask about them.')
    await user.click(screen.getByRole('button', { name: 'Add files' }))

    expectOpen()
    expect(screen.getByLabelText('Add files')).toHaveFocus()
  })

  it('gives the focus to the drawer when the file input is disabled, as it is while files upload', async () => {
    const user = userEvent.setup()
    stubWindowWidth(390)
    stubPage({
      'GET /api/datasets/i/documents': () => Response.json([]),
      'POST /api/datasets/i/documents': () => new Promise<Response>(() => {}),
    })

    render(<App />)
    await screen.findByText('Add files to Invoices to ask about them.')
    await user.upload(screen.getByLabelText('Add files'), new File(['text'], 'a.txt'))
    expect(screen.getByLabelText('Add files')).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Add files' }))

    expectOpen()
    expect(sidebar()).toHaveFocus()
  })

  it('leaves the drawer closed on a window wide enough for the sidebar, and only moves the focus', async () => {
    const user = userEvent.setup()
    stubWindowWidth(1440)
    stubPage({ 'GET /api/datasets/i/documents': () => Response.json([]) })

    render(<App />)
    await screen.findByText('Add files to Invoices to ask about them.')
    await user.click(screen.getByRole('button', { name: 'Add files' }))

    expectClosed()
    expect(screen.getByLabelText('Add files')).toHaveFocus()
  })
})
