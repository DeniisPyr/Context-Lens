# Context-Lens

Ask questions about your own documents and get answers backed by exact quotes, each linked to the lines it comes from. When the documents don't contain the answer, Context-Lens says so instead of guessing.

> Work in progress: currently a FastAPI backend that uses Gemini to answer questions from an uploaded text document, with citations to its lines. Verifying those citations is next.

## Run locally

Requirements: Python 3.13, [uv](https://docs.astral.sh/uv/), and a [Gemini API key](https://aistudio.google.com/apikey).

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

## Code quality

```bash
cd backend
uv run pytest
uv run ruff check .
uv run ruff format .
```
