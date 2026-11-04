# Confirmed UX intake — 2026-10-05

The user requested an English fast draft, with unconfirmed choices marked so they can review and change them.

## Required behavior

- Manual checking of one email and graduation-project demonstration.
- Choose or drag and drop one `.eml` file, click **Analyze**, wait, and receive **Legit** or **Phishing**.
- Required states: no file selected, file selected, analyzing, success, and error.
- File errors and timeouts are operational failures, never a third email class.
- MVP shows the label only. Probability scores, indicators, and email inspector belong to future extensions.
- Result includes a readable text label; color alone cannot communicate the class.

## User-provided assumptions to preserve visibly

- **[ASSUMPTION A1 — audience]** Individuals checking email, team members, and lecturers watching the demo.
- **[ASSUMPTION A2 — devices]** Desktop priority, responsive to phone screens.
- **[ASSUMPTION A3 — style]** Compact, clear, light background and deep blue primary color. Exact values unconfirmed.
- **[ASSUMPTION A4 — layout]** One page with upload area, Analyze action, and result area. Exact composition unconfirmed.

## Approved inputs and priority

Use the existing PRD and web-application spec, cross-check against updated `docs/IAP_Web_Application_Plan.md` and `Graph_IAP419t`.

The latest user requirements take precedence: `.eml` upload and exactly `legit/phishing` results. The Graph's three Results labels must be interpreted as superseded; use it for the ML processing flow only.

If a source is missing, state that clearly. Do not imply that an unavailable diagram has been inspected. Do not rewrite source plans as part of this UX drafting task.

## Draft delivery

Produce `DESIGN.md` for appearance and `EXPERIENCE.md` for behavior. Keep both at `status: draft`; do not assert that assumptions have been approved. Represent page layout, upload, two-label results, and processing/error states. A fast draft does not require a creative-tool mockup or live application.
