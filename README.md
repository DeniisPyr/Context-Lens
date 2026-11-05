# Context-Lens

Ask questions about your own documents and get answers backed by exact quotes, each linked to the lines it comes from. When the documents don't contain the answer, Context-Lens says so instead of guessing.

> Work in progress: currently a FastAPI backend that uses Gemini to answer questions from an uploaded text document, with documents stored in Postgres. Citations are checked against the document's lines, and answers that can't be verified get a "not found" reply. The React frontend can upload documents, list them and ask about them, showing each answer with citations that open the document at the cited lines, and shows whether the API is reachable.

## Run locally

Requirements: Python 3.13, [uv](https://docs.astral.sh/uv/), a [Gemini API key](https://aistudio.google.com/apikey), [Node 26](https://nodejs.org/), and [Docker](https://docs.docker.com/get-docker/).

Start Postgres from the repo root. The command returns once it accepts connections:

```bash
docker compose up -d --wait
```

Then set up and start the backend:

```bash
cd backend
uv sync
cp .env.example .env  # then paste your key into .env
uv run alembic upgrade head
uv run uvicorn context_lens.main:app --reload
```

- Health check: http://localhost:8000/api/health
- Interactive API docs: http://localhost:8000/docs

To run the frontend, keep the backend running and use another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173, upload a `.txt` or `.md` file (up to 1 MB) and ask a question about it. Click a citation's lines to read them in the document. Vite forwards `/api` requests to the backend at `http://localhost:8000`. To use a different address, set `API_PROXY_TARGET` (see `frontend/.env.example`).

You can also call the API directly. Read a document or ask about it using the `id` from the upload response:

```bash
curl -F "file=@notes.txt" http://localhost:8000/api/documents

curl http://localhost:8000/api/documents/<id from the upload>

curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"document_id": "<id from the upload>", "question": "What do these notes say?"}'
```

## Database

Documents live in Postgres, so uploads survive a backend restart. Everything except the health check needs it. While Postgres is down those requests answer 503, and they work again once it's back, without restarting the backend. If the migrations haven't been applied, the 503 gives the command to run.

After pulling a change that adds a file to `backend/migrations/versions/`, apply the migrations again:

```bash
cd backend
uv run alembic upgrade head
```

The data lives in a Docker volume, so it survives `docker compose down`. To wipe it, run `docker compose down -v`, which deletes everything in the database. The defaults work as they are. To change them, see `.env.example` in the repo root and `DATABASE_URL` in `backend/.env.example`.

## Project structure

The backend lives in `backend/src/context_lens/`, and each file has one job:

```
context_lens/
├── main.py                  # creates the app, registers routers and handlers
├── settings.py              # configuration, from the environment or .env
├── dependencies.py          # what routes can ask for: GeminiDep, DocumentStoreDep, SettingsDep
├── exception_handlers.py    # maps domain and database errors to HTTP responses
├── clients/gemini.py        # talks to the Gemini API
├── db/                      # everything that knows about Postgres
│   ├── document_store.py    # reads and writes documents
│   ├── engine.py            # builds the connection pool
│   └── models.py            # the database tables
├── routers/                 # route functions only
│   └── api.py, ask.py, documents.py, health.py
├── schemas/                 # API request and response models
│   └── ask.py, documents.py, health.py
└── services/                # logic, no FastAPI imports
    ├── answering.py         # builds the prompt, asks Gemini, verifies citations
    └── documents.py         # validates uploads and splits text into lines
```

Postgres and the migrations live outside that folder:

```
compose.yaml                 # runs Postgres for development
backend/
├── alembic.ini              # Alembic's settings, without the database URL
└── migrations/
    ├── env.py               # runs migrations against DATABASE_URL
    └── versions/            # one file for each schema change
```

The frontend lives in `frontend/src/`:

```
src/
├── main.tsx             # starts React
├── App.tsx              # the page: puts the parts below together
├── index.css            # page styles
├── api/                 # every HTTP call lives here
│   ├── ask.ts           # asks a question about a document
│   ├── documents.ts     # lists, uploads and reads documents
│   ├── errors.ts        # turns a failed response into a readable message
│   ├── health.ts        # asks the backend whether it's healthy
│   └── request.ts       # sends a request and turns any failure into a message
├── components/
│   ├── Answer.tsx       # shows one answer and its citations
│   ├── ApiStatus.tsx    # shows whether the API is reachable
│   ├── Ask.tsx          # chooses a document and asks a question
│   ├── Documents.tsx    # shows the upload form and the document list
│   ├── LineViewer.tsx   # shows a citation's lines in the document
│   └── UploadForm.tsx   # chooses and uploads a file
├── hooks/
│   └── useDocuments.ts  # loads the document list
└── test/setup.ts        # test setup
```

Tests sit next to the code they cover, as `*.test.ts` or `*.test.tsx`.

## Code quality

```bash
cd backend
uv run pytest
uv run ruff check .
uv run ruff format .
```

Most backend tests need Postgres running, and skip with a reminder if it isn't. They create throwaway databases and drop them afterwards, so they never touch your data.

```bash
cd frontend
npm run lint
npm test
npm run build
```
