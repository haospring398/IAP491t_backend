# Frontend and hosting research

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

Access date: **2026-10-05**. Primary vendor documentation, official release repositories, and vendor-published npm metadata were checked. These are research findings and **provisional architecture recommendations**, not a stack commitment or a tested deployment. No installation, account action, deployment, training, or evaluation was performed.

## Version provenance and proposed seed

| Component | Verified current release / compatibility | Provisional exact seed |
|---|---|---|
| Next.js | **16.3.8**, marked Latest in the official release repository; September 30 security patch. [Release](https://github.com/vercel/next.js/releases/tag/v16.3.8) | `next=16.3.8`; pair `eslint-config-next=16.3.8`. |
| create-next-app | **16.3.8** in the official versioned package source and published npm package. [Package source](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/create-next-app/package.json), [published package](https://www.npmjs.com/package/create-next-app?activeTab=readme) | Invoke `create-next-app@16.3.8`, not a floating `@latest`. |
| Node.js | **24.21.0 LTS**; 22.x also LTS, 26.x Current, 20.x EOL. Next.js requires at least 20.9. [LTS release](https://nodejs.org/en/blog/release/v24.21.0), [release policy/status](https://nodejs.org/en/about/previous-releases), [Next requirements](https://nextjs.org/docs/app/getting-started/installation) | Local development target `24.21.0`; `engines.node="24.x"`. |
| React / React DOM | The versioned starter selects **19.2.8** for both. [Starter dependency generator](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/create-next-app/templates/index.ts) | `react=19.2.8`, `react-dom=19.2.8`. |
| TypeScript | Latest stable **7.0.2**; the current starter nevertheless emits `typescript: "^5"`. **5.9.3** is an official stable 5.x release. [Current release](https://github.com/microsoft/TypeScript/releases/tag/v7.0.2), [5.9.3](https://github.com/microsoft/TypeScript/releases/tag/v5.9.3), [starter source](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/create-next-app/templates/index.ts) | `typescript=5.9.3` initially, preserving the starter's major line. |
| Tailwind CSS | Latest stable **4.3.3**; the starter emits `tailwindcss: "^4"` and `@tailwindcss/postcss: "^4"`. [Release](https://github.com/tailwindlabs/tailwindcss/releases/tag/v4.3.3), [starter source](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/create-next-app/templates/index.ts) | Pin `tailwindcss=4.3.3`, `@tailwindcss/postcss=4.3.3`; lock the complete resolved tree. |

Starter defaults are TypeScript, ESLint, Tailwind, App Router, Turbopack, alias `@/*`, and agent guidance files. Its defaults do **not** enable React Compiler or a `src/` directory. Select flags explicitly, because `--yes` can reuse saved preferences. [Installation defaults](https://nextjs.org/docs/app/getting-started/installation), [versioned CLI source](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/create-next-app/index.ts)

TypeScript 7 is supported for `next build` through the project-local CLI, but its JavaScript compiler API differs and the CLI configuration is still described as experimental. This is a reason to retain the starter's TypeScript 5 line for the MVP, not a claim that TypeScript 7 is unsupported. [Next.js TypeScript guidance](https://nextjs.org/docs/app/api-reference/config/typescript)

Local evidence: repository search found no `package.json` or `package-lock.json`; **no installed project frontend dependency versions are established**. Read-only commands returned **Node v24.19.0** and **npm.cmd 11.17.0**. `npm --version` through `npm.ps1` was blocked by the existing PowerShell execution policy; `npm.cmd --version` worked. The recommended seed is therefore **source-verified, not locally built or tested**. Implementation must create and retain a lockfile, use `npm ci`, run type-check/lint/production build, and record the actual resolved versions before calling it a tested baseline.


## Fit for the one-page Analyze MVP

Provisional fit: one responsive root page, a small client upload/result component, and a Node Route Handler such as `/api/analyze` forwarding to the separate Python API. Keep model artifacts and inference in the Python deployment. Use `web/frontend/` as the source root and keep sibling contracts available; exclude Python corpora and artifacts from the frontend build. App Router Route Handlers support POST and standard request-body APIs, including FormData. [Route Handler documentation](https://nextjs.org/docs/app/api-reference/file-conventions/route)

Use a Route Handler for file upload. Server Actions default to a **1 MB entire request-body limit**, so an unchanged Server Action would reject the proposed 2 MiB file. [Server Actions body size](https://nextjs.org/docs/app/api-reference/config/next-config-js/serverActions)

Tailwind 4 targets Chrome 111+, Safari 16.4+, and Firefox 128+. Responsive mobile and desktop layouts fit this modern-browser scope; do not claim older-browser support without additional work. [Browser compatibility](https://tailwindcss.com/docs/compatibility)

## Runtime and future hosting requirements

The PRD’s approximately 400 MiB peak-RAM assumption remains a future, unqualified research target. It is not a memory cap or guarantee for the current local legacy demo, and no measurement is claimed.

The 2026-10-19 cleanup supersedes the earlier hosting selection. The current frontend and Python backend run locally; no provider is selected or certified. This update does not qualify unrelated product requirements, model quality or E0.

Enforce the 2 MiB file cap and bounded multipart consumption independently in browser, proxy and backend. Content-Length alone is insufficient. Application deadlines remain backend 60s, proxy 150s and browser 165s, with bounded worker startup and termination/reaping. Any future host must support these behaviors and measured whole-process memory, warm/cold startup, readiness, recovery and complete multipart transfer.

Store `ML_API_TOKEN` server-side and scope credentials per environment. [Next.js environment behavior](https://nextjs.org/docs/app/guides/environment-variables). Keep verified model/code/resources/policy together and preserve them over restarts. A remote frontend needs a reachable backend; developer localhost works only with a local frontend/proxy. Local checks do not certify future hosting.
