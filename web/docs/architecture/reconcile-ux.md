---
name: UX input reconciliation
status: complete-with-suggested-source-updates
created: 2026-10-05
scope: DESIGN.md and EXPERIENCE.md against this run's architecture spine
sources:
  - ARCHITECTURE-SPINE.md
  - ../ux/DESIGN.md
  - ../ux/EXPERIENCE.md
source_files_changed: false
review_gate_passed: false
---

# UX Input Reconciliation

The two draft UX documents were read in full and compared in a separate UX-only pass with this run's updated [ARCHITECTURE-SPINE.md](ARCHITECTURE-SPINE.md), including AD-13 and the browser-generated correlation-ID contract. This is mandatory input reconciliation, not UX approval. Only this report was written; the spine and source documents were not edited.

The established manual flow, five states, two English result labels, filename identity, transient session intent, and truthful progress rules align. The final reread confirms that the spine has resolved the earlier UX retry mismatch: invalid upstream responses and internal failures now permit bounded manual Retry, and Analyze cannot bypass the unchanged-file retry count. No material UX-required behavior is missing from the spine. Several UX open-choice statements still need a source-owner handoff to the initial shared policy while preserving its unqualified status.

## Suggested source updates

| ID | Evidence and consequence | Suggested fix |
| --- | --- | --- |
| UX-R1 — earlier retry conflict resolved | [EXPERIENCE State Patterns](../ux/EXPERIENCE.md#state-patterns), line 90, groups startup HTML/non-JSON and service authentication failures with “Retain; bounded Retry.” The final [Spine Consistency Conventions](ARCHITECTURE-SPINE.md#consistency-conventions), Retry and Upstream normalization rows, now allows `UPSTREAM_INVALID_RESPONSE` after 5s and `INTERNAL_ERROR` after 10s. This matches the UX's bounded recovery intent. | Retain suitable input and drive recovery from the validated canonical error code and shared retry count. The user-facing cause categories may stay readable; no raw provider/account page is added. Replace the historical non-retryable interpretation with this final policy during source-owner handoff. |
| UX-R2 — required policy handoff | [EXPERIENCE State Patterns](../ux/EXPERIENCE.md#state-patterns), line 93, says final codes/parser/retry eligibility remain open. [Assumptions and Open Choices](../ux/EXPERIENCE.md#assumptions-and-open-choices), lines 150–151, still describes Q3/Q4 and retry/concurrency as unresolved. The spine now assigns one backend-owned schema/policy and an explicit initial profile under [AD-5/6/7](ARCHITECTURE-SPINE.md#invariants--rules). Builders could independently choose limits or omit the retry bound. | Replace “unresolved” with “initial architecture policy specified; qualification pending.” Reference the shared policy rather than inventing separate UX constants. Initial Retry: manual only, at most two retries for an unchanged selected file across Retry and Analyze after failure; 5s for busy/model/upstream unavailable or invalid upstream response; 10s for timeout/internal error, matching `Retry-After`. Input errors require correction/replacement; success/replacement clears retry state. Explain a disabled/exhausted Retry in text, and prevent Analyze from bypassing the count. These are `[ASSUMPTION]` policy values, not measured availability or latency promises. |
| UX-R3 — required privacy wording precision | [EXPERIENCE Interaction Primitives](../ux/EXPERIENCE.md#interaction-primitives), line 101, says no local storage/server history “is required,” which can be read as optional persistence. Refresh clearing is tagged A5, whereas [spine AD-9](ARCHITECTURE-SPINE.md#ad-9--transient-data-and-safe-processing-adopted) binds memory-only state and refresh clearing. The conditional retention-copy paragraph already avoids an unverified promise. | State that selected files/results stay in browser memory and must not be persisted in browser storage or server result history; refresh clears them. Identify that constraint as source/architecture binding while keeping A5 implementation details, focus, announcements, and interaction proposals editable. Preserve the requirement to verify cleanup/logging/session behavior before publishing retention copy. |
| UX-R4 — phase wording clarification | The [EXPERIENCE phase rule](../ux/EXPERIENCE.md#state-patterns) correctly allows specific phases only when observed. [Source-described session](../ux/EXPERIENCE.md#source-described-session), step 5, says sending/startup/processing text appears, which could be read as requiring each phase. Spine AD-8/AD-13 now defines a truthful, bounded current-attempt phase channel with generic “Analyzing…” when its phase is unknown. | Suggested step 5: “Analyzing… appears; a more specific sending, startup, or processing phase appears only when reliably observable under the integration contract.” Follow AD-13's validated current-request phases; stop observation on timeout/replacement/removal/terminal state. Do not infer startup from generic 503/provider HTML, time elapsed, or an arbitrary animation. This creates no new screen or classification field. |
| UX-R5 — contract acceptance clarification | [EXPERIENCE Component Patterns](../ux/EXPERIENCE.md#component-patterns), line 60, requires completed status and a valid label, but does not explicitly state the spine's exact success envelope and current-attempt validation. Other draft sections already suppress stale results. [Spine AD-5/8](ARCHITECTURE-SPINE.md#invariants--rules) makes both mandatory. | Clarify that success requires the current attempt's runtime-validated strict response: completed status, exactly one lowercase `legit` or `phishing` label, and no unexpected fields. Keep the displayed filename from the captured browser attempt; the backend's canonical `message.eml` filename is not the UI result identity. No additional screen or output field is needed. |

The initial file policy is **2,097,152 whole-file bytes including encoded attachments**, with a separate **2,162,688-byte multipart envelope**. Show the configured file limit to users; keep the envelope and parser work bounds in shared implementation policy. The initial browser deadline is **165s**; timeout clears/invalidate the attempt and shows no class. These values remain architecture assumptions awaiting joint qualification, and should not become a completion-duration promise. [Spine Consistency Conventions](ARCHITECTURE-SPINE.md#consistency-conventions)

## Confirmed alignment to preserve

| Concern | UX evidence | Spine relationship |
| --- | --- | --- |
| Explicit one-email flow | Choose/drop one `.eml`; metadata and transmission notice precede Analyze; selection sends nothing. | AD-5/6/8. No automatic upload, inspector, history, account, or readiness screen. |
| State model | Exactly `no-file`, `file-selected`, `analyzing`, `success`, `error`; success variants/phases add no state. “Ready to analyze” describes selection only. | AD-8/11. Operational failure remains an error, never a third class. |
| Result integrity | Capture filename/request identity; clear prior output on starts/retry/replacement/removal; suppress late responses; duplicate starts and file mutation blocked during analyzing. | AD-7/8. No stale label or cross-attempt result commitment. |
| Readable labels | Exact English `Legit` and `Phishing`; neutral equally readable styling and text beyond color. | AD-8. No “Safe,” confidence, probability, or accuracy claim. |
| Privacy and safe display | Transmission copy is explicit; retention promise is conditional; no email HTML/script/link/attachment execution or tracking fetches. | AD-9. Keep privacy enforcement an acceptance condition. |
| Progress and cancellation | Indeterminate progress, observable phases only, no invented percentages/durations; no Cancel or server-stop promise. | AD-7/8/13. The phase channel supplies observation while leaving exactly five top-level UI states. Backend termination on its own deadline does not justify a browser cancellation claim. |
| Fixtures and hosting evidence | Sample results visibly distinguished; E0 eligibility, measured hosting, and public-access policy remain unverified. | AD-2/10/12. Fixture/local/cloud acceptance remain distinct; no new login flow is implied by a deployment access gate. |

No visual change to [DESIGN.md](../ux/DESIGN.md) is required for this reconciliation. Its wireframe, shared component names, filename wrapping, readable pending/disabled states, neutral class treatment, and absence of scores/inspectors fit the spine. Contrast, focus, responsive behavior, and other accessibility checks remain future implementation validation.

## Draft assumptions remain intact

| Assumption | Preservation rule |
| --- | --- |
| A1 — audience | Keep demo/project/lecturer audience and Linh explicitly illustrative; no interview evidence is added. |
| A2 — devices | Keep desktop priority and phone-responsive rules proposed; architecture does not certify device coverage. |
| A3 — visual values | Keep all colors, typography, radii, spacing, contrast targets, and exact dimensions draft proposals. |
| A4 — composition | Keep the single centered page and wireframe composition draft; source-bound explicit Analyze and output constraints still govern. |
| A5 — interactions/accessibility | Keep control, help, focus, announcement, keyboard and reduced-motion details proposed. Distinguish binding attempt/session safety constraints from editable presentation details; do not promote the whole category to approved UX. |

Both UX frontmatters must remain `status: draft`. The architecture expressly keeps A1–A5 editable before UI acceptance. Adopting shared transport/session policy does not approve the brand, layout, audience, or interaction design. [Spine Deferred](ARCHITECTURE-SPINE.md#deferred)

## Verification boundary

Validation performed: complete document comparison and targeted source-line checks against the updated spine. No UI, API, privacy cleanup, retry, model, accessibility, local-container, or cloud tests were run. Suggested changes are recorded for the source owners; no source was rewritten, and this reconciliation supplies no implementation certification.
