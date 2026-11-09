# Answer quality: whole_document, gemini-3.8-flash

72 questions about 7 documents (set sha256:a99a1993da3e0496282e3b3055adef75b9428689d6c06aa53ad63278d9cae67a), 3 repeats, concurrency 1, started 2026-11-09T01:26:29+00:00, took 790.9 s.

## Summary

| Measure | Value |
| --- | --- |
| Questions | 72 |
| Runs | 216 |
| Gemini errors | 0 |
| Correct | 100% (215/216) |
| Answer accuracy | 99% (155/156) |
| Citation accuracy | 99% (155/156) |
| Evidence shown to Gemini | 100% (156/156) |
| False not found | 1% (1/156) |
| Not found accuracy | 100% (60/60) |
| Rejected by the verifier | 0% (1/216) |
| Median seconds | 3.3 |
| p95 seconds | 5.7 |
| Max seconds | 20.0 |
| Mean input tokens | 4325 |
| Mean output tokens, with thinking | 343 |
| Total input tokens | 934098 |
| Total output tokens, with thinking | 74048 |

## By category

| Category | Runs | Errors | Correct | Answer accuracy | Citation accuracy | Evidence shown | False not found | Not found accuracy | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fact | 96 | 0 | 99% (95/96) | 99% (95/96) | 99% (95/96) | 100% (96/96) | 1% (1/96) | n/a | 3.2 | 4162 |
| multi_fact | 36 | 0 | 100% (36/36) | 100% (36/36) | 100% (36/36) | 100% (36/36) | 0% (0/36) | n/a | 3.8 | 5633 |
| cross_document | 18 | 0 | 100% (18/18) | 100% (18/18) | 100% (18/18) | 100% (18/18) | 0% (0/18) | n/a | 4.7 | 6321 |
| injection | 6 | 0 | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) | 0% (0/6) | n/a | 3.3 | 2568 |
| missing_related | 42 | 0 | 100% (42/42) | n/a | n/a | n/a | n/a | 100% (42/42) | 3.1 | 3791 |
| missing_unrelated | 18 | 0 | 100% (18/18) | n/a | n/a | n/a | n/a | 100% (18/18) | 2.4 | 2405 |

## By document

| Document | Runs | Errors | Correct | Answer accuracy | Citation accuracy | Evidence shown | False not found | Not found accuracy | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cestovni-nahrady.md | 24 | 0 | 100% (24/24) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (3/3) | 3.3 | 2384 |
| employee-handbook.md | 36 | 0 | 100% (36/36) | 100% (24/24) | 100% (24/24) | 100% (24/24) | 0% (0/24) | 100% (12/12) | 3.2 | 3090 |
| hplc-maintenance-sop.txt | 39 | 0 | 97% (38/39) | 97% (32/33) | 97% (32/33) | 100% (33/33) | 3% (1/33) | 100% (6/6) | 4.0 | 11925 |
| it-security-policy.md | 30 | 0 | 100% (30/30) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (9/9) | 3.0 | 2379 |
| steering-committee-minutes.md | 30 | 0 | 100% (30/30) | 100% (18/18) | 100% (18/18) | 100% (18/18) | 0% (0/18) | 100% (12/12) | 3.2 | 2360 |
| supplier-agreement.md | 30 | 0 | 100% (30/30) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (9/9) | 3.4 | 3077 |
| velmorin-leaflet.md | 27 | 0 | 100% (27/27) | 100% (18/18) | 100% (18/18) | 100% (18/18) | 0% (0/18) | 100% (9/9) | 2.9 | 2449 |

## Runs that weren't correct

- `sop-flow-rate-accuracy` #3: citations rejected by the verifier
