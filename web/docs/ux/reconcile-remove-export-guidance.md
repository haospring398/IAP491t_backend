# Remove .eml export guidance — focused reconciliation

Updated: 2026-10-06.

The user requested: “Bỏ hướng dẫn xuất file .eml” (remove `.eml` export instructions). This direction supersedes older export-help clauses in the source plan, PRD, spec and architecture wherever those clauses require instructions for obtaining an `.eml` file. It does not change the accepted upload format or defer any existing inference/release requirement.

| Input | Current treatment |
| --- | --- |
| [DESIGN.md](DESIGN.md) | Remove `export-guidance` from component tokens, visual table, wireframe and placement. Retain the privacy/transmission notice before Analyze. |
| [EXPERIENCE.md](EXPERIENCE.md) | Remove export microcopy, disclosure behavior, expansion journey step, accessibility disclosure rule, A5 help detail and export-help acceptance check. Invalid-structure recovery asks the participant to choose another `.eml`. |
| [PRD](../prd/prd.md), [SPEC](../spec/SPEC.md) and [architecture](../architecture/ARCHITECTURE-SPINE.md) | Synchronize current requirements with this user override; retain capability, requirement and decision IDs. |
| [Original plan](../IAP_Web_Application_Plan.md), prior reconciliations, reviews, extracts and memlog entries | Preserve as historical/source records. Older export-help requirements do not override the current user direction. JSON export and model-release export are separate topics and keep their existing treatment. |

Both spines remain `draft`: the user has not confirmed the remaining A1–A5 assumptions. Basic one-file `.eml` upload instructions, filename/size, privacy/transmission notice, explicit Analyze, exact Legit/Phishing labels, all five states, other assumptions/tokens and the imported image remain in place. The single Analyze surface remains spine-only; this scoped update adds no mock or optional broad UX review.

## Scoped coverage checks

Proactive Pass 1 coverage checks passed for both edited spines: eight matching components across frontmatter and both tables, 20 resolved unique token references, 11 hex colors, five top-level states, two named-protagonist flows with numbered steps/climax/failure handling, canonical sections and 37 local links/source paths. Every imported/mockup/wireframe file present remains linked by both spines. Basic upload copy, transmission notice, binary labels and A1–A5 markers remain present; export UI/component/recovery clauses are absent.

Frontmatter validation checked lexical token paths and shape; no full YAML parser was used. These documentation checks do not establish implementation behavior or model eligibility. Optional broad UX review and application tests were not run for this scoped documentation update.
