# UX source extract — web spec and all four companions

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

Read on 2026-10-05. This is source extraction, not a verified model/API/deployment claim. The latest user intake overrides incompatible source details: manual selection or drag/drop of one `.eml`, an explicit **Analyze** action, exactly **Legit** / **Phishing** rendered for successful responses (`legit` / `phishing` in the contract), English UI, and processing failures with no classification. Probability, indicators and an email inspector are extensions only. Audience, desktop-first responsive form, light/deep-blue palette and single-page arrangement remain `[ASSUMPTION]` decisions for the draft.

## Sources read completely

- [SPEC.md](../../../../specs/spec-iap-web-application/SPEC.md) — product scope, CAP-1–CAP-6, constraints, assumptions, Q1–Q5.
- [api-and-experience.md](../../../../specs/spec-iap-web-application/api-and-experience.md) — upload flow, response semantics, input/privacy/concurrency boundaries.
- [model-and-inference.md](../../../../specs/spec-iap-web-application/model-and-inference.md) — target eligibility, coherent release, raw-email inference, E0 gate.
- [deployment-and-acceptance.md](../../../../specs/spec-iap-web-application/deployment-and-acceptance.md) — proposed stack, demonstration constraints, acceptance evidence.
- [brownfield-and-evidence.md](../../../../specs/spec-iap-web-application/brownfield-and-evidence.md) — historical observations versus current evidence and graph reconciliation.

## Behavior and terminology to preserve

One exported email per attempt; display its filename and size before analysis and filename with the successful label. Provide export guidance. Changes of file clear obsolete results; duplicate submissions are prevented. Only transient uploads and browser-session results are supported; no history, accounts, batch inbox scanning or database. Uploaded HTML is never rendered; URLs, attachments and tracking images are never opened/fetched. Sources: [user flow](../../../../specs/spec-iap-web-application/api-and-experience.md#user-flow), [privacy](../../../../specs/spec-iap-web-application/api-and-experience.md#privacy-authentication-and-concurrency), [non-goals](../../../../specs/spec-iap-web-application/SPEC.md#non-goals).

Exact source state/flow names are **Upload**, **Sending/startup/analyzing**, **Completed**, **Failed**. The source defines no named-protagonist journey titles. The draft may distinguish empty selection, file selected, sending, backend startup, analyzing, success and failure as UX states while retaining these source names in its source mapping. Loading uses readable text without invented percentage progress. Failure covers unsuitable input, insufficient content, unavailable model, busy service, connectivity failure and timeout; offer another file or bounded retry. Source: [user flow](../../../../specs/spec-iap-web-application/api-and-experience.md#user-flow).

## Validation values and error contract

| Boundary | Source contract / certainty |
| --- | --- |
| Files per attempt | Exactly one suitable, nonempty `.eml`. |
| Whole-file size | **2 MiB (2,097,152 bytes)**, including encoded attachments, is a proposed initial default, not a finalized operational limit. |
| Structural validity | Extension alone and client MIME type are insufficient; backend validates suitable email structure and useful content. |
| MIME resource limits | Part count, depth, decoded output and defect-acceptance policy are unresolved Q3; invent no numeric values. |
| Wrong/empty/malformed/insufficient input | Proposed HTTP 400 or 422. |
| Oversize | Proposed HTTP 413. |
| Busy | Proposed HTTP 429 or 503. |
| Model unready | HTTP 503; readiness must also be 503 when unready. |
| Upstream timeout | Proposed HTTP 504. |
| Unreachable/authentication/provider startup | Final mappings/codes unresolved Q3; provider HTML/non-JSON responses become recoverable application errors. |

Sources: [input and resource boundary](../../../../specs/spec-iap-web-application/api-and-experience.md#input-and-resource-boundary), [routes and response](../../../../specs/spec-iap-web-application/api-and-experience.md#routes-and-response), [Q3/Q4](../../../../specs/spec-iap-web-application/SPEC.md#open-questions).

`POST /api/analyze` is the frontend server proxy; `POST /v1/analyze` is the Python inference endpoint. Success is `{"analysis_status":"completed","label":"phishing"}` with `label` strictly `legit|phishing`; `analysis_status` is a request state, never a third class. The minimal response does not require filename, probabilities, raw email, features or indicators. Failure contains `error.code`, `error.message`, `request_id`, omitting labels and stacktraces. The browser retains its selected filename. `/health/live` and `/health/ready` are distinct. Source: [routes and response](../../../../specs/spec-iap-web-application/api-and-experience.md#routes-and-response).

Timeout durations, warm/cold latency budgets, retry schedule and Python/proxy deadlines remain **Q4**. No fixed retry count/wait duration or elapsed-time SLA is committed. Client/proxy timeout does not itself stop Python inference; the service must bound task runtime/resources and concurrency. Begin with one active inference and reject excess work clearly. UX should not claim that timed-out work stopped, start unbounded retries, or simulate elapsed completion. Sources: [routes and response](../../../../specs/spec-iap-web-application/api-and-experience.md#routes-and-response), [privacy and concurrency](../../../../specs/spec-iap-web-application/api-and-experience.md#privacy-authentication-and-concurrency).

## ML semantics affecting honest results

Class 0 means reviewed legitimate email → `legit`; class 1 requires confirmed phishing provenance/review → `phishing`. Ordinary spam and unknown positives are excluded from the default benchmark; renaming mixed-positive legacy models is insufficient. Real predictions require **E0 — Eligible ML release**. Clearly marked samples can support UI/API development pending E0 but cannot satisfy real inference acceptance. Sources: [eligible target](../../../../specs/spec-iap-web-application/model-and-inference.md#eligible-training-target), [constraints](../../../../specs/spec-iap-web-application/SPEC.md#constraints).

Inference uses original MIME bytes → raw engineered features before cleaning → fitted Doc2Vec inference → same-run training-fitted scaler transform → Doc2Vec then scaled engineered-feature concatenation → one same-run classifier. Verify the release manifest/hashes/configuration/corpora/target; unsuitable releases fail startup/readiness. Expected 40 engineered + 100 embedding = 140 input dimensions are internal checks, not required UI panels. Historical selected-run metadata and old mixed-positive metrics are not proof of phishing-only eligibility; no accuracy, confidence or release-ready claim belongs in the draft. Sources: [feature contract](../../../../specs/spec-iap-web-application/model-and-inference.md#feature-contract), [artifact contract](../../../../specs/spec-iap-web-application/model-and-inference.md#artifact-and-manifest-contract), [brownfield state](../../../../specs/spec-iap-web-application/brownfield-and-evidence.md#current-local-context).

## Stack and demonstration limits

Next.js/TypeScript/Tailwind, separate FastAPI/Docker backend and initial one Uvicorn worker are the **proposed baseline**, pending architecture/version pinning; no established UI component library is committed. Hosting is unspecified; future resource/startup behavior needs measurement before it becomes a UI promise. Preserve readable startup/unavailable states, test the demo before presentation and support a documented local Docker fallback labeled as a local demonstration. No paid plan/trial, GPU, database or keepalive cron is requested. Sources: [baseline](../../../../specs/spec-iap-web-application/deployment-and-acceptance.md#proposed-implementation-baseline), [hosting/fallback](../../../../specs/spec-iap-web-application/deployment-and-acceptance.md#hosting-feasibility-and-fallback).

Keep backend credentials server-side and logs free of raw email, subject/sender/recipient/filename; permitted internal fields include request ID, byte count, duration, status and release ID. Provider/public access controls and quotas remain Q5. Source: [privacy](../../../../specs/spec-iap-web-application/api-and-experience.md#privacy-authentication-and-concurrency).

## Conflicts, missing evidence and open decisions

- The referenced graph's three outputs **Legitimate/Spam/Phishing** conflict with the latest two-label requirement; use **Legit/Phishing**. Graph probability/indicators/inspector fields are deferred. Model storage is required; results stay in session memory. Neither the source spec nor this extraction claims the image was revised. [Graph reconciliation](../../../../specs/spec-iap-web-application/brownfield-and-evidence.md#source-snapshot).
- The spec reported no web PRD/UX/architecture before its creation. That is a historical observation; another extractor/root must confirm whether a PRD now exists. Do not treat the spec's prior scan as current absence. [Current local context](../../../../specs/spec-iap-web-application/brownfield-and-evidence.md#current-local-context).
- No palette, layout, intended audience, named protagonist, typography or spacing is specified here. Tag the user's proposed audience/device/color/layout choices and any new visual tokens as assumptions.
- Q1/Q2 (eligible release), Q3 (input/error details), Q4 (runtime/retry policy), Q5 (deployment/public-access controls) remain implementation-readiness questions, not reasons to withhold a clearly marked UX draft. [Open questions](../../../../specs/spec-iap-web-application/SPEC.md#open-questions).

Extraction validation: all five requested files read; no source files, draft spines, model artifacts or reports changed; no model execution, tests, metrics verification, browsing or deployment performed.
