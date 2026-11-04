---
title: 'Local demo using the existing real email classifier'
type: 'feature'
created: '2026-10-06'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'c916685b5196e6f0ed7530e481be24dd91f685e3'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-iap-web-application/local-demo.md'
---

<frozen-after-approval reason="User approved the concrete local real-model demo proposal with 'được'; do not modify intent without renegotiation">

## Intent

**Problem:** The frontend currently has no real backend. Waiting for phishing-only E0 qualification prevents demonstrating the existing pipeline.

**Approach:** Connect the local Next application to a separate Python service using the current verified run and XGBoost. Disclose mixed spam/phishing semantics; retain the application boundary for a later whole-release upgrade.

## Boundaries & Constraints

**Always:** Local loopback only; English UI; actual same-run inference; binary model outcomes Legit and Spam / phishing. Add `spam_or_phishing` to the strict shared success enum, reserve `phishing` for future qualified releases. Keep existing exact envelope, errors, request identity, transport policy, status channel and retry controls. One authenticated admission before body consumption, no queue; one spawned resident model child; bounded receive/parse/inference, terminate/reap on timeout/disconnect, recover readiness. No sensitive logging or persistent uploads. Pin the selected run once at startup, verify all hashes/test dimensions, controlled pickle and loaded classes/widths before readiness. Freeze observed stopwords fallback, no WordNet, inherited inference defaults, numerical threads and deterministic process/content seed; restore RNG per request. These are legacy demo settings, not E0 certification.

**Never:** Heuristic/sample fallback; silently label mixed positives Phishing; modify preprocessing, corpora, model files, pointer, offline training/evaluation or metrics; download resources in requests; publish/deploy; claim phishing accuracy, E0, Linux/Docker portability or cloud budgets. Preserve authorized pending relocation to `web/` and other user changes.

## I/O & Edge-Case Matrix

| Scenario | Input / state | Expected behavior | Error handling |
|---|---|---|---|
| Real inference | Valid plain/HTML/multipart/charset/attachment email | Completed actual XGBoost label, correct filename in UI; no remote fetch | No scores/features |
| Invalid input | Empty, wrong extension, malformed/absent header, no usable tokens, extra form parts | Reject before inference | Shared 400/413/422 error, no label |
| Resource bounds | Excess body/file, MIME nodes/depth, decoded text/tokens | Reject actual overrun, never truncate | Shared too-large/resource error |
| Startup failure | Missing/tampered/incompatible run or configuration | Live responsive, ready503; no classification | MODEL_UNAVAILABLE |
| Busy/deadline | Active job, expired deadline, slow receive/worker | Busy rejected without queue; timeout kills/reaps before replacement | SERVICE_BUSY/ANALYSIS_TIMEOUT |
| Identity/auth | Bad UUID/deadline or token; unrelated status query | Safe rejection; status only observes matching work/startup | No secret/label/content exposure |
| Repeatability | Repeated/reordered inputs and restarted child | Same feature vectors and labels | Fail verification on drift |
| UI mapping | Mixed-positive success or future qualified phishing fixture | Spam / phishing or Phishing exactly; visible demo notice | Unknown success rejected |

</frozen-after-approval>

## Code Map

- `artifact_store.py`: `selected_run`, `verify_run`, hashes and matching test counts. Use once in child startup from root; no loose fallback. Current run `e7dcdcc3551e46fc93582836f4a74976` loads XGBoost successfully: classes0/1, Doc2Vec100 + engineered40 =140.
- `preprocess.py`: raw bytes accepted; `extract_engineered_features` before `cleanText`, `remove_stopwords`, `tokenize_text`; no fitted changes. Isolate global counters in serial child. Observed fallback sklearn English stopwords, WordNet absent; freeze this policy. Saved Doc2Vec epochs1 and alpha/min_alpha approximately -0.035: preserve inherited defaults explicitly and disclose limitation; positive-alpha qualification remains future work.
- `web/contracts/{analysis.schema.json,transport-policy.json}`: single wire/policy authority. Add label, regenerate `web/frontend/lib/contracts.generated.ts`.
- `web/frontend/components/AnalysisPage.tsx`: replace binary label ternary with exhaustive map, visible local-demo disclosure. Existing controller/proxy preserve state safety and credentials.
- `web/frontend/lib/proxy.ts`: canonical message.eml, bearer token, UUID/deadline; reuse unchanged.
- `web/frontend/AGENTS.md`: read relevant installed Next docs before changes.
- `.venv`: Python3.11 ML packages through sibling-venv .pth; working local environment only. FastAPI/Uvicorn/multipart absent; install pinned API dependencies separately without changing ML packages.

## Tasks & Acceptance

**Execution:**
- [x] `backend/` — implement local FastAPI supervisor, spawned inference adapter and bounded validation using shared policy; pins/API dependency instructions, safe health/status/errors and meaningful tests including matrix failures.
- [x] `web/contracts/`, `web/frontend/` — synchronize strict label types/rendering/tests and demo disclosure; update env example without secrets.
- [x] `backend/README.md`, `web/README.md`, root `README.md` — tested native local run/configuration and whole-release upgrade guidance; sample `.eml` fixtures with no expected quality claims.
- [x] `_bmad-output/specs/spec-iap-web-application/`, `web/docs/` — derive approved local exception from append-only decisions, retain final E0 contract; refresh handover snapshots.
- [x] `backend/tests/`, `web/frontend/tests/` — execute actual-model API/proxy/browser flow, repeat/order/restart and meaningful failure tests; existing checks separately from qualification.

**Acceptance Criteria:**
- Given the verified local run and token, when the documented service and frontend start and a real email is submitted through the browser/proxy, then the actual model response appears with matching filename and truthful mixed-target label.
- Given a worker failure or timeout, when another attempt follows recovery, then no previous label survives and exactly one usable child exists.
- Given existing frontend workflows, when checks/build run, then selection, retries, stale suppression and strict error handling remain passing.
- Given the legacy demo, when handover is read, then real operational evidence is separated from pending E0 and future whole-release upgrades.

## Implementation Notes

- The parent runs bmad-spec as its sole writer for the canonical spec folder; implementation consumes local-demo.md and leaves canonical derivation to the parent. Parent refreshes web/docs after final verification. All other execution tasks remain implementation-owned.
- Existing Git changes are the authorized relocation to web/ and its docs; preserve them. Whole-tree Git status is costly because of the corpus index; scope diagnostics to product files. No commits or remote operations in the implementation handoff.
- Parent verification: direct Adapter inference on plain.eml returned real legit with 140 columns. New backend suite passed 12 tests in 57.544s outside sandbox (Windows multiprocessing Pipe is denied inside sandbox), including 5 MIME fixtures, repeated/reordered/restarted vectors/labels, auth/bounds/admission and timeout/disconnect reaping/recovery. Baseline offline suite remains 1 pass, 4 failures and 3 errors across 8 tests; no core repair or new metrics are claimed.

- Final verification before review: targeted idle-worker recovery passed; frontend 26 unit/11 browser tests, contracts/lint/production build and hermetic integration passed. Parent Chrome actual-model smoke passed five MIME browser/API comparisons and unavailable clearing (1 test, 17.538s). Shared handover verified 54 source/snapshot hash pairs and 187 local links; 49 upstream/pipeline/pointer hashes unchanged.

## Spec Change Log

No intent changes were required after approval.

## Review Triage Log

| Finding | Verdict | Evidence and route |
|---|---|---|
| Blind1: import-time policy failure | medium | policy.py reads JSON/RequestId before app creation; missing/malformed contracts prevent health startup. Patch guarded configuration initialization without a fallback inference policy. |
| Blind2: invalid-policy error handling | medium | launch catches validation failure, but budget/error_response still dereference missing fields. Patch safe unavailable response and prevent admission when configuration is invalid. |
| Blind3: recovery release drift | medium | Supervisor pins path only and overwrites metadata after recovery; changed self-consistent manifest at that path is accepted. Patch initial manifest-digest pin through recovery. |
| Blind4: startup failure attribution | medium | worker sends unavailable/None and parent drops failure reason; local operator cannot distinguish artifact/environment/worker startup stage. Patch safe internal stage code, excluding sensitive exceptions. |
| Blind5: constant/misencoded prediction regression | medium | Tests accept either legal response and compare same adapter results; classifier bypass/mapping inversion remains undetected. Patch independent vector-to-classifier and numeric-to-wire assertions. |
| Blind6: actual admission verification | medium | Busy test preassigns active_id and does not exercise first-request admission. Patch actual overlapping requests with second-body nonconsumption and unchanged child. |
| Blind7: slow receive deadline | medium | Timeout test delays IPC, not upload; receive timer/reaping path lacks a regression. Patch stalled upload, capacity cleanup and recovery test. |
| Blind8: observed status phases | medium | Status checks cover idle unknown only; constant unknown implementation passes. Patch receiving/processing/startup and unrelated-ID observations with terminal erasure. |
| Blind9: loaded artifact guards | medium | Existing failures stub verification or missing path; incorrect loaded classes/widths and verify/load changed bytes are untested. Patch targeted controlled loading regressions. |
| Blind10: lossy README paragraphs | low | New root README still contains literal question marks in prior relocation paragraphs, harming everyday run instructions. Directly correct prose to readable English. |
| Edge1: import-time policy failure | medium | Same confirmed bootstrap failure as Blind1; patch shared cause. |
| Edge2: Unicode deadline digits | medium | budget uses isdigit then int; Latin-1 superscript digit reaches uncaught ValueError. Patch ASCII epoch-digit validation and canonical error test. |
| Gap1: independent feature composition | medium | Filed regression evidence accepted: removing scaler transform preserves shape/repeatability/parity tests. Patch independent expected normalization and Doc2Vec-first assertions. |
| Gap2: numeric/wire label mapping | medium | Filed evidence accepted: inverted mapping keeps current tests passing. Patch numeric0/1-to-legit/spam_or_phishing assertions; same mapping gap as Blind5. |

## Verification

Final parent verification after all review patches: backend 24 tests passed in 60.695s; frontend contracts, 26 unit tests, lint and production build passed; one hermetic integration and 11 Chrome browser regressions passed. Actual pinned-model smoke passed in 12.966s, comparing five MIME cases through Python, Next proxy and Chrome and checking unavailable-result clearing. All 14 review findings were fixed, including shared causes; nothing was deferred. Focused patch verification separately passed 14 tests in 45.567s. The 49 preserved upstream/pipeline/pointer hashes remain unchanged. Existing offline failures remain baseline debt, and these operational checks do not establish E0 or phishing-only accuracy.

- `.venv/Scripts/python.exe -m unittest discover -s backend/tests -v`: actual model and boundary tests pass; record failures separately in existing root tests.
- `npm.cmd run contracts:check`, `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build`, `npm.cmd run test:integration`, `npm.cmd run test:browser`, `npm.cmd run test:real-model` from `web/frontend`: shared contract and UI regressions pass.
- Run the actual backend and Next proxy with server-only local secret; verify browser email upload/result and unavailable behavior. Tests requiring spawn/network may need sandbox escalation.
