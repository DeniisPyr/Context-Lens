# Context-Lens

Ask questions about your own documents and get answers backed by exact quotes, each linked to the lines it comes from. When the documents don't contain the answer, Context-Lens says so instead of guessing.

> Work in progress: currently a FastAPI backend that answers questions with Gemini and accepts text document uploads. Answering from those documents is next, then citations.

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

Ask a question:

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Say hello in Czech."}'
```

Upload a `.txt` or `.md` file (up to 1 MB, kept in memory until the server restarts), then list your uploads:

```bash
curl -F "file=@notes.txt" http://localhost:8000/api/documents
curl http://localhost:8000/api/documents
```

## Code quality

```bash
cd backend
uv run pytest
uv run ruff check .
uv run ruff format .
```
