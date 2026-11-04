# Context-Lens

Ask questions about your own documents and get answers backed by exact quotes, each linked to the lines it comes from. When the documents don't contain the answer, Context-Lens says so instead of guessing.

> Work in progress: currently a FastAPI backend that uses Gemini to answer questions from an uploaded text document. Citations are checked against the document's lines, and answers that can't be verified get a "not found" reply. The React frontend can upload documents and list them, and shows whether the API is reachable. Asking questions still goes through the API directly.

## Run locally

Requirements: Python 3.13, [uv](https://docs.astral.sh/uv/), a [Gemini API key](https://aistudio.google.com/apikey), and [Node 26](https://nodejs.org/).

```bash
cd backend
uv sync
cp .env.example .env  # then paste your key into .env
uv run uvicorn context_lens.main:app --reload
```

- Health check: http://localhost:8000/api/health
- Interactive API docs: http://localhost:8000/docs

Upload a `.txt` or `.md` file (up to 1 MB, kept in memory until the server restarts), then ask a question using the `id` from the response:

```bash
curl -F "file=@notes.txt" http://localhost:8000/api/documents

curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"document_id": "<id from the upload>", "question": "What do these notes say?"}'
```

List your uploads:

```bash
curl http://localhost:8000/api/documents
```

To run the frontend, keep the backend running and use another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173 to upload `.txt` and `.md` files and see the list. To ask about a document you uploaded there, get its `id` from `curl http://localhost:8000/api/documents`. Vite forwards `/api` requests to the backend at `http://localhost:8000`. To use a different address, set `API_PROXY_TARGET` (see `frontend/.env.example`).

## Project structure

The backend lives in `backend/src/context_lens/`, and each file has one job:

```
context_lens/
├── main.py                  # creates the app, registers routers and handlers
├── settings.py              # configuration, from the environment or .env
├── dependencies.py          # what routes can ask for: GeminiDep, DocumentStoreDep, SettingsDep
├── exception_handlers.py    # maps domain errors to HTTP responses
├── clients/gemini.py        # talks to the Gemini API
├── routers/                 # route functions only
│   └── api.py, ask.py, documents.py, health.py
├── schemas/                 # API request and response models
│   └── ask.py, documents.py, health.py
└── services/                # logic, no FastAPI imports
    ├── answering.py         # builds the prompt, asks Gemini, verifies citations
    └── documents.py         # validates uploads and stores documents
```

The frontend lives in `frontend/src/`:

```
src/
├── main.tsx             # starts React
├── App.tsx              # the page: puts the parts below together
├── index.css            # page styles
├── api/                 # every HTTP call lives here
│   ├── documents.ts     # lists and uploads documents
│   ├── errors.ts        # turns a failed response into a readable message
│   └── health.ts        # asks the backend whether it's healthy
├── components/
│   ├── ApiStatus.tsx    # shows whether the API is reachable
│   ├── Documents.tsx    # loads and shows the document list
│   └── UploadForm.tsx   # chooses and uploads a file
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

```bash
cd frontend
npm run lint
npm test
npm run build
```
