# Architecture input contracts

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

Read-only extraction, 2026-10-05. This working artifact records requirements and open design choices; it does not resolve E0, verify artifacts, select a host or certify implementation. The SPEC and all companions remain the canonical implementation contract; final PRD/addendum and the latest draft UX pair provide traceability. No source document or imported graph was changed.

## Source authority and settled scope

- One nonempty, structurally suitable `.eml`, selected or dropped, with filename/size visible and **explicit Analyze**. Selecting never transmits content. English success labels are exactly **Legit** and **Phishing**, domain values `legit` and `phishing`. Errors contain no class. Score/confidence/risk, indicators and inspector remain extensions. [S], [P], [X]
- Class 0 means reviewed legitimate email; class 1 means evidenced phishing. Ordinary spam and unknown positives are excluded from the default target. Existing mixed-positive models cannot qualify through relabeling or `INCLUDE_SPAM=False` alone. [M], [P]
- Real predictions require E0. Visibly marked samples can unblock UI/API work but cannot count as real-model acceptance; UX proposes “Sample result — not a real analysis,” never a third class. [M], [X]
- The frontend and Python backend remain separate; hosting is unspecified after the 2026-10-19 cleanup. Next.js/TypeScript/Tailwind, FastAPI/Docker, pytest and Playwright remain the proposed implementation baseline; versions, packages and backend host need architecture/compatibility decisions. Future hosting requires separate measurement and qualification. [S], [PA], [D]
- Preserve raw-email extraction before cleaning, ordered `preprocess.FEATURE_NAMES`, fitted-training scaler, same-run Doc2Vec/classifier and concatenation **Doc2Vec then scaled engineered features**. The 40/100/140 widths are checked expectations, not a hardcoded schema. No training, dataset loading, fitting, evaluation or corpus downloads in requests. [M], [A]
- The graph is reference data. Its MIME/raw-structural versus cleaned-Doc2Vec branches support this split, but its three-class results, probability/indicators/inspector and “Model + results storage” do not authorize those product features or retained email results. It does not explicitly specify scaler or concatenation order. Its missing-image history has been superseded by the inspected unchanged import. [G], [X]

## Capability and requirement coverage

| Capability | Functional coverage | Cross-cutting architecture implications |
| --- | --- | --- |
| CAP-1: submit one email | FR-1, FR-2 | NFR-1/2/3/5: transmission only on Analyze; structural validation; bounded uploads/parser; safe metadata and readable errors |
| CAP-2: eligible binary prediction | FR-3, FR-4, FR-9 | NFR-4: target provenance; coherent release; exact label mapping; no class on failure; feature/label parity |
| CAP-3: progress/recovery | FR-4, FR-5, FR-6 | NFR-3/5: duplicate suppression, attempt identity, stale-response suppression, truthful text states and bounded retry/deadlines |
| CAP-4: readiness/attribution | FR-7 | NFR-1/2/4: liveness differs from readiness; unsuitable release/configuration/corpora/target blocks readiness; private operational attribution |
| CAP-5: reproducible release | FR-8, FR-9 | NFR-4 plus resource evidence: E0 provenance, hashes/dimensions/environment, target-specific evaluation, real MIME inference and repeatability |
| CAP-6: measured demonstration/handover | FR-10 | NFR-1 through NFR-5: measured deployment/fallback, browser/API/build/privacy checks, restart-safe artifacts and tested local Docker/run/deploy/rollback guidance |

FR/NFR meanings and acceptance remain those of the final PRD. NFR-1 is transient handling; NFR-2 isolation/credentials; NFR-3 bounded operation; NFR-4 reproducibility; NFR-5 readable interaction. No numeric accuracy, latency, throughput or concurrency SLA has been supplied. [S], [P]

## API boundary currently specified

| Boundary | Existing contract | Still needs a common decision |
| --- | --- | --- |
| Browser → proxy | `POST /api/analyze`, one multipart email | Multipart field name; duplicate/unknown-part policy; request-ID source/propagation; precise whole-request overhead limit |
| Proxy → backend | Authenticated `POST /v1/analyze`, server-side token | Header name/secret config, outbound deadlines, response validation/error normalization and retryability |
| Liveness | `GET /health/live`, minimal process information | Response body/schema and privacy/access policy |
| Readiness | `GET /health/ready`; 503 if unsuitable model/configuration/corpora/target | Ready success body/status details; internal readiness reasons and non-sensitive release attribution |
| Success | `{"analysis_status":"completed","label":"phishing"}`; `label` exactly `legit|phishing` | Public request ID or release ID is not required by current minimal shape; strict additional-field/version policy needs architecture |
| Failure | `error.code`, `error.message`, `request_id`; no label or stacktrace | Enumerated codes, exact JSON envelope, status mapping, retry indication/headers and generic exception policy |

Filename belongs to the browser's captured attempt; it is not required in success JSON. Model/release identity and feature/timing checks are internal verification data, not MVP panels. Invalid success payloads are errors, never guessed classes. Provider HTML/non-JSON startup/error content must be normalized into an actionable error; raw HTML and stacktraces never reach the UI. [API], [PA], [X]

The source proposes 400 **or** 422 for empty/unsuitable/malformed/insufficient-content input; 413 for oversize; 429 **or** 503 for busy; 503 for model unready; 504 for upstream timeout. Unreachable upstream, backend authentication failure and provider startup responses have no final mapping. Q3 owns final codes/statuses. Choosing one implementation independently would produce incompatible clients. [API]

## Input, time, concurrency and resource budgets

- **Provisional whole-email cap:** 2 MiB, including encoded attachments. It is not a decoded-body limit and does not include guaranteed multipart headroom. Browser/proxy/backend must agree; actual complete multipart request needs deployment measurement. Approximately **400 MiB peak RAM** is an initial project target, not a demonstrated measurement or provider guarantee. [S], [API], [D], [P]
- Extension plus suitable email structure is required; client MIME type is untrusted. MIME defect acceptance, missing-header behavior, useful-content rule, part count, nesting depth, decoded-byte/output size and associated error codes remain Q3. The parser/adapter policy must be versioned with the release rather than silently changing an old model. [API], [M]
- One worker and one active inference are the prescribed initial baseline. Reject excess work clearly; no unbounded queue. The admission scope (whole parser+inference versus model-only), busy status, cancellation/kill boundary and handling after disconnect remain design calls. Doc2Vec shared RNG/concurrency must prevent repeated-input labels changing with request order. Exact inference settings/vector tolerance remain Q2/Q4. [M], [PA]
- No fixed warm/cold latency, startup allowance, proxy timeout, Python task timeout, retry count, backoff interval or throughput target is agreed. Q4 must establish them and measurement evidence. A client/proxy timeout does not stop Python computation; backend execution itself must be bounded. Do not present the conditional ~15 working days or E0 inventory 1–2 days as an operational deadline. [API], [D], [P]
- UX requires manual bounded Retry with no automatic retry loop, no overlapping attempts, and no Cancel action/server-stop promise. Truthful default “Analyzing…” can be used when sending/startup/processing phases are not observable. More specific phases must follow reliable evidence. [X]

## Data ownership, retention and secrets

The browser owns selection, exact display filename, attempt identity and result state; all are transient session memory. The proxy owns backend secret and request forwarding/normalization. The Python service owns validation/parsing, release loading/readiness, bounded admission/inference and cleanup. Persistent model releases/manifests/evaluation evidence are distinct from transient uploaded emails. No database, account, server history or local-storage persistence is required. Refresh-to-no-file and remove/change behavior are draft A5 details. [API], [X], [M]

Do not persist raw email. Clean framework-spooled files on success/failure; prefer RAM within budgets. Logs/analytics omit raw content, subject, sender, recipient and filename. Allowed fields are request ID, bytes, duration, status and release ID. No HTML/script execution, links/attachment opening, tracking image requests, DNS/WHOIS or remote content fetching. Backend verifies the server-only token; CORS is not authentication. Public access must be controlled or use suitable cross-instance rate controls, rather than claiming a per-instance counter is global. Privacy copy is a target until cleanup/log/session enforcement is validated. [API], [P], [X]

## Release/E0 and deployment evidence

E0 requires reviewed dataset snapshot/per-source label provenance, controlled same-run artifacts and hashes, compatible versions/corpora, ordered schema/dimensions/classes, real `.eml` bytes-to-result harness, release-specific target evaluation and initial RAM/startup/latency. Manifest must additionally identify source revision, inference parameters and decision/threshold rule. Classifier/threshold selection uses separate validation; evaluation uses independent suitably grouped tests, deduplication before splitting, training-only scaler fit and positive-class score ROC-AUC. Only team-controlled pickle may be loaded. [M], [A]

Current metadata records run `e7dcdcc3551e46fc93582836f4a74976` with 40/100/140 and stored hashes, but reading that manifest is not artifact hash verification, compatible loading or target provenance. The historical mixed-positive XGBoost table is candidate rationale, not phishing-only accuracy or final classifier selection. E0 remains unverified. [B], [PA]

E1 design may overlap E0. E2 inference/API/container needs compatible environment/readiness/parity/bounds; E3 real frontend acceptance depends on the eligible release; E4 needs measured hosting/multipart/warm/cold/unavailable behavior; E5 needs meaningful checks and local/deploy/rollback handover. Fixture-only success cannot satisfy E3. Existing unittest obligations remain in addition to proposed new pytest/Playwright checks. [D], [A]

Future hosting is unspecified. Qualify whole-process resources, startup, complete multipart uploads, enforced deadlines, access controls and restart-safe verified model provisioning before choosing a host. Preserve local frontend/proxy operation; no paid plan/trial, required GPU, database or keepalive cron. Local success does not certify hosting. [D], [PA]

## Open decisions and UX assumptions

| Item | Open contract / owner |
| --- | --- |
| Q1 | Eligible dataset snapshot, per-source provenance and retraining necessity — ML workstream, before E0 |
| Q2 | Selected release/classifier, environment/corpora, inference settings/revision and model-quality criteria — ML, before real prediction acceptance |
| Q3 | MIME policy, parser budgets, error codes/HTTP mapping — API, before E2/E3 acceptance |
| Q4 | Warm/cold budgets, backend/proxy deadlines, manual retry policy, RNG/vector tolerance — API/deployment, before E2/E4 acceptance |
| Q5 | Measured free host/account limits and controlled access versus global rate control — deployment, before E4 |
| UX A1/A2 | Illustrative audience/persona and desktop-first responsive device priorities; no interviewed-persona/device evidence |
| UX A3/A4 | Exact visual tokens and centered one-page layout/wireframe are draft choices; graph is not styling authority |
| UX A5 | Proposed remove/change/cancel-picker, focus, disclosures, refresh/reset, accessibility announcement and control behavior require implementation validation |

The latest UX defines a five-state spine (no-file, file-selected, analyzing, success, error). Established requirements settle exact labels, explicit Analyze, no label on errors, and duplicate/stale-result prevention. UX-specific composition/tokens and interaction details remain draft assumptions; architecture should preserve the established flow without claiming visual approval. [P], [X], [V]

## Highest divergence risks for separate builders

1. Parsing independently: raw MIME extraction versus cleaned-body extraction; defect/missing-header/useful-content decisions; encoded versus decoded caps; attachment policy. A shared versioned adapter and budget contract is needed.
2. Contract guessing: multipart field name, 400 versus 422, busy 429 versus 503, upstream normalization, retry signal, public versus internal request/release metadata and success validation.
3. Release guessing: latest pointer versus frozen eligible release, XGBoost candidate versus validation winner, mixed-positive versus phishing-only target, Doc2Vec mode/RNG/settings and schema widths.
4. Timeout guessing: proxy only versus enforceable backend deadline, retry while old work continues, queue versus immediate rejection, parser outside versus inside admission and cold-start phase detection.
5. Ownership guessing: persisting session results/filename, analytics payloads, temporary-file cleanup, browser-exposed backend token or independent local rate counters.
6. Gate guessing: treating samples, source graph, local manifest, inherited metrics or local Docker fallback as E0/cloud acceptance; promoting provisional 2 MiB/400 MiB or provider snapshot values to measured facts.

[S]: ../../../../specs/spec-iap-web-application/SPEC.md
[API]: ../../../../specs/spec-iap-web-application/api-and-experience.md
[M]: ../../../../specs/spec-iap-web-application/model-and-inference.md
[D]: ../../../../specs/spec-iap-web-application/deployment-and-acceptance.md
[B]: ../../../../specs/spec-iap-web-application/brownfield-and-evidence.md
[P]: ../../../prds/prd-PhishingEmailDetection-2026-10-05/prd.md
[PA]: ../../../prds/prd-PhishingEmailDetection-2026-10-05/addendum.md
[X]: ../../../ux-designs/ux-PhishingEmailDetection-2026-10-05/EXPERIENCE.md
[V]: ../../../ux-designs/ux-PhishingEmailDetection-2026-10-05/DESIGN.md
[G]: ../../../ux-designs/ux-PhishingEmailDetection-2026-10-05/.working/source-graph-image.md
[A]: ../../../../../AGENTS.md
