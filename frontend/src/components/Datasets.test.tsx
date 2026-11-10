import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'

// These tests render the whole page, so only fetch is faked.

type Route = (init?: RequestInit) => Response | Promise<Response>

function stubRoutes(routes: Record<string, Route>) {
  const fetchStub = vi.fn<typeof fetch>(async (url, init) => routes[`${init?.method ?? 'GET'} ${url}`](init))
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

const reports = { id: 'r', name: 'Reports' }
const invoices = { id: 'i', name: 'Invoices' }
const contracts = { id: 'c', name: 'Contracts' }

const documentsPath = (id: string) => `/api/datasets/${id}/documents`
const listOf = (id: string) => `GET ${documentsPath(id)}`

// The page with these datasets, each of them empty, and an API that answers.
function stubPage(datasets: (typeof reports)[], routes: Record<string, Route> = {}) {
  const emptyLists = Object.fromEntries(datasets.map(({ id }) => [listOf(id), () => Response.json([])]))
  return stubRoutes({
    'GET /api/health': () => Response.json({ status: 'ok' }),
    'GET /api/session': () => Response.json({ login_required: false, logged_in: true }),
    'GET /api/datasets': () => Response.json(datasets),
    ...emptyLists,
    ...routes,
  })
}

// Like the real fetch: never answers by itself, and rejects once aborted.
const rejectsOnAbort: Route = (init) =>
  new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })

// The GET route for a list that changes: each load gets the next list, and the last one stays.
function listThatChanges<T>(...lists: T[][]): Route {
  let load = 0
  return () => Response.json(lists[Math.min(load++, lists.length - 1)])
}

// Answers one request only when the test says so, and rejects once aborted like the real fetch.
function waitingRoute() {
  let resolve!: (response: Response) => void
  const route: Route = (init) =>
    new Promise((res, reject) => {
      resolve = res
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })
  return {
    route,
    // Waits for the request first, because the page sends some requests from an effect.
    answer: async (response: Response) => {
      await waitFor(() => expect(resolve).toBeDefined())
      await act(async () => resolve(response))
    },
  }
}

const datasetSelect = () => screen.getByRole<HTMLSelectElement>('combobox', { name: 'Dataset' })
const nameInput = () => screen.getByRole<HTMLInputElement>('textbox', { name: 'New dataset name' })
const createButton = () => screen.getByRole('button', { name: 'Create' })
const newDatasetButton = () => screen.getByRole('button', { name: 'New dataset' })
const questionBox = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Question' })
const startMessage = 'Create a dataset to get started.'
// The question a Delete button asks, for a dataset or a document. Named, because the theme switch is a group too.
const deleteQuestion = () => screen.queryByRole('group', { name: /^Delete / })

// Waits for a document's row in the list, by its Delete button, which names the file.
const findDocument = (filename: string) => screen.findByRole('button', { name: `Delete ${filename}` })

const requestsTo = (fetchStub: ReturnType<typeof stubRoutes>, url: string, method = 'GET') =>
  fetchStub.mock.calls.filter((call) => call[0] === url && (call[1]?.method ?? 'GET') === method)

// Opens the form first when there are datasets already, and it's closed.
async function createNamed(user: UserEvent, name: string) {
  if (!screen.queryByRole('textbox', { name: 'New dataset name' })) await user.click(newDatasetButton())
  await user.clear(nameInput())
  await user.type(nameInput(), name)
  await user.click(createButton())
}

function expectNoDocumentsOrAsk() {
  expect(screen.queryByRole('heading', { name: 'Documents' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: /^Ask a question/ })).not.toBeInTheDocument()
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('before any dataset exists', () => {
  it('says how to start and shows no documents, no ask section and no select', async () => {
    stubPage([])

    render(<App />)

    expect(await screen.findByText(startMessage)).toBeInTheDocument()
    expectNoDocumentsOrAsk()
    expect(screen.queryByRole('combobox', { name: 'Dataset' })).not.toBeInTheDocument()
    expect(nameInput()).toBeInTheDocument()
    // Creating a dataset is all there is to do, so the form can't be closed.
    expect(screen.queryByRole('button', { name: 'New dataset' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
  })

  it('says nothing while the first load is running', async () => {
    const fetchStub = stubPage([], { 'GET /api/datasets': rejectsOnAbort })

    render(<App />)
    await waitFor(() => expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(1))

    expect(screen.queryByText(startMessage)).not.toBeInTheDocument()
    expectNoDocumentsOrAsk()
  })

  it('shows the error instead when the first load fails, and still offers the form', async () => {
    stubPage([], { 'GET /api/datasets': () => new Response('Bad Gateway', { status: 502 }) })

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the datasets.')
    expect(screen.queryByText(startMessage)).not.toBeInTheDocument()
    expectNoDocumentsOrAsk()
    expect(nameInput()).toBeInTheDocument()
  })

  it('shows the backend message when the first load fails with one', async () => {
    const detail = 'The database is unavailable right now. Please try again.'
    stubPage([], { 'GET /api/datasets': () => Response.json({ detail }, { status: 503 }) })

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
  })

  it('aborts the first load on unmount', async () => {
    const fetchStub = stubPage([], { 'GET /api/datasets': rejectsOnAbort })

    const { unmount } = render(<App />)
    // The datasets load once the session check has answered.
    await waitFor(() => expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(1))
    const signal = requestsTo(fetchStub, '/api/datasets')[0][1]?.signal
    expect(signal?.aborted).toBe(false)

    unmount()

    expect(signal?.aborted).toBe(true)
  })

  it('does not show an error when strict mode cancels the first request', async () => {
    const fetchStub = stubPage([], { 'GET /api/datasets': rejectsOnAbort })

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
    await waitFor(() => expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(2))
    await act(async () => {})

    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('moves on to the documents and ask sections once the first dataset is created', async () => {
    const user = userEvent.setup()
    stubPage([], {
      'GET /api/datasets': listThatChanges([], [reports]),
      'POST /api/datasets': () => Response.json(reports, { status: 201 }),
      [listOf(reports.id)]: () => Response.json([]),
    })

    render(<App />)
    await screen.findByText(startMessage)
    await createNamed(user, 'Reports')

    expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
    expect(datasetSelect()).toHaveValue(reports.id)
    expect(screen.queryByText(startMessage)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ask a question about Reports' })).toBeInTheDocument()
    // The form closes, and the focus goes to the button that opens it again.
    expect(screen.queryByRole('textbox', { name: 'New dataset name' })).not.toBeInTheDocument()
    expect(newDatasetButton()).toHaveFocus()
  })
})

describe('the New dataset button', () => {
  it('opens the form under it, with the focus in the name field', async () => {
    const user = userEvent.setup()
    stubPage([reports])

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })

    expect(newDatasetButton()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('textbox', { name: 'New dataset name' })).not.toBeInTheDocument()

    await user.click(newDatasetButton())

    expect(newDatasetButton()).toHaveAttribute('aria-expanded', 'true')
    expect(nameInput()).toHaveFocus()
    expect(createButton()).toBeEnabled()
  })

  it.each([
    ['Cancel', (user: UserEvent) => user.click(screen.getByRole('button', { name: 'Cancel' }))],
    ['Escape', (user: UserEvent) => user.keyboard('{Escape}')],
    ['New dataset again', (user: UserEvent) => user.click(newDatasetButton())],
  ])('closes the form on %s, sends nothing and puts the focus back on New dataset', async (_name, close) => {
    const user = userEvent.setup()
    const fetchStub = stubPage([reports])

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await user.click(newDatasetButton())
    await user.type(nameInput(), 'Invoices')
    await close(user)

    expect(screen.queryByRole('textbox', { name: 'New dataset name' })).not.toBeInTheDocument()
    expect(newDatasetButton()).toHaveFocus()
    expect(newDatasetButton()).toHaveAttribute('aria-expanded', 'false')
    expect(requestsTo(fetchStub, '/api/datasets', 'POST')).toHaveLength(0)

    // Nothing typed is kept for the next time.
    await user.click(newDatasetButton())
    expect(nameInput()).toHaveValue('')
  })

  it('keeps the form open and the name typed when creating fails', async () => {
    const user = userEvent.setup()
    stubPage([reports], { 'POST /api/datasets': () => new Response('Bad Gateway', { status: 502 }) })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await createNamed(user, 'Invoices')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not create the dataset.')
    expect(nameInput()).toHaveValue('Invoices')
    expect(newDatasetButton()).toHaveAttribute('aria-expanded', 'true')
  })
})

describe('the card of the selected dataset', () => {
  const document = (id: string) => ({ id, filename: `${id}.txt`, line_count: 1, page_count: null })

  it('shows its name, how many documents it holds and where it is in the list', async () => {
    const user = userEvent.setup()
    stubPage([reports, invoices, contracts], {
      [listOf(contracts.id)]: () => Response.json([document('a'), document('b')]),
      [listOf(reports.id)]: () => Response.json([document('c')]),
    })

    render(<App />)
    await findDocument('a.txt')

    expect(screen.getByText('Contracts', { selector: '.switcher-name' })).toBeInTheDocument()
    expect(datasetSelect()).toHaveAccessibleDescription('2 documents · 3 of 3 datasets')

    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('c.txt')

    expect(screen.getByText('Reports', { selector: '.switcher-name' })).toBeInTheDocument()
    expect(datasetSelect()).toHaveAccessibleDescription('1 document · 1 of 3 datasets')
  })

  it('leaves the number of documents out until they have loaded, and says when it is the only dataset', async () => {
    const { route, answer } = waitingRoute()
    stubPage([reports], { [listOf(reports.id)]: route })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })

    expect(datasetSelect()).toHaveAccessibleDescription('the only dataset')

    await answer(Response.json([]))

    expect(datasetSelect()).toHaveAccessibleDescription('0 documents · the only dataset')
  })
})

describe('the Dataset select', () => {
  it('offers every dataset by name, in the order of the list, and selects the newest', async () => {
    const fetchStub = stubPage([reports, invoices, contracts])

    render(<App />)

    const options = within(await screen.findByRole('combobox', { name: 'Dataset' })).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual(['Reports', 'Invoices', 'Contracts'])
    expect(datasetSelect()).toHaveValue(contracts.id)
    await screen.findByText('No documents yet.')
    expect(requestsTo(fetchStub, documentsPath(contracts.id))).toHaveLength(1)
    expect(requestsTo(fetchStub, documentsPath(reports.id))).toHaveLength(0)
  })

  it('loads the documents of the dataset the user chooses', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([reports, invoices], {
      [listOf(reports.id)]: () => Response.json([{ id: '1', filename: 'report.txt', line_count: 3, page_count: null }]),
    })

    render(<App />)
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Dataset' }), reports.id)

    expect(await findDocument('report.txt')).toBeInTheDocument()
    expect(datasetSelect()).toHaveValue(reports.id)
    expect(requestsTo(fetchStub, documentsPath(reports.id))).toHaveLength(1)
  })

  it('keeps an explicit choice when a file is uploaded, which only reloads the documents', async () => {
    const user = userEvent.setup()
    const report = { id: '1', filename: 'report.txt', line_count: 1, page_count: null }
    const fetchStub = stubPage([reports, invoices], {
      [listOf(reports.id)]: listThatChanges([], [report]),
      [`POST ${documentsPath(reports.id)}`]: () => Response.json(report, { status: 201 }),
    })

    render(<App />)
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Dataset' }), reports.id)
    await screen.findByText('No documents yet.')
    await user.upload(screen.getByLabelText('Add files'), new File(['text'], 'report.txt'))

    await findDocument('report.txt')
    expect(datasetSelect()).toHaveValue(reports.id)
    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(1)
  })

  it('shows names as plain text', async () => {
    const name = '<img src=x onerror=alert(1)>'
    stubPage([{ id: 'x', name }])

    const { container } = render(<App />)

    expect(await screen.findByRole('option', { name })).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('stays inside the page width', async () => {
    const user = userEvent.setup()
    stubPage([reports])

    render(<App />)

    expect(await screen.findByRole('combobox', { name: 'Dataset' })).toHaveStyle({
      width: '100%',
      boxSizing: 'border-box',
    })
    await user.click(newDatasetButton())
    expect(nameInput()).toHaveStyle({ width: '100%', boxSizing: 'border-box' })
  })
})

describe('creating a dataset', () => {
  it('limits the name to what the backend accepts', async () => {
    stubPage([])

    render(<App />)
    await screen.findByText(startMessage)

    expect(nameInput()).toHaveAttribute('maxlength', '100')
  })

  it.each([
    ['empty', ''],
    ['only whitespace', '   '],
  ])('shows an alert and sends nothing when the name is %s', async (_name, typed) => {
    const user = userEvent.setup()
    const fetchStub = stubPage([])

    render(<App />)
    await screen.findByText(startMessage)
    if (typed) await user.type(nameInput(), typed)
    await user.click(createButton())

    expect(screen.getByRole('alert')).toHaveTextContent('Type a name first.')
    expect(requestsTo(fetchStub, '/api/datasets', 'POST')).toHaveLength(0)
    expect(createButton()).toBeEnabled()
  })

  it('posts the trimmed name as JSON', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([], {
      'GET /api/datasets': listThatChanges([], [reports]),
      'POST /api/datasets': () => Response.json(reports, { status: 201 }),
      [listOf(reports.id)]: () => Response.json([]),
    })

    render(<App />)
    await screen.findByText(startMessage)
    await createNamed(user, '  Reports ')
    await screen.findByText('No documents yet.')

    const [[url, init = {}]] = requestsTo(fetchStub, '/api/datasets', 'POST')
    expect(url).toBe('/api/datasets')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual({ name: 'Reports' })
  })

  it('closes the form, reloads the list from the server and selects the new dataset', async () => {
    const user = userEvent.setup()
    // The reloaded list also holds a dataset this page didn't create: appending the POST response can't show it.
    const fetchStub = stubPage([reports], {
      'GET /api/datasets': listThatChanges([reports], [reports, invoices, contracts]),
      'POST /api/datasets': () => Response.json(invoices, { status: 201 }),
      [listOf(invoices.id)]: () => Response.json([]),
    })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await createNamed(user, 'Invoices')

    expect(await screen.findByRole('option', { name: 'Contracts' })).toBeInTheDocument()
    expect(datasetSelect()).toHaveValue(invoices.id)
    expect(screen.queryByRole('textbox', { name: 'New dataset name' })).not.toBeInTheDocument()
    expect(newDatasetButton()).toHaveFocus()
    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(2)
    expect(requestsTo(fetchStub, documentsPath(contracts.id))).toHaveLength(0)
  })

  it('goes straight to the new dataset, without passing through the newest old one', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const fetchStub = stubPage([reports, invoices], {
      'GET /api/datasets': vi
        .fn<Route>()
        .mockImplementationOnce(() => Response.json([reports, invoices]))
        .mockImplementation(route),
      'POST /api/datasets': () => Response.json(contracts, { status: 201 }),
      [listOf(contracts.id)]: () => Response.json([]),
    })

    render(<App />)
    const select = await screen.findByRole('combobox', { name: 'Dataset' })
    await waitFor(() => expect(requestsTo(fetchStub, documentsPath(invoices.id))).toHaveLength(1))
    await user.selectOptions(select, reports.id)
    await createNamed(user, 'Contracts')

    // The reload is still running, and the page has already moved.
    expect(await screen.findByRole('option', { name: 'Contracts' })).toBeInTheDocument()
    expect(datasetSelect()).toHaveValue(contracts.id)

    await answer(Response.json([reports, invoices, contracts]))

    expect(datasetSelect()).toHaveValue(contracts.id)
    await waitFor(() => expect(requestsTo(fetchStub, documentsPath(contracts.id))).toHaveLength(1))
    // One request for Invoices, from when it was the default. Passing through it again would make two.
    expect(requestsTo(fetchStub, documentsPath(invoices.id))).toHaveLength(1)
  })

  it('falls back to the newest dataset when the new one is gone after the reload', async () => {
    const user = userEvent.setup()
    stubPage([reports], {
      'GET /api/datasets': listThatChanges([reports], [reports, contracts]),
      'POST /api/datasets': () => Response.json(invoices, { status: 201 }),
      [listOf(invoices.id)]: () => Response.json([]),
      [listOf(contracts.id)]: () => Response.json([]),
    })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await createNamed(user, 'Invoices')

    await screen.findByRole('option', { name: 'Contracts' })
    expect(datasetSelect()).toHaveValue(contracts.id)
    expect(screen.queryByRole('option', { name: 'Invoices' })).not.toBeInTheDocument()
  })

  it('keeps the new dataset selected and shows the error when the reload fails', async () => {
    const user = userEvent.setup()
    stubPage([reports], {
      'GET /api/datasets': vi
        .fn<Route>()
        .mockResolvedValueOnce(Response.json([reports]))
        .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 })),
      'POST /api/datasets': () => Response.json(invoices, { status: 201 }),
      [listOf(invoices.id)]: () => Response.json([]),
    })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await createNamed(user, 'Invoices')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the datasets.')
    expect(datasetSelect()).toHaveValue(invoices.id)
  })

  it('clears a load error once the reload after creating works', async () => {
    const user = userEvent.setup()
    stubPage([], {
      'GET /api/datasets': vi
        .fn<Route>()
        .mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
        .mockResolvedValueOnce(Response.json([reports])),
      'POST /api/datasets': () => Response.json(reports, { status: 201 }),
      [listOf(reports.id)]: () => Response.json([]),
    })

    render(<App />)
    await screen.findByRole('alert')
    await createNamed(user, 'Reports')
    await screen.findByText('No documents yet.')

    await vi.waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(datasetSelect()).toHaveValue(reports.id)
  })

  it('aborts a slow first load when a dataset is created, so it cannot overwrite the result', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const fetchStub = stubPage([], {
      'GET /api/datasets': vi
        .fn<Route>()
        .mockImplementationOnce(route)
        .mockImplementation(() => Response.json([reports])),
      'POST /api/datasets': () => Response.json(reports, { status: 201 }),
      [listOf(reports.id)]: () => Response.json([]),
    })

    render(<App />)
    await screen.findByRole('button', { name: 'New dataset' })
    await createNamed(user, 'Reports')
    await screen.findByText('No documents yet.')

    expect(requestsTo(fetchStub, '/api/datasets')[0][1]?.signal?.aborted).toBe(true)

    // The old, empty list arrives late.
    await answer(Response.json([]))

    expect(datasetSelect()).toHaveValue(reports.id)
    expect(screen.queryByText(startMessage)).not.toBeInTheDocument()
  })

  it('shows the message from the backend and keeps the typed name and the selection', async () => {
    const user = userEvent.setup()
    const detail = 'A dataset with this name already exists.'
    const fetchStub = stubPage([reports, invoices], {
      'POST /api/datasets': () => Response.json({ detail }, { status: 409 }),
    })

    render(<App />)
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Dataset' }), reports.id)
    await createNamed(user, 'Invoices')

    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
    expect(nameInput()).toHaveValue('Invoices')
    expect(datasetSelect()).toHaveValue(reports.id)
    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(1)
    expect(createButton()).toBeEnabled()
  })

  it.each<[string, Route]>([
    ['a 502 with no JSON', () => new Response('Bad Gateway', { status: 502 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['a validation error whose detail is an array', () => Response.json({ detail: [{ msg: 'x' }] }, { status: 422 })],
  ])('shows the fallback on %s and keeps the name', async (_name, post) => {
    const user = userEvent.setup()
    stubPage([], { 'POST /api/datasets': post })

    render(<App />)
    await screen.findByText(startMessage)
    await createNamed(user, 'Reports')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not create the dataset.')
    expect(nameInput()).toHaveValue('Reports')
  })

  it('removes the alert when a later attempt is sent', async () => {
    const user = userEvent.setup()
    stubPage([], {
      'GET /api/datasets': listThatChanges([], [reports]),
      'POST /api/datasets': () => Response.json(reports, { status: 201 }),
      [listOf(reports.id)]: () => Response.json([]),
    })

    render(<App />)
    await screen.findByText(startMessage)
    await user.click(createButton())
    await screen.findByRole('alert')
    await createNamed(user, 'Reports')
    await screen.findByText('No documents yet.')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('disables the button while creating, so a second click sends nothing', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const fetchStub = stubPage([], {
      'GET /api/datasets': () => Response.json([]),
      'POST /api/datasets': route,
    })

    render(<App />)
    await screen.findByText(startMessage)
    await createNamed(user, 'Reports')

    expect(createButton()).toBeDisabled()
    await user.click(createButton())
    expect(requestsTo(fetchStub, '/api/datasets', 'POST')).toHaveLength(1)

    await answer(new Response('Bad Gateway', { status: 502 }))

    expect(createButton()).toBeEnabled()
  })

  it('stops the browser from submitting the form itself', async () => {
    stubPage([])

    render(<App />)
    await screen.findByText(startMessage)

    // fireEvent returns false when the handler called preventDefault.
    expect(fireEvent.submit(nameInput().form!)).toBe(false)
  })
})

describe('switching to another dataset', () => {
  const oldDocument = { id: 'old', filename: 'old.txt', line_count: 3, page_count: null }
  const newDocument = { id: 'new', filename: 'new.txt', line_count: 3, page_count: null }
  const answered = { status: 'answered', answer: 'The old answer.', citations: [] }

  // Starts on Invoices, the newest, which holds a document.
  function stubTwoDatasets(routes: Record<string, Route> = {}) {
    return stubPage([reports, invoices], {
      [listOf(invoices.id)]: () => Response.json([oldDocument]),
      [listOf(reports.id)]: () => Response.json([newDocument]),
      'POST /api/ask': () => Response.json(answered),
      ...routes,
    })
  }

  async function askTheOldDataset(user: UserEvent) {
    render(<App />)
    await user.click(await screen.findByRole('textbox', { name: 'Question' }))
    await user.paste('The old question')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
  }

  it('removes the old list at once, before the new one has arrived', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubTwoDatasets({ [listOf(reports.id)]: route })

    render(<App />)
    await findDocument('old.txt')
    await user.selectOptions(datasetSelect(), reports.id)

    expect(screen.queryByText('old.txt')).not.toBeInTheDocument()

    await answer(Response.json([newDocument]))

    expect(await findDocument('new.txt')).toBeInTheDocument()
    expect(screen.queryByText('old.txt')).not.toBeInTheDocument()
  })

  it('aborts the old request, so a late answer cannot show under the new dataset', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const fetchStub = stubTwoDatasets({ [listOf(invoices.id)]: route })

    render(<App />)
    await screen.findByRole('heading', { name: 'Documents' })
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')

    expect(requestsTo(fetchStub, documentsPath(invoices.id))[0][1]?.signal?.aborted).toBe(true)

    await answer(Response.json([oldDocument]))

    expect(screen.queryByText('old.txt')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('removes the typed question', async () => {
    const user = userEvent.setup()
    stubTwoDatasets()

    render(<App />)
    await user.type(await screen.findByRole('textbox', { name: 'Question' }), 'The old question')
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')

    expect(questionBox()).toHaveValue('')
  })

  it('removes the answer', async () => {
    const user = userEvent.setup()
    stubTwoDatasets()

    await askTheOldDataset(user)
    await screen.findByRole('article')
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')

    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.queryByText('The old answer.')).not.toBeInTheDocument()
    expect(questionBox()).toHaveValue('')
  })

  it('does not show an answer that arrives after the switch', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubTwoDatasets({ 'POST /api/ask': route })

    await askTheOldDataset(user)
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')

    await answer(Response.json(answered))

    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled()
  })

  it('does not bring the old state back when switching back', async () => {
    const user = userEvent.setup()
    stubTwoDatasets()

    await askTheOldDataset(user)
    await screen.findByRole('article')
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')
    await user.selectOptions(datasetSelect(), invoices.id)
    await findDocument('old.txt')

    expect(questionBox()).toHaveValue('')
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('asks the new dataset, and names it in the ask section and the answer', async () => {
    const user = userEvent.setup()
    const fetchStub = stubTwoDatasets()

    render(<App />)
    await findDocument('old.txt')
    expect(screen.getByRole('heading', { name: 'Ask a question about Invoices' })).toBeInTheDocument()
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')
    await user.type(questionBox(), 'Why?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByRole('article')

    const [[, init]] = requestsTo(fetchStub, '/api/ask', 'POST')
    expect(JSON.parse(init?.body as string)).toEqual({ dataset_id: reports.id, question: 'Why?' })
    expect(screen.getByRole('heading', { name: 'Ask a question about Reports' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Ask a question about Invoices' })).not.toBeInTheDocument()
    expect(screen.getByText('You asked about Reports: Why?')).toBeInTheDocument()
  })

  it('offers no form when the new dataset has no documents', async () => {
    const user = userEvent.setup()
    stubTwoDatasets({ [listOf(reports.id)]: () => Response.json([]) })

    render(<App />)
    await findDocument('old.txt')
    await user.selectOptions(datasetSelect(), reports.id)
    await screen.findByText('No documents yet.')

    expect(screen.getByRole('heading', { name: 'Ask a question about Reports' })).toBeInTheDocument()
    expect(screen.getByText('Upload a document to ask about it.')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Question' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ask' })).not.toBeInTheDocument()
  })

  it('removes an error from asking', async () => {
    const user = userEvent.setup()
    const detail = 'Gemini is unavailable right now. Please try again.'
    stubTwoDatasets({ 'POST /api/ask': () => Response.json({ detail }, { status: 503 }) })

    await askTheOldDataset(user)
    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(questionBox()).toHaveValue('')
  })

  it('removes an error about the old list', async () => {
    const user = userEvent.setup()
    stubTwoDatasets({ [listOf(invoices.id)]: () => new Response('Bad Gateway', { status: 502 }) })

    render(<App />)
    await screen.findByRole('alert')
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('closes an open question about deleting a document, and does not bring it back', async () => {
    const user = userEvent.setup()
    const fetchStub = stubTwoDatasets()

    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Delete old.txt' }))
    expect(screen.getByRole('group', { name: 'Delete old.txt?' })).toBeInTheDocument()
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')

    expect(deleteQuestion()).not.toBeInTheDocument()

    await user.selectOptions(datasetSelect(), invoices.id)
    await screen.findByRole('button', { name: 'Delete old.txt' })

    expect(deleteQuestion()).not.toBeInTheDocument()
    expect(fetchStub.mock.calls.filter((call) => call[1]?.method === 'DELETE')).toHaveLength(0)
  })

  it('uploads into the new dataset', async () => {
    const user = userEvent.setup()
    const fetchStub = stubTwoDatasets({
      [`POST ${documentsPath(reports.id)}`]: () => Response.json(newDocument, { status: 201 }),
    })

    render(<App />)
    await findDocument('old.txt')
    await user.selectOptions(datasetSelect(), reports.id)
    await findDocument('new.txt')
    await user.upload(screen.getByLabelText('Add files'), new File(['text'], 'another.txt'))

    await vi.waitFor(() => expect(requestsTo(fetchStub, documentsPath(reports.id), 'POST')).toHaveLength(1))
    expect(requestsTo(fetchStub, documentsPath(invoices.id), 'POST')).toHaveLength(0)
  })
})

describe('during an upload run', () => {
  const uploaded = () =>
    Response.json({ id: '1', filename: 'a.txt', line_count: 1, page_count: null }, { status: 201 })

  // Choosing the files starts the run.
  async function startRun(user: UserEvent, ...filenames: string[]) {
    await user.upload(
      await screen.findByLabelText('Add files'),
      filenames.map((filename) => new File(['text'], filename)),
    )
  }

  function postsAnsweredByTheTest() {
    const pending: ((response: Response) => void)[] = []
    const route: Route = () => new Promise((resolve) => pending.push(resolve))
    return { route, answer: (position: number, response: Response) => act(async () => pending[position](response)) }
  }

  it('disables the select and the New dataset and Delete dataset buttons until the run ends', async () => {
    const user = userEvent.setup()
    const { route, answer } = postsAnsweredByTheTest()
    stubPage([reports, invoices], { [`POST ${documentsPath(invoices.id)}`]: route })

    render(<App />)
    await startRun(user, 'a.txt', 'b.txt')

    expect(datasetSelect()).toBeDisabled()
    expect(newDatasetButton()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Delete dataset' })).toBeDisabled()

    await answer(0, uploaded())

    expect(datasetSelect()).toBeDisabled()
    expect(newDatasetButton()).toBeDisabled()

    await answer(1, new Response('Bad Gateway', { status: 502 }))

    expect(datasetSelect()).toBeEnabled()
    expect(newDatasetButton()).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Delete dataset' })).toBeEnabled()
  })

  it('sends every file to the dataset selected when the run started', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([reports, invoices], { [`POST ${documentsPath(reports.id)}`]: uploaded })

    render(<App />)
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Dataset' }), reports.id)
    await screen.findByText('No documents yet.')
    await startRun(user, 'a.txt', 'b.txt')

    await vi.waitFor(() => expect(newDatasetButton()).toBeEnabled())
    expect(requestsTo(fetchStub, documentsPath(reports.id), 'POST')).toHaveLength(2)
    expect(requestsTo(fetchStub, documentsPath(invoices.id), 'POST')).toHaveLength(0)
  })

  it('keeps the rows after the run, until the user moves to another dataset', async () => {
    const user = userEvent.setup()
    stubPage([reports, invoices], { [`POST ${documentsPath(invoices.id)}`]: uploaded })

    render(<App />)
    await startRun(user, 'a.txt')
    expect(await screen.findByText('Uploaded')).toBeInTheDocument()

    await user.selectOptions(datasetSelect(), reports.id)

    expect(screen.queryByText('Uploaded')).not.toBeInTheDocument()
  })

  it('lets the user ask about the files uploaded so far while the run goes on', async () => {
    const user = userEvent.setup()
    const { route, answer } = postsAnsweredByTheTest()
    stubPage([reports], {
      [listOf(reports.id)]: listThatChanges([], [{ id: '1', filename: 'a.txt', line_count: 1, page_count: null }]),
      [`POST ${documentsPath(reports.id)}`]: route,
    })

    render(<App />)
    await startRun(user, 'a.txt', 'b.txt')
    await answer(0, uploaded())

    expect(await screen.findByRole('textbox', { name: 'Question' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled()
    expect(datasetSelect()).toBeDisabled()
  })
})

describe('while a dataset is being created', () => {
  it('holds back the select and the upload, so the new dataset cannot pull the page away from a run', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const fetchStub = stubPage([reports], {
      'GET /api/datasets': listThatChanges([reports], [reports, invoices]),
      'POST /api/datasets': route,
      [listOf(invoices.id)]: () => Response.json([]),
    })

    render(<App />)
    const fileInput = await screen.findByLabelText('Add files')
    await createNamed(user, 'Invoices')

    expect(datasetSelect()).toBeDisabled()
    expect(createButton()).toBeDisabled()
    expect(newDatasetButton()).toBeDisabled()
    expect(fileInput).toBeDisabled()

    await answer(Response.json(invoices, { status: 201 }))

    expect(datasetSelect()).toBeEnabled()
    expect(datasetSelect()).toHaveValue(invoices.id)
    expect(screen.getByLabelText('Add files')).toBeEnabled()
    expect(requestsTo(fetchStub, documentsPath(invoices.id), 'POST')).toHaveLength(0)
  })

  it('lets go of them when creating fails', async () => {
    const user = userEvent.setup()
    stubPage([reports], {
      'POST /api/datasets': () => Response.json({ detail: 'A dataset with this name already exists.' }, { status: 409 }),
    })

    render(<App />)
    await screen.findByLabelText('Add files')
    await createNamed(user, 'Reports')
    await screen.findByRole('alert')

    expect(datasetSelect()).toBeEnabled()
    expect(createButton()).toBeEnabled()
    expect(screen.getByLabelText('Add files')).toBeEnabled()
  })
})

describe('deleting a dataset', () => {
  const deleteDatasetButton = () => screen.getByRole('button', { name: 'Delete dataset' })
  const questionFor = (name: string) =>
    screen.queryByRole('group', { name: `Delete ${name} and all its documents? This can't be undone.` })
  const confirmButton = () => within(deleteQuestion()!).getByRole('button', { name: 'Delete' })
  const cancelButton = () => within(deleteQuestion()!).getByRole('button', { name: 'Cancel' })
  const deleted: Route = () => new Response(null, { status: 204 })
  const deletesOf = (fetchStub: ReturnType<typeof stubRoutes>) =>
    fetchStub.mock.calls.filter((call) => call[1]?.method === 'DELETE').map(([url]) => url)

  async function deleteSelected(user: UserEvent) {
    await user.click(deleteDatasetButton())
    await user.click(confirmButton())
  }

  it('offers a Delete dataset button beside the select, and none before a dataset exists', async () => {
    stubPage([reports])

    const { unmount } = render(<App />)

    const button = await screen.findByRole('button', { name: 'Delete dataset' })
    expect(button.closest('.dataset-choice')).toBe(datasetSelect().closest('.dataset-choice'))
    unmount()

    stubPage([])
    render(<App />)
    await screen.findByText(startMessage)

    expect(screen.queryByRole('button', { name: 'Delete dataset' })).not.toBeInTheDocument()
  })

  it('asks first, naming the selected dataset, and sends nothing until the user confirms', async () => {
    const user = userEvent.setup()
    const confirmDialog = vi.spyOn(window, 'confirm')
    const fetchStub = stubPage([reports, invoices])

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await user.click(deleteDatasetButton())

    expect(questionFor('Invoices')).toBeInTheDocument()
    expect(screen.getByText("Delete Invoices and all its documents? This can't be undone.")).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(confirmDialog).not.toHaveBeenCalled()
    expect(deletesOf(fetchStub)).toEqual([])
    confirmDialog.mockRestore()
  })

  it('moves the focus to the confirm button, and back to Delete dataset after Cancel, sending nothing', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([reports])

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await user.click(deleteDatasetButton())

    expect(confirmButton()).toHaveFocus()

    await user.click(cancelButton())

    expect(questionFor('Reports')).not.toBeInTheDocument()
    expect(deleteDatasetButton()).toHaveFocus()
    expect(datasetSelect()).toHaveValue(reports.id)
    expect(deletesOf(fetchStub)).toEqual([])
  })

  it('deletes the selected dataset, reloads the list and falls back to the newest remaining one', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([reports, invoices, contracts], {
      'GET /api/datasets': listThatChanges([reports, invoices, contracts], [invoices, contracts]),
      'DELETE /api/datasets/r': deleted,
    })

    render(<App />)
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Dataset' }), reports.id)
    await deleteSelected(user)

    await vi.waitFor(() => expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(2))
    expect(deletesOf(fetchStub)).toEqual(['/api/datasets/r'])
    expect(screen.queryByRole('option', { name: 'Reports' })).not.toBeInTheDocument()
    expect(datasetSelect()).toHaveValue(contracts.id)
    // Once when Contracts was the default at the start, and again now that the page has fallen back to it.
    await waitFor(() => expect(requestsTo(fetchStub, documentsPath(contracts.id))).toHaveLength(2))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(deleteQuestion()).not.toBeInTheDocument()
  })

  it('moves to the newest remaining dataset at once, without waiting for the reload', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubPage([reports, invoices], {
      'GET /api/datasets': vi
        .fn<Route>()
        .mockImplementationOnce(() => Response.json([reports, invoices]))
        .mockImplementation(route),
      'DELETE /api/datasets/i': deleted,
    })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await deleteSelected(user)

    await vi.waitFor(() => expect(datasetSelect()).toHaveValue(reports.id))
    expect(screen.queryByRole('option', { name: 'Invoices' })).not.toBeInTheDocument()
    expect(datasetSelect()).toBeEnabled()

    await answer(Response.json([reports]))

    expect(datasetSelect()).toHaveValue(reports.id)
  })

  it('shows the start prompt again once the last dataset is deleted', async () => {
    const user = userEvent.setup()
    stubPage([reports], {
      'GET /api/datasets': listThatChanges([reports], []),
      'DELETE /api/datasets/r': deleted,
    })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await deleteSelected(user)

    expect(await screen.findByText(startMessage)).toBeInTheDocument()
    expectNoDocumentsOrAsk()
    expect(screen.queryByRole('combobox', { name: 'Dataset' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete dataset' })).not.toBeInTheDocument()
    expect(createButton()).toBeEnabled()
  })

  it('treats a 404 as done, since the dataset is gone either way', async () => {
    const user = userEvent.setup()
    stubPage([reports, invoices], {
      'GET /api/datasets': listThatChanges([reports, invoices], [reports]),
      'DELETE /api/datasets/i': () => Response.json({ detail: 'Dataset not found.' }, { status: 404 }),
    })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await deleteSelected(user)

    await vi.waitFor(() => expect(datasetSelect()).toHaveValue(reports.id))
    expect(screen.queryByRole('option', { name: 'Invoices' })).not.toBeInTheDocument()
    expect(screen.queryByText('Dataset not found.')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the dataset and shows the message from the backend when deleting fails', async () => {
    const user = userEvent.setup()
    const detail = 'The database is unavailable right now. Please try again.'
    const fetchStub = stubPage([reports, invoices], {
      'DELETE /api/datasets/i': () => Response.json({ detail }, { status: 503 }),
    })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await deleteSelected(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
    expect(datasetSelect()).toHaveValue(invoices.id)
    expect(screen.getByRole('option', { name: 'Invoices' })).toBeInTheDocument()
    expect(deleteQuestion()).not.toBeInTheDocument()
    expect(deleteDatasetButton()).toHaveFocus()
    // The page lets go again.
    expect(datasetSelect()).toBeEnabled()
    expect(newDatasetButton()).toBeEnabled()
    expect(screen.getByLabelText('Add files')).toBeEnabled()
    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(1)
  })

  it.each<[string, Route]>([
    ['a 502 with no JSON', () => new Response('Bad Gateway', { status: 502 })],
    ['a dropped connection', () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('shows the fallback on %s', async (_name, route) => {
    const user = userEvent.setup()
    stubPage([reports], { 'DELETE /api/datasets/r': route })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await deleteSelected(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not delete the dataset.')
    expect(datasetSelect()).toHaveValue(reports.id)
  })

  it('makes the whole page busy while the request runs', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubPage([reports, invoices], {
      [listOf(invoices.id)]: () => Response.json([{ id: '1', filename: 'a.txt', line_count: 1, page_count: null }]),
      'GET /api/datasets': listThatChanges([reports, invoices], [reports]),
      'DELETE /api/datasets/i': route,
    })

    render(<App />)
    const fileInput = await screen.findByLabelText('Add files')
    await screen.findByRole('button', { name: 'Delete a.txt' })
    await deleteSelected(user)

    expect(confirmButton()).toBeDisabled()
    expect(cancelButton()).toBeDisabled()
    expect(datasetSelect()).toBeDisabled()
    expect(newDatasetButton()).toBeDisabled()
    expect(fileInput).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Delete a.txt' })).toBeDisabled()

    await answer(new Response(null, { status: 204 }))

    expect(datasetSelect()).toHaveValue(reports.id)
    expect(datasetSelect()).toBeEnabled()
    expect(newDatasetButton()).toBeEnabled()
  })

  it('cannot be deleted during an upload run', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubPage([reports], { [`POST ${documentsPath(reports.id)}`]: route })

    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Delete dataset' }))
    await user.upload(screen.getByLabelText('Add files'), new File(['text'], 'a.txt'))

    expect(confirmButton()).toBeDisabled()
    expect(cancelButton()).toBeEnabled()
    await user.click(cancelButton())
    expect(deleteDatasetButton()).toBeDisabled()

    await answer(new Response('Bad Gateway', { status: 502 }))

    expect(deleteDatasetButton()).toBeEnabled()
  })

  it('cannot be deleted while a dataset is being created', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubPage([reports], { 'POST /api/datasets': route })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await createNamed(user, 'Invoices')

    expect(deleteDatasetButton()).toBeDisabled()

    await answer(Response.json({ detail: 'A dataset with this name already exists.' }, { status: 409 }))

    expect(deleteDatasetButton()).toBeEnabled()
  })

  it('closes an open question when another dataset is chosen, so it cannot delete the wrong one', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([reports, invoices])

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await user.click(deleteDatasetButton())
    await user.selectOptions(datasetSelect(), reports.id)

    expect(deleteQuestion()).not.toBeInTheDocument()
    expect(deleteDatasetButton()).toBeEnabled()
    expect(deletesOf(fetchStub)).toEqual([])
  })

  it('closes an open question when a new dataset is created and selected', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([reports], {
      'GET /api/datasets': listThatChanges([reports], [reports, invoices]),
      'POST /api/datasets': () => Response.json(invoices, { status: 201 }),
    })

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await user.click(deleteDatasetButton())
    await createNamed(user, 'Invoices')
    await vi.waitFor(() => expect(datasetSelect()).toHaveValue(invoices.id))

    expect(questionFor('Invoices')).not.toBeInTheDocument()
    expect(questionFor('Reports')).not.toBeInTheDocument()
    expect(deletesOf(fetchStub)).toEqual([])
  })

  it('shows the name as plain text in the question', async () => {
    const user = userEvent.setup()
    const name = '<img src=x onerror=alert(1)>'
    stubPage([{ id: 'x', name }])

    const { container } = render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await user.click(deleteDatasetButton())

    expect(questionFor(name)).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('wraps a long name in the question, and cuts it short in the card of the select', async () => {
    const user = userEvent.setup()
    const name = 'x'.repeat(100)
    stubPage([{ id: 'x', name }])

    render(<App />)
    await screen.findByRole('combobox', { name: 'Dataset' })
    await user.click(deleteDatasetButton())

    expect(questionFor(name)).toHaveStyle({ overflowWrap: 'anywhere', flexWrap: 'wrap', minWidth: '0px' })
    expect(questionFor(name)?.parentElement).toHaveStyle({ flexWrap: 'wrap' })
    const shownName = screen.getByText(name, { selector: '.switcher-name' })
    expect(shownName).toHaveStyle({ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' })
    expect(shownName.parentElement).toHaveStyle({ minWidth: '0px' })
  })
})
