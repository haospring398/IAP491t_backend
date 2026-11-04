---
title: 'Serve a 19-10 training run in the local web demo'
type: 'feature'
created: '2026-10-21'
status: 'done'
baseline_commit: '249792a01aaf91608040c03b3077ec7ff0c51ca4'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-iap-web-application/local-demo.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Root `preprocess.py` now emits 53 engineered features, so the web backend can no longer verify or load its pinned legacy run (40 features) and never becomes ready. Users chose to move the web to the current pipeline instead of keeping legacy preprocessing.

**Approach:** The web worker loads a 19-10 baseline run (`runs/<name>/dumped_models/classification/run_manifest.json`, schema 2) pinned in `policy.py`, serves the manifest's `selected_model` with its validation threshold, and reproduces training preprocessing and Doc2Vec inference exactly. No real run exists yet; tests build a small synthetic fixture run.

**Decisions (2026-10-21):**
- A positive result from a `target_mode: phishing` run emits `phishing` (UI "Phishing"); `broad` emits `spam_or_phishing`. `local-demo.md` records this as a disclosed local exception: validation evidence only, no E0 or test-quality claim.
- The always-visible notice becomes one static sentence true for both targets: "Local demo model: phishing detection accuracy has not been independently established." No contract change.
- Serve the manifest's `selected_model` (user choice, overriding AD-2's explicit-selection rule for this local demo; recorded in `local-demo.md`).
- Keep the full spec (~2,000 tokens) rather than splitting off documentation.

## Boundaries & Constraints

**Always:** Pin exactly one run path in `web/backend/policy.py`; reject any other path. Before readiness verify: `status == "complete"`, `schema_version == 2`, every `artifacts` SHA-256, `settings.feature_names == preprocess.FEATURE_NAMES`, recorded preprocessing signature equals current `pipeline_cache.preprocessing_signature()`, selected model is sklearn-kind with finite threshold, loaded types/classes `[0, 1]`/widths (`doc2vec_dim` + 53). Verify the exact bytes before unpickling. Use the same functions as training for cleaning/features (`pipeline_cache._process`) and Doc2Vec inference (one shared function). Positive iff positive-class probability >= threshold. Keep envelope, endpoints, errors, startup stages, RNG capture/restore, single worker, transient uploads. UI copy English; comments/README Vietnamese.

**Never:** Import `train.py`, `evaluate.py`, `load_data.py` from the web worker; serve BERT; fall back to loose files, `artifact_store` runs or another classifier; modify `Dataset/`, existing `runs/`, or `dumped_models/classification/runs/`; hand-edit `contracts.generated.ts` or `web/docs/`; train a real model in this change.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Legit email | fixture run, score < threshold | `{"analysis_status":"completed","label":"legit"}` | N/A |
| Positive email | score >= threshold, `target_mode` phishing | `phishing` | N/A |
| Positive, broad run | `target_mode` broad | `spam_or_phishing` | N/A |
| Run not configured / missing | pin unset or path absent | worker unavailable | `RUN_VERIFICATION` |
| Tampered artifact | any hash mismatch | not ready | `RUN_VERIFICATION` / `ARTIFACT_BYTES` |
| Incomplete run | `status: incomplete` | not ready | `RUN_VERIFICATION` |
| Schema/preprocessing drift | feature names or signature differ | not ready | `MODEL_COMPATIBILITY` |
| BERT selected | `selected_model` kind `bert` | not ready | `MODEL_COMPATIBILITY` |

</frozen-after-approval>

## Code Map

- `web/backend/adapter.py` -- `Adapter._load` (166-232) uses `artifact_store.selected_run/verify_run`, fixed `XGBoost.pkl`, inherited alpha/epochs, frozen sklearn stopwords; `vector` (234) / `analyze` (257, `predict` + hardcoded `spam_or_phishing`); `GLOBALS` (26) allowlists only Doc2Vec/StandardScaler/XGBoost; `validate_email` (114) limits/tokens — keep limits.
- `web/backend/policy.py:25` -- `RUN_ID`; replace with run path pin.
- `web/backend/service.py` -- uses only `metadata["run"]`, `metadata["manifest_sha256"]` (105-118); no label logic. Keep.
- `web/backend/tests/test_demo.py` -- `AdapterVerification` (226), `RealModelAPI` (326, asserts width 140, epochs 1), `Repeatability` (615) and `Boundaries` (159, patches `artifact_store.selected_run`) depend on legacy run; `Lifecycle` (576) uses legacy pinned path string.
- `train.py` -- `infer_doc_vectors` (125, alpha 0.025/min 0.0005/`INFERENCE_EPOCHS`, per-text seed); `prepare_data` settings (199) lack the preprocessing signature; `training()` manifest (489).
- `pipeline_cache.py` -- `_process(job)` feature stage yields `_clean_text`, `_features`; `preprocessing_signature()`; imports only `preprocess`, nltk, bs4.
- `web/frontend/components/AnalysisPage.tsx:7,30` -- label map (already maps `phishing`), static notice; tests `tests/browser/analysis.spec.ts:39-45`, `tests/integration/real-model.test.ts:56,68,75`.
- Docs: `web/backend/README.md` (3-7, 90-101, 141-144), `web/README.md:31-32`, `web/frontend/README.md` (6-7, 42-45), `AGENTS.md` web lines, `_bmad-output/specs/spec-iap-web-application/local-demo.md`.

## Tasks & Acceptance

**Execution:**
- [x] `preprocess.py` -- add shared `infer_document_vector(model, text, epochs)` (tokenize, empty token, content seed, alpha/min_alpha constants) -- single implementation for parity.
- [x] `train.py` -- `infer_doc_vectors` calls it; record `{"signature", "lemmatization", "stopwords"}` from the cache in manifest `settings.preprocessing` -- serving can verify parity.
- [x] `web/backend/policy.py` -- replace `RUN_ID` with `RUN_PATH` (relative to ROOT, `None` until a run is trained) -- explicit pin.
- [x] `web/backend/adapter.py` -- schema-2 verification, selected sklearn model + threshold, `_process`-based features, shared inference, label per decision, stopwords frozen to the recorded list, allowlist covering the ten sklearn/xgboost classifiers, updated metadata -- core change.
- [x] `web/backend/tests/test_demo.py` -- fixture run built once via `train.training(data=synthetic, train_bert=False, run_ablation=False)`; port real-model tests; add matrix cases; unpickle every fixture classifier through `ControlledUnpickler`.
- [x] `web/frontend/components/AnalysisPage.tsx`, `tests/browser/analysis.spec.ts`, `tests/integration/real-model.test.ts` -- static notice text from Decisions; tests accept `phishing`/`spam_or_phishing` per run target.
- [x] READMEs, `AGENTS.md`, `local-demo.md`; then `node web/scripts/sync-docs.mjs`.

**Acceptance Criteria:**
- Given a fixture run pinned, when the worker starts, then it reports ready and the same email gives identical vectors/labels across repeat, reorder and restart.
- Given the fixture run, when the adapter scores its test emails, then labels equal `(predict_proba[:,1] >= threshold)` of the training-side vectors built from the same rows.
- Given no configured run, when the backend starts, then liveness works and readiness reports unavailable without a crash.

### Review Findings

Code review 2026-10-21 (`bmad-code-review`, full mode). All four reviewer subagents (blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor) stalled for 600 s on three attempts (Opus, Sonnet, in-project inputs); the review was performed inline by the implementing agent and is therefore not independent.

- [x] [Review][Decision] Run pin overridable by environment — Frozen constraint says "Pin exactly one run path in `web/backend/policy.py`"; implementation adds `IAP_WEB_RUN_PATH` override (`policy.pinned_run()`), used by tests because spawned workers do not see patches. Choose: keep the documented override, or make `policy.RUN_PATH` the only source and give tests another mechanism. — resolved 2026-10-21: user chose to keep the documented `IAP_WEB_RUN_PATH` override (accepted as implemented).
- [x] [Review][Patch] Unpickler allows calling any function in `sklearn.`/`xgboost.` modules (verified: a pickle invoking `sklearn.utils.validation.check_scalar` executes) — restrict prefix matches to classes; all 12 fixture artifacts still load [web/backend/adapter.py:46]
- [x] [Review][Patch] Unused `import hashlib` after moving Doc2Vec inference to `preprocess.py` [train.py:7]
- [x] [Review][Patch] README omits that `train.py` trains BERT by default and a BERT-selected run is refused by the web; add `--skip-text-training` guidance [web/backend/README.md:156]

Rejected:
- low: `_process` errors map to `INVALID_EMAIL` instead of `MODEL_UNAVAILABLE` — failures after `validate_email` are content-driven extraction errors that training also treats as data errors; changing it adds branching.
- low: no test for backslash artifact-key normalization — only affects runs trained on Windows before this change, which already fail the preprocessing-signature check.
- false: hashing every artifact could exceed the worker startup deadline — `workerStartupMs` is 120000; hashing even a 440 MB BERT checkpoint takes seconds.
- low: unconfigured and tampered runs both report `RUN_VERIFICATION` — a distinct stage would add public surface; README explains both causes.
- low: README paragraphs mix Vietnamese and English — new text follows the AGENTS.md Vietnamese README rule; cosmetic.
- low: `validate_email` and `_process` both clean the text — negligible cost per request.

## Implementation Notes

- 2026-10-21: The dispatched implementation subagent stalled (no progress for 600 s) without changing files; implemented directly from this spec.
- Pin mechanism: `policy.RUN_PATH` (None until a run is trained) with `IAP_WEB_RUN_PATH` override via `policy.pinned_run()`. The override is needed because the worker is a spawned child, so test patches do not reach it; exactly one run is still accepted per process and any other `pinned` path is rejected.
- `train.py` wrote manifest artifact keys with OS separators (`dumped_models\classification\...` on Windows). The adapter normalizes keys to `/`, and `train.py` now writes POSIX keys (`as_posix()`), so manifests are portable. Existing runs are untouched.
- Unpickler allowlist: exact Doc2Vec/numpy/builtins globals plus any `sklearn.`/`xgboost.` module (needed for the ten candidate classifiers); integrity relies on the verified hashes. All ten fixture classifiers load through it.
- Serving casts engineered features to float32 before `transform` and the result to float32, matching training; fixture test vectors match `data_X_test.npy` within 1e-6.
- Unrelated pre-existing working-tree deletions (root `evaluation_results.csv`, `label_conflicts.csv`, `importance_report/`, legacy loose pickles in `dumped_models/classification/`) were left unstaged and are not part of this change.
- Verification run: web backend 30/30; root tests 24/24; frontend typecheck, lint, unit 26/26, contracts:check, build, integration 1/1, browser 11/11 and `test:real-model` 1/1 (Edge channel, `IAP_WEB_RUN_PATH` pointed at a scratch fixture run). No real (non-fixture) run was trained.

## Spec Change Log

## Review Triage Log

## Design Notes

Parity by construction: both training and serving call `pipeline_cache._process` and `preprocess.infer_document_vector`; the preprocessing signature hashes `preprocess.py`/`pipeline_cache.py`, stopwords and lemmatization, so any drift fails startup instead of silently changing predictions.

## Verification

**Commands:**
- `.venv/Scripts/python.exe -m unittest discover -s web/backend/tests -v` -- expected: all pass.
- `.venv/Scripts/python.exe -m unittest discover -s tests -v` -- expected: 24/24 pass.
- `npm.cmd test` and the checks listed in `web/backend/README.md` (from `web/frontend`) -- expected: pass.
