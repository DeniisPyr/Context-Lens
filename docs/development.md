# Development guide

[Back to the README](../README.md)

For the Docker quick start, see [Try it locally](../README.md#try-it-locally). This guide covers running the backend and frontend separately, using the API, and checking the code.

## Run the app for development

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

No login is needed unless you set `ACCESS_PASSWORD` in `backend/.env`. Then the page asks for it, as the Docker app does. Without it, the backend warns at startup that anyone who can reach it can use it.

To run the frontend, keep the backend running and use another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173 and create a dataset in the sidebar. Add `.txt`, `.md` or `.pdf` files to it (up to 1 MB each), with Add files in the sidebar or by dropping them on it; they upload at once. Then ask a question at the bottom of the page, and press Enter to send it. Each question becomes a card. If the answer depends on something the question doesn't say, the card asks back, with the lines that show why, and a box to reply in. Click a source's lines, or its page for a PDF, to read them in the panel beside the cards. To delete a document, use the trash button in its row; to delete a dataset with all its documents, use Delete above the dataset. Both ask before they delete anything. The theme switch at the bottom of the sidebar follows the system or keeps light or dark. Vite forwards `/api` requests to the backend at `http://localhost:8000`. To use a different address, set `API_PROXY_TARGET` (see `frontend/.env.example`).

You can also call the API directly. Create a dataset and upload a file into it using the `id` from its response, then read the document, ask about it or delete it using the `id` from the upload response. When an answer's `status` is `needs_clarification`, its `answer` is a question back: send the question again with that text and your reply in `clarification`. Deleting the dataset deletes its documents too. With a password set, log in first with `curl -c cookies.txt -X POST http://localhost:8000/api/session -H "Content-Type: application/json" -d '{"password": "<ACCESS_PASSWORD>"}'`, and add `-b cookies.txt` to each command below:

```bash
curl -X POST http://localhost:8000/api/datasets \
  -H "Content-Type: application/json" \
  -d '{"name": "My notes"}'

curl -F "file=@notes.txt" http://localhost:8000/api/datasets/<id from the dataset>/documents

curl http://localhost:8000/api/datasets/<id from the dataset>/documents

curl http://localhost:8000/api/documents/<id from the upload>

curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"dataset_id": "<id from the dataset>", "question": "What do these notes say?"}'

curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"dataset_id": "<id from the dataset>", "question": "What do these notes say?",
       "clarification": {"question": "<the answer that asked back>", "reply": "The ones from March."}}'

curl -X DELETE http://localhost:8000/api/documents/<id from the upload>

curl -X DELETE http://localhost:8000/api/datasets/<id from the dataset>
```

## Code quality

```bash
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Most backend tests need Postgres running, and skip with a reminder if it isn't. They create throwaway databases and drop them afterwards, so they never touch your data.

```bash
cd frontend
npm run lint
npm test
npm run build
```

`scripts/check-docker-stack.sh` checks a running Docker app: the login, the size cap, a rate limit and the security headers. CI builds the images, starts the app and runs the check for pull requests and pushes to `main`.
