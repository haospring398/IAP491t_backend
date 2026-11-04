---
id: SPEC-iap-web-application
companions:
  - api-and-experience.md
  - model-and-inference.md
  - deployment-and-acceptance.md
  - brownfield-and-evidence.md
  - local-demo.md
  - ../../../AGENTS.md
  - ../../planning-artifacts/ux-designs/ux-PhishingEmailDetection-2026-10-05/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-PhishingEmailDetection-2026-10-05/EXPERIENCE.md
  - ../../planning-artifacts/architecture/architecture-PhishingEmailDetection-2026-10-05/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/architecture/architecture-PhishingEmailDetection-2026-10-05/.working/brownfield-audit.md
sources:
  - ../../../docs/IAP_Web_Application_Plan.md
  - ../../planning-artifacts/prds/prd-PhishingEmailDetection-2026-10-05/prd.md
  - ../../planning-artifacts/prds/prd-PhishingEmailDetection-2026-10-05/addendum.md
---

> Canonical contract: read this SPEC and every companion together. The user-approved local exception in local-demo.md takes precedence for the disclosed native legacy demo. Qualified phishing-only release requirements remain binding; architecture assumptions and draft UX are not certified by local execution.

# IAP Email Classification Web Application

Hosting update 2026-10-19: the current cleanup supersedes the earlier deployment selection. The demo runs locally and future hosting is unspecified. This update does not validate unrelated original product requirements, E0 or phishing-only quality.

Pipeline update 2026-10-20: the root offline pipeline now follows the 19-10 upstream version, adding a phishing-only training target, validation-based classifier/threshold selection and a BERT candidate. The upstream copy is incomplete and its 2026-10-19 candidate run is not reproducible with current code. The local demo still uses pinned run `e7dcdcc3551e46fc93582836f4a74976`; this update does not pass E0 or change the web contract.

Explanation update 2026-10-24: a successful result may now carry an exact per-result factor explanation (PRD FR-11, AD-14). It describes the served model's behavior, not phishing quality; presentation of dataset-shortcut factors such as `is_html` remains Q9.

## Why

Let a demo participant submit one exported email to the existing ML pipeline now, then upgrade to a qualified phishing-only release later. The current mixed-positive model can support a disclosed local operational demo; it cannot establish phishing-only accuracy or E0 provenance.

## Capabilities

- **CAP-1**
  - **intent:** A user can submit one exported email for analysis.
  - **success:** Picker/drop accept one suitable nonempty .eml within the configured whole-file limit, show filename/size and wait for explicit Analyze; unsuitable input is rejected before inference.
- **CAP-2**
  - **intent:** A user can obtain the active release's classification for the submitted email.
  - **success:** Actual local legacy analysis displays Legit or Spam / phishing with its filename and visible target disclosure; a future E0-qualified release displays Legit or Phishing. Failures and invalid/obsolete responses display no classification, and marked samples do not count as real inference. When the active release has an exact explanation method, success also shows up to five model factors with direction and relative strength under AD-14; failures and obsolete attempts show none.
- **CAP-3**
  - **intent:** A user can follow processing and recover from a failed attempt.
  - **success:** Five readable states, observed processing subphases, bounded recovery and attempt identity prevent duplicate or obsolete results.
- **CAP-4**
  - **intent:** Callers can determine readiness and the team can identify the release used.
  - **success:** Liveness and readiness differ; unsuitable artifacts/configuration/resources prevent readiness. Local operational readiness explicitly uses mixed-target semantics; phishing-only readiness additionally requires target eligibility. Internal attribution excludes email content.
- **CAP-5**
  - **intent:** The team can verify a reproducible release eligible for the requested classification target.
  - **success:** Local checks establish actual coherent artifacts, loaded dimensions and bytes-to-prediction behavior without quality claims; future E0 additionally establishes reviewed label provenance, target-specific evaluation and initial resource evidence.
- **CAP-6**
  - **intent:** The team can run and hand over a working demonstration.
  - **success:** The native local frontend/proxy/backend demo has tested run instructions and matching operational checks. Final deployment/fallback acceptance still requires agreed integration/integrity measurements, local Docker and run/deploy/rollback guidance.

## Constraints

- Follow local-demo.md for the explicitly authorized local legacy exception. Its mixed class 1 emits spam_or_phishing, displayed Spam / phishing; it must never silently emit phishing. Reserve phishing for confirmed phishing in an E0-qualified release. Neither target turns Legit into a guarantee of safety.
- The model is binary. The coordinated strict protocol can express legit, spam_or_phishing or phishing according to the active release; keep the strict completed envelope (label plus the optional AD-14 explanation) and existing endpoints/errors. A visible English local-demo notice discloses mixed spam/phishing positives and pending phishing-only evidence.
- For qualified phishing-only releases, class 0 requires reviewed legitimate provenance, class 1 confirmed phishing; exclude ordinary spam/unknown positives from the default benchmark. Numeric labels and display renaming do not establish eligibility. Real qualified acceptance depends on E0; marked samples remain sample evidence only.
- Selection never transmits content; explicit Analyze does. Retention copy requires verified enforcement. Follow five-state, attempt identity, observable progress and bounded retry behavior in api-and-experience.md and adopted UX, subject to the scoped label exception.
- Use same-run Doc2Vec, fitted scaler and one classifier; extract raw-byte features before cleanup in FEATURE_NAMES order, concatenate Doc2Vec first. Follow model-and-inference.md and AGENTS outcomes. Never import offline training/evaluation/corpus scripts into requests or fabricate fallback predictions.
- Explanations follow AD-14: exact contributions of the served classifier for that email, text-embedding dimensions grouped as one factor, at most five factors from the shared factor catalogue with direction and relative strength, the fixed English notice, no logging, and no explanation when the release lacks an exact method. Factors describe model behavior, never proof, confidence or quality.
- Preserve architecture AD-1 through AD-13, shared limits/schemas/errors/deadlines and tagged assumptions except the documented local target/native-packaging exception. Bound execution/concurrency/retries; keep credentials server-only, uploads transient and sensitive data out of logs.
- Native local services bind loopback, pin and verify one current run at startup and retain observed inference/resource settings. This is operational compatibility, not a self-contained training lock, historical preprocessing parity or approval of inherited negative Doc2Vec learning rates.
- Future upgrade/rollback replaces the whole compatible model/preprocessing/resources/environment release. Keep previous runs/pointer on failures. Qualified Linux/Docker packaging and measured future hosting remain requirements; no publication is authorized by the local demo.
- DESIGN/EXPERIENCE remain draft with UX A1-A5. Local scope adds truthful target disclosure, no mandatory model screen. Reconcile actual offline script/test drift before qualifying a new release; AGENTS conventions are required outcomes rather than proof of implementation.
- Report matching operational/quality evidence and actual case counts separately. Historical metrics, uploads and demonstration emails cannot prove phishing quality, Vietnamese accuracy or completed RQ2/RQ3.

## Non-goals

- In-app .eml export instructions, scores/confidence/risk, approximate or sampled explanations (for example LIME), raw feature values, inspector/full feature tables/model-info screens and JSON export. The bounded AD-14 factor explanation is in scope.
- A separate Spam or uncertain model class; Spam / phishing names the existing mixed positive class only.
- Gmail/extensions/accounts/batch/history/database/inbox automation; paid plans/trials, required GPUs and keepalive cron.
- Retraining, report regeneration or external publication in the local demo task; claims of E0, phishing-only quality, portable packaging or cloud viability from local checks.

## Success signal

Real privacy-scrubbed email completes the local browser-to-current-model session with matching filename, truthful target output, an exact factor explanation where supported and actionable errors without fabricated labels or factors. Separate future qualified acceptance requires E0, harness/API parity, repeatability/privacy, measured resources/quality costs and handover evidence defined in deployment-and-acceptance.md; local execution does not waive those gates.

## Assumptions

- **ARCH-A1:** Hexagonal boundaries, Next.js/FastAPI seed, package pins and immutable Linux packaging are architecture defaults pending locked-build/model compatibility evidence.
- **ARCH-A2:** The shared parser/body/token, deadline/reap, retry and progress-polling profiles are unmeasured defaults; qualify or revise them together before E2/E4.
- **ARCH-A3:** Future hosting is unspecified and requires suitable access protection and whole-container measurements; local operation does not qualify it.
- The roughly 15-working-day web estimate assumes an eligible release and compatible environment; relabeling/retraining needs separate estimation.
- **UX-A1:** Individuals, project members and lecturers are an assumed audience; Linh is illustrative, with no interviewed persona.
- **UX-A2:** Desktop-first responsive web with phone picker parity is the draft device direction.
- **UX-A3:** Light/deep-blue appearance and all exact tokens/contrast targets in DESIGN are provisional; no UI library is confirmed.
- **UX-A4:** One centered Analyze page and its wireframe/composition are proposed.
- **UX-A5:** Detailed controls, refresh, focus, keyboard, announcements, zoom and reduced-motion behavior in EXPERIENCE are proposed defaults.
- PRD question owners identify workstreams; the team still assigns individuals.

## Open Questions

- **Q1:** Which reviewed dataset snapshot and per-source provenance establish legitimate/phishing eligibility, and is a new release required?
- **Q2:** Which classifier/release, compatible environment, explicit inference settings, source revision and model-quality acceptance criteria will be certified?
- **Q3:** Can the adopted shared input/parser/schema/error profile qualify unchanged, or which coordinated revisions are needed before E2/E3 contract acceptance?
- **Q4:** Which warm/cold acceptance budgets, vector tolerance and measured clock-skew/deadline/retry/reap evidence qualify the initial timing profile before E2/E4?
- **Q5:** Which measured free host/account access gate qualifies the controlled cloud demo, and what shared abuse controls are needed if anonymous publication is requested?
- **Q6:** Which UX A1-A5 audience/device, appearance/layout, component-library and interaction/accessibility proposals should be confirmed or revised before UX approval?
- **Q7:** Which upstream revision supplies the missing `specialists.py`, `BertEmailClassifier`, `split_train_validation_test`, `prepare_semantic_text` and attachment-inspection code, so training, tests and the 53-feature candidate become reproducible?
- **Q8:** Should the qualified release use the Doc2Vec + engineered-feature classifier (AD-1/AD-3), or is BERT in scope? BERT requires a new architecture decision covering its text policy, resources and parity.
- **Q9:** How should factors reflecting dataset construction rather than phishing (currently `is_html`, present in 0.7% of legitimate and 94.9% of phishing test emails) be retrained, labelled or excluded before explanation acceptance?
