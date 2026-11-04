# Input reconciliation: IAP Web Application Plan

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

Input: [docs/IAP_Web_Application_Plan.md](../../../../docs/IAP_Web_Application_Plan.md). Compared with [prd.md](prd.md), [addendum.md](addendum.md), and the adopted [SPEC](../../../specs/spec-iap-web-application/SPEC.md) plus all four companions. No canonical memlog was read or modified. This is a document reconciliation, not implementation or model verification.

**Verdict: reconciled; no material source gap or unresolved source contradiction found.** Implementation details retained by explicit SPEC-companion adoption need not be repeated in the PRD.

## Load-bearing source coverage

| Source idea or constraint | Where the final documents preserve it |
| --- | --- |
| Research demonstration; one selected/dropped `.eml`; two successful labels; separate Next.js frontend/Python backend; preference for free hosting | PRD vision, FR-1/FR-3 and MVP scope; SPEC CAP-1/CAP-2 and constraints |
| Minimal filename/result UI; uploading, backend startup, processing and recoverable errors; no fabricated progress or error-case classification; prevent duplicate/stale results | PRD FR-1 through FR-6 and NFR-5; API/experience companion's user flow |
| Ordinary spam is not phishing; review per-source provenance; numeric IDs, directory names and `INCLUDE_SPAM = False` alone cannot prove target correctness | PRD glossary, FR-3/FR-8 and Q1; model/inference companion's eligible-training-target rules |
| `legit` is reviewed legitimate email, not automatically all non-phishing spam; eligible same-run release and target-specific evaluation required before real prediction acceptance | PRD glossary/E0 dependencies; model/inference companion's target, artifact and evaluation contracts |
| Marked fixtures can support UI/API development while E0 is pending, but cannot satisfy real-model acceptance | PRD FR-4, scope and dependencies; SPEC constraints |
| Preserve raw-MIME extraction before cleaning; ordered 40 features and expected 100/140 widths must be checked; fitted scaler/Doc2Vec/one classifier; no request training or resource downloads | Addendum technical baseline; model/inference companion's feature/artifact contract |
| API success/error separation, liveness/readiness, server-only verified token, MIME/size limits, bounded concurrency/deadlines/retry and provider non-JSON startup handling | PRD FR-2/FR-6/FR-7, NFR-2/NFR-3, Q3/Q4; addendum and API/experience companion |
| Transient email/session-only results; temporary-file cleanup; no sensitive logs or executing/fetching email HTML, links, tracking resources or attachments | PRD NFR-1/NFR-2; API/experience companion |
| Measured hosting feasibility; restart-safe artifacts; resource/multipart checks; unspecified future hosting and local operation; no paid trial, database or keepalive cron | PRD FR-10/non-goals/Q5; addendum and deployment/acceptance companion |
| E0–E5 dependency order; conditional 15-day web estimate; relabel/retrain estimate separate; warm/cold measurements; reproducible local/deploy/rollback handover; meaningful story checks/review | PRD FR-8 through FR-10, A3 and dependencies; addendum delivery table; deployment and brownfield companions |
| Probability/indicators/inspector/export/Gmail/extension/accounts/batch/database outside MVP; no Vietnamese efficacy, unsupported prevention counters or completed RQ2/RQ3 claims | PRD non-goals; addendum claim boundaries; SPEC and brownfield companion |

## Qualitative ideas and scope changes

The source's restrained demonstration intent survives: this is one understandable upload/result session, rather than a dashboard or email investigation product. Clear text states, bounded recovery, honest startup/error behavior, and internal rather than mandatory UI metadata are retained. The source's warning that a few successful examples cannot establish phishing accuracy survives in the success/counter-metrics and adopted research boundaries.

The PRD makes acceptance more explicit without adding a product capability. SM-1/SM-2 quantify coverage over the agreed fixture cases; SM-C2 requires zero integrity violations in covered checks. They are labeled planned checks, with no production-wide guarantee. Reporting target-specific false positives/negatives and resource/error costs operationalizes the source's target-specific evaluation and resource measurements. New workstream owner labels, the demo-participant role and the JTBD restatement are openly attributed assumptions or restatements, not source interview evidence.

NFR-4's failed-publication preservation and independent/probability-based evaluation details come from the explicitly adopted repository instructions and SPEC, not an unacknowledged expansion of the plan. Supplemental competitor context is isolated in the addendum and explicitly introduces no feature, demand or novelty requirement.

## Proposal versus fact

The plan itself classifies the stack, 2 MiB limit, approximately 400 MiB target and 15-working-day estimate as proposals. PRD A1/A2/A3/A5, open questions and the addendum preserve their provisional status. Hosting is unspecified; XGBoost is a historical packaging candidate, not the certified winner. The later cleanup supersedes the earlier hosting selection while retaining the frontend/Python separation.

No numeric model-quality, latency or throughput threshold is invented. Q2/Q4 require those decisions/evidence before associated acceptance, and Q5 preserves hosting/account/rate-control uncertainty. Required checks are not reported as completed.

## Apparent contradictions resolved by attribution

The plan's ZIP LFS pointers, legacy 42/142 README, unpinned dependencies and hard-prediction AUC are snapshot observations. The addendum and brownfield companion explicitly distinguish them from current local metadata and repository conventions; they do not claim that the current selected artifacts are pointers or that current evaluation still uses hard predictions. Local 40/100/140 metadata and earlier completed ML repair do not prove verified hashes, current compatibility or phishing-only E0 eligibility.

The graph's three-label/broader-output wording is a source artifact requiring later alignment, not the approved product scope. Report/diagram changes remain separate work and are not represented as already completed. The plan's historical BMad command examples are reconciled to installed capabilities through the addendum/brownfield route without requiring an installation upgrade.

**Outstanding source gaps: none.** Existing Q1–Q5 remain substantive project decisions; their presence is faithful preservation of unresolved implementation/evidence matters, not a reconciliation failure.
