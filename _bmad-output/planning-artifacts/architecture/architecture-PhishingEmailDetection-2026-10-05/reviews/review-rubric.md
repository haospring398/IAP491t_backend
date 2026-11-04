# Architecture reviewer gate: rubric walker

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

**Verdict: Needs fixes before handoff.** The main boundaries, binary-target eligibility, same-run feature contract, privacy and measured deployment envelope are coherent, but phase observability and failed-worker termination are not fully enforceable as written. Two medium wording ambiguities also permit divergent implementations.

Review date: 2026-10-05. Scope: feature-altitude build substrate for CAP-1–CAP-6. Reviewed spine SHA256: `DC15AB0BE83382708F1AA8CF1FB16E6D6E3E9477753806C7F23CAE54ACC4CB8A`. No spine/source edits, model deserialization, training, evaluation or application execution. The standard-library linter ran through `.venv/Scripts/python.exe` and reported `ok: true`, zero mechanical findings. Parent is applying mandatory input-reconciliation additions; those additions were not present in this snapshot and must be checked on the resulting version.

## High findings

### RR-1 — CAP-3/FR-5 phases have no common observation contract

**Location:** AD-5, AD-8; final PRD FR-5 versus latest draft UX State Patterns.

The final [PRD FR-5](../../../prds/prd-PhishingEmailDetection-2026-10-05/prd.md#3-follow-processing-and-recover) requires distinguishable sending, backend startup and processing. The [draft UX](../../../ux-designs/ux-PhishingEmailDetection-2026-10-05/EXPERIENCE.md#state-patterns) permits generic “Analyzing…” when these stages cannot be observed. AD-8 currently adopts the latter fallback without settling how the stronger final requirement is met. AD-5 exposes only a synchronous final success/error response and minimal readiness; those bodies cannot by themselves establish a particular attempt's current processing phase.

**Divergent compliant builders:** Frontend shows generic analyzing for every pending request, relying on the draft UX. API returns only the final strict result and exposes no attempt observations. Both comply with present ADs, while FR-5 fails. Another frontend may infer startup from elapsed time or generic 503 and misclassify permanent unready states as startup.

**Disposition: autofix/design decision before handoff.** Preserve strict minimal POST success and add a single shared, truthful observation/preflight contract with an explicit owner and exact status semantics. It must distinguish cold/loading from permanent unready, connect processing observations to the admitted current attempt, define transport/upload observation, and prevent stale observations committing a result. If observability is intentionally omitted, reconcile FR-5 upstream explicitly rather than silently weaken it. Do not fake phases or count elapsed time as evidence. This is an interoperability decision, not a Deferred UI refinement.

### RR-2 — AD-7 has no enforced endpoint when a timed-out child cannot be reaped

**Location:** AD-7, AD-11, deadline/recovery policy.

AD-7 calls for terminate/reap and says a failure to reap leaves the service unready and “requires container restart.” It gives no finite termination/reaping grace, escalation, or actor that performs that restart. AD-11 keeps liveness 200 while the supervisor responds. A compliant supervisor could therefore return timeout/unready and wait indefinitely for an operator while the original child may still consume CPU or retain data. No replacement should be started while that process may remain alive.

**Divergent compliant builders:** One supervisor interprets “requires restart” as an operations alert and continues serving liveness; another kills itself to trigger a container restart. Only the latter gives the stated finite work envelope without human intervention.

**Disposition: autofix.** Define bounded terminate → hard-kill → reap escalation and include its grace in the execution/response bound. If a child still cannot be confirmed exited, discard all its IPC, retain unready/no admission, and have the supervisor exit so the configured container lifecycle performs restart. Explicitly prohibit a replacement child until old-worker exit is confirmed. The local/cloud run configuration must enforce that restart behavior, and timeout tests must cover it. A frontend timeout, readiness 503 or instruction for an operator is insufficient to enforce computation bounds.

## Medium findings

### RR-3 — “Fixtures” conflates mock responses and real-model qualification emails

**Location:** Consistency Conventions → Contract acceptance; Deferred eligible-release row.

The convention says “Fixtures are visibly marked ‘Sample result — not a real analysis’ and cannot satisfy E0/real-model acceptance.” But [model E0 evidence](../../../../specs/spec-iap-web-application/model-and-inference.md#e0-evidence-required) intentionally requires real inference on privacy-scrubbed `.eml` fixtures. The PRD glossary allows Fixture to mean either a verification email or a marked sample response. A builder could mark genuine model output as non-real evidence or reject the required fixture-based E0 evidence entirely.

**Disposition: autofix.** Replace the broad sentence with:

> Mock/sample responses are visibly marked “Sample result — not a real analysis” and cannot satisfy E0 or real-model acceptance. Privacy-scrubbed verification-email fixtures processed by the qualified real release supply harness/API/browser acceptance evidence.

Use “mock/sample responses” rather than “fixtures” for the same exclusion in Deferred.

### RR-4 — MIME-type handling does not specify whether a claim is ignored or rejected

**Location:** AD-6, sentence “Reject extra parts and untrusted MIME-type claims.”

Every browser-supplied file Content-Type is untrusted. The [API companion](../../../../specs/spec-iap-web-application/api-and-experience.md#input-and-resource-boundary) requires extension plus actual structure without trusting that type; it does not demand rejection of every claim. Current wording can yield one validator accepting empty or `application/octet-stream` metadata when bytes are a valid email and another rejecting the same input before parsing.

**Disposition: autofix.** Replace with:

> Reject extra multipart fields/files. Treat the client-declared file MIME type as untrusted metadata; it neither establishes validity nor by itself causes rejection. Validate the original `.eml` extension and actual bytes/structure under the common release policy.

If an allowlist is deliberately required instead, name it explicitly in the common contract and qualify browser/provider behavior; do not leave it to each validator.

## Good-spine checklist

| Rubric dimension | Assessment |
| --- | --- |
| Real divergence points at feature altitude | Main model/HTTP/policy ownership, immutable deployment, admission and browser-attempt rules are fixed. RR-1/RR-2 are remaining load-bearing seams. |
| Enforceable ADs | AD-1–6 and AD-8–12 have usable owner/action constraints except RR-1/RR-4; AD-7 needs explicit failure escalation under RR-2. |
| Six capabilities | All six have mapped homes. Reconciliation additions must make CAP-1 export/size, CAP-5 E0/parity/evaluation evidence and CAP-6 tested handover explicit; see [reconcile-spec.md](../reconcile-spec.md). |
| Deferred interoperability | ML values/release evidence, resource qualification and cloud access are hard gates with owners. Internal filenames/transitive pins can remain implementation-owned because schemas/generated clients have one owner. Phase observation cannot be deferred independently. |
| Current named technology | Dated primary-source links and version/starter fit are retained in the two working research notes; seed is explicitly uninstalled/unbuilt. This pass checked that evidence exists, not deployment or model compatibility. |
| Brownfield ratification | Dynamic 40-feature schema, original MIME, current helper seams and same-run artifacts are ratified. Actual loose training publication, import-time evaluation, hardcoded importance dimensions and sibling virtualenv drift are disclosed and gated; no false claim that AGENTS requirements are already integrated. |
| Inherited invariants | No parent spine was supplied. Canonical SPEC requirements remain binding; RR-1 is the documented final-PRD/draft-UX conflict. |
| Environmental/operational envelope | Local/preview/production secrets, environment isolation and unspecified future hosting, whole-container measurements, persistent model versus transient requests, readiness, rollback and local frontend fallback are covered. Failed-worker restart ownership is RR-2. |
| Assumptions | Stack/profile/process choices are tagged; 2 MiB/400 MiB and latency/retry bounds are not represented as measured results. E0, model-quality values, artifact/environment compatibility and cloud access remain evidence gates. |

The spine should pass a targeted recheck once RR-1–RR-4 and the acknowledged input-reconciliation additions land. No further implementation detail is requested by this rubric pass.

## Targeted recheck — updated verdict

2026-10-05. Latest reviewed spine SHA256: `131C29DFB26951AC05401590CB4DE11F935B04E899277803C7DAF9A235FD4FB1`. This verdict supersedes the initial snapshot verdict above. Lint rerun after the substantive changes returned `ok: true`, zero findings.

**Updated verdict: PASS for architectural completeness, with one low terminology cleanup.** No critical, high or medium rubric finding remains. This is documentation handoff readiness; E0, profile qualification, compatible builds and measured cloud acceptance remain explicit future gates.

| Finding | Resolution |
| --- | --- |
| RR-1 | AD-13 owns a separate strict authenticated phase channel, precise service-starting/current-attempt receiving/processing/unknown semantics, bounded polling, current-attempt correlation and no phase-derived result commits. AD-8 uses real observations; provider wake with no reliable observation remains generic rather than fabricated. Strict minimal POST success is preserved. Final PRD phases now have an implementation contract. |
| RR-2 | AD-7 sets 1s terminate/reap then 1s hard-kill/reap, forbids descendants/replacement alongside an unreaped child, and requires supervisor nonzero exit for container recovery. Profile accounts for kill/reap and trusted forwarded deadline; readiness remains false until replacement qualification. |
| RR-3 | Contract acceptance now explicitly excludes only mock/sample responses and permits real-model email fixtures as qualification evidence. This resolves the medium acceptance ambiguity. One residual shorthand in Deferred is the low item below. |
| RR-4 | AD-6 makes client MIME non-authoritative and suitability a function of extension plus actual bytes/structure under the common adapter/policy. MIME traversal, decoded-byte counting and token overflow semantics are also now explicit. |
| Reconciliation RS-1–RS-4 | Correct source path, filename/size/export guidance, manifest revision/E0 fixture-feature-evaluation-resource evidence, internal warning policy and tested E0–E5 handover obligations are present. [SPEC reconciliation](../reconcile-spec.md) and [PRD/addendum reconciliation](../reconcile-prd.md) record coverage. |

**Low — Deferred terminology:** The eligible-release row still says “fixtures may unblock contract/UI work only.” The controlling acceptance row now settles the actual semantics, so this is no longer an eligibility/interop blocker. For consistent terminology, replace that phrase with “mock/sample responses may unblock contract/UI work only.” No new decision or source change is needed.

The six capability homes, enforceable work/ownership boundaries, brownfield drift disclosure, environmental envelope and labeled assumptions continue to satisfy the rubric after these changes. No further structural addition is requested.
