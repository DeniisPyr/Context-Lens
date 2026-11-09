# Context-Lens

Ask questions about your own documents and get answers backed by exact quotes, each linked to the lines it comes from. When the documents don't contain the answer, Context-Lens says so instead of guessing.

> Work in progress: a FastAPI backend and a React frontend. Documents are uploaded into named datasets and stored in Postgres, and each one is split into chunks of lines that Gemini embeds and pgvector stores. A question is asked of a whole dataset: the closest chunks are found, and Gemini answers from them, citing the file, the lines and an exact quote for every claim. Citations are checked against the documents, and answers that can't be verified get a "not found" reply. The frontend creates and deletes datasets, uploads many files at once, deletes documents, asks questions of the selected dataset and opens each citation at its lines. An evaluation command scores the answers on a fixed set of questions and compares them with answers from whole documents.

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

Then open http://localhost:5173, create a dataset, upload `.txt` or `.md` files into it (up to 1 MB each), and ask a question about the dataset. Click a citation's lines to read them in its document. To delete a document, use the Delete button in its row; to delete a dataset with all its documents, use Delete dataset beside the Dataset select. Both ask before they delete anything. Vite forwards `/api` requests to the backend at `http://localhost:8000`. To use a different address, set `API_PROXY_TARGET` (see `frontend/.env.example`).

You can also call the API directly. Create a dataset and upload a file into it using the `id` from its response, then read the document, ask about it or delete it using the `id` from the upload response. Deleting the dataset deletes its documents too:

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

curl -X DELETE http://localhost:8000/api/documents/<id from the upload>

curl -X DELETE http://localhost:8000/api/datasets/<id from the dataset>
```

## Database

Documents live in Postgres, so uploads survive a backend restart. Each one belongs to a dataset, and a filename can only be in a dataset once. Deleting a dataset deletes its documents with it, and a deleted dataset's name or document's filename can be used again. Everything except the health check needs Postgres. While Postgres is down those requests answer 503, and they work again once it's back, without restarting the backend. If the migrations haven't been applied, the 503 gives the command to run.

After pulling a change that adds a file to `backend/migrations/versions/`, apply the migrations again:

```bash
cd backend
uv run alembic upgrade head
```

Documents you already have move to a dataset named `My documents` when the migration that adds datasets runs, and any duplicate filenames among them get a number, as in `notes (2).txt`.

### Chunks and embeddings

An upload also prepares the document for search:
- **Chunks:** the text is split into chunks of whole lines, up to 1,000 characters each. A chunk ends at a blank line where it can, so a paragraph or list entry stays whole and a heading stays with the text under it.
- **Embeddings:** Gemini's `gemini-embedding-2` turns each chunk, labelled with its filename, into 768 numbers. They're stored with the chunk and its line numbers in the `chunks` table, using pgvector.
- **All or nothing:** the document and its chunks are saved together. If Gemini is unavailable or fails, the upload is refused and nothing is stored.
- **Deleting:** deleting a document or a dataset deletes its chunks too.
- **Cost:** embedding spends credits on every upload, about 5 cents for a 1 MB file at November 2026 prices. So a dataset holds at most 100 documents; to change that, set `MAX_DOCUMENTS_PER_DATASET` in `backend/.env`. An upload that would be refused, such as a duplicate filename or one into a full dataset, is refused before anything is sent to Gemini.

The 1,000-character size comes from a comparison on the evaluation set, when it had 48 questions. Each of its 32 answerable questions was searched against the chunks of all 7 documents, looking for the chunk that holds each of the 40 passages the answers come from.
- **Size:** of 600, 1,000 and 1,500 characters, 1,000 ranked those chunks highest. It put them first for 57% of the passages, in the top 3 for 88%, and in the top 10 for all of them.
- **Filename label:** labelling each chunk with its filename helped at every size. At 1,500 characters it raised the share in the top 5 from 72% to 98%.

Documents uploaded before chunks existed have none. After applying the migration that adds them, index those documents once. This calls Gemini, so `--dry-run` first shows how much text it would send:

```bash
cd backend
uv run python -m context_lens.index_documents --dry-run
uv run python -m context_lens.index_documents
```

It only touches documents without chunks, so running it again is safe and retries any that failed.

The data lives in a Docker volume, so it survives `docker compose down`. To wipe it, run `docker compose down -v`, which deletes everything in the database. The defaults work as they are. To change them, see `.env.example` in the repo root and `DATABASE_URL` in `backend/.env.example`.

## How a question is answered

A question is asked of a whole dataset, in four steps:

1. **Search:** Gemini embeds the question, labelled `task: search result | query: …`, and Postgres finds the 8 chunks of the dataset closest to it by cosine distance. It's an exact scan without a vector index, which is fast at this size and never misses a closer chunk. To change the number of chunks, set `CHUNKS_PER_QUESTION` in `backend/.env`.
2. **Excerpts:** the chunks are grouped by file and put in line order, with neighbouring chunks merged, and every line keeps its number.
3. **Answer:** Gemini answers from these excerpts only, and gives each claim a citation with the file, the lines and a quote copied from them.
4. **Check:** each quote must be word for word in the document's real lines, and those lines must be among the ones Gemini was shown. A citation whose range is wider than its quote is narrowed to the lines the quote is on. If any citation fails, the whole answer is replaced with "not found".

A dataset without chunks gets "not found" without asking Gemini. That includes documents uploaded before chunks existed and not yet indexed (see [Chunks and embeddings](#chunks-and-embeddings)).

## Evaluation

`backend/evals/` holds a fixed set of 72 questions about 7 fictional documents, for measuring how well the app answers. The documents are an employee handbook, an IT security policy, steering committee minutes, a leaflet for a made-up medicine, a travel-expenses policy in Czech, a 726-line instrument maintenance SOP with 40 look-alike error codes, and a supplier agreement. Together they make one dataset of 95 chunks.

- 52 questions have an answer. Each lists the facts a right answer must contain, with alternative phrasings, and the lines it must cite, in which file. Two ask about facts that a line in a document, addressed to AI assistants, tries to change, and six need two documents.
- 20 have no answer in any of the documents, so the app must say "not found". Some ask about something next to what a document covers, and some are general knowledge that Gemini knows but must not use.

The first 48 questions were written for the whole-document baseline, which got every one right. The other 24 are made to be hard for search but fair to a careful reader. Each one does one of these:

- needs two documents
- uses everyday words instead of the document's own
- needs facts far apart in a long document
- has a look-alike value nearby for another case
- has no answer, although a passage covers something similar

A run is correct when it answers with every fact, cites every expected line range in the right file and uses no forbidden phrase. For a question without an answer, it's correct when it says "not found". Grading is plain text matching with no second model as a judge, so the same answers always get the same scores. The set is checked on every test run: each expected fact must appear in the lines the question says to cite.

The evaluation answers in one of two ways:

- **`rag`**, the default, answers as the app does, with the app's own code. Every document is chunked and embedded once at the start, for about half a cent. Then each question goes through the same search, excerpts, prompt and check as `POST /api/ask`. Only the store differs: the chunks are kept in memory and searched exactly by cosine distance, as Postgres does.
- **`whole_document`** sends each question's documents whole: its own document, plus the other one for a question that needs two. That's how the app answered before search. It's also told which document holds the answer, which the app never is.

To check the set and see how much text the prompts would send, without calling Gemini:

```bash
cd backend
uv run python -m context_lens.evaluation --dry-run
```

To run it, with the key from `backend/.env`. This calls Gemini once for each question and repeat, so it spends credits. At gemini-3.8-flash's prices in November 2026, 3 repeats cost about $0.75 for `rag` and $1.00 for `whole_document`:

```bash
uv run python -m context_lens.evaluation --repeats 3 --output evals/results/rag.json
uv run python -m context_lens.evaluation --method whole_document --repeats 3 --output evals/results/whole-document.json
uv run python -m context_lens.evaluation.compare evals/results/whole-document.json evals/results/rag.json --output evals/results/comparison.md
```

More options:

- `--chunks <n>` changes how many chunks `rag` gives each question.
- `--only <id>` asks one question.
- `--model <name>` tries another Gemini model.

The JSON report keeps every answer, citation and excerpt Gemini was shown, and the markdown file next to it sums them up. The comparison lists every question the two methods got differently, with the reasons.

### Results: search compared with whole documents

From [evals/results/comparison.md](backend/evals/results/comparison.md), with gemini-3.8-flash and 3 repeats of each of the 72 questions:

| Measure | Whole documents | Search (`rag`) |
| --- | --- | --- |
| Correct | 100% (215/216) | 95% (205/215) |
| Correct, questions that need two documents | 100% (18/18) | 61% (11/18) |
| Correct, questions with facts in two places of one document | 100% (36/36) | 92% (33/36) |
| Expected lines shown to Gemini | 100% (156/156) | 94% (146/155) |
| "Not found" when there's no answer | 100% (60/60) | 100% (60/60) |
| Median / p95 seconds | 3.3 / 5.7 | 4.5 / 8.2 |
| Input tokens per question | 4,325 on average; 11,925 for the SOP | 2,392 on average; 2,337 for the SOP |
| Output tokens per question, with thinking | 343 | 441 |
| Cost per 1,000 questions | $4.53 | $3.45 |

One `rag` run ended in a Gemini error ("unavailable"), so the `rag` rates count 215 runs.

What this shows:

- **Search misses the second half of a question.**
  - All 10 wrong `rag` runs were questions whose answer sits in two places. The question is embedded once, so the 8 closest chunks match the part of it that dominates.
  - In 9 of those runs, 3 questions each time, search never showed Gemini the second passage. For example, "Who reviewed the SOP, and which action item does that person own?" needs the reviewer's name to find the action item, and the name isn't in the question. Gemini then said "not found" or left that part out, instead of guessing.
  - In the 10th run, both passages were shown and Gemini still said "not found".
- **It didn't answer what the documents don't say.** Both methods said "not found" for all 20 questions without an answer. That includes the ones where search returned a passage about a similar case.
- **It's cheaper, and its cost doesn't grow with the documents.**
  - Search sends 45% fewer input tokens. It sends about the same for the 726-line SOP as for a short leaflet.
  - Gemini thinks a little longer over excerpts, so the saving here is 24% per question.
  - The bigger point is scale: a dataset of 100 documents can't be sent whole at all.
- **It's about a second slower**, because of the embedding request and the longer thinking.
- **The whole-document method isn't perfect either.** Its one wrong run quoted a heading from the line above its cited range, so the check rejected the answer.

Searching once for each part of a question, or giving it more chunks, might fix the questions whose answer sits in two places, and this set can measure either change.

## Project structure

The backend lives in `backend/src/context_lens/`, and each file has one job:

```
context_lens/
├── main.py                  # creates the app, registers routers and handlers
├── settings.py              # configuration, from the environment or .env
├── dependencies.py          # what routes can ask for: GeminiDep, ChunkStoreDep, DatasetStoreDep, DocumentStoreDep, SettingsDep
├── exception_handlers.py    # maps domain and database errors to HTTP responses
├── index_documents.py       # the command that indexes documents stored before chunks existed
├── clients/gemini.py        # talks to the Gemini API: answers and embeddings
├── db/                      # everything that knows about Postgres
│   ├── chunk_store.py       # finds the chunks of a dataset closest to a question
│   ├── dataset_store.py     # reads and writes datasets
│   ├── document_store.py    # reads and writes documents and their chunks
│   ├── engine.py            # builds the connection pool
│   ├── ids.py               # turns an id from the API into a UUID
│   └── models.py            # the database tables
├── evaluation/              # measures answer quality; the web app doesn't use it
│   ├── __main__.py          # the command: python -m context_lens.evaluation
│   ├── cases.py             # loads the question set and checks it
│   ├── compare.py           # the command that compares two reports
│   ├── dataset.py           # the evaluation's documents as one dataset, searched in memory
│   ├── matching.py          # finds a phrase in an answer, as a whole word
│   ├── methods.py           # the two ways of answering: from search, or from whole documents
│   ├── report.py            # builds the JSON report and its markdown summary
│   ├── runner.py            # asks every question, and records what Gemini was shown and what it cost
│   └── scoring.py           # scores each answer and sums the scores up
├── routers/                 # route functions only
│   └── api.py, ask.py, datasets.py, documents.py, health.py
├── schemas/                 # API request and response models
│   └── ask.py, datasets.py, documents.py, health.py
└── services/                # logic, no FastAPI imports
    ├── answering.py         # builds the prompt from excerpts, asks Gemini, verifies citations
    ├── chunking.py          # splits a document into chunks of lines
    ├── datasets.py          # what a dataset is, and its errors
    ├── documents.py         # validates uploads and splits text into lines
    ├── embeddings.py        # the embedding size, and how a chunk is labelled for it
    ├── indexing.py          # chunks a document and embeds the chunks
    └── search.py            # answers a question from the chunks a search finds in a dataset
```

Postgres, the migrations and the evaluation questions live outside that folder:

```
compose.yaml                 # runs Postgres for development
backend/
├── alembic.ini              # Alembic's settings, without the database URL
├── evals/                   # the evaluation
│   ├── questions.toml       # the questions, with the facts and lines a right answer needs
│   ├── documents/           # the fictional documents they're about
│   └── results/             # reports from evaluation runs, and their comparison
└── migrations/
    ├── env.py               # runs migrations against DATABASE_URL
    └── versions/            # one file for each schema change
```

The frontend lives in `frontend/src/`:

```
src/
├── main.tsx                   # starts React
├── App.tsx                    # the page: puts the parts below together and keeps the selected dataset
├── index.css                  # page styles
├── api/                       # every HTTP call lives here
│   ├── ask.ts                 # asks a question about a dataset
│   ├── datasets.ts            # lists, creates and deletes datasets
│   ├── documents.ts           # lists, uploads, reads and deletes documents
│   ├── errors.ts              # turns a failed response into a readable message
│   ├── health.ts              # asks the backend whether it's healthy
│   └── request.ts             # sends a request and turns any failure into a message
├── components/
│   ├── Answer.tsx             # shows one answer and its citations
│   ├── ApiStatus.tsx          # shows whether the API is reachable
│   ├── Ask.tsx                # asks a question about the selected dataset
│   ├── ConfirmDelete.tsx      # a Delete button that asks first, inline
│   ├── CreateDatasetForm.tsx  # names and creates a dataset
│   ├── DatasetContents.tsx    # everything for one dataset: its documents and the questions
│   ├── Datasets.tsx           # chooses a dataset, offers to create one and to delete it
│   ├── Documents.tsx          # shows the upload form and the document list, with Delete buttons
│   ├── LineViewer.tsx         # shows a citation's lines in the document
│   └── UploadForm.tsx         # chooses files, uploads them one by one and says how each went
├── hooks/
│   ├── useDatasets.ts         # loads the dataset list
│   └── useDocuments.ts        # loads the documents of a dataset
└── test/setup.ts              # test setup
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
