---

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.
name: Application plan and Graph input reconciliation
status: complete-with-suggested-source-updates
created: 2026-10-05
scope: Application plan and unchanged imported Graph against this run's architecture spine
sources:
  - ARCHITECTURE-SPINE.md
  - ../../../../docs/IAP_Web_Application_Plan.md
  - ../../ux-designs/ux-PhishingEmailDetection-2026-10-05/imports/graph-iap419t.png
source_files_changed: false
---

# Plan and Graph Input Reconciliation

The [application plan](../../../../docs/IAP_Web_Application_Plan.md) was read in full, and the [unchanged imported Graph](../../ux-designs/ux-PhishingEmailDetection-2026-10-05/imports/graph-iap419t.png) was directly inspected with `view_image`. This was a separate pass after the UX-pair reconciliation. The final available [architecture spine](ARCHITECTURE-SPINE.md) was reread, including its updated manifest schema, bounded MIME/token semantics, deadline propagation, phase observation, starter profile and E0–E5 delivery gates.

**Result:** No material plan-required constraint is missing from the updated spine. The plan's optional alternative backend hosting branch has been narrowed by an explicit architecture choice. The original Graph retains superseded product scope and is reference data, not an instruction to add it back.

Only this reconciliation report was created. No plan, spine, code, source image, or imported image was edited; no tests, model loading, inference, training or deployment were performed. Imported Graph SHA-256 observed during this pass: `a5649657fe85867616ce388389f958deeb439bad8066ae11b46d6d18e82c911e`.

## Constraint reconciliation

| Plan requirement | Updated spine coverage |
| --- | --- |
| §§1, 3, 6: manually choose/drop one `.eml`, explicitly Analyze, show filename and only Legit/Phishing on successful processing; no score/indicator/inspector/account/history/database extension | AD-5/6/8/9 and Deferred. Exactly five UI states; failures never become a class; source UX retains picker/drop presentation. |
| §3.1: reviewed legitimate class 0 and confirmed phishing class 1; exclude ordinary spam and unknown positives; do not rename mixed-positive artifacts or reuse legacy metrics as phishing-only results | AD-2 and E0 qualification. Offline team qualification and evidence references precede runtime readiness; fixtures cannot satisfy real acceptance. |
| §§2, 4.2, 5, 8 E0/E2: same-release Doc2Vec, scaler and one selected classifier; raw engineered features before cleaning; resource/inference policy and object widths/classes verified; `transform`/`infer_vector`, no request training | AD-1/2/3/4/11 and E0 qualification. Feature schema comes from `FEATURE_NAMES`; concatenation order is Doc2Vec then scaled engineered features. Existing 40+100=140 is an expectation, not a substitute for loaded-object verification. |
| §§4.1, 4.3, 8 E4: Next.js frontend and token-holding Route Handler, separate Python backend; future hosting unspecified | AD-10/11/12 retain resource/startup, multipart, deadline, recovery and restart qualification. The current demo runs locally; no paid/trial/GPU/database/keepalive dependency is adopted. |
| §§6–7: bounded upload, actionable canonical errors, minimal liveness/readiness, genuine sending/startup/processing states, timeout and bounded retry | AD-5/6/7/8/11/13 and Consistency Conventions. Strict classification success remains two fields. Separate phase observation adds no score, label, screen or history; unknown phase remains generic Analyzing. |
| §§7–8: classifier/threshold selection uses separate validation, appropriately grouped independent test, parity harness, repeat/order determinism and vector tolerance | AD-2/3/4 and E0 qualification. Classification metrics use labels; positive-class scores/index govern ROC-AUC and any threshold. Legacy ranking does not automatically select XGBoost. |
| §§8 E3–E5, 12: real browser-to-model flow, no stale or duplicate result, safe secrets/logs, measured warm/cold behavior, meaningful frontend/API/browser checks and tested local/deploy/rollback instructions | AD-5/7/8/9/10/12 and Delivery gates. Sample, local, model qualification and cloud acceptance remain distinct. Architecture does not assert any check passed. |
| §11: bytes/structure instead of client MIME claims; bounded MIME/parser output; temporary cleanup; no content/filename logs; no URL/DNS/WHOIS/attachment fetching or execution; one admitted inference with no unbounded queue; backend work must stop at its own deadline | AD-6/7/9. Root/part/depth/decoded/token counting is explicit; rejection never truncates model input. Supervisor owns spools/IPC and bounded terminate/kill/reap; internal structure warnings do not widen logs or responses. |

## Source differences and suggested updates

| ID | Difference | Reconciliation / suggested source update |
| --- | --- | --- |
| PLAN-R1 — hosting selection superseded | The 2026-10-19 cleanup removes the earlier provider selection and deployment integration. | Keep local frontend/proxy and Python service available. Any future host requires a separate measured packaging/resource/access decision; this cleanup does not qualify unrelated product requirements. |
| PLAN-R2 — progress contract handoff | Plan §7 enumerates analyze and health endpoints but does not list the architecture's separate current-attempt phase channel. Plan §§6/8 still requires truthful observed startup/processing presentation. | Reference AD-13's shared, authenticated, runtime-validated status contract and bounded polling. Preserve the original two-field classification success and five top-level states. Generic provider HTML/503 or elapsed time cannot itself prove a phase. The updated spine already supplies the necessary integration decision. |
| PLAN-R3 — historical artifact evidence | Plan §§2/4.3/5 describe the source ZIP's LFS-pointer artifacts and its declared model sizes/ranking. The current workspace audit observes a selected immutable-run manifest and different actual local file sizes, without certifying current artifact integrity or target eligibility. | Keep the ZIP observations explicitly historical when deriving stories; use the current run/audit for local inventory and E0 verification for all runtime or target claims. Neither source proves the current model is eligible or future hosting fits. XGBoost remains an unqualified candidate, not a settled classifier. No source facts were rewritten in this pass. |

## Direct Graph reconciliation

| Visible reference data | Binding interpretation for this MVP |
| --- | --- |
| `.eml` input; parsed-email branch to 40 structural features; cleaned text to Gensim Doc2Vec; concatenation into one vector | Retain the two representation branches and raw-before-clean feature extraction. The Graph omits scaler and branch concatenation order; AD-3 and plan §4.2 supply both. It establishes neither actual Doc2Vec mode nor proven saved dimensions. |
| Trained selected classifier, with class-label and probability outputs | Serve one E0-qualified classifier. Probability may participate in a qualified internal decision rule, but is absent from MVP responses/UI. “Best selected” is not proof that a current classifier was correctly selected or evaluated. |
| Results: Legitimate, Spam, Phishing; probability score; detected indicators; email inspector | Superseded by the latest binary MVP and updated plan §3: exact domain labels `legit|phishing`, English Legit/Phishing, filename only on success. No Spam/Unknown result, risk score, indicators or inspector is restored. |
| Offline training: Enron → Legitimate, Nazario → Phishing, SpamAssassin → Spam; train/validation/test; compare/select | Retain offline separation and independent validation/test discipline. Dataset names and the pictured labels do not establish record provenance or qualify a binary release; AD-2/E0 still controls eligibility. |
| Frontend ↔ Backend API ↔ Model + results storage; Flask / FastAPI alternatives | Current choice is Next.js proxy plus FastAPI, immutable model storage, and transient browser/request memory. The storage icon neither requires a database nor authorizes persistent result history. The Graph's alternative framework names are descriptive reference options. |
| Colored panels, numbered stages and pipeline arrows | Architecture illustration only. They do not approve UI branding, require a multistage screen/progress percentage, or override draft UX A1–A5. |

The Graph remains unchanged and therefore retains those historical scope differences visibly. No revised diagram or diagram certification is claimed. Mandatory label, privacy, validation, timeout, parity, model-eligibility and handover constraints are preserved by the spine; no additional product surface is required by this reconciliation.
