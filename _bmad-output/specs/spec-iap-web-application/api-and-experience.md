# API and Upload Experience

The user-approved [local demo contract](local-demo.md) overrides conflicting target labels, E0-before-real-inference and native-versus-qualified packaging clauses only for the disclosed local legacy demo. Detailed qualified-release requirements below remain the future phishing-only acceptance contract. Local success uses legit or spam_or_phishing; phishing is reserved for the qualified target. Actual mixed-model checks do not pass E0 or cloud/Docker acceptance.

Applies to CAP-1 through CAP-4. [EXPERIENCE.md](../../planning-artifacts/ux-designs/ux-PhishingEmailDetection-2026-10-05/EXPERIENCE.md) owns detailed behavior and English copy; [DESIGN.md](../../planning-artifacts/ux-designs/ux-PhishingEmailDetection-2026-10-05/DESIGN.md) owns visual tokens and composition. Both are adopted draft companions; their A1-A5 assumptions retain that status.

[ARCHITECTURE-SPINE.md](../../planning-artifacts/architecture/architecture-PhishingEmailDetection-2026-10-05/ARCHITECTURE-SPINE.md) is the decision record for AD-5/6/7/8/9/10/11/13. Its tagged initial policies are shared implementation defaults, not qualified limits or measured SLAs.

## Participants and session

The PRD roles are **demo participant** and **project team**. The job is to submit an exported email and see the research pipeline's classification. **Source-described session:** choose/drop one email, inspect filename/size, start Analyze, follow truthful processing, then receive that filename with one label or recover from an error. Linh in EXPERIENCE is an illustrative assumed participant.

## User flow

Exactly five top-level states refine the original source terms:

| State | Source term | Required behavior |
| --- | --- | --- |
| no-file | Upload | Picker/drop available; Analyze disabled; no result or readiness claim. |
| file-selected | Upload | Show filename/size; locally suitable input enables Analyze. Selection never sends content; "Ready to analyze" describes selection. |
| analyzing | Sending/startup/analyzing | One attempt owns the filename; prevent duplicate starts and clear prior output. Use readable indeterminate text. |
| success | Completed | Require completed status and a valid label; show that attempt's filename and exactly one label with equal neutral styling, followed by the AD-14 factors when present. |
| error | Failed | Explain the cause, show no current or previous classification or factors, and offer replacement or permitted bounded Retry. |

Selection is followed by an explicit Analyze action. Before it, explain that analysis sends the email to the server. Retention copy requires verified temporary-file cleanup, logging and browser-session behavior; do not claim local-only processing or label Legit as "Safe."

Sending, startup and processing appear only with reliable observations. AD-13 defines a separate authenticated status channel with transient active-request phases; otherwise show "Analyzing...". A status-poll failure cannot commit a label or fail the terminal POST. Never invent percentages, duration or hidden stages.

Capture attempt identity and filename at start. Clear prior results on replacement/retry/error and suppress responses after timeout, replacement, removal or a newer attempt. Retry starts a fresh non-overlapping attempt under the architecture's shared manual policy, including same-file attempt counting across both Analyze and Retry controls. Retain a suitable file only when recovery permits; an invalid file needs replacement. Explain actual disabled-Retry policy, without promising that timeout stopped server work.

EXPERIENCE A5 proposes idle Change/Remove controls, locked file mutation while analyzing, picker cancellation preserving selection, and removal/refresh returning to no-file. Its keyboard, announcements, focus, zoom and reduced-motion floor remains provisional under Q6. No Cancel action or server-cancellation promise is specified.

## Routes and response

| Endpoint | Owner | Contract |
| --- | --- | --- |
| `POST /api/analyze` | Next.js frontend server route | Receive one multipart file, enforce upload policy and forward with a server-side backend token. |
| `POST /v1/analyze` | Python backend | Validate/parse email, infer using the eligible release and return the classification. |
| `GET /health/live` | Python backend | Report process liveness with minimal information. |
| `GET /health/ready` | Python backend | Eligible child/policy readiness: 200 ready or 503 unready; busy capacity is a separate condition. |
| `GET /api/analysis-status?request_id=<uuid>` | Frontend proxy | Forward the current attempt's status query with server credentials; validate the envelope/header. |
| `GET /v1/analysis-status?request_id=<uuid>` | Python supervisor | Report only observed startup or matching active receive/process phase; never return a class/history. |

Minimal success:

```json
{"analysis_status":"completed","label":"phishing"}
```

Success with an AD-14 explanation:

```json
{"analysis_status":"completed","label":"phishing","explanation":{"factors":[
  {"factor":"reply_to_differs_from_sender","direction":"positive","strength":1.0},
  {"factor":"text_content","direction":"positive","strength":0.74},
  {"factor":"num_urls","direction":"negative","strength":0.18}]}}
```

The success envelope has exactly `analysis_status`, `label` and the optional `explanation`, with no other fields. The label enum is exactly `legit|phishing`. `explanation` contains exactly `factors`: 1–5 items, each with exactly `factor` (an ID from `web/contracts/explanation-factors.json`), `direction` (`positive|negative`, relative to class 1) and `strength` (number greater than 0 and at most 1). It is present only when the release has an exact explanation method. The browser associates its captured filename with this attempt; no filename, score, probability, raw email, raw feature value or full feature table appears in the response. Invalid completed status, label or explanation payloads become processing errors without a guessed label or factors. Internal metadata supports release, feature and timing verification without exposing email content. Model-info remains an extension.

Browser creates a fresh UUIDv4 `X-Request-ID` per attempt; proxy validates and propagates correlation only. Missing/invalid IDs return `INVALID_REQUEST` with a newly generated ID. Every analysis response carries the matching ID header. Proxy validates the original extension, forwards exactly one multipart field `file` with canonical filename `message.eml`, and leaves actual filename association in the browser.

Failures use the exact `error.code`, `error.message` and `request_id` envelope, omitting classification and stacktrace. Map provider HTML/non-JSON startup responses, backend authentication failure and unknown errors to readable recoverable copy rather than raw provider pages. EXPERIENCE supplies proposed messages.

| Initial shared error code | HTTP | Recovery |
| --- | --- | --- |
| INVALID_REQUEST (multipart, extension or extra parts) | 400 | Correct or replace input. |
| EMAIL_TOO_LARGE | 413 | Replace input. |
| EMPTY_EMAIL, INVALID_EMAIL, INSUFFICIENT_CONTENT, RESOURCE_LIMIT | 422 | Correct or replace input. |
| SERVICE_BUSY | 429 | Retain suitable input; eligible manual retry. |
| MODEL_UNAVAILABLE, UPSTREAM_UNAVAILABLE | 503 | Same bounded policy. |
| ANALYSIS_TIMEOUT | 504 | No result; eligible manual retry. |
| UPSTREAM_INVALID_RESPONSE | 502 | Safe error; eligible manual retry. |
| INTERNAL_ERROR | 500 | Safe error; eligible manual retry. |

These are AD-5/6 draft-policy choices, superseding earlier either/or defaults. Q3 still requires qualification or coordinated revision. Valid canonical backend errors pass through with proxy correlation; unreachable/provider-startup responses become UPSTREAM_UNAVAILABLE, transport deadlines become ANALYSIS_TIMEOUT, and auth failures/unexpected statuses/invalid non-JSON success become UPSTREAM_INVALID_RESPONSE. Never expose raw provider bodies.

AD-13 returns exactly request_id plus phase (`unknown|starting|receiving|processing`), with response ID/header matching the query. Actual child startup/recovery may report service-wide starting; receiving/processing must match the current active ID. Erase phase state on completion/failure. Poll only while the attempt is current, using the architecture's bounded non-overlapping schedule; poll failure does not replace terminal POST behavior.

The initial manual-retry and deadline/reap profile lives in the spine's Consistency Conventions; all controls obey it. Q4 requires measurements, including clock skew and process termination. Browser timeout invalidates its attempt and never promises immediate backend cancellation.

## Input and resource boundary

- Use the same versioned AD-6 file/body/MIME/decoded-output/token profile at all consumers; the initial file cap is 2 MiB including encoded attachments. Enforce actual consumed bytes before unconstrained parsing and test multipart overhead; invalid/missing shared policy prevents readiness/deployment.
- Accept one file through picker or drop. Browser checks assist; the backend verifies actual suitable MIME/content rather than trusting filename or client-declared MIME type.
- Reject unsuitable/oversized input and budget overrun before inference; overflow rejects instead of truncating. A recognized nonempty header and normalized useful text are required. The release-owned traversal/tokenization adapter defines root/node/depth/decoded-byte/final-token semantics and the defect allowlist; Q3 qualifies this shared profile.
- Preserve Unicode; privacy-scrubbed fixtures cover plain text, HTML, multipart, varied charsets, attachments and malformed mail. Missing headers/structure produce internal warnings under the versioned preprocessing policy.
- Changing missing-value behavior or feature schema requires a new validated release.

## Privacy, authentication and concurrency

- Uploads are transient, preferably RAM-backed within resource limits; clean parent-owned spools and IPC on every terminal path, plus abandoned spools at restart. Results stay in transient browser-session memory, with no local-storage or server-history requirement.
- Logs/analytics exclude raw content, subject, sender, recipient, filename, labels and explanation factors. Allowed fields: request ID, bytes, duration, status and release ID; content digests are also excluded.
- Uploaded HTML/scripts are neither rendered nor executed; URLs, attachments and tracking images are not opened/fetched. Feature extraction makes no DNS/WHOIS/remote attachment requests. Any future inspector needs processed safe text.
- Only .eml input is accepted from users; only team-controlled pickle is loaded for the release.
- Backend tokens stay in server environment variables and are verified by the backend. CORS is not authentication; the browser never receives the token.
- Use one ASGI supervisor with one resident serial spawned ML child under AD-7. Authenticate/acquire the sole admission before body consumption, hold it through cleanup, and reject excess work without a queue. The child owns parsing/features/inference; parent owns asynchronous body collection, deadline, request directory and IPC. Apply bounded terminate/reap/hard-kill recovery; an unreaped child exits the supervisor and cannot coexist with a replacement.
- Initial cloud acceptance is a controlled demo under AD-10: verify account-supported server access protection first. Anonymous publication needs verified shared abuse controls under Q5; per-instance counters are insufficient. No login/account UI is added; local proxy binds loopback.
