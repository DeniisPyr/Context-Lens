# Answer quality: rag, gemini-3.8-flash

72 questions about 7 documents (set sha256:a99a1993da3e0496282e3b3055adef75b9428689d6c06aa53ad63278d9cae67a), 3 repeats, concurrency 1, started 2026-11-09T01:39:41+00:00, took 1165.0 s.

Search: the 8 nearest of 95 chunks for each question. Indexing embedded 77,684 characters in 3.9 s.

## Summary

| Measure | Value |
| --- | --- |
| Questions | 72 |
| Runs | 216 |
| Gemini errors | 1 |
| Correct | 95% (205/215) |
| Answer accuracy | 94% (145/155) |
| Citation accuracy | 94% (145/155) |
| Evidence shown to Gemini | 94% (146/155) |
| False not found | 5% (7/155) |
| Not found accuracy | 100% (60/60) |
| Rejected by the verifier | 0% (0/215) |
| Median seconds | 4.5 |
| p95 seconds | 8.2 |
| Max seconds | 24.6 |
| Mean input tokens | 2392 |
| Mean output tokens, with thinking | 441 |
| Total input tokens | 514225 |
| Total output tokens, with thinking | 94753 |

## By category

| Category | Runs | Errors | Correct | Answer accuracy | Citation accuracy | Evidence shown | False not found | Not found accuracy | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fact | 96 | 1 | 100% (95/95) | 100% (95/95) | 100% (95/95) | 100% (95/95) | 0% (0/95) | n/a | 4.2 | 2461 |
| multi_fact | 36 | 0 | 92% (33/36) | 92% (33/36) | 92% (33/36) | 92% (33/36) | 0% (0/36) | n/a | 5.5 | 2353 |
| cross_document | 18 | 0 | 61% (11/18) | 61% (11/18) | 61% (11/18) | 67% (12/18) | 39% (7/18) | n/a | 7.1 | 2395 |
| injection | 6 | 0 | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) | 0% (0/6) | n/a | 5.3 | 2250 |
| missing_related | 42 | 0 | 100% (42/42) | n/a | n/a | n/a | n/a | 100% (42/42) | 4.4 | 2368 |
| missing_unrelated | 18 | 0 | 100% (18/18) | n/a | n/a | n/a | n/a | 100% (18/18) | 3.7 | 2202 |

## By document

| Document | Runs | Errors | Correct | Answer accuracy | Citation accuracy | Evidence shown | False not found | Not found accuracy | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cestovni-nahrady.md | 24 | 0 | 100% (24/24) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (3/3) | 4.5 | 2991 |
| employee-handbook.md | 36 | 0 | 83% (30/36) | 75% (18/24) | 75% (18/24) | 75% (18/24) | 12% (3/24) | 100% (12/12) | 4.4 | 2419 |
| hplc-maintenance-sop.txt | 39 | 0 | 92% (36/39) | 91% (30/33) | 91% (30/33) | 91% (30/33) | 9% (3/33) | 100% (6/6) | 4.7 | 2337 |
| it-security-policy.md | 30 | 0 | 100% (30/30) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (9/9) | 4.3 | 2054 |
| steering-committee-minutes.md | 30 | 0 | 97% (29/30) | 94% (17/18) | 94% (17/18) | 100% (18/18) | 6% (1/18) | 100% (12/12) | 4.6 | 2385 |
| supplier-agreement.md | 30 | 1 | 100% (29/29) | 100% (20/20) | 100% (20/20) | 100% (20/20) | 0% (0/20) | 100% (9/9) | 4.4 | 2249 |
| velmorin-leaflet.md | 27 | 0 | 100% (27/27) | 100% (18/18) | 100% (18/18) | 100% (18/18) | 0% (0/18) | 100% (9/9) | 4.2 | 2438 |

## Runs that weren't correct

- `agreement-p1-response` #2: Gemini error: GeminiUnavailableError
- `cross-company-phone-loss` #1: said not found; evidence employee-handbook.md line 139 not shown to Gemini
- `cross-company-phone-loss` #2: said not found; evidence employee-handbook.md line 139 not shown to Gemini
- `cross-company-phone-loss` #3: said not found; evidence employee-handbook.md line 139 not shown to Gemini
- `cross-lims-go-live-support` #1: said not found
- `cross-sop-reviewer-aurora-action` #1: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
- `cross-sop-reviewer-aurora-action` #2: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
- `cross-sop-reviewer-aurora-action` #3: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
- `handbook-manager-home-office-contribution` #1: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
- `handbook-manager-home-office-contribution` #2: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
- `handbook-manager-home-office-contribution` #3: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
