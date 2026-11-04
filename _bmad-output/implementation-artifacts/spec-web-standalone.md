---
title: 'Run the web folder standalone, without the parent project'
type: 'refactor'
created: '2026-10-29'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '6ed340681a1abf3daaca5a9337f1e83cdc9eec1a'
context: ['{project-root}/AGENTS.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `web/` only runs inside the full repository. The backend is imported as `web.backend` from the project root, resolves the pinned run under the root `runs/`, needs the root `.venv` (ML packages are unpinned in `web/`) and its `nltk_data`, and its tests train their fixture through root `train.py` and `dataset_audit.py`.

**Approach:** Make `web/` self-contained. The backend uses package-relative imports and resolves contracts, the run and samples against the `web/` folder. A stdlib script copies a verified run (and the NLTK data it was trained with) into `web/`. Pinned requirements cover the whole backend. The tests use a committed fixture run. Starting from the project root with `python -m web.backend` keeps working.

## Boundaries & Constraints

**Always:**
- Keep every current startup check: complete schema-2 manifest, SHA-256 of the artifacts that are loaded, feature names, preprocessing signature and stopwords, model types and widths, and the XGBoost additivity check on `data_X_test.npy`.
- Keep `frozen_pipeline/*.py` byte-identical.
- Keep the HTTP contract and UI copy unchanged.
- Write comments and README text in Vietnamese.

**Never:**
- Modify `runs/`, `Dataset/`, `model/` or the legacy run.
- Import any root module at backend runtime or in backend tests.
- Commit model artifacts larger than the fixture.
- Make `sync-docs.mjs` standalone. It stays a parent-repository tool.

**Decisions (human, 2026-10-29):**
- Model files travel by bundling into `web/model/`, which git ignores. Copying or zipping `web/` carries them; a git clone re-runs the bundle script.
- The bundle is the full run: `run_manifest.json` plus all manifest artifacts (about 665 MB). Adapter verification is unchanged.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Standalone start | `web/` copied alone with a bundled run; `python -m backend` run from `web/` | `/health/ready` is 200; analysis works | N/A |
| Root start | full repo; `python -m web.backend` run from the root | Same behavior as today | N/A |
| No bundle | `web/` copied without `model/` and no `IAP_WEB_RUN_PATH` set | Liveness 200, readiness 503 (not ready), no classification | Existing `StartupFailure` stage |
| Tampered bundle | A bundled artifact's bytes changed | Not ready (RUN_VERIFICATION) | Existing handling |
| Bundle script, bad source | The source run fails a hash check, or a required file is missing | Exits non-zero; nothing is half-written into `web/model/` | Writes to a temporary folder, then renames it into place |

</frozen-after-approval>

## Code Map

- `web/backend/__init__.py` -- Puts `frozen_pipeline/` first on sys.path. Will also put the bundled `nltk_data` first on the NLTK search path (`NLTK_DATA`, inherited by the spawn child) before NLTK is imported.
- `web/backend/__main__.py:11` -- `uvicorn.run("web.backend.service:app")` becomes `f"{__package__}.service:app"`.
- `web/backend/service.py:16-17`, `adapter.py:13` -- Absolute `web.backend.*` imports become relative. The spawn child re-imports the same qualified name.
- `web/backend/policy.py:7,13,29-35` -- `ROOT=parents[2]` and `"web/contracts"` become `WEB_ROOT=parents[1]` and `"contracts"`. `RUN_PATH` becomes `model/2026-10-23_web2`; relative overrides resolve against `WEB_ROOT`.
- `web/backend/adapter.py:190-205,216-220,284-296` -- `os.chdir` and run resolution move to `WEB_ROOT`; artifact verification stays unchanged; the provenance `run` and `code_sha256` paths (`backend/...`).
- `web/backend/tests/test_demo.py:22-73` and its `ROOT / "web/backend/..."` / `patch("web.backend...")` uses -- Use relative package imports or the `__package__` name. `setUpModule` copies the committed fixture into a temp folder. `record_id` is inlined as `sha256(location)`, matching `dataset_audit.py:10`.
- `web/frontend/tests/integration/real-model.test.ts:13,42-44` -- Use `cwd = web/` and `-m backend`. Take Python from `IAP_WEB_PYTHON`, else `web/.venv`.
- Root `.gitattributes:2`, root `.gitignore` -- The rules for `web/` move into `web/.gitattributes` and `web/.gitignore`.
- Pinned versions (root `.venv`, Python 3.11.2): numpy 2.4.6, scipy 1.17.1, gensim 4.4.0, scikit-learn 1.9.1, xgboost 3.2.0, nltk 3.10.3, beautifulsoup4 4.15.0, textblob 0.20.1, pandas 3.0.6. The signature also hashes the bs4/nltk versions, the stopwords and wordnet availability.

## Tasks & Acceptance

**Execution:**
- [x] `web/backend/{__init__,__main__,service,adapter,policy}.py` -- Relative imports; resolve paths against `WEB_ROOT`; NLTK path -- this is what makes standalone start possible.
- [x] `web/scripts/bundle-run.py` -- New, stdlib only. Run `--run <dir>` from any Python. It verifies the manifest hashes and copies `run_manifest.json`, every manifest artifact, and the NLTK `corpora/stopwords` and `corpora/wordnet.zip` (from `--nltk-data`, default `<repo>/.venv/nltk_data`) into `web/model/<run-id>/` and `web/model/nltk_data/` through a temporary folder.
- [x] `web/backend/requirements.txt` -- `-r requirements-api.txt` plus the ML pins above.
- [x] `web/backend/tests/build_fixture.py` + `web/backend/tests/fixture_run/` -- A generator (needs the full repo; reuses the existing `synthetic_email` and `train.training` call) and the committed small run.
- [x] `web/backend/tests/test_demo.py` -- Use the committed fixture. Remove the root imports.
- [x] `web/frontend/tests/integration/real-model.test.ts` -- Use the standalone launch.
- [x] `web/.gitignore`, `web/.gitattributes` -- Ignore `model/` and `.venv/`; keep `frozen_pipeline/*.py -text`.
- [x] `web/README.md`, `web/backend/README.md`, `AGENTS.md` -- Standalone setup (venv, requirements, bundle, run, tests); note that relative `IAP_WEB_RUN_PATH` now resolves from `web/`. Then run `node web/scripts/sync-docs.mjs`.

**Acceptance Criteria:**
- Given `web/` copied to an empty temp folder outside the repo with a fresh venv installed from `backend/requirements.txt` and a bundled run, when the backend tests run there and `python -m backend` starts, then all tests pass and readiness is 200, with no `.py` files present outside the copy.
- Given the full repo, when `python -m web.backend` runs from the root, then it serves the same run with an identical `manifest_sha256`.

## Verification

**Commands:**
- `.venv/Scripts/python.exe -m unittest discover -s web/backend/tests -v` (root) -- all pass
- Same command run inside a standalone copy (`python -m unittest discover -s backend/tests`) -- all pass
- `npm.cmd run contracts:check; npm.cmd test; npm.cmd run lint; npm.cmd run build; npm.cmd run test:real-model` in `web/frontend` -- pass
- `git diff --quiet -- web/backend/frozen_pipeline` -- unchanged

## Implementation Notes

- The committed fixture is trained with `PYTHONHASHSEED=0`, because Doc2Vec inference depends on Python's hash seed; the vector-equality test runs in a spawned child with the same seed, like the service worker.
- `requirements.txt` starts with a coding line so pip 22 reads its Vietnamese comments.
- Added `web/backend/tests/test_bundle_run.py` (3 tests) to cover the matrix row "Bundle script, bad source".

## Review Triage Log

| # | Source | Finding | Verdict | Evidence / route |
|---|--------|---------|---------|------------------|
| 1 | verification-gap | Root launch `python -m web.backend` with a relative run path is untested | medium | All unit tests set absolute `IAP_WEB_RUN_PATH`; real-model now launches from `web/`. Patch: add a relative-path test with a foreign cwd. |
| 2 | verification-gap, blind | `NLTK_DATA` prepend in `backend/__init__.py` is untested | medium | No test references `NLTK_DATA`; root `.venv` hides a regression. Patch: test that the bundled folder comes first when it exists. |
| 3 | blind | No guard that backend imports no root module | medium | The claim is only manually checked. Patch: test that no loaded module file lies in the repo outside `web/`. |
| 4 | blind, edge | `real-model.test.ts` dropped the root `.venv` fallback; a missing interpreter raises an unhandled spawn error | medium | `spawn` of a missing exe emits `error` with no listener; previously the root `.venv` worked. Patch: fall back to `../.venv`, fail with a clear message. |
| 5 | blind, edge, verification-gap | Two-folder swap in `bundle-run.py` is not atomic; the docs claim no partial copy | low | Second `replace` failing leaves the new run with the old `nltk_data`. Patch: correct the docstring and README wording. |
| 6 | edge | Unanchored `model/` and `.venv/` in `web/.gitignore` | low | Matches any nested `model/` folder; none exists today. Patch: anchor to `/model/` and `/.venv/`. |
| 7 | blind | AGENTS test-count sentence is confusing | low | `discover` reports 41. Patch: state 41. |
| 8 | blind | Mixed English/Vietnamese mid-sentence in `web/README.md` and `web/frontend/README.md` | low | Policy asks README text in Vietnamese. Patch: keep whole sentences in one language. |
| 9 | blind | `RecordId` inlined without a check | low | `build_fixture.py` can assert equality with `dataset_audit.record_id`. Patch. |
| 10 | blind | `--run` resolves from cwd, unlike `RUN_PATH`; undocumented | low | Patch: one doc sentence. |
| 11 | blind, edge | Tests in a git clone without the bundle lack exact NLTK data | medium | Consistent with the human decision that a clone re-runs the bundle; before this change tests needed the root `.venv` NLTK data. Defer. |
| 12 | blind, edge | Shared `nltk_data` and unchecked NLTK source | medium | Stopword mismatch fails closed at startup; wordnet content is not in the signature (pre-existing design). Defer. |
| 13 | blind, edge | Windows locks, `.old-*` leftovers, no pruning of old bundles | low | Rare; fixes add cleanup logic. Reject. |
| 14 | blind | Fixture binaries untracked | false | They are committed in step 5, not missing. |
| 15 | blind | TREC 2007 docs in `README.md`/`AGENTS.md` without code | false | Pre-existing uncommitted user edits, not part of this change; excluded when committing. |
| 16 | edge | `__package__` None when `__main__.py` runs as a script | low | Relative imports already require `-m`; not a supported launch. Reject. |
| 17 | edge | Non-object manifest JSON escapes as a traceback | low | Needs a corrupt manifest; still exits non-zero. Reject. |
| 18 | edge | `wordnet/` directory instead of `wordnet.zip` rejected | low | Root `.venv` has the zip; the error is clear. Reject. |
| 19 | edge | `build_fixture.py` deletes the fixture before copying | low | Developer-only, recoverable from git. Reject. |
| 20 | edge | Root start needs the bundle or `IAP_WEB_RUN_PATH` | false | Matches the human decision and the README. |
