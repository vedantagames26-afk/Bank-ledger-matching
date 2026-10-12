# Seeded scenarios and expected decisions

All references and financial events below are synthetic. `data/expected_results.json` supplies independent expectations, checked by `test_expected_fixture`. Further domain tests exercise invariants and cases that need isolated controlled fixtures.

| Scenario | Source/example | Expected evidence/outcome |
|---|---|---|
| Exact reference and amount | Most ledger rows; setl_demo_00 | MATCHED after financial/date/integrity gates |
| Exact amount, missing reference | L006; setl_demo_04 | MATCHED with normalized available weights, no zero-confidence shortcut |
| Small unexplained difference | L004; setl_demo_01 | REVIEW; ₹75 payment excess / ₹120 bank shortage |
| Gross differs from net | Settlement groups; refunds 00–14, adjustments 00–07 | Separate charges/events explain net arithmetic; no invoice-to-net comparison |
| T+2 working-day cycle | Payment Jan 1 → settlement Jan 5 | Consistent with configured cycle |
| Weekend shifts elapsed days | Friday Jan 2 payments → Tuesday Jan 6 | Four calendar days, two working days |
| Holiday shifts expected date | Controlled Jan 6 holiday test fixture | Verified/local-evidence fixture shifts expected date to Jan 7; **not a real verified holiday demo claim** |
| Unexplained delay | setl_demo_07; L012 | DELAYED; cause not invented |
| Adjacent/similar amounts | L008/L009 | REVIEW; equivalent competing source support |
| Duplicate gateway event | pay_demo_010 repeated | Both rows retained/quarantined; L010 and setl_demo_02 REVIEW |
| Split payment | L000, pay_demo_000_0 / _1 | MATCHED, ₹4,000 + ₹6,000 supported by genuine shared order |
| Partial collection | L001 | PARTIAL, ₹4,000 collected and ₹4,000 residual |
| Invoice grouped through gateway | Other gateway ledgers | Payment association does not require direct invoice bank credit |
| Direct collection | D000–D019 | Direct ledger → bank profile; no UTR required |
| Unrelated bank activity | BOTHER000–BOTHER099 | All 100 remain unallocated and visible |
| Missing settlement credit | setl_demo_05 | UNMATCHED; other differently referenced rows aren't forced into it |
| Failed payment | L002 / pay_demo_002; five additional attempts | FAILED ledger case; failed amounts excluded from settlement collections |
| Contradictory reference | L011 shared payment ID but wrong order ID | REVIEW despite otherwise exact amount |
| Competing bank credits | BSET03/BAMB03 | setl_demo_03 REVIEW; one row allocated, other remains visible |
| Incorrect date prevents acceptance | L012 event shifted twenty days | DELAYED, not automatically accepted |
| Duplicate ledger input | Isolated domain fixture | DUPLICATE quarantined, cannot steal good row's allocation |
| Reference with large discrepancy | Isolated settlement/bank fixture | Candidate retained and REVIEW despite difference outside amount discovery window |
| Greedy-steal prevention | Global bank fixture | Strong reference gets the only bank row; weak row stays unallocated |
| Unverified holiday | Three isolated calendar fixtures | No date shift and no factual holiday explanation |

Data period spans January through early February 2026. Bank value/posting dates may differ. Ordinary unrelated entries include credits and debits; the generated opening balance and every subsequent balance are coherent.

The demo ledger has one deliberately absent gateway collection (`L003`) and one partial collection (`L001`). `L010`'s duplicated payment events are not deleted to manufacture a clean settlement net. The authoritative settlement report preserves its original value, so duplicate quarantine leaves a visible integrity discrepancy.
