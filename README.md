# PhishingEmailDetection (bản mở rộng đầy đủ kỹ thuật)

Pipeline phân loại email phishing (Doc2Vec + đặc trưng kỹ thuật + 10 classifier,
thêm nhánh BERT) và web demo dùng model thật.

Code pipeline cập nhật theo bản **19-10** của repo
[buidangduy05/IAP491t_backups](https://github.com/buidangduy05/IAP491t_backups)
(commit `ae08251`), đã cập nhật tới commit `b535958` (23-10: Phishing Pot, khử
làm rối văn bản, feature link/payload tệp đính kèm cho nhánh specialist, bộ lọc 2
tầng `--target-mode broad` + `phishing_vs_spam`).

## Cấu trúc thư mục

```
PhishingEmailDetection/
├── load_data.py              # đọc Dataset/ (Nazario, CSV, SpamAssassin, Enron, EPVME, Phishing Pot, TREC 2007 thô)
├── preprocess.py             # làm sạch text + trích đặc trưng (FEATURE_NAMES)
├── pipeline_cache.py         # cache SQLite cho bước tiền xử lý, chạy song song
├── dataset_audit.py          # sổ đối soát ingestion (ingestion.sqlite, load_summary.json)
├── train.py                  # training: --mode specialists|baseline, --output <run-dir>
├── evaluate.py               # đánh giá: --run <run-dir>
├── predict_specialists.py    # dự đoán một email với các nhánh chuyên trách (--spam-stage: lọc 2 tầng)
├── benchmark_pipeline.py     # đo tốc độ cache tiền xử lý
├── analyze_feature_importance.py
├── download_nazario.py       # tải corpus Nazario về Dataset/phishing/
├── artifact_store.py         # xác minh run đã publish — web demo dùng
├── requirements.txt
├── tests/                    # test_pipeline.py (19-10), test_evaluate.py (artifact_store)
├── docs/                     # DATA_PIPELINE_REVIEW.md, IAP_Web_Application_Plan.md
├── Dataset/                  # dữ liệu gốc: enron/, phishing/, spamassassin/, phishing_pot/, trec07p/
├── runs/                     # kết quả từng lần train/đánh giá, mỗi lần một thư mục
│   ├── 2026-09-28_baseline/  # 10 classifier, Doc2Vec + 42 feature
│   └── 2026-10-19_bert/      # bổ sung BERT, chọn ngưỡng theo validation
├── dumped_models/
│   └── classification/
│       ├── current.json      # run mà web demo đang ghim
│       └── runs/<run-id>/    # model của web demo — không xoá/di chuyển
├── model/                    # model chọn để deploy (copy tay)
├── web/                      # frontend Next.js, backend Python, contracts, docs
├── paper/                    # tài liệu tham khảo
└── _bmad/, _bmad-output/, .agents/   # công cụ và tài liệu lập kế hoạch BMad
```

Mỗi lần chạy nên ghi vào một thư mục mới trong `runs/` (đặt tên
`YYYY-MM-DD_<mô-tả>`) thay vì ghi đè ra root.

## Cài đặt

```bash
cd PhishingEmailDetection
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -c "import nltk; [nltk.download(r, download_dir='.venv/nltk_data') for r in ('stopwords', 'wordnet', 'omw-1.4', 'punkt', 'punkt_tab')]"
```

Dữ liệu NLTK đặt trong `.venv/nltk_data` để chỉ ảnh hưởng project này (đã có sẵn bản
tải ngày 2026-09-22 ở `nltk_data/`, chép bằng `cp -r nltk_data .venv/nltk_data`; NLTK
không tự tìm thư mục `nltk_data/` ở gốc project). Khi có dữ liệu này, tiền xử lý dùng
stopwords của NLTK và bật lemmatization bằng WordNet; khi thiếu, code âm thầm chuyển
sang stopwords của sklearn và bỏ lemmatization. Hai cấu hình cho chữ ký tiền xử lý khác
nhau, nên lúc train và lúc chạy web phải dùng cùng một dữ liệu NLTK, nếu không web sẽ
từ chối run.

Nhánh BERT dùng `torch==2.10.0` và `transformers==4.57.6` (đã có trong
`requirements.txt`, cùng phiên bản với run `2026-10-19_bert`). Lệnh trên cài
torch bản CPU; nếu máy có GPU NVIDIA, cài bản CUDA trước:

```bash
.venv/Scripts/python.exe -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
```

Không cần BERT thì train với `--skip-text-training`.

`oletools` (có trong `requirements.txt`) dùng để phân tích macro VBA trong tệp đính
kèm; thiếu thì feature macro bị bỏ qua. Đọc QR code (`inspect_email_qr_codes`, chưa
dùng khi train) cần cài thêm `zxing-cpp` và `Pillow`; đọc QR trong PDF cần `PyMuPDF`.
Các gói này không có trong `requirements.txt`.

## Chạy

### TREC 2007 bản thô (`Dataset/trec07p/`, tuỳ chọn)

`TREC_07.csv` trong `Dataset/phishing/` là bản đã bỏ header và HTML (chỉ khoảng 0,04%
dòng còn thẻ HTML), nên mọi email hợp lệ từ CSV đều là văn bản thuần. Bản thô của
cùng corpus còn đủ header và HTML: 25.220 ham (17,1% là HTML) và 50.199 spam, đo ngày
2026-10-27. Bản này bổ sung email hợp lệ dạng HTML thật, giúp giảm thiên lệch của
feature `is_html`.

- Tải `trec07p.tgz` (ví dụ từ Kaggle `bayes2003/emails-for-spam-or-ham-classification-trec-2007`,
  nguồn gốc <https://plg.uwaterloo.ca/~gvcormac/treccorpus07/>), rồi giải nén để có
  `Dataset/trec07p/data/inmail.*` và `Dataset/trec07p/full/index`. Corpus chỉ dùng cho
  nghiên cứu.
- Spam trong corpus có email thật mang mã độc. Trên Windows, thêm thư mục
  `Dataset/trec07p` vào exclusion của Microsoft Defender **trước khi** giải nén, vì
  Defender có thể xoá file khi đọc. File có trong `full/index` nhưng thiếu trên đĩa được
  ghi vào `trec07p_missing_from_extract`.
- Khi có thư mục này, `TREC_07.csv` bị loại (ghi `excluded` trong sổ ingestion) để
  một email không xuất hiện hai lần dưới hai dạng mà dedup không nhận ra. Ham là lớp
  0. Spam mang nhãn `spam_or_phishing` giống CSV, nên bị loại ở chế độ `phishing` và
  không vào tầng 2.

```bash
# 1. Copy dữ liệu vào Dataset/ (xem README trong mỗi thư mục con)

# 2. Kiểm tra dữ liệu (không train)
python train.py --audit-only --output runs/2026-10-20_audit

# 3. Train (--target-mode phishing|broad|phishing_vs_spam, mặc định phishing)
python train.py --output runs/2026-10-20_<mo-ta>

# 4. Đánh giá
python evaluate.py --run runs/2026-10-20_<mo-ta>
```

> **Lưu ý:** các phần còn thiếu của bản 19-10 (`specialists.py`,
> `pipeline_cache.py`, `BertEmailClassifier`, `inspect_email_attachments`) đã
> được bổ sung. `docs/SPECIALIST_PIPELINE.md` (được `DATA_PIPELINE_REVIEW.md`
> nhắc tới) vẫn chưa có. Bản cập nhật 23-10 đổi `preprocess.py` và
> `pipeline_cache.py` ở thư mục gốc. Từ 2026-11-04 web demo phục vụ run upstream
> `runs/2026-11-02_baseline_v6` (134 feature; validation chọn MLP, web phục vụ XGBoost được
> pin để có explanation) bằng bản sao đóng băng của code
> upstream a202d55 đã train run đó (`web/backend/frozen_pipeline/`); pipeline gốc không đổi.

## Kỹ thuật phát hiện phishing (trong `preprocess.py`)

1. Content/NLP  2. URL-based  3. Header-based  4. HTML/structure
5. Attachment  6. Social-engineering

Số chiều và thứ tự feature lấy từ `preprocess.FEATURE_NAMES`; vector Doc2Vec
được ghép trước các feature kỹ thuật đã scale.

## Web demo

Web demo chạy model thật từ một run schema 2 ghim bằng `RUN_PATH`
trong `web/backend/policy.py` hoặc biến môi trường `IAP_WEB_RUN_PATH` (đường dẫn tương
đối tính từ `web/`), không train hay đánh giá lại. Run được đóng gói vào `web/model/`
(git bỏ qua) bằng `python web/scripts/bundle-run.py --run runs/2026-11-02_baseline_v6`
(bản sao đã kiểm hash của `runs/baseline_v6` upstream, cần `tldextract`, `magika` và
`oletools` theo `web/backend/requirements.txt`), nên thư
mục `web/` chạy được khi chép riêng. Làm theo
[web/backend/README.md](web/backend/README.md) để chạy
`.venv/Scripts/python.exe -m web.backend` từ thư mục này (hoặc `python -m backend` từ
`web/` với `web/.venv`), và cấu hình cùng token
server-only cho app Next trong [web/](web/README.md) (`cd web/frontend`,
`npm.cmd run dev`). Kết quả hiển thị Legit hoặc Phishing (run v6 có
`target_mode: phishing`). Python service và app Next chỉ bind loopback.

Web demo không dùng `preprocess.py` và `pipeline_cache.py` ở thư mục này mà dùng bản
sao đóng băng trong `web/backend/frozen_pipeline/` (đúng code đã train run đang pin),
và từ chối run có chữ ký tiền xử lý khác bản sao đó. Sửa hai file ở thư mục gốc không
ảnh hưởng web; muốn web dùng code khác thì lấy run schema 2 mới, chép nguyên byte hai file
đã train run đó vào `web/backend/frozen_pipeline/`, đóng gói và pin run mới, tạo lại
fixture test (`web/backend/tests/build_fixture.py`) và chạy test web backend.
