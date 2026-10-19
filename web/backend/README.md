# Real-model email analysis service

See the repository [README](../../README.md) for setup, model provisioning, API routes, verification and the limits of this source-only publication.

Run `python -m web.backend` from the repository root. Shared schemas and transport policy are in [../contracts/](../contracts/README.md).

Wait for `/health/ready` to return HTTP 200 before the first Analyze. HTTP 503
while the verified worker is starting is expected; retry the readiness check. If
it stays unready, inspect the backend startup log and token, shared-policy and
trusted-model configuration before restarting. Liveness alone does not mean the
worker is ready.
