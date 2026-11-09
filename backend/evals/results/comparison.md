# Answer quality compared: whole_document and rag

72 questions about 7 documents (set sha256:a99a1993da3e0496282e3b3055adef75b9428689d6c06aa53ad63278d9cae67a).

|  | whole_document | rag |
| --- | --- | --- |
| Report | evals/results/whole-document.json | evals/results/rag.json |
| Method | whole_document | rag |
| Model | gemini-3.8-flash | gemini-3.8-flash |
| Repeats | 3 | 3 |
| Chunks per question | n/a | 8 |

## Summary

| Measure | whole_document | rag |
| --- | --- | --- |
| Questions | 72 | 72 |
| Runs | 216 | 216 |
| Gemini errors | 0 | 1 |
| Correct | 100% (215/216) | 95% (205/215) |
| Answer accuracy | 99% (155/156) | 94% (145/155) |
| Citation accuracy | 99% (155/156) | 94% (145/155) |
| Evidence shown to Gemini | 100% (156/156) | 94% (146/155) |
| False not found | 1% (1/156) | 5% (7/155) |
| Not found accuracy | 100% (60/60) | 100% (60/60) |
| Rejected by the verifier | 0% (1/216) | 0% (0/215) |
| Median seconds | 3.3 | 4.5 |
| p95 seconds | 5.7 | 8.2 |
| Max seconds | 20.0 | 24.6 |
| Mean input tokens | 4325 | 2392 |
| Mean output tokens, with thinking | 343 | 441 |
| Total input tokens | 934098 | 514225 |
| Total output tokens, with thinking | 74048 | 94753 |

## By category

| Category | Correct, whole_document | Correct, rag | Answer accuracy, whole_document | Answer accuracy, rag |
| --- | --- | --- | --- | --- |
| fact | 99% (95/96) | 100% (95/95) | 99% (95/96) | 100% (95/95) |
| multi_fact | 100% (36/36) | 92% (33/36) | 100% (36/36) | 92% (33/36) |
| cross_document | 100% (18/18) | 61% (11/18) | 100% (18/18) | 61% (11/18) |
| injection | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| missing_related | 100% (42/42) | 100% (42/42) | n/a | n/a |
| missing_unrelated | 100% (18/18) | 100% (18/18) | n/a | n/a |

## Questions with different results

- `sop-flow-rate-accuracy`: whole_document 2/3, rag 3/3
  - whole_document #3: citations rejected by the verifier
- `agreement-p1-response`: whole_document 3/3, rag 2/3
  - rag #2: Gemini error: GeminiUnavailableError
- `cross-company-phone-loss`: whole_document 3/3, rag 0/3
  - rag #1: said not found; evidence employee-handbook.md line 139 not shown to Gemini
  - rag #2: said not found; evidence employee-handbook.md line 139 not shown to Gemini
  - rag #3: said not found; evidence employee-handbook.md line 139 not shown to Gemini
- `cross-lims-go-live-support`: whole_document 3/3, rag 2/3
  - rag #1: said not found
- `cross-sop-reviewer-aurora-action`: whole_document 3/3, rag 0/3
  - rag #1: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
  - rag #2: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
  - rag #3: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
- `handbook-manager-home-office-contribution`: whole_document 3/3, rag 0/3
  - rag #1: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
  - rag #2: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
  - rag #3: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
