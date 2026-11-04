---
title: 'Sửa và tạo lại artifact huấn luyện'
type: 'bugfix'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'NO_VCS'
context: []
---

<frozen-after-approval reason="Ý định của người dùng; chỉ sửa khi người dùng đồng ý thay đổi">

## Intent

**Vấn đề:** Artifact hiện có không đồng bộ. Bộ nạp dữ liệu coi cả CSV là một email phishing và không tách mbox Nazario không có phần mở rộng; việc huấn luyện lại có thể cho kết quả sai hoặc ghi đè dở dang.

**Hướng xử lý:** Tách email trong mbox, nạp từng dòng CSV có nội dung và nhãn 0/1, bỏ CSV vector; xử lý thiếu dữ liệu và trùng lặp trước khi chia tập. Ghi mỗi lần huấn luyện vào bộ artifact riêng, kiểm tra rồi mới công bố. Đánh giá bộ mới sau khi huấn luyện từ corpus hiện có.

## Boundaries & Constraints

**Luôn giữ:** Nhãn 0=hợp lệ, 1=lớp dương; khử trùng lặp trước khi chia tập; trích đặc trưng trước khi làm sạch; fit scaler trên train; thứ tự `[Doc2Vec | engineered đã chuẩn hóa]` theo `FEATURE_NAMES`. Manifest ghi số mẫu theo nguồn, schema, kích thước test, SHA-256 và mã lần chạy. Giữ lệnh `python train.py` và `python evaluate.py`.

**Không làm:** Không coi cả CSV hoặc mbox là một email; không đổi nhãn từng dòng CSV; không dùng CSV vector như email thô. Không xóa artifact cũ hoặc công bố kết quả mới trước khi lần chạy hoàn tất.

## I/O & Edge-Case Matrix

| Tình huống | Đầu vào / trạng thái | Kết quả mong đợi | Xử lý lỗi |
|------------|----------------------|------------------|-----------|
| Mbox | `.mbox` và `phishing-*` không có đuôi | Tách từng email | Ghi số lượng, báo tệp lỗi |
| CSV | Có `subject`/`body`/`label`; hoặc chỉ có vector | Giữ nhãn theo dòng email; bỏ CSV vector | Đếm dòng thiếu nội dung/nhãn sai |
| Huấn luyện | Hoàn tất 10 classifier hoặc bị ngắt | Chỉ đổi con trỏ sau khi bộ mới hoàn tất | Giữ lần chạy cũ khi lỗi |
| Artifact sai | Thiếu tệp, hash/schema sai | Dừng trước khi ghi chỉ số | Nêu tệp lỗi |

</frozen-after-approval>
## Code Map

- `load_data.py`: `_read_csv_emails`, `_read_phishing_rows`, `_read_raw_emails`, `load_data_enron`; existing parsing and Windows trailing-dot handling satisfy the loading goal. Preserve row labels and source/error counters.
- `preprocess.py`: `compute_dedup_key` normalizes body whitespace and case; preserve `FEATURE_NAMES` and raw-email feature extraction.
- `train.py`: `training` deduplicates before splitting, extracts before cleaning, fits scaler on train only; `save_training_run` writes all ten classifiers into an isolated run before publication. Full corpus is the current policy (`BALANCED_MODE=0`).
- `artifact_store.py`: `write_manifest`, `verify_run`, `selected_run`, `publish`; reuse hash/schema validation and atomic pointer replacement. Preserve old runs.
- `evaluate.py`: `load_artifacts`, `evaluate`; validates selected artifacts, computes probability ROC-AUC, writes reports only through the CLI. Do not import for inspection.
- `analyze_feature_importance.py`: verifies selected run and derives embedding dimensions from its manifest.
- `tests/test_evaluate.py`: seven passing tests cover CSV/mbox parsing, probability AUC, artifact corruption/schema failures and interrupted publication.
- `README.md`, corpus/model READMEs: already describe current artifact paths and positive-class semantics.

## Tasks & Acceptance

**Execution:**
- [x] `load_data.py` -- parse individual CSV/mbox emails, preserve labels, skip vector CSVs and Markdown, record source errors.
- [x] `train.py`, `artifact_store.py` -- publish verified isolated runs atomically and preserve previous selection on failure.
- [x] `evaluate.py`, `analyze_feature_importance.py` -- select and verify a single coherent run before model loading.
- [x] `README.md`, corpus/model READMEs -- document commands, artifact paths and spam in the positive class.
- [x] `tests/test_evaluate.py` -- add meaningful coverage for normalized cross-source duplicates before splitting; verify existing seven tests remain green.
- [x] `evaluation_results.csv`, `metric-verification/log-provenance.json` -- verify all ten model rows against the successful evaluation log supplied by the user; record run identity, hashes and printed-precision limits. Full recomputation was superseded by this evidence.
- [x] This spec -- reconcile completion markers with verified evidence; retain historical failures and record final validation.

**Acceptance Criteria:**
- Given labelled CSVs, extensionless Nazario mboxes, vector CSVs and Markdown, when loading, then each email retains its label and non-email inputs contribute no samples.
- Given matching normalized bodies from different sources, when the training preparation deduplicates before splitting, then a duplicate key cannot occur in both train and test.
- Given an interrupted training or invalid artifact publication, when selecting a run, then the previous complete run remains selected or absence is reported.
- Given missing files, wrong hashes or incompatible schema, when evaluating, then validation fails before reports are written.
- Given the verified full-corpus run and user-provided successful train/evaluate log, when checking report provenance, then run identity and all ten CSV rows match the log at printed precision; the evaluator uses positive-class probabilities and compatible 128,186 by 140 test input.

## Implementation Notes

Historical implementation reported CSV/mbox fixes, isolated runs, manifest verification and seven passing tests. An earlier full-corpus attempt stopped after 80,000 Enron files because of memory pressure; that attempt published no run. Those notes describe an earlier attempt, not the currently selected completed run.

Planning investigation on 2026-09-26 verified the selected run's fourteen artifact hashes, array sizes, feature order and all ten classifiers' input widths/classes. The scaler expects 40 engineered features and Doc2Vec has 100 dimensions. The manifest records 751,422 loaded samples, 324,136 removed duplicates and 427,286 retained samples, including 517,401 Enron messages before deduplication. Seven vector CSVs contributed zero samples. The obsolete sampling question is removed because a completed full-corpus run now exists; no sampling change is proposed.

Historical planning validation: `.venv/Scripts/python.exe -m unittest discover -s tests -v` passed all seven tests. No training or root report regeneration was performed. Existing CSV metrics have not yet been independently matched to the selected run.

## Spec Change Log

## Review Triage Log
- low, rejected: Older verification sentences conflict with later completion evidence unless read chronologically. This finding requests spec edits and is rejected under the review routing rule; historical stage labels and final results clarify completion during normal reconciliation.
- low, patched: Aggregate log hashes and tolerance did not expose the fifty-value comparison. `log-provenance.json` now stores each terminal/CSV value and absolute difference, making the printed-precision claim auditable.
- low, patched: Partial recomputed CSV lacked recorded run/hash linkage. Provenance now records run ID, manifest/partial-CSV hashes, completed models, exact comparison and incomplete-run limitations.
- low, patched: Duplicate regression checked identities but omitted sample-accounting assertions. It now checks 11 loaded, 1 removed and 10 retained at the intercepted split; focused and full suite validation passed.
- Verification-gap reviewer: no gaps found. Edge-case reviewer: no findings. No findings deferred by this review.

## Verification

- `.venv/Scripts/python.exe -m unittest discover -s tests -v` -- parsing, publication, evaluation and new duplicate coverage pass.
- Read-only `selected_run()` and classifier/scaler/Doc2Vec schema inspection -- hashes, counts and dimensions agree (completed during planning).
- Compare successful train/evaluate terminal log to selected run and all ten CSV rows -- tolerance 0.0000005000001 for six-decimal terminal output; record hashes and preserve root reports.
- Inspect training order and manifest counts -- deduplication precedes splitting; raw features precede cleaning; scaler fits only training samples. Report spam-inclusive positive-class metrics without claiming pure-phishing generalization.
### Implementation verification (2026-09-26)

- Added a regression invoking actual training preparation through its actual train/test split. Different source headers and body case/whitespace normalize to one key, the first label is retained, and raw-body keys carried through preprocessing cannot appear in both partitions. Expensive downstream training is stopped at the split. Test cleanup restores source/training/extraction counters.
- Final full suite: `.venv/Scripts/python.exe -m unittest discover -s tests -v` passed all eight tests in 24.313 seconds.
- Historical implementation stage: metric comparison was running in isolated `_bmad-output/implementation-artifacts/metric-verification/`; root reports and selected artifacts remain untouched.

### User-supplied evaluation evidence (2026-09-26)

User selected BD after providing C:/Users/PC/Downloads/result.txt and accepting that redundant full recomputation is unnecessary. The log records completion of the selected run followed by successful evaluate.py and saved reports. All fifty printed metrics (ten models, five metrics each) agree with the current CSV within half a unit at six decimal places. Hashes and limits are recorded in metric-verification/log-provenance.json. This supersedes the earlier pending recomputation note; partial recomputation is not claimed as full verification. Root models, pointer, CSV and plots were not regenerated. Review is pending.

### Final completion (2026-09-26)

All eight tests passed in 18.572 seconds after review fixes. The matrix is covered by corpus CSV/mbox tests, invalid-artifact tests, interrupted-training and publication tests, and the successful user-supplied full-run evaluation log. Three independent review layers completed; minor test-accounting and evidence-recording improvements were applied, with no deferred review findings. The metric-verifier process was stopped; its three completed rows are explicitly partial. Full train/evaluate was not rerun. No local commit was created because the project has no Git metadata.
