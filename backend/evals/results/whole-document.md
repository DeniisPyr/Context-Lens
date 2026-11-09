# Answer quality: whole_document, gemini-3.8-flash

78 questions about 7 documents (set sha256:11f4e10b904eb0045fd6a54934928b97e68d6d0eaa0fc3a018ee60af58edd43c), 3 repeats, concurrency 1, started 2026-11-09T13:27:44+00:00, took 1560.6 s.

## Summary

| Measure | Value |
| --- | --- |
| Questions | 78 |
| Runs | 234 |
| Gemini errors | 1 |
| Correct | 100% (233/233) |
| Answer accuracy | 100% (156/156) |
| Citation accuracy | 100% (156/156) |
| Evidence shown to Gemini | 100% (156/156) |
| False not found | 0% (0/156) |
| Not found accuracy | 100% (60/60) |
| Clarified | 100% (17/17) |
| Needless clarification | 0% (0/216) |
| Rejected by the verifier | 0% (0/233) |
| Median seconds | 4.5 |
| p95 seconds | 19.9 |
| Max seconds | 55.2 |
| Mean input tokens | 5656 |
| Mean output tokens, with thinking | 534 |
| Total input tokens | 1317889 |
| Total output tokens, with thinking | 124520 |

## By category

| Category | Runs | Errors | Correct | Answer accuracy | Citation accuracy | Evidence shown | False not found | Not found accuracy | Clarified | Needless clarification | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fact | 96 | 0 | 100% (96/96) | 100% (96/96) | 100% (96/96) | 100% (96/96) | 0% (0/96) | n/a | n/a | 0% (0/96) | 4.2 | 4245 |
| multi_fact | 36 | 0 | 100% (36/36) | 100% (36/36) | 100% (36/36) | 100% (36/36) | 0% (0/36) | n/a | n/a | 0% (0/36) | 5.4 | 5716 |
| cross_document | 18 | 0 | 100% (18/18) | 100% (18/18) | 100% (18/18) | 100% (18/18) | 0% (0/18) | n/a | n/a | 0% (0/18) | 6.9 | 6404 |
| injection | 6 | 0 | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) | 0% (0/6) | n/a | n/a | 0% (0/6) | 4.5 | 2652 |
| missing_related | 42 | 0 | 100% (42/42) | n/a | n/a | n/a | n/a | 100% (42/42) | n/a | 0% (0/42) | 4.0 | 3874 |
| missing_unrelated | 18 | 0 | 100% (18/18) | n/a | n/a | n/a | n/a | 100% (18/18) | n/a | 0% (0/18) | 3.1 | 2488 |
| clarify | 18 | 1 | 100% (17/17) | n/a | n/a | n/a | n/a | n/a | 100% (17/17) | n/a | 20.8 | 21521 |

## By document

| Document | Runs | Errors | Correct | Answer accuracy | Citation accuracy | Evidence shown | False not found | Not found accuracy | Clarified | Needless clarification | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cestovni-nahrady.md | 24 | 0 | 100% (24/24) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (3/3) | n/a | 0% (0/24) | 4.2 | 2467 |
| employee-handbook.md | 36 | 0 | 100% (36/36) | 100% (24/24) | 100% (24/24) | 100% (24/24) | 0% (0/24) | 100% (12/12) | n/a | 0% (0/36) | 4.3 | 3172 |
| hplc-maintenance-sop.txt | 48 | 0 | 100% (48/48) | 100% (33/33) | 100% (33/33) | 100% (33/33) | 0% (0/33) | 100% (6/6) | 100% (9/9) | 0% (0/39) | 5.4 | 14210 |
| it-security-policy.md | 36 | 1 | 100% (35/35) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (9/9) | 100% (5/5) | 0% (0/30) | 4.3 | 3563 |
| steering-committee-minutes.md | 30 | 0 | 100% (30/30) | 100% (18/18) | 100% (18/18) | 100% (18/18) | 0% (0/18) | 100% (12/12) | n/a | 0% (0/30) | 4.4 | 2443 |
| supplier-agreement.md | 33 | 0 | 100% (33/33) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (9/9) | 100% (3/3) | 0% (0/30) | 4.6 | 5940 |
| velmorin-leaflet.md | 27 | 0 | 100% (27/27) | 100% (18/18) | 100% (18/18) | 100% (18/18) | 0% (0/18) | 100% (9/9) | n/a | 0% (0/27) | 4.1 | 2532 |

## Runs that weren't correct

- `clarify-it-document-handling` #2: Gemini error: GeminiUnavailableError
