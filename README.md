# IAP491t backend

Python FastAPI email-analysis service extracted from the current PhishingEmailDetection project. The frontend is published separately at [IAP491t_Web](https://github.com/haospring398/IAP491t_Web).

## Included source

- `web/backend/`: authenticated API, serial worker supervision, model adapter, API dependencies, regression tests and five synthetic MIME samples.
- `web/contracts/`: response schemas and the shared transport/deadline policy used by the frontend.
- `preprocess.py`: raw-email engineered features and text preprocessing required by the adapter.
- `artifact_store.py`: selected-run manifest, artifact hash and dimension verification.
- `requirements-ml.txt`: direct ML package versions observed in the existing native Windows Python 3.11 environment; this is not a transitive dependency lock or a qualified Linux/cloud release.

Model files, training/test artifacts, real email, datasets, tokens and virtual environments are excluded. The original project and its corpus/history are not copied into this repository.

## Local setup

Run commands from this repository root. Use Python 3.11:

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r web/backend/requirements-api.txt -r requirements-ml.txt
$env:ML_API_TOKEN = (.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
.venv/Scripts/python.exe -m web.backend
```

`ML_API_TOKEN` is a server environment variable; `.env` files are not automatically loaded. Copy the generated token locally to the frontend server configuration. Never commit the token or use a `NEXT_PUBLIC_` variable. The entry point binds `127.0.0.1:8000` with one worker and no access log. `--port` changes the local port.

Dependency installation alone does not provide a model. With missing artifacts the process can serve liveness, but readiness is HTTP 503 and analysis returns MODEL_UNAVAILABLE; there is no simulated inference fallback.

## Provision the matching trusted model release separately

The adapter is pinned to immutable run `e7dcdcc3551e46fc93582836f4a74976`. Preserve the original verified release and the pointer:

```text
dumped_models/classification/current.json
dumped_models/classification/runs/e7dcdcc3551e46fc93582836f4a74976/
    manifest.json
    data_X_test.npy
    data_y_test.npy
    model_dbow.pkl
    feature_scaler.pkl
    Logistic Regression.pkl
    Random Forest.pkl
    XGBoost.pkl
    SVM.pkl
    KNN.pkl
    Naive Bayes.pkl
    Decision Tree.pkl
    MLP.pkl
    AdaBoost.pkl
    Gradient Boosting.pkl
```

Use the original `current.json` selecting this run. The current verifier checks all 14 manifest-listed artifacts and matching test arrays; copying just the three inference pickle files is insufficient. Keep the whole release outside Git and provision it through administrator-controlled storage. Startup verifies hashes, class values, sample counts and dimensions before enabling analysis. Only trusted model artifacts may be loaded.

The actual classifier is XGBoost, with 100 Doc2Vec values followed by 40 same-run scaled engineered features. Labels are 0=legitimate and 1=spam_or_phishing; SpamAssassin spam is included in the positive class. Phishing-only accuracy has not been established. Legacy Doc2Vec inference uses the inherited one epoch and negative alpha/min_alpha; this export does not retrain or tune it.

## API and frontend connection

- `GET /health/live`: process alive, HTTP 200.
- `GET /health/ready`: HTTP 200 only after successful verified-model startup; otherwise 503.
- `POST /v1/analyze`: authenticated, exactly one `.eml` file in multipart field `file`, maximum 2 MiB.
- `GET /v1/analysis-status?request_id=<uuid>`: authenticated progress for the correlated request.

Authenticated requests use `Authorization: Bearer <token>`. Analysis requires a v4 UUID `X-Request-ID` and trusted epoch-millisecond `X-Analysis-Deadline`; the Next.js server proxy supplies these. Successful responses are exactly `{"analysis_status":"completed","label":"legit"}` or `{"analysis_status":"completed","label":"spam_or_phishing"}`. Errors/status and matching response IDs follow [the shared contract](web/contracts/README.md).

One authenticated analysis is admitted at a time, with no queue. Uploads stay in memory; the service does not fetch links/images or execute attachments. Input/MIME/token/deadline bounds and worker termination/recovery are shared with the frontend through the transport policy. No training or evaluation is run by requests.

For local frontend use, set server-only `ML_API_URL=http://127.0.0.1:8000` and the same `ML_API_TOKEN`. For a frontend hosted on Vercel, the separately hosted backend must have an HTTPS URL reachable from Vercel. A developer's localhost is not reachable from Vercel. Use separate preview/production tokens and endpoints.

This source publication is not a cloud deployment. Cloud packaging still needs a reproducible dependency environment, the complete trusted artifact release, a suitable HTTPS ingress/host binding and runtime startup/memory/deadline verification. The current convenience entry point deliberately binds loopback.

## Verification

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-WebRequest http://127.0.0.1:8000/health/ready
.venv/Scripts/python.exe -m unittest discover -s web/backend/tests -v
```

The full regression suite requires the verified model release and ML dependencies. Synthetic files under `web/backend/samples/` exercise MIME behavior, not expected prediction quality. Preserve preprocessing, dependencies, Doc2Vec, scaler, classifier, manifest and contracts as a coherent release when upgrading or rolling back.
