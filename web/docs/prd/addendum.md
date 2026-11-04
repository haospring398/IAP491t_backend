# PRD Addendum: IAP Email Classification Web Application

This file preserves technical decisions and supporting context without turning the product requirements into an implementation guide. The [SPEC](../spec/SPEC.md) and **all** its companions remain the complete implementation contract; PRD creation does not modify or supersede them. E0 remains unverified.

## Adopted implementation material

| Artifact | Material downstream must retain |
| --- | --- |
| [API and experience](../spec/api-and-experience.md) | Upload states, server/backend routes, success/error schema, provisional status mapping, MIME boundaries, credentials, privacy and temporary-file cleanup |
| [Model and inference](../spec/model-and-inference.md) | Audited two-class target, raw-MIME extraction, ordered features, fitted scaler/Doc2Vec/classifier coherence, release manifest, evaluation and repeated-inference parity |
| [Deployment and acceptance](../spec/deployment-and-acceptance.md) | Proposed stack, measured hosting/fallback selection, E0–E5 windows/evidence and handover checks |
| [Brownfield and evidence](../spec/brownfield-and-evidence.md) | ZIP versus local metadata, historical metrics/graph/report boundaries, research limits and installed BMad routing |
| [Repository instructions](../PROJECT-CONTEXT.md) | Pipeline commands, publication preservation, test/artifact provenance, feature order, Windows corpus handling and source-bias pitfalls |

## Technical baseline and boundaries

`[ASSUMPTION A5: Carry the source-proposed Next.js/TypeScript/Tailwind frontend route and separate FastAPI/Docker backend as the starting point; architecture confirms versions and packaging.]` Frontend and Python backend remain separate. The current demo runs locally; future hosting is unspecified and requires separate qualification.

The proposed request path is `POST /api/analyze` forwarding one multipart Email file to authenticated `POST /v1/analyze`. `GET /health/live` checks the process; `GET /health/ready` returns 503 when the service lacks suitable release/configuration/corpora/target evidence. Success has `analysis_status: completed` and `label: legit|phishing`; errors have `error.code`, `error.message` and `request_id`, without a result or stacktrace. Exact failure mappings remain Q3.

Preserve parse-original-MIME → raw engineered features → clean subject/body for Doc2Vec → fitted scaler transform → concatenation of Doc2Vec then scaled features → one classifier. The current code and pinned local demo run use 40 engineered features and a 100-dimensional embedding, totaling 140. The 2026-10-19 phishing-target candidate records 53 engineered features (153 total), whose 13 attachment-inspection features depend on upstream code absent here (Q7). Actual ordered schema and artifact widths must be checked against the selected release. Use only one verified training run, with hashes, label target/provenance, compatible environment, preprocessing/corpora, inference parameters and decision rule recorded. No dataset loader, training/evaluation, fitting or NLTK download runs inside a request.

Begin with one worker and one active inference, with bounded work; record RNG/concurrency settings so request order cannot change repeated-input labels. Validate timeout behavior in Python as well as the proxy. Classifier/threshold selection uses separate validation; deduplication precedes splitting, the scaler is fitted on training data only, and test independence/probability ROC-AUC follow the adopted repository instructions.

## Delivery dependencies

| Gate | Source planning estimate | Required evidence |
| --- | --- | --- |
| E0 | 1–2 days inventory/trial; retraining separately estimated | Audited legitimate/phishing target; controlled same-run release; real inference; evaluation and initial RAM/startup/latency |
| E1 | Day 3; may overlap E0 | Shared product/UX/architecture/API decisions and small stories with acceptance criteria |
| E2 | Days 4–6 | Inference/API/container; compatible lockfile/corpora; readiness; parity; bounded processing |
| E3 | Days 7–9 | Browser flow through the real Eligible release; result identity, recovery and credential isolation |
| E4 | Days 10–11 | Measured free-hosting decision or documented fallback; HTTPS/envs, restart-safe model and warm/cold/unavailable trials |
| E5 | Days 12–15 | Meaningful build/inference/API/browser checks, privacy inspection, measured latency and tested local/deploy/rollback handover |

These are conditional estimates, not completed stages or a promised delivery date. Local Docker fallback is a demonstration mode and does not prove the cloud route works.

Measure startup and near-limit-email whole-process RAM, real multipart consumption, deadline/recovery and restart-safe artifacts before selecting future hosting. Retain the 2 MiB file cap and prove parity for any optimization. Keep local operation available; no paid trial/plan, database or keepalive cron is required.

Preserve privacy-scrubbed plain-text/HTML/multipart/varied-charset/attachment/malformed fixtures; browser selection/drop, file-change, startup, retry and error checks; repeated label/parity checks; sensitive-log inspection; warm/cold measurements with case counts/sizes/environment. Original diagram Results/training/storage wording and the report must be aligned separately with the accepted target/release; neither raw source is edited by creating this PRD.

## Evidence and claim boundaries

The supplied plan reports ZIP LFS pointers, legacy README 42/142, unpinned dependencies and a hard-prediction AUC column. Those observations are attributed to its snapshot; they are not newly verified current-workspace facts. Local pointer/manifest metadata records a run with 40/100/140 dimensions, but metadata reading does not verify hashes, load the model or establish phishing-only provenance. Earlier completed ML repair work likewise does not complete E0 or the web application. The 2026-10-20 adoption of the 19-10 pipeline adds a phishing-only target mode and validation-selected thresholds. Its 2026-10-19 run reports validation metrics only; test arrays/scores are absent, so no test-set or phishing-only quality claim is established.

The historical mixed-positive XGBoost table is candidate rationale only; target-specific validation must choose the accepted classifier. Do not copy those metrics into a phishing-only result or treat Unicode support as Vietnamese accuracy evidence. E0 and a web demonstration do not complete RQ2/RQ3, ablation, independent-source evaluation or explanation-quality research. Inspect matching logs before repeating expensive evaluation; deliberate report regeneration is a separate action.

The installed catalogue is BMad 6.12.0: subsequent work uses `bmad-ux`, `bmad-architecture`, `bmad-create-epics-and-stories` and `bmad-sprint-planning`; the plan's `bmad-ticket` is not an installed command. Keep the existing installation and established SPEC semantics consistent.

## Supplemental landscape context

Sublime's official CLI documentation describes `.eml` analysis using rules and structured query output; its API accepts base64-encoded raw `.eml`. This is an investigation/rule-analysis workflow with a broader output than the authorized binary research demonstration. [Official CLI workflow](https://docs.sublime.security/reference/analysis-api-cli), [official analysis API](https://docs.sublime.security/reference/analyzemessage).

PhishTool's official privacy policy describes submitted-email/attachment/analysis retention and acknowledges personal information in email chains. The policy states a 2021-06-26 modification date; direct retrieval returned 403 during this operation, so this observation relies on indexed official-page content and does not certify its current implementation. [Official privacy policy](https://www.phishtool.com/privacy-policy).

**Inference:** These examples help distinguish email investigation from this MVP's classification session; they do not justify adding an inspector or scores; the AD-14 factor explanation was approved separately on 2026-10-24. Raw-email processing still carries content/metadata even when the result is one label, so the demo's transient-handling claim needs implementation evidence. This supplemental context does not override the user's plan or SPEC, and introduces no market-size, novelty or commercial-demand claim.
