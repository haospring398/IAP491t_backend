# Web workspace

This folder contains the frontend, Python backend, shared contracts and documentation for
handover to another developer. Keep `frontend/` and `contracts/` together.

```text
web/
  backend/            Local Python API, inference adapter, samples and tests
  frontend/           Next.js application, server proxy, tests and MIT attribution
  contracts/          Runtime schemas and shared transport policy
  docs/               Linked snapshots of spec, UX, architecture and requirements
  scripts/            Đóng gói run vào model/ và làm mới bản chụp tài liệu
  model/              Run đã đóng gói (git bỏ qua, tạo bằng scripts/bundle-run.py)
```

## Run locally

Use Node 24.x. From the PhishingEmailDetection repository root:

```powershell
cd web/frontend
npm.cmd ci
Copy-Item .env.example .env.local
npm.cmd run dev
```

If you received `web/` as a standalone folder, enter its `frontend/` directory
instead. Open `http://127.0.0.1:3000`. Để dùng model thật cục bộ, làm theo
[hướng dẫn Python service](backend/README.md): từ `web/` (kể cả bản chép riêng) tạo
`.venv`, cài `backend/requirements.txt` và chạy `.venv/Scripts/python.exe -m backend`
(hoặc chạy `python -m web.backend` từ thư mục gốc project như trước), rồi cấu hình cho
frontend `ML_API_URL=http://127.0.0.1:8000` (chỉ phía server) và cùng `ML_API_TOKEN` đã
sinh. Empty configuration returns an
unavailable error with no classification. Demo hiển thị Legit, hoặc Phishing (run
`target_mode: phishing`) / Spam / phishing (run `broad`), kèm thông báo rằng độ chính
xác phát hiện phishing chưa được đánh giá độc lập. Backend cần một run schema 2 đã train
(hiện là run upstream baseline_v6; xem `RUN_PATH` trong hướng dẫn backend).
See [frontend instructions](frontend/README.md) for checks and service boundaries.

The frontend's bundler and tracing root resolve to this `web/` folder, so its
build excludes the parent Python pipeline and corpora. Relative imports resolve
the sibling schemas regardless of whether the whole repository or only `web/`
is copied. The frontend source root is `web/frontend/` in this repository,
or `frontend/` in a standalone web workspace; keep sibling contracts available.

## Share with another developer

Chép thư mục này nhưng bỏ các thư mục Python `__pycache__/` và `*.py[cod]`, `.venv/`,
`frontend/node_modules/`, `frontend/.next/`, `frontend/test-results/`,
`frontend/playwright-report/`, `*.tsbuildinfo` và các file `.env*` cục bộ. Include `.env.example`, package files, schemas, source, tests and
MIT attribution. The recipient installs dependencies using `npm.cmd ci`. Giữ lại
`model/` (khoảng 1,2 GB cho run đang pin, tạo bằng
`python web/scripts/bundle-run.py --run runs/2026-11-02_baseline_v6` trong repository đầy đủ) để
backend chạy được mà không cần thư mục gốc; các thư mục run cũ trong `model/` (như
`2026-10-23_web2`, nay bị từ chối) và `model/nltk_data` không còn được dùng, nên xoá trước
khi chép. Người nhận tạo `.venv` bằng Python 3.11.16 (uv) và cài
`backend/requirements.txt`, như trong hướng dẫn backend. Clone từ git không có `model/` vì git bỏ qua
thư mục này: phải chạy lại script đóng gói (cần run gốc), nếu không backend sống nhưng
không sẵn sàng.

The [documentation index](docs/README.md) points to the current spec, UX and
architecture snapshots. They are handover references; canonical BMad documents
remain in the parent repository's `_bmad-output/`. After changing canonical
documents, refresh the snapshots from this repository:

```powershell
node web/scripts/sync-docs.mjs
```

The snapshot refresh requires the full PhishingEmailDetection repository;
it is not needed to build or develop the copied frontend. Bản chép `web/` gồm code
Python service, bản sao tiền xử lý đóng băng trong `backend/frozen_pipeline/`, run fixture
test commit sẵn trong `backend/tests/fixture_run/` và, nếu đã đóng gói, `model/`. Các module
pipeline khác ở thư mục gốc (`train.py`, `evaluate.py`, `artifact_store.py`), dữ liệu và môi
trường Python gốc vẫn nằm ở project cha; chỉ cần chúng khi train run mới, đóng gói run hoặc
tạo lại fixture (`backend/tests/build_fixture.py`). Chạy backend và test backend chỉ cần `web/` có
`model/` và `.venv` cài từ `backend/requirements.txt`. Local real-model operational tests are separate
from pending phishing-only E0 eligibility and future cloud deployment. Nhãn Phishing
của run đang pin là ngoại lệ local dựa trên bằng chứng validation, chưa qua E0.
