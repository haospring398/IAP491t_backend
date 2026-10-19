# Prepared inference release: 2026-10-10

The model archive is provided separately and is not stored in Git. Deploy this source with the matching archive, following [DEPLOYMENT.md](DEPLOYMENT.md).

| Field | Value |
| --- | --- |
| Archive | `iap-inference-20261010.tar` |
| Bytes | `307046400` (292.82 MiB) |
| Run | `e7dcdcc3551e46fc93582836f4a74976` |
| Source manifest SHA-256 | `5407b0aac9118f8f0611205c7d84d773bd0af74f7107459d5ee2c37a19ec11bb` |

Set `MODEL_RELEASE_SHA256` to:

```text
1a5284c3c902aa45625dab0807cb32bdad9bed8eb595586efc43adb900d1bf00
```

The archive contains the unchanged source manifest, release provenance, Doc2Vec, scaler and XGBoost artifacts. The complete original training run was verified before export. Changing a bound runtime source/configuration/lock file requires a fresh export and matching digest.

Preparation uses Linux CPython 3.12.14 with the frozen `uv.lock`; 52 backend tests passed. All five original/cloud vectors and label envelopes matched. The cloud-profile API also passed five real-model uploads, correlation, readiness and invalid-token rejection using an offline pre-provisioned archive cache. That cached worker initialized in 2.634 seconds with peak RSS 812892 KiB; this excludes a real Blob download and Vercel infrastructure. The installed Linux dependencies occupy about 1020 MiB before Vercel-specific bundling, so enable the documented Large Functions profile and inspect actual build output.

Actual Vercel build, private Blob download, hosted readiness/recovery and frontend integration are pending dashboard deployment. Local evidence does not establish hosted acceptance or phishing-only model quality.
