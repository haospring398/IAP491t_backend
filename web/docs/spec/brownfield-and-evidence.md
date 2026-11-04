# Brownfield State and Evidence Boundaries

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

The user-approved [local demo contract](local-demo.md) overrides conflicting target labels, E0-before-real-inference and native-versus-qualified packaging clauses only for the disclosed local legacy demo. Detailed qualified-release requirements below remain the future phishing-only acceptance contract. Local success uses legit or spam_or_phishing; phishing is reserved for the qualified target. Actual mixed-model checks do not pass E0 or cloud/Docker acceptance.

Distinguish inherited snapshots, observed local context and evidence required by E0.

## Source snapshot

The 2026-10-06 user decision removes in-app `.eml` export instructions, superseding the plan's older Upload helper requirement. Current UX, PRD, spec and AD-8 follow that removal; the original plan remains a historical source.

The plan attributes its ZIP/report observations to `IAP491t_backups.zip` and `Report_FA26IA05-C1(1).pdf` (Appendix A, pages 28-32); those were not independently inspected in this update. Its original Graph filename is `Graph_IAP419t.drawio (1)(1).png`; the later user-supplied filename variant is now imported and directly inspected below.

| Source-reported observation | Design implication |
| --- | --- |
| Loader INCLUDE_SPAM=True and numeric CSV labels include ordinary spam/phishing | Audit source/release target; flags/display names cannot establish eligibility. |
| ZIP lacks frontend/API/inference service | Build the product adapter and upload/API experience around the offline pipeline. |
| Twelve .pkl and two .npy ZIP files are LFS pointers | Obtain controlled objects or recreate a separately evaluated release. |
| Doc2Vec pointer about 146 MB; XGBoost about 0.44 MB | One classifier still needs embedding/scaler; measure actual RAM. |
| Legacy README says 42 engineered/142 total dimensions | Use ordered FEATURE_NAMES and verified artifacts; recorded expectation is 40/100/140. |
| Dependencies unpinned | Recover compatible versions and lock inference dependencies. |
| Snapshot evaluation CSV uses hard predictions for AUC | Follow AGENTS.md's positive-class probability ROC-AUC and code/artifact/log provenance. |
| Unicode retained; keywords/stopwords mainly English | Unicode support does not establish Vietnamese accuracy. |
| Doc2Vec mode/size, two class tags and alpha decay concerns | Investigate retraining as a new experiment; preserve inherited metric attribution. |

The old XGBoost table reports accuracy 93.38%, precision 88.62%, recall 81.98% and F1 85.17%, highest old-table F1. These are historical mixed-positive reference values, not metrics verified in this update or phishing-only evidence. XGBoost is a packaging candidate; target-specific validation selects the accepted classifier.

## Directly inspected Graph

The adopted UX includes [the unchanged Graph import](../ux/imports/graph-iap419t.png), directly viewed during the earlier UX/spec work. Its SHA256 is `a5649657fe85867616ce388389f958deeb439bad8066ae11b46d6d18e82c911e`, matching the UX import record for user-supplied `Graph_IAP419t.drawio (1).png`. The earlier missing-image observation remains historical.

| Visible reference | Current contract |
| --- | --- |
| .eml input, MIME parse, raw parsed-email 40 structural-feature branch and cleaned Doc2Vec branch, concatenation | Preserve raw-feature extraction before cleaning. Fitted scaler and Doc2Vec-then-scaled-feature order come from plan/AGENTS, not explicit image annotations. |
| Selected trained classifier and Predict/class/probability | Serve one verified classifier; internal probability may support a recorded decision rule, without mandatory score display. |
| Legitimate/Spam/Phishing, probability, indicators and inspector | Display one label plus AD-14 factors; defer probability, inspector and other extended fields, and keep errors outside the class enum. |
| Enron/legitimate, Nazario/phishing, SpamAssassin/spam; train/validation/test and compare/select | Architecture reference; actual source provenance, target/release and independent evaluation still need evidence. |
| XGBoost/RF/SVM/MLP candidate names | No candidate selection or benchmark is certified. |
| Frontend/backend/model + results storage | Store verified model artifacts; keep results transient in browser-session memory without a database/server history. |
| Colored architecture panels | No approval of UX palette, tokens or composition. |

The imported image and source originals are unchanged. A revised drawio file, eligible model, working deployment or privacy enforcement is not established by image inspection. Detailed upstream interpretation remains linked from the adopted DESIGN/EXPERIENCE.

## Current local context

The prior spec read selected run `e7dcdcc3551e46fc93582836f4a74976` and manifest metadata of 40 ordered features, 100 embedding dimensions, 140 total and artifact hashes. This is a dated metadata observation distinct from ZIP pointer bytes; no artifact loading/hash recomputation, inference or eligibility verification was performed in this update.

On 2026-10-06, PRD/addendum, draft DESIGN/EXPERIENCE and final architecture exist and are incorporated into this contract. Their existence does not complete shared contract qualification, stories, application implementation or E0. Earlier no-PRD/no-UX findings describe the initial spec-creation snapshot. Earlier ML repairs retain their recorded spam-inclusive target.

The earlier read found Git metadata, with observed HEAD `34648b04405c69d0be09cf5b86c16f104ea02966`; earlier no-Git observations in repository/planning context are historical. HEAD presence does not establish that working sources or model artifacts match that revision. The unchanged web plan SHA256 is `41de6bc1a27d03354e480f27539446d23f50aa171dae8c39a9b0e76d2a2ed62d`.

AGENTS.md governs pipeline paths, atomic publication, tests, label disclosures, feature order, Windows trailing-dot corpus handling, source-bias pitfalls and metric evidence. Preserve previous runs/current pointer on failed publication; inspect matching selected-run/log evidence before expensive evaluation. File presence, old completion records and inherited metrics do not prove the current target.

## Architecture and actual code gaps

The unchanged [ARCHITECTURE-SPINE.md](../architecture/ARCHITECTURE-SPINE.md) and factual [brownfield audit](../architecture/.working/brownfield-audit.md) are adopted companions. AD-1 through AD-13 govern implementation; assumption-tagged policies/seeds still require qualification. Source research/review/production logs are not adopted as separate contract files.

The audit's 2026-10-05 static observations expose gaps between AGENTS conventions and actual scripts. **Pipeline update 2026-10-20:** the root pipeline now follows the 19-10 version of `buidangduy05/IAP491t_backups` (commit `ae08251`). `evaluate.py` has a main guard and computes CSV/plot ROC-AUC from positive-class scores; `train.py --output runs/<name>` writes a schema-version-2 `run_manifest.json` with `target_mode`, validation-selected classifier and per-model thresholds, without `artifact_store.py` publication. Remaining gaps: the upstream version is incomplete (`preprocess.py` lacks `BertEmailClassifier`, `split_train_validation_test`, `prepare_semantic_text` and the attachment inspection behind 13 features; `specialists.py` is missing), so `train.py`, `predict_specialists.py` and `tests/test_pipeline.py` cannot import; importance width remains hardcoded at 100; the web demo verifier reads `manifest.json` and cannot load schema-2 runs. These are implementation gaps to reconcile before release qualification, not conflicting permission to weaken conventions.

The adopted audit retains the preprocessing/raw-byte/parser/resource/global-counter/RNG seams, selected-run metadata and loaded-object verifier gaps, dated artifact file sizes, broad-positive provenance, test drift, Windows package metadata and absolute sibling-venv dependency. Metadata/file sizes do not establish hashes, loaded objects, runtime RAM, a portable environment or target eligibility. Consumer checks must use the qualified release and actual current code rather than presume earlier ML fixes are integrated.

Architecture framework/provider entries remain source-dated unbuilt proposals; no versions or hosting guarantees were reverified here. The exact stack/policy tables and diagrams remain in the adopted spine, with locked-build/Linux/model/account/resource gates intact.

## Installed planning route

The prior installed catalogue records BMad 6.12.0. Use local capabilities without requiring an installation upgrade:

| Purpose | Capability |
| --- | --- |
| Refresh repository context | bmad-project-context when requested |
| Requirements / UX / technical decisions | bmad-prd / bmad-ux / bmad-architecture |
| Maintain this contract | bmad-spec |
| Epics/stories / readiness/tracking | bmad-create-epics-and-stories / bmad-sprint-planning |
| Implement / requested code review | bmad-build / bmad-code-review |

The plan's bmad-ticket/generic status examples are not installed routing commands. Its deprecated document-project purpose maps to the local context capability. An implementation cycle needs a concrete story, code/context inspection, implementation, meaningful checks, review, status update and team-repository commit.

## Glossary and research limits

- **Email file:** one exported .eml including encoded attachments.
- **Analysis:** one attempt to validate that file and obtain a classification.
- **Legit / phishing:** reviewed class 0 legitimate / class 1 confirmed phishing; ordinary spam is not automatically included in either target.
- **Processing error:** unsuccessful analysis, never a third class.
- **Eligible release / E0:** coherent verified target/provenance/environment/evaluation release and the gate establishing it with initial resources.
- **Fixture:** privacy-scrubbed verification email or visibly marked sample response while real integration is pending.

A working web demo or eligible E0 release does not complete RQ2/RQ3; ablation and independent-source tests need separate experiments. Do not invent predictions, benchmarks, explanations, phishing-prevention counts or phishing-only attribution for mixed-positive results.

The plan cites Al-Subaiey et al. (2024), DOI `10.1016/j.compeleceng.2024.109625`, for a web/LIME example; this does not establish LIME or measured explanation quality in IAP. AD-14's exact factor explanation is the only XAI in the MVP; LIME is not used. The PRD addendum's investigation/retention examples motivate scope restraint and verified transient handling only; they add no market-size, novelty or commercial-demand claim.

Inherited official links support later verification, not external research performed by this update:
- BMad: [installation](https://docs.bmad-method.org/start/install-bmad/), [existing codebases](https://docs.bmad-method.org/existing-codebases/start-in-an-existing-codebase/), [requirements/spec](https://docs.bmad-method.org/plan/define-requirements-and-a-specification/), [UX/architecture](https://docs.bmad-method.org/plan/design-ux-and-architecture/), [stories/tracking](https://docs.bmad-method.org/plan/break-work-into-stories-and-track-it/).

This update derives and self-validates documentation; it supplies no new model, training, evaluation, application-test or deployment evidence.
