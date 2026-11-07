- source_spec: `_bmad-output/implementation-artifacts/spec-reliable-evaluation-artifacts.md`
  summary: Add a training-run manifest to prove that test arrays, scaler, Doc2Vec, and classifiers belong together.
  evidence: Equal sample counts and feature widths can still allow artifacts from separate runs to produce plausible but invalid metrics; train.py currently emits no shared run identifier.
- source_spec: `_bmad-output/implementation-artifacts/spec-reliable-evaluation-artifacts.md`
  summary: Publish evaluation CSV and plots as one consistent report set.
  evidence: evaluate.py writes the CSV before rendering plots, so plotting failure can leave new metrics beside old images; this behavior predates the current fix.
- source_spec: `_bmad-output/implementation-artifacts/spec-reliable-evaluation-artifacts.md`
  summary: Refresh the ROC-AUC warning in AGENTS.md after the evaluation change.
  evidence: The managed context block says the CSV uses predicted labels, but evaluate.py now uses positive-class probabilities for both CSV and plot; editing the managed block belongs in a project-context refresh.
  resolved: 2026-10-20 bmad-project-context refresh; the AGENTS.md block states positive-class probability ROC-AUC for both CSV and ROC plots.

- source_spec: '_bmad-output/implementation-artifacts/spec-move-backend-to-web.md'
  summary: Document the web/backend package and its test command in the root agent guidance.
  evidence: Existing AGENTS.md covers only the root pipeline; this workflow defers agent-guidance edits. Current service README already documents the relocated package and passing suite.
  resolved: 2026-10-20 bmad-project-context refresh; the AGENTS.md block documents web/backend's dependency on root modules and its test command.


- source_spec: `_bmad-output/implementation-artifacts/spec-web-standalone.md`
  summary: Let backend tests in a git clone of web/ (no bundle) get the exact NLTK stopwords/wordnet the fixture was trained with, e.g. by shipping them beside the fixture.
  evidence: The fixture records lemmatization and NLTK stopwords; without web/model/nltk_data or the root .venv data the preprocessing signature differs and adapter tests fail at MODEL_COMPATIBILITY.
- source_spec: `_bmad-output/implementation-artifacts/spec-web-standalone.md`
  summary: Tie bundled NLTK data to each run and verify it at bundle time (stopwords against the manifest, a hash of wordnet.zip).
  evidence: web/model/nltk_data is shared and replaced by every bundle; wordnet content is not part of the preprocessing signature, so a different wordnet.zip changes lemmatization without rejection.

- source_spec: `_bmad-output/implementation-artifacts/spec-web-serve-baseline-v6.md`
  summary: Apply the 15 baseline_v6 attachment rules (preprocess.ATTACHMENT_RULES) to the web label as "model OR rules", with a contract field and UI copy naming the fired rule.
  evidence: The user chose model-only for the v6 switch on 2026-11-04; rules need a contract and UI change beyond serving the run.

- source_spec: `_bmad-output/implementation-artifacts/spec-web-serve-baseline-v6.md`
  summary: Commit a small set of real baseline_v6 test-split emails (including one with an attachment and one with a malformed address header) and a test that re-extracts them through Adapter.vector against their data_X_test rows.
  evidence: The 250-email parity check (199/250 exact on Python 3.11.16, 250/250 labels) lives only in a scratchpad script; committing real corpus emails needs a decision on which sources may be redistributed.

- source_spec: `_bmad-output/implementation-artifacts/spec-web-serve-baseline-v6.md`
  summary: Measure source bias of the 82 features new in baseline_v6 (e.g. hdr_null_return_path, hdr_return_path_domain_mismatch, mime_signature_count, mime_max_blank_line_run) before trusting them or giving them "Known dataset bias" notes.
  evidence: Unverified (medium if true): Enron maildir lacks Return-Path and several header/MIME features may mark the corpus rather than phishing; settle with per-source feature rates and runs/2026-11-02_baseline_v6/evaluation_by_source.csv.

- source_spec: `_bmad-output/implementation-artifacts/spec-web-serve-baseline-v6.md`
  summary: State in AGENTS.md that root evaluate.py / analyze_feature_importance.py must not be run on runs/2026-11-02_baseline_v6 (root pipeline has 53 features, evaluate.py overwrites upstream's evidence) and that upstream runs are importable when the code that trained them is published and hash-matched.
  evidence: Running evaluate.py --run runs/2026-11-02_baseline_v6 would overwrite evaluation_results.csv and the plots that back FP 1359 / FN 42; AGENTS.md still frames upstream runs as non-importable.

- source_spec: `_bmad-output/implementation-artifacts/spec-web-serve-baseline-v6.md`
  summary: Decide whether oletools (and onnxruntime) versions must be enforced at startup, since preprocessing_signature() hashes only bs4, tldextract and magika.
  evidence: Unverified (medium if true): another olevba version may change attachment_vba_* / attachment_xlm_macro_count; settle by extracting the attachment samples under a different oletools version and comparing.

- source_spec: `_bmad-output/implementation-artifacts/spec-web-mlp-integrated-gradients.md`
  summary: Serve the baseline_v6 MLP with closed-form Integrated Gradients explanations (spec approved ready-for-dev on 2026-11-04, not implemented).
  evidence: Superseded the same day by serving the v6 XGBoost with exact pred_contribs (spec-web-serve-v6-xgboost.md); kept in case the demo returns to the MLP.

- source_spec: `_bmad-output/implementation-artifacts/spec-web-serve-v6-xgboost.md`
  summary: Add a step to AGENTS.md "To serve another run": check that policy.MODEL_NAME exists in the new run's manifest["models"] or set it to "selected".
  evidence: MODEL_NAME is hardcoded to "XGBoost"; a run without that model fails at MODEL_COMPATIBILITY; web/backend/README.md already says so but AGENTS.md does not.

- source_spec: `_bmad-output/implementation-artifacts/spec-web-serve-v6-xgboost.md`
  summary: Review the served v6 XGBoost's top factors (especially hdr_* and mime_* features) for dataset-source bias now that they are shown to users, and add "Known dataset bias" notes where measured.
  evidence: Unverified (medium if true): only num_attachments carries a note; settle with per-source feature rates or pred_contribs summaries per source on data_X_test.

- source_spec: `_bmad-output/implementation-artifacts/spec-merge-upstream-v6-code.md`
  summary: Pin line endings of root preprocess.py and pipeline_cache.py (root .gitattributes, LF like the a202d55 blobs or CRLF like upstream's training checkout)
  evidence: preprocessing_signature hashes file bytes and core.autocrlf=true, so the root signature changes between checkouts (cache invalidation, run signature drift); CRLF would make root signatures equal baseline_v6's 4c010fc3.

- source_spec: `_bmad-output/implementation-artifacts/spec-merge-upstream-v6-code.md`
  summary: Fix _simhash None/int column being cast to float64 in upstream group_email_variants/pipeline_cache (report upstream first)
  evidence: Verified: pandas stores [None, 2**64-3] as float64 and int() returns 2**64, so near-duplicate grouping uses rounded fingerprints; v6 was trained with the same behaviour, so a fix changes splits.

- source_spec: `_bmad-output/implementation-artifacts/spec-merge-upstream-v6-code.md`
  summary: Check CompressedEmail str->bytes change for CSV rows (CLI path vs training(data=...))
  evidence: Edge-case reviewer reports clean_text/features differ between the two paths; unverified here; would be medium if true.

- source_spec: `_bmad-output/implementation-artifacts/spec-merge-upstream-v6-code.md`
  summary: Add an audit_dataset test with malspam and trec07p
  evidence: --audit-only has its own source list that no test runs, so it can drift from load_training_emails.

- source_spec: `_bmad-output/implementation-artifacts/spec-merge-upstream-v6-code.md`
  summary: AGENTS.md: disclose malspam/EPVME in the positive class, exempt byte-identical upstream files from the Vietnamese-comment rule, and note the local baseline_v6 manifest (867316b, MLP) differs from upstream 3c88826 (XGBoost)
  evidence: Review of the v6 merge; agent-context edits are deferred by the review workflow.

- source_spec: `_bmad-output/implementation-artifacts/spec-merge-upstream-v6-code.md`
  summary: Upstream robustness gaps: malspam zip NotImplementedError/EOFError, scratch ledger/raw-email store left on crash, predict_specialists KeyError on old BERT manifests, lone surrogate in str email
  evidence: All in byte-identical upstream code; low impact locally (no malspam data, no old specialist manifests in use).
