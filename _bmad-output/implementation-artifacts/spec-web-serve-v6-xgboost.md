---
title: 'Web serves the baseline_v6 XGBoost with exact explanations'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: 'bfa84685dbd1d5c86b64305e0189db78c7c6d605'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The web serves the baseline_v6 run's validation-selected MLP. That model has no exact contributions, so results carry only a label and the AD-14 factor explanation is gone.

**Approach:** Pin the run's XGBoost classifier explicitly and serve it at its own validation threshold from the manifest (0.2114). The existing exact `pred_contribs` explanation path then applies unchanged.

## Boundaries & Constraints

**Always:**
- The served classifier comes from a pinned model name in `web/backend/policy.py` (`MODEL_NAME = "XGBoost"`). An environment override exists for tests and child processes. No value means "use the manifest's `selected_model`", which is today's behaviour.
- The name must exist in `manifest["models"]` and pass the same checks the selected model passes today: sklearn kind, plain file name, threshold in [0, 1], ControlledUnpickler, widths and classes. Otherwise the worker is unready at MODEL_COMPATIBILITY.
- The served model uses its own manifest threshold, never the selected model's.
- Metadata keeps `selected_model` (the manifest's choice) and adds `served_model`.
- Explanation, catalogue, contract and UI stay unchanged.

**Never:**
- Retrain or edit the run or the frozen pipeline.
- Change the HTTP contract.
- Touch the deferred Integrated Gradients spec.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HAPPY_PATH | v6 bundle, MODEL_NAME XGBoost, valid .eml | Label at XGBoost threshold + 1–5 exact factors | N/A |
| Unknown name | MODEL_NAME not in manifest models | Worker unready, stage MODEL_COMPATIBILITY | Existing startup error |
| No pin | Override set to use the selected model | Manifest `selected_model` (MLP) served, label only | N/A |
| Non-sklearn pin | Pinned model has kind `bert` | Unready, MODEL_COMPATIBILITY | Existing |

</frozen-after-approval>

## Code Map

- `web/backend/policy.py`:
  - :33-40 holds `RUN_PATH`, `RUN_PATH_ENV` and `pinned_run()`.
  - Add `MODEL_NAME = "XGBoost"`, an env override (e.g. `IAP_WEB_MODEL`) and a resolver. Mirror `pinned_run`, but make it possible to request the manifest selection (e.g. the override value `selected`).
- `web/backend/adapter.py`:
  - :252-258 `selected = manifest["selected_model"]; config = manifest["models"][selected]`: resolve the served name first and fail MODEL_COMPATIBILITY when it is missing.
  - :310 metadata: add `served_model`.
  - The explanation gate (`hasattr(get_booster)`) needs no change.
- `web/backend/tests/test_demo.py`:
  - The fixture manifest selects MLP and also holds XGBoost. Tests that forced XGBoost by editing `selected_model` (`select_xgboost`) now get it from the pin.
  - Label-only cases need the override back to the selection.
  - `PinnedRelease` (:929-) asserts MLP, explanation None and FP 1359 / FN 42. It must now assert `served_model` XGBoost, `xgboost_pred_contribs`, factors in the result and XGBoost test FP 1292 / FN 76 (`runs/2026-11-02_baseline_v6/evaluation_results.csv`).
  - Add matrix rows: unknown name, selection override.
- `web/frontend/tests/integration/real-model.test.ts:75-90`: restore the explanation assertions (keys include `explanation`, shown factor labels equal `factorCatalogue` labels; see the commit before bfa8468).
- Docs (Vietnamese READMEs, English BMad):
  - `AGENTS.md` (pinned run sentence: served XGBoost, explanation);
  - `web/backend/README.md`;
  - `web/README.md` if it mentions MLP;
  - `_bmad-output/specs/spec-iap-web-application/local-demo.md` (2026-11-04 update: explicit served model, consistent with AD-2 explicit selection);
  - then `node web/scripts/sync-docs.mjs`.

## Tasks & Acceptance

**Execution:**
- [x] `web/backend/policy.py`, `adapter.py` -- pinned model name with override and validation; metadata `served_model`.
- [x] `web/backend/tests/test_demo.py` -- adapt fixture tests; matrix rows; PinnedRelease for XGBoost.
- [x] `web/frontend/tests/integration/real-model.test.ts` -- expect explanation.
- [x] Docs -- update and sync.

**Acceptance Criteria:**
- Given the bundled v6 run, when the worker starts, then metadata reports `served_model` XGBoost, `selected_model` MLP, threshold 0.2113690823… and explanation `xgboost_pred_contribs`.
- Given the bundled test arrays, when the served model scores them, then FP 1292 / FN 76.
- Given the five sample emails through the real stack, when analysed, then each result shows 1–5 catalogued factors.

## Implementation Notes

- `policy.pinned_model()` returns `IAP_WEB_MODEL` or `MODEL_NAME`, and None for `selected` (or `MODEL_NAME = None` with no variable); the adapter serves `pinned_model() or selected_model`. The adapter also rejects a non-string file and a boolean threshold for the served model.
- Test module start clears an inherited `IAP_WEB_MODEL` and restores it afterwards. Added matrix rows: BERT pinned, BERT selected (`selected`), unknown pinned name (adapter and worker), pinned nested file, pinned threshold 1.5, pinned boolean threshold; plus `test_pinned_model_uses_own_threshold_and_selection_override` (`selected`, `MLP`, `MODEL_NAME = None`).
- Root `README.md` sentence on the served run updated as well. The 250-email label agreement in `web/backend/README.md` was measured while MLP was served and was not re-measured for XGBoost; the table header now says so.
- Verification 2026-11-04: web backend 49 tests OK (web/.venv, from web/, about 44 s, PinnedRelease ran against the bundle); frontend `npm.cmd test` 29/29, typecheck, lint, contracts:check, build, `test:browser` 12/12 and `test:real-model` (msedge) passed.

## Spec Change Log

## Review Triage Log

Review pass 1 (2026-11-04; layers: blind-hunter, edge-case-hunter, verification-gap — verification-gap reported no gaps):

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | Worker restart re-reads policy/env, so an edited `MODEL_NAME` silently serves another classifier with the same manifest digest (BH, EC) | low | service.py:80 passes only run and digest; `_startup` checks only `manifest_sha256` | patch |
| 2 | Tests that need XGBoost rely on the production `MODEL_NAME`; `MODEL_NAME = None`/`selected` gives KeyError or a trivially passing broad_xgboost (BH, EC) | low | test_demo.py uses `models[policy_module.MODEL_NAME]` and no explicit override in Explanation/Repeatability | patch |
| 3 | real-model test inherits `IAP_WEB_MODEL` from the developer shell (EC) | low | Backend spawned with `...process.env` | patch |
| 4 | build_fixture.py docstring still says tests enable XGBoost by editing selected_model (BH) | low | build_fixture.py:10-12 unchanged | patch |
| 5 | local-demo decision omits the trade-off vs the selected MLP (FN 76 vs 42, FP 1292 vs 1359) (BH) | low | Bullet cites only XGBoost numbers | patch |
| 6 | 2026-10-21 bullet "served classifier is the manifest's selected_model" not marked superseded (BH) | low | local-demo.md:11; new bullet only names "the next bullet" | patch |
| 7 | Meaning of empty `IAP_WEB_MODEL` (use MODEL_NAME) undocumented (BH) | low | README documents names and `selected` only | patch (doc) |
| 8 | Empty/`..`/drive-relative `file` names pass the plain-name check (EC) | low | Pre-existing check; manifest is hash-verified team data and such a path fails at ARTIFACT_BYTES | reject |
| 9 | Whitespace/case variants of the override leave the worker unready (EC) | low | Fails closed at MODEL_COMPATIBILITY; normalisation adds behaviour | reject |
| 10 | A model literally named `selected` cannot be pinned (EC) | false | No run names a model `selected`; sklearn names are fixed in train.py | reject |
| 11 | real-model test reads `.label` of an unknown factor without a clear assert (EC) | low | Unlikely (catalogue covers all 134 + text); fix adds a guard | reject |
| 12 | selected_model=XGBoost path with explanation no longer tested (EC) | low | Explanation gate is independent of how the name is chosen; selection path covered by `test_pinned_model_uses_own_threshold_and_selection_override` | reject |
| 13 | Spec notes say XGBoost labels were not re-measured; no recorded command (BH) | low | Fix edits this spec; parity script commit already deferred | reject |
| 14 | AGENTS.md "To serve another run" lacks a MODEL_NAME step (BH) | low | Fix edits agent-context files | defer |
| 15 | `Explanation` now uses the shared fixture folder (BH) | maybe-false | Would need a test that mutates `FIXTURE["run"]`; variants copy it | reject |
| 16 | XGBoost factors now reach users without a source-bias review of the hdr_* features (BH) | maybe-false | Needs per-source feature rates; already a deferred item, now user-facing | defer |
| 17 | real-model test does not check notes, direction, strength or notice (BH) | low | Browser spec covers rendering with mocked data | reject |

## Verification

**Commands:**
- `cd web; .venv/Scripts/python.exe -m unittest discover -s backend/tests -v` -- expected: all pass.
- In web/frontend: `npm.cmd test`, `npm.cmd run test:browser`, `$env:PLAYWRIGHT_CHANNEL='msedge'; npm.cmd run test:real-model` -- expected: pass.
