# Answer quality compared: whole_document and rag

78 questions about 7 documents (set sha256:11f4e10b904eb0045fd6a54934928b97e68d6d0eaa0fc3a018ee60af58edd43c).

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
| Questions | 78 | 78 |
| Runs | 234 | 234 |
| Gemini errors | 1 | 1 |
| Correct | 100% (233/233) | 92% (215/233) |
| Answer accuracy | 100% (156/156) | 92% (143/156) |
| Citation accuracy | 100% (156/156) | 92% (143/156) |
| Evidence shown to Gemini | 100% (156/156) | 94% (147/156) |
| False not found | 0% (0/156) | 6% (10/156) |
| Not found accuracy | 100% (60/60) | 100% (60/60) |
| Clarified | 100% (17/17) | 71% (12/17) |
| Needless clarification | 0% (0/216) | 0% (0/216) |
| Rejected by the verifier | 0% (0/233) | 0% (1/233) |
| Median seconds | 4.5 | 5.2 |
| p95 seconds | 19.9 | 22.1 |
| Max seconds | 55.2 | 58.7 |
| Mean input tokens | 5656 | 2588 |
| Mean output tokens, with thinking | 534 | 694 |
| Total input tokens | 1317889 | 603028 |
| Total output tokens, with thinking | 124520 | 161587 |

## By category

| Category | Correct, whole_document | Correct, rag | Answer accuracy, whole_document | Answer accuracy, rag | Clarified, whole_document | Clarified, rag | Needless clarification, whole_document | Needless clarification, rag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fact | 100% (96/96) | 99% (95/96) | 100% (96/96) | 99% (95/96) | n/a | n/a | 0% (0/96) | 0% (0/96) |
| multi_fact | 100% (36/36) | 92% (33/36) | 100% (36/36) | 92% (33/36) | n/a | n/a | 0% (0/36) | 0% (0/36) |
| cross_document | 100% (18/18) | 50% (9/18) | 100% (18/18) | 50% (9/18) | n/a | n/a | 0% (0/18) | 0% (0/18) |
| injection | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) | n/a | n/a | 0% (0/6) | 0% (0/6) |
| missing_related | 100% (42/42) | 100% (42/42) | n/a | n/a | n/a | n/a | 0% (0/42) | 0% (0/42) |
| missing_unrelated | 100% (18/18) | 100% (18/18) | n/a | n/a | n/a | n/a | 0% (0/18) | 0% (0/18) |
| clarify | 100% (17/17) | 71% (12/17) | n/a | n/a | 100% (17/17) | 71% (12/17) | n/a | n/a |

## Questions with different results

- `agreement-invoice-payment`: whole_document 3/3, rag 2/3
  - rag #2: citations rejected by the verifier
- `cross-company-phone-loss`: whole_document 3/3, rag 0/3
  - rag #1: said not found; evidence employee-handbook.md line 139 not shown to Gemini
  - rag #2: said not found; evidence employee-handbook.md line 139 not shown to Gemini
  - rag #3: said not found; evidence employee-handbook.md line 139 not shown to Gemini
- `cross-lims-go-live-support`: whole_document 3/3, rag 0/3
  - rag #1: said not found
  - rag #2: said not found
  - rag #3: said not found
- `cross-sop-reviewer-aurora-action`: whole_document 3/3, rag 0/3
  - rag #1: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
  - rag #2: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
  - rag #3: said not found; evidence steering-committee-minutes.md line 99 not shown to Gemini
- `handbook-manager-home-office-contribution`: whole_document 3/3, rag 0/3
  - rag #1: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
  - rag #2: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
  - rag #3: missing fact: 6 months / six months / 6-month / six-month; evidence employee-handbook.md line 157 not shown to Gemini
- `clarify-lx500-failed-test`: whole_document 3/3, rag 0/3
  - rag #1: said not found; evidence hplc-maintenance-sop.txt line 294 not shown to Gemini; case hplc-maintenance-sop.txt lines 247–249 not shown to Gemini; case hplc-maintenance-sop.txt lines 276–278 not shown to Gemini; case hplc-maintenance-sop.txt lines 292–294 not shown to Gemini; case hplc-maintenance-sop.txt lines 346–352 not shown to Gemini
  - rag #2: said not found; evidence hplc-maintenance-sop.txt line 294 not shown to Gemini; case hplc-maintenance-sop.txt lines 247–249 not shown to Gemini; case hplc-maintenance-sop.txt lines 276–278 not shown to Gemini; case hplc-maintenance-sop.txt lines 292–294 not shown to Gemini; case hplc-maintenance-sop.txt lines 346–352 not shown to Gemini
  - rag #3: said not found; evidence hplc-maintenance-sop.txt line 294 not shown to Gemini; case hplc-maintenance-sop.txt lines 247–249 not shown to Gemini; case hplc-maintenance-sop.txt lines 276–278 not shown to Gemini; case hplc-maintenance-sop.txt lines 292–294 not shown to Gemini; case hplc-maintenance-sop.txt lines 346–352 not shown to Gemini
- `clarify-it-document-handling`: whole_document 2/3, rag 0/3
  - rag #1: didn't ask which situation applies; case it-security-policy.md line 72 not shown to Gemini; case it-security-policy.md line 73 not shown to Gemini
  - rag #2: didn't ask which situation applies; case it-security-policy.md line 72 not shown to Gemini; case it-security-policy.md line 73 not shown to Gemini
  - rag #3: Gemini error: GeminiUnavailableError
