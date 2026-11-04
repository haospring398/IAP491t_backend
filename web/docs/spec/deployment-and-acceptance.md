# Deployment and Acceptance

The user-approved [local demo contract](local-demo.md) overrides conflicting target labels, E0-before-real-inference and native-versus-qualified packaging clauses only for the disclosed local legacy demo. Detailed qualified-release requirements below remain the future phishing-only acceptance contract. Local success uses legit or spam_or_phishing; phishing is reserved for the qualified target. Actual mixed-model checks do not pass E0 or cloud/Docker acceptance.

Applies to CAP-1 through CAP-6. Checks below are planned acceptance obligations; their listing is not a passed result.

The adopted [architecture](../architecture/ARCHITECTURE-SPINE.md) owns the exact initial seed, dependency boundaries and shared policies. Its assumption tags remain live; table presence or final architecture status does not qualify a build, model or deployment.

## Proposed implementation baseline

| Layer | Baseline |
| --- | --- |
| Frontend/proxy | Next.js, TypeScript, Tailwind; local server route |
| Separate Python API | FastAPI/Docker; one ASGI supervisor and one resident serial ML child |
| Backend candidate | Unspecified; future selection requires resource/compatibility checks |
| Storage | Read-only qualified model/code/resource/policy image; transient request data/browser-session results; no database |
| New web checks | Pytest inference/API; Playwright important browser flows |
| Existing pipeline checks | `.venv/Scripts/python.exe -m unittest discover -s tests -v` per AGENTS.md; on 2026-10-20 it ran 9 tests with 1 passing (`test_pipeline` cannot import missing `specialists`; `test_evaluate` drifts from 19-10 code), so report against that baseline |
| Local demo checks | `.venv/Scripts/python.exe -m unittest discover -s web/backend/tests -v` (25 tests passed on 2026-10-20) plus the frontend checks in `web/backend/README.md` |
| Collaboration | Team Git repository; reviewable stories and rollback |

Frontend and Python backend remain separate. Hosting is unspecified; the 2026-10-19 cleanup supersedes the earlier deployment selection without qualifying unrelated product requirements or E0. Architecture retains its framework/package/packaging profile subject to compatibility and resource qualification.

## Hosting feasibility and fallback

The PRD’s approximately 400 MiB peak-RAM assumption remains a future, unqualified research target. It is not a memory cap or guarantee for the current local legacy demo, and no measurement is claimed.

The current demo runs locally. Any future host requires measured whole-container supervisor/child/load/temp RAM, startup/warm/near-limit-email latency, timeout/reap/recovery, restart persistence and complete multipart behavior. Serialized size does not establish RAM. Test actual consumed bytes against the 2 MiB whole-file cap and shared multipart limits.

Retain one worker, exclude training-only dependencies where compatible and prove parity for any optimization. Document local operation with a local frontend/proxy; a remote frontend cannot reach developer localhost. Choose and qualify hosting separately before cloud deployment.

Future qualified packaging follows AD-11: immutable matching artifacts, code, resources and shared policy with an absolute read-only release root, no hot swaps or request-time installation/download. Only the child loads models; rollback moves the complete compatible release. HTTPS, server secrets, suitable access controls and measured unavailable/recovery behavior remain future hosting requirements.

Do not activate paid trials/plans, require GPUs, add a database or run keepalive cron. Open/test the demo before the presentation; public access/rate controls and deadlines remain Q4/Q5.

## Dependency order and evidence

The roughly 15-working-day web estimate assumes an eligible release/environment. E0's 1-2 days cover inventory/trials; relabeling/retraining requires separate estimation. E1 may overlap E0; real prediction acceptance depends on E0.

| Gate | Planned window | Required evidence |
| --- | --- | --- |
| E0 - Eligible ML release | 1-2 days inventory after Q7 restores the missing upstream code; retraining separately estimated | Reviewed target/provenance, coherent real artifacts/manifest, real harness inference, target-specific evaluation, initial RAM/startup/latency |
| E1 - Shared requirements/design | Day 3; may overlap E0 | Common requirements/UX/architecture/API and small stories with inputs/outputs/acceptance; resolve applicable labels/limits/release/error decisions |
| E2 - Inference/API/container | Days 4-6 | Shared adapter, eligibility/readiness, lockfile/corpora, feature/label parity, MIME/Unicode/HTML/attachment/error checks, repeatability/bounded execution |
| E3 - Frontend integration | Days 7-9 | Real upload/two-label result, truthful progress/recovery, duplicate/stale suppression and no browser backend token |
| E4 - Hosting decision | Days 10-11 | Resource/multipart/warm/cold/unavailable measurements, working free URLs or justified fallback, HTTPS/envs/restart-safe artifacts/cleanup |
| E5 - Integration/handover | Days 12-15 | Build and meaningful inference/API/browser checks, privacy log inspection, measured latency/counts/sizes/environment, tested local/deploy/rollback guidance |

These windows are estimates. Final PRD and architecture plus draft UX now exist; E1 still needs applicable shared contract qualification and stories. Document status does not satisfy E0 or any implementation gate.

## Requirement traceability

| PRD requirement | Capability | Acceptance focus |
| --- | --- | --- |
| FR-1 Submit one file | CAP-1 | Picker/drop, name/size, explicit Analyze |
| FR-2 Reject unsuitable input | CAP-1 | Invalid/oversized/insufficient input rejected before inference |
| FR-3 Eligible classification | CAP-2/5 | Reviewed legitimate/phishing target; exact two-label mapping |
| FR-4 Result identity | CAP-2/3 | Attempt filename, old-output clearing, sample markings |
| FR-5 Readable state | CAP-3 | Five states/truthful subphases; no fake progress or stale/duplicate results |
| FR-6 Recovery | CAP-3 | Input/model/busy/network/timeout/non-JSON errors and bounded policy |
| FR-7 Readiness | CAP-4 | Live differs from ready; unsuitable release/config/corpora/target blocks readiness |
| FR-8 E0 evidence | CAP-5 | Provenance, hashes/dimensions/settings, real inference/evaluation/resources |
| FR-9 Inference agreement | CAP-5 | Harness/API parity and repeated-label/order invariance |
| FR-10 Reproducible demonstration | CAP-6 | Measured deployment/fallback, restart-safe release and tested handover |
| FR-11 Explain a result | CAP-2/5 | Exact additive factors, grouped text factor, repeatability, no factors in errors/logs/status, label-only for releases without an exact method |

NFR-1 data handling, NFR-2 isolation/credentials and NFR-3 bounded operation are in API/privacy/input policy; NFR-4 reproducibility is in model/release policy and AGENTS.md; NFR-5 readability is in the adopted UX. All remain cross-cutting obligations.

## Success and counter-metrics

Use the agreed privacy-scrubbed fixture set and release evidence. Record case counts and failures; minimum quality, latency and throughput thresholds are not invented.

| PRD signal | Planned acceptance |
| --- | --- |
| SM-1 - Real session completion | Every agreed valid fixture completes browser-to-eligible-release inference with matching filename, one label and, where supported, an exact factor explanation (FR-1/3/4/10/11). |
| SM-2 - Error integrity | Every required invalid/unready/busy/connectivity/timeout case shows a processing error without classification (FR-2/6/7). |
| SM-3 - Reproducible handover | E0, feature/label parity, repeatability, privacy/credentials and documented local demo pass their checks (FR-8/9/10; NFR-1-4). |
| SM-C1 - Quality/resource costs | Report target-specific false positives/negatives, rejected inputs, failures, warm/cold latency and peak RAM alongside successful sessions; thresholds remain Q2/Q4. |
| SM-C2 - Integrity violations | Covered checks find zero fabricated error labels, stale-file results, request-order label changes, exposed credentials, sensitive-content retention/logging, non-additive factors or factor changes across repeated input; this is not a production-wide guarantee. |

## Acceptance coverage

- Fixtures include plain text, HTML, multipart, varied charsets, attachments and malformed mail without personal data; harness/API features and decisions match the eligible release.
- Input/error checks cover multiple files, empty/wrong extension/unsuitable structure, configured boundary sizes, insufficient content, model unavailable, busy, unreachable/offline, timeout, authentication/provider non-JSON and invalid success payload.
- Browser checks exercise no-file, file-selected, analyzing, both successful labels with and without an explanation, and error; verify factors clear with the result on replacement/removal/retry/error, and verify explicit transmission, filename identity, replacement/removal/retry clearing, duplicate starts and late responses after timeout/new attempts.
- Test proposed UX-A5 controls/keyboard/screen-reader announcements/focus/reduced motion, long filenames, phone widths and zoom; validate DESIGN contrast targets in actual states. These are future checks of draft defaults, not approved tokens or accessibility certification.
- Artifact/configuration/resources/target/policy failures prevent readiness; busy capacity remains separate. Qualification covers exact manifest schema, loaded objects, same-fixture feature/vector/label parity and repeated/reordered/restarted inputs under AD-4.
- Explanation checks cover startup and per-request additivity, catalogue coverage of every served feature, identical factors under repeated/reordered/restarted input, strict rejection of malformed explanations, and absence of factors from errors, status responses and logs.
- Verify server-side credentials, safe offline email handling, temporary-file cleanup and sensitive-log exclusion. Publish privacy/retention copy only after enforcement; clearly mark sample responses pending E0.
- Record warm/cold latency/count/size/environment, startup and whole-container peak RAM. Qualify shared input/error limits, no-queue admission, trusted deadline/skew reserves, child terminate/reap/recovery, spool cleanup, same-file retry counting and bounded non-overlapping status polls before E2/E4 sign-off. Recheck provider/account access protection and limits before cloud selection.
- Frontend build and meaningful inference/API/browser checks pass. README/manifest/local-deploy-rollback instructions let another member reproduce the environment; report actual validation performed, with no inferred CI.
- Align the research report and original diagram's Results/training/storage wording with the accepted target/release. This spec does not modify those originals.

Each implementation story requires reviewable changes and meaningful checks. Demonstration emails do not establish phishing quality, source-independent generalization, explanation quality or completed RQ2/RQ3. Exact additivity establishes fidelity to the model, not that its factors are meaningful phishing evidence.

## Decision ownership

Owners are workstream assumptions pending individual assignment.

| Question | Workstream | Revisit condition |
| --- | --- | --- |
| Q1 target/provenance | ML | Before E0 passes |
| Q2 release/settings/quality criteria | ML | Before real prediction acceptance |
| Q3 shared input/parser/schema/error profile | API | Qualify or jointly revise before E2/E3 acceptance |
| Q4 budgets/deadlines/retries/reap/skew/parity tolerance | API and deployment | Qualify the initial profile before E2/E4 acceptance |
| Q5 measured host/account access gate/quotas | Deployment | Before controlled cloud publication/E4; shared abuse controls before anonymous access |
| Q6 UX A1-A5 and UI-library choice | Individual owner unassigned | Before UX approval |
| Q7 missing upstream pipeline code | ML | Before any retraining, E0 inventory or reproduction of the 2026-10-19 candidate |
| Q8 BERT versus Doc2Vec release architecture | ML and architecture | Before selecting a BERT release; requires a new AD |
| Q9 dataset-shortcut factors in explanations | ML and UX | Before FR-11 acceptance |
