---
title: 'Per-result factor explanation in the web demo (FR-11, AD-14)'
type: 'feature'
created: '2026-10-24'
status: 'done'
baseline_commit: 'e6be65a586c925c7204fafbfc9c503b0eb3299ef'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-24.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A web result shows only a label, so users and the lecturer cannot see what the served model relied on. The approved change (FR-11, AD-14) now admits an explanation, but the contract, backend and UI do not support one.

**Approach:** The ML child computes exact XGBoost contributions for the scored vector, groups the 100 Doc2Vec dimensions into `text_content`, and returns up to five factors (`factor`, `direction`, `strength`) in an optional `explanation` object. A shared English catalogue in `web/contracts/` names the factors. The browser validates the response and renders a neutral factor list under the result.

## Boundaries & Constraints

**Always:**
- Follow AD-14 exactly:
  - additivity within 1e-3 at startup and on every request;
  - at most five nonzero factors, ordered by |contribution| with ties broken by feature order (text first);
  - `strength` = |c|/max shown, rounded to 2 decimals, and factors that round to 0 are dropped;
  - `direction` is relative to class 1.
- Fail closed:
  - a per-request mismatch → `INTERNAL_ERROR`, with no result;
  - a startup mismatch or a served feature missing from the catalogue → unready (new stage `EXPLANATION`);
  - a malformed explanation or an unknown/duplicate factor → the browser shows a processing error.
- Factors stay transient: never logged, and never in errors or the status channel. The browser clears them with the result.
- Copy follows EXPERIENCE:
  - heading "What the model relied on" and the fixed notice;
  - direction "Toward Phishing" / "Toward Legit";
  - strength bands ≥0.67 Strong, ≥0.34 Moderate, otherwise Weak;
  - `is_html` carries the catalogue note "Known dataset bias" (Q9 provisional).
- Bars use one neutral color for both directions and are `aria-hidden`. Only the label stays in the live region.

**Never:** No LIME, sampling, `shap` package or surrogate model; non-XGBoost classifiers return the label only. No raw feature values, scores or probabilities. No change to training, runs, the label decision or the threshold. Do not edit `contracts.generated.ts` by hand.

**Decision (agent, not user-visible for the pinned run):** `target_mode: broad` releases omit `explanation`, because the browser cannot name their positive class for Legit results and the response must stay exactly as the contract specifies.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Explained | XGBoost, `target_mode: phishing` | label plus 1–5 factors; the top factor has strength 1.0 | N/A |
| Unsupported | other classifier or broad target | exactly `analysis_status` and `label` | N/A |
| Per-request mismatch | contributions do not reproduce the margin | no result | `INTERNAL_ERROR` (500) |
| Startup check fails | additivity on the first 256 test rows fails, or the catalogue lacks a served feature | live, not ready | stage `EXPLANATION` |
| Bad wire data | unknown or duplicate factor, more than 5 items, strength 0, extra key | no label or factors | `UPSTREAM_INVALID_RESPONSE` |

</frozen-after-approval>

## Code Map

- `web/backend/adapter.py` -- `Adapter._load` (verification stages, `self.classifier`, `self.doc.vector_size`), `score`, `analyze`, and `worker`, which already maps `Rejection` codes. Refactor `analyze` to compute the vector once. Reuse the `pred_contribs` and additivity approach from `analyze_shap.contributions`.
- `web/backend/policy.py` -- `load_configuration` returns the configuration documents and `validate_policy` checks them. Add the catalogue as a fourth document (`FACTORS`) and validate its structure and a sample explained success.
- `web/backend/service.py` -- passes the child payload through unchanged and logs nothing. Leave it untouched.
- `web/contracts/analysis.schema.json` -- `AnalysisSuccess` (`additionalProperties: false`). Add optional `explanation` plus `Explanation`/`ExplanationFactor` definitions (factor pattern `^[a-z][a-z0-9_]{0,63}$`).
- `web/frontend/lib/contracts.ts` -- AJV validators. `isSuccess` is used by `client.ts` and `proxy.ts`. Wrap it to also check catalogue membership and uniqueness, and validate the catalogue at import, like `validatePolicy`.
- `web/frontend/lib/analysis-controller.ts` -- add `explanation?` to the success state.
- `web/frontend/components/AnalysisPage.tsx`, `app/globals.css` -- the success markup and the `.result-label` styles. Add the list outside the `role="status"` div.
- Tests:
  - `web/backend/tests/test_demo.py`: `variant_run`, `FIXTURE`, `repeatability_child`, `RealModelAPI` exact-key assertions, the `Configuration` file loop and `test_validation_threshold_and_target_label_mapping`, which compares whole dicts.
  - `frontend/tests/unit/contracts.test.ts`, `controller.test.ts`, `tests/browser/analysis.spec.ts`, `tests/integration/real-model.test.ts`: these assert exact success keys.

## Tasks & Acceptance

**Execution:**
- [x] `web/contracts/explanation-factors.json` -- new `{version: 1, factors: {id: {label, note?}}}` catalogue covering `text_content` and all 53 `FEATURE_NAMES`, with plain English labels -- single source for display text.
- [x] `web/contracts/analysis.schema.json`, `web/contracts/README.md` -- add the explanation definitions and document the catalogue -- contract.
- [x] `web/frontend/lib/contracts.generated.ts` -- regenerate with `npm.cmd run contracts:generate` -- generated types.
- [x] `web/backend/policy.py` -- load and validate `FACTORS`; `validate_policy` checks a sample explained success -- shared configuration.
- [x] `web/backend/adapter.py` -- `EXPLANATION` stage, startup checks, `contributions`/`explain` helpers, and `analyze` returning the optional explanation; metadata records the explanation method -- core behavior.
- [x] `web/frontend/lib/contracts.ts`, `lib/explanation.ts` (new: factor text, direction text, strength band), `lib/analysis-controller.ts`, `components/AnalysisPage.tsx`, `app/globals.css` -- validation and the neutral list UI.
- [x] `web/backend/tests/test_demo.py` -- XGBoost `variant_run` tests for every matrix row, repeatability of explanations, an unsupported classifier and broad target, catalogue gaps, and malformed catalogue configuration; relax the exact-key assertions to allow `explanation`.
- [x] Frontend tests -- contract acceptance/rejection, strength bands, the controller carrying and clearing explanations, a browser render and clear test, and a real-model check of the list against the API response.
- [x] `web/backend/README.md`, `AGENTS.md` -- Vietnamese explanation notes; update test counts with the actual results.

**Acceptance Criteria:**
- Given the pinned XGBoost run, when each of the five sample emails is analyzed, then every success contains 1–5 catalogued factors, and repeated, reordered and restarted runs return identical explanations.
- Given a factor list, when compared with independently recomputed contributions, then the grouping, ordering, direction and strength match AD-14.
- Given success with an explanation, when the file is replaced or removed, retried or fails, then no factor remains on the page.

## Verification

**Commands:**
- `.venv/Scripts/python.exe -m unittest discover -s web/backend/tests -v` -- all pass.
- `.venv/Scripts/python.exe -m unittest discover -s tests -v` -- no regressions.
- From `web/frontend`, run `npm.cmd run contracts:check`, `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd run build`, then `test:integration`, `test:browser` and `test:real-model` with `PLAYWRIGHT_CHANNEL=msedge` -- all pass.

## Implementation Notes

- Implemented directly in the main session (fallback allowed by step 3): `general-purpose` subagents stalled for 600 s in this environment earlier in the session.
- New files: `web/contracts/explanation-factors.json`, `web/frontend/lib/explanation.ts`, `web/frontend/tests/unit/explanation.test.ts`. Contract-rejection tests live in `explanation.test.ts`, not `contracts.test.ts`.
- `Adapter.width` is stored at `MODEL_COMPATIBILITY` because `contributions` runs at startup, before `metadata` exists. `metadata["explanation"]` is `"xgboost_pred_contribs"` or `None`.
- The `Repeatability` test now runs on an XGBoost copy of the fixture and compares the full result, including the explanation.
- Pinned run `runs/2026-10-23_web2`: readiness took about 17 s including the 256-row additivity check. All five samples returned 5 factors. A scratch check with two spawned processes (repeated plus reversed order) gave identical results.
- Verification on 2026-10-24:
  - web backend: 36 tests OK, then 37 after the review patches;
  - root: 26 tests OK;
  - frontend: contracts:check, typecheck, lint and build OK; unit 29/29; integration 1/1; browser 12/12 (Edge); real-model 1/1.

## Spec Change Log

## Review Triage Log

Pass 1 (2026-10-24, layers blind-hunter, edge-case-hunter and verification-gap). No intent_gap or bad_spec, so no loopback. All patches applied and re-verified.

| # | Layer | Finding | Verdict | Evidence / route |
|---|-------|---------|---------|------------------|
| 1 | blind, edge | Explanation margin may drift from the `predict_proba` that sets the label (`best_iteration`, `missing`, wrapper) | low, rejected | `train.py` builds XGBoost with `early_stopping=False`; the pinned model has `binary:logistic`, missing=nan, no best_iteration. Max \|sigmoid(margin)−proba\| over 2,000 test rows is 3e-8. The fix would add a guard for state not shown to be reachable. |
| 2 | blind | `hasattr(get_booster)` duck typing; objective not checked | low, rejected | `ControlledUnpickler` admits only sklearn/xgboost classes, the classifier must be a `ClassifierMixin` with `predict_proba`, and training fixes the objective. The fix adds a guard against unreachable state. |
| 3 | blind, edge | Startup `np.load` reads the whole test array to slice 256 rows | low | patch: `mmap_mode="r"`. |
| 4 | blind, edge | `data_X_test.npy` is re-read after hashing without a byte re-check | false | The file is data-only (`allow_pickle=False`), and the rows only feed a self-consistency additivity check of the model. Altered rows cannot change any served result. |
| 5 | blind | The schema allows an explanation alongside a `spam_or_phishing` label, but the UI always says "Toward Phishing" | low, rejected | The backend never emits explanations for broad runs (tested). The fix adds a guard on unreachable output. |
| 6 | blind, edge, gap-other | The Python catalogue validator accepts `version: true`; the TypeScript one rejects it | low | patch: reject bool on the Python side; tests added on both sides. |
| 7 | edge | Python `strip` and JS `trim` disagree on some Unicode whitespace | low | patch: one shared printable-ASCII regex on both sides; tests cover a leading space, NBSP and length 81. |
| 8 | blind, edge, gap | The all-zero / rounded-away path omits the explanation and is untested | low | patch: a test asserts label-only output for zero contributions; the README documents it. Real-model and Repeatability require an explanation only for real emails, which always have non-zero text contributions. |
| 9 | blind | The "independent" test duplicates the ranking logic | low | patch: hand-computed test covering a tie, the rounding drop and the five-factor cap. |
| 10 | blind | No backend test that factors stay out of logs, status and errors | low, rejected | Built in by design: the adapter and service log no results, the status schema is strict `{request_id, phase}`, and `error_response` builds from codes only. A log assertion would need new test plumbing for an unreachable leak. |
| 11 | blind | "Strong" can be read as an absolute measure | low, rejected | The frozen intent fixes the copy to EXPERIENCE (approved 2026-10-24), and its bands are defined relative to the largest factor. Raised with the user as a possible UX follow-up. |
| 12 | blind | The catalogue is required even for releases that never explain | low, rejected | By design, like the other shared contract files (the frontend also needs it at import). Documented in the contracts README. |
| 13 | blind | The contracts README says the backend rejects unknown or duplicate factors | low | patch: reworded (backend checks coverage and builds unique lists; proxy and client reject). |
| 14 | blind | `factorText` called three times; duplicate `overflow-wrap`; literal `#e2e8f0` | low | patch for the first two. The colour literal matches the existing `.button:disabled` style (false). |
| 15 | gap | The proxy forwarding/rejecting of explanations is untested | gap (pre-verified) | patch: a proxy unit passthrough plus unknown and duplicate factor rows expecting `UPSTREAM_INVALID_RESPONSE`. |
