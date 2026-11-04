# Local real-model service

Demo Windows cục bộ này phục vụ một run schema 2 (`dumped_models/classification/run_manifest.json`).
Run được pin bằng `RUN_PATH` trong `web/backend/policy.py` hoặc biến môi trường
`IAP_WEB_RUN_PATH`; đường dẫn tương đối của cả hai đều tính từ thư mục `web/`, không phải
thư mục gốc project. Hiện pin `model/2026-11-02_baseline_v6`: bản đóng gói của
`runs/2026-11-02_baseline_v6`, tức bản sao cục bộ (đã kiểm mọi SHA-256 của manifest) của
`runs/baseline_v6` upstream (buidangduy05/IAP491t_backups, commit 867316b, train bằng code
commit a202d55). Run này dùng 134 feature (`preprocess.BASELINE_FEATURE_NAMES`, có kiểm tra
file đính kèm bằng Magika/oletools/tldextract), không lemmatize, không NLTK; validation chọn
MLP, nhưng web phục vụ XGBoost được pin của cùng run (xem dưới). `web/scripts/bundle-run.py` chép run vào `web/model/`. `web/model/` không nằm
trong git (khoảng 1,2 GB cho run đang pin; các thư mục run cũ như `model/2026-10-23_web2`, nay
bị từ chối, và `model/nltk_data` không còn được dùng, nên xoá trước khi chép): chép hoặc nén
cả `web/` thì mang theo run; clone từ git thì phải
chạy lại script đóng gói (cần run gốc) hoặc đặt `IAP_WEB_RUN_PATH`, nếu không worker sẽ
không sẵn sàng.

`web/` chạy độc lập, không cần phần còn lại của project: backend chỉ dùng import tương
đối trong package, đọc contracts, run và samples theo thư mục `web/`, và không import
module nào ở thư mục gốc (kể cả trong test).

Web không dùng `preprocess.py`/`pipeline_cache.py` ở thư mục gốc mà dùng bản sao đóng
băng trong `web/backend/frozen_pipeline/`: đúng từng byte code upstream đã train run đang
pin (commit `a202d55`; `preprocess.py` giữ xuống dòng CRLF như bản đã băm lúc train, sha256
`51a4d22c…`, `pipeline_cache.py` giữ LF, sha256 `1f744d8c…`). `web/backend/__init__.py`
đặt thư mục này lên đầu `sys.path` trước mọi lần import. Nhờ vậy pipeline gốc giữ nguyên
(không gộp code upstream v6 vào `train.py`/`preprocess.py` gốc) mà web vẫn phục vụ run v6.
Không sửa hay format lại hai file này: chữ ký tiền xử lý băm từng byte, và `.gitattributes`
tắt việc đổi xuống dòng cho chúng.

Web phục vụ classifier được pin bằng `MODEL_NAME` trong `web/backend/policy.py` (hiện
`"XGBoost"`) hoặc biến môi trường `IAP_WEB_MODEL` (tiến trình con kế thừa), với ngưỡng
validation của chính model đó trong manifest (XGBoost của v6: 0,2113690823…), không phải
ngưỡng của `selected_model`. Giá trị `selected` (hoặc `MODEL_NAME = None` khi không đặt biến)
phục vụ `selected_model` của manifest (MLP của v6, chỉ trả nhãn). `IAP_WEB_MODEL` rỗng được
coi như không đặt, tức dùng `MODEL_NAME`, không phải `selected_model`. Tên pin phải có trong
`manifest["models"]` và qua cùng các kiểm tra bên dưới, nếu không worker không sẵn sàng ở
stage `MODEL_COMPATIBILITY`. Metadata của supervisor ghi cả `selected_model` (lựa chọn của
manifest) và `served_model`; worker khởi động lại phải phục vụ đúng `served_model` đã nhớ
(cùng run và digest manifest), nếu sửa `MODEL_NAME` hay `IAP_WEB_MODEL` giữa chừng thì báo
`RELEASE_CHANGED`. Dương tính khi xác suất lớp 1 ≥ ngưỡng. Run `target_mode: phishing` trả `phishing`
(Phishing), run `broad` trả `spam_or_phishing` (Spam / phishing). Đây là ngoại lệ
local đã công bố: chỉ có bằng chứng validation, chưa qua E0 hay đánh giá chất lượng
trên tập test.

## Start locally

### Đóng gói run (một lần, trong repository đầy đủ)

`bundle-run.py` chỉ dùng thư viện chuẩn, chạy bằng Python nào cũng được. Nó kiểm SHA-256
của mọi artifact trong manifest ngay lúc chép, rồi chép `run_manifest.json` và các artifact
đó vào `web/model/<run-id>/`. Mọi thứ được ghi vào một thư mục tạm rồi mới đổi tên vào chỗ:
hash sai hoặc thiếu file thì lệnh thoát với mã khác 0 và `web/model/` không đổi. Run v6
không dùng NLTK nên script không còn chép dữ liệu NLTK; thư mục `web/model/nltk_data/` cũ
(nếu có) không còn được dùng và có thể xoá. `--run` tương đối tính từ thư mục hiện hành
(khác `RUN_PATH`/`IAP_WEB_RUN_PATH`, vốn tính từ `web/`).

```powershell
python web/scripts/bundle-run.py --run runs/2026-11-02_baseline_v6
```

`runs/2026-11-02_baseline_v6/` (git bỏ qua `runs/`) được tạo từ Git LFS của upstream: tải
`run_manifest.json`, mọi artifact trong manifest và các CSV báo cáo nhỏ của
`runs/baseline_v6` tại commit 867316b, rồi kiểm SHA-256 từng artifact với manifest. Các CSV
lớn (`split_manifest.csv`, `train_metadata.csv`, `training_dispositions.csv`,
`label_scope_excluded.csv`, `error_analysis.csv`) không được tải.

### Chạy độc lập từ `web/`

Dùng Python 3.11.16 (hoặc bản 3.11 mới hơn, có `email.utils.getaddresses(strict=...)`) và
một virtualenv riêng `web/.venv` (git bỏ qua). Python 3.11.2 của `.venv` gốc phân tích địa
chỉ sai cú pháp khác lúc upstream trích feature v6 (xem "Giới hạn đã đo" bên dưới).
`uv python install` cài Python vào thư mục riêng của uv, không đụng Python hệ thống.
`requirements.txt` gồm `requirements-api.txt` và các gói ML khoá đúng phiên bản.
Generate a token in a Python-service PowerShell window, then start the service:

```powershell
cd web
uv python install 3.11.16
uv venv .venv --python 3.11.16 --seed
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
$env:ML_API_TOKEN = (.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
$env:ML_API_TOKEN  # Display only in your local terminal to copy into the second window.
.venv/Scripts/python.exe -m backend
```

### Chạy từ thư mục gốc

`.venv` gốc (Python 3.11.2, `getaddresses` không có `strict`) không còn chạy được backend hay
test backend: worker từ chối khởi động ở stage `DEPENDENCY_LOAD`. Từ thư mục gốc vẫn chạy
được bằng Python của `web/.venv`. Backend vẫn phục vụ run đã đóng gói trong `web/model/`;
muốn dùng thẳng run trong `runs/` thì đặt
`$env:IAP_WEB_RUN_PATH = '../runs/2026-11-02_baseline_v6'` (tương đối từ `web/`). Hai cách
cho cùng `manifest_sha256` vì script đóng gói chép nguyên byte manifest.

```powershell
$env:ML_API_TOKEN = (web/.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
web/.venv/Scripts/python.exe -m web.backend
```

In a second PowerShell window, use the same generated token as the first window.
Copy it locally through the terminal; do not commit it or put it in a public variable:

```powershell
cd web/frontend
npm.cmd ci
$env:ML_API_URL = 'http://127.0.0.1:8000'
$env:ML_API_TOKEN = '<same generated token from the Python-service window>'
npm.cmd run dev
```

Wait for `/health/ready` to return HTTP 200 before the first Analyze. HTTP 503
while the verified worker is starting is expected; retry the readiness check. If
it stays unready, inspect the backend startup log and token, shared-policy and
trusted-model configuration before restarting. Liveness alone does not mean the
worker is ready.

Open `http://127.0.0.1:3000`. Select a file from `web/backend/samples/` and click Analyze.
Selection alone sends nothing. The result includes your selected filename and the
truthful mixed-target label. Samples have no expected label or quality claim.
Alternatively set these server-only values in ignored `web/frontend/.env.local`.
Neither variable may use the `NEXT_PUBLIC_` prefix. Empty/mismatched configuration
returns a safe unavailable error. Both services bind loopback; no publication is
part of this demo. Stop both consoles with Ctrl+C. The backend supports `--port`
for another local port; update `ML_API_URL` to match.

Readiness can take several seconds because startup verifies **all** run hashes and
matching test arrays before loading the three inference artifacts. Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-WebRequest http://127.0.0.1:8000/health/ready
```

Live returns `{"status":"alive"}`; ready returns `{"status":"ready"}` only after
verification, otherwise HTTP503 with `{"status":"unready"}`. A missing token,
unconfigured or wrong run, tampered/incompatible artifact or invalid shared policy leaves
liveness available and classification disabled. Repair startup configuration and
restart the service. Runtime child death, deadline or disconnect reaps the old child
before reloading the startup-pinned run; readiness remains unavailable during recovery.
Đường dẫn run chỉ được đọc lúc khởi động; thay đổi sau đó không được áp dụng cho tới
khi khởi động lại. Giữ nguyên mọi run hiện có.

## Runtime behavior

The supervisor authenticates one admitted request before consuming its body; it
rejects busy requests without a queue. One spawned resident child performs bounded
multipart/MIME parsing, feature extraction and prediction. Uploads stay in memory;
there is no upload spool, persistent email history or sensitive access/content log.
Links, remote images and attachments are never fetched or executed. The browser
contacts its same-origin Next proxy, which alone holds the Bearer token and forwards
the canonical filename `message.eml` with UUID/deadline headers.

Both services consume `web/contracts/transport-policy.json`: 2 MiB file, bounded
multipart, 100 MIME nodes, root depth 0 through 20, 2 MiB eligible decoded subject/body
UTF-8 and 50,000 final normalized tokens. Actual overflow rejects without truncation.
Parser defects are rejected. Attachments count as MIME nodes and file bytes, but
their text does not become body tokens or spend the eligible decoded-text budget.
The trusted proxy deadline is clamped to 60s backend execution with the 4s cleanup
reserve. Deadline/disconnect termination uses 1s TERM reap and 1s KILL reap; an
unreapable child terminates the supervisor without launching another child.
Status exposes only startup or matching current receiving/processing phase and
never a label, content, filename or history.

Trước khi sẵn sàng, adapter kiểm tra: manifest `status: complete` và schema 2; SHA-256
của mọi artifact; `settings.feature_names` trùng `preprocess.BASELINE_FEATURE_NAMES`
(134 feature; run ghi `FEATURE_NAMES` cũ như `2026-10-23_web2` bị từ chối); chữ ký tiền
xử lý ghi lúc train (`settings.preprocessing`) và danh sách stopwords trùng
`pipeline_cache.preprocessing_signature()` hiện tại; classifier phục vụ (tên pin hoặc
`selected_model`) có trong `manifest["models"]`, là sklearn/XGBoost (BERT bị từ chối), tên
file không chứa thư mục và ngưỡng trong [0, 1]; kiểu, lớp `[0, 1]` và độ rộng (Doc2Vec 100 + 134 = 234)
của object đã nạp. Thiếu `magika`, `oletools` hoặc `tldextract` thì worker không sẵn sàng ở
stage `DEPENDENCY_LOAD` (bản đóng băng nạp lười các gói này và bỏ qua olevba nếu thiếu, nên
feature sẽ sai thay vì báo lỗi); run có `lemmatization: true` bị từ chối ở
`INFERENCE_SETTINGS`. Byte của từng file được kiểm tra lại trước khi unpickle;
danh sách global cho phép gồm Doc2Vec/numpy và module `sklearn.`/`xgboost.`. Chỉ hỗ
trợ file model cục bộ đáng tin; đây không phải sandbox cho pickle lạ.

Tiền xử lý và suy luận dùng chính code lúc train (bản đóng băng): `pipeline_cache._process` (trích
feature từ byte gốc trước khi làm sạch, không lemmatize), `preprocess.baseline_feature_vector`
(ghép 134 feature theo đúng thứ tự `BASELINE_FEATURE_NAMES`, float32 như `train.py` v6) và
`preprocess.infer_document_vector` (alpha 0.025, min_alpha 0.0005, số epoch suy luận
của run, seed theo nội dung). Stopwords được cố định theo danh sách ghi trong run.
Scaler chỉ `transform`, vector Doc2Vec đứng trước feature đã chuẩn hoá. Một luồng
tính toán, hash seed 0 cho tiến trình con, khôi phục RNG Python/NumPy/Doc2Vec sau mỗi
request. Không tải tài nguyên, không fit, train hay evaluate trong request.

Explanation (FR-11, AD-14): khi classifier phục vụ là XGBoost và run có `target_mode:
phishing`, kết quả kèm `explanation.factors` gồm tối đa 5 factor `{factor, direction,
strength}`. Đây là đóng góp SHAP chính xác (`pred_contribs`) trên margin của đúng vector
đã cho ra nhãn: 100 chiều Doc2Vec gộp thành `text_content`, `direction` tính theo lớp 1,
`strength` là độ lớn tương đối so với factor mạnh nhất. Tên hiển thị tiếng Anh nằm trong
`web/contracts/explanation-factors.json`, phủ `text_content` và đủ 134 feature của v6
(`num_attachments` kèm ghi chú tạm "Known dataset bias" vì email hợp lệ trong dữ liệu train
gần như không có file đính kèm; `is_html` và `html_to_text_ratio` không còn là input). Với run
v6, web phục vụ XGBoost được pin nên mỗi kết quả kèm explanation; MLP (`selected_model`)
không có đóng góp chính xác nên khi phục vụ nó (`IAP_WEB_MODEL=selected`) chỉ có nhãn. 15 luật file đính kèm (`ATTACHMENT_RULES`) của upstream không đổi nhãn
(để sau). Lúc khởi động, adapter kiểm tính cộng trên 256 dòng test đầu
và kiểm catalogue phủ đủ feature (sai thì không sẵn sàng, stage `EXPLANATION`); mỗi
request kiểm lại tính cộng, sai thì trả `INTERNAL_ERROR`. Classifier khác, run `broad`,
hoặc email mà mọi đóng góp đều bằng 0 thì chỉ trả nhãn. Factor không được ghi log và không có trong lỗi hay kênh status. Factor mô tả
model đang dựa vào đâu, không phải bằng chứng email độc hại.

The observed environments are Python 3.11.16 (`web/.venv`, created with uv) and Python
3.11.2 (root `.venv`) on native Windows; ML packages are
NumPy 2.4.6, SciPy 1.17.1, Gensim 4.4.0, scikit-learn 1.9.1, XGBoost 3.2.0,
beautifulsoup4 4.15.0, tldextract 5.4.0, Magika 1.0.3 (onnxruntime 1.31.1) and oletools
0.60.2, installed directly in both venvs (the former `project_legacy_packages.pth` link to a
sibling `venv/` was removed on 2026-10-20). `requirements.txt` khoá toàn bộ backend (API,
gói ML và phụ thuộc gián tiếp) theo đúng các phiên bản này; nltk và textblob đã bỏ.
`requirements-api.txt` chỉ khoá phần API, dùng khi `.venv` gốc đã có gói ML. Chữ ký tiền
xử lý băm phiên bản beautifulsoup4, tldextract và magika cùng danh sách stopwords, nên môi
trường lệch sẽ bị từ chối (`MODEL_COMPATIBILITY`).

Giới hạn đã đo (2026-11-04): upstream trích feature v6 trong sandbox Linux (README upstream:
Python 3.11.2 của Debian 12, nhiều khả năng có bản vá CVE-2023-27043 của Debian cho
`email.utils.getaddresses`; manifest
chỉ ghi Python 3.11.9 của bước train). Trích lại 250 email test lấy từ `Dataset/` cục bộ
(Enron maildir, SpamAssassin, Nazario, CSV, Phishing Pot; 50 mỗi nhóm) rồi so với
`data_X_test.npy` (atol 1e-6):

| Python | Vector feature trùng | Lệch | Lệch lớn nhất | Nhãn MLP trùng | Nhãn XGBoost trùng |
|---|---:|---:|---:|---:|---:|
| 3.11.2 (`.venv` gốc, không có `strict`) | 192 | 58 | 13,2 | 250/250 | chưa đo |
| 3.11.16 (`web/.venv`) | 199 | 51 | 0,43 | 250/250 | 250/250 |

Python 3.11.16 xoá hết lệch do địa chỉ sai cú pháp (`num_recipients`,
`hdr_from_address_count`…). 51 ca còn lại (39 SpamAssassin, 11 Nazario, 1 Phishing Pot) chỉ
lệch feature thống kê thân email (`char_length`, `digit_ratio`, `mime_max_blank_line_run`;
ca Phishing Pot thêm `word_count`, `uppercase_word_ratio`). Ở các ca đã thử, bản email
upstream trích thiếu một ký tự xuống dòng cuối so với file trong `Dataset/` (bỏ ký tự đó thì
khớp). Loader upstream đọc
file bằng `rb` và mbox bằng `get_bytes`, nên ký tự bị mất ở một bước không có trong code
đã đăng; web không giả lập bước đó trên email người dùng tải lên. Doc2Vec lệch tối đa
0,008. Nhãn XGBoost được đo lại ngày 2026-11-04 với `web/.venv` (Python 3.11.16).
XGBoost phục vụ ở ngưỡng của nó trên `data_X_test.npy` cho đúng FP 1292 / FN 76 như dòng
XGBoost của `evaluation_results.csv` (MLP được chọn: FP 1359 / FN 42).
Không phân phối virtualenv; cài lại từ `requirements.txt`. Adapter
startup records manifest/code hashes, actual package versions and settings in
transient supervisor metadata for local verification without widening HTTP results.

## Verify and upgrade

```powershell
# Trong web/ (kể cả bản chép riêng), với web/.venv (Python 3.11.16):
.venv/Scripts/python.exe -m unittest discover -s backend/tests -v
# Hoặc từ thư mục gốc: web/.venv/Scripts/python.exe -m unittest discover -s web/backend/tests -v
cd frontend
npm.cmd run contracts:check
npm.cmd test
npm.cmd run lint
npm.cmd run build
$env:PLAYWRIGHT_CHANNEL = 'msedge'
npm.cmd run test:integration
npm.cmd run test:real-model
npm.cmd run test:browser
```

Test backend dùng một run schema 2 nhỏ (khoảng 220 KB) dựng trên email tổng hợp theo cách
`train.py` upstream tạo run v6 (134 feature, Doc2Vec, scaler, XGBoost và MLP, chọn MLP, khoá
artifact viết bằng `\`), commit sẵn trong `web/backend/tests/fixture_run/` (`web/.gitattributes`
tắt đổi xuống dòng vì manifest băm từng byte). Chúng chép run này vào thư mục tạm, trỏ
`IAP_WEB_RUN_PATH` tới bản chép và không import module nào ở thư mục gốc, nên chạy được cả từ
thư mục gốc (`web.backend`) lẫn từ `web/` (`backend`). Khi đổi bản đóng băng hoặc email tổng
hợp, tạo lại fixture từ thư mục gốc bằng `web/.venv/Scripts/python.exe web/backend/tests/build_fixture.py` (chỉ
dùng hai module đóng băng, không import `train.py` gốc, với `PYTHONHASHSEED=0` như worker vì
vector Doc2Vec phụ thuộc hash seed). Chúng kiểm tra vector/nhãn lúc phục vụ trùng mảng test
lúc train, và các ca run chưa cấu hình, chưa hoàn tất, artifact bị sửa, lệch schema (kể cả
danh sách `FEATURE_NAMES` cũ) hoặc tiền xử lý, lemmatize, BERT được chọn hoặc được pin, tên
pin không có trong run, model pin có file hay ngưỡng sai, thiếu gói trích feature, đổi model phục vụ khi khởi động lại;
fixture chọn MLP nên các test cần XGBoost tự đặt `IAP_WEB_MODEL=XGBoost` (không dựa vào
`MODEL_NAME`), còn các ca chỉ có nhãn đặt `IAP_WEB_MODEL=selected`. Nhóm test `Explanation`
dùng XGBoost để so factor với đóng góp
tính độc lập (phủ `text_content` và 134 feature), kiểm lặp lại/đảo thứ tự/khởi động lại và
các ca fail closed. `PinnedRelease` nạp run v6 đã đóng gói (bỏ qua nếu chưa đóng gói) và
kiểm 234 cột, chữ ký `4c010fc3…`, `selected_model` MLP, `served_model` XGBoost ở ngưỡng
0,2113690823…, explanation `xgboost_pred_contribs` với 1–5 factor có trong catalogue cho
năm email mẫu và FP 1292 / FN 76 trên mảng
test đóng gói (bỏ qua nếu chưa đóng gói hoặc `RUN_PATH` là None). Test backend phải chạy bằng
`web/.venv` (hoặc một Python 3.11 có `getaddresses(strict=...)`). `test:real-model` khởi động
backend bằng `python -m backend` từ `web/`, với Python lấy từ biến `IAP_WEB_PYTHON` (nếu có),
rồi `web/.venv`, rồi `.venv` gốc (`.venv` gốc 3.11.2 bị từ chối, nên cần `web/.venv`); nó cần run đã đóng gói (hoặc `IAP_WEB_RUN_PATH`) và yêu cầu
run v6 (XGBoost được pin) trả nhãn kèm explanation, và trình duyệt hiện đúng nhãn factor của
catalogue.

Edge is installed on the tested workstation. For another installed browser select
its Playwright channel, or install Playwright Chromium. `test:real-model` starts actual
loopback web/backend/Next processes and checks five MIME samples through real API,
proxy and browser plus unavailable-result clearing; nó chỉ cần `web/` có run đã đóng gói.
The frontend-only `test:integration` checks transport serialization with a clearly
marked fixture backend. Browser regression fixtures
remain marked samples. Backend tests compare vector hashes and labels for five
emails under repeat, reorder and restarted child; they also exercise auth,
identity, limits, busy admission, artifact/readiness and recovery failures.
Process/network/browser execution may require sandbox approval. These checks
establish demo operation, not model quality, E0, Linux/Docker portability or cloud
timing/memory acceptance. Existing offline tests are assessed separately.

Đổi sang run mới: lấy run schema 2 (train bằng `train.py --output runs/<tên>`, hoặc tải run
upstream vào `runs/<YYYY-MM-DD_tên>` và kiểm mọi hash), chép nguyên byte `preprocess.py` và
`pipeline_cache.py` đúng bản đã train run đó (byte đã băm vào chữ ký, kể cả kiểu xuống dòng)
đè lên hai file trong `web/backend/frozen_pipeline/`, sửa adapter nếu run dùng danh sách
feature khác, đóng gói bằng
`python web/scripts/bundle-run.py --run runs/<tên>`, đặt `RUN_PATH = "model/<tên>"` (hoặc
`IAP_WEB_RUN_PATH`), kiểm `MODEL_NAME` có trong `manifest["models"]` của run mới (hoặc
đặt `selected`), tạo lại fixture bằng `build_fixture.py`, chạy test backend rồi khởi
động lại. `train.py` mặc
định train cả BERT; nếu BERT được chọn trên validation (và `MODEL_NAME` là `selected`) hoặc được pin thì web từ chối khởi động
(`MODEL_COMPATIBILITY`), nên với run dành cho web hãy thêm `--skip-text-training`. Sửa
hai file đóng băng làm đổi chữ ký tiền xử lý, nên run đang pin sẽ bị từ chối. Nhãn `phishing` hiện dựa trên bằng chứng validation;
E0 vẫn cần rà soát nguồn nhãn và đánh giá độc lập. Giữ nguyên ranh giới HTTP và luồng
frontend; muốn quay lại run trước thì đặt lại `RUN_PATH` (cùng code tiền xử lý đã
train run đó). Xem [ngoại lệ local](../../_bmad-output/specs/spec-iap-web-application/local-demo.md).
