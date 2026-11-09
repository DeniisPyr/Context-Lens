# Answer quality: rag, gemini-3.8-flash

78 questions about 7 documents (set sha256:11f4e10b904eb0045fd6a54934928b97e68d6d0eaa0fc3a018ee60af58edd43c), 3 repeats, concurrency 1, started 2026-11-09T13:27:44+00:00, took 1798.2 s.

Search: the 8 nearest of 95 chunks for each question. Indexing embedded 77,684 characters in 4.1 s.

## Summary

| Measure | Value |
| --- | --- |
| Questions | 78 |
| Runs | 234 |
| Gemini errors | 1 |
| Correct | 92% (215/233) |
| Answer accuracy | 92% (143/156) |
| Citation accuracy | 92% (143/156) |
| Evidence shown to Gemini | 94% (147/156) |
| False not found | 6% (10/156) |
| Not found accuracy | 100% (60/60) |
| Clarified | 71% (12/17) |
| Needless clarification | 0% (0/216) |
| Rejected by the verifier | 0% (1/233) |
| Median seconds | 5.2 |
| p95 seconds | 22.1 |
| Max seconds | 58.7 |
| Mean input tokens | 2588 |
| Mean output tokens, with thinking | 694 |
| Total input tokens | 603028 |
| Total output tokens, with thinking | 161587 |

## By category

| Category | Runs | Errors | Correct | Answer accuracy | Citation accuracy | Evidence shown | False not found | Not found accuracy | Clarified | Needless clarification | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fact | 96 | 0 | 99% (95/96) | 99% (95/96) | 99% (95/96) | 100% (96/96) | 1% (1/96) | n/a | n/a | 0% (0/96) | 4.7 | 2542 |
| multi_fact | 36 | 0 | 92% (33/36) | 92% (33/36) | 92% (33/36) | 92% (33/36) | 0% (0/36) | n/a | n/a | 0% (0/36) | 5.8 | 2436 |
| cross_document | 18 | 0 | 50% (9/18) | 50% (9/18) | 50% (9/18) | 67% (12/18) | 50% (9/18) | n/a | n/a | 0% (0/18) | 9.1 | 2478 |
| injection | 6 | 0 | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) | 0% (0/6) | n/a | n/a | 0% (0/6) | 6.3 | 2332 |
| missing_related | 42 | 0 | 100% (42/42) | n/a | n/a | n/a | n/a | 100% (42/42) | n/a | 0% (0/42) | 5.0 | 2451 |
| missing_unrelated | 18 | 0 | 100% (18/18) | n/a | n/a | n/a | n/a | 100% (18/18) | n/a | 0% (0/18) | 3.9 | 2285 |
| clarify | 18 | 1 | 71% (12/17) | n/a | n/a | n/a | n/a | n/a | 71% (12/17) | n/a | 22.1 | 4037 |

## By document

| Document | Runs | Errors | Correct | Answer accuracy | Citation accuracy | Evidence shown | False not found | Not found accuracy | Clarified | Needless clarification | Median seconds | Mean input tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cestovni-nahrady.md | 24 | 0 | 100% (24/24) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (3/3) | n/a | 0% (0/24) | 5.2 | 3074 |
| employee-handbook.md | 36 | 0 | 83% (30/36) | 75% (18/24) | 75% (18/24) | 75% (18/24) | 12% (3/24) | 100% (12/12) | n/a | 0% (0/36) | 4.9 | 2502 |
| hplc-maintenance-sop.txt | 48 | 0 | 88% (42/48) | 91% (30/33) | 91% (30/33) | 91% (30/33) | 9% (3/33) | 100% (6/6) | 67% (6/9) | 0% (0/39) | 5.7 | 2732 |
| it-security-policy.md | 36 | 1 | 94% (33/35) | 100% (21/21) | 100% (21/21) | 100% (21/21) | 0% (0/21) | 100% (9/9) | 60% (3/5) | 0% (0/30) | 4.8 | 2350 |
| steering-committee-minutes.md | 30 | 0 | 90% (27/30) | 83% (15/18) | 83% (15/18) | 100% (18/18) | 17% (3/18) | 100% (12/12) | n/a | 0% (0/30) | 5.0 | 2468 |
| supplier-agreement.md | 33 | 0 | 97% (32/33) | 95% (20/21) | 95% (20/21) | 100% (21/21) | 5% (1/21) | 100% (9/9) | 100% (3/3) | 0% (0/30) | 5.7 | 2537 |
| velmorin-leaflet.md | 27 | 0 | 100% (27/27) | 100% (18/18) | 100% (18/18) | 100% (18/18) | 0% (0/18) | 100% (9/9) | n/a | 0% (0/27) | 4.7 | 2521 |

## Runs that weren't correct

- `agreement-invoice-payment` #2: citations rejected by the verifier
- `cross-company-phone-loss` #1: said not found; evidence employee-handbook.md line 139 not shown to Gemini
- `cross-company-phone-loss` #2: said not found; evidence employee-handbook.md line 139 not shown to Gemini
- `cross-company-phone-loss` #3: said not found; evidence employee-handbook.md line 139 not shown to Gemini
- `cross-lims-go-live-support` #1: said not found
- `cross-lims-go-live-support` #2: said not found
- `cross-lims-go-live-support` #3: said not found
- `cross-sop-reviewer-aurora-action` #1: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
- `cross-sop-reviewer-aurora-action` #2: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
- `cross-sop-reviewer-aurora-action` #3: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
- `handbook-manager-home-office-contribution` #1: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
- `handbook-manager-home-office-contribution` #2: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
- `handbook-manager-home-office-contribution` #3: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
- `clarify-lx500-failed-test` #1: said not found; evidence hplc-maintenance-sop.txt line 294 not shown to Gemini; case hplc-maintenance-sop.txt lines 247–249 not shown to Gemini; case hplc-maintenance-sop.txt lines 276–278 not shown to Gemini; case hplc-maintenance-sop.txt lines 292–294 not shown to Gemini; case hplc-maintenance-sop.txt lines 346–352 not shown to Gemini
- `clarify-lx500-failed-test` #2: said not found; evidence hplc-maintenance-sop.txt line 294 not shown to Gemini; case hplc-maintenance-sop.txt lines 247–249 not shown to Gemini; case hplc-maintenance-sop.txt lines 276–278 not shown to Gemini; case hplc-maintenance-sop.txt lines 292–294 not shown to Gemini; case hplc-maintenance-sop.txt lines 346–352 not shown to Gemini
- `clarify-lx500-failed-test` #3: said not found; evidence hplc-maintenance-sop.txt line 294 not shown to Gemini; case hplc-maintenance-sop.txt lines 247–249 not shown to Gemini; case hplc-maintenance-sop.txt lines 276–278 not shown to Gemini; case hplc-maintenance-sop.txt lines 292–294 not shown to Gemini; case hplc-maintenance-sop.txt lines 346–352 not shown to Gemini
- `clarify-it-document-handling` #1: didn't ask which situation applies; case it-security-policy.md line 72 not shown to Gemini; case it-security-policy.md line 73 not shown to Gemini
- `clarify-it-document-handling` #2: didn't ask which situation applies; case it-security-policy.md line 72 not shown to Gemini; case it-security-policy.md line 73 not shown to Gemini
- `clarify-it-document-handling` #3: Gemini error: GeminiUnavailableError
