# Reconciliation: updated web plan and Graph

The [updated web plan](../IAP_Web_Application_Plan.md) agrees with the latest UX intake: choose or drop one `.eml`, click **Analyze**, and show **Legit** or **Phishing** only after successful analysis. API labels remain `legit` and `phishing`. File errors, unavailable processing and timeout are request states, never additional classifications. The latest intake adds English interface copy and a quick draft with clearly marked assumptions about users, device preference, colors and layout (plan §§1, 3 and 6).

The user-supplied [Graph_IAP419t image](imports/graph-iap419t.png) has now been directly inspected and imported unchanged from `Graph_IAP419t.drawio (1).png`. Its title is EMAIL THREAT DETECTION / SYSTEM ARCHITECTURE. This resolves the previous missing-image evidence gap; earlier extract/memlog entries remain historical. The [direct image extract](.working/source-graph-image.md) records visible content and evidence limits.

The image shows `.eml` → MIME parsing, a parsed-email **40 structural features** branch alongside a cleaned **Doc2Vec** text branch, concatenation, one selected trained classifier and Predict. The ML contract adds the fitted scaler, **Doc2Vec followed by scaled engineered features**, and same-run/release artifacts from plan §4.2 and [project instructions](../PROJECT-CONTEXT.md), “Conventions that differ from defaults”; those scaler/order requirements are not explicitly annotated in the picture. Engineered features remain extracted before cleaning.

| Directly observed in the image | Current resolution |
| --- | --- |
| Results: Legitimate, Spam, Phishing | Successful MVP output is exactly **Legit / Phishing**; errors are processing states. |
| Probability in Predict/Results; detected indicators; email inspector | Deferred extensions, with no score, indicators or inspector required on the MVP page. |
| Offline Enron → Legitimate, Nazario → Phishing, SpamAssassin → Spam; Train/Validation/Test and Compare → select | Reference architecture only. Verify actual label provenance and an eligible `legit_vs_phishing` release; neither the picture nor a renamed mixed-positive class establishes eligibility. |
| XGBoost, RF, SVM, MLP / … classifier choices | Candidate examples; no deployed classifier selection or benchmark is certified. |
| Frontend ↔ Flask/FastAPI Backend API ↔ Model + results storage | Preserve necessary model artifacts; keep results transient in browser-session memory with no MVP database/server history (plan §§1.1 and 4.1). |
| Colored architecture panels and component illustrations | Architectural reference only; A3 visual tokens and A4 page layout remain unconfirmed UX assumptions. |

No source image, plan, PRD, spec or project instructions were modified. No revised diagram is asserted.

The draft does not certify a model's eligibility for `legit_vs_phishing`, actual application behavior, measured latency or implemented privacy controls. The plan requires verified label provenance rather than renaming a mixed spam/phishing positive class; any sample results must be clearly marked. Session-only results, no retained raw email, no email-content/filename logging and safe email handling remain implementation requirements to verify (plan §§3.1 and 11).
