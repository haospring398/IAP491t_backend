---
title: 'Merge upstream v6 pipeline code into the root pipeline'
type: 'feature'
created: '2026-11-07'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '28292cd70bdd7c1ec55e603a23351a4597f2c62b'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The root pipeline still follows upstream b535958 (53 FEATURE_NAMES, BERT); upstream buidangduy05/IAP491t_backups has since published the v6 code (a202d55; HEAD 3c88826 changes only a run manifest) that trained the served baseline_v6 run, so root training cannot reproduce or extend v6.

**Approach:** Three-way merge, file by file, base upstream b535958 → upstream a202d55, onto the local files (histories are unrelated). Upstream wins on design: 134 BASELINE_FEATURE_NAMES, ATTACHMENT_RULES, `--features-only`/`--from-features` stages, `load_data_malspam`, no BERT. Keep the useful local parts: raw TREC 2007 loader (loaded first, supersedes TREC_07.csv) and `--feature-set` where it still applies to the 134 features.

## Boundaries & Constraints

**Always:** Root files only; code comments and README in Vietnamese. Preserve labels 0/1, Windows path handling, dedup-before-split, train-only scaler, Doc2Vec-then-features order. Keep `infer_document_vector`. Missing `Dataset/malspam` must not be an error.

**Never:** Touch `web/` (frozen copies stay byte-exact), `Dataset/`, `runs/`, `model/`, `paper/`. Do not stage the pre-existing deletions of root legacy artifacts or `web/frontend/next-env.d.ts`. Do not train or run evaluate.py on real data.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full load | trec07p + phishing + others present | trec07p loaded first; TREC_07.csv excluded; malspam absent → skipped | Wrong order still raises |
| Feature set | `--feature-set no_era_proxies` | 131 engineered columns; `settings.feature_names`/`feature_set` record them | Unknown set rejected by argparse |
| Two stages | `--features-only` then `--from-features` | Export holds all 134; feature set applied at vectorize | Both flags together → parser error |

</frozen-after-approval>

## Code Map

- Trial merge: scratchpad `m/` (`*.base` b535958, `*.up` 3c88826, `*.local`, `*.merged`), upstream clone `up/`. CRLF stripped before merge.
- Clean merges, take `*.merged` as is: `analyze_feature_importance.py`, `benchmark_pipeline.py`, `dataset_audit.py`, `evaluate.py`, `pipeline_cache.py`, `predict_specialists.py`, `specialists.py`, `preprocess.py` (keeps local `infer_document_vector`; drops `BertEmailClassifier`, `prepare_semantic_text`).
- `load_data.py` -- 3 conflicts, union: keep TREC07P constants + `load_data_trec07p` and add MALSPAM constants/loader; `SINGLE_MESSAGE_DIRNAMES` includes trec07p; discovery skips malspam zips and keeps `in_trec`.
- `train.py` -- 10 conflicts: upstream structure (`prepare_features`/`vectorize`/`export_features`, `shrink`), plus `load_data_trec07p` first in `load_training_emails`, plus feature set.
- `requirements.txt` -- keep upstream `tldextract==5.4.0`; drop torch/transformers/safetensors.
- `tests/test_pipeline.py` -- keep both trec07p and malspam tests; adapt the local `html_content` ablation test to the new feature sets.
- `tests/test_shap.py` -- calls `train.training(..., train_bert=False)`; remove that argument.
- Local-only, keep: `artifact_store.py` (legacy FEATURE_NAMES manifests, test_evaluate), `analyze_shap.py` (reads `settings.feature_names`).
- `README.md` -- 3 conflicts: upstream text + local trec07p/feature-set/web sections.
- `AGENTS.md` -- merge base now a202d55; BERT and FEATURE_NAMES conventions updated.

## Tasks & Acceptance

**Execution:**
- [x] Clean files -- copy `*.merged` into the project (CRLF/LF as each local file had) -- upstream changes the local side never touched.
- [x] `load_data.py` -- resolve as above -- both corpora loadable.
- [x] `train.py` -- resolve; `FEATURE_SETS = ('full', 'no_era_proxies')`, drop list `ERA_PROXY_FEATURES` over BASELINE_FEATURE_NAMES, applied in `vectorize` by name; `--feature-set` flag passed through `training`; remove BERT code -- `no_html_presence`/`html_content` are now upstream defaults.
- [x] `requirements.txt`, `tests/test_pipeline.py`, `tests/test_shap.py` -- as Code Map.
- [x] `README.md`, `AGENTS.md` -- merged docs; run `node web/scripts/sync-docs.mjs` after AGENTS.md.

**Acceptance Criteria:**
- Given the merged tree, when `python -c "import train, evaluate, specialists, predict_specialists, benchmark_pipeline, analyze_feature_importance, analyze_shap, artifact_store"` runs, then no ImportError.
- Given the merge, when diffing each merged file against upstream a202d55, then the only differences are the documented local parts.
- Given web/, when diffing, then nothing changed and frozen copies keep their hashes.

## Design Notes

Upstream v6 already removed `is_html`/`html_to_text_ratio` and added the HTML security counts, so local `no_html_presence` and `html_content` equal v6 `full`. Only `no_era_proxies` (drop `num_https_urls`, `num_http_urls`, `has_hidden_elements`) still differs. Rule features stay present, so evaluate.py's rule lookup by `settings.feature_names` keeps working.

## Verification

**Commands:**
- `.venv/Scripts/python.exe -m unittest discover -s tests -v` -- expected: all pass (QR test may skip).
- `git diff --stat -- web` -- expected: empty.

## Implementation Notes

- Nine files are byte-identical to upstream a202d55 (the seven clean merges plus requirements.txt; preprocess.py keeps infer_document_vector because upstream added it too). Root preprocess.py and pipeline_cache.py now equal the frozen web copies in content; only line endings can differ.
- requirements.txt taken from upstream whole: drops torch/transformers/safetensors (BERT) and nltk/textblob (v6), adds tldextract==5.4.0 and magika==1.0.3 (both already in .venv).
- train.py = upstream + trec07p loaded first (through `shrink`), `feature_columns`/`FEATURE_SETS = ('full', 'no_era_proxies')` applied in `vectorize` and `prepare_data`, `training(feature_set=...)`, `--feature-set` (rejected with `--mode specialists` and `--features-only`), as_posix artifact keys.
- load_data.py: discovery skips malspam zips before the Phishing Pot/trec07p checks; comment notes that download_malspam.py is unpublished.
- Local-only tests adapted: test_evaluate BERT test now asserts old BERT entries are skipped (upstream evaluate behaviour); interrupted-training test patches prepare_features/vectorize. New tests: CLI option conflicts, `--from-features` with `no_era_proxies`.
- README rebuilt from upstream's rewrite plus local provenance, folder tree, trec07p, feature set, web demo; references to unpublished sandbox/, download_malspam.py and docs are marked as such.
- `node web/scripts/sync-docs.mjs` refreshed web/docs/PROJECT-CONTEXT.md and manifest.json (expected snapshot sync); web/backend unchanged. web/frontend/next-env.d.ts was already modified before this work.
- Root tests: 49 ran, 48 passed, 1 skipped (QR, zxing-cpp absent).
- Review patches: compressed-load check in the trec07p test, --from-features target-mode/feature-name refusals, specialists mode rejects --features-only/--from-features, README (Python strict caveat, --mode default, pre-v6 runs, inference column selection), ArtifactStoreTests docstring. Root tests after patches: 49 ran, 48 passed, 1 skipped.

## Spec Change Log

## Review Triage Log

Layers: blind-hunter (BH), edge-case-hunter (EC), verification-gap (VG). "Upstream" = code byte-identical to a202d55, not written by this merge.

| # | Layer | Finding | Verdict | Evidence / route |
|---|---|---|---|---|
| 1 | BH, EC | AGENTS says root preprocess.py byte-identical to a202d55 but it is LF, frozen copy CRLF | false | Root sha beba69b8 equals the a202d55 git blob; the CRLF bytes are upstream's training checkout, already explained in AGENTS/README. Rejected |
| 2 | BH, EC | No .gitattributes pins line endings of root preprocess.py/pipeline_cache.py; autocrlf changes the signature per checkout | medium | Verified: no root .gitattributes, core.autocrlf=true, signature hashes bytes. Pre-existing; LF vs CRLF is a user choice. defer |
| 3 | BH | Docs do not say root-trained runs get a signature other than 4c010fc3 | low | Same root cause as #2; README now explains line-ending dependence. Merged into #2 |
| 4 | BH | README omits the getaddresses(strict) Python caveat | low | Verified in AGENTS web notes. patch (README Cài đặt) |
| 5 | BH | Signature lacks Python version / strict flag | low | Upstream design. Rejected (fix adds surface to upstream code) |
| 6 | BH | load_exported_features does not compare signature with current code | false | The run records the export's own signature, which is what the model was trained on. Rejected |
| 7 | BH | README inference note ignores no_era_proxies column selection | low | Verified. patch (README) |
| 8 | BH | positive_label 'phishing' while malspam/EPVME are positives | medium | Upstream labels; disclosure convention lives in AGENTS. defer |
| 9 | BH | predict_specialists KeyError on old manifests with BERT text branch | low | Upstream code. defer |
| 10 | BH, EC | Spec says web/ untouched but sync-docs changed web/docs | low | True, expected snapshot sync; fix edits spec. Rejected |
| 11 | BH | Spec mixes 3c88826 and a202d55 | false | Code Map and Intent both state 3c88826 changes no code. Rejected |
| 12 | BH | AGENTS still says baseline_v6 selected MLP | low | Local manifest is 867316b (MLP); AGENTS edit. defer |
| 13 | BH | Upstream English comments vs Vietnamese-comment policy | low | Byte-identical upstream files; AGENTS exception. defer |
| 14 | BH | README silent on --from-features provenance (no ingestion.sqlite, unhashed copies, cache/workers ignored) | low | Upstream behaviour, rare. Rejected |
| 15 | BH | --mode default changed specialists→baseline undocumented | low | Verified (28292cd default specialists). patch (README) |
| 16 | BH | README says pre-v6 runs unusable though evaluate works | low | Verified. patch (README wording) |
| 17 | BH | No combined full-load test | low | Covered by #19 patch plus existing trec07p/malspam tests. Merged into #19 |
| 18 | BH, EC | DatasetAudit / raw_email_store leave scratch files on crash | low | Upstream. defer |
| 19 | VG | Compressed load path (compress=True, EmailStore) with trec07p untested | gap | patch: trec07p test now reloads with EmailStore and compares raw bytes, labels, order |
| 20 | VG | --from-features target-mode and feature-name guards untested | gap | patch: two assertRaises added to export test |
| 21 | VG | audit_dataset with malspam/trec07p untested | gap | Diagnostic path, untested before. defer |
| 22 | VG, EC | --mode specialists silently ignores --features-only/--from-features | low | Verified in train.py CLI. patch: parser.error + CLI test case |
| 23 | VG | training(features_only=True, from_features=...) trains | low | Python API only; CLI rejects. Rejected |
| 24 | VG | Stale ArtifactStoreTests docstring | low | Verified. patch (docstring) |
| 25 | EC | _simhash None + 64-bit ints cast to float64, rounding fingerprints | medium | Verified with pandas (2**64-3 -> 2**64). Upstream code that also trained v6; fixing diverges. defer |
| 26 | EC | Malspam zip NotImplementedError/EOFError escape | low | Upstream; no malspam data locally. defer |
| 27 | EC | CompressedEmail turns str CSV rows into bytes; CLI and training(data=) parse differently | maybe-false | Reviewer reports verified; not re-run here. Upstream. defer (medium if true) |
| 28 | EC | Two rows Selected-on-validation=True with attachment rules | low | Upstream evaluate. Rejected |
| 29 | EC | attachment_rule_flags docstring vs old runs | low | Upstream. Rejected |
| 30 | EC | All-BERT manifest crashes plotting | low | Unreachable for current runs. Rejected |
| 31 | EC | Non-string JSONL text in export | false | Export is hash-verified own output. Rejected |
| 32 | EC | Provenance files copied without hash | low | Upstream. Rejected |
| 33 | EC | load_all_datasets logs malspam as excluded but never loads it | low | Upstream behaviour; load_all_datasets has no caller. Rejected |
| 34 | EC | _with_recipient checks only first To | low | Upstream. Rejected |
| 35 | EC | Lone surrogate in str email raises | low | Upstream. defer |
