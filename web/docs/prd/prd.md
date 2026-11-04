---
title: IAP Email Classification Web Application
status: final
created: 2026-10-05
updated: 2026-10-24
inputs:
  - ../IAP_Web_Application_Plan.md
  - ../spec/SPEC.md
---

# PRD: IAP Email Classification Web Application

Hosting update 2026-10-19: the current cleanup supersedes the earlier deployment selection. The demo runs locally and future hosting is unspecified. This update does not validate unrelated original product requirements, E0 or phishing-only quality.

Pipeline update 2026-10-20: the offline pipeline now follows the 19-10 upstream version with a phishing-only training mode and validation-selected thresholds. This provides candidate evidence toward Q1/Q2 but does not pass E0: the upstream copy is incomplete and its candidate run is not reproducible with current code. FR/NFR scope is unchanged.

Explanation update 2026-10-24: MVP scope now includes a per-result explanation (FR-11) showing the main factors behind the served classifier's decision, computed exactly from that model. It explains model behavior only; it does not establish phishing quality. How factors reflecting dataset construction (currently `is_html`) are presented remains Q9.

## Document purpose

Define the MVP's user behavior, scope and acceptance criteria for the project team and downstream UX, architecture and story planning. This PRD builds on the [web plan](../IAP_Web_Application_Plan.md) and [SPEC](../spec/SPEC.md); read the SPEC's companions for the complete implementation contract. Technical decisions and supporting context belong in [addendum.md](addendum.md).

Finalizing this document does not complete E0 or certify a working application. Changes to the product contract must also be reconciled through `bmad-spec`.

## Vision and target users

Turn the existing offline email-classification research into a usable demonstration: a participant submits one exported email and sees the eligible model's `legit` or `phishing` result. The demonstration must show that the browser and the verified research pipeline work together without presenting spam-inclusive results as phishing-only evidence.

The primary role is a **demo participant** with an exported email. The **project team** verifies the release, operates the demonstration and provides reproducible handover evidence.

**Job to be done:** When I have an exported email, I want to submit it and see the research pipeline's classification.

**Source-described session:** Choose or drop one Email file, inspect its name/size, start Analysis, follow sending/startup/processing, and receive the filename with one result. If a Processing error occurs, choose another file or retry within the allowed policy.

Roles and the job to be done restate the supplied plan; no interviewed personas, enterprise requirements or named-persona journeys were supplied.

## MVP scope and non-goals

MVP includes the single-file session, two-label result, recoverable errors, release/readiness evidence, transient/private input handling and the verified demonstration/handover below. E0 blocks real prediction acceptance. Frontend and Python backend run locally; future hosting is unspecified, with free hosting preferred and feasibility to be measured.

Explicit non-goals:

- In-app instructions or help panels for exporting email as `.eml`.

- Score/confidence/risk displays, Spam or uncertain output labels, approximate or sampled explanations (for example LIME), email inspector, full feature tables, raw feature values, model-info pages and JSON export. FR-11's bounded factor explanation is the only explanation in scope.
- Gmail integration, browser extensions, accounts, batch scanning, server history, databases and automated inbox handling.
- Paid trials/plans, required GPUs, keepalive cron or unsupported counters of phishing prevented.
- Claims of Vietnamese accuracy, phishing-only quality or completed RQ2/RQ3 without the corresponding experiments.

`[ASSUMPTION A3: The roughly 15-working-day web estimate assumes an Eligible release and compatible environment; relabeling/retraining requires separate estimation.]` Clearly marked samples may support UX/API work while E0 is pending.

## Glossary

- **Email file:** One exported `.eml`, including encoded attachments.
- **Analysis:** One attempt to validate an Email file and obtain its classification.
- **`legit`:** Class 0, reviewed legitimate email in the defined dataset; it does not automatically include ordinary non-phishing spam.
- **`phishing`:** Class 1, phishing confirmed by source provenance or review.
- **Processing error:** An unsuccessful Analysis; it is not a third email class.
- **Eligible release:** A coherent, verified model release with the required target, provenance, environment and evaluation evidence.
- **E0:** The evidence gate establishing an Eligible release and initial resource feasibility.
- **Fixture:** A privacy-scrubbed verification email, or a visibly marked sample response used while real-model integration is pending.

## Features and functional requirements

### 1. Submit an Email file

- **FR-1 — Submit one file.** A demo participant can select or drag/drop one Email file, see its filename/size and start Analysis. **Acceptance:** Both submission methods work for one file; no batch or account workflow is required.
- **FR-2 — Reject unsuitable input.** Invalid input is rejected before model inference. **Acceptance:** Empty files, unsuitable extension/structure, insufficient useful content and files exceeding the configured whole-file limit produce Processing errors. `[ASSUMPTION A1: Start with the source-proposed 2 MiB cap, including encoded attachments; confirm actual multipart limits before deployment.]` MIME defect and parser policies remain open under Q3.

### 2. Obtain a trustworthy result

- **FR-3 — Classify with an Eligible release.** Successful Analysis returns exactly `legit` or `phishing`. **Acceptance:** Mapping uses the reviewed target; mixed spam/phishing positives cannot qualify by changing a display label. Ordinary spam and unknown positives are excluded from the default benchmark unless separately evidenced as phishing.
- **FR-4 — Preserve result identity.** The participant sees the analyzed filename and one result only after successful inference. **Acceptance:** Processing errors never produce a classification; changing files removes the previous result. Sample responses are visibly marked and cannot satisfy real-model acceptance.
- **FR-11 — Explain a result.** With a successful result, the participant sees up to five main factors that moved the served classifier toward or away from the positive class, each with a direction and a relative strength, and a notice that factors describe the model's reasoning, not proof about the email. **Acceptance:** Factors are computed exactly from the served classifier for that email (contributions plus base value reproduce the model output); the text-embedding dimensions appear as one text factor; no score, probability, raw feature value or email content is shown; identical input yields identical factors regardless of request order or restart; errors and obsolete attempts show no factors; a release without an exact explanation method shows the label only. Presentation of dataset-shortcut factors remains Q9.

### 3. Follow processing and recover

- **FR-5 — Show readable state.** Sending, backend startup, processing, completion and failure are distinguishable. **Acceptance:** State is expressed in text, no fabricated percentage is shown, duplicate submissions are prevented and a late prior-file response cannot replace the current file's state.
- **FR-6 — Recover from failures.** The participant can choose another file or retry according to a bounded policy. **Acceptance:** Input problems, unavailable model, busy service, unreachable backend, timeout and provider non-JSON startup responses produce actionable Processing errors without a result. Retry/deadline settings remain open under Q4.

### 4. Establish service and release readiness

- **FR-7 — Report readiness honestly.** Callers can distinguish a running process from a service ready for Analysis. **Acceptance:** Unsuitable model artifacts, configuration, corpora or target evidence prevent readiness; internal metadata identifies the release used without logging email content.
- **FR-8 — Establish E0 evidence.** The project team can demonstrate that the release qualifies for the requested target. **Acceptance:** Reviewed per-source label provenance, verified same-run artifacts/dimensions/configuration, real Email file inference, target-specific validation/test results and initial resource measurements are recorded. Historical mixed-positive metrics do not certify the new target.
- **FR-9 — Preserve inference agreement.** Browser/API integration uses the verified pipeline's decisions. **Acceptance:** Harness and API agree on Fixture features/results; repeated identical requests retain their label regardless of request order under the recorded inference method. Q2/Q4 define unresolved settings and vector tolerance.

### 5. Demonstrate and hand over

- **FR-10 — Deliver a reproducible demonstration.** The project team can operate the measured deployment path and hand it over. **Acceptance:** A working free deployment or explicitly identified fallback, restart-safe release, important browser/API/error checks, warm/cold measurements, run/deploy/rollback guidance and a tested local Docker demonstration are available. A local fallback does not certify the cloud path.

## Cross-cutting requirements

- **NFR-1 — Data handling:** Email files and results are transient; temporary uploads are cleaned on success/failure. Logs/analytics omit raw email, subject, sender, recipient and filename. Allowed operational fields are request ID, byte count, duration, status and release ID. Explanation factors are result data: transient and never logged.
- **NFR-2 — Isolation and credentials:** Uploaded HTML/scripts, URLs and attachments are neither executed nor fetched; processing makes no DNS/WHOIS/remote attachment requests. Backend credentials remain server-side and are verified by the backend; the browser never receives them.
- **NFR-3 — Bounded operation:** Input size, MIME parts/depth/decoded output, active inference, runtime and retries are bounded; excess work is rejected rather than queued indefinitely. A frontend timeout must not leave backend work unbounded. Exact budgets remain open under Q3/Q4. `[ASSUMPTION A2: Approximately 400 MiB peak RAM is an initial project target, not a provider limit or demonstrated result.]`
- **NFR-4 — Reproducibility:** Use the same verified release for preprocessing, scaling, embedding, classification and evaluation, with compatible pinned dependencies/corpora. Uploads do not retrain or refit the pipeline. Preserve previous runs and the selected release on failed publication.
- **NFR-5 — Readable interaction:** Upload, results and recovery remain understandable through text rather than color alone. Detailed UI design/copy follows from UX work without adding features to the MVP.

## Success and counter-metrics

Measure the agreed Fixture set and release evidence; report case counts and failures rather than only successful uploads. These are planned acceptance targets, not achieved results.

- **SM-1 — Real session completion:** Every agreed valid Fixture completes the browser-to-Eligible-release path with the matching filename and two-label result and, where the release supports it, an exact factor explanation. Validates FR-1, FR-3, FR-4, FR-10 and FR-11.
- **SM-2 — Error integrity:** Every required invalid/unready/busy/connectivity/timeout case returns a Processing error without a classification. Validates FR-2, FR-6 and FR-7.
- **SM-3 — Reproducible handover:** E0, harness/API agreement, repeatability, privacy/credential checks and the documented local demonstration pass their acceptance checks. Validates FR-8, FR-9, FR-10 and NFR-1 through NFR-4.
- **SM-C1 — Quality and resource costs:** Report target-specific false positives/negatives, rejected inputs, failures, warm/cold latency and peak RAM alongside SM-1. Minimum model-quality and final operational thresholds remain open under Q2/Q4; upload success and a high phishing-label count are not efficacy metrics.
- **SM-C2 — Integrity violations:** Covered checks must find zero fabricated error-case labels, stale-file results, request-order label changes, exposed credentials, sensitive-content retention/logging, or factor lists that fail to reproduce the model output or change across repeated input. Counterbalances SM-1 through SM-3; passing covered checks is not a production-wide guarantee.

## Dependencies and open questions

UX/architecture and visibly marked samples can proceed under the established scope; unresolved budgets and hosting evidence block the associated implementation sign-off. The [addendum](addendum.md#delivery-dependencies) preserves E0–E5 ordering.

`[ASSUMPTION A4: Owners below identify project workstreams; the team still assigns individual people.]`

| ID | Unresolved decision/evidence | Owner | Revisit condition |
| --- | --- | --- | --- |
| Q1 | Reviewed dataset snapshot, per-source legitimate/phishing provenance and whether a new release is required | ML workstream | Before E0 can pass |
| Q2 | Selected classifier/release, compatible environment, inference settings/source revision and model-quality acceptance criteria | ML workstream | Before real prediction acceptance |
| Q3 | MIME defects, parser limits, precise error codes and HTTP mapping | API workstream | Before E2/E3 contract acceptance |
| Q4 | Warm/cold budgets, Python/proxy deadlines, retries and inference/vector tolerance | API and deployment workstreams | Before E2/E4 resource/behavior acceptance |
| Q5 | Measured free host, account eligibility/quotas and public-demo access/rate controls | Deployment workstream | Before E4 cloud deployment |
| Q7 | Upstream revision supplying the missing pipeline modules/functions needed for training, tests and the 53-feature candidate | ML workstream | Before E0 inventory or retraining |
| Q8 | Whether the qualified release stays on Doc2Vec + engineered features or adopts BERT | ML and architecture workstreams | Before selecting a BERT release |
| Q9 | How factors that reflect dataset construction rather than phishing (currently `is_html`: 0.7% of legitimate vs 94.9% of phishing test emails; 11% false-positive rate on HTML legitimate mail in run 2026-10-23_web2) are retrained, labelled or excluded in explanations | ML and UX workstreams | Before FR-11 acceptance |

No numeric accuracy, latency or throughput target has been invented. E0 evidence and the applicable decisions above must be resolved before claiming the associated feature is accepted.

## Assumptions index

- **A1 — FR-2:** Initial 2 MiB whole-file cap from the source proposal.
- **A2 — NFR-3:** Approximately 400 MiB peak RAM as a provisional project target.
- **A3 — MVP scope:** Roughly 15 working days conditional on an Eligible release; ML work separately estimated.
- **A4 — Open questions:** Role-based workstream owners pending assignment of people.
- **A5 — Addendum:** Proposed implementation stack remains subject to architecture and compatibility measurements.
