# Context-Lens

Ask questions about your own documents and get answers backed by exact quotes, each linked to the lines it comes from. When the documents don't contain the answer, Context-Lens says so instead of guessing.

> Work in progress: currently a FastAPI backend with a health check.

## Run locally

Requirements: Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
uv run uvicorn context_lens.main:app --reload
```

- Health check: http://localhost:8000/api/health
- Interactive API docs: http://localhost:8000/docs

## Code quality

```bash
cd backend
uv run ruff check .
uv run ruff format .
```
