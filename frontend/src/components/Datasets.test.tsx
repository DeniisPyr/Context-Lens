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
const questionBox = () => screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Question' })
const startMessage = 'Create a dataset to get started.'

const requestsTo = (fetchStub: ReturnType<typeof stubRoutes>, url: string, method = 'GET') =>
  fetchStub.mock.calls.filter((call) => call[0] === url && (call[1]?.method ?? 'GET') === method)

async function createNamed(user: UserEvent, name: string) {
  await user.clear(nameInput())
  await user.type(nameInput(), name)
  await user.click(createButton())
}

function expectNoDocumentsOrAsk() {
  expect(screen.queryByRole('heading', { name: 'Documents' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Ask a question' })).not.toBeInTheDocument()
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
  })

  it('says nothing while the first load is running', () => {
    stubPage([], { 'GET /api/datasets': rejectsOnAbort })

    render(<App />)

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

  it('aborts the first load on unmount', () => {
    const fetchStub = stubPage([], { 'GET /api/datasets': rejectsOnAbort })

    const { unmount } = render(<App />)
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
    expect(screen.getByRole('heading', { name: 'Ask a question' })).toBeInTheDocument()
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
      [listOf(reports.id)]: () => Response.json([{ id: '1', filename: 'report.txt', line_count: 3 }]),
    })

    render(<App />)
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Dataset' }), reports.id)

    expect(await screen.findByRole('option', { name: 'report.txt' })).toBeInTheDocument()
    expect(datasetSelect()).toHaveValue(reports.id)
    expect(requestsTo(fetchStub, documentsPath(reports.id))).toHaveLength(1)
  })

  it('keeps an explicit choice when a file is uploaded, which only reloads the documents', async () => {
    const user = userEvent.setup()
    const report = { id: '1', filename: 'report.txt', line_count: 1 }
    const fetchStub = stubPage([reports, invoices], {
      [listOf(reports.id)]: listThatChanges([], [report]),
      [`POST ${documentsPath(reports.id)}`]: () => Response.json(report, { status: 201 }),
    })

    render(<App />)
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Dataset' }), reports.id)
    await screen.findByText('No documents yet.')
    await user.upload(screen.getByLabelText(/^Choose/), new File(['text'], 'report.txt'))
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    await screen.findByRole('option', { name: 'report.txt' })
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
    stubPage([reports])

    render(<App />)

    expect(await screen.findByRole('combobox', { name: 'Dataset' })).toHaveStyle({
      width: '100%',
      boxSizing: 'border-box',
    })
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

  it('clears the input, reloads the list from the server and selects the new dataset', async () => {
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
    expect(nameInput()).toHaveValue('')
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
  const oldDocument = { id: 'old', filename: 'old.txt', line_count: 3 }
  const newDocument = { id: 'new', filename: 'new.txt', line_count: 3 }
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

  async function askAboutTheOldDocument(user: UserEvent) {
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
    await screen.findByRole('option', { name: 'old.txt' })
    await user.selectOptions(datasetSelect(), reports.id)

    expect(screen.queryByText('old.txt')).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'old.txt' })).not.toBeInTheDocument()

    await answer(Response.json([newDocument]))

    expect(screen.getByRole('option', { name: 'new.txt' })).toBeInTheDocument()
    expect(screen.queryByText('old.txt')).not.toBeInTheDocument()
  })

  it('aborts the old request, so a late answer cannot show under the new dataset', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const fetchStub = stubTwoDatasets({ [listOf(invoices.id)]: route })

    render(<App />)
    await screen.findByRole('heading', { name: 'Documents' })
    await user.selectOptions(datasetSelect(), reports.id)
    await screen.findByRole('option', { name: 'new.txt' })

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
    await screen.findByRole('option', { name: 'new.txt' })

    expect(questionBox()).toHaveValue('')
  })

  it('removes the answer', async () => {
    const user = userEvent.setup()
    stubTwoDatasets()

    await askAboutTheOldDocument(user)
    await screen.findByRole('article')
    await user.selectOptions(datasetSelect(), reports.id)
    await screen.findByRole('option', { name: 'new.txt' })

    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.queryByText('The old answer.')).not.toBeInTheDocument()
    expect(questionBox()).toHaveValue('')
  })

  it('does not show an answer that arrives after the switch', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubTwoDatasets({ 'POST /api/ask': route })

    await askAboutTheOldDocument(user)
    await user.selectOptions(datasetSelect(), reports.id)
    await screen.findByRole('option', { name: 'new.txt' })

    await answer(Response.json(answered))

    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled()
  })

  it('does not bring the old state back when switching back', async () => {
    const user = userEvent.setup()
    stubTwoDatasets()

    await askAboutTheOldDocument(user)
    await screen.findByRole('article')
    await user.selectOptions(datasetSelect(), reports.id)
    await screen.findByRole('option', { name: 'new.txt' })
    await user.selectOptions(datasetSelect(), invoices.id)
    await screen.findByRole('option', { name: 'old.txt' })

    expect(questionBox()).toHaveValue('')
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('asks about the documents of the new dataset', async () => {
    const user = userEvent.setup()
    const fetchStub = stubTwoDatasets()

    render(<App />)
    await screen.findByRole('option', { name: 'old.txt' })
    await user.selectOptions(datasetSelect(), reports.id)
    await screen.findByRole('option', { name: 'new.txt' })
    await user.type(questionBox(), 'Why?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    await screen.findByRole('article')

    const [[, init]] = requestsTo(fetchStub, '/api/ask', 'POST')
    expect(JSON.parse(init?.body as string)).toEqual({ document_id: newDocument.id, question: 'Why?' })
  })

  it('removes an error about the old list', async () => {
    const user = userEvent.setup()
    stubTwoDatasets({ [listOf(invoices.id)]: () => new Response('Bad Gateway', { status: 502 }) })

    render(<App />)
    await screen.findByRole('alert')
    await user.selectOptions(datasetSelect(), reports.id)
    await screen.findByRole('option', { name: 'new.txt' })

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('closes an open question about deleting a document, and does not bring it back', async () => {
    const user = userEvent.setup()
    const fetchStub = stubTwoDatasets()

    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Delete old.txt' }))
    expect(screen.getByRole('group', { name: 'Delete old.txt?' })).toBeInTheDocument()
    await user.selectOptions(datasetSelect(), reports.id)
    await screen.findByRole('option', { name: 'new.txt' })

    expect(screen.queryByRole('group')).not.toBeInTheDocument()

    await user.selectOptions(datasetSelect(), invoices.id)
    await screen.findByRole('button', { name: 'Delete old.txt' })

    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    expect(fetchStub.mock.calls.filter((call) => call[1]?.method === 'DELETE')).toHaveLength(0)
  })

  it('uploads into the new dataset', async () => {
    const user = userEvent.setup()
    const fetchStub = stubTwoDatasets({
      [`POST ${documentsPath(reports.id)}`]: () => Response.json(newDocument, { status: 201 }),
    })

    render(<App />)
    await screen.findByRole('option', { name: 'old.txt' })
    await user.selectOptions(datasetSelect(), reports.id)
    await screen.findByRole('option', { name: 'new.txt' })
    await user.upload(screen.getByLabelText(/^Choose/), new File(['text'], 'another.txt'))
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    await vi.waitFor(() => expect(requestsTo(fetchStub, documentsPath(reports.id), 'POST')).toHaveLength(1))
    expect(requestsTo(fetchStub, documentsPath(invoices.id), 'POST')).toHaveLength(0)
  })
})

describe('during an upload run', () => {
  const uploaded = () => Response.json({ id: '1', filename: 'a.txt', line_count: 1 }, { status: 201 })

  async function startRun(user: UserEvent, ...filenames: string[]) {
    await user.upload(
      await screen.findByLabelText(/^Choose/),
      filenames.map((filename) => new File(['text'], filename)),
    )
    await user.click(screen.getByRole('button', { name: 'Upload' }))
  }

  function postsAnsweredByTheTest() {
    const pending: ((response: Response) => void)[] = []
    const route: Route = () => new Promise((resolve) => pending.push(resolve))
    return { route, answer: (position: number, response: Response) => act(async () => pending[position](response)) }
  }

  it('disables the select and the Create button until the run ends', async () => {
    const user = userEvent.setup()
    const { route, answer } = postsAnsweredByTheTest()
    stubPage([reports, invoices], { [`POST ${documentsPath(invoices.id)}`]: route })

    render(<App />)
    await startRun(user, 'a.txt', 'b.txt')

    expect(datasetSelect()).toBeDisabled()
    expect(createButton()).toBeDisabled()

    await answer(0, uploaded())

    expect(datasetSelect()).toBeDisabled()
    expect(createButton()).toBeDisabled()

    await answer(1, new Response('Bad Gateway', { status: 502 }))

    expect(datasetSelect()).toBeEnabled()
    expect(createButton()).toBeEnabled()
  })

  it('sends every file to the dataset selected when the run started', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage([reports, invoices], { [`POST ${documentsPath(reports.id)}`]: uploaded })

    render(<App />)
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Dataset' }), reports.id)
    await screen.findByText('No documents yet.')
    await startRun(user, 'a.txt', 'b.txt')

    await vi.waitFor(() => expect(createButton()).toBeEnabled())
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

  it('offers the files uploaded so far to Ask while the run goes on', async () => {
    const user = userEvent.setup()
    const { route, answer } = postsAnsweredByTheTest()
    stubPage([reports], {
      [listOf(reports.id)]: listThatChanges([], [{ id: '1', filename: 'a.txt', line_count: 1 }]),
      [`POST ${documentsPath(reports.id)}`]: route,
    })

    render(<App />)
    await startRun(user, 'a.txt', 'b.txt')
    await answer(0, uploaded())

    expect(await screen.findByRole('option', { name: 'a.txt' })).toBeInTheDocument()
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
    const fileInput = await screen.findByLabelText(/^Choose/)
    await createNamed(user, 'Invoices')

    expect(datasetSelect()).toBeDisabled()
    expect(createButton()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled()
    expect(fileInput).toBeDisabled()

    await answer(Response.json(invoices, { status: 201 }))

    expect(datasetSelect()).toBeEnabled()
    expect(datasetSelect()).toHaveValue(invoices.id)
    expect(screen.getByRole('button', { name: 'Upload' })).toBeEnabled()
    expect(requestsTo(fetchStub, documentsPath(invoices.id), 'POST')).toHaveLength(0)
  })

  it('lets go of them when creating fails', async () => {
    const user = userEvent.setup()
    stubPage([reports], {
      'POST /api/datasets': () => Response.json({ detail: 'A dataset with this name already exists.' }, { status: 409 }),
    })

    render(<App />)
    await screen.findByLabelText(/^Choose/)
    await createNamed(user, 'Reports')
    await screen.findByRole('alert')

    expect(datasetSelect()).toBeEnabled()
    expect(createButton()).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Upload' })).toBeEnabled()
  })
})
