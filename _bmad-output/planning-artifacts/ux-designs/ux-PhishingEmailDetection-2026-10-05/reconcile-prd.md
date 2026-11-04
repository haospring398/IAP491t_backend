# PRD → UX Draft Reconciliation

Sources: [PRD](../../prds/prd-PhishingEmailDetection-2026-10-05/prd.md) and [addendum](../../prds/prd-PhishingEmailDetection-2026-10-05/addendum.md). This records UX proposals; source originals were not edited.

| Source material | Draft treatment |
| --- | --- |
| Roles **demo participant**, **project team**; **Source-described session** | Preserved in EXPERIENCE.md; named Linh is explicitly `[ASSUMPTION A1]`. No interviewed persona is claimed. |
| FR-1/2 upload, name/size, export guidance, pre-inference input rejection | Covered by upload/file/help patterns and input-error rows. Source-proposed 2 MiB cap and parser acceptance stay open. |
| FR-3/4 two-label, eligible-release and result identity | Exactly `legit|phishing`, presented Legit/Phishing; previous/stale output suppressed. E0 is unverified; marked samples cannot qualify real inference. |
| FR-5/6 sending/startup/processing and recoverable failure | Five top-level states with truthful analyzing subphases and explicit recovery journey; no false progress, third class or unbounded retry. |
| FR-7–10 readiness, evidence, parity and reproducible demonstration | Preserved as implementation/handover dependencies rather than new product screens or accepted evidence. |
| NFR-1–5 privacy, isolation, bounded operation, reproducibility and readability | Privacy copy conditional on enforcement, no content execution/fetching, exact request identity, text labels and proposed accessibility floor. |
| Latest user design direction | A1 audience, A2 devices, A3 visual values, A4 single-page composition, A5 detailed interaction/accessibility remain visibly unconfirmed proposals. English and core `.eml`/Analyze/two-label behavior are confirmed. |

No PRD MVP requirement is deliberately dropped. Scores/indicators/inspector and other non-goals remain deferred as already authorized; source engineering details remain upstream rather than duplicated as UI content. Open items are upload/parser limits, runtime/retry budgets, eligible target/release, privacy enforcement and measured deployment. Both spines remain `status: draft`.
