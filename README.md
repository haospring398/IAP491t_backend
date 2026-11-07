# Phishing Email Detection (IAP491)

Phát hiện email phishing từ **raw email** (`.eml`, mbox, CSV): trích 134 feature kỹ thuật cùng một vector
Doc2Vec 100 chiều, train **9 classifier** và chọn **1 model tốt nhất trên tập validation**.
Tập test chỉ được dùng để đánh giá sau cùng, không dùng để chọn model hay ngưỡng. Kèm theo là web demo
chạy model thật (`web/`).

Code pipeline theo repo [buidangduy05/IAP491t_backups](https://github.com/buidangduy05/IAP491t_backups):
bản **19-10** (commit `ae08251`), cập nhật tới **v6** (commit `a202d55`, đã train run `baseline_v6`;
commit mới nhất `3c88826` chỉ đổi manifest của run). Hai lịch sử git không chung gốc nên code được merge
3 chiều theo từng file. Phần riêng của project được giữ lại: loader TREC 2007 bản thô (`Dataset/trec07p`),
`--feature-set no_era_proxies`, `artifact_store.py`, `analyze_shap.py` và web demo. Nhánh BERT đã bỏ như upstream.

## Cấu trúc thư mục

```
PhishingEmailDetection/
├── load_data.py              # đọc Dataset/ (Nazario, CSV, SpamAssassin, Enron, EPVME, Phishing Pot, malspam, TREC 2007 thô)
├── preprocess.py             # làm sạch text + trích feature (BASELINE_FEATURE_NAMES, ATTACHMENT_RULES)
├── pipeline_cache.py         # cache SQLite cho bước tiền xử lý, chạy song song
├── dataset_audit.py          # sổ đối soát ingestion (ingestion.sqlite, load_summary.json)
├── train.py                  # training: --mode baseline|specialists, --output <run-dir>
├── evaluate.py               # đánh giá: --run <run-dir>
├── analyze_feature_importance.py, analyze_shap.py   # feature importance, SHAP của XGBoost
├── specialists.py, predict_specialists.py           # chế độ cũ: 4 nhánh chuyên trách, lọc 2 tầng
├── benchmark_pipeline.py     # đo tốc độ cache tiền xử lý
├── download_nazario.py       # tải corpus Nazario về Dataset/phishing/
├── artifact_store.py         # xác minh/publish run cũ trong dumped_models/classification/runs/
├── requirements.txt
├── tests/                    # test_pipeline.py, test_evaluate.py, test_shap.py
├── docs/                     # DATA_PIPELINE_REVIEW.md, IAP_Web_Application_Plan.md
├── Dataset/                  # dữ liệu gốc (git bỏ qua, trừ README của từng nguồn)
├── runs/                     # kết quả từng lần train/đánh giá, mỗi lần một thư mục runs/<YYYY-MM-DD_mô-tả>
├── dumped_models/classification/runs/<run-id>/   # run web cũ, không còn phục vụ — không xoá/di chuyển
├── model/                    # model chọn để deploy (copy tay)
├── web/                      # frontend Next.js, backend Python (code tiền xử lý đóng băng), contracts, docs
├── paper/                    # tài liệu tham khảo
└── _bmad/, _bmad-output/, .agents/   # công cụ và tài liệu lập kế hoạch BMad
```

## Cài đặt

Python 3.11. Nên dùng bản có `email.utils.getaddresses(..., strict=...)` (ví dụ 3.11.16; Debian 12 đã vá ngược
cho 3.11.2): upstream trích feature của v6 với bản đó, còn python.org 3.11.2 (`.venv` hiện tại) cho vài feature
header/body hơi khác (xem `web/backend/README.md`). Chữ ký tiền xử lý không ghi phiên bản Python nên không phát
hiện được khác biệt này.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Không cần dữ liệu NLTK nữa: v6 gỡ `nltk`/`textblob` (CVE chưa có bản vá), chép danh sách stopword vào
`preprocess.NLTK_ENGLISH_STOPWORDS` và tắt lemmatization. `oletools` phân tích macro VBA trong tệp đính kèm;
`magika` nhận diện loại nội dung tệp; `tldextract` tách domain theo Public Suffix List (offline). Đọc QR code
(`inspect_email_qr_codes`, chưa dùng khi train) cần cài thêm `zxing-cpp` và `Pillow`; đọc QR trong PDF cần `PyMuPDF`.

## Dữ liệu

Dataset **không có trong repo**. Đặt dữ liệu vào `Dataset/` theo cấu trúc sau:

| Thư mục / file | Nội dung | Nhãn |
|---|---|---|
| `Dataset/enron/maildir/` | Enron, khoảng 517k email nội bộ | Hợp lệ |
| `Dataset/spamassassin/` | Các thư mục `*_easy_ham`, `*_hard_ham`, `*_spam` | Hợp lệ / spam theo tên thư mục |
| `Dataset/phishing/` | Nazario (`phishing-2015` … `phishing-2025`, `phishing0-3.mbox`, `private-phishing4.mbox`, `20051114.mbox`) | Phishing |
| `Dataset/phishing/*.csv` | CEAS-08, Enron, Ling, SpamAssassin, TREC-05/06/07 (Zenodo 8339691, kiểm tra MD5) | Hợp lệ / `spam_or_phishing` |
| `Dataset/trec07p/` | TREC 2007 bản thô (tuỳ chọn, xem dưới); khi có thì `TREC_07.csv` bị loại | Hợp lệ / `spam_or_phishing` |
| `Dataset/EPVME_extracted/` | 49k email tấn công giả lập (spoofing, XSS, MIME) | `malicious_synthetic` |
| `Dataset/phishing_pot/email/*.eml` | Phishing thật từ honeypot ([phishing_pot](https://github.com/rf-peixoto/phishing_pot), CC BY-NC 4.0) | Phishing |
| `Dataset/malspam/<năm>/*.zip` | Email malspam thật kèm file độc từ [malware-traffic-analysis.net](https://www.malware-traffic-analysis.net/), giữ nguyên zip có mật khẩu (tuỳ chọn) | `malspam` (lớp dương) |
| `Dataset/StealthPhisher2025.csv` | Corpus URL, không phải email | Không dùng để train email |
| `Dataset/df.csv` | Nhãn 0/1/2 không có tài liệu | Bị loại (vẫn được ghi lại) |

Tải Nazario: `python download_nazario.py` (tải lại và ghi đè file nào có dung lượng khác bản trên server;
`--only-recent N` chỉ tải N file cuối danh sách). Upstream dùng `download_malspam.py` để tải malspam nhưng
chưa công bố script này; thiếu `Dataset/malspam/` thì loader bỏ qua, không lỗi.

Quy tắc nhãn:
- Nhãn lấy theo nguồn dữ liệu, **không bao giờ suy từ nội dung**.
- Chỉ những file Nazario có tên đã đăng ký mới được gán nhãn phishing.
- File hoặc dòng không rõ nhãn được giữ lại với nhãn `unknown` để xem xét, không đưa vào train.

### TREC 2007 bản thô (`Dataset/trec07p/`, tuỳ chọn)

`TREC_07.csv` trong `Dataset/phishing/` là bản đã bỏ header và HTML (chỉ khoảng 0,04% dòng còn thẻ HTML),
nên mọi email hợp lệ từ CSV đều là văn bản thuần. Bản thô của cùng corpus còn đủ header và HTML: 25.220 ham
(17,1% là HTML) và 50.199 spam, đo ngày 2026-10-27. Bản này bổ sung email hợp lệ dạng HTML thật.

- Tải `trec07p.tgz` (ví dụ từ Kaggle `bayes2003/emails-for-spam-or-ham-classification-trec-2007`, nguồn gốc
  <https://plg.uwaterloo.ca/~gvcormac/treccorpus07/>), rồi giải nén để có `Dataset/trec07p/data/inmail.*` và
  `Dataset/trec07p/full/index`. Corpus chỉ dùng cho nghiên cứu.
- Spam trong corpus có email thật mang mã độc. Thêm `Dataset/` vào exclusion của antivirus (Defender,
  Kaspersky…) **trước khi** giải nén, vì antivirus có thể xoá file khi đọc. File có trong `full/index` nhưng
  thiếu trên đĩa được ghi vào `trec07p_missing_from_extract`.
- Khi có thư mục này, `TREC_07.csv` bị loại (ghi `excluded` trong sổ ingestion) để một email không xuất hiện
  hai lần dưới hai dạng mà dedup không nhận ra. Ham là lớp 0. Spam mang nhãn `spam_or_phishing` giống CSV, nên
  bị loại ở chế độ `phishing` và không vào tầng 2. `train.py` luôn nạp trec07p trước `Dataset/phishing/`.

## Chạy

```powershell
# (Tùy chọn) Đọc và đối soát toàn bộ dataset, không train.
.venv/Scripts/python.exe train.py --audit-only --output runs/2026-11-07_audit

# Train 9 model và chọn 1 model trên validation.
.venv/Scripts/python.exe train.py --workers 4 --output runs/2026-11-07_<mô-tả>

# Tính metrics trên test, vẽ ROC/confusion matrix, phân tích lỗi theo nguồn.
.venv/Scripts/python.exe evaluate.py --run runs/2026-11-07_<mô-tả>

# (Tùy chọn) Feature importance của các model dạng cây; SHAP của XGBoost.
.venv/Scripts/python.exe analyze_feature_importance.py --model-dir runs/2026-11-07_<mô-tả>/dumped_models/classification
.venv/Scripts/python.exe analyze_shap.py --run runs/2026-11-07_<mô-tả>
```

| Tùy chọn | Ý nghĩa |
|---|---|
| `--target-mode phishing` (mặc định) | Phishing + EPVME + malspam / hợp lệ. Spam và `spam_or_phishing` bị loại |
| `--target-mode broad` | Mọi thư độc hại (kể cả spam) / hợp lệ: tầng 1 của lọc hai tầng |
| `--target-mode phishing_vs_spam` | Phishing / spam, chỉ dùng nguồn ghi rõ loại: tầng 2 |
| `--feature-set no_era_proxies` | Bỏ `num_https_urls`, `num_http_urls`, `has_hidden_elements` (nghi phản ánh thời đại của email hợp lệ, đều trước 2008), còn 131 feature. Chỉ chọn cột lúc train |
| `--features-only` / `--from-features <thư mục>` | Tách 2 bước: trích feature (nơi đọc email độc hại) rồi train từ bản xuất, không đọc lại email thô |
| `--workers N` | Số process tiền xử lý (mặc định tối đa 4) |
| `--cache-dir` | Thư mục cache tiền xử lý (mặc định `.pipeline_cache/`) |

Mỗi lần chạy cần một thư mục `--output` mới. Run cũ không bao giờ bị ghi đè. `--mode` mặc định nay là
`baseline` (trước merge v6 là `specialists`). Run train bằng code trước v6 (53 feature) không tái lập hay train
tiếp được bằng code hiện tại, nhưng `evaluate.py` vẫn đánh giá lại được (bỏ qua mục BERT).

> ⚠️ **RAM và thời gian.** Toàn bộ dataset có khoảng 800k email. Máy 16 GB nên đóng bớt ứng dụng khác
> trước khi chạy. SVM (`SVC(probability=True)`) và KNN chậm khi tập train có vài trăm nghìn dòng.

### Tách bước trích feature và train

Malspam, EPVME và Phishing Pot chứa malware thật. Mọi phân tích đều **tĩnh** (email và attachment chỉ được đọc,
không bao giờ được chạy), nhưng chỉ bước trích feature chạm vào nội dung độc hại. Upstream chạy bước đó trong
một container Docker cách ly (không mạng, root chỉ đọc, non-root, RAM 7 GB) bằng `sandbox/sandbox.ps1`; thư mục
`sandbox/` **chưa được công bố** nên không có trong project này. Hai bước vẫn chạy được không cần Docker:

```powershell
.venv/Scripts/python.exe train.py --features-only --workers 4 --output runs/2026-11-07_features
.venv/Scripts/python.exe train.py --from-features runs/2026-11-07_features --output runs/2026-11-07_<mô-tả>
```

Bản xuất ở dạng **không chạy được code**: vector `.npy` (đọc với `allow_pickle=False`), text sạch `.jsonl.gz`,
metadata CSV, cùng SHA-256 của từng file trong `features_manifest.json`. Bước train kiểm tra hash và không bao giờ
đọc email thô. Bản xuất luôn đủ 134 feature; `--feature-set` áp dụng ở bước train.

## Cách hoạt động

```
raw email ─► load_data.py ─► khử trùng + gom nhóm gần trùng ─► chia train/validation/test 60/20/20 theo nhóm
                                     │
                                     ▼
          preprocess.py: text hiển thị đã khử obfuscation ─► Doc2Vec (100 chiều)
                         134 feature kỹ thuật ─► StandardScaler (fit trên train)
                                     │
                                     ▼
          train.py: 9 classifier ─► chọn ngưỡng trên validation ─► chọn 1 model ─► evaluate.py (test)
```

**Chống rò rỉ dữ liệu**
- Email trùng nội dung (SHA-256) chỉ giữ một bản. Cùng nội dung nhưng nhãn mâu thuẫn thì loại cả hai, ghi vào `label_conflicts.csv`.
- Email gần trùng (SimHash, Hamming ≤ 3) luôn nằm chung một tập, không bị chia giữa train và test.
- Vocabulary Doc2Vec và StandardScaler chỉ fit trên tập train.

**Tiền xử lý text**
- Bỏ phần HTML bị ẩn (`display:none`, chữ cùng màu nền, `font-size:0`…).
- Ghép chữ bị tách bằng tag (`Pa<span>ss</span>word`).
- Đổi homoglyph Cyrillic/Greek, chữ "font lạ" (math bold, fullwidth, small caps) về Latin.
- Xóa ký tự vô hình.
- Bỏ các chuỗi chỉ lộ nguồn dữ liệu: subject mẫu của EPVME, địa chỉ `phishing@pot`.

### 134 feature (`preprocess.BASELINE_FEATURE_NAMES`)

| Nhóm | Số | Ví dụ |
|---|---:|---|
| Nội dung | 7 | Độ dài, tỷ lệ chữ hoa, dấu `!`, ký hiệu tiền |
| URL | 11 | Số URL, IP, rút gọn link, TLD đáng ngờ, anchor/href lệch |
| Header | 6 | Freemail, Reply-To khác người gửi, thương hiệu trong display name |
| HTML | 4 | Form, script, phần tử ẩn, email chỉ có ảnh. `is_html` và `html_to_text_ratio` **không** vào model: `is_html` chỉ là điều kiện để chạy các kiểm tra HTML (email không có phần HTML nhận 0); `html_to_text_ratio` > 0 đúng khi có HTML nên cũng chỉ lộ "có HTML hay không" |
| Attachment | 19 | File thực thi ngụy trang, macro, double extension, archive mã hóa, PDF active content, nội dung active (HTML/script/binary) mang tên tài liệu/ảnh theo Magika |
| Social engineering | 5 | Từ khóa khẩn cấp, thông tin nhạy cảm, thương hiệu, lời chào chung chung, trúng thưởng |
| Header security / giả mạo | 21 | Nhiều `From`, From injection, envelope sai cú pháp, Return-Path lệch, domain giả dạng/ghép thương hiệu, domain người gửi giả dạng domain người nhận |
| Link | 14 | URL chứa email người nhận, open redirect, hosting miễn phí, anchor nêu thương hiệu sai domain, link giả dạng domain người gửi, tỷ lệ link ra ngoài domain người gửi, hình dạng host lạ nhất (độ dài, chữ số, gạch nối, entropy, subdomain, punycode) |
| Payload attachment | 11 | olevba (AutoExec, VBA stomping, XLM), HTML smuggling, ISO, LNK, OneNote, PDF `/URI`, `.mobileconfig` |
| HTML/script | 13 | `eval`, `atob`, `document.write`, iframe ẩn, ô nhập mật khẩu, chuỗi mã hóa dài |
| HTML payload | 23 | **URL trong thuộc tính HTML**: scheme nguy hiểm (`javascript:`, `data:text/html`…), URL bị obfuscate (entity/tab trong scheme, `user@host`, IP hex/thập phân, `%` trong host, `\`), form gửi ra ngoài, `<meta refresh>`, `<base href>`. **Phần tử ẩn chứa payload**: link ẩn tới domain không có trong phần hiển thị, chuỗi mã hóa (base64/hex/`%xx`/`\x`), script/markup, chuỗi entropy cao. **JavaScript bị obfuscate**: escape `\x`/`\u`, mảng char-code, cắt nối chuỗi, chữ ký packer/JSFuck/aaencode/jjencode/obfuscator.io, chuỗi mã hóa entropy cao, giải mã rồi thực thi; redirect, ghi DOM. **HTML injection**: payload markup/script trong query của link, markup active trong giá trị thuộc tính, markup bị mã hóa (`&lt;script`, `%3Cscript`), thẻ nguy hiểm (`object`, `embed`, `iframe srcdoc`, `svg onload`), CSS `expression()` |

Mọi phân tích attachment đều **tĩnh**: không thực thi, không giải nén ra đĩa, không mở URL.

**Loại nội dung file (Magika).** Ngoài magic byte, mỗi attachment (kể cả file trong ZIP) được Google Magika
(`magika==1.0.3`, model deep learning chạy offline trên CPU) gán nhãn nội dung (`content_type` trong
`inspect_email_attachments`). Magika mạnh ở định dạng text mà magic byte không phân biệt được: HTML, JavaScript,
VBScript, PowerShell, batch, script UTF-16. Tên/MIME là tài liệu hoặc ảnh (`.pdf`, `.docx`, `.jpg`, `image/*`…)
nhưng nội dung active → `attachment_disguised_active_count`. Magika chỉ cho biết **loại** file, không phán file độc.

**URL bị gateway bọc.** Link do gateway phía người nhận viết lại (Outlook Safe Links, Proofpoint URL Defense v1–v3,
Barracuda LinkProtect, Trend Micro Click-Time) được gỡ về URL gốc (`unwrap_gateway_url`) trước mọi feature URL/link.
Redirect phía người gửi (`google.com/url`, `l.facebook.com`) giữ nguyên, vì đó là dấu hiệu open redirect.

**File gửi qua link cloud** (Drive, OneDrive/SharePoint, Dropbox, iCloud Mail Drop, Proton Drive, WeTransfer, Box,
MEGA, Zoho WorkDrive, Adobe) và email thông báo chia sẻ của nhà cung cấp: `inspect_cloud_file_links`,
`cloud_file_link_count`, `cloud_share_notification` trong `_content_indicators`. Chỉ là **bằng chứng**, không vào
model: dữ liệu legit (Enron, SpamAssassin ham) gần như không có link loại này, nên model sẽ học "email hiện đại = phishing".

### Luật chắc chắn (`preprocess.ATTACHMENT_RULES`)

Gần như không email nào trong tập train mang macro tự chạy, LNK hay HTML smuggling, nên model học được trọng
số gần 0 cho các feature này. Vì vậy 15 dấu hiệu dưới đây **tự gắn cờ email**, chạy song song với model:
file thực thi ngụy trang, exe nhúng trong file khác, double extension, tên file chứa ký tự đảo chiều (RLO),
macro AutoExec, VBA stomping, macro XLM, LNK chứa lệnh, HTML smuggling, ISO/IMG, OneNote nhúng file,
archive có mật khẩu kèm mật khẩu trong body, Apple `.mobileconfig`, nội dung active mang tên tài liệu/ảnh (Magika),
và **JavaScript bị obfuscate trong HTML body** (`obfuscated_script`).

- Mỗi luật đã được đo: **0 lần kích hoạt** trên email hợp lệ có attachment (119 email SpamAssassin ham;
  Enron maildir và các CSV không có attachment).
- Luật Magika (`disguised_active_content`, đo 2026-10-31): 0/556 email SpamAssassin ham có phần đính kèm
  (tính cả phần inline); bắt 10 spam, 6 Phishing Pot (HTML đặt tên `.pdf`), 35 malspam (JS/PE đặt tên `.png`/`.jpg`).
- Luật `obfuscated_script` (`html_js_obfuscated`, đo 2026-11-02): kích hoạt khi có chữ ký obfuscator (packer,
  JSFuck, aaencode, jjencode, obfuscator.io) hoặc ≥ 2 trong 6 dấu hiệu (escape, mảng char-code, cắt nối chuỗi,
  chuỗi mã hóa, giải mã rồi thực thi). 0/1.008 email HTML hợp lệ (SpamAssassin ham + CSV Zenodo), dù 129 email
  trong số đó có JavaScript thật. JSON-LD (`application/ld+json`) không bị tính là script.
- Không dùng làm luật: "có file thực thi" (5/119 email hợp lệ), script/form và PDF active content (phổ biến ở
  file hợp lệ, và model có hơn 200 ví dụ phishing để tự học).
- `evaluate.py` báo thêm dòng `<model> + attachment rules` (model **hoặc** luật, cùng ngưỡng) và file
  `attachment_rule_hits.csv`. Web demo gọi `preprocess.assess_attachment_rules(raw)`.

Domain được tách theo **Public Suffix List** (bản đóng gói trong `tldextract==5.4.0`, không cần mạng):
`a.b.example.co.uk` → `example.co.uk`, `user.github.io` là một site riêng. Phát hiện giả dạng có hai lớp:
so với `BRAND_DOMAINS` (khoảng 28 thương hiệu), và so link/người gửi/người nhận **với nhau**
(`domains_look_alike`: homoglyph, `rn`→`m`, sửa 1–2 ký tự, đổi đuôi tên dài, ghép bằng gạch nối).
Lớp thứ hai dùng được cho mọi domain, không cần danh sách.

Những dấu hiệu được trích nhưng **cố ý không đưa vào model**, vì trong các corpus này chúng phản ánh nguồn
chứ không phải phishing: Authentication-Results/SPF/DKIM, số hop `Received`, Message-ID, X-Mailer, số đếm
obfuscation, dấu hiệu BEC, độ phổ biến domain theo Tranco (`enron.com` không có trong danh sách 2026), host trên
suffix private của PSL (chỉ phổ biến ở phishing sau 2015).

### 9 classifier và cách chọn

- **9 classifier:** XGBoost, Random Forest, MLP, Logistic Regression, SVM, KNN, Decision Tree, AdaBoost, Gradient Boosting.
  Naive Bayes đã bị loại (2026-11-02): GaussianNB bão hòa xác suất về 0/1 trên vector Doc2Vec + feature đã chuẩn hóa (baseline_v5: ngưỡng 1e-45, recall 0,65).
- **Tune:** XGBoost, Random Forest và MLP có nhiều bộ tham số ứng viên, được so trên validation.
- **Ngưỡng mỗi model:** trên validation, lấy recall cao nhất với điều kiện precision ≥ 0,9 (`MIN_VALIDATION_PRECISION`).
- **Model được chọn:** model tốt nhất theo quy tắc trên, ghi vào `run_manifest.json` (`selected_model`).

## Kết quả của một run

| File | Nội dung |
|---|---|
| `dumped_models/classification/*.pkl` | 9 model, `model_dbow.pkl` (Doc2Vec), `feature_scaler.pkl` |
| `dumped_models/classification/run_manifest.json` | Model được chọn, ngưỡng, tên feature, chữ ký tiền xử lý, hash các file |
| `validation_results.csv`, `ablation_validation.csv` | Kết quả mọi ứng viên trên validation; so sánh Doc2Vec / feature / kết hợp |
| `evaluation_results.csv`, `evaluation_by_source.csv`, `error_analysis.csv` | Metrics trên test (sau khi chạy `evaluate.py`), kể cả dòng `+ attachment rules` |
| `attachment_rule_hits.csv` | Số email trong test mà mỗi luật attachment bắt được, và bao nhiêu trong số đó thật sự là phishing |
| `ROCs.png`, `confusion-matrix.png` | Biểu đồ trên test |
| `model-metrics.png` | Biểu đồ cột Precision, Recall, F1, ROC-AUC, AP, FP của từng model trên test |
| `load_summary.json`, `ingestion.sqlite` | Đối soát từng file/bản ghi đã đọc |
| `source_labels.csv`, `label_conflicts.csv`, `label_scope_excluded.csv`, `training_dispositions.csv` | Nhãn theo nguồn, mâu thuẫn, bị loại, và lý do cho từng email |

## Giới hạn cần biết

- **Mỗi nguồn chỉ chứa một lớp.** Ví dụ Enron toàn email hợp lệ, Nazario toàn phishing. Model có thể học "nguồn" thay vì "phishing", nên hãy xem `evaluation_by_source.csv` chứ đừng chỉ nhìn F1 tổng.
- **Spam** có nhãn rõ chỉ đến từ SpamAssassin (khoảng năm 2002), nên tầng `phishing_vs_spam` dễ học theo thời kỳ.
- `Dataset/phishing_pot/email/sample-3989.csv` là danh sách dữ liệu cá nhân bị rò rỉ, không phải email. Loader không đọc nó. Không commit thư mục này.
- **Antivirus** (Defender, Kaspersky…) có thể cách ly mẫu EPVME/Phishing Pot/TREC chứa malware khi chúng được giải nén hoặc mở. Loader ghi lại các file bị chặn (`files_blocked_by_antivirus`) và mẫu Phishing Pot thiếu so với git (`phishing_pot_missing_from_checkout`) thay vì dừng, nên số email đọc được có thể khác nhau giữa các máy. Thêm `Dataset/` vào exclusion trước khi chuẩn bị dữ liệu.
- **Suy luận** phải dùng `preprocess.extract_baseline_features()` và `preprocess.infer_document_vector()` để vector khớp với lúc train. Hàm đầu luôn trả đủ 134 cột; với run `--feature-set no_era_proxies`, chọn các cột theo `settings.feature_names` trong manifest trước khi scale.

## Web demo

Web demo chạy model thật từ một run schema 2 ghim bằng `RUN_PATH` trong `web/backend/policy.py` hoặc biến môi
trường `IAP_WEB_RUN_PATH` (đường dẫn tương đối tính từ `web/`), không train hay đánh giá lại. Run được đóng gói vào
`web/model/` (git bỏ qua) bằng `python web/scripts/bundle-run.py --run runs/2026-11-02_baseline_v6` (bản sao đã
kiểm hash của `runs/baseline_v6` upstream), nên thư mục `web/` chạy được khi chép riêng. Làm theo
[web/backend/README.md](web/backend/README.md) để chạy backend bằng `web/.venv` (`python -m backend` từ `web/`), và
cấu hình cùng token server-only cho app Next trong [web/](web/README.md) (`cd web/frontend`, `npm.cmd run dev`).
Python service và app Next chỉ bind loopback.

Web demo không dùng `preprocess.py` và `pipeline_cache.py` ở thư mục này mà dùng bản sao đóng băng trong
`web/backend/frozen_pipeline/` (đúng byte code upstream `a202d55` đã train run đang pin), và từ chối run có chữ ký
tiền xử lý khác bản sao đó. Sửa hai file ở thư mục gốc không ảnh hưởng web. Từ khi merge v6, nội dung hai file ở
gốc giống hệt bản đóng băng, nhưng chữ ký băm cả byte xuống dòng: `preprocess.py` đóng băng là CRLF như lúc upstream
train, còn bản ở gốc là CRLF hay LF tuỳ `core.autocrlf` lúc checkout. Muốn web dùng run khác thì chép nguyên byte
hai file đã train run đó vào `web/backend/frozen_pipeline/`, đóng gói và pin run mới, tạo lại fixture test
(`web/backend/tests/build_fixture.py`) và chạy test web backend.

## Kiểm tra

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Tài liệu khác: [docs/DATA_PIPELINE_REVIEW.md](docs/DATA_PIPELINE_REVIEW.md). Upstream còn nhắc
`SPECIALIST_PIPELINE.md` và `PIPELINE_VALIDATION.md` nhưng chưa công bố hai file này.
