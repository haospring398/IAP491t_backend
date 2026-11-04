# Email analysis frontend

Next.js App Router, TypeScript and Tailwind application adapted from the supplied
Mailguard upload surface. It is a single English Analyze page with five states.
Selecting a file sends nothing; Analyze sends exactly one nonempty `.eml` of at
most 2 MiB. Success displays the captured filename and Legit, Phishing (run
`target_mode: phishing`) hoặc Spam / phishing (run `broad`) theo run backend đang phục vụ.
The separate real Python service is in the sibling `../backend/` folder.

## Local run

Node 24.x is required (verified locally with 24.19.0); use `npm.cmd` in PowerShell.
From the project root:

```powershell
cd web/frontend
npm.cmd ci
Copy-Item .env.example .env.local
npm.cmd run dev
```

Open `http://127.0.0.1:3000`. The app binds loopback locally. Leave backend variables
unset when no service is available: Analyze returns MODEL_UNAVAILABLE with no
classification. Refresh clears in-memory file/results. Follow
[backend setup](../backend/README.md) to start the actual startup-pinned run.

Configure **server-only** `ML_API_URL` (base URL, HTTPS for cloud or loopback HTTP
for a local service) and `ML_API_TOKEN` in `.env.local` or the shell, matching the
Python-service token. Do not use NEXT_PUBLIC variables. The proxy sends Bearer credentials
only server-side, rejects redirects, and forwards canonical `message.eml` without
the original filename. Separate local/preview/production endpoints and secrets;
preview must not inherit production credentials.

## Service handover requirements

The separately configured service must enforce release/readiness verification,
server Bearer authentication, the shared schemas/policy under `../contracts/`,
one serial no-queue analysis slot, safe MIME parsing, deadline termination/reap,
transient cleanup and sensitive-log exclusion. Required routes are authenticated
`POST /v1/analyze` and `GET /v1/analysis-status?request_id=<uuid>`, plus the planned
liveness/readiness endpoints. Every analysis/status reply must carry the matching
X-Request-ID; exact success is completed plus declared lowercase legit,
spam_or_phishing or phishing. Model nhị phân trả `legit` và một nhãn dương theo target
của run; [ngoại lệ local](../docs/spec/local-demo.md) cho phép trả `phishing` dựa trên
bằng chứng validation trong khi E0 phishing-only vẫn đang chờ. Errors
use the canonical code/message/request_id envelope and matching HTTP map.

The proxy has a 150s budget including body consumption, and replaces client
deadlines with trusted X-Analysis-Deadline. The browser budget is 165s. These
application deadlines remain enforced during local operation. Status polling is
non-overlapping every 2s, at most 75 polls, with 3s poll deadlines. Poll failures
fall back to generic Analyzing; terminal POST alone determines the outcome.

Retries are manual: at most two per unchanged selected file after failure, with
shared 5s or 10s cooldown. Analyze cannot bypass that allowance. Input failures
require replacement. Timeouts invalidate browser identity without promising
immediate server cancellation. The service must enforce its own trusted deadline.

## Verification

```powershell
npm.cmd run contracts:check
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
npm.cmd run test:integration
npm.cmd run test:real-model  # Full parent repository + local model environment required.
npx.cmd playwright install chromium
npm.cmd run test:browser
```

If Edge is already installed, skip the Chromium download and set
`$env:PLAYWRIGHT_CHANNEL = 'msedge'` before integration/browser commands.
For installed Chrome use `chrome` instead.

Playwright starts the production frontend on loopback port 3100 with backend
configuration empty. Browser fixtures explicitly intercept responses and insert
"Sample result — not a real analysis" into the test page. No production fixture
flag, alternate response shape or synthetic classifier exists. These tests prove
UI/contract/error boundaries; they do not prove ML inference, model quality or E0.
Unit tests cover schemas, consumed upload bounds, proxy correlation/auth/deadline,
normalization and attempt/retry/stale/progress behavior. Browser traces/screenshots
are local test artifacts, not retained email history.

`test:real-model` starts the real local Python model service and production
Next server, uploads five MIME cases in the browser, compares actual API/proxy
responses and checks service-down clearing. Test này chạy `python -m backend` từ `web/`,
lấy trình thông dịch từ biến `IAP_WEB_PYTHON` nếu có, nếu không thì `web/.venv`, rồi tới
`.venv` ở thư mục gốc repository; nếu không có cái nào thì test báo lỗi rõ ràng. Nó cần run
đã đóng gói trong `web/model/` (hoặc `IAP_WEB_RUN_PATH`).
The frontend-only `test:integration` uses a hermetic loopback HTTP
backend fixture's marked sample verifies actual route configuration,
multipart serialization, canonical filename, server bearer, trusted deadline and
status correlation. Fixture checks do not establish real inference. Production test
runs require `npm.cmd run build` first. For focused source checks without rebuilding,
set `$env:FRONTEND_TEST_DEV="1"` before integration/browser commands, then remove
that test-only option with `Remove-Item Env:FRONTEND_TEST_DEV`; it selects Next dev
only in the test harnesses. Production application behavior has no fixture switch.

## Build and hosting handover

Pinned seed: Next 16.3.8, React/React DOM 19.2.8, TypeScript 5.9.3, Tailwind and
PostCSS plugin 4.3.3. `package-lock.json` records resolved dependencies. Build with
`npm.cmd run build`; start locally with `npm.cmd start` after configuring `.env.local`.
This implementation uses an explicit manual scaffold with App Router, ESLint,
TypeScript, Tailwind, no `src/` directory, no React Compiler, and alias `@/*`.

Keep `web/frontend/` (or `frontend/` in a standalone web workspace) and its sibling
contracts in the same checkout. Keep Python/corpora/model artifacts outside the
frontend build. Hosting is unspecified. Any future host must provide backend
reachability, server-only environment secrets, access protection and measured
warm/cold/upload/deadline/privacy behavior. Roll back frontend/schema/policy with
the compatible qualified backend release.

Local real inference and bounded operational behavior are tested separately from
pending E0 target/provenance, quality qualification, cloud access protection and
deployment acceptance. The legacy mixed spam/phishing release cannot be renamed
as phishing-only inference. Upgrade and roll back the whole compatible release.

Adapted MIT source attribution is in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
and [LICENSE](LICENSE).

The complete shareable web workspace is now under `web/`: this frontend,
the sibling `backend/` and `contracts/`, and linked handover snapshots in `../docs/`.
See [web workspace instructions](../README.md) before copying it to another developer.
