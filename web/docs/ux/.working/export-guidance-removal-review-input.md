# File: DESIGN.md

---
name: PhishingEmailDetection
description: Draft visual identity for a manual single-email classification demonstration.
status: draft
sources:
  - ../../prd/prd.md
  - ../../prd/addendum.md
  - ../../spec/SPEC.md
  - ../../spec/api-and-experience.md
  - ../../spec/model-and-inference.md
  - ../../spec/deployment-and-acceptance.md
  - ../../spec/brownfield-and-evidence.md
  - ../../IAP_Web_Application_Plan.md
  - ../imports/graph-iap419t.png
updated: 2026-10-06
colors:
  primary: '#123C69'
  primary-foreground: '#FFFFFF'
  background: '#F8FAFC'
  surface: '#FFFFFF'
  foreground: '#0F172A'
  secondary-text: '#475569'
  border: '#64748B'
  focus: '#1D4ED8'
  disabled-surface: '#E2E8F0'
  error-text: '#9F1239'
  error-surface: '#FFF1F2'
typography:
  title:
    fontFamily: 'system-ui, sans-serif'
    fontSize: 28px
    fontWeight: '700'
    lineHeight: '1.25'
  body:
    fontFamily: 'system-ui, sans-serif'
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
  label:
    fontFamily: 'system-ui, sans-serif'
    fontSize: 16px
    fontWeight: '600'
    lineHeight: '1.5'
  meta:
    fontFamily: 'system-ui, sans-serif'
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  result:
    fontFamily: 'system-ui, sans-serif'
    fontSize: 24px
    fontWeight: '700'
    lineHeight: '1.3'
rounded:
  md: 8px
  lg: 12px
spacing:
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '5': 24px
  '6': 32px
  gutter-phone: 16px
  gutter-desktop: 32px
  content-max: 800px
  control-min: 44px
components:
  page-heading:
    foreground: '{colors.foreground}'
    fontSize: '{typography.title.fontSize}'
  upload-area:
    background: '{colors.surface}'
    border: '{colors.border}'
    radius: '{rounded.lg}'
    padding: '{spacing.5}'
  file-summary:
    foreground: '{colors.foreground}'
    fontSize: '{typography.meta.fontSize}'
  file-controls:
    foreground: '{colors.primary}'
    minHeight: '{spacing.control-min}'
  analyze-button:
    background: '{colors.primary}'
    foreground: '{colors.primary-foreground}'
    disabledBackground: '{colors.disabled-surface}'
    disabledForeground: '{colors.secondary-text}'
    radius: '{rounded.md}'
    minHeight: '{spacing.control-min}'
  privacy-note:
    foreground: '{colors.secondary-text}'
    fontSize: '{typography.meta.fontSize}'
  status-result-area:
    background: '{colors.surface}'
    foreground: '{colors.foreground}'
    errorBackground: '{colors.error-surface}'
    errorForeground: '{colors.error-text}'
    radius: '{rounded.lg}'
  recovery-actions:
    foreground: '{colors.primary}'
    minHeight: '{spacing.control-min}'
---

# PhishingEmailDetection — Design Draft

## Brand & Style

**[ASSUMPTION A3 — all visual values]** A compact, clear, light interface with deep blue primary actions. Every token above, including type, dimensions and radii, is a proposal for review. This identity supports a manual email check and project demonstration. No component library or existing brand system is confirmed.

Behavior and English microcopy live in [EXPERIENCE.md](../EXPERIENCE.md). **Legit** and **Phishing** have equally readable, neutral styling; the written label communicates the class. An operational error receives separate error styling without becoming a classification.

The directly inspected [Graph_IAP419t image](../imports/graph-iap419t.png) supplies an architectural reference for the email/ML flow. Its colored pipeline panels are not an approved product visual direction or page composition; **[ASSUMPTION A3]** tokens and **[ASSUMPTION A4]** layout remain proposals. See the [direct visual extract](source-graph-image.md) and [source reconciliation](../reconcile-plan-graph.md).

## Colors

**[ASSUMPTION A3]** `{colors.background}` frames `{colors.surface}` cards. `{colors.foreground}` carries headings/results; `{colors.secondary-text}` carries helper text. `{colors.primary}` with `{colors.primary-foreground}` identifies Analyze; `{colors.border}` defines controls and `{colors.focus}` marks keyboard focus. Error text/fill use `{colors.error-text}` and `{colors.error-surface}`.

Proposed contrast targets: normal text at least 4.5:1; large text at least 3:1; meaningful control boundaries and focus indicators at least 3:1 against adjacent surfaces. Check these in the implemented states, including drag/focus/disabled treatment. Do not differentiate successful classes through color alone.

## Typography

**[ASSUMPTION A3]** Use system sans-serif throughout. Title uses `title`; instructions use `body`; action labels use `label`; metadata/helper copy use `meta`; successful labels use `result`. Preserve text resizing and wrapping. Filenames must remain fully readable without forcing horizontal page scrolling.

## Layout & Spacing

**[ASSUMPTION A4 — layout]** One centered vertical column, up to `{spacing.content-max}`, with upload → action → result/status. **[ASSUMPTION A2 — device rules]** Use `{spacing.gutter-phone}` below a proposed 640px viewport breakpoint and `{spacing.gutter-desktop}` above it; keep the same reading order. Exact spacing follows **[ASSUMPTION A3]**.

```text
             centered content column
+------------------------------------------+
| Email analysis                           |
| Choose one email, then select Analyze.    |
| +--------------------------------------+ |
| | Drop one .eml file here               | |
| | [Choose file]                        | |
| | Filename + size, when selected       | |
| | [Change file] [Remove file], idle    | |
| +--------------------------------------+ |
| Server-processing / privacy note         |
| [Analyze]                               |
| +--------------------------------------+ |
| | Status, result, or processing error   | |
| | Filename + one label on success     | |
| | Recovery actions on error           | |
| +--------------------------------------+ |
+------------------------------------------+
```

| Placement | Component | Composition |
| --- | --- | --- |
| Top | page-heading | Title, then one instruction line. |
| First card | upload-area, file-summary, file-controls | Picker/drop target followed by selected metadata and idle controls. |
| Before action | privacy-note | Transmission notice. |
| Primary action | analyze-button | One prominent action, aligned with column. |
| Following action | status-result-area, recovery-actions | Stable position; content grows naturally for status/error/result. |

This wireframe is a proposal, not an approved mockup. The single Analyze surface is **spine-only** for this fast draft; no HTML or UI mockup image is required by this delivery. The two spines win on conflict with later visual artifacts.

## Elevation & Depth

**[ASSUMPTION A3]** White surfaces and visible borders establish hierarchy. No shadow is required. Keep progress, errors and results in the same region to make state changes easy to follow.

## Shapes

**[ASSUMPTION A3]** Use `{rounded.lg}` for upload/status surfaces and `{rounded.md}` for buttons. Preserve a visible focus outline, independent of rounded borders.

## Components

All visual rules in this table are **[ASSUMPTION A3]**; placement is **[ASSUMPTION A4]**. Names match EXPERIENCE.md.

| Component | Visual specification |
| --- | --- |
| page-heading | `title` heading plus `body` instruction; no decorative graphic. |
| upload-area | Surface, bordered drop target, `body` instructions; focus/drag adds focus outline and text cue. |
| file-summary | Plain-text filename and formatted byte size; wrap long names; `meta` typography. |
| file-controls | Text-labelled secondary buttons; visible border/focus; wrap when necessary. |
| analyze-button | Primary fill and white label; disabled uses disabled tokens plus actual disabled state; pending label remains readable. |
| privacy-note | `meta` text directly before Analyze; no unsupported certification icon. |
| status-result-area | Surface with text status; both successful labels use identical `result` typography. Error text/fill are reserved for processing failure. |
| recovery-actions | Visible text-labelled secondary controls below error copy; no hover-only action. |

## Do's and Don'ts

| Do | Don't |
| --- | --- |
| Write the exact successful label and analyzed filename. | Add Spam, Unknown, a score or an inspector to this MVP. |
| Make selected, pending and disabled states clear in text. | Depend on color, decorative badges or fake percentages. |
| Keep proposed visual choices tagged A3/A4. | Treat this draft as an approved brand or implemented application. |


# File: EXPERIENCE.md

---
name: PhishingEmailDetection
status: draft
sources:
  - ../../prd/prd.md
  - ../../prd/addendum.md
  - ../../spec/SPEC.md
  - ../../spec/api-and-experience.md
  - ../../spec/model-and-inference.md
  - ../../spec/deployment-and-acceptance.md
  - ../../spec/brownfield-and-evidence.md
  - ../../IAP_Web_Application_Plan.md
  - ../imports/graph-iap419t.png
updated: 2026-10-06
---

# PhishingEmailDetection — Experience Draft

## Foundation

Manual checking and project demonstration: select/drop **one `.eml`**, click **Analyze**, wait, then receive **Legit** or **Phishing** (`legit`/`phishing` domain labels). UI language is English. Processing failures are operational states, never a third class. MVP output contains the label and filename; probability, indicators and email inspector are extensions.

**[ASSUMPTION A1 — audience]** Individuals checking email, project members and lecturers. Sources call the roles **demo participant** and **project team**; no interviewed personas exist. **[ASSUMPTION A2 — devices]** Desktop-first responsive web. **[ASSUMPTION A4 — layout]** One page. [DESIGN.md](../DESIGN.md) owns appearance; no UI component library is confirmed.

## Information Architecture

| Surface | Entry | Delivers | Key Flows | Visual reference |
| --- | --- | --- | --- | --- |
| Analyze | Open application | Selection/drop, metadata, transmission notice, explicit action, progress, two-label result and recovery | Source-described session; Recover from a processing error | Spine-only: DESIGN.md wireframe/placement table. |

**[ASSUMPTION A4]** No navigation menu or separate results page. Every required state stays on Analyze. No history, account, inspector or technical-readiness surface is added.

## Voice and Tone

Use short English sentences stating what happened and the next action. Label results exactly **Legit** or **Phishing**; do not replace Legit with “Safe.” Never claim perfect detection, confidence, phishing-only accuracy or completed deployment.

| Context | Proposed microcopy |
| --- | --- |
| Title/instruction | “Email analysis” / “Choose one email, then select Analyze.” |
| Upload | “Drop one .eml file here” / “Choose file” |
| File helper | “One .eml file. Maximum size: {configured limit}, including attachments.” |
| Before Analyze | “Selecting a file does not send it. Select Analyze to send this email to the analysis server.” |

Retention copy is conditional on verified enforcement: “Files are processed temporarily. Results are kept only for this browser session.” This is the **source-required target**, not a verified privacy promise; validate cleanup/logging/session behavior before publishing it. Do not claim processing is local-only.

## Component Patterns

Visual tokens resolve to DESIGN.md; matching component names are deliberate. Newly proposed control/focus rules are **[ASSUMPTION A5 — interaction/accessibility]**.

| Component | Behavioral rules |
| --- | --- |
| page-heading | One semantic page heading; instruction describes the explicit start. |
| upload-area | Native file picker and one-file drop accept `.eml`; selection never sends content. More than one dropped file becomes an actionable error. Client checks assist; backend validates actual MIME/content. |
| file-summary | Show selected filename and size before Analyze; render filename as plain text and associate successful output with that exact request. |
| file-controls | **[ASSUMPTION A5]** Change file opens picker; Remove file clears selection/result/error to no-file. Available while idle; disabled during the active request. |
| analyze-button | Enabled only for a locally suitable selection; one activation starts one attempt and clears prior output. Disabled immediately during analyzing; label “Analyzing…”. |
| privacy-note | Visible before submission; distinguish selection from server transmission and verified retention policy. |
| status-result-area | Text state announced when changed; success requires completed status and a valid `legit|phishing` label. Progress uses indeterminate activity only. Error contains no label, score or old result. |
| recovery-actions | Choose another file for unsuitable input; Retry only for retained suitable files and when bounded service policy permits. No automatic retry loop. |

## State Patterns

Exactly **five top-level states**. Success variants and analyzing phases do not add states.

| State | Text/content | Action and result integrity |
| --- | --- | --- |
| no-file | “No file selected.” Upload instructions; no result. | Choose/drop enabled; Analyze disabled. Initial/cold page needs no model-readiness claim. |
| file-selected | Filename, size, “Ready to analyze.” | Analyze enabled after local checks; idle change/remove controls. This text describes selection, not backend readiness. |
| analyzing | “Analyzing…” by default; truthful subphases below. | Block duplicate start and file mutation; no previous classification. |
| success | “Analysis complete.” Filename; either **“Result: Legit”** or **“Result: Phishing”**, according to the successful response. | Exactly one label, identical neutral structure; idle change/remove available; no indicators. |
| error | “Analysis could not be completed.” Specific cause below; no classification. | Retain a suitable selection when recovery permits; invalid input needs replacement. |

Source mapping is preserved verbatim: **Upload** → no-file/file-selected; **Sending/startup/analyzing** → analyzing; **Completed** → success; **Failed** → error. PRD **Source-described session** is retained in Key Flows.

Analyzing subphases: “Sending email…” only while transmission is observable; “Starting analysis service…” only when the integration reliably identifies startup; “Analyzing email…” when processing is known. Otherwise show “Analyzing…” without inferring hidden backend stages. Never simulate startup, invent a percentage or promise a completion duration.

| Error condition | Proposed English message | Recovery |
| --- | --- | --- |
| Multiple files / wrong extension | “Choose one .eml file.” | Choose another file. |
| Empty | “This file is empty. Choose another .eml file.” | Replace. |
| Too large | “This file exceeds the {configured limit} limit, including attachments.” | Replace. |
| Invalid structure | “This file could not be read as an email. Choose another .eml file.” | Replace. |
| Insufficient content | “This email does not contain enough usable content for analysis.” | Replace. |
| Model unavailable | “Analysis is unavailable. Try again later.” | Retain suitable file; Retry when permitted, or replace. |
| Busy | “The analysis service is busy. Try again later.” | Same bounded policy. |
| Offline / unreachable | “The analysis service could not be reached. Check your connection and try again.” | Retain; Retry when permitted. |
| Timeout | “Analysis timed out. No result is available.” | Retain; Retry only when policy permits; do not claim server work stopped. |
| Startup HTML/non-JSON or service authentication failure | “The analysis service is unavailable. Try again later.” | Retain; bounded Retry. No account or provider-error page. |
| Invalid success payload / unexpected failure | “Analysis could not be completed. Try again later.” | No guessed label; retain if suitable and retryable. |

Generic failure covers unmapped errors. Use readable mapped copy, not stacktraces or raw provider HTML. Final error codes, parser acceptance and retry eligibility remain open; disabled Retry needs a textual explanation from the actual policy.

## Interaction Primitives

**[ASSUMPTION A5]** Click/tap or keyboard activation; drag/drop has an equivalent picker. File-picker cancellation keeps the prior selection/state. Replacement clears previous output before accepting the new file; a rejected replacement must not leave an old successful label on screen.

Capture request identity and filename at start. Suppress responses after timeout, replacement, removal or a newer attempt; an obsolete response cannot become the current success. Clear output before every retry; prevent overlapping attempts. No Cancel action or promise of server cancellation is proposed.

Do not render email HTML, execute scripts, open links/attachments or fetch tracking images. Result/selection memory is transient; no local storage/server history is required. Browser refresh starts at no-file **[ASSUMPTION A5]**. Public access/rate policy belongs to deployment decisions, not a new login flow.

## Accessibility Floor

Text labels rather than color alone are confirmed. Additional rules are **[ASSUMPTION A5]**, pending implementation validation:

- Label native input and buttons; tab order follows page composition. Visible focus uses `{colors.focus}`; controls use `{spacing.control-min}` as the proposed minimum target size.
- Announce progress and final label politely; announce errors once as alerts. Mark the status area busy during analyzing. Do not repeatedly announce an unchanged pending message.
- Keep focus predictable after activation; retain Analyze focus through pending/completion where practical. If a disabled/removed control loses focus, move it to the status area. Do not trap focus.
- Ensure filename/size, selected state, disabled actions and result identity are available to screen readers.
- Honor reduced motion with static progress text; support keyboard-only use, text resizing/zoom and phone widths without horizontal page scroll. Contrast targets live in DESIGN.md.

## Key Flows

### Source-described session

**[ASSUMPTION A1]** Linh is an illustrative demo participant, not an interviewed persona.

1. Linh opens Analyze; no-file guidance is visible.
2. Linh chooses or drops one `.eml`.
3. File-selected shows its name/size and the pre-submission transmission notice.
4. Linh clicks Analyze; the current attempt owns the selected filename and controls lock.
5. Truthful sending/startup/processing text appears within analyzing.
6. **Climax:** Success shows the same filename and exactly **Legit** or **Phishing**, with no score or inspector.

Failure path: invalid selection or an unsuccessful request enters error, without a class, and follows the recovery journey. PRD roles and journey wording are retained; Linh supplies only an explicitly assumed illustration.

### Recover from a processing error

**[ASSUMPTION A1]** Linh continues the illustrative session.

1. Linh reads a specific error; no previous result remains.
2. For an invalid file, Linh chooses a replacement. For a recoverable service error, the suitable selection remains and Retry follows the bounded policy.
3. A replacement returns to file-selected and requires Analyze; permitted Retry starts a new attempt with cleared output.
4. **Climax:** Successful recovery displays one label for the correct filename. Another failure keeps an actionable error with no fabricated classification.

## Responsive & Platform

**[ASSUMPTION A2]** Preserve all actions on desktop and phone; drop is optional on touch devices because the picker provides parity. **[ASSUMPTION A4]** One column at every width; metadata/actions wrap and the primary action may stretch on narrow screens. Gutters and maximum width reference `{spacing.gutter-phone}`, `{spacing.gutter-desktop}` and `{spacing.content-max}`; all exact dimensions remain A3 proposals.

## Assumptions and Open Choices

| Item | Draft position / revisit |
| --- | --- |
| [ASSUMPTION A1] | Audience and illustrative Linh; confirm against actual demo participants. |
| [ASSUMPTION A2] | Desktop priority and phone-responsive rules; confirm target devices. |
| [ASSUMPTION A3] | All exact colors/type/radii/spacing in DESIGN.md; review before visual approval. |
| [ASSUMPTION A4] | Single centered page/layout and spine-only wireframe; review composition. |
| [ASSUMPTION A5] | Proposed removal, focus, refresh, keyboard and announcement details; review behavior. |
| Upload/parser | Source-proposed 2 MiB whole-file cap is provisional, not a UX commitment. Confirm synchronized browser/proxy/backend limit, encoded-attachment handling and Q3 parser policy before showing the configured value. |
| Runtime/retry | Q4 deadlines and bounded retry/concurrency policy unresolved; invent no count, waiting period or SLA. |
| Real inference | E0 phishing-only release eligibility is unverified. Mark fixtures “Sample result — not a real analysis”; retain the same two labels, never a third sample class. Do not silently substitute legacy mixed-positive inference. |
| Privacy/deployment | Verify retention/cleanup/logging, measured host and public access policy before production copy/readiness claims. |

## Proposed Acceptance Checks

These are future implementation checks; this draft does not claim they passed.

1. Picker/drop select exactly one file, show metadata and wait for explicit Analyze; transmission notice is available before submission.
2. Both valid success labels show the correct filename; changing/removing/retrying clears old output. Double-clicks and late responses cannot create duplicate or stale results.
3. Every input/service/timeout/bad-payload case shows actionable error without a class. Progress phases are truthful; retries remain bounded and do not imply stopped server work.
4. Keyboard/screen-reader, focus, contrast, long filenames, phone/zoom and reduced-motion checks satisfy the proposed floor.
5. Verify real-model eligibility, privacy/transmission/cleanup and sample markings before claiming an operational demonstration.

## Source Reconciliation

The [PRD](../../prd/prd.md), [SPEC experience contract](../../spec/api-and-experience.md) and [updated plan](../../IAP_Web_Application_Plan.md) support this flow. Requirements for readiness/release/handover remain engineering evidence, without extra MVP screens.

The user's 2026-10-06 direction removes `.eml` export instructions from the current UX. See the [focused reconciliation](../reconcile-remove-export-guidance.md) for precedence over older export-help requirements. The other draft assumptions remain unconfirmed.

The user-supplied [Graph_IAP419t image](../imports/graph-iap419t.png) has now been directly inspected and imported unchanged, resolving the earlier missing-image finding. Its parsed-email structural-feature branch and cleaned Doc2Vec branch converge before a selected classifier; explicit scaler and concatenation order come from the plan/project instructions. The image's Legitimate/Spam/Phishing results and probability/indicators/inspector are superseded by the latest two-label MVP. Its corpus labels, trained-model selection and Model + results storage are architectural references, not proof of an eligible current model or persistent result history. Transient session results, real-release eligibility and verified privacy enforcement remain required.

See the [direct image extract](source-graph-image.md) and [source reconciliation](../reconcile-plan-graph.md) for the image-to-MVP differences. The image evidence update left the source image, plan, PRD and spec unchanged; it did not certify implementation. Prior missing-image records in [.working/](./) and the memlog remain historical.


# File: reconcile-remove-export-guidance.md

# Remove .eml export guidance — focused reconciliation

Updated: 2026-10-06.

The user requested: “Bỏ hướng dẫn xuất file .eml” (remove `.eml` export instructions). This direction supersedes older export-help clauses in the source plan, PRD, spec and architecture wherever those clauses require instructions for obtaining an `.eml` file. It does not change the accepted upload format or defer any existing inference/release requirement.

| Input | Current treatment |
| --- | --- |
| [DESIGN.md](../DESIGN.md) | Remove `export-guidance` from component tokens, visual table, wireframe and placement. Retain the privacy/transmission notice before Analyze. |
| [EXPERIENCE.md](../EXPERIENCE.md) | Remove export microcopy, disclosure behavior, expansion journey step, accessibility disclosure rule, A5 help detail and export-help acceptance check. Invalid-structure recovery asks the participant to choose another `.eml`. |
| [PRD](../../prd/prd.md), [SPEC](../../spec/SPEC.md) and [architecture](../../architecture/ARCHITECTURE-SPINE.md) | Synchronize current requirements with this user override; retain capability, requirement and decision IDs. |
| [Original plan](../../IAP_Web_Application_Plan.md), prior reconciliations, reviews, extracts and memlog entries | Preserve as historical/source records. Older export-help requirements do not override the current user direction. JSON export and model-release export are separate topics and keep their existing treatment. |

Both spines remain `draft`: the user has not confirmed the remaining A1–A5 assumptions. Basic one-file `.eml` upload instructions, filename/size, privacy/transmission notice, explicit Analyze, exact Legit/Phishing labels, all five states, other assumptions/tokens and the imported image remain in place. The single Analyze surface remains spine-only; this scoped update adds no mock or optional broad UX review.

## Scoped coverage checks

Checks will be recorded after validating the edited spines. These documentation checks do not establish implementation behavior or model eligibility.
