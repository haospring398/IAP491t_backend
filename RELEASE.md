# Prepared CPU inference release: 2026-10-13

Deploy this source with the new CPU-profile archive using [DEPLOYMENT.md](DEPLOYMENT.md). The preceding full-package archive does not match this code/lock; keep it with its old deployment for rollback.

| Field | Value |
| --- | --- |
| Archive | `iap-inference-20261013-cpu.tar` |
| Bytes | `307046400` (292.82 MiB) |
| Run | `e7dcdcc3551e46fc93582836f4a74976` |
| Source manifest SHA-256 | `5407b0aac9118f8f0611205c7d84d773bd0af74f7107459d5ee2c37a19ec11bb` |

Set `MODEL_RELEASE_SHA256` to:

```text
82af34716d7efdfe54d2af5d874ce09a46d8c1617071fd59c8ba182de0c5869f
```

The model files and source manifest are unchanged. The archive's code/dependency provenance was regenerated for `xgboost-cpu==3.2.0`; changing a bound source/config/lock needs another matched export. Models and credentials remain outside Git.

Linux CPython 3.12.14 frozen CPU dependencies occupy 306692508 bytes (292.48 MiB without bytecode, including test dependencies), with neither full XGBoost nor NCCL installed. This targets the standard 500 MB Python bundle; actual Vercel build size still needs observation.

The final 64-test backend suite passed, including observation-mode failure handling, explicit full-reference enforcement and virtual-environment interpreter preservation. Five full-XGBoost/CPU observations matched exactly in separate environments, including every vector hash and result envelope, and matched the independently captured pre-change reference. The cached cloud API passed five real-model uploads, correlation, readiness and wrong-token rejection. Cached initialization was 2.286 seconds, child peak RSS 797916 KiB; this excludes a real Blob download and Vercel infrastructure.

Actual Vercel build, private Blob download, hosted readiness/recovery and frontend integration remain pending dashboard deployment. Local evidence does not establish hosted acceptance or phishing-only model quality.

The independent pre-change observation is published at [full-XGBoost reference](web/backend/tests/fixtures/full-xgboost-reference-20261012.json), captured from source revision `3ba6c3d90eb67117d179fe3e3a6781ebaf5693e2` before the CPU changes. Its SHA-256 is `39eebe1c3aadc43b004f44ea3cbf2e3ea7eee0a7b6a7f1fd682dc1d586f72554`; it contains only synthetic sample observations and runtime metadata.
