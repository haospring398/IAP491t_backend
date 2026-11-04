# Reconciliation: canonical SPEC package

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

2026-10-05. Compared [ARCHITECTURE-SPINE.md](ARCHITECTURE-SPINE.md) against [SPEC](../../../specs/spec-iap-web-application/SPEC.md), all four authored companions and the canonical [.memlog](../../../specs/spec-iap-web-application/.memlog.md). This is mandatory input reconciliation, not a code review or implementation acceptance. Spine/source documents were not edited.

## Preserved contracts

| Capability | Reconciled spine coverage |
| --- | --- |
| CAP-1 | AD-5/6/8 supply one multipart `.eml`, explicit Analyze, shared validation, no selection-time transmission and pre-inference rejection. Display size/export guidance are not explicit; see RS-2. |
| CAP-2 | AD-2/3/5/8 preserve eligible `0 → legit`, `1 → phishing`, same-run raw-feature/scaler/Doc2Vec/classifier contract, exact success labels/filename and no class on errors. |
| CAP-3 | AD-5/7/8 provide text-based truthful progress, attempt identity, duplicate/stale-response prevention and bounded manual recovery. |
| CAP-4 | AD-2/9/11 separate liveness/readiness, fail closed for unsuitable release/configuration/resources/target, and keep release attribution private. Busy capacity remains distinct from unready state. |
| CAP-5 | AD-2/3/4/11 preserve provenance, artifact integrity, inferred widths, locked environment and repeat/order/restart determinism. Explicit qualification/evaluation evidence needs the additions in RS-3. |
| CAP-6 | AD-9–12 preserve local Next.js/separate-Python path and unspecified future hosting, transient input, secrets, restart-safe model, immutable rollback and local fallback. Tested handover obligations need RS-4. |

The eligible target is not weakened: ordinary spam/unknown positives are excluded; existing mixed positives cannot be renamed; fixtures cannot satisfy E0 or real prediction. Original MIME extraction precedes cleaning, concatenation remains Doc2Vec then scaled engineered features, and artifact widths are derived rather than hardcoded. One worker/one active inference, enforceable backend deadlines, no unbounded queue, no content fetching, transient spools/results and server-only credentials match the package.

The exact multipart field, canonical filename, UUID header, JSON error envelope/status enum, 100 parts/depth 20/decoded-byte/token limits, deadlines and manual retry schedule are new architecture choices under Q3/Q4, correctly labeled assumptions. They do not contradict the source's unresolved alternatives. Qualification before E2/E4 must remain mandatory; no measured SLA or resolved model-quality threshold is claimed.

## Concrete reconciliation findings and exact suggested fixes

### RS-1 — Broken primary-source reference

Spine frontmatter currently names `../../../../IAP_Web_Application_Plan.md`. Read-only checks found that path absent and `docs/IAP_Web_Application_Plan.md` present. The SPEC package source and memlog correctly use the docs path. A reader following architecture lineage cannot resolve the present spine entry.

Replace only that entry with:

```yaml
  - ../../../../docs/IAP_Web_Application_Plan.md
```

### RS-2 — CAP-1 presentation details are not assigned explicitly

[API companion, User flow](../../../specs/spec-iap-web-application/api-and-experience.md#user-flow) requires filename **and size**, plus email-export guidance. AD-8 assigns the captured filename but not selected size or guidance; neither appears elsewhere in the spine. These are small existing requirements, not proposed new UI scope.

Append to AD-8's rule:

> Before Analyze, show the selected filename and byte size and provide inline guidance for exporting one email as `.eml`; selection alone never sends its contents.

### RS-3 — CAP-5 release qualification omits important acceptance mechanics

[Model companion, Artifact and manifest contract](../../../specs/spec-iap-web-application/model-and-inference.md#artifact-and-manifest-contract), [Evaluation and parity](../../../specs/spec-iap-web-application/model-and-inference.md#evaluation-and-parity) and [E0 evidence required](../../../specs/spec-iap-web-application/model-and-inference.md#e0-evidence-required) explicitly require source revision, same-run test counts/dimensions, feature-value as well as label parity, real MIME fixtures, separate validation/grouped independent testing and initial resource trials at E0. AD-2 mentions evaluation evidence and code hashes, while AD-4/contract acceptance mention label/schema repeatability. Those phrases do not explicitly require feature-value equality, the test-sample check, evaluation selection independence or E0 measurements before later hosting work. Code hashes alone do not preserve the requested source commit/revision field.

Add **source commit/revision** to AD-2's manifest list, then append this compact qualification rule to AD-2 or a dedicated E0 acceptance row:

> E0 evidence must include the reviewed dataset snapshot and per-source provenance; verified same-run hashes, classes, ordered widths and matching evaluation sample counts; privacy-scrubbed plain-text, HTML, multipart, varied-charset, attachment and malformed `.eml` fixtures; bytes-to-prediction harness/API engineered-feature values, embedding-tolerance and label agreement; and initial peak RAM, startup and warm/cold latency trials. Select the classifier and any threshold on separate validation; keep an independent appropriately grouped test partition, deduplicate before splitting and fit the scaler only on training samples. Probability decisions and ROC-AUC use the confirmed positive-class index/scores; classification metrics use predicted labels. Record the policy, tolerance and release-specific target evaluation. E0 remains pending until this evidence qualifies the real release.

No requirement to regenerate evaluation is implied. The existing successful log must be inspected first; any new report generation remains deliberate under the adopted repository instructions.

Also append to AD-6:

> Missing-header/structure warning codes are recorded internally according to the release policy without retaining email contents or widening the log-field allowlist.

This preserves [API companion, Input and resource boundary](../../../specs/spec-iap-web-application/api-and-experience.md#input-and-resource-boundary). It does not require adding warnings to the minimal public success response.

### RS-4 — CAP-6 tested handover and E0–E5 dependency boundary need an explicit acceptance row

[SPEC CAP-6](../../../specs/spec-iap-web-application/SPEC.md#capabilities) requires a **tested** local Docker demo plus run/deploy/rollback instructions, required integration checks and measured warm/cold behavior. [Deployment companion, Dependency order and evidence](../../../specs/spec-iap-web-application/deployment-and-acceptance.md#dependency-order-and-evidence) and [Acceptance coverage](../../../specs/spec-iap-web-application/deployment-and-acceptance.md#acceptance-coverage) additionally require browser upload/error/retry flows, frontend build, privacy inspection, case counts/sizes/environment and documentation. AD-12 names recording a local demonstration and AD-11 defines rollback integrity; the current spine does not explicitly make tested handover/build/browser/privacy evidence a completion condition. Its opening says source acceptance remains binding, so this is an omission in builder-facing assignment, not an authorized reduction of scope.

Append a consistency acceptance row:

> E1 design/sample work may overlap E0; E2 qualification and E3 real-browser prediction acceptance use the eligible release. E4 cloud acceptance requires measured whole-container memory, actual multipart transfer and warm/cold/unavailable/timeout/recovery behavior. E5 handover requires the frontend build, meaningful inference/API/browser checks including upload/drop/change/retry/error flows, sensitive-log/credential/temp-cleanup inspection, measurements with case count/size/environment, and tested local Docker run/deploy/rollback instructions. A local demo, fixture result or architecture document does not certify E0 or the cloud path.

## Boundaries that need no reconciliation edit

- Local frontend/proxy operation remains the current demonstration path. A future remote frontend requires a reachable backend and separately qualified packaging/resources/access.
- The 2 MiB cap and resource targets require applicable acceptance evidence; future hosting is unspecified. Provider-account research is outside this SPEC-only pass, and this pass does not validate its current service claims.
- Historic ZIP pointers, local-manifest metadata and old mixed-positive metrics remain evidence boundaries. The spine does not use them to assert eligible inference, accuracy or cloud feasibility.
- Original diagram/report alignment and RQ2/RQ3 research remain separate source obligations; no source-image edit or research completion is claimed. The imported graph does not expand the binary MVP.

Outcome: all six capabilities have architectural homes and the main invariants agree. RS-1 is a concrete bad link; RS-2–RS-4 make existing acceptance obligations explicit enough for independent builders. Q1/Q2 evidence and Q3/Q4/Q5 qualification remain open rather than silently certified.

## Fix-resolution addendum — latest spine

2026-10-05. Targeted reread of spine SHA256 `131C29DFB26951AC05401590CB4DE11F935B04E899277803C7DAF9A235FD4FB1` confirms all four SPEC reconciliation items resolved:

| Item | Resolution |
| --- | --- |
| RS-1 | Frontmatter now resolves `../../../../docs/IAP_Web_Application_Plan.md`. |
| RS-2 | AD-8 explicitly assigns selected filename/size and inline `.eml` export guidance; Delivery gates require drop/upload browser checks. |
| RS-3 | AD-2 includes source commit/revision and a shared versioned approved manifest; E0 qualification includes dataset/per-source evidence, same-run hashes/classes/widths/test counts, real MIME fixture harness/API feature/embedding/label parity, initial resources, independent validation/grouped tests, training-only scaler and positive-score ROC-AUC. AD-6 records transient internal missing-header/structure warning codes. |
| RS-4 | Delivery gates explicitly preserve E0–E5 dependencies, frontend build, inference/API/browser flows, private-log/secret/cleanup checks, measurements with case count/size/environment and tested local Docker run/deploy/rollback instructions. |

No unresolved SPEC-package requirement remains from this reconciliation pass. Added AD-13 separates bounded truthful operational observation from strict terminal prediction; it adds no email class, score, result persistence or inspector. Fixed termination escalation and MIME authority further implement the existing bounded/privacy constraints. Q1/Q2 release evidence, Q3/Q4 profile qualification and Q5 measured cloud access remain explicit acceptance gates. This addendum reports documentation reconciliation, not completed E0, tests, model qualification or deployment.
