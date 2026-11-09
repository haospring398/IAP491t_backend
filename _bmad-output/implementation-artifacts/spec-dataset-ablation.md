---
title: 'Dataset contribution ablation of the v6 baseline'
type: 'feature'
created: '2026-11-09'
status: 'done'
route: 'dispatch'
baseline_commit: 'a7db1051bad4dc47fa41617b5581089963c5ea24'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The thesis supervisor asks to separate each dataset and measure, compare and demonstrate its contribution to detection. The pipeline only trains on all datasets at once.

**Approach:** A resumable root script `dataset_ablation.py` runs, in priority order:
1. a cross-group near-duplicate overlap report;
2. `reference` plus 2 extra seeds (noise floor);
3. leave-one-out per dataset group;
4. `only_<positive group>` experiments and a random-removal control.

It reuses the verified export `runs/2026-11-08_features_v6` and the `train.py` code path. Every experiment is scored on the identical complete test split, per source/group, with threshold-free and count metrics and deltas against the reference.

## Boundaries & Constraints

**Always:**
- **User decisions:**
  - Retrain Doc2Vec per experiment.
  - Use all 9 classifiers with the unchanged `build_candidates` grids and validation thresholds at precision >= 0.90.
  - Grouping A, positive groups:
    - `nazario` = all `phishing-20xx`, `phishing*.mbox`, `private-phishing4.mbox`, `20051114.mbox`;
    - `phishing_pot`;
    - `epvme`;
    - `malspam`.
  - Grouping A, legitimate groups:
    - `enron` = `enron` + `Enron.csv`;
    - `spamassassin` = raw + `SpamAssasin.csv`;
    - `trec` = `trec07p` + `TREC_05.csv` + `TREC_06.csv`;
    - `ceas`;
    - `ling`.
- **Experiments**, 18 at about 4 h each, run in this order:
  - `reference`, `reference_seed43`, `reference_seed44`. The seed changes the Doc2Vec and classifier seeds, never the split.
  - `without_<group>` × 9.
  - `without_enron_trec` (decision 2026-11-09). It removes `enron` and `trec` together, because they overlap heavily (5,795 near-duplicate clusters; TREC 2005 ham is Enron mail). Train keeps 15,511 legitimate vs 42,889 positive rows, so the class ratio inverts; the README says to read this experiment through per-group AUC/AP and counts, not recall/FPR at the threshold.
  - `only_<positive group>` × 4, each with one positive group and all legitimate groups.
  - `random_like_nazario`, stratified (decision 2026-11-09). It removes whole pure-positive `_group` clusters, drawn at random with a seed and separately for train and validation. The total target equals `without_nazario`'s removed rows in that split.
    - Strata: per positive group, the target is the group's share of all positive rows in the split, including clusters excluded from the draw.
    - Only single-group clusters no larger than 5% of the total target are drawn. Larger clusters are never drawn (e.g. the 6,011-row EPVME XSS template cluster).
    - Tolerance: total within ±1%; each group within ±2% of its own target.
    - `experiment.json` records removed rows and clusters per group, the excluded clusters with their sizes, and the number of clusters `without_nazario` removes.
- **Removal scope.** Removal applies to train AND validation. Test stays complete and identical across experiments.
- **Hash seed.** Re-exec with `PYTHONHASHSEED=0`. Never reuse `runs/2026-11-08_baseline_v6_local`.
- **Resumability.**
  - Each experiment is runnable and resumable on its own: CLI subset, skip completed, lock file.
  - Stop on any Source not in the group table.
- **Per-experiment outputs.** Store the test scores of all 9 models. For each model, record `threshold_constraint_met`, which is `select_threshold`'s `precision_target_met`: False means the fallback threshold with the best F2 was used. Never change `evaluate.py`.
- **Summary contents:**
  - **Overall rows:** the full test split and the full test split excluding `epvme` rows. The second is the headline figure for real phishing.
  - **EPVME provenance, as supplied by the user.** EPVME (Exploiting Protocol Vulnerability Malicious Email) is from Zhang et al., Cybersecurity 8:14 (2025), DOI 10.1186/s42400-024-00309-6; github.com/sunknighteric/EPVME-Dataset (GPL-3.0). EPVME is about 61% of the positive rows.
    - Synthetic emails. Non-payload fields (From/To/Subject/body) are drawn at random, per attack type, from benign or malicious samples of Enron, Nazario, SpamAssassin and TREC07. No per-sample source mapping is published.
    - Payloads: SPF/DMARC header spoofing, S/MIME/OpenPGP signature manipulation (CMS/MIME/ID attacks), and XSS payloads taken from the Wooyun Email XSS dataset (Fang et al., 2020).
    - Header-attack bodies are mostly drawn from malicious samples (phishing or spam). Signature attacks build on the body of benign signed emails, mixed with phishing/spam text and the payload. XSS samples take their non-payload fields from benign samples.
    - Every email is labelled malicious, not strictly phishing.
  - **Per-group metrics:** ROC-AUC and AP, plus TP/FP/FN/TN. A group has a single class, so score it against the complementary class of the full test split: a positive group vs all test legitimate rows, or all test positives vs a legitimate group.
  - **Deltas** per same classifier family.
  - **A fixed-family table and heatmap** that use the family the reference selected. Every experiment retunes that family's grid on its own validation set, so the model is not the same object across experiments.
  - **The validation-selected view.**
  - **A cross-source matrix** (CSV and heatmap): rows are `reference` and the `only_*` experiments, columns are test recall per positive group.
  - **Seed spread**, min/max/std over the 3 reference seeds, overall and per group.
  - `threshold_constraint_met` alongside every row.
  - **Breakdowns from stored scores, no extra training** (decision 2026-11-09), each with its support:
    - Nazario test recall split into rows in clusters that contain EPVME vs pure-Nazario clusters;
    - EPVME test recall per heuristic attack family.
- **Overlap report** (`overlap_by_group.csv`), over the selected rows, per split and in total. For each group pair, count:
  - (a) the clusters that span both groups;
  - (b) the label mix of those clusters, with row counts: same-label clusters (positive–positive or legitimate–legitimate) and mixed-label clusters (positive and legitimate rows).

  List `epvme` × `nazario`, `epvme` × `enron`, `epvme` × `spamassassin` and `epvme` × `trec` first.
- **README wording:**
  - Results are "marginal contribution when the group is removed from train/validation, on a fixed test split".
  - The positive class is malicious email: phishing + malspam + EPVME synthetic.
  - Phishing mode excludes the spam of CEAS/Ling/SpamAssassin/TREC/Enron.csv, so those groups contribute legitimate mail only.
  - Group contents are post exact-dedup, as read from the code:
    - Exact copies with different labels are all dropped (`conflicting_labels`).
    - For same-label copies, one is kept by label rank: legitimate/phishing/malspam first, then malicious_synthetic, then spam. Ties go to the earlier source in load order: `trec07p` → `phishing/` (Nazario + CSVs) → SpamAssassin raw → Enron raw → EPVME → Phishing Pot → malspam.
    - So removing a group cannot remove its exact copies that were attributed to another source.
  - How `group_email_variants` treats near-duplicates, as read from the code:
    - Clusters are formed regardless of label, on the same normalized-body hash or SimHash Hamming distance ≤ 3.
    - Mixed-label clusters are kept, and every row keeps its own label.
    - A whole cluster goes into one split.
    - No near-duplicate conflict resolution exists. EPVME rows can therefore share a cluster, and therefore a split, with the legitimate email they were built from.
  - 3 seeds give only a rough noise estimate.
  - Explain `threshold_constraint_met`.
  - EPVME limitations:
    - (a) Removing a group does not remove its content that lives inside EPVME. For example, `without_nazario` still trains on Nazario bodies through EPVME.
    - (b) `only_epvme` results on Nazario must be read together with the overlap report.
    - (c) EPVME can carry spam bodies with a positive label, which is inconsistent with phishing mode excluding spam. This is why the overall row without epvme is the headline figure for real phishing.
  - Further limitations (decision 2026-11-09, facts verified on the export):
    - 5,871 of 6,171 (≈95%) heuristic-XSS train rows sit in one near-duplicate cluster of 6,011 rows. The cluster is a template whose body is "This is a test mail for XSS." (cleaned text `test mail xss`). Validation has 100 and test 102 heuristic-XSS rows.
    - The XSS payload sits in the From/Subject headers, not in body markup. None of the 36 HTML/script features fires on that cluster, while the header feature `hdr_markup_in_headers` fires on 99.9% of it and on 0% of legitimate train rows. Doc2Vec mainly sees the template sentence.
    - Attack families are heuristic, not source labels. The heuristic total of about 6,373 XSS rows differs from the 4,716 XSS samples that the user reports from Table 2 of the paper.
    - 107 mixed-label clusters with 497 rows: epvme × enron 53, × spamassassin 98, × trec 346.
    - The random control is a single draw.
- **load_data.py comment.** Replace the EPVME provenance comment at `load_data.py:50-55` with the user-supplied provenance above. Change the comment only.
- **Language.** Vietnamese comments and README; English spec.

**Never:**
- Write into `Dataset/`, existing `runs/`, `model/` or `web/`.
- Change `train.py`/`evaluate.py`/`load_data.py` behaviour.
- Use test data for selection.
- Store model pickles.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Overlap | `--overlap` | `overlap_by_group.csv` in seconds, no training | N/A |
| Run | `--features runs/2026-11-08_features_v6 --output runs/2026-11-09_dataset_ablation [--experiments ...]` | One folder per experiment: `experiment.json` (complete), CSVs, `test_scores.npz` | Unknown name → exit listing valid names |
| Resume | Complete experiment with the same export digest and definition | Skipped | Mismatch → refuse; use a new `--output` |
| Parallel or crashed | `lock` present | Skipped with a message | `--unlock NAME` |
| Summary | `--summarize` | Summary CSVs and heatmaps from completed experiments | None complete → clear error |
| New source | Source missing from the table | Stop before training | ValueError naming it |

</frozen-after-approval>

## Code Map

- `train.py:317` `load_exported_features` -- loads the export with hash verification. Frames carry Text, Features, Source, LabelKind, Class, `_group` and RecordId.
- `train.py:246` `vectorize(frames, preprocessing, epochs, seed)` -- Doc2Vec runs with `workers=1`, so it is deterministic given the seed and the hash seed.
- `train.py:347` `build_candidates(y_train, seed)` and `train.py:374` `tune_classifiers` -- reuse both. The decision dict of each winner carries `precision_target_met`. Skip `feature_ablation`.
- `train.py:74-111` -- the load order, quoted in the README.
- `evaluate.py:29-85` -- `positive_scores`, `select_threshold` (fallback to the best F2 at `:57`), `validation_rank`, `classification_metrics`. Per-source rows follow `evaluate.py:248-251`.
- `preprocess.py:2681-2705` -- global exact dedup:
  - conflicting labels → all copies dropped;
  - otherwise one copy kept by `_label_rank`, then load order.
- `preprocess.py:2731-2790` -- `group_email_variants`: label-agnostic union on body hash or SimHash ≤ 3.
- `preprocess.py:2793-2832` -- the group-disjoint split.
- `load_data.py:50-55` -- the EPVME provenance comment, to be replaced. Labels stay `malicious_synthetic`, class 1.
- `web/backend/tests/build_fixture.py:64-67` -- the re-exec pattern.
- `runs/2026-11-08_features_v6/` -- read-only, 29 Sources.
  - Train positives: 42,889 (nazario 6,096, pot 7,345, epvme 26,017, malspam 3,431).
  - Train legitimate: 201,076.
  - Nazario validation: 2,031.
- `tests/test_pipeline.py` -- tiny exports built with `export_features`.
- `AGENTS.md` -- also fix this sentence: "SpamAssassin spam is positive" holds only for `--target-mode broad` (`train.py:148-154`).

## Tasks & Acceptance

**Execution:**
- [x] `dataset_ablation.py` -- Implement:
  - the group table and the experiment registry;
  - the overlap report;
  - the per-experiment run;
  - atomic status, lock and resume;
  - the CLI: `--features --output --experiments --list --overlap --summarize --unlock`, plus a hidden `--doc2vec-epochs`;
  - the summary outputs: `summary_overall.csv`, `summary_by_group.csv`, `summary_fixed_classifier.csv`, `summary_cross_source.csv`, `seed_spread.csv`, `summary_nazario_by_cluster.csv`, `summary_epvme_by_attack.csv` and the heatmaps.

  Rationale: the supervisor's request.
- [x] `tests/test_dataset_ablation.py` -- On a tiny synthetic export with small candidates and few epochs, test:
  - grouping completeness and the unknown-source error;
  - identical test rows across experiments;
  - `without`/`only` removal;
  - cluster-wise random removal: no cluster split, counts within ±1%;
  - pairwise group AUC and the overall row without epvme;
  - `threshold_constraint_met`;
  - resume, lock and definition mismatch;
  - fixed-family deltas, cross-source matrix, seed spread and cross-group overlap counts;
  - cluster label-mix counts:
    - a cluster with an epvme positive and an enron legitimate row is counted once, as mixed, for that pair with its row counts;
    - a cluster with an epvme and a nazario positive is counted as same-label;
    - a cluster within one group is not counted.

  Rationale: guards about 68 h of runs.
- [x] `README.md` -- Add a Vietnamese section: commands, run order, outputs, parallel use and runtime, plus every README wording item from Boundaries.
- [x] `load_data.py` -- Replace the EPVME comment at lines 50-55 with the user-supplied provenance. Comment only.
- [x] `AGENTS.md` -- Add the script and fix the SpamAssassin wording, then run `node web/scripts/sync-docs.mjs`.

**Acceptance Criteria:**
- Given any two experiments, when compared, then their test RecordIds are identical and in the same order.
- Given `without_G`, then no train or validation row belongs to G, and G's rows are flagged `held_out`.
- Given `only_P`, then no other positive group appears in train or validation.
- Given `random_like_nazario`, then its removed train and validation counts are each within ±1% of `without_nazario`'s, each positive group is within ±2% of its stratum target, no cluster larger than 5% of the target is drawn, and no `_group` cluster is split between removed and kept rows.
- Given the root suite on .venv, then everything passes except the zxing skip.

## Implementation Notes

- Implemented directly in the main session, without a subagent.
- **Files touched:**
  - new: `dataset_ablation.py`, `tests/test_dataset_ablation.py`;
  - edited: `README.md` (section "Ablation theo dataset" and folder tree), `AGENTS.md` (script entry, SpamAssassin wording, test count 57/58), `load_data.py` (EPVME comment only);
  - synced: `web/docs`.
- **Row selection works on metadata only.** Selection uses `Source`, `Class` and `_group` from the hash-checked `*_metadata.csv`, so `--list` and `--overlap` run without loading texts: about 4 s and 23 s on the real export. Training loads the full export through `load_exported_features` and asserts that RecordIds align with the metadata.
- **`random_like_nazario` draws only pure-positive clusters.** Taking the positive rows of a mixed-label cluster would split it, which the AC forbids. The draw aims at the exact target and accepts ±1%.
  - On the real export it removes 6,097 of 6,096 train rows and 2,032 of 2,031 validation rows.
- **Rows that contradict their group stop the run.** `annotate` raises when a row's class contradicts its group, e.g. spam leaking in from a broad-mode export. `load_metadata` also refuses non-phishing exports.
- **`--overlap` result on the real export, totals:**
  - `epvme`×`nazario`: 1,325 clusters, all same-label except 1.
  - `epvme`×`enron`: 12 clusters, all mixed.
  - `epvme`×`spamassassin`: 16, all mixed.
  - `epvme`×`trec`: 79, all mixed.
  - `enron`×`trec`: 5,795 clusters, all same-label legitimate. TREC 2005 is built on Enron mail.
- **Verification:**
  - `tests.test_dataset_ablation`: 9 tests OK.
  - Full root suite: 58 tests, OK, 1 skipped (zxing).
- **Review patches (pass 1):**
  - A re-check after taking the lock.
  - Per-experiment failure handling: `status: failed` plus the traceback, the queue continues, exit code 1.
  - The `ablation.json` output marker: refuses foreign, non-empty or `--features` folders.
  - The resume key now includes the epochs and `PYTHONHASHSEED`. `environment` records library versions and code hashes.
  - `summarize` refuses mixed exports or settings.
  - Overlap label mix is computed per pair.
  - A `delta_vs_reference_selected_Rate` column for the selected-model heatmaps.
  - A zero-delta heatmap scale.
  - Test RecordIds are checked inside `run_experiment` and hashed from the vectorized rows.
  - `TREC_07.csv` added to the group table.
  - Mutually exclusive mode flags. `--doc2vec-epochs` must be ≥ 1.
  - README corrections: train vs validation ratios, EPVME share per split, `enron`×`trec` overlap, the 6,011-row EPVME cluster, the threshold caveat for `without_epvme`, parallel summaries.
  - Tests grew to 13.
  - The real overlap report was regenerated with the marker. The epvme×nazario cluster that spans 3 groups is now same-label: 1,325 clusters, all same-label.
- **Verification after patches:**
  - `tests.test_dataset_ablation`: 13 tests OK.
  - Full root suite: 62 tests, OK, 1 skipped.
  - `--list` is unchanged: 17 experiments.
- **Renegotiation 2026-11-09, user approved (a), (b) and (c):**
  - **Pre-run checks:** the 6,011-row cluster is an EPVME XSS template; the payload sits in From/Subject; the HTML features are 0% on the cluster; `hdr_markup_in_headers` fires on 99.9% of it and on 0% of legitimate train rows. The original random control removed 55/20/16/9% (epvme/pot/nazario/malspam) against an expected 61/17/14/8%.
  - **Implementation:**
    - `DEFINITION_VERSION` set to 2.
    - `without_*` definitions take `groups`, and `without_enron_trec` is added (18 experiments).
    - `stratified_cluster_mask` uses largest-remainder strata targets. It draws only pure, single-group clusters of at most 5% of the target, and records the details in `random_control`.
    - `score_breakdowns` writes `summary_nazario_by_cluster.csv` and `summary_epvme_by_attack.csv`; `summarize` now takes the test metadata.
    - README limitations updated (XSS facts, heuristic families, 497 mixed rows, single draw); AGENTS updated.
  - **Real export:**
    - Train removes 6,097/6,096 rows (nazario 867/866, pot 1,044, epvme 3,698, malspam 488) in 4,858 clusters, vs 4,343 for `without_nazario`. The 6,011-row cluster is excluded.
    - Validation removes 2,035/2,031 rows.
  - **Verification:**
    - `tests.test_dataset_ablation`: 14 tests OK.
    - Root suite: 63 tests, OK, 1 skipped.
    - No second review pass was run on this renegotiation.

## Spec Change Log

## Review Triage Log

Pass 1 (Blind Hunter = B, Edge Case Hunter = E, Verification Gap = V). Routes: patch unless stated.

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| E1 | Lock race: another process completes between the state check and `O_EXCL` | medium | Real TOCTOU in `run_experiment`. Patch: re-check the state ignoring the lock once it is held. |
| E2/B5 | `--unlock` does not check that the owning process is dead; the old `finally` can delete a new owner's lock | low | Only after a deliberate manual unlock of a live run; README now warns. A PID check on Windows (`os.kill(pid, 0)` sends CTRL_C) adds complexity. Rejected. |
| E3 | A single-class train/validation subset fails only after Doc2Vec | low | The real export has both classes in every experiment (`--list`), and the failure is loud. Rejected (adds a guard for an undemonstrated state). |
| E4/B4 | One failing experiment stops the 68 h queue | medium | Real: exceptions propagate out of the loop in `main`. Patch: record `failed`, continue, exit 1. |
| E5 | `summarize` can mix experiments from different exports or definitions | medium | Real: pending experiments run with whatever export is given. Patch: `summarize` refuses mixed key sets; the output marker binds the folder to one export. |
| E6 | A complete status with missing or edited CSV/npz | low | Missing files fail loudly in `summarize`; edits require tampering. Rejected. |
| E7 | Overlap label mix is computed on the whole cluster for 3+ group clusters | low | Real: 2 such clusters; one made epvme×nazario show 1 mixed. Patch: per-pair label mix. |
| E8 | `--doc2vec-epochs 0` silently becomes 40 | low | Direct correction. Patch: `is None` check plus `positive_int`. |
| E9 | Mode flags are silently ignored by precedence | low | Small direct fix. Patch: mutually exclusive group; `--experiments` rejected with modes. |
| E10 | `--list` fails if random removal is infeasible | low | Feasible on the real export (6,097/2,032). Rejected. |
| E11 | The heatmap scale breaks when all deltas are 0 | low | Real: `vmin` = 0. Patch: `limit = ... or 1.0`. |
| E12 | Lock/resume atomicity claim | medium | Same root cause as E1/E2. Handled there. |
| E13 | The root `.gitattributes` is untracked; the docs rely on it | medium | Pre-existing uncommitted work from the LF task (user chose not to commit). Defer. |
| V1 | Seed variation is never verified | medium | Pre-verified. Patch: test asserts different `test_scores_sha256` for reference vs seed43. |
| V2 | The `main` training path and the PYTHONHASHSEED re-exec are untested | medium | Pre-verified. Patch: subprocess test (`--experiments reference --doc2vec-epochs 2`, hash seed 0, 9 models, summary). |
| V3 | Resume of an interrupted or failed experiment is untested | medium | Pre-verified. Patch: tests for a `running` record rerun and for failure releasing the lock and recording `failed`. |
| V4 | `--list` is untested | low | Filed defer. Cheap, so patched: `test_list_reports_counts_and_status`. |
| B1 | The resume key lacks epochs and hash seed | medium | Real: a `--doc2vec-epochs 2` trial in the real output would count as complete. Patch: both are in `definition_record`. |
| B2 | No library versions or code hashes | low | Direct addition. Patch: `environment` in `experiment.json` (recorded, not compared). |
| B3 | Can write into existing runs, against the AGENTS policy | medium | Real (`--output runs/<existing> --overlap` worked). Patch: `claim_output` with the `ablation.json` marker. |
| B6 | README class ratios are labelled validation but are train | low | Verified: train 4.69→1.35, validation 5.13→1.46; malspam 1:59 train, 1:56 validation. Patch README. Spec Design Notes are not edited (spec edits are rejected). |
| B7 | The selected-view delta compares the same family, not the reference's selected model | medium | Real: `_with_deltas` keys on Model. Patch: `delta_vs_reference_selected_Rate`, used by `heatmap_selected_*`. |
| B8 | Deltas ignore the seed noise | low | Enhancement; `seed_spread.csv` exists as specified. Rejected. |
| B9 | No confidence intervals for small test groups | low | Enhancement beyond the spec; counts are reported. Rejected. |
| B10 | Random control: one draw; a 6,011-row EPVME cluster could dominate | low | Verified the cluster exists. The seed-42 draw avoids it (4,369 clusters). The definition is frozen. README documents it; rejected as code change. |
| B11 | No random controls for other groups | low | The intent specifies one control. Rejected. |
| B12 | README omits the large enron×trec overlap | medium | Verified: 5,795 clusters. Patch README. |
| B13 | Exact-duplicate attribution counts are not reported | low | The dispositions file lacks the kept copy's key, so attribution cannot be computed. Rejected. |
| B14 | The `without_epvme` headline threshold is calibrated with EPVME | low | True caveat. Patch README (prefer AUC/AP). |
| B15 | "61%" holds only for train | low | Verified: 60.7% train, 57.2% validation, 52.9% test. Patch README. |
| B16 | The test alignment check is weak; the RecordId hash comes from unfiltered metadata | low | Direct correction. Patch: compare and hash `subset['test'].RecordId` in `run_experiment`. |
| B17 | Parallel processes overwrite summary files | low | Real but benign: last writer wins. Patch README: rerun `--summarize` at the end. |
| B18 | `TREC_07.csv` is missing from the group table | low | Real for exports without raw trec07p. Patch: map to `trec`. |
| B19 | Missing test branches | medium | Same as V2–V4, plus `without_<legit>`. Patch: `without_ling` added to setUp; FPR `held_out` asserted. |

## Design Notes

**Threshold effect.** Deltas mix a content effect with a threshold effect. For example, removing `enron` moves the validation class ratio from 4.7:1 to about 1.35:1. Threshold-free per-group AUC/AP and raw counts separate the two effects. `threshold_constraint_met` flags runs whose threshold is a fallback. `only_malspam` is about 1:58, so a fallback is likely there.

**Fixed-family view.** It isolates the dataset effect from a change of selected family.

**Random control.** `random_like_nazario` separates "fewer positives" from "these positives". Drawing whole clusters mirrors how a group removal drops near-duplicates together.

**`only_*` and the cross-source matrix.** They show what each dataset achieves alone. Leave-one-out understates the value of datasets that resemble each other. The overall row without EPVME is the figure for real phishing.

## Verification

**Commands:**
- `.venv/Scripts/python.exe -m unittest tests.test_dataset_ablation -v` -- expected: all pass
- `.venv/Scripts/python.exe -m unittest discover -s tests` -- expected: OK (skipped=1)
- `.venv/Scripts/python.exe dataset_ablation.py --features runs/2026-11-08_features_v6 --output runs/2026-11-09_dataset_ablation --list` -- expected: 18 experiments in order, with train/validation counts
- `... --overlap` -- expected: `overlap_by_group.csv` written; inspect it before the long runs
