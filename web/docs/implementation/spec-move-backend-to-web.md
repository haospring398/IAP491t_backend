---
title: 'Move the local backend into web'
type: 'chore'
created: '2026-10-08'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
baseline_commit: '152c1876dbd718778fa225182c42d18a30db428b'
context: []
---

<frozen-after-approval reason="The user explicitly requested moving backend into web">

## Intent

**Problem:** The backend remains outside the web directory that groups the web application's files.

**Approach:** Move backend into web/backend and update package imports, root-relative resource resolution, startup commands, existing tests and handover documentation. Preserve the current model, preprocessing, API and frontend behavior; keep training artifacts and the root Python environment in place.

</frozen-after-approval>

## Implementation Notes

- Mechanical relocation with no new API or irreversible operation; no intent gaps. Run the existing backend suite and real-model browser smoke rather than adding duplicate tests. Commands continue from the project root using `.venv/Scripts/python.exe -m web.backend`; tests use `web/backend/tests`.
- Policy must resolve the project root from its new depth, allowing access to web/contracts, root preprocessing and same-run model artifacts. Update adapter provenance paths, supervisor/worker imports, mocks, sample locations and browser test launch. Update current documentation and synchronize snapshots; preserve historical planning intent.
- Git's corpus-sized index has stale stat entries after the previous commit; preserve unrelated staging and use scoped content checks rather than a whole-tree refresh.
- Initial verification: 24 backend tests passed in 77.244s; actual-model Edge smoke passed five MIME comparisons and unavailable-result clearing in 20.513s; frontend TypeScript check passed. Handover initially verified 55 source/snapshot hash pairs and 201 relative links.
- Review corrections add an explicit web package to prevent installed packages shadowing the new namespace and record the relocated policy module in internal code provenance. Preserve all inference methods and resources; compare baseline inference methods against current vectors and labels for the five samples.
- Final verification: all 24 backend tests passed in 51.506s after review corrections. Five samples produced exactly equal vectors and labels using the previous commit's vector/analyze methods and the current methods on the same verified artifacts; email validation AST is unchanged. Package resolution chose the local explicit web package over a controlled shadow package, and policy provenance is present. Ignore Python caches at workspace level. No root pipeline, model artifacts, pointer, API envelope or frontend behavior changed. One existing agent-guidance improvement was deferred; the relocation and operational verification are complete.

## Review Triage Log

- Namespace package shadowing: medium, patch. Python can select a later regular web package over a local implicit namespace; web/__init__.py makes the root-local package deterministic.
- Missing policy provenance: low, patch. The relocated policy's root resolution affects resources; include its hash in internal metadata without changing HTTP results.
- Root agent guidance omits backend paths/tests: low, defer. Existing AGENTS.md only describes the root pipeline and already omitted the prior service; current backend README is correct. The workflow explicitly defers changes to agent guidance.
- Baseline inference comparison missing: low, patch verification. Existing boundary tests pass but a five-sample old-method/current-method comparison strengthens preservation evidence without changing model artifacts or adding redundant tests.
- Test harness hides startup stderr: low, rejected. Stderr suppression predates this relocation; imports and actual readiness pass. Safe operator stage logs remain available during normal startup. Bounded failure-log capture would add diagnostic handling beyond a simple path correction and is unnecessary for this verified move.
