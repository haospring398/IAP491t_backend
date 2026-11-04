# PRD source extract for the UX draft

Extracted 2026-10-05. This is a source summary, not a new product contract. Latest user instructions take precedence where they narrow or clarify the UX.

## Sources

- [PRD](../../prd/prd.md), especially Vision and target users, MVP scope and non-goals, Features and functional requirements, and Cross-cutting requirements.
- [PRD addendum](../../prd/addendum.md), especially Technical baseline and boundaries, Delivery dependencies, and Evidence and claim boundaries.

## Roles and journeys, preserved exactly

- Source roles: **demo participant** and **project team**. Job to be done: submit an exported email and see the research pipeline's classification.
- The source session is labeled **Source-described session**; it has no separate journey title or named protagonist. Its sequence is choose/drop one Email file, inspect filename/size, start Analysis, follow sending/startup/processing, then receive filename and one result. Processing errors lead to choosing another file or bounded retry.
- The PRD explicitly states that no interviewed personas or named-persona journeys were supplied. Therefore any named protagonist in EXPERIENCE.md must be visibly tagged `[ASSUMPTION]`, not attributed to this PRD. Latest user candidate groups (individuals, project members, lecturers) are also assumptions.

See [PRD: Vision and target users](../../prd/prd.md#vision-and-target-users).

## MVP surfaces and behavior

- One exported `.eml`, selected with a file picker or drag/drop; show filename and size; provide export guidance; Analysis starts explicitly. This supports the user's single-page upload/button/result layout.
- Reject unsuitable inputs before inference: empty file, unsuitable extension/structure, insufficient useful content, excessive whole-file size. The proposed **2 MiB including encoded attachments** cap is **PRD assumption A1**, not an accepted measured limit. Parser and MIME policy are unresolved Q3.
- Successful output is exactly domain label `legit` or `phishing`, with the analyzed filename. Latest user presentation is **Legit** / **Phishing** in an English UI; capitalized presentation does not change the API/domain labels.
- A result appears only after successful inference. Replacing a file clears its prior result. A stale response from a prior file cannot replace current state.
- Prevent duplicate submission and distinguish **sending**, **backend startup**, **processing**, **completion**, **failure** through text. No fabricated percentage. The user's requested top-level five states can group sending/startup/processing beneath **analyzing** while preserving readable phase distinctions.
- Support bounded retry or replacement for invalid input, unavailable model, busy service, unreachable backend, timeout and provider non-JSON startup responses. Exact budgets/retry policy remain Q4; do not invent seconds or retry counts.
- **Processing error** is an unsuccessful Analysis, never a third email class. Do not show a label, fallback prediction, or previous success result in an error state.

See [PRD: Features and functional requirements](../../prd/prd.md#features-and-functional-requirements).

## MVP exclusions and result honesty

- Excluded from the MVP: probability/confidence/risk, Spam/uncertain labels, indicators, XAI/LIME, email inspector, feature tables, model-info page and JSON export. The latest user expressly reserves probability, indicators and inspector for extensions.
- Also excluded: accounts, inbox integration, Gmail/browser extension, batch scan, server history/database, automated inbox handling and efficacy counters.
- Real predictions require an **Eligible release** (E0). A visibly marked sample may support UX/API work while E0 is pending, but cannot satisfy real-model acceptance. A prototype must not imply E0 has passed.
- Historical spam-inclusive positive metrics do not certify a phishing-only target; changing the display label does not qualify a release. Avoid accuracy claims, promises that an email is safe, or claims of Vietnamese accuracy.
- Frontend/backend readiness and release evidence are implementation/handover concerns. The MVP does not require a dedicated readiness, model-information or release screen; user-facing unavailability belongs in actionable processing/error states.

See [PRD: MVP scope and non-goals](../../prd/prd.md#mvp-scope-and-non-goals), [PRD: Glossary](../../prd/prd.md#glossary), and [addendum: Evidence and claim boundaries](../../prd/addendum.md#evidence-and-claim-boundaries).

## Privacy and accessibility floor

- Files/results are transient; temporary uploads are cleaned after success/failure. Logs/analytics must omit raw email, subject, sender, recipient and filename. Permitted operational fields: request ID, byte count, duration, status, release ID.
- Uploaded HTML/scripts, URLs and attachments are not executed or fetched; no DNS/WHOIS/remote-attachment request. Credentials stay server-side. These are requirements that need implementation evidence, not already verified privacy guarantees.
- Render filenames as plain text. Email content/attachment preview is outside this MVP; do not introduce a content inspector or execute embedded email HTML.
- PRD accessibility requirement NFR-5: upload, results and recovery must remain understandable through text, not color alone. It does not define a complete keyboard/screen-reader standard. Additional keyboard, semantic-label, focus and live-status rules should be captured as explicit UX draft decisions/assumptions.
- Readable error text must be actionable; error response has code/message/request ID without a result or stacktrace. The UI need not expose internal metadata unless useful to recovery/support.

See [PRD: Cross-cutting requirements](../../prd/prd.md#cross-cutting-requirements) and [addendum: Technical baseline and boundaries](../../prd/addendum.md#technical-baseline-and-boundaries).

## Reconciliation and unresolved choices

1. **No product-scope conflict with the latest user intake:** PRD already specifies manual single `.eml`, explicit start, exactly `legit|phishing`, transient processing and no result for errors.
2. **State granularity needs retention:** latest five visible states are compatible with FR-5 only if the analyzing state still exposes sending/startup/processing as text phases; one generic spinner alone loses source requirements.
3. **Source diagram mismatch is acknowledged:** addendum requires original Results/training/storage wording to be aligned separately; a raw graph with three results cannot override this accepted two-class UX. PRD creation did not alter the raw graph.
4. **Persona/device/style/layout are unresolved design assumptions:** PRD confirms demo participant/project team but supplies no interviewed personas, desktop/mobile priority, colors or concrete page composition. Preserve `[ASSUMPTION]` markings requested by the user for these choices.
5. **No fabricated operational commitments:** 2 MiB is provisional A1; timeout/retry/warm-cold budgets are Q4; parser policy is Q3. Display configured limits and real states when implemented.
6. **E0 remains unverified:** UX drafts and marked samples can proceed, but cannot certify actual phishing-only inference, deployment, privacy enforcement or readiness.

See [PRD: Dependencies and open questions](../../prd/prd.md#dependencies-and-open-questions) and [addendum: Delivery dependencies](../../prd/addendum.md#delivery-dependencies).
