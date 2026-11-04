# Source extract: updated web plan and graph evidence

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

Prepared 2026-10-05 for UX drafting. This is a source extract, not a claim that the application or model is implemented. Source: [IAP_Web_Application_Plan.md](../../IAP_Web_Application_Plan.md). Latest user directions take precedence over older source wording: English UI, one selected or dropped `.eml`, an explicit **Analyze** action, and a successful result of **Legit** or **Phishing** only.

## Evidence boundary

The updated plan is present and was read as UTF-8. It names `Graph_IAP419t.drawio (1)(1).png` and reports that the image is titled `EMAIL THREAT DETECTION`. No matching Graph/IAP419/IAP491t file was found in the workspace, including a hidden-file scan with ignores disabled and dependency/data directories excluded. Therefore the image was not independently inspected in this UX pass; the graph details below are attributed to the plan's reconciliation table. No revised image or drawio file is established. No source originals were modified.

## Required product scope

- One email file, chosen with a file picker or drag-and-drop; a successful request displays exactly one classification.
- API labels are `legit` and `phishing`; English display labels are **Legit** and **Phishing**. Show the filename with the result.
- Invalid files, insufficient usable content, model unavailable, transport failure, busy service and timeout are processing errors. They are not a third email class and must never manufacture either success label.
- The user explicitly requires a click on **Analyze** after selection. Choosing or dropping a file alone does not start analysis.
- Probability/confidence, indicators, email inspector, 40-feature table, JSON export and model-info are extensions. Accounts, bulk scans, inbox integration, server history and a database are also outside MVP.
- A one-page workspace with upload and result areas is proposed by the plan. The user requests this layout but marks it as an assumption for review, alongside primary users, desktop preference, light theme and dark blue primary color. Preserve those assumption markers in the UX draft.

## Graph-derived ML flow, through the plan

The plan's graph table reports input `.eml` → MIME parsing and clean text → fusion of 40 engineered features and Doc2Vec → one selected trained classifier → results. Its request diagram specifies:

1. Web receives `.eml` and forwards it to the Python inference backend.
2. Validate the file and parse MIME.
3. Extract engineered URL/header/HTML/attachment and other features from the original email before cleaning. Transform with the previously fitted scaler.
4. Normalize subject/body text and infer a vector with the previously fitted Doc2Vec model.
5. Concatenate Doc2Vec followed by scaled engineered features and run one classifier from the same verified release.
6. Return `legit` or `phishing` only when inference succeeds.

The internal stages do not justify a detailed pipeline display in the MVP. User-facing status text may describe uploading, service startup and analyzing only when the implementation can substantiate those states. Do not invent numerical progress.

## Required UI states and behavior

| State | Source-backed behavior | Draft implication |
| --- | --- | --- |
| No file | One-file upload entry point | Picker/drop-zone guidance; Analyze disabled until a usable selection exists |
| File selected | Filename, size, explicit analysis action | English filename/size row and Analyze button; selection does not imply completed upload or analysis |
| Analyzing | Uploading, service startup and analysis states; no fake percentage; bounded retry | Text plus indeterminate activity indicator; block duplicate submission |
| Success | Filename and exactly Legit or Phishing | Clearly written label, not color alone; no score or inspector |
| Error | File/content/model/timeout messages; choose another file or retry | State-specific English message and useful action, with no classification label |

The plan requires no mixing a previous file's result with a newly selected file and no duplicate sends during processing. Result state must be associated with the exact selected request. Text is required alongside color. Clearing/replacing the selected file and detailed keyboard/focus behavior are UX design choices to specify, not behavior already implemented.

## File, timeout, privacy and safety constraints

- Proposed maximum upload: **2 MiB** for the complete `.eml`, including encoded attachments; one file per request. This is a plan proposal rather than a measured hosting guarantee. Draft helper text can show `One .eml file · up to 2 MiB`, with the limit marked as inherited/proposed.
- Extension alone is insufficient. Validate actual email structure, empty files, usable content, MIME defects and parser limits before inference. Exact parser acceptance policy remains unspecified.
- Startup timing is unmeasured. Show a textual startup state only when observed; do not promise a UX duration.
- A timeout and bounded retries are required; exact deadlines and retry count are not set by this plan. A Next.js route timeout does not itself stop Python inference, so Retry must not blindly create overlapping work.
- Service overload is rejected with a message rather than an unlimited queue. Non-JSON provider startup responses also need handling.
- Store results only in browser memory for the current session, with no required database. Do not persist raw email or log body, headers, subject, sender, recipient or filename; clean any temporary spool files on success and failure.
- Email is sent for server processing; it is not a local-only check. Privacy copy must accurately describe implemented retention and transmission, avoiding unsupported promises.
- MVP does not render email HTML, open links or attachments, or automatically fetch URLs, DNS, WHOIS or attachments. Do not expose email content merely to fill the results area.
- Error responses use `error.code`, `error.message`, and `request_id`; do not show stack traces. The UX may map these to readable English, without exposing HTTP codes as required product content.

## Source conflicts and unresolved evidence

| Source wording | Current resolution |
| --- | --- |
| Graph Results reportedly has Legitimate, Spam, Phishing | Superseded: displayed results are Legit and Phishing; no Spam or uncertain result. This extract does not modify the missing image. |
| Graph reportedly includes probability, detected indicators and inspector | Deferred beyond MVP under the latest user instruction. |
| Graph refers to model plus results storage | Model artifacts remain necessary; results are session-only. |
| Current/historical positive class reportedly mixes spam and phishing | Cannot be relabeled as phishing. Genuine inference acceptance requires target provenance and a matching verified release; marked UI fixtures may be drafted meanwhile. |
| Historical metrics or project observations copied from ZIP/report | The plan acknowledges source snapshots and no implemented application. UX drafting does not reverify runtime artifacts or authorize publication of accuracy claims. |

Missing evidence: independently accessible graph image; exact parser rules; agreed upload-limit boundary handling; actual cold/warm performance; timeout and retry policy; and eligibility of a real model release for `legit_vs_phishing`. These limit implementation/readiness claims, but do not prevent the requested marked UX draft.
