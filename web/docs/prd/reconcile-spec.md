# SPEC Input Reconciliation

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

Date: 2026-10-05. Verdict: **PASS — no load-bearing gaps or contradictions found.**

## Compared inputs

Read `SPEC.md`, `api-and-experience.md`, `model-and-inference.md`, `deployment-and-acceptance.md`, `brownfield-and-evidence.md` from `_bmad-output/specs/spec-iap-web-application/` and the adopted root `AGENTS.md`; compared them with this folder's `prd.md` and `addendum.md`.

The PRD's document purpose adopts the SPEC companions, and the addendum explicitly retains the SPEC and **all** companions as the complete implementation contract without superseding them. Details preserved by that adoption do not need to be duplicated in the product requirements.

## Capability coverage

| Input capability | PRD coverage | Reconciliation |
| --- | --- | --- |
| CAP-1 — Single exported email | FR-1, FR-2, A1 | Selection/drop, filename/size/export guidance, nonempty suitable `.eml`, whole-file bounds and rejection before inference retained. |
| CAP-2 — Eligible binary classification | FR-3, FR-4, glossary, FR-9 | Exact `legit`/`phishing`, reviewed target, filename identity, errors without labels and fixtures distinguished from real inference retained. |
| CAP-3 — Processing and recovery | FR-4 through FR-6, NFR-5 | Readable states, cold startup, bounded retry, duplicate/stale-response prevention and failure recovery retained. |
| CAP-4 — Readiness and attribution | FR-7, NFR-1/NFR-2, addendum baseline | Live/ready distinction, unsuitable-release blocking, release trace, server-side authentication and private logs retained; exact routes/schema/readiness 503 retained in addendum/adopted API companion. |
| CAP-5 — Reproducible eligible release | FR-8, FR-9, NFR-4, dependencies | E0 provenance, coherent same-run artifacts/dimensions/configuration, real inference, target-specific evaluation, resource evidence and repeatability retained. |
| CAP-6 — Demonstration and handover | FR-10, success measures, delivery dependencies | Measured free path or declared fallback, meaningful checks, warm/cold measurements, restart-safe release, tested local Docker demo and local/deploy/rollback guidance retained. |

## Invariants and retained detail

The PRD/addendum preserve the reviewed legitimate-versus-phishing target, default exclusion of ordinary spam/unknown positives, no display-label conversion of mixed positives, E0 dependency and clearly marked samples. Raw MIME extraction before cleaning, ordered features, fitted scaler/Doc2Vec, concatenation order, one same-run classifier, no request training/evaluation/downloads and actual width verification are retained directly or through the adopted model contract.

Transient email/session results, restricted operational logging, safe parsing without HTML/URL/attachment execution or fetching, cleanup on success/failure, backend-verified server credentials, bounded MIME/processing/retry/concurrency and Python-side timeout behavior remain required. Full manifest fields, artifact verification, positive-score ROC-AUC, validation/test separation, RNG/vector parity, Windows corpus handling, source-bias pitfalls and existing pipeline commands remain adopted through the explicit references.

E0–E5 dependencies and conditional windows, measured hosting/fallback selection, provider/account re-verification and handover checks remain intact. Historical ZIP/metrics claims remain distinct from current metadata and from verified E0 evidence. Non-goals and the limits on Vietnamese accuracy, phishing-only metrics, XAI and RQ2/RQ3 claims remain intact.

## Assumptions and open questions

- **A1/A2/A3/A5:** 2 MiB whole-file limit, approximately 400 MiB peak RAM, conditional 15-working-day estimate and proposed implementation stack retain their provisional status. Future hosting remains unspecified and unqualified.
- **A4:** Workstream owners are explicitly a planning assumption pending individual assignments, not claimed source evidence.
- **Q1:** Dataset snapshot, per-source provenance and retraining need remain unresolved.
- **Q2:** Release/environment/inference/source revision remain unresolved. Added model-quality acceptance criteria are also explicitly unresolved; no numeric quality target is asserted.
- **Q3:** MIME policy, parser caps and exact errors/status mappings remain unresolved; referenced HTTP suggestions are not promoted to final decisions.
- **Q4:** Warm/cold budgets, Python/proxy deadlines, retry and vector tolerance remain unresolved; no invented latency/throughput target appears.
- **Q5:** Measured free host, account eligibility/quotas and public-demo access/rate controls remain unresolved.

Generic participant/team roles and the source-described session are qualified as supplied activities rather than interviewed/named personas. Fixture completion and integrity measures operationalize existing acceptance behavior; they do not claim achieved results or model accuracy.

## Gaps and scope of verdict

**Gaps: none.** No required correction to `prd.md` or `addendum.md` was identified against this input contract. This is document reconciliation only: no model/artifact verification, application checks, provider verification or E0 sign-off was performed, and no memlog was accessed.
