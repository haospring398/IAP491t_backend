---
title: 'Remove the previous serverless deployment integration'
type: 'chore'
created: '2026-10-19'
status: 'done'
route: 'dispatch'
baseline_commit: '009ad857a45eded21d80059ae9dd49fc85866cab'
frontend_baseline: '1b3f3a38e46658a9d5c4658fd11658b5f0490c3d'
workspace_baseline: '5cce305cf52d28bce73a2db8f3e8e933b48bd4e9'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="explicit user request">

## Intent

Remove everything maintained for deploying the web application to the previously selected serverless provider, including its backend private Blob release mechanism. Keep the existing local Python inference service, frontend, shared API behavior, model files and AI pipeline working. The user explicitly requests deletion and previously authorized publishing frontend/backend changes.

## Boundaries & Constraints

**Always:** Apply the cleanup in the original workspace and both separate publication checkouts. Preserve unrelated user edits and current remote history. Local commands remain Python 3.11 `.venv/Scripts/python.exe -m web.backend` and Node 24 `npm.cmd run dev`. Preserve token authentication, upload/MIME limits, enforced proxy/browser/backend deadlines, serial admission/recovery and truthful mixed-class labels. Keep framework dependencies and official Next.js source links, even when their GitHub organization shares the former provider name. Preserve generic future hosting requirements where useful; remove provider-specific setup, limits, account instructions and declarations that provider selection is still binding.

**Never:** Train, evaluate, alter model bytes, change the selected run/pointer, touch corpus/CSV files, edit agent instructions, rewrite Git history or perform provider account/resource operations. Do not copy or delete either environment or traverse a model symlink. Do not change unrelated user frontend commits. Root `.git` is read-only and has a huge corpus: do not run whole-root status/diff or stage root files. No commit/push by the implementation agent; the parent handles publication.

</frozen-after-approval>

## Code Map

- Original workspace: `C:/Users/PC/Downloads/IAP/IAP491-Phishing_Email_Detection/PhishingEmailDetection`.
- Backend checkout: `C:/Users/PC/AppData/Local/Temp/iap-backend-publish-20d4e4ae30aa41b0aa8e0152f27d0212`, clean main at baseline. Local-only source baseline `bba9203d69f088a152355fad9da74a9ca493ae02` is available. Restore only deployment-modified local adapter/service from this revision, then apply coordinated shared policy cleanup. Keep trusted local verifier and requirements-ml.txt.
- Frontend checkout: `C:/Users/PC/AppData/Local/Temp/iap-web-cleanup-20261019`, clean master at frontend_baseline; recent user commits deleted obsolete root Vite files. Preserve those commits. Old frontend temporary checkout is unusable; never use it.
- Backend-only additions to remove: `.python-version`, `pyproject.toml`, `uv.lock`, `app.py`, `vercel_app.py`, `vercel.json`, `DEPLOYMENT.md`, `RELEASE.md`, `scripts/export_release.py`, `scripts/verify_release.py`, `web/backend/cloud_release.py`, `web/backend/cloud_worker.py`, `web/backend/tests/test_cloud.py`. Remove cloud-related ignore entries and README sections; retain generic secret/model/environment ignores, including exact `dumped_models` to protect the existing ignored symlink.
- Local `web/frontend/app/api/analyze/route.ts`: platform-only maxDuration and matching unit assertion; `handlerSeconds` exists in shared policy/schema, frontend generated types/validation and backend policy.py. Remove that unused deployment ceiling coherently in all three copies, retaining browser/proxy/backend ordering. Regenerate generated contracts instead of editing by hand.
- Canonical docs: `docs/IAP_Web_Application_Plan.md`, `_bmad-output/specs/spec-iap-web-application`, `_bmad-output/planning-artifacts`, `_bmad-output/implementation-artifacts/spec-integrate-zip-frontend.md`, `deferred-work.md`. Use targeted edits preserving non-deployment content. Include hidden memlogs and working review inputs, replacing obsolete hosting decisions with neutral local/unspecified-host descriptions; remove provider limits/references, not Next.js upstream citations. Record that current cleanup supersedes the earlier deployment selection without implying unrelated original product requirements were validated.
- `web/scripts/sync-docs.mjs` refreshes `web/docs` linked snapshots and hashes from canonical documents. It does not prune deleted snapshots: explicitly remove obsolete mirrored files if any.
- Delete dedicated `_bmad-output/deployment-artifacts/vercel-backend` (including generated archive copies and metadata) and `spec-vercel-backend.md`, `spec-vercel-cpu-bundle.md`; remove their deferred-work entry. Before any recursive deletion resolve/verify exact absolute path is within the named workspace target; never delete dumped_models or a computed unverified path.

## Tasks & Acceptance

- [x] Remove standalone backend deployment files and cloud hooks; document local startup and model provisioning only.
- [x] Remove frontend deployment settings/docs, coordinate policy/schema validators/types in workspace and publication copies, preserving unrelated frontend changes.
- [x] Remove dedicated deployment artifacts/specs and provider instructions throughout canonical docs, then refresh/prune handover snapshots.
- [x] Produce a concise change summary and unified review diff in Windows TEMP, including original-workspace text changes (capture before content before editing) and both checkout diffs. Exclude binary archive contents, caches, environment files, models and corpus. Report diff absolute path.
- [x] Run meaningful available verification: original local backend regression discovery, frontend contracts check, unit tests, lint, build; verify publication sources match intended changed components. Do not install packages without need. Linux cached environment may be used if native backend dependencies are insufficient, but report actual environment and failures. Do not add mirror tests for deletions.

**Acceptance Criteria:**
- Given the cleanup, when scanning maintained source/docs, then deployment integration, private Blob release path and provider setup instructions are absent; allowed matches are framework package names/upstream source URLs and this task's removal inventory.
- Given a configured local verified run, when existing regression checks execute, then local inference/auth/transport behavior remains intact.
- Given original selected artifacts, when cleanup finishes, then pointer SHA remains `8c1ec9ab1ffb3d7215194b8b0addd29e072c08bf3e9d23ec856d50a1154ed603` and manifest SHA remains `5407b0aac9118f8f0611205c7d84d773bd0af74f7107459d5ee2c37a19ec11bb`.

## Implementation Notes

Investigation found no provider SDK in the original frontend. Keep Next tracing roots required for sibling contracts. Source deletion does not remove previously created remote resources or existing Git history. Original workspace files can contain unrelated modifications: edit only relevant fragments. Publication repositories were fetched before implementation.

Removed 13 standalone cloud integration files and restored the local adapter/service while retaining generic per-request body cleanup. Removed the unused deployment handler ceiling coherently from shared schemas, policy validators, generated types and route tests. Refreshed 55 handover snapshots. Deleted nine dedicated deployment artifact files totaling 614,102,060 bytes, including two archives totaling 614,092,800 bytes, and both previous deployment specs. The obsolete E4 provider fallback was updated to unspecified future hosting/local operation.

Review diff (line endings normalized for review): C:/Users/PC/AppData/Local/Temp/iap-remove-cloud-evidence-20261019/review-normalized.diff. Source before-capture, separate publication diffs and a verified-path deletion summary are in the same evidence directory.

Canonical frontend: contracts:check, all 26 unit tests, lint and Next production build passed. Sandbox initially blocked Node child spawn and Python multiprocessing pipes; tests were rerun with the required process permissions. Native backend discovery is pending completion of that rerun. No source change was made to work around sandbox restrictions.

Native Windows Python 3.11 backend rerun completed: 24 tests passed in 141.830 seconds, including real-model API, identity/authentication, bounds, deadline/reap/recovery and repeated/reordered/restarted samples. Reviews completed with two diagnostic layers filing findings and the edge-case layer returning an empty list. The previous pending status above is superseded by this observed result.

## Review Triage Log

| Finding | Verdict | Evidence and route |
| --- | --- | --- |
| Blind 1: generic archive ignore protections removed | medium | The backend ignore diff removed tar/release patterns, allowing locally packaged trusted models to be staged accidentally. Patch: retain generic archive exclusions while removing the provider-specific ignore entry. |
| Blind 2: deleting cloud lock loses qualified local dependency resolution | false | The removed lock targets Python 3.12 cloud runtime; the documented native Python 3.11 profile already uses requirements-ml/API pins and trusted original environment. No qualified portable local lock was claimed or removed. Retaining that cloud environment would contradict the requested removal; creating a new local lock is separate qualification work. |
| Blind 3: local provenance is lost with cloud startup logging | false | Adapter.metadata still records manifest/code hashes, runtime package versions and inference settings, and Supervisor.metadata retains it. Removed initialization/peak-RSS logging only existed in the deleted cloud startup branch. Local provenance checks passed; no local startup record consumer was removed. |
| Blind 4: unchanged policy version lacks shape-change guidance | low | All current schema/policy/type/validator copies match, but the shared README lacks explicit coordinated-upgrade guidance for removal of the deployment ceiling. Patch a dated compatibility note; wire responses stay version 1. |
| Blind 5: worker body lifetime lacks regression verification | medium | Existing erasure tests observe admission/status only and do not detect a raw upload retained while the resident worker waits. Patch with a lifetime observation at the next actual receive boundary for success and rejected input. |
| Blind 6: local readiness wait is not explicit | low | Standalone README lists ready 200/503 and its check command, but does not tell the user to wait before the first upload after restoring local startup. Patch concise waiting/startup-failure guidance in local setup instructions. |
| Blind 7: provisional 400 MiB target becomes inconsistent | low | PRD A2/NFR-3 and plan summary retain an unqualified future target while replacement hosting requirements omit its status. Patch explicit retention as a future research target, not a cap or guarantee for the existing local legacy demo. |
| Blind 8: rewritten historical reviews retain old review dates | low | Modified review text includes current hosting decisions while original review headers/verdicts remain dated October 5. Patch dated amendments distinguishing cleanup edits from the historical review and runtime evidence. |
| Blind 9: preserve obsolete provider decisions in memlogs | false | The user explicitly requested removing the provider integration and its related instructions. Restoring those obsolete entries would conflict with that request; current memlogs contain dated superseding decisions and Git history is preserved. Historical review amendment notes address provenance without reintroducing removed setup. |
| Blind 10: UX source extract retains removed provider timing/line citations | low | The source extract still claims about-minute startup from deleted provider evidence and points to shifted line numbers. Patch unmeasured-startup wording and remove obsolete numeric citations while keeping its linked source document. |
| Gap 1: request-body release not verified | medium | Verified test gap: startup/status erasure assertions do not observe the previous upload's lifetime. Same cause and patch as Blind 5; exercise the real resident worker loop with tracked payloads for success and rejection. |

## Completion Evidence

All seven patch groups were corrected: generic archive ignores restored; coordinated contract compatibility documented; worker lifetime regression added; local readiness waiting documented; the future unqualified 400 MiB target clarified; 17 historical materials received dated amendments; stale UX startup estimates and numeric citations were removed. No findings were deferred.

The additional model-free lifetime test passed for both success and rejection. A temporary in-memory worker without cleanup failed both cases, confirming the test detects the retention defect without altering production source. The 24-test real-model backend discovery and all 26 frontend unit tests, contracts check, lint and production build passed before these final documentation/test-only patches; runtime code was unchanged afterward. The new focused test was run successfully after patches. No redundant full suite was run for documentation-only corrections.

Revalidated all 55 source/snapshot hash pairs, canonical/publication runtime and test parity, unchanged selected pointer/manifest hashes and clean whitespace checks. Removed artifact/archive byte totals are recorded above; the original model release remains intact. Existing root pipeline tests were not run because this change does not alter the AI pipeline; no pipeline-wide pass is claimed.

Published and verified remote heads:
- Backend main: `762c343242f9e7b922d0ef8e6e9d8f40f2983fea`.
- Frontend master: `20658d18441b905f453c5c210a00a684b4a3043f`.

Both publication working trees are clean. Original-workspace edits remain in its filesystem; its read-only Git metadata was not modified. Existing remote deployment/storage resources were not accessed or deleted; the user previously chose dashboard-managed account operations.
