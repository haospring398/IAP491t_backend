# Draft Spine Pair — Pass 1 Coverage Notes

2026-10-05. Proactive mechanical coverage walk from `bmad-ux/references/validate.md`; this is not an opt-in UX review, approval or implementation test.

| Category | Coverage |
| --- | --- |
| Flows | Exact **Source-described session** has an illustrative, assumed Linh, numbered steps, explicit climax and failure path. Recovery has the same structure. FR-1–6 land on Analyze; FR-7–10 remain explicitly retained engineering/readiness/handover evidence rather than invented UI surfaces. |
| Tokens | DESIGN defines flat hex colors, nested typography and rounded/spacing/component objects. References in both spines point to defined token paths; contrast targets are stated, without an implementation certification. |
| Components | Both tables contain exactly page-heading, upload-area, file-summary, file-controls, analyze-button, export-guidance, privacy-note, status-result-area and recovery-actions. Each has visual and behavioral rules. |
| States | One Analyze surface; no-file, file-selected, analyzing, success, error. Two success variants and truthful progress subphases are explicitly subordinate. Empty/cold entry, input/focus, connectivity/unready/busy/timeout/provider/bad-payload failures, disabled state and stale-response suppression are covered. There is no account/permission UI scope. |
| Visual references | No files in imports, mockups or wireframes were found. Analyze is explicitly spine-only with inline ASCII composition in DESIGN; no visual orphan. Spines-win-on-conflict is stated once. |

Nonblocking draft gaps remain explicit: A1–A5 unconfirmed; graph image unavailable for independent inspection; upload/parser and retry/runtime policies open; eligible release, privacy enforcement and deployment unverified. Source frontmatter/links should receive the parent's mechanical path check. No source original or application/model artifact was modified by distillation.

## Current evidence update — 2026-10-05

The no-import/missing-image findings above describe the first draft pass and are historical. The user subsequently supplied [Graph_IAP419t](../imports/graph-iap419t.png), now imported unchanged and directly inspected. Its [visual extract](source-graph-image.md) is linked from both [DESIGN.md Brand & Style](../DESIGN.md#brand--style) and [EXPERIENCE.md Source Reconciliation](../EXPERIENCE.md#source-reconciliation), and the [current reconciliation](../reconcile-plan-graph.md) records the two-label/output/storage differences. Both spine source lists include the import, so it has an explicit architectural purpose and is not an orphan or a UI mockup. Analyze remains spine-only; A3/A4 visual assumptions and unresolved implementation evidence remain unchanged. This note updates source coverage only; no broader UX review or application tests ran.
