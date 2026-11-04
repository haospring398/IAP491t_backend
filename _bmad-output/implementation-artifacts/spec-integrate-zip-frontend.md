---
title: Integrate the supplied frontend with the agreed email-analysis contract
type: feature
created: 2026-10-06
status: done
baseline_commit: 34648b04405c69d0be09cf5b86c16f104ea02966
route: dispatch
review_loop_iteration: 0
context:
  - AGENTS.md
  - _bmad-output/specs/spec-iap-web-application/SPEC.md
---

<frozen-after-approval reason="User explicitly requested integration into the current project according to the agreed spec.">

## Intent

**Problem:** The supplied Mailguard ZIP has an upload interface, but its Vite routing, boolean response, export instructions, indicators and unsafe attempt handling disagree with the current contract.

**Approach:** Adapt its upload-card composition and inline icons into a runnable Next.js frontend with the specified single Analyze page and server proxy. Connect only to a separately configured eligible backend; unavailable configuration produces an operational error. The user's integration request authorizes this implementation within the existing spec.

## Boundaries & Constraints

**Always:** English UI; exact five states; one nonempty .eml up to 2 MiB; explicit Analyze; captured filename and UUIDv4; neutral Legit/Phishing labels; bounded manual retries; server-only credentials; strict runtime schemas; shared versioned architecture defaults. Keep MIT attribution for adapted source. Follow DESIGN's current system-font, deep-blue, 800px-column, wrapping and accessibility defaults.

**Never:** Import the ZIP backend, heuristic classification, offline ML scripts or node_modules. Add export guides, indicators, probability, history, account screens or real-model/retention claims without evidence. Modify corpus/model/training artifacts or canonical planning sources. Deploy or activate hosting.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected behavior | Error handling |
|---|---|---|---|
| Valid selection | One nonempty .eml within limit | Metadata; no transmission until Analyze | Backend owns MIME suitability |
| Invalid replacement | Multiple, empty, wrong extension, oversized | Clear old result; error | Replace file; no class |
| Picker cancellation | Existing selection/result | Preserve previous state | No request |
| Valid terminal reply | Matching ID; exact completed/legit or phishing | Captured filename and one neutral label | Reject extras/aliases/stale replies |
| Service failure | Canonical, transport, HTML, invalid payload | Safe actionable copy; no class | Manual retry under shared policy |
| Active attempt | Double click/drop/change/remove | Sole attempt; file mutation locked | Ignore late/unmounted replies |
| No backend configured | Analyze | MODEL_UNAVAILABLE | No synthetic classification |
| Progress channel failure | Active request | Generic Analyzing | Terminal POST remains authoritative |

</frozen-after-approval>

## Code Map

- Source archive: `C:/Users/PC/Downloads/Phishing_Email_Detection_Web-main.zip`; entries are under `Phishing_Email_Detection_Web-main/`. Read only the authored frontend source and LICENSE; do not extract dependency directories.
- ZIP `frontend/src/pages/AnalysisPage.jsx`: adapt card/control composition; replace state machine, request logic, result and guide link.
- ZIP `frontend/src/components/Icon.jsx` and root `LICENSE`: reuse upload/mail icons and preserve MIT notice.
- ZIP `frontend/src/styles.css`: adapt analyzer/drop/control layout to current DESIGN; exclude navigation, guides, remote fonts and class-specific safety styling.
- `frontend/`: absent before this change; new App Router application, TypeScript, Tailwind, Node proxy and tests.
- `contracts/`: absent; add canonical JSON schemas and versioned transport policy shared by frontend and future backend. Generate TypeScript types from schemas; validate actual wire data.
- `api-and-experience.md`, `ARCHITECTURE-SPINE.md`, DESIGN and EXPERIENCE: contract sources. Architecture supplies exact provisional error/deadline/retry/polling choices; qualification remains outstanding.
- Python pipeline, artifacts and existing tests: preserve; no imports/execution needed for this frontend task.

## Tasks & Acceptance

**Execution:**
- [x] `frontend/package.json`, lockfile and framework/config files -- create pinned Next 16.3.8, React 19.2.8, TypeScript 5.9.3, Tailwind 4.3.3 application -- match verified registry seed and architecture.
- [x] `contracts/analysis.schema.json`, `transport-policy.json`, generator/runtime modules -- publish exact success/error/status contracts and one shared policy -- avoid independent limits and aliases.
- [x] `frontend/components/AnalysisPage.tsx`, icons, browser client/state modules -- implement selection, immutable attempts, recovery and truthful progress -- replace ZIP races and unlimited retry.
- [x] `frontend/app/page.tsx`, layout and CSS -- single centered accessible responsive surface -- implement current visual defaults without product expansion.
- [x] `frontend/app/api/analyze/route.ts`, status route and proxy modules -- enforce actual bounded bytes before multipart parsing, exact file part, safe error normalization, correlation, canonical filename, trusted deadline and server-only bearer -- connect frontend safely to future service.
- [x] `frontend/tests/` -- meaningful contract, proxy, state/client and browser fixtures -- prove integrity/error boundaries without pretending E0 is complete.
- [x] `frontend/README.md`, `.env.example`, attribution/license -- document local run, frontend source root, separate service requirements and unresolved E0 -- make handover reproducible.

**Acceptance Criteria:**
- Given the app is opened or refreshed, when no file is selected, then only the Analyze surface is shown and Analyze is disabled.
- Given either valid response label, when the current attempt completes, then its filename and exactly Legit or Phishing appear without indicators or score.
- Given an active attempt, when another activation or file mutation occurs, then no duplicate request or filename/result mismatch occurs.
- Given a recoverable failure, when the same file is retried, then shared cooldown and at most two retries apply across all submission actions; input errors require replacement.
- Given a configured proxy, when a request is forwarded, then only server code sends its token and canonical message.eml; invalid or provider replies produce safe errors.
- Given keyboard, phone, long filename and reduced-motion use, when controls/states change, then controls remain operable and labels/focus/layout stay readable.
- Given E0 is unavailable, when the frontend is verified, then real-model and deployment acceptance remain explicitly unclaimed.

## Implementation Notes

- Browser verification scopes application alerts separately from Next's route announcer. Retry timing now resolves Date.now dynamically so the controller and UI use the same clock under instrumentation; browser tests also await each actual retry request before asserting its outcome. Rebuild and rerun unit/browser checks after this change.
- Parent verification found Turbopack scoped resolution to frontend/ and could not import sibling contracts/. Set explicit repository root for Turbopack and output tracing; rebuild and recheck before acceptance.
- Investigation facts: no intent gaps in this bounded frontend adaptation; no irreversible action; new frontend/contracts only. Broad E0/hosting qualification stays outside this task. Node installed is 24.19.0; npm must use npm.cmd under PowerShell. Registry confirmed Next 16.3.8 exists. Git branch is main; whole-tree status stalled, so no whole-tree clean-state claim is made. Only this task's new paths were staged to capture the review diff; no commit or push was made.

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence and route |
|---|---|---|
| Blind 1: same-file reselection resets retries | false | AD-5/6 Consistency Conventions explicitly reset retry state on replacement; selecting/dropping a replacement is separate from retained-file Retry/Analyze activations. No content-identity persistence or bypass-proof quota is specified. Retained-file submission controls already share the tested cap. Rejected. |
| Blind 2: rejected upstream body lifetime | medium | normalize/readWire reject headers before consuming or cancelling response.body and then clear the timer; a rejected streaming response can remain open. Patch body cancellation on early rejection. |
| Blind 3: incoming request cancellation | medium | Neither proxy listens to request.signal; aborting a supplied Request leaves its upstream fetch active until timeout. Patch local cancellation propagation only; backend deadline remains independent. |
| Blind 4: browser response size | false | Browser requests only the application's same-origin routes, whose response producers return bounded schema payloads and whose proxy caps upstream bytes before parsing. No middleware exists in this implementation and provider replies do not reach the browser directly; the claimed oversized producer path is absent. Rejected. |
| Blind 5: status media type | low | pollStatus parses valid JSON despite an incorrect media type. The current proxy always emits JSON, but adding the existing terminal media-type predicate is a direct correction. Patch. |
| Blind 6: contradictory recovery policy | medium | validatePolicy accepts INVALID_EMAIL with a positive cooldown; AnalysisController then retains unsuitable input and allows Retry, violating input replacement semantics on a policy edit. Patch a runtime recovery invariant and regression test. |
| Blind 7: indefinite cooldown ticks | low | The error-state interval continues after cooldown/exhaustion, causing unnecessary renders in ordinary stalled recovery. Patch termination after expiry and avoid exhausted intervals. |
| Blind 8: Remove keyboard focus | medium | Remove unmounts the focused button and has no surviving focus target; keyboard users lose their position. Patch focus to the surviving picker button. |
| Blind 9: restrictions description | low | file-help exists but no picker control references it. Patch aria-describedby directly. |
| Blind 10: actual proxy timeout tests | medium | Existing helper test manually aborts boundedBytes and cannot detect a no-op proxy timer. Patch real proxy timer regressions. |
| Blind 11: actual configured route test | medium | Proxy tests inject fetch and the only actual browser route uses empty configuration, so broken backendConfig/serialization would pass. Patch configured local HTTP route coverage. |
| Edge 1: rejected upstream body lifetime | medium | Same verified early-response-body cancellation omission as Blind 2. Patch the shared root cause. |
| Edge 2: reselection claim | false | Same explicit architecture replacement-reset rule as Blind 1; retained-file Retry/Analyze remain capped. Rejected. |
| Gap 1: configured service selection | medium | Filed regression evidence is accepted: returning null unconditionally from backendConfig would pass existing tests. Patch actual configured route coverage and rejected URL/token cases. |
| Gap 2: proxy deadline enforcement | medium | Filed regression evidence is accepted: disabling proxy timers would pass existing tests. Patch upload/fetch/body/status timeout regressions with correlation and cancellation. |


## Verification

- Frontend typecheck, ESLint, generated-contract freshness, unit/integration tests and production build must pass.
- Browser checks cover select/drop/change/remove, both labels, malformed response, mutation lock, stale response, retry boundaries and responsive keyboard behavior using explicit test-only fixtures.
- Independent Build review evaluates changed code and verification gaps; report actual results and remaining backend/E0 limitations.

### Executed validation (2026-10-06)

- TypeScript typecheck, ESLint, generated-contract freshness and production build passed.
- 15 unit/integration tests passed; 8 Playwright tests passed using installed Chrome against the production build. Test-only results are visibly marked as samples.
- Matrix coverage: selection/cancellation and both terminal labels (browser initial-flow test); invalid replacement (browser replacement test and proxy input tests); service failure and retry bounds (browser retry test and proxy normalization tests); active/stale attempts (browser lock/timeout tests and controller tests); missing backend (browser actual-proxy test); failed or observed status polling (browser lock/progress tests).
- Inspected the 320px phone screenshot: long filename wraps, controls fit, neutral result and status focus remain visible.
- Real model eligibility, backend inference and deployed hosting acceptance remain unverified and are not claimed.

### Final validation after review patches (2026-10-06)

- Parent reran the complete unit suite: 26 passed, 0 failed/skipped.
- Production configured-route HTTP integration: 1 passed. It verifies actual multipart serialization, canonical filename, server bearer, trusted deadline, correlation and observed status against a visibly named test-only fixture.
- Production Playwright suite with installed Chrome: 10 passed in 15.0s, including keyboard removal focus and cooldown timer cleanup.
- TypeScript, full ESLint, generated-contract freshness and optimized production build passed after the final test typing fixes.
- All accepted review findings were patched and covered by passing regressions. No findings were deferred. The three disproved findings remain individually logged above.
- Preserved-source hashes: all 49 pipeline/planning files match their pre-integration snapshots. Backend/model eligibility and deployment are still separate, unverified work.

### Web workspace relocation (2026-10-06 follow-up)

At the user's request, the frontend and shared contracts moved to `web/frontend/`
and `web/contracts/`. Their sibling imports and dependency lockfile are preserved.
`web/README.md` is the current run/share entry point; `web/docs/` contains portable
planning snapshots refreshed by `web/scripts/sync-docs.mjs`. Canonical planning
remains under `_bmad-output/`, with only the current structural path references
adjusted. Earlier file paths and verification above describe the original build.

Relocation validation: generated-contract freshness and optimized production
build (including TypeScript) passed from `web/frontend/`; all 26 unit tests and
the configured production-route integration test passed. The 51 handover
snapshots match their recorded hashes, and 171 local document links resolve.
The dependency lockfile is unchanged; the old root frontend/contracts folders
are absent. No application logic, Python pipeline or model/data artifacts were
changed by the relocation. No deployment or new commit was performed.
