# Evaluation

[Back to the README](../README.md)


`backend/evals/` holds a fixed set of 78 questions about 7 fictional documents, for measuring how well the app answers. The documents are an employee handbook, an IT security policy, steering committee minutes, a leaflet for a made-up medicine, a travel-expenses policy in Czech, a 726-line instrument maintenance SOP with 40 look-alike error codes, and a supplier agreement. Together they make one dataset of 95 chunks.

- 52 questions have an answer. Each lists the facts a right answer must contain, with alternative phrasings, and the lines it must cite, in which file. Two ask about facts that a line in a document, addressed to AI assistants, tries to change, and six need two documents.
- 20 have no answer in any of the documents, so the app must say "not found". Some ask about something next to what a document covers, and some are general knowledge that Gemini knows but must not use.
- 6 need a clarifying question, such as "A test on our LX-500 just failed. What should I do?", where five tests each have their own procedure. Each comes with the user's reply, such as "It was the static leak test.", and the facts of the answer to it. Two have their situations in different documents, so search has to find both.

Of the 72 questions that need no clarifying question, the first 48 were written for the whole-document baseline, which got every one right. The other 24 are made to be hard for search but fair to a careful reader. Each one does one of these:

- needs two documents
- uses everyday words instead of the document's own
- needs facts far apart in a long document
- has a look-alike value nearby for another case
- has no answer, although a passage covers something similar

A run is correct when it answers with every fact, cites every expected line range in the right file and uses no forbidden phrase. For a question without an answer, it's correct when it says "not found". A clarifying-question run is correct when Gemini asks back first and then answers the reply that way. When it asks, the evaluation sends the reply, as a user would. Every other question must be answered without a clarifying question, so asking where there's no need counts as wrong. Grading is plain text matching with no second model as a judge, so the same answers always get the same scores. The set is checked on every test run: each expected fact must appear in the lines the question says to cite.

The evaluation answers in one of two ways:

- **`rag`**, the default, answers as the app does, with the app's own code. Every document is chunked and embedded once at the start, for about half a cent. Then each question goes through the same search, excerpts, prompt and check as `POST /api/ask`. Only the store differs: the chunks are kept in memory and searched exactly by cosine distance, as Postgres does.
- **`whole_document`** sends each question's documents whole: its own document, plus the other one for a question that needs two, and every document holding a situation for a clarifying question. That's how the app answered before search. It's also told which document holds the answer, which the app never is.

To check the set and see how much text the prompts would send, without calling Gemini:

```bash
cd backend
uv run python -m context_lens.evaluation --dry-run
```

To run it, with the key from `backend/.env`. This calls Gemini once for each question and repeat, and twice when it asks back, so it spends credits. At gemini-3.8-flash's prices in November 2026, 3 repeats cost about $1.05 for `rag` and $1.45 for `whole_document`:

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

From [evals/results/comparison.md](../backend/evals/results/comparison.md), with gemini-3.8-flash and 3 repeats of each question. One run of each method ended in a Gemini error (a timeout), so the rates leave it out. First, the 72 questions that need no clarifying question:

| Measure | Whole documents | Search (`rag`) |
| --- | --- | --- |
| Correct | 100% (216/216) | 94% (203/216) |
| Correct, questions that need two documents | 100% (18/18) | 50% (9/18) |
| Correct, questions with facts in two places of one document | 100% (36/36) | 92% (33/36) |
| Expected lines shown to Gemini | 100% (156/156) | 94% (147/156) |
| "Not found" when there's no answer | 100% (60/60) | 100% (60/60) |
| Asked a clarifying question it didn't need | 0% (0/216) | 0% (0/216) |
| Median / p95 seconds | 4.4 / 9.3 | 5.1 / 9.5 |
| Input tokens per question | 4,408 on average; 12,008 for the SOP | 2,474 on average; 2,420 for the SOP |
| Output tokens per question, with thinking | 368 | 501 |
| Cost per 1,000 questions | $4.69 | $3.73 |

Then the 6 questions that need one:

| Measure | Whole documents | Search (`rag`) |
| --- | --- | --- |
| Asked back | 100% (17/17) | 71% (12/17) |
| Then answered the reply right | 100% (17/17) | 100% (12/12) |
| Median seconds, both questions | 20.8 | 22.1 |
| Input tokens, both questions | 21,521 | 4,037 |
| Cost per 1,000 | $26.08 | $14.82 |

What this shows:

- **Search misses the second half of a question.**
  - 9 of the 13 wrong `rag` runs on clear questions were questions whose answer sits in two places. The question is embedded once, so the 8 closest chunks match the part of it that dominates. For 3 questions, every time, search never showed Gemini the second passage. For example, "Who reviewed the SOP, and which action item does that person own?" needs the reviewer's name to find the action item, and the name isn't in the question. Gemini then said "not found" or left that part out, instead of guessing.
  - A 4th question, "To what date was the go-live of the new LIMS moved, and within what time must Corvane resolve a priority 1 incident?", got "not found" in all 3 runs, although search showed both passages. Before Gemini could ask back, the same question was answered right in 2 of 3 runs, so the new instruction has likely made Gemini more careful there.
  - In the last one, Gemini copied a line number from the prompt into the middle of its quote, so the quote wasn't word for word in the document, and the check rejected the answer.
- **It doesn't ask when it needn't.** Neither method asked a clarifying question about any of the 72 clear questions, in 432 runs.
- **It asks when it should, if search finds the situations.**
  - With whole documents, Gemini asked every time, and answered every reply right.
  - With search, when it asked, it answered every reply right too. It missed two questions. For "A test on our LX-500 just failed. What should I do?", search found the list of error codes rather than the five test procedures, and Gemini said "not found". For "What rules do I have to follow when handling the document I'm working on?", search found the handling rules but not the classification levels, and Gemini listed the rules for every level instead of asking which one the document has.
  - Asking back takes two calls and longer thinking: about 22 seconds for the whole exchange, and 1.5 cents.
- **It didn't answer what the documents don't say.** Both methods said "not found" for all 20 questions without an answer. That includes the ones where search returned a passage about a similar case.
- **It's cheaper, and its cost doesn't grow with the documents.**
  - Search sends 44% fewer input tokens. It sends about the same for the 726-line SOP as for a short leaflet.
  - Gemini thinks a little longer over excerpts, so the saving here is 20% per question.
  - The bigger point is scale: a full dataset, up to 100 files of up to 1 MB each, can hold far more text than one prompt can take.

Searching once for each part of a question, or giving it more chunks, might fix the questions whose answer sits in two places, and also show Gemini the situations it needs to see before it can ask back. This set can measure either change.
