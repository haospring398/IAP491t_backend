# Model Eligibility and Inference

The user-approved [local demo contract](local-demo.md) overrides conflicting target labels, E0-before-real-inference and native-versus-qualified packaging clauses only for the disclosed local legacy demo. Detailed qualified-release requirements below remain the future phishing-only acceptance contract. Local success uses legit or spam_or_phishing; phishing is reserved for the qualified target. Actual mixed-model checks do not pass E0 or cloud/Docker acceptance.

Applies to CAP-2, CAP-4 and CAP-5. E0 is a release acceptance gate; current artifact metadata does not certify a phishing-only service. Follow AD-14 for per-result explanations.

Follow AD-1/2/3/4/11 in the adopted [architecture](../../planning-artifacts/architecture/architecture-PhishingEmailDetection-2026-10-05/ARCHITECTURE-SPINE.md); the [brownfield audit](../../planning-artifacts/architecture/architecture-PhishingEmailDetection-2026-10-05/.working/brownfield-audit.md) records the legacy seams and verification gaps to reconcile before release qualification.

## Eligible training target

| Class | Required evidence | Web label |
| --- | --- | --- |
| 0 | Reviewed legitimate email with source provenance | `legit` |
| 1 | Phishing confirmed by source provenance or review | `phishing` |

Verify the actual dataset snapshot and each source's label convention. Numeric 1, a phishing directory, `classes_ = [0, 1]` or `INCLUDE_SPAM = False` alone is insufficient. Exclude ordinary spam and unknown positives from the default benchmark. SpamAssassin ham may qualify for class 0; a spam record needs separate phishing evidence to qualify for class 1. Legit does not automatically include all non-phishing ordinary spam.

Mixed spam/phishing artifacts need a reviewed target-specific training/evaluation release with its own manifest/results. Preserve legacy semantics and evidence. Pending E0, fixture output must be visibly marked **"Sample result — not a real analysis"** and retain Legit/Phishing; samples cannot satisfy real inference acceptance.

## Feature contract

1. Parse original MIME bytes, retaining subject/body/header/URL/HTML/attachment information needed by engineered extraction.
2. Extract engineered features before `cleanText`; derive order from `preprocess.FEATURE_NAMES`.
3. Normalize subject/body for the already fitted Doc2Vec and use `infer_vector`.
4. Apply the same release's training-fitted scaler with `transform`.
5. Concatenate **Doc2Vec first, scaled engineered features second**, then use one selected classifier from that release.

| Engineered group in the source | Count |
| --- | ---: |
| Content/NLP statistics | 7 |
| URL | 11 |
| Sender/header | 6 |
| HTML/structure | 6 |
| Attachment properties | 5 |
| Social engineering | 5 |
| Total | 40 |

Expected embedding/total widths for the current code and the pinned local demo run are 100/140. The 2026-10-19 phishing-target candidate run records 53 engineered features (the 40 above plus 13 attachment-inspection counts produced by upstream code absent from this repository), so a release built from it needs width 153 and matching preprocessing code. Verify actual `vector_size`, `scaler.n_features_in_`, classifier input width and ordered features against the manifest/code; numeric comments and legacy README cannot establish compatibility. Dimension changes also require compatible feature-importance analysis under AGENTS.md.

Requests never call dataset loading, import/run training or evaluation, or fit models/scalers. Load one release once in the resident ML child, not also in the supervisor; ten research classifiers remain offline. Configure corpora/stopwords/lemmatization explicitly; do not download NLTK resources in requests.

## Artifact and manifest contract

An XGBoost candidate uses `model_dbow.pkl`, `feature_scaler.pkl`, `XGBoost.pkl` and a manifest; another evaluated winner substitutes its classifier. The Doc2Vec filename does not establish its mode.

Offline export first verifies the full immutable training run, then packages one explicitly selected classifier plus its same-run Doc2Vec/scaler. Runtime loads only the qualified bundle; full-run hashing/test-array loading must not occur per request. ML owns `web/contracts/deployment-manifest.schema.json` version 1, and exporter/runtime validate that same schema. Offline team review establishes target eligibility; metadata alone cannot.

The manifest records:

- Release ID, controlled artifact filenames/hashes and source commit/revision.
- Python/compatible package versions, ordered FEATURE_NAMES, embedding size and hybrid width.
- Class mapping, target `legit_vs_phishing` and dataset/label provenance or review evidence.
- Preprocessing/corpora/stopword/lemmatization configuration and explicit inference parameters.
- Versioned decision/threshold rule and linkage to that release's evaluation evidence.
- Source-run ID/manifest hash, preprocessing code/resource hashes, complete self-contained environment lock, language/resource policy and explicit offline-reviewed E0 references.

Before metrics, verify hashes, matching test counts, dimensions and classes. Classifier, Doc2Vec, scaler and test arrays come from the same run; legacy loose files cannot substitute. Reject Git LFS pointer bytes, including the `version https://git-lfs.github.com/spec/v1` marker. Retrieve controlled objects in the team's repository with `git lfs pull` if needed, or recreate a separate evaluated release. Load only team-controlled pickle.

Unsuitable artifacts/configuration/corpora/target evidence fail startup/readiness clearly. Numeric classes and widths alone do not prove eligibility. Recover and lock compatible inference dependencies rather than blindly upgrading packages used by pickle. Preserve previous runs/current pointer on failed publication. Runtime additionally checks loaded Doc2Vec/scaler/classifier dimensions/classes, finite feature values and numeric predictions exactly 0 or 1; hashes do not replace pickle trust or target review.

## Evaluation and parity

- Deduplicate before splitting; extract raw engineered features before cleaning; fit the scaler only on training data.
- Select classifier and any threshold on separate validation; preserve independent grouped testing and record the experiment/release/decision rule. Model-quality acceptance criteria remain Q2.
- Internal probability decisions use the confirmed positive-class index. ROC-AUC uses positive-class scores; classification metrics use labels. Never publish inherited hard-prediction AUC as probability ROC-AUC.
- Harness/API engineered features match, embeddings meet recorded tolerance and labels agree. AD-4 specifies process hash seed before imports, release/content-derived RNG reset/restore under serialization, explicit positive finite alpha/min-alpha/fixed epochs and one numerical thread for the initial profile. Exact release values/tolerance remain Q2/Q4; qualification covers repeated, reordered and restarted inputs.
- If retraining changes explicit Doc2Vec mode/vector size, two class-label tags or manual alpha decay, treat it as a new experiment rather than attributing inherited metrics to the changed model.
- Link reports to the eligible target/release. Inspect matching successful logs before costly recomputation; `evaluate.py --run runs/<name>` overwrites the reports in the run folder it is given and runs only when regeneration is intended.

## Explanation (AD-14)

- Compute contributions in the ML child from the same final vector and loaded classifier that produced the label; never repeat preprocessing or load a second model for explanation.
- Use exact methods only. Tree ensembles use the booster's exact contribution output on the decision margin (XGBoost `pred_contribs`). Other classifiers omit `explanation` unless a separate exact method is approved; BERT is not served.
- Sum the first `doc2vec_dim` columns into `text_content`; engineered columns keep `FEATURE_NAMES` order. The bias term is not a factor.
- Select at most five nonzero factors by absolute contribution; `strength` is relative to the largest shown. `direction` is relative to the class-1 margin and independent of the decision threshold, so a Legit result can list factors pointing toward the positive class.
- Startup verifies additivity on the release's test arrays (within 1e-3) and catalogue coverage of every served feature; each request rechecks additivity. Factors follow AD-4 repeatability.
- Factors describe this release's model behavior. They are not evidence that an email is malicious, are not validated as human-meaningful and do not establish model quality.

## Legacy seams and environment

Preserve raw upload bytes through both engineered extraction and text cleaning; never decode the whole upload as UTF-8 first. Freeze stopword fallback, optional WordNet lemmatization, MIME traversal and regex-tokenization policy from the qualified release. Isolate module-global feature counters under serialized processing; do not reset training statistics from requests. The existing parser does not supply upload admission limits.

The selected-run verifier checks file/hash/schema/test arrays but does not validate loaded model/scaler dimensions/classes; add runtime bundle checks. The manifest lacks complete source/resources/environment/inference/target provenance. The audit's Windows package metadata and absolute sibling-venv .pth dependency are observations, not a portable training lock. Build a self-contained locked Linux environment with packaged resources and fail closed on required resource drift.

As of the 2026-10-20 pipeline update, evaluation is import-guarded and uses positive-class ROC-AUC; training writes a schema-2 run manifest under its `--output` folder rather than publishing through `artifact_store.py`. Remaining gaps are missing upstream modules/functions, test expectations for them, and hardcoded importance width. AGENTS conventions remain required outcomes; reconcile these gaps before generating/qualifying a release. Never import those offline scripts into the service, and do not treat their tests as a proven green baseline.

## E0 evidence required

Inventory real artifacts, needed training data, environment and label provenance. Privacy-scrubbed plain-text/HTML/multipart/charset/attachment/malformed fixtures must demonstrate bytes-to-prediction inference, matching dimensions/mapping, target-specific validation/test evidence and preliminary RAM/startup/latency. Relabel/retraining work needs separate estimation and the resulting release must pass the same checks. No model or resource result is established by this spec update. For FR-11, also record startup additivity, factor repeatability on the fixtures and the release's global SHAP summary and top error drivers (`analyze_shap.py --run runs/<name>`), which inform Q9.

The 19-10 pipeline provides a candidate E0 path: `TARGET_MODE = 'phishing'` keeps class 0 plus records whose `LabelKind` is `phishing`, and logs excluded rows to `label_scope_excluded.csv`; splits are group-disjoint; and classifier/threshold selection uses validation with a 0.90 precision target. Its 2026-10-19 run selected XGBoost on validation, but test arrays/scores are absent, two BERT tokenizer hashes differ from the manifest, and its 53-feature schema cannot be reproduced with current code. It is therefore candidate evidence, not a passed E0. Per-source provenance review (Q1) is still required.
