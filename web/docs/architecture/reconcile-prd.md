# Reconciliation: final PRD and addendum

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

2026-10-05. Compared the latest [architecture spine](ARCHITECTURE-SPINE.md) against final [prd.md](../prd/prd.md) and [addendum.md](../prd/addendum.md). This is mandatory input reconciliation, not implementation acceptance. No spine/source edits, training, model loading, report regeneration or deployment.

**Result:** No missing or conflicting product requirement remains after the reconciliation additions. The strongest prior conflict, observable processing phases, now has a shared AD-13 observation contract while the terminal POST result remains minimal. One residual mock/fixture wording item is tracked in the [rubric review](reviews/review-rubric.md); it does not authorize changing the PRD target or acceptance gates.

## Requirement coverage

| PRD requirement | Latest spine coverage |
| --- | --- |
| FR-1: one select/drop file, filename/size, export guidance, Analyze | AD-5/6/8 define one `.eml`, explicit transmission, filename/size and export help. Delivery gates explicitly require upload/drop browser checks. |
| FR-2: unsuitable input before inference | AD-6 and canonical HTTP map cover extension/actual structure, empty input, insufficient normalized content, whole-file/body/part/depth/decoded/token bounds and reject-on-overflow. Q3 choices are shared assumptions pending qualification. |
| FR-3: eligible `legit|phishing` target | AD-2/3 require reviewed class semantics, exclude ordinary spam/unknown positives and prohibit display-name changes as qualification. E0 is offline-reviewed evidence, not inferred runtime metadata. |
| FR-4: correct-file result/no class on errors/marked samples | AD-5/8 fix exact terminal schema, captured filename, attempt identity and clearing obsolete output. Contract acceptance distinguishes mock responses from real-model fixtures. |
| FR-5: readable distinguishable phases, completion/failure, duplicate/stale safety | AD-8/13 use actual browser upload events and a separate bounded status channel for supervisor startup/body receipt/matching worker processing. Unknown/unavailable phase stays generic; elapsed time is never phase evidence. Only the terminal POST can commit success/failure. |
| FR-6: actionable bounded recovery | Shared error enum/status/normalization and same-file retry policy cover bad input, unready/busy/unreachable/timeout/provider failures. Retry/Analyze cannot bypass the count; exhausted retries require text. |
| FR-7: honest liveness/readiness and attribution | AD-2/9/11 fail closed for release/policy/resources/target; minimal live/ready schemas expose no model details. Busy capacity differs from readiness, and internal release ID is allowlisted. |
| FR-8: E0 provenance/release/real inference/evaluation/resource evidence | AD-2 and E0 qualification row require dataset/per-source evidence, approved manifest schema/revision, same-run hashes/classes/widths/test counts, real MIME fixtures, release-specific evaluation and initial resource trials. |
| FR-9: harness/API feature/result parity and request-order stability | AD-3/4, E0 qualification and contract acceptance require engineered-feature equality, embedding tolerance, label agreement and repeat/order/restart determinism. Exact ML policy/tolerance remains gated. |
| FR-10: measured free deployment or fallback and tested handover | AD-11/12 and Delivery gates require immutable restart-safe bundle, measured cold/warm/error behavior, build/API/browser checks, private logs/secrets/cleanup and tested local Docker run/deploy/rollback instructions. Local fallback does not certify cloud. |
| NFR-1: transient input/result, cleanup, log exclusions | AD-9 specifies session memory and all-path request-spool/IPC cleanup; only request ID/bytes/duration/status/internal release ID are loggable. No email content/filename/history/database/local storage. |
| NFR-2: safe processing and server credentials | AD-9/10 prohibit HTML/script/attachment execution and URL/DNS/WHOIS/tracking requests; backend verifies server-only environment-scoped Bearer token. No browser secret or CORS-as-auth assumption. |
| NFR-3: bounded input/work/retry/resource envelope | AD-6/7/13 plus shared profile bound parser/token/body work, single admitted analysis, backend deadline/kill/reap, status polls and retries. No unbounded queue; proxy deadline also bounds late backend admission. |
| NFR-4: same verified release/environment, no retraining, publication preservation | AD-1–4/11 fix dependency separation, raw-feature order, fitted scaler, immutable code/model/resource/policy deployment and previous-run/pointer preservation on failed publication. |
| NFR-5: text-readable interaction without new scope | AD-8/13 specify readable English phases/results/errors, no fake percentages and no color-only class meaning. Draft UX tokens/focus/layout remain assumptions. |

## Success, scope and claim boundaries

SM-1–SM-3 have concrete homes in E0 qualification, contract acceptance and Delivery gates: real valid-fixture browser/API completion, required invalid/service/error cases without a label, reproducibility/privacy/parity and tested handover. SM-C1 is preserved through target-specific FP/FN, full case/failure counts, latency and memory measurement. SM-C2 is addressed by enforceable class/error separation, current-attempt commits, repeatability, secret/log/retention exclusions and explicit acceptance checks. Neither document claims those checks passed.

One manual English binary session remains the MVP. Scores/confidence/risk, Spam/uncertain labels, indicators/XAI, inspector/features/model-info/JSON export, accounts/history/database/batch/inbox automation and unsupported prevention metrics remain excluded. AD-13 is an operational phase observation channel, with no label, filename, history or email data; it does not add a product inspector or broaden the strict successful prediction response.

## Addendum decisions and dependency reconciliation

- Next.js frontend with separate Python service remains the application boundary; hosting is unspecified after the cleanup. Framework/container/library versions remain researched architecture seeds subject to compatibility checks.
- Original MIME bytes → engineered features before cleaning → release-frozen Doc2Vec text/inference → fitted scaler transform → Doc2Vec-first fusion → one selected same-run classifier are preserved. Widths derive from ordered schema and verified objects, not legacy 42/142 comments.
- One serial ML worker, deterministic RNG/reset/restore, pinned resources/environment, no request-time corpus download and no training/evaluation imports preserve the adopted boundaries.
- E1 design/sample work may overlap E0; E2/E3 real prediction uses the qualified release; E4 requires real hosting/container/multipart/warm/cold/error measurements; E5 requires actual build/inference/API/browser/privacy/handover evidence. Estimates remain conditional and ML retraining is separately estimated.
- Dedicated local frontend/proxy plus Docker is a compatible documented fallback. The cleanup supersedes earlier provider alternatives; future hosting needs a separate measured decision.
- Previous ZIP observations, current manifest metadata, old mixed-positive metrics, Unicode support and previous repair completion do not establish eligibility, compatible loading, phishing quality, Vietnamese accuracy, cloud acceptance or RQ2/RQ3 completion. Original diagram/report alignment remains separate work; no such edits are claimed here.
- The supplemental competitor observations are context, not authorization for investigation panels, retention or new response fields. The spine preserves the binary/private scope.

## Assumptions and unresolved acceptance gates

PRD A1/A2 (2 MiB/~400 MiB) remain unverified initial targets. A3 (roughly 15 working days with an eligible release) remains an estimate; no delivery date is inferred from runtime deadlines. A4 workstream owners remain roles; architecture gives one schema/contract owner for cross-unit decisions. A5 baseline technologies are now explicit tagged architecture seeds, not tested installations.

Q1/Q2 target, dataset, selected release/classifier, compatible environment, exact inference/resources/vector tolerance and model-quality criteria remain ML-owned gates before E0/real predictions. Q3/Q4 now have one shared initial parser/error/deadline/retry profile, which owners must qualify or revise together before E2/E4 acceptance. Q5 hosting/account/access and actual cloud behavior remain deployment gates. These are acknowledged evidence requirements, not missing architecture dimensions or permission to diverge.
