# Reconciliation — SPEC and four companions

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

Latest user intake governs this UX draft. The original spec and companion files remain unchanged.

## Preserved requirements

- Select or drag/drop exactly one nonempty, suitable `.eml`, then press **Analyze**; show filename/size and clear obsolete results when replacing the file. Keep the source state terms **Upload**, **Sending/startup/analyzing**, **Completed**, **Failed**; empty/selected file states refine Upload. Prevent duplicate submissions and use readable loading text without invented percentages. [API user flow](../../../specs/spec-iap-web-application/api-and-experience.md#user-flow).
- Successful results display exactly **Legit** or **Phishing**, corresponding to `legit` / `phishing`. Errors, startup failure and timeout produce no classification label. Results remain in browser-session memory; uploaded HTML/attachments/tracking resources are not rendered or opened. [Response semantics](../../../specs/spec-iap-web-application/api-and-experience.md#routes-and-response), [privacy](../../../specs/spec-iap-web-application/api-and-experience.md#privacy-authentication-and-concurrency).
- The user adds English interface copy and manual-check/project-demo context. Audience, desktop-first responsive form, light/deep-blue palette and one-page layout stay explicitly assumed. Neither the spec nor its companions establish confirmed visual tokens or a named protagonist.

## Superseded or deferred ideas

The graph's **Legitimate/Spam/Phishing** output is superseded by the latest two-label requirement. Probability, indicators and email inspector remain possible extensions rather than MVP components; model-info, history, accounts and batch scanning remain outside scope. No qualitative idea is silently dropped. [Graph reconciliation](../../../specs/spec-iap-web-application/brownfield-and-evidence.md#source-snapshot), [non-goals](../../../specs/spec-iap-web-application/SPEC.md#non-goals).

## Unresolved items retained

- **2 MiB whole-file cap** is provisional. MIME defects, part/depth/decoded-output limits, error codes and final status mappings remain **Q3**. Timeout deadlines, retry counts/schedule and warm/cold latency budgets remain **Q4**; the UX draft does not convert them into promised values. [Input boundary](../../../specs/spec-iap-web-application/api-and-experience.md#input-and-resource-boundary), [open questions](../../../specs/spec-iap-web-application/SPEC.md#open-questions).
- Next.js/TypeScript/Tailwind and separate FastAPI/Docker are a **proposed stack**, not a finalized architecture or established UI library. Cold-start/unavailable states and a clearly identified local Docker fallback remain relevant; provider timings/quotas are not newly verified promises. [Deployment baseline and fallback](../../../specs/spec-iap-web-application/deployment-and-acceptance.md).
- **E0 — Eligible ML release** is an implementation acceptance gate, not a blocker to this assumed UX draft. Real `phishing` results require reviewed phishing provenance and a coherent validated release; mixed spam/phishing legacy artifacts cannot qualify through renamed labels. UI samples pending E0 must be clearly identified. [Eligible target and E0](../../../specs/spec-iap-web-application/model-and-inference.md).
- The spec's prior absence finding for a web PRD is historical; current source discovery determines which documents now exist. [Evidence boundary](../../../specs/spec-iap-web-application/brownfield-and-evidence.md#current-local-context).

All source-file paths in [the compact extraction](.working/source-spec.md) resolve successfully; original source documents, model artifacts and reports were not edited or executed.
