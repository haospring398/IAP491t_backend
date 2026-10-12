# Vercel dashboard deployment

This prepares the existing mixed-target demo. Its positive label is `spam_or_phishing`, including SpamAssassin spam; it does not establish phishing-only model quality. No training, evaluation/report regeneration or selected-pointer update is part of deployment.

## 1. Use the published backend source

In Vercel, choose **Add New → Project**, import the dedicated `IAP491t` backend repository, select its `main` branch and keep the root directory at the repository root. Let Vercel detect **FastAPI**. The discovery entrypoint is `app.py`, which imports `vercel_app.py`; the local `python -m web.backend` entrypoint is for loopback use.

The committed `.python-version` and `requires-python` pin Python 3.12. Runtime dependencies are defined in `pyproject.toml` with the transitive `uv.lock`; use the automatic Python dependency installation. Leave build/output overrides unset. The runtime config sets a 180-second function limit and excludes exports, models, datasets, environments, tests and sample files. [Python runtime documentation](https://vercel.com/docs/functions/runtimes/python), [FastAPI discovery](https://vercel.com/kb/guide/ship-a-fastapi-app-on-vercel).

Check **Fluid Compute** in Project Settings → Functions after creating the project. The Linux ML dependency bundle may exceed the standard Python bundle limit even with models excluded. Vercel documents automatic Large Functions beta enrollment for new projects, supporting up to 5 GB with Fluid Compute. **Do not add `VERCEL_SUPPORT_LARGE_FUNCTIONS` in the New Project environment form**: that form rejects the system-managed name. For this new-project flow, remove that row and deploy using the automatic enrollment. Inspect the build's actual bundle-size/runtime evidence. Vercel documents a separate opt-in for existing projects; follow its platform prompt if an older project hits the size limit rather than forcing a rejected variable into this form. If the account cannot support the required resources within its existing plan, resolve that account prerequisite before deploying; this setup never changes a billing plan. [Large Functions announcement](https://vercel.com/changelog/vercel-functions-can-now-be-up-to-5-gb-in-package-size), [Fluid Compute](https://vercel.com/docs/fluid-compute).

An initial deployment without release configuration serves liveness but remains unready. Finish provisioning and redeploy before connecting the frontend.

## 2. Prepare or obtain the verified archive

Use the handover's archive path and SHA-256 if an export has already been prepared. To make a fresh export, run from this source checkout using the trusted original environment:

```powershell
& 'C:/path/to/original-project/.venv/Scripts/python.exe' scripts/export_release.py `
  --source-run 'C:/path/to/original-project/dumped_models/classification/runs/e7dcdcc3551e46fc93582836f4a74976' `
  --output 'C:/private-release-storage/iap-inference-unique-release.tar'
```

Keep the printed `sha256`, byte size and `source_manifest_sha256` with the deployment evidence. The exporter verifies all original manifest hashes and test counts/schema, loads the trusted models to check types/dimensions/settings, then publishes atomically. Partial or corrupt source cannot publish a release. It refuses to replace an existing output and never changes `current.json`.

Before uploading, verify the original/cloud vectors and exact labels on all five synthetic MIME samples in separate seeded children:

```powershell
& 'C:/path/to/original-project/.venv/Scripts/python.exe' scripts/verify_release.py `
  --source-run 'C:/path/to/original-project/dumped_models/classification/runs/e7dcdcc3551e46fc93582836f4a74976' `
  --archive 'C:/private-release-storage/iap-inference-unique-release.tar'
```

Expect `"parity":"passed"` and `"sample_count":5`. Save the output with the source/archive handover. Export and parity require an environment matching the committed dependency lock; local parity is separate from hosted acceptance.

The archive contains `release.json`, the unchanged original `manifest.json`, `model_dbow.pkl`, `feature_scaler.pkl` and `XGBoost.pkl`. Its uncompressed streaming TAR avoids holding an archive and extracted model together in ephemeral storage. Download/extraction is capped at 384 MiB; metadata is capped at 1 MiB per file. Cache recovery rechecks artifact hashes and reconstructs the canonical archive digest, binding all provenance back to the configured pin. URLs must be private Blob HTTPS URLs without query strings; redirects are refused.

Every release records canonical UTF-8/LF code hashes, runtime package versions, feature names and inherited inference settings. Runtime checks the installed transitive dependency closure against the pinned lock, including platform markers. Changing any bound source/config/lock file requires a fresh export paired with that source deployment. The original manifest digest seeds inference, so packaging does not change predictions. Preserve the original one epoch and negative alpha/min_alpha; do not tune them during deployment.

## 3. Upload through a private Blob store

In the backend project's **Storage** tab, create a **Blob** store with **Private** access and connect the correct Preview/Production environment. Keep the provided `BLOB_READ_WRITE_TOKEN` on the backend server. In the store's file browser, upload the handover `.tar` file under a unique release pathname and copy its private URL. Do not overwrite previous releases or upload real email. Vercel's dashboard supports uploads; [Blob setup and dashboard operations](https://vercel.com/docs/vercel-blob), [private Blob access](https://vercel.com/docs/vercel-blob/private-storage).

If a large browser upload fails, the authenticated Vercel CLI offers this manual alternative; its current CLI must support private stores:

```powershell
# Read the store token into this session securely; do not commit or print it.
vercel blob put 'C:/private-release-storage/iap-inference-unique-release.tar' --access private --multipart
```

The CLI reads `BLOB_READ_WRITE_TOKEN` from your environment. The backend downloads the administrator-provisioned archive directly from Blob with authentication; no uploaded email controls a fetch URL. [Blob CLI](https://vercel.com/docs/cli/blob).

## 4. Set backend environment variables and redeploy

| Variable | Value |
| --- | --- |
| `MODEL_BLOB_URL` | Exact `https://<store-id>.private.blob.vercel-storage.com/<unique-release>.tar` URL |
| `MODEL_RELEASE_SHA256` | Exported archive's lowercase 64-character SHA-256 |
| `BLOB_READ_WRITE_TOKEN` | Connected private store's server token |
| `ML_API_TOKEN` | New unpredictable backend API token, also used by the frontend server proxy |

Use separate Preview/Production API tokens, endpoints and storage credentials. `ML_API_TOKEN` authenticates analysis; `BLOB_READ_WRITE_TOKEN` provisions models. Neither belongs in browser variables, Git, a request URL or screenshots/logs. Redeploy after adding environment variables. The model is pinned for the lifetime of a deployment worker; changing env/Blob contents is not a supported hot swap.

## 5. Verify the real HTTPS backend

Open `https://<backend>/health/live`: expect HTTP 200 with `{"status":"alive"}`. Open `/health/ready`: expect 503 while starting and 200 with `{"status":"ready"}` only after full validation/loading. Keep an authenticated analyze invocation active during cold provisioning: Vercel may pause background initialization after a health-only invocation returns. Health polling alone cannot prove background completion.

After successful startup, Vercel function logs contain one sanitized `Model worker ready` JSON record with the run/manifest/archive digests, Python/direct package versions, initialization seconds and child peak RSS when the platform supports it. Use that record for runtime provenance and resource evidence; it contains no URL, credential or email. Live readiness, uploads, startup latency, memory and recovery evidence remain pending until observed in the hosted deployment. Model-free import/local tests are not evidence that a cloud worker loaded.

Use a synthetic sample for the first authenticated request, with a v4 UUID and epoch-millisecond deadline 150 seconds ahead. For example in PowerShell:

```powershell
$requestId = [guid]::NewGuid().ToString()
$requestDeadline = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() + 150000
curl.exe --max-time 165 --silent --show-error `
  -H "Authorization: Bearer $env:ML_API_TOKEN" `
  -H "X-Request-ID: $requestId" `
  -H "X-Analysis-Deadline: $requestDeadline" `
  -F 'file=@web/backend/samples/plain.eml;type=message/rfc822' `
  'https://<backend>/v1/analyze'
```

Expect exactly `{"analysis_status":"completed","label":"legit"}` or the same envelope with `spam_or_phishing`. Repeat with all five synthetic MIME samples; these check inference compatibility, not accuracy. Missing/invalid/tampered provisioning must remain unready and must never return a class. Verify an incorrect API token is rejected, oversized email is bounded, and cold restart/recovery cannot change the release. Do not log email bodies or credentials. Vercel Deployment Protection, if enabled, must allow the authenticated frontend server to reach the backend; use Vercel's supported server-side protection configuration rather than publishing a secret in browser code.

Cold startup has at most 120 seconds; upload/startup share the original trusted 150-second proxy budget minus the cleanup/skew reserve. Model analysis still receives at most 60 seconds and can receive less after startup. Worker termination/reaping stays bounded before replacement; transient provisioning files are removed on failure/recovery. Cold download checks a 105-second budget with a 15-second socket limit; the supervisor enforces the hard startup deadline. Slow startup can legitimately produce `ANALYSIS_TIMEOUT` with the same request ID and no result.

## 6. Connect the frontend and preserve rollback

In the separately deployed `IAP491t_Web` frontend project's server environment, set `ML_API_URL=https://<backend>` and the matching `ML_API_TOKEN`. Do not add the Blob token to the frontend. Redeploy the frontend and test a real `.eml` through its normal upload flow. Record backend/frontend deployment URLs and coherent source/archive identities.

One analysis is admitted per instance, with no queue. Vercel may start many instances: admission is not a global lock, and status polling routed to another instance can return `unknown`. No durable shared progress or email retention is introduced.

Vercel documents only a 500 ms SIGTERM shutdown grace, which can preempt lifespan cleanup. Request-time worker recovery uses the shared bounded termination/reaping policy; interrupted provisioning leftovers are removed before the next load. Verify actual infrastructure shutdown behavior separately. [FastAPI startup/shutdown limits](https://vercel.com/docs/frameworks/backend/fastapi).

Keep the preceding successful backend deployment and its unique Blob archive. Roll back the source deployment and its matched release URL/digest/package lock together; restore the frontend endpoint/token pair if needed. Do not regenerate training artifacts or delete prior runs. If current live readiness/upload/recovery/frontend checks have not actually passed, report them as pending; a successful source build is not deployment acceptance.
