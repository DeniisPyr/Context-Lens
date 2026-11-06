# Answer quality: whole_document, gemini-3.8-flash

48 questions about 7 documents (set sha256:bf47d7fcc7fb767e64fc5ea1b62ad4271ff49811666020c7c620ab1e24c6d551), 3 repeats, concurrency 1, started 2026-11-06T10:44:16+00:00, took 674.6 s.

## Summary

| Measure | Value |
| --- | --- |
| Questions | 48 |
| Runs | 144 |
| Gemini errors | 0 |
| Correct | 100% (144/144) |
| Answer accuracy | 100% (96/96) |
| Citation accuracy | 100% (96/96) |
| False not found | 0% (0/96) |
| Not found accuracy | 100% (48/48) |
| Rejected by the verifier | 0% (0/144) |
| Median seconds | 3.5 |
| p95 seconds | 7.9 |
| Max seconds | 52.3 |
| Mean input tokens | 3941 |
| Mean output tokens, with thinking | 347 |
| Total input tokens | 567450 |
| Total output tokens, with thinking | 49916 |

## By category

| Category | Runs | Errors | Correct | Answer accuracy | Citation accuracy | False not found | Not found accuracy | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fact | 66 | 0 | 100% (66/66) | 100% (66/66) | 100% (66/66) | 0% (0/66) | n/a | 3.5 | 4067 |
| multi_fact | 24 | 0 | 100% (24/24) | 100% (24/24) | 100% (24/24) | 0% (0/24) | n/a | 4.9 | 4720 |
| injection | 6 | 0 | 100% (6/6) | 100% (6/6) | 100% (6/6) | 0% (0/6) | n/a | 4.3 | 2540 |
| missing_related | 30 | 0 | 100% (30/30) | n/a | n/a | n/a | 100% (30/30) | 3.5 | 4256 |
| missing_unrelated | 18 | 0 | 100% (18/18) | n/a | n/a | n/a | 100% (18/18) | 2.8 | 2377 |

## By document

| Document | Runs | Errors | Correct | Answer accuracy | Citation accuracy | False not found | Not found accuracy | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cestovni-nahrady.md | 18 | 0 | 100% (18/18) | 100% (15/15) | 100% (15/15) | 0% (0/15) | 100% (3/3) | 3.3 | 1982 |
| employee-handbook.md | 21 | 0 | 100% (21/21) | 100% (12/12) | 100% (12/12) | 0% (0/12) | 100% (9/9) | 3.5 | 2886 |
| hplc-maintenance-sop.txt | 24 | 0 | 100% (24/24) | 100% (18/18) | 100% (18/18) | 0% (0/18) | 100% (6/6) | 4.4 | 11743 |
| it-security-policy.md | 18 | 0 | 100% (18/18) | 100% (12/12) | 100% (12/12) | 0% (0/12) | 100% (6/6) | 3.6 | 2152 |
| steering-committee-minutes.md | 21 | 0 | 100% (21/21) | 100% (12/12) | 100% (12/12) | 0% (0/12) | 100% (9/9) | 3.6 | 2032 |
| supplier-agreement.md | 21 | 0 | 100% (21/21) | 100% (15/15) | 100% (15/15) | 0% (0/15) | 100% (6/6) | 4.0 | 3046 |
| velmorin-leaflet.md | 21 | 0 | 100% (21/21) | 100% (12/12) | 100% (12/12) | 0% (0/12) | 100% (9/9) | 3.1 | 2092 |

## Runs that weren't correct

None.
