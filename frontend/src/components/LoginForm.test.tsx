import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'

// These tests render the whole page, so the session reaches App through the real hook and only fetch is faked.

type Route = (init?: RequestInit) => Response | Promise<Response>

function stubRoutes(routes: Record<string, Route>) {
  const fetchStub = vi.fn<typeof fetch>(async (url, init) => routes[`${init?.method ?? 'GET'} ${url}`](init))
  vi.stubGlobal('fetch', fetchStub)
  return fetchStub
}

type Session = { login_required: boolean; logged_in: boolean }

const noLogin: Session = { login_required: false, logged_in: true }
const loggedOut: Session = { login_required: true, logged_in: false }
const loggedIn: Session = { login_required: true, logged_in: true }

const reports = { id: 'r', name: 'Reports' }
const invoices = { id: 'i', name: 'Invoices' }

const noContent = () => new Response(null, { status: 204 })
const wrongPassword: Route = () => Response.json({ detail: 'Wrong password.' }, { status: 401 })
// What every other route answers once the session has ended.
const logInFirst = () => Response.json({ detail: 'Log in first.' }, { status: 401 })
const sessionEnded = 'Your session has ended. Log in again.'

// The page with this session and an API that answers: the password is right, logging out works, and there are two
// datasets, Reports and Invoices, both empty.
function stubPage(session: Session, routes: Record<string, Route> = {}) {
  return stubRoutes({
    'GET /api/health': () => Response.json({ status: 'ok' }),
    'GET /api/session': () => Response.json(session),
    'POST /api/session': noContent,
    'DELETE /api/session': noContent,
    'GET /api/datasets': () => Response.json([reports, invoices]),
    'GET /api/datasets/r/documents': () => Response.json([]),
    'GET /api/datasets/i/documents': () => Response.json([]),
    ...routes,
  })
}

// Like the real fetch: never answers by itself, and rejects once aborted.
const rejectsOnAbort: Route = (init) =>
  new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })

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

const requestsTo = (fetchStub: ReturnType<typeof stubRoutes>, url: string, method = 'GET') =>
  fetchStub.mock.calls.filter((call) => call[0] === url && (call[1]?.method ?? 'GET') === method)

const passwordInput = () => screen.getByLabelText<HTMLInputElement>('Password')
const logInButton = () => screen.getByRole('button', { name: 'Log in' })
const logOutButton = () => screen.queryByRole('button', { name: 'Log out' })
const datasetSelect = () => screen.getByRole<HTMLSelectElement>('combobox', { name: 'Dataset' })
const nameInput = () => screen.getByRole<HTMLInputElement>('textbox', { name: 'New dataset name' })
const newDatasetButton = () => screen.getByRole('button', { name: 'New dataset' })

const findLoginForm = () => screen.findByLabelText<HTMLInputElement>('Password')
// The app is there once the newest dataset's documents have loaded.
async function findApp() {
  await screen.findByText('No documents yet.')
}

async function logInWith(user: UserEvent, password: string) {
  await user.type(passwordInput(), password)
  await user.click(logInButton())
}

// The form to create a dataset opens from the New dataset button, since there are datasets already.
async function createNamed(user: UserEvent, name: string) {
  await user.click(newDatasetButton())
  await user.type(nameInput(), name)
  await user.click(screen.getByRole('button', { name: 'Create' }))
}

function expectNoLoginForm() {
  expect(screen.queryByRole('heading', { name: 'Log in' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Log in' })).not.toBeInTheDocument()
}

function expectNoApp() {
  expect(screen.queryByRole('heading', { name: 'Questions in this session' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Documents' })).not.toBeInTheDocument()
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('when no login is required', () => {
  it('shows the app with no login form and no Log out button', async () => {
    const fetchStub = stubPage(noLogin)

    render(<App />)
    await findApp()

    expectNoLoginForm()
    expect(logOutButton()).not.toBeInTheDocument()
    expect(requestsTo(fetchStub, '/api/session', 'POST')).toHaveLength(0)
  })
})

describe('while the session is being checked', () => {
  it('shows only the title, the intro and the API status', async () => {
    const fetchStub = stubPage(loggedIn, { 'GET /api/session': rejectsOnAbort })

    render(<App />)
    await screen.findByText('API online')

    expect(screen.getByRole('heading', { name: 'Context-Lens' })).toBeInTheDocument()
    expect(screen.getByText('Ask questions about your documents and get answers you can check.')).toBeInTheDocument()
    expectNoLoginForm()
    expectNoApp()
    expect(logOutButton()).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(0)
  })

  it('aborts the check on unmount', () => {
    const fetchStub = stubPage(loggedIn, { 'GET /api/session': rejectsOnAbort })

    const { unmount } = render(<App />)
    const signal = requestsTo(fetchStub, '/api/session')[0][1]?.signal
    expect(signal?.aborted).toBe(false)

    unmount()

    expect(signal?.aborted).toBe(true)
  })

  it('does not show an error when strict mode cancels the first check', async () => {
    const fetchStub = stubPage(loggedIn, { 'GET /api/session': rejectsOnAbort })

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
    await act(async () => {})

    expect(requestsTo(fetchStub, '/api/session')).toHaveLength(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('when the session check fails', () => {
  it('shows the error and a way to try again, but neither the login form nor the app', async () => {
    const fetchStub = stubPage(loggedOut, { 'GET /api/session': () => new Response('Bad Gateway', { status: 502 }) })

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent("Could not check whether you're logged in.")
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
    expectNoLoginForm()
    expectNoApp()
    expect(logOutButton()).not.toBeInTheDocument()
    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(0)
  })

  it('shows the message from the backend when there is one', async () => {
    const detail = 'The database is unavailable right now. Please try again.'
    stubPage(loggedOut, { 'GET /api/session': () => Response.json({ detail }, { status: 503 }) })

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent(detail)
  })

  it('checks again on Try again, showing nothing meanwhile, and then the login form', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const fetchStub = stubPage(loggedOut, {
      'GET /api/session': vi
        .fn<Route>()
        .mockImplementationOnce(() => new Response('Bad Gateway', { status: 502 }))
        .mockImplementation(route),
    })

    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'Try again' }))

    expect(requestsTo(fetchStub, '/api/session')).toHaveLength(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
    expectNoLoginForm()

    await answer(Response.json(loggedOut))

    expect(await findLoginForm()).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })
})

describe('the login form', () => {
  it('shows instead of the app when a login is required, and loads nothing behind it', async () => {
    const fetchStub = stubPage(loggedOut)

    render(<App />)

    expect(await findLoginForm()).toHaveAttribute('type', 'password')
    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(logInButton()).toBeEnabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expectNoApp()
    expect(logOutButton()).not.toBeInTheDocument()
    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(0)
  })

  it('allows the same password length as the backend, and lets a password manager fill it in', async () => {
    stubPage(loggedOut)

    render(<App />)

    const input = await findLoginForm()
    expect(input).toHaveAttribute('maxlength', '1000')
    expect(input).toHaveAttribute('autocomplete', 'current-password')
  })

  it('asks for the password instead of sending an empty one', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage(loggedOut)

    render(<App />)
    await findLoginForm()
    await user.click(logInButton())

    expect(screen.getByRole('alert')).toHaveTextContent('Type the password first.')
    expect(requestsTo(fetchStub, '/api/session', 'POST')).toHaveLength(0)
    expectNoApp()
  })

  it('sends the password as typed, spaces and all', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage(loggedOut)

    render(<App />)
    await findLoginForm()
    await logInWith(user, ' my secret ')
    await findApp()

    const [[, init]] = requestsTo(fetchStub, '/api/session', 'POST')
    expect(JSON.parse(init?.body as string)).toEqual({ password: ' my secret ' })
  })

  it('shows the message for a wrong password and keeps the form and what was typed', async () => {
    const user = userEvent.setup()
    stubPage(loggedOut, { 'POST /api/session': wrongPassword })

    render(<App />)
    await findLoginForm()
    await logInWith(user, 'guess')

    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong password.')
    expect(passwordInput()).toHaveValue('guess')
    expect(logInButton()).toBeEnabled()
    expectNoApp()
  })

  it('falls back when logging in fails without a message', async () => {
    const user = userEvent.setup()
    stubPage(loggedOut, { 'POST /api/session': () => new Response('Bad Gateway', { status: 502 }) })

    render(<App />)
    await findLoginForm()
    await logInWith(user, 'secret')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not log in.')
    expectNoApp()
  })

  it('says Logging in… and takes no second click while the password is on its way', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const fetchStub = stubPage(loggedOut, { 'POST /api/session': route })

    render(<App />)
    await findLoginForm()
    await logInWith(user, 'secret')

    const waiting = screen.getByRole('button', { name: 'Logging in…' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(requestsTo(fetchStub, '/api/session', 'POST')).toHaveLength(1)

    await answer(noContent())

    await findApp()
  })

  it('clears the last error while the next try is on its way', async () => {
    const user = userEvent.setup()
    const { route } = waitingRoute()
    stubPage(loggedOut, {
      'POST /api/session': vi.fn<Route>().mockImplementationOnce(wrongPassword).mockImplementation(route),
    })

    render(<App />)
    await findLoginForm()
    await logInWith(user, 'guess')
    await screen.findByRole('alert')
    await user.click(logInButton())

    expect(screen.getByRole('button', { name: 'Logging in…' })).toBeDisabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the app and loads the datasets once the password is right', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage(loggedOut)

    render(<App />)
    await findLoginForm()
    await logInWith(user, 'secret')
    await findApp()

    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(1)
    expect(datasetSelect()).toHaveValue(invoices.id)
    expectNoLoginForm()
    expect(logOutButton()).toBeEnabled()
  })
})

describe('the Log out button', () => {
  it('shows when a login is required, once logged in', async () => {
    stubPage(loggedIn)

    render(<App />)
    await findApp()

    expect(logOutButton()).toBeEnabled()
    expectNoLoginForm()
  })

  it('logs out and shows the login form again, empty', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage(loggedIn)

    render(<App />)
    await findApp()
    await user.click(logOutButton()!)

    expect(await findLoginForm()).toHaveValue('')
    expect(requestsTo(fetchStub, '/api/session', 'DELETE')).toHaveLength(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(logOutButton()).not.toBeInTheDocument()
    expectNoApp()
  })

  it('says Logging out… and takes no second click while waiting', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    const fetchStub = stubPage(loggedIn, { 'DELETE /api/session': route })

    render(<App />)
    await findApp()
    await user.click(logOutButton()!)

    const waiting = screen.getByRole('button', { name: 'Logging out…' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(requestsTo(fetchStub, '/api/session', 'DELETE')).toHaveLength(1)

    await answer(noContent())

    expect(await findLoginForm()).toBeInTheDocument()
  })

  it('keeps the app and says so when logging out fails, since the session goes on', async () => {
    const user = userEvent.setup()
    stubPage(loggedIn, { 'DELETE /api/session': () => new Response('Bad Gateway', { status: 502 }) })

    render(<App />)
    await findApp()
    await user.click(logOutButton()!)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not log out.')
    expect(logOutButton()).toBeEnabled()
    expect(screen.getByRole('heading', { name: 'Questions in this session' })).toBeInTheDocument()
    expectNoLoginForm()
  })

  it('starts the app over on the next login: the datasets load again and nothing from before is left', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage(loggedIn)

    render(<App />)
    await findApp()
    await user.selectOptions(datasetSelect(), reports.id)
    await user.click(newDatasetButton())
    await user.type(nameInput(), 'Contracts')
    await user.click(logOutButton()!)
    await findLoginForm()
    await logInWith(user, 'secret')
    await findApp()

    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(2)
    expect(datasetSelect()).toHaveValue(invoices.id)
    // The form is closed again, and opens empty.
    expect(screen.queryByRole('textbox', { name: 'New dataset name' })).not.toBeInTheDocument()
    await user.click(newDatasetButton())
    expect(nameInput()).toHaveValue('')
  })
})

describe('when the session ends while the app is open', () => {
  it('goes back to the login form and says why when a later request gets a 401', async () => {
    const user = userEvent.setup()
    stubPage(loggedIn, { 'POST /api/datasets': logInFirst })

    render(<App />)
    await findApp()
    await createNamed(user, 'Contracts')

    expect(await findLoginForm()).toHaveValue('')
    expect(screen.getByRole('alert')).toHaveTextContent(sessionEnded)
    expect(screen.queryByText('Log in first.')).not.toBeInTheDocument()
    expect(logOutButton()).not.toBeInTheDocument()
    expectNoApp()
  })

  it('does not loop: it neither checks the session again nor reloads the datasets', async () => {
    // The check keeps saying logged in, so a page that checked again on a 401 would show the app, load the datasets,
    // get another 401, and go round.
    const fetchStub = stubPage(loggedIn, { 'GET /api/datasets': logInFirst })

    render(<App />)
    await findLoginForm()
    await act(async () => {})

    expect(screen.getByRole('alert')).toHaveTextContent(sessionEnded)
    expect(requestsTo(fetchStub, '/api/session')).toHaveLength(1)
    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(1)
    expectNoApp()
  })

  it('takes a 401 from logging in for a wrong password, not for another ended session', async () => {
    const user = userEvent.setup()
    stubPage(loggedIn, { 'POST /api/datasets': logInFirst, 'POST /api/session': wrongPassword })

    render(<App />)
    await findApp()
    await createNamed(user, 'Contracts')
    await findLoginForm()
    await logInWith(user, 'guess')

    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong password.')
    expect(screen.queryByText(sessionEnded)).not.toBeInTheDocument()
    expect(passwordInput()).toHaveValue('guess')
  })

  it('starts the app over on the next login: the datasets load again and nothing from before is left', async () => {
    const user = userEvent.setup()
    const fetchStub = stubPage(loggedIn, { 'POST /api/datasets': logInFirst })

    render(<App />)
    await findApp()
    await user.selectOptions(datasetSelect(), reports.id)
    await createNamed(user, 'Contracts')
    await findLoginForm()
    await logInWith(user, 'secret')
    await findApp()

    expect(requestsTo(fetchStub, '/api/datasets')).toHaveLength(2)
    expect(datasetSelect()).toHaveValue(invoices.id)
    // The form is closed again, and opens empty.
    expect(screen.queryByRole('textbox', { name: 'New dataset name' })).not.toBeInTheDocument()
    await user.click(newDatasetButton())
    expect(nameInput()).toHaveValue('')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(logOutButton()).toBeEnabled()
  })

  it('ignores a 401 that comes back after the user has logged out', async () => {
    const user = userEvent.setup()
    const { route, answer } = waitingRoute()
    stubPage(loggedIn, { 'POST /api/datasets': route })

    render(<App />)
    await findApp()
    await createNamed(user, 'Contracts')
    await user.click(logOutButton()!)
    await findLoginForm()
    await answer(logInFirst())

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    await logInWith(user, 'secret')
    await findApp()
  })

  it('asks for a login even when none was required at first, as after the backend got a password', async () => {
    const user = userEvent.setup()
    stubPage(noLogin, { 'POST /api/datasets': logInFirst })

    render(<App />)
    await findApp()
    await createNamed(user, 'Contracts')

    expect(await findLoginForm()).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(sessionEnded)

    await logInWith(user, 'secret')
    await findApp()

    expect(logOutButton()).toBeEnabled()
  })
})
