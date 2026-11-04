# Web development handover

These are snapshots of the parent project's canonical documents with local
document links adjusted for this folder. `manifest.json` records their source
paths and hashes. Update the originals through the project's planning workflows
and run `node web/scripts/sync-docs.mjs` to refresh this handover folder.

Read these first:

- [SPEC and companion contract](spec/SPEC.md): capabilities, API, errors and acceptance.
- [Design](ux/DESIGN.md) and [Experience](ux/EXPERIENCE.md): visual and behavioral defaults.
- [Architecture spine](architecture/ARCHITECTURE-SPINE.md): shared decisions and limits.
- [PRD](prd/prd.md): product scope and requirements.
- [Frontend integration record](implementation/spec-integrate-zip-frontend.md): delivered work and actual verification.
- [Local real-model demo contract](spec/local-demo.md): the approved mixed spam/phishing scope and future release upgrade.
- [Backend run instructions](backend/README.md) and [local demo implementation record](implementation/spec-local-real-model-demo.md): setup and actual verification.
- [Backend relocation record](implementation/spec-move-backend-to-web.md): current package paths and commands after moving into web/backend.

PRD and architecture describe the final phishing-only target; UX remains draft.
The current spec explicitly permits a local demo using the existing mixed
spam/phishing model, with its positive output displayed as Spam / phishing.
This scoped exception takes precedence over older fixture-only restrictions.
E0 phishing-only qualification, portable Docker packaging and cloud acceptance
remain pending. Read the implementation record for the actual checks performed.
Older reviews and the [original web plan](IAP_Web_Application_Plan.md) provide
historical context; the current spec and local-demo companion govern this scope.

[Pipeline context](PROJECT-CONTEXT.md) describes the root Python pipeline.
The service code lives in web/backend; pipeline modules, corpora, model artifacts
and the Python environment remain in the parent project. Older implementation
records preserve the paths used when they were written; use the current backend
README for commands.
