# Current-tech reality review — 2026-10-05

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

**Initial verdict: PASS with two handover corrections. Final targeted recheck: PASS, both corrections resolved.** No incompatible committed version, unsupported hosting certification, or claim of an installed/tested stack was found. This is an architecture research gate; it does not certify dependency resolution, model compatibility, deployment, or runtime performance.

Reviewed `ARCHITECTURE-SPINE.md`, `.working/frontend-hosting-research.md`, `.working/python-service-research.md`, and `.working/brownfield-audit.md`. Existing primary-source research was reused; new browsing resolved package peer/Python compatibility, exact CLI options, and the image tag. Read-only local checks queried standard-library metadata and Node; no project/ML imports, artifact loading, training, evaluation, installation, build, or deployment occurred.

## Findings

1. **The binding spine does not specify the exact starter profile.** Location: `ARCHITECTURE-SPINE.md`, Stack and Structural Seed. It pins create-next-app/Next.js 16.3.8 but leaves the scaffolding options in research prose. A builder using `--yes` can inherit saved preferences and obtain a different router, directory layout, linter, or React Compiler setting. Add a short binding profile: TypeScript, ESLint, Tailwind, App Router, default Turbopack, `@/*`, no `src/`, no React Compiler, npm, `frontend/` root. The versioned CLI supports explicit flags such as `--ts --eslint --tailwind --app --no-src-dir --no-react-compiler --use-npm --import-alias "@/*"`; it also supports `--skip-install` when scaffolding precedes the required exact dependency edits. Pin the emitted TypeScript/Tailwind ranges to the spine's exact choices before locking. This is a reproducibility/handover correction, not a demonstrated incompatibility. [Versioned CLI](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/create-next-app/index.ts), [versioned dependency generator](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/create-next-app/templates/index.ts).

2. **The research's hosting measurement profile is stale relative to the spine.** Location: `.working/frontend-hosting-research.md`, Provisional hosting gate. The research requires a “single-process container,” while AD-7/AD-11 choose an ASGI supervisor and a resident ML child. Replace that phrase with the selected supervisor-plus-worker container and explicitly include both processes, worker loading/replacement, and parent-owned upload/IPC storage in peak measurements. AD-12 already states the correct whole-container condition; retaining conflicting research instructions could lead implementation to qualify a smaller process arrangement than it deploys.

## Version and fit checks

| Commitment | Result |
| --- | --- |
| create-next-app / Next.js 16.3.8; React / React DOM 19.2.8 | The exact versioned generator selects React 19.2.8; Next's React peer range accepts it. [Generator](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/create-next-app/templates/index.ts), [Next package metadata](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/next/package.json). |
| Node target 24.21.0 LTS; Node 24.x | Existing research verifies the Node release and managed-major behavior; Next requires Node >=20.9.0. Local `node --version` remains v24.19.0, and the spine accurately calls 24.21.0 a target. [Next package metadata](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/next/package.json). |
| TypeScript 5.9.3; Tailwind / PostCSS plugin 4.3.3 | Existing official release research supports the pins. They stay in the generator's `^5` and `^4` major ranges. The research distinguishes TypeScript 7.0.2's current release from the chosen starter-compatible 5.x line. Full resolution/build remains pending. [Generator](https://raw.githubusercontent.com/vercel/next.js/v16.3.8/packages/create-next-app/templates/index.ts). |
| Python 3.11.17-slim-bookworm | Official Images lists this exact tag and amd64 support. A build must still record the resolved digest. [Official Images definition](https://raw.githubusercontent.com/docker-library/official-images/master/library/python). |
| FastAPI 0.142.2; Uvicorn 0.54.0; python-multipart 0.0.32 | Maintainer-published metadata confirms the versions and Python >=3.10 requirements, covering 3.11. This establishes interpreter fit only; transitive resolution and ML serialization compatibility remain E0/E2 evidence. [FastAPI](https://pypi.org/project/fastapi/0.142.2/), [Uvicorn](https://pypi.org/project/uvicorn/0.54.0/), [python-multipart](https://pypi.org/project/python-multipart/0.0.32/). |
| Hosting | Unspecified after the cleanup. Future hosting requires resource, startup, access, request-size and deadline qualification; local checks certify only their observed local behavior. |

The local Python metadata exactly matches the audit's 3.11.2 Windows interpreter and listed ML distributions; core distributions resolve into the sibling `venv/Lib/site-packages`. FastAPI, Starlette, Uvicorn, and python-multipart are absent. `requirements.txt` remains unpinned. These observations support AD-11's self-contained Linux-lock requirement and do not establish the serialized run's original training environment.

The spine correctly distinguishes a researched seed from a built stack, model qualification from fixture acceptance, managed Node majors from exact local targets, and cloud acceptance from local fallback. No further current-tech blocker was found.

## Targeted recheck after reconciliation patches

**Final verdict: PASS — no open current-tech findings.** The complete available spine and the changed hosting-gate paragraph were reread on 2026-10-05. Version pins did not change, so the source compatibility evidence above remains applicable; no redundant browsing, installation or build was performed.

- Finding 1 is resolved by the binding Starter options convention: exact create-next-app 16.3.8, TypeScript, ESLint, Tailwind, App Router, `@/*`, no `src/`, no React Compiler, and a retained actual-resolution lockfile. Those selections match the previously inspected versioned CLI/template APIs.
- Finding 2 is resolved: the research now requires the proposed supervisor-plus-ML-child container and whole-container cold/steady/request measurements including both processes and temporary buffers. AD-12 retains the explicit unmeasured free-host gate.
- The deadline profile keeps backend < proxy < browser with trusted deadline propagation, bounded kill/reap and clock-skew qualification. Multipart parsing belongs to the killable child while the parent owns cleanup storage. Neither Uvicorn keep-alive nor client timeout substitutes for terminating ML work.
- The final bounded Retry policy now covers invalid upstream responses/internal errors and shares the unchanged-file count across Retry/Analyze. The separate phase channel uses supported HTTP/Route Handler APIs and keeps classification success unchanged; it makes no measured latency, provider cold-wake phase, or cancellation promise.

The architecture remains a draft researched substrate. Exact dependency resolution, trusted model/environment parity, temporary cleanup, repeatability, resource fit, account/tier access protection and actual local/cloud acceptance still require their stated evidence gates.
