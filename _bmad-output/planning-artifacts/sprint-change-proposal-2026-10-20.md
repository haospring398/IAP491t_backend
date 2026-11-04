---
title: Sprint Change Proposal — 19-10 pipeline adoption
status: approved
created: 2026-10-20
approved: 2026-10-20
mode: incremental
scope: moderate
trigger: Root offline pipeline replaced with the 19-10 upstream version (uncommitted working tree)
---

# Sprint Change Proposal — 19-10 Pipeline Adoption

## 1. Issue summary

The root offline pipeline now follows the 19-10 version of `buidangduy05/IAP491t_backups` (commit `ae08251`). The planning documents (PRD, addendum, architecture spine, SPEC and companions, dated 2026-10-05/06) do not mention this version, its phishing-only training target, validation-based thresholds, BERT candidate or EPVME corpus, and several of their code-gap statements are now wrong.

Discovered on 2026-10-20 while refreshing repository context. The change is a technical/strategic shift in the research pipeline, not a failed story; no epics exist, so the SPEC capabilities and E-gates stand in for epics.

Evidence (verified 2026-10-20 against the working tree; changes are uncommitted on top of `5cce305`):

- `train.py`: `TARGET_MODE = 'phishing'` keeps class 0 plus `LabelKind == 'phishing'` and writes `label_scope_excluded.csv`; group-disjoint `split_train_validation_test`; per-classifier threshold selection on validation with `MIN_VALIDATION_PRECISION = 0.90`; BERT branch; `--mode specialists|baseline`, `--output runs/<name>`; writes schema-version-2 `run_manifest.json`; does not use `artifact_store.py`.
- `evaluate.py`: main guard present; CSV and ROC plots use positive-class scores; `--run` selects the run folder.
- Incomplete upstream copy: `preprocess.py` lacks `BertEmailClassifier`, `split_train_validation_test`, `prepare_semantic_text` and attachment inspection; `specialists.py` is absent. `train.py`, `predict_specialists.py` and `tests/test_pipeline.py` cannot import.
- `runs/2026-10-19_bert/`: `target_mode = phishing`, `selected_model = XGBoost` (validation threshold 0.112, precision 0.928, recall 0.997), `test_used_for_selection = false`. Its manifest lists 53 engineered features; current `preprocess.FEATURE_NAMES` has 40 (the 13 extra are `attachment_*` inspection counts). Validation/test arrays and BERT score arrays are absent; `bert/tokenizer.json` and `bert/vocab.txt` hashes differ from the manifest (16 of 18 present artifacts match).
- `analyze_feature_importance.py` hardcodes `DOC2VEC_DIM = 100`.
- Tests: root suite ran 9 tests, 1 passing (`test_pipeline` import error; `test_evaluate` drifts from 19-10 code). `web/backend/tests` ran 25 tests, all passing (~4 min).
- Web demo unaffected: still pinned to `dumped_models/classification/runs/e7dcdcc3551e46fc93582836f4a74976` (40 + 100 = 140) and verified through `artifact_store.py`'s `manifest.json`.

## 2. Impact analysis

**Epic (capability) impact.** CAP-1–CAP-4 and CAP-6 are unaffected; the local demo keeps its pinned run and contract. CAP-5 / E0 is materially affected: the 19-10 phishing target mode is a candidate E0 path (Q1/Q2), but E0 is now additionally blocked on restoring the missing upstream code (new Q7), and BERT raises an unplanned architecture question (new Q8).

**Story impact.** No stories exist. One new ML work item is needed: obtain the missing upstream modules/functions (Q7) before any E0 inventory or retraining.

**Artifact conflicts.**

| Artifact | Conflict |
| --- | --- |
| PRD `prd.md` | No mention of pipeline update; open-question table lacks Q7/Q8 |
| PRD `addendum.md` | Assumes a single 40-feature schema; no claim boundary for validation-only metrics |
| `ARCHITECTURE-SPINE.md` | Structural seed shows root `backend/`; Deferred offline-cleanup row is stale; no BERT entry; manifest schema mismatch unrecorded |
| SPEC `SPEC.md` | No pipeline-update note; Q7/Q8 missing |
| SPEC `brownfield-and-evidence.md` | States "no evaluate main guard" and "label-based CSV AUC" |
| SPEC `model-and-inference.md` | Same stale statements; single 40/140 width; root-report wording; no E0 candidate note |
| SPEC `deployment-and-acceptance.md` | Test baseline unstated; no backend test row; E0 window ignores Q7; ownership lacks Q7/Q8 |
| DESIGN / EXPERIENCE | None (already Legit/Phishing) |
| `AGENTS.md`, `deferred-work.md`, `web/docs/` | Context refresh pending; two deferred items closable; snapshots stale |

**Technical impact.** No code, contract or deployment change. The web verifier cannot load schema-2 runs, so any future release from the 19-10 pipeline needs an exporter step (recorded under Architecture Deferred, not implemented here).

## 3. Recommended approach

**Option 1 — Direct adjustment (selected).** Update the documents with the verified facts and add Q7/Q8 plus one ML prerequisite work item. Effort: low. Risk: low. Timeline: E0's estimate now starts after Q7.

- Option 2 — Rollback to pre-19-10 code: not viable; the 19-10 adoption is the user's chosen direction.
- Option 3 — MVP review: not needed; FR/NFR scope and the E0 gate are unchanged.

## 4. Detailed change proposals (all approved)

### Proposal 1 — SPEC `brownfield-and-evidence.md`, "Architecture and actual code gaps" (line 59)

OLD:
> The audit's 2026-10-05 static observations expose gaps between AGENTS conventions and actual scripts. Fresh 2026-10-06 read-only rg/AST checks confirm no training artifact-store publication/save_training_run function, loose pickle writes, no evaluate main guard and label-based CSV AUC; importance width remains hardcoded and tests expect absent training state/functions. These are implementation gaps to reconcile before release qualification, not conflicting permission to weaken conventions. No affected module was imported or executed.

NEW:
> The audit's 2026-10-05 static observations expose gaps between AGENTS conventions and actual scripts. **Pipeline update 2026-10-20:** the root pipeline now follows the 19-10 version of `buidangduy05/IAP491t_backups` (commit `ae08251`). `evaluate.py` has a main guard and computes CSV/plot ROC-AUC from positive-class scores; `train.py --output runs/<name>` writes a schema-version-2 `run_manifest.json` with `target_mode`, validation-selected classifier and per-model thresholds, without `artifact_store.py` publication. Remaining gaps: the upstream version is incomplete (`preprocess.py` lacks `BertEmailClassifier`, `split_train_validation_test`, `prepare_semantic_text` and the attachment inspection behind 13 features; `specialists.py` is missing), so `train.py`, `predict_specialists.py` and `tests/test_pipeline.py` cannot import; importance width remains hardcoded at 100; the web demo verifier reads `manifest.json` and cannot load schema-2 runs. These are implementation gaps to reconcile before release qualification, not conflicting permission to weaken conventions.

Rationale: the old paragraph's evaluate claims are false for current code; the new one records verified remaining gaps.

### Proposal 2 — SPEC `model-and-inference.md`

**2a. Feature contract (line 38).** OLD: "Expected embedding/total widths are 100/140. Verify actual `vector_size`, …" NEW:
> Expected embedding/total widths for the current code and the pinned local demo run are 100/140. The 2026-10-19 phishing-target candidate run records 53 engineered features (the 40 above plus 13 attachment-inspection counts produced by upstream code absent from this repository), so a release built from it needs width 153 and matching preprocessing code. Verify actual `vector_size`, …

**2b. Evaluation and parity (line 68).** OLD: "… `evaluate.py` overwrites root reports and runs only when regeneration is intended." NEW:
> … `evaluate.py --run runs/<name>` overwrites the reports in the run folder it is given and runs only when regeneration is intended.

**2c. Legacy seams (line 76).** OLD: "Current static checks confirm legacy loose-file training publication, import-time evaluation, label-based CSV AUC, test expectations for missing training APIs and hardcoded importance width." NEW:
> As of the 2026-10-20 pipeline update, evaluation is import-guarded and uses positive-class ROC-AUC; training writes a schema-2 run manifest under its `--output` folder rather than publishing through `artifact_store.py`. Remaining gaps are missing upstream modules/functions, test expectations for them, and hardcoded importance width.

**2d. E0 evidence required (append).** NEW:
> The 19-10 pipeline provides a candidate E0 path: `TARGET_MODE = 'phishing'` keeps class 0 plus records whose `LabelKind` is `phishing`, and logs excluded rows to `label_scope_excluded.csv`; splits are group-disjoint; and classifier/threshold selection uses validation with a 0.90 precision target. Its 2026-10-19 run selected XGBoost on validation, but test arrays/scores are absent, two BERT tokenizer hashes differ from the manifest, and its 53-feature schema cannot be reproduced with current code. It is therefore candidate evidence, not a passed E0. Per-source provenance review (Q1) is still required.

Rationale: two feature schemas now exist; three statements are stale; the phishing mode is new Q1/Q2 evidence but not E0.

### Proposal 3 — `SPEC.md`

**3a. Insert after the "Hosting update 2026-10-19" line (line 24).** NEW:
> Pipeline update 2026-10-20: the root offline pipeline now follows the 19-10 upstream version, adding a phishing-only training target, validation-based classifier/threshold selection and a BERT candidate. The upstream copy is incomplete and its 2026-10-19 candidate run is not reproducible with current code. The local demo still uses pinned run `e7dcdcc3551e46fc93582836f4a74976`; this update does not pass E0 or change the web contract.

**3b. Append to Open Questions.** NEW:
> - **Q7:** Which upstream revision supplies the missing `specialists.py`, `BertEmailClassifier`, `split_train_validation_test`, `prepare_semantic_text` and attachment-inspection code, so training, tests and the 53-feature candidate become reproducible?
> - **Q8:** Should the qualified release use the Doc2Vec + engineered-feature classifier (AD-1/AD-3), or is BERT in scope? BERT requires a new architecture decision covering its text policy, resources and parity.

Rationale: the canonical contract records the update; Q7 is a new prerequisite; Q8 keeps BERT from being adopted implicitly.

### Proposal 4 — SPEC `deployment-and-acceptance.md`

**4a. Baseline table (line 18).** OLD: "| Existing pipeline checks | `.venv/Scripts/python.exe -m unittest discover -s tests -v` per AGENTS.md |" NEW:
> | Existing pipeline checks | `.venv/Scripts/python.exe -m unittest discover -s tests -v` per AGENTS.md; on 2026-10-20 it ran 9 tests with 1 passing (`test_pipeline` cannot import missing `specialists`; `test_evaluate` drifts from 19-10 code), so report against that baseline |
> | Local demo checks | `.venv/Scripts/python.exe -m unittest discover -s web/backend/tests -v` (25 tests passed on 2026-10-20) plus the frontend checks in `web/backend/README.md` |

**4b. Gate table, E0 row (line 41).** OLD window: "1-2 days inventory; retraining separately estimated". NEW window: "1-2 days inventory after Q7 restores the missing upstream code; retraining separately estimated". Evidence column unchanged.

**4c. Decision ownership (append).** NEW:
> | Q7 missing upstream pipeline code | ML | Before any retraining, E0 inventory or reproduction of the 2026-10-19 candidate |
> | Q8 BERT versus Doc2Vec release architecture | ML and architecture | Before selecting a BERT release; requires a new AD |

Rationale: actual test baselines prevent misattributed failures; E0 timing depends on Q7; Q7/Q8 need owners.

### Proposal 5 — PRD `prd.md`

**5a. Insert after the "Hosting update 2026-10-19" line (line 13).** NEW:
> Pipeline update 2026-10-20: the offline pipeline now follows the 19-10 upstream version with a phishing-only training mode and validation-selected thresholds. This provides candidate evidence toward Q1/Q2 but does not pass E0: the upstream copy is incomplete and its candidate run is not reproducible with current code. FR/NFR scope is unchanged.

**5b. Open-questions table (append after Q5).** NEW:
> | Q7 | Upstream revision supplying the missing pipeline modules/functions needed for training, tests and the 53-feature candidate | ML workstream | Before E0 inventory or retraining |
> | Q8 | Whether the qualified release stays on Doc2Vec + engineered features or adopts BERT | ML and architecture workstreams | Before selecting a BERT release |

Rationale: the final PRD's requirements stand; it records new evidence and the new blocker, aligned with SPEC numbering (Q6 is the SPEC's UX question).

### Proposal 6 — PRD `addendum.md`

**6a. Technical baseline (line 21).** OLD: "The current expected feature schema is 40 engineered features and a 100-dimensional embedding, totaling 140; actual ordered schema and artifact widths must be checked." NEW:
> The current code and pinned local demo run use 40 engineered features and a 100-dimensional embedding, totaling 140. The 2026-10-19 phishing-target candidate records 53 engineered features (153 total), whose 13 attachment-inspection features depend on upstream code absent here (Q7). Actual ordered schema and artifact widths must be checked against the selected release.

**6b. Evidence and claim boundaries (append to the first paragraph, line 44).** NEW:
> The 2026-10-20 adoption of the 19-10 pipeline adds a phishing-only target mode and validation-selected thresholds. Its 2026-10-19 run reports validation metrics only; test arrays/scores are absent, so no test-set or phishing-only quality claim is established.

Rationale: two schemas now exist; high validation metrics must not be reported as test results.

### Proposal 7 — `ARCHITECTURE-SPINE.md` (AD-1–AD-13 rules unchanged)

**7a. Insert after the "Hosting update 2026-10-19" line (line 30).** NEW:
> Pipeline update 2026-10-20: the offline pipeline follows the 19-10 upstream version (phishing-only target mode, schema-2 `run_manifest.json`, validation-selected thresholds, BERT candidate). AD-1 through AD-13 are unchanged; the resulting gaps and BERT question are recorded under Deferred.

**7b. Structural seed tree (lines 182–194).** Move `backend/  application ports, HTTP supervisor, worker, inference adapter` from the repository root to under `web/`, after `frontend/`, matching commit `5cce305`.

**7c. Deferred, offline-cleanup row.** OLD:
> | Offline training/evaluation/importance cleanup — ML implementation | Before generating/qualifying a new release, reconcile actual loose-file publication, import-time evaluation and hardcoded dimensions with required AGENTS conventions. Never import those scripts into the service. |

NEW:
> | Offline pipeline completion — ML implementation | Before generating/qualifying a new release, restore the missing 19-10 upstream modules/functions (Q7), make `analyze_feature_importance.py` read the release's embedding width instead of hardcoding 100, and have the offline exporter translate the schema-2 `run_manifest.json` into the AD-2 deployment manifest. The current web verifier reads `manifest.json` and cannot load schema-2 runs. Never import those scripts into the service. |

**7d. Deferred, new row.** NEW:
> | BERT classifier candidate — ML + architecture | Before selecting a BERT release (Q8). AD-1/AD-3/AD-4 assume Doc2Vec + scaled engineered features with one classifier; BERT needs a new AD for its text policy, windowing/aggregation, GPU-free CPU resources, determinism and parity before it can serve. |

Rationale: the backend move was not reflected; the cleanup row is stale; BERT conflicts with the current ADs and AD-12's no-required-GPU rule.

### Proposal 8 — Secondary artifacts and handoff

- **8a. `AGENTS.md`:** resume `bmad-project-context` refresh in a fresh context. Carry the prepared ledger (18 retain, 4 rewrite: orientation, project-root/path line, test line with 1/9 baseline, hardcoded `DOC2VEC_DIM`) and the verified additions (web backend's dependency on root `preprocess.py`/`artifact_store.py`, backend test command, `npm.cmd`, generated `contracts.generated.ts`, `web/docs/` as synced snapshots), plus: do not use `runs/2026-10-19_bert` for web or inference until current code reproduces its 53-feature schema. The five interview questions remain open.
- **8b. `implementation-artifacts/deferred-work.md`:** after 8a, close "Refresh the ROC-AUC warning in AGENTS.md" (the block already states probability ROC-AUC) and "Document the web/backend package…"; keep "training-run manifest" and "consistent report set" (`evaluate.py` still writes CSV before plots).
- **8c. `web/docs/`:** after 1–7 and 8a, run `node web/scripts/sync-docs.mjs`; `PROJECT-CONTEXT.md` is currently stale.

## 5. Implementation handoff

**Scope: Moderate** — documentation updates across planning artifacts plus one new ML prerequisite; no replan of MVP scope.

| Order | Owner | Responsibility |
| --- | --- | --- |
| 1 | Developer agent (or `bmad-spec` / `bmad-prd` / `bmad-architecture` in update mode) | Apply Proposals 1–7 exactly as written; keep document statuses (PRD/architecture `final`, UX `draft`) |
| 2 | `bmad-project-context` | Proposal 8a and 8b |
| 3 | Developer agent | Proposal 8c snapshot refresh |
| 4 | ML workstream | Q7: obtain the missing upstream modules/functions; prerequisite for E0 inventory and retraining |
| Later | ML + architecture (`bmad-architecture`) | Q8: decide whether BERT enters the release architecture |

**Success criteria**

- No planning document still states "no evaluate main guard" or "label-based CSV AUC".
- Q7 and Q8 appear in PRD, SPEC and deployment ownership with owners.
- The architecture structural seed shows `web/backend/`.
- `web/docs/` snapshots match `web/docs/manifest.json` after sync.
- No document claims E0, test-set or phishing-only quality from the 2026-10-19 run.

Sprint status: N/A — no `sprint-status.yaml` exists; no epics were added, removed or renumbered.

## Approval and handoff log

- 2026-10-20: Proposals 1–8 approved individually in incremental mode; complete proposal approved by the user without conditions.
- Scope classified **Moderate**; routed to the Developer agent (Proposals 1–7, 8c), `bmad-project-context` (8a, 8b) and the ML workstream (Q7), with Q8 held for ML + architecture.
- No planning artifact, code, contract or model was modified by this workflow; edits are applied by the handoff owners above.
