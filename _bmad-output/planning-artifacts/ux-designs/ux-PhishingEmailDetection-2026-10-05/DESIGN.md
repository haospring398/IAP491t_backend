---
name: PhishingEmailDetection
description: Draft visual identity for a manual single-email classification demonstration.
status: draft
sources:
  - ../../prds/prd-PhishingEmailDetection-2026-10-05/prd.md
  - ../../prds/prd-PhishingEmailDetection-2026-10-05/addendum.md
  - ../../../specs/spec-iap-web-application/SPEC.md
  - ../../../specs/spec-iap-web-application/api-and-experience.md
  - ../../../specs/spec-iap-web-application/model-and-inference.md
  - ../../../specs/spec-iap-web-application/deployment-and-acceptance.md
  - ../../../specs/spec-iap-web-application/brownfield-and-evidence.md
  - ../../../../docs/IAP_Web_Application_Plan.md
  - imports/graph-iap419t.png
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
  explanation-list:
    foreground: '{colors.foreground}'
    fontSize: '{typography.meta.fontSize}'
    barFill: '{colors.secondary-text}'
    barTrack: '{colors.border}'
---

# PhishingEmailDetection — Design Draft

## Brand & Style

**[ASSUMPTION A3 — all visual values]** A compact, clear, light interface with deep blue primary actions. Every token above, including type, dimensions and radii, is a proposal for review. This identity supports a manual email check and project demonstration. No component library or existing brand system is confirmed.

Behavior and English microcopy live in [EXPERIENCE.md](EXPERIENCE.md). **Legit** and **Phishing** have equally readable, neutral styling; the written label communicates the class. An operational error receives separate error styling without becoming a classification.

The directly inspected [Graph_IAP419t image](imports/graph-iap419t.png) supplies an architectural reference for the email/ML flow. Its colored pipeline panels are not an approved product visual direction or page composition; **[ASSUMPTION A3]** tokens and **[ASSUMPTION A4]** layout remain proposals. See the [direct visual extract](.working/source-graph-image.md) and [source reconciliation](reconcile-plan-graph.md).

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
| explanation-list | `meta` list below the result in the same surface. Both directions use the same neutral bar fill on a border-colored track; direction is written in text, never shown by red/green. Bar width is proportional to strength with a small minimum visible width. |
| recovery-actions | Visible text-labelled secondary controls below error copy; no hover-only action. |

## Do's and Don'ts

| Do | Don't |
| --- | --- |
| Write the exact successful label and analyzed filename, then the model factors in text with neutral bars. | Add Spam, Unknown, a score, probabilities, red/green factor colors or an inspector to this MVP. |
| Make selected, pending and disabled states clear in text. | Depend on color, decorative badges or fake percentages. |
| Keep proposed visual choices tagged A3/A4. | Treat this draft as an approved brand or implemented application. |
