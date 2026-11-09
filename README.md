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
├── dataset_ablation.py       # ablation theo dataset: bỏ/chỉ giữ từng nhóm dataset, so trên cùng tập test
├── analyze_feature_importance.py, analyze_shap.py   # feature importance, SHAP của XGBoost
├── specialists.py, predict_specialists.py           # chế độ cũ: 4 nhánh chuyên trách, lọc 2 tầng
├── benchmark_pipeline.py     # đo tốc độ cache tiền xử lý
├── download_nazario.py       # tải corpus Nazario về Dataset/phishing/
├── download_malspam.py       # tải malspam (zip có mật khẩu) về Dataset/malspam/
├── artifact_store.py         # xác minh/publish run cũ trong dumped_models/classification/runs/
├── requirements.txt
├── tests/                    # test_pipeline.py, test_evaluate.py, test_shap.py, test_dataset_ablation.py
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
`--only-recent N` chỉ tải N file cuối danh sách). Tải malspam (tuỳ chọn): `python download_malspam.py`
(`--years 2024 2025` để giới hạn năm; mặc định quét từ 2013, khoảng 1–2 giờ vì chờ 1 giây giữa hai request).
Script lưu zip có mật khẩu nguyên dạng vào `Dataset/malspam/<năm>/`, nhưng chỉ khi danh mục zip có file `.eml`;
zip chỉ chứa malware/attachment/pcap và zip email phishing bị bỏ ngay trong RAM. Kết quả ghi ở
`Dataset/malspam/manifest.csv` (SHA-256 từng zip) và `skipped.csv`; chạy lại không tải trùng. Upstream nhắc tới
`download_malspam.py` nhưng chưa công bố; bản ở đây được thêm và sửa local (2026-11-08), nên tập malspam không trùng
đúng tập upstream đã dùng. Thiếu `Dataset/malspam/` thì loader bỏ qua, không lỗi.

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

## Ablation theo dataset (`dataset_ablation.py`)

Đo đóng góp của từng dataset theo yêu cầu "tách từng dataset ra để đo lường, so sánh". Script đọc một bản xuất
`train.py --features-only` (ví dụ `runs/2026-11-08_features_v6`, đã kiểm hash). Mỗi thí nghiệm bỏ hoặc chỉ giữ một
nhóm dataset trong **train và validation**, train lại Doc2Vec cùng 9 classifier đúng như `train.py` (ngưỡng chọn trên
validation, precision ≥ 0,9), rồi chấm trên **cùng một tập test đầy đủ**: mọi thí nghiệm dùng chung dòng test và thứ tự.
Mọi thí nghiệm chạy với `PYTHONHASHSEED=0` (script tự khởi động lại nếu cần), vì vector Doc2Vec phụ thuộc hash seed.

**Nhóm dataset.**
- Nhóm dương:
  - `nazario`: mọi `phishing-20xx`, `phishing*.mbox`, `private-phishing4.mbox`, `20051114.mbox`;
  - `phishing_pot`;
  - `epvme`;
  - `malspam`.
- Nhóm hợp lệ:
  - `enron`: `enron` và `Enron.csv`;
  - `spamassassin`: bản thô và `SpamAssasin.csv`;
  - `trec`: `trec07p`, `TREC_05.csv`, `TREC_06.csv`. Bảng nhóm còn ánh xạ `TREC_07.csv` → `trec` cho bản xuất làm
    khi không có `Dataset/trec07p`; trong `runs/2026-11-08_features_v6` nó có 0 dòng, vì `load_data.py` loại CSV này
    khi có bản thô (cùng corpus TREC 2007);
  - `ceas`;
  - `ling`.

Source lạ làm script dừng thay vì bị gom nhầm.

**18 thí nghiệm, theo thứ tự ưu tiên** (mỗi thí nghiệm khoảng 4 giờ trên máy 16 GB, tổng khoảng 72 giờ):
1. `reference`, `reference_seed43`, `reference_seed44`: đủ dữ liệu. Seed đổi seed của Doc2Vec và classifier, không đổi
   cách chia tập; ba lần chạy này cho mức nhiễu.
2. `without_<nhóm>` × 9: bỏ một nhóm.
3. `without_enron_trec`: bỏ cùng lúc Enron và TREC. Hai nhóm này chồng lấn rất nhiều (xem phần cụm gần trùng), nên bỏ
   riêng từng nhóm thì nhóm kia bù vào. Train chỉ còn 15.511 email hợp lệ so với 42.889 email dương: tỷ lệ lớp đảo
   ngược, nên đọc thí nghiệm này qua `Pair-ROC-AUC`/`Pair-AP` và số đếm theo nhóm, không qua recall/FPR ở ngưỡng.
4. `only_<nhóm dương>` × 4: một nhóm dương cùng toàn bộ email hợp lệ, tức là mỗi dataset một mình làm được gì.
5. `random_like_nazario`: đối chứng ngẫu nhiên phân tầng, riêng cho train và validation (seed cố định).
   - Mục tiêu tổng bằng số dòng mà `without_nazario` bỏ.
   - Mỗi nhóm dương bỏ theo tỷ lệ của nó trên toàn bộ mẫu dương của tập, kể cả cụm bị loại khỏi lần bốc (train:
     khoảng 61% EPVME, 17% Phishing Pot, 14% Nazario, 8% malspam).
   - Chỉ bốc trọn các cụm `_group` thuần dương, thuộc một nhóm và không lớn hơn 5% mục tiêu. Vì vậy cụm template XSS
     6.011 dòng không bao giờ bị bốc; cụm lẫn nhãn và cụm vắt nhiều nhóm cũng không.
   - Dung sai: tổng ±1%, từng nhóm ±2% phần của nhóm đó. `experiment.json` (`random_control`) ghi số dòng và số cụm
     bỏ theo nhóm, các cụm bị loại kèm kích thước, và số cụm mà `without_nazario` bỏ. Trên
     `runs/2026-11-08_features_v6`, train bỏ 6.097/6.096 dòng trong 4.858 cụm, so với 4.343 cụm của `without_nazario`.
   - `undrawable_rows` đếm dòng dương của từng nhóm nằm trong cụm không được bốc (lẫn nhãn, vắt nhóm hoặc quá lớn).
     Train có 1.854 dòng Nazario như vậy, hầu hết chung cụm với EPVME, và 7.334 dòng EPVME (gồm cụm template 6.011
     dòng). `without_nazario` bỏ cả những dòng Nazario này, còn đối chứng thì không bao giờ bỏ được. Vì vậy đối chứng
     bỏ phần Nazario "riêng" nhiều hơn tỷ lệ và phần Nazario chung với EPVME ít hơn.
   - Đối chứng này tách "ít mẫu dương hơn" khỏi "chính các mẫu Nazario". Nó chỉ có một lần bốc.

```powershell
$F = "runs/2026-11-08_features_v6"; $O = "runs/2026-11-09_dataset_ablation"
.venv/Scripts/python.exe dataset_ablation.py --features $F --output $O --list       # 18 thí nghiệm, số dòng, trạng thái
.venv/Scripts/python.exe dataset_ablation.py --features $F --output $O --overlap    # bước 0, vài chục giây
.venv/Scripts/python.exe dataset_ablation.py --features $F --output $O              # chạy hết, bỏ qua thí nghiệm đã xong
.venv/Scripts/python.exe dataset_ablation.py --features $F --output $O --experiments reference without_malspam
.venv/Scripts/python.exe dataset_ablation.py --features $F --output $O --summarize  # chỉ tổng hợp
.venv/Scripts/python.exe dataset_ablation.py --features $F --output $O --unlock without_enron  # lock của lần bị ngắt
```

**Chạy song song, tiếp tục khi bị ngắt.**
- **Song song.** Có thể mở nhiều cửa sổ, mỗi cửa sổ chạy `--experiments` khác nhau; mỗi tiến trình cần thêm vài GB RAM.
  File `lock` trong thư mục thí nghiệm ngăn hai tiến trình chạy cùng một thí nghiệm.
- **Tổng hợp.** Mỗi tiến trình tự tổng hợp khi xong, nên các file `summary_*` có thể bị cửa sổ khác ghi đè. Khi mọi
  cửa sổ đã xong, chạy `--summarize` một lần nữa để lấy bản cuối.
- **Tiếp tục khi bị ngắt.** Thí nghiệm đã `complete` với cùng bản xuất và định nghĩa (gồm cả số epoch và
  `PYTHONHASHSEED`) thì được bỏ qua. Nếu khác, script dừng cả hàng đợi (`DefinitionMismatch`) và yêu cầu dùng
  `--output` mới. Thí nghiệm bị ngắt
  hoặc lỗi sẽ chạy lại từ đầu ở lần sau; nếu lock còn sót thì xoá bằng `--unlock`, nhưng chỉ khi chắc chắn không còn
  tiến trình nào chạy thí nghiệm đó.
- **Khi một thí nghiệm lỗi.** Thí nghiệm đó được ghi `status: failed` kèm traceback, các thí nghiệm sau vẫn chạy, danh
  sách thí nghiệm lỗi được in trước phần tổng hợp, và lệnh trả mã 1 ở cuối.
- **Không sửa code giữa đợt.** Mỗi tiến trình ghi hash code lúc khởi động. Nếu file code trên đĩa khác mốc đó khi một
  thí nghiệm bắt đầu, thí nghiệm bị từ chối; `code_changed_during_run` ghi các file bị sửa trong lúc thí nghiệm chạy.
  Commit trước khi chạy để `git_code_dirty` là `false`.
- **Thư mục output.** Script chỉ ghi vào thư mục mới hoặc thư mục có `ablation.json` của cùng bản xuất. Thư mục không
  rỗng khác, ví dụ một run có sẵn trong `runs/`, sẽ bị từ chối; thư mục con nằm trong bản xuất, trong một run (có
  `manifest.json`/`features_manifest.json`) hoặc trong một thư mục ablation khác cũng vậy.

**Kết quả.**

| File | Nội dung |
|---|---|
| `<thí nghiệm>/experiment.json` | Định nghĩa, hash bản xuất, số dòng giữ/bỏ theo tập và nhóm, ngưỡng và `threshold_constraint_met` từng model, model được chọn, hash dòng test và điểm, môi trường lúc bắt đầu (phiên bản, hash code, commit, `git_code_dirty`), `code_changed_during_run`, thời gian |
| `<thí nghiệm>/test_overall.csv`, `test_by_group.csv`, `test_by_source.csv`, `validation_results.csv` | Chỉ số trên test của 9 model: tổng thể, theo nhóm, theo Source; các ứng viên trên validation |
| `<thí nghiệm>/test_scores.npz` | Điểm của 9 model trên test (không lưu model, để tiết kiệm khoảng 1 GB mỗi thí nghiệm) |
| `overlap_by_group.csv` | Cụm gần trùng vắt qua hai nhóm, theo cặp và theo tập: số cụm, cụm cùng nhãn, cụm lẫn nhãn (hai nhóm của cặp khác lớp), `clusters_with_both_labels` (cụm có cả hai lớp, kể cả do nhóm thứ ba), số dòng |
| `summary_overall.csv` | Tổng thể theo hai phạm vi, `all` và `without_epvme`, kèm `delta_*` so với `reference` cùng họ classifier (dòng của chính `reference` để trống) |
| `summary_by_group.csv` | Theo nhóm: TP/FP/FN/TN, `Rate` (recall với nhóm dương, FPR với nhóm hợp lệ), `Pair-ROC-AUC`/`Pair-AP`, `held_out`, `delta_*` |
| `summary_fixed_classifier.csv` | Cùng họ classifier mà `reference` chọn |
| `summary_cross_source.csv`, `heatmap_cross_source.png` | Ma trận recall: hàng là `reference` và `only_*`, cột là nhóm dương |
| `seed_spread.csv` | Min, max, độ lệch chuẩn qua 3 seed của `reference`, tổng thể và theo nhóm |
| `summary_nazario_by_cluster.csv` | Recall trên Nazario test, tách dòng nằm trong cụm có EPVME và dòng trong cụm thuần Nazario (kèm support). Với `without_nazario` và `only_epvme`, khoảng cách giữa hai số cho thấy bao nhiêu recall đến từ việc EPVME chứa body Nazario |
| `summary_epvme_by_attack.csv` | Recall trên EPVME test theo họ tấn công heuristic, kèm support (XSS chỉ có 102 dòng test) |
| `heatmap_{fixed,selected}_{recall,fpr}.png` | Độ chênh recall (nhóm dương) và FPR (nhóm hợp lệ) so với `reference`. `fixed` dùng họ classifier mà `reference` chọn. `selected` so model mỗi thí nghiệm chọn trên validation với model `reference` chọn (cột `delta_vs_reference_selected_Rate`) |

**Cách đọc kết quả.**
- **Cách gọi đúng.** Gọi kết quả là "đóng góp biên khi bỏ nhóm khỏi train/validation, trên tập test cố định", không phải "hiệu quả" tuyệt đối
  của dataset. Leave-one-out đánh giá thấp các dataset giống nhau (bỏ cái này thì cái kia bù), vì vậy cần đọc cùng
  `only_*` và ma trận chéo nguồn.
- **Lớp dương** là email độc hại: phishing, malspam và EPVME tổng hợp. Ở phishing mode, spam của CEAS, Ling,
  SpamAssassin, TREC và `Enron.csv` bị loại (`outside_label_scope`), nên các nhóm đó chỉ đóng góp email hợp lệ.
- **Mức nhiễu.** Đọc `seed_spread.csv` trước khi diễn giải độ chênh. Ba seed chỉ cho ước lượng thô, và tập test không
  đổi giữa các seed. Kích thước nhóm chênh nhau tới khoảng 100 lần: bỏ `enron` (143 nghìn dòng train) chủ yếu đo việc
  mất dữ liệu. Độ chênh nhỏ của một nhóm nhỏ không chứng minh nhóm đó vô dụng.
- **Ngưỡng.** Bỏ một nhóm làm đổi tỷ lệ lớp, nên ngưỡng chọn trên validation bị dời theo. Ví dụ bỏ `enron` đổi tỷ lệ
  hợp lệ:dương của train từ 4,7:1 thành 1,35:1, và của validation từ 5,1:1 thành 1,46:1. `Pair-ROC-AUC`/`Pair-AP` không phụ thuộc ngưỡng giúp tách hiệu ứng nội dung khỏi hiệu ứng ngưỡng. Mỗi
  nhóm chỉ có một lớp, nên được chấm cùng toàn bộ lớp còn lại của tập test: nhóm dương so với mọi email hợp lệ, nhóm
  hợp lệ so với mọi email dương.
- **Precision phụ thuộc tỷ lệ lớp của test.** Precision trên test là precision *tại tỷ lệ lớp của test*, không phải
  precision trong hộp thư thật. Test đầy đủ có 16,6% email dương; bỏ EPVME còn 8,6% (6.152/71.502), nên precision của
  MLP ở `reference` tụt từ 0,90 xuống 0,81 dù số FP không đổi. Phép tính (không phải kết quả đo) với recall 0,998 và
  FPR 2,24% của MLP:

  | Tỷ lệ email dương | Precision ước tính |
  |---|---|
  | 8,6% (test không tính EPVME) | ≈ 0,81 |
  | 1% | ≈ 0,31 |
  | 0,1% | ≈ 0,04 |

  Vì vậy FPR 2,24% là cao cho một bộ lọc thật, dù ROC-AUC đạt 0,9994. Khi báo cáo, dùng FPR và ROC-AUC/AP làm chỉ số
  chính. Một điểm vận hành khác (ví dụ ngưỡng chọn trên validation sao cho FPR ≤ 0,1%) tính lại được từ
  `test_scores.npz` và điểm validation mà không cần train; đó là phân tích riêng sau ablation, chưa có trong script.
- **FPR theo nhóm cần kèm support.** Ở `reference` (MLP), FPR của SpamAssassin là 6,5% (82/1.252) và của CEAS là 4,8%
  (161/3.359), so với Enron 1,7%. Tách SpamAssassin theo thư mục (chỉ 395 email thô còn giữ tên thư mục; 857 dòng từ
  `SpamAssasin.csv` thì không): `hard_ham` 15,1% (11/73), `easy_ham` 5,1% (16/313), `SpamAssasin.csv` 6,4% (55/857).
  `hard_ham` là thư hợp lệ được chọn vì giống spam, nên FPR cao ở đó phù hợp với giả thuyết này, nhưng 73 email là
  quá ít để kết luận. Với nhóm nhỏ (Ling 468, SpamAssassin 1.252 email test), độ chênh vài điểm phần trăm chỉ là vài
  chục email.
- **`threshold_constraint_met = False`** nghĩa là không có ngưỡng nào đạt precision 0,9 trên validation, nên model dùng
  ngưỡng dự phòng có F2 tốt nhất (`select_threshold`). Recall thấp của các thí nghiệm đó có thể do ngưỡng chứ không phải
  do dữ liệu. Điều này dễ xảy ra nhất với `only_malspam`: tỷ lệ dương:hợp lệ khoảng 1:59 trên train và 1:56 trên
  validation.
- **Họ classifier cố định.** "Cùng họ classifier" là cùng loại model mà `reference` chọn, tune lại grid trên validation
  của từng thí nghiệm, chứ không phải cùng một model.
- **Khử trùng lặp y hệt** (đọc từ `preprocess.py`, trước khi chia tập):
  - Các bản trùng y hệt mang nhãn khác nhau bị loại hết (`conflicting_labels`).
  - Bản trùng cùng nhãn được giữ một bản theo thứ hạng nhãn: hợp lệ/phishing/malspam, rồi `malicious_synthetic`,
    rồi spam. Cùng hạng thì giữ nguồn nạp trước, theo thứ tự `trec07p` → `phishing/` (Nazario và các CSV) →
    SpamAssassin thô → Enron thô → EPVME → Phishing Pot → malspam.
  - Vì vậy bỏ một nhóm không bỏ được các bản trùng y hệt của nó đã được tính cho nguồn khác.
- **Cụm gần trùng** (`group_email_variants`):
  - Cụm được gom không xét nhãn: cùng hash body đã chuẩn hóa, hoặc SimHash lệch không quá 3 bit.
  - Cụm lẫn nhãn được giữ nguyên, mỗi dòng giữ nhãn riêng, và cả cụm nằm trong cùng một tập.
  - Không có bước xử lý xung đột cho cụm gần trùng. Vì vậy mẫu EPVME có thể chung cụm, và chung tập, với email hợp lệ
    mà nó được dựng từ đó. `overlap_by_group.csv` đếm các trường hợp này. Các cặp `epvme × nazario/enron/spamassassin/trec`
    đứng đầu báo cáo. Một cụm vắt qua 3 nhóm được tính lẫn nhãn theo từng cặp.
  - Kết quả trên `runs/2026-11-08_features_v6`, tổng 3 tập:

    | Cặp nhóm | Số cụm | Loại cụm | Số dòng |
    |---|---|---|---|
    | `epvme × nazario` | 1.325 | cùng nhãn | 1.993 EPVME, 3.198 Nazario |
    | `epvme × enron` | 12 | lẫn nhãn | |
    | `epvme × spamassassin` | 16 | lẫn nhãn | |
    | `epvme × trec` | 79 | lẫn nhãn | |
    | **`enron × trec`** | **5.795** | cùng nhãn | 11.242 Enron, 8.777 TREC |

  - Chồng lấn lớn nhất là `enron × trec`, vì TREC 2005 được dựng từ thư Enron. Vì vậy `without_enron` vẫn train trên
    nội dung Enron qua TREC, và ngược lại; hai thí nghiệm này đo đóng góp phần riêng của từng nhóm.
  - `without_enron_trec` đo phần đóng góp chung của khối email hợp lệ dạng Enron.
  - 107 cụm lẫn nhãn, tổng 497 dòng trên cả 3 tập: `epvme × enron` 53, `× spamassassin` 98, `× trec` 346. So với
    khoảng 400 nghìn dòng thì đây là nhiễu nhãn nhỏ.
- **EPVME.** Nguồn: Exploiting Protocol Vulnerability Malicious Email, Zhang et al., *Cybersecurity* 8:14 (2025),
  DOI 10.1186/s42400-024-00309-6, github.com/sunknighteric/EPVME-Dataset, GPL-3.0. EPVME chiếm khoảng 61% mẫu dương
  của train, 57% của validation và 53% của test.
  - Đây là email tổng hợp: From/To/Subject/body được lấy ngẫu nhiên, theo từng loại tấn công, từ mẫu lành tính hoặc độc
    hại của Enron, Nazario, SpamAssassin và TREC07. Không có bảng ánh xạ nguồn cho từng mẫu.
  - Payload gồm giả mạo SPF/DMARC, thao túng chữ ký S/MIME/OpenPGP, và XSS từ Wooyun Email XSS.
  - Mọi mẫu gán nhãn malicious, không phải phishing thuần.
  - Hệ quả:
    - (a) Bỏ một nhóm không bỏ được nội dung của nhóm đó nằm trong EPVME. Ví dụ, `without_nazario` vẫn còn body
      Nazario qua EPVME.
    - (b) Kết quả `only_epvme` trên Nazario phải đọc cùng `overlap_by_group.csv`.
    - (c) EPVME có thể mang body spam với nhãn dương, không nhất quán với việc phishing mode loại spam. Vì vậy dòng
      tổng thể `without_epvme` là con số chính khi nói về phishing thật.
    - Lưu ý về dòng `without_epvme`: ngưỡng của nó vẫn được chọn trên validation có EPVME (57% mẫu dương). Precision
      0,9 trên validation vì thế không đảm bảo precision tương ứng trên phishing thật. Với phạm vi này, nên ưu tiên
      ROC-AUC/AP, vốn không phụ thuộc ngưỡng.
  - **Mẫu XSS** (kiểm tra trên `runs/2026-11-08_features_v6`):
    - 5.871/6.171 dòng XSS heuristic của train (khoảng 95%) nằm trong một cụm gần trùng 6.011 dòng. Cụm còn có 138 dòng
      `unattributed` và 2 dòng `from_injection`. Validation có 100 và test có 102 dòng XSS heuristic, nên khả năng
      phát hiện XSS gần như không được đo trên test.
    - Cụm đó là một template: body luôn là "This is a test mail for XSS." (text sau làm sạch: `test mail xss`).
      Payload XSS nằm trong header `From`/`Subject`, không nằm trong markup của body.
    - Không feature nào trong 36 feature HTML/script (`HTML_SECURITY_FEATURE_NAMES`, `HTML_PAYLOAD_FEATURE_NAMES`) bật
      trên cụm này. Feature header `hdr_markup_in_headers` bật trên 99,9% cụm và 0% email hợp lệ của train. Vì vậy với
      XSS, Doc2Vec chủ yếu thấy câu template, còn feature thủ công thấy payload qua header.
    - Họ tấn công (`attack_family`) là heuristic của `load_data.py`, không phải nhãn gốc của dataset. Tổng khoảng 6.373
      dòng XSS theo heuristic khác với 4.716 mẫu XSS trong Table 2 của bài báo (theo số liệu nhóm đọc từ bài báo).
      Không báo cáo con số heuristic như số mẫu XSS thật.

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
train, còn bản ở gốc luôn là LF (`.gitattributes` ở gốc đặt `eol=lf`, như blob upstream), nên run train ở gốc có
chữ ký khác run đang pin. Muốn web dùng run khác thì chép nguyên byte
hai file đã train run đó vào `web/backend/frozen_pipeline/`, đóng gói và pin run mới, tạo lại fixture test
(`web/backend/tests/build_fixture.py`) và chạy test web backend.

## Kiểm tra

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Tài liệu khác: [docs/DATA_PIPELINE_REVIEW.md](docs/DATA_PIPELINE_REVIEW.md). Upstream còn nhắc
`SPECIALIST_PIPELINE.md` và `PIPELINE_VALIDATION.md` nhưng chưa công bố hai file này.
