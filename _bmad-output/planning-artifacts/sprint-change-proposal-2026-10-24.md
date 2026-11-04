---
title: Sprint Change Proposal — Per-result factor explanation
status: approved
created: 2026-10-24
approved: 2026-10-24
mode: incremental
scope: major
trigger: User request to display explanations/indicators after the 2026-10-23 SHAP analysis of runs/2026-10-23_web2
---

# Sprint Change Proposal — Per-result Factor Explanation

## 1. Issue summary

The user asked for the web result to explain what the model relied on (explanations/indicators), applying to the whole MVP, not only the local demo. Every planning document currently excludes this: PRD non-goals (`prd.md:43`), SPEC non-goals (`SPEC.md:68`) and strict success envelope (`api-and-experience.md:50`), architecture AD-5/AD-8 and the Deferred row "Scores, indicators, inspector… — only upon new scope approval", UX "no indicators" (`EXPERIENCE.md:70`) and `local-demo.md:18`. The shared schema (`web/contracts/analysis.schema.json`) rejects any extra success field.

Discovered on 2026-10-23/24 after `analyze_shap.py` was run on the pinned run; the lecturer had asked whether the 53 engineered features are credible phishing signals. Category: new stakeholder requirement. No epics exist; the SPEC capabilities and E-gates stand in for epics, as in the 2026-10-20 proposal.

Evidence (run `runs/2026-10-23_web2`, XGBoost selected on validation, threshold 0.0358, test set 66,325 legitimate / 1,081 phishing; manifest and all 18 artifact hashes verified on 2026-10-24):

- XGBoost `pred_contribs` yields exact per-email contributions; contributions plus bias reproduce the margin (checked in `analyze_shap.py` and `tests/test_shap.py`).
- Global attribution: Doc2Vec (100 dimensions grouped) 39.4%, engineered features 60.6%; largest single features `is_html` 22.5% and `from_display_name_length` 12.7%.
- `is_html` is present in 0.74% of legitimate and 94.9% of phishing test emails; every CSV-derived legitimate source has 0.000 because those corpora store bodies without MIME structure. False-positive rate is 11.0% (54/491) on HTML legitimate mail versus 0.05% (34/65,834) on plain-text legitimate mail; recall is 78.2% (43/55) on plain-text phishing versus 100% (1,026/1,026) on HTML phishing. `is_html` is the top driver of 54 of 88 false positives.

An explanation is therefore feasible and cheap, but it will expose a dataset shortcut; how that is presented is recorded as open question Q9.

## 2. Impact analysis

**Capability impact.** CAP-2 success gains an optional factor explanation. CAP-5 gains explanation qualification (additivity, repeatability, catalogue coverage). CAP-3 must keep factors out of errors and obsolete attempts. CAP-6 gains matching checks. CAP-1 and CAP-4 are unchanged. Implementation can proceed now; FR-11 acceptance is blocked by Q9.

**Story impact.** No stories exist. One implementation work item covers contract, backend, frontend, tests and docs (Section 5).

**Artifact conflicts.**

| Artifact | Conflict |
| --- | --- |
| PRD `prd.md` | Non-goal excludes indicators/XAI; no explanation FR; NFR-1/SM silent; no Q9 |
| PRD `addendum.md` | States examples do not justify indicators |
| SPEC `SPEC.md` | CAP-2, constraints, non-goals, success signal; no Q9 |
| SPEC `api-and-experience.md` | Exact two-field success envelope; error/log rules omit factors |
| SPEC `model-and-inference.md` | No explanation computation rule or E0 evidence |
| SPEC `deployment-and-acceptance.md` | No FR-11 traceability, checks or Q9 owner |
| SPEC `brownfield-and-evidence.md` | Defers indicators; "XAI remains outside MVP" |
| SPEC `local-demo.md` | "Do not add … indicators"; exact two-field envelope |
| `ARCHITECTURE-SPINE.md` | AD-5 strict success, AD-8 exclusion, Deferred row; no AD for explanation |
| `EXPERIENCE.md` / `DESIGN.md` | "No indicators" in success; no component, copy or tokens |
| `AGENTS.md`, `web/docs/` | No pointer to explanation code/catalogue; snapshots must be synced |

**Technical impact.** Contract change (new optional `explanation` object and factor catalogue) with regenerated client types; adapter computes contributions in the ML child; frontend renders a new result component; new backend and frontend tests. No training, dataset or run change; the pinned run already supports exact contributions.

## 3. Recommended approach

**Hybrid: MVP scope addition (Option 3) applied through direct document adjustment (Option 1).** Core goals are unchanged; one FR and one AD are added and existing exclusions are narrowed to approximate explanations, scores and raw values.

- Effort: medium (documents) plus medium (implementation, roughly 1–2 days including tests).
- Risk: medium. Explanations can be read as proof or confidence and currently surface the `is_html` shortcut; mitigated by exact-method-only, neutral wording and visuals, a fixed notice, a provisional bias note and Q9 gating acceptance.
- Option 2 (rollback): not applicable.
- Timeline: E3 frontend integration gains the explanation component; FR-11 acceptance waits for Q9.

Decisions taken with the user: incremental review; whole-MVP scope; relative strength bars without numbers; `is_html` treatment deferred to Q9 with a provisional "known dataset bias" note in the local demo.

## 4. Detailed change proposals (all approved on 2026-10-24)

### Proposal 1 — PRD `prd.md`

- Frontmatter `updated: 2026-10-24`.
- Add after the pipeline update banner: "Explanation update 2026-10-24: MVP scope now includes a per-result explanation (FR-11) showing the main factors behind the served classifier's decision, computed exactly from that model. It explains model behavior only; it does not establish phishing quality. How factors reflecting dataset construction (currently `is_html`) are presented remains Q9."
- Non-goal OLD: "Score/confidence/risk displays, Spam or uncertain output labels, indicators, XAI/LIME, email inspector, feature tables, model-info pages and JSON export." NEW: "Score/confidence/risk displays, Spam or uncertain output labels, approximate or sampled explanations (for example LIME), email inspector, full feature tables, raw feature values, model-info pages and JSON export. FR-11's bounded factor explanation is the only explanation in scope."
- Add after FR-4: "**FR-11 — Explain a result.** With a successful result, the participant sees up to five main factors that moved the served classifier toward or away from the positive class, each with a direction and a relative strength, and a notice that factors describe the model's reasoning, not proof about the email. **Acceptance:** Factors are computed exactly from the served classifier for that email (contributions plus base value reproduce the model output); the text-embedding dimensions appear as one text factor; no score, probability, raw feature value or email content is shown; identical input yields identical factors regardless of request order or restart; errors and obsolete attempts show no factors; a release without an exact explanation method shows the label only. Presentation of dataset-shortcut factors remains Q9."
- NFR-1 appended: "Explanation factors are result data: transient and never logged."
- SM-1 NEW: "… and, where the release supports it, an exact factor explanation. Validates FR-1, FR-3, FR-4, FR-10 and FR-11." SM-C2 NEW: "… exposed credentials, sensitive-content retention/logging, or factor lists that fail to reproduce the model output or change across repeated input."
- Add Q9: "| Q9 | How factors that reflect dataset construction rather than phishing (currently `is_html`: 0.7% of legitimate vs 94.9% of phishing test emails; 11% false-positive rate on HTML legitimate mail in run 2026-10-23_web2) are retrained, labelled or excluded in explanations | ML and UX workstreams | Before FR-11 acceptance |"

Rationale: the PRD defines MVP scope; the explanation needs its own acceptance criteria and the known shortcut must be an explicit open question.

### Proposal 2 — SPEC `SPEC.md`

- Add after the pipeline update: "Explanation update 2026-10-24: a successful result may now carry an exact per-result factor explanation (PRD FR-11, AD-14). It describes the served model's behavior, not phishing quality; presentation of dataset-shortcut factors such as `is_html` remains Q9."
- CAP-2 success appended: "When the active release has an exact explanation method, success also shows up to five model factors with direction and relative strength under AD-14; failures and obsolete attempts show none."
- Constraint OLD: "…keep the exact completed envelope and existing endpoints/errors." NEW: "…keep the strict completed envelope (label plus the optional AD-14 explanation) and existing endpoints/errors."
- New constraint: "Explanations follow AD-14: exact contributions of the served classifier for that email, text-embedding dimensions grouped as one factor, at most five factors from the shared factor catalogue with direction and relative strength, the fixed English notice, no logging, and no explanation when the release lacks an exact method. Factors describe model behavior, never proof, confidence or quality."
- Non-goal OLD: "In-app .eml export instructions, scores/confidence/risk, indicators/XAI/LIME, inspector/features/model-info screens and JSON export." NEW: "In-app .eml export instructions, scores/confidence/risk, approximate or sampled explanations (for example LIME), raw feature values, inspector/full feature tables/model-info screens and JSON export. The bounded AD-14 factor explanation is in scope."
- Success signal OLD: "…matching filename, truthful mixed-target output and actionable errors without fabricated labels." NEW: "…matching filename, truthful target output, an exact factor explanation where supported and actionable errors without fabricated labels or factors."
- Add "**Q9:** How should factors reflecting dataset construction rather than phishing (currently `is_html`, present in 0.7% of legitimate and 94.9% of phishing test emails) be retrained, labelled or excluded before explanation acceptance?"

Rationale: the SPEC is the canonical web contract and must match FR-11; "mixed-target" is also stale for the phishing-target run.

### Proposal 3 — `ARCHITECTURE-SPINE.md`

- Frontmatter `updated: 2026-10-24`; banner: "Explanation update 2026-10-24: AD-14 adds an exact per-result factor explanation; AD-5 and AD-8 now admit it. Presentation of dataset-shortcut factors is deferred to Q9."
- New AD after AD-13:

  > ### AD-14 — Exact factor explanation [ADOPTED; catalogue wording and strength bands ASSUMPTION]
  >
  > - **Binds:** CAP-2, CAP-3, CAP-5; ML worker, HTTP contract and browser result.
  > - **Prevents:** Explanations that disagree with the served decision, leak email content, vary across repeats or read as proof or confidence.
  > - **Rule:** The ML child computes exact additive contributions of the served classifier's decision margin for the same vector that produced the label (tree ensembles: XGBoost `pred_contribs`). It sums the Doc2Vec dimensions into one `text_content` factor and keeps each engineered feature as its own factor, named by `preprocess.FEATURE_NAMES`. Startup verifies on the release's test arrays that contributions plus bias reproduce the margin within 1e-3; a per-request mismatch returns `INTERNAL_ERROR` with no result. The response carries 1–5 nonzero factors with the largest absolute contribution, ordered descending (ties in feature order, text first), each `{factor, direction, strength}`: `direction` is `positive` or `negative` relative to class 1; `strength` is |contribution| divided by the largest shown, rounded to two decimals in (0, 1]. Factor IDs and English display text come from the versioned `web/contracts/explanation-factors.json`; readiness fails if a served feature lacks an entry. A release whose classifier has no exact method omits `explanation`; no LIME, sampling or surrogate model. Factors are result data: transient, never logged, absent from the status channel and errors, and covered by AD-4 repeat/reorder/restart checks. Changing the method, grouping or catalogue is a contract change.

- AD-5 OLD: "Strict success is exactly `{"analysis_status":"completed","label":"legit"}` or its `phishing` equivalent." NEW: "Strict success is `{"analysis_status":"completed","label":"legit"}` or its `phishing` equivalent, optionally with the AD-14 `explanation` object; no other fields."
- AD-8 OLD: "Score, indicators, inspector, history and account screens remain outside this MVP." NEW: "Show AD-14 factors only inside the current success result and clear them with it. Score, inspector, history and account screens remain outside this MVP."
- Consistency Conventions: IDs/schema NEW "…exact lowercase labels; no success extras beyond the AD-14 explanation." Contract acceptance appended: "Qualify explanation additivity, factor repeatability across repeat/order/restart, catalogue coverage, and absence of factors in errors, logs and status responses."
- Capability map: add AD-14 to CAP-2 and CAP-5.
- Deferred OLD: "| Scores, indicators, inspector, persistence, scaling and extra delivery material — product | Only upon new scope approval; no dormant MVP fields, datastore or extra screen. |" NEW: "| Scores, raw feature values, inspector, persistence, scaling and extra delivery material — product | Only upon new scope approval; no dormant MVP fields, datastore or extra screen. AD-14 factor explanations were approved on 2026-10-24. |" New row: "| Dataset-shortcut factors (Q9) — ML + UX | Before FR-11 acceptance, decide whether `is_html` and similar source-format features are retrained away, disclosed as known dataset bias in the catalogue, or excluded; any exclusion must itself be disclosed. |"

Rationale: AD-14 fixes fidelity, repeatability, privacy and exact-method-only invariants; a shared catalogue keeps AD-5's single-contract rule. The 1e-3 tolerance matches the existing SHAP check.

### Proposal 4 — SPEC `api-and-experience.md`

- User flow success NEW: "Require completed status and a valid label; show that attempt's filename and exactly one label with equal neutral styling, followed by the AD-14 factors when present." Error NEW: "Explain the cause, show no current or previous classification or factors, and offer replacement or permitted bounded Retry."
- Replace the response paragraph with the minimal success example, plus:

  ```json
  {"analysis_status":"completed","label":"phishing","explanation":{"factors":[
    {"factor":"reply_to_differs_from_sender","direction":"positive","strength":1.0},
    {"factor":"text_content","direction":"positive","strength":0.74},
    {"factor":"num_urls","direction":"negative","strength":0.18}]}}
  ```

  "The success envelope has exactly `analysis_status`, `label` and the optional `explanation`, with no other fields. The label enum is exactly `legit|phishing`. `explanation` contains exactly `factors`: 1–5 items, each with exactly `factor` (an ID from `web/contracts/explanation-factors.json`), `direction` (`positive|negative`, relative to class 1) and `strength` (number greater than 0 and at most 1). It is present only when the release has an exact explanation method. The browser associates its captured filename with this attempt; no filename, score, probability, raw email, raw feature value or full feature table appears in the response. Invalid completed status, label or explanation payloads become processing errors without a guessed label or factors. Internal metadata supports release, feature and timing verification without exposing email content. Model-info remains an extension."
- Privacy OLD: "Logs/analytics exclude raw content, subject, sender, recipient and filename." NEW: "Logs/analytics exclude raw content, subject, sender, recipient, filename, labels and explanation factors."

Rationale: a malformed explanation invalidates the whole response, consistent with fail-closed handling; example IDs are real `FEATURE_NAMES` entries.

### Proposal 5 — SPEC `model-and-inference.md`

- Line 5 appended: "Follow AD-14 for per-result explanations."
- New section after "Evaluation and parity":

  > ## Explanation (AD-14)
  >
  > - Compute contributions in the ML child from the same final vector and loaded classifier that produced the label; never repeat preprocessing or load a second model for explanation.
  > - Use exact methods only. Tree ensembles use the booster's exact contribution output on the decision margin (XGBoost `pred_contribs`). Other classifiers omit `explanation` unless a separate exact method is approved; BERT is not served.
  > - Sum the first `doc2vec_dim` columns into `text_content`; engineered columns keep `FEATURE_NAMES` order. The bias term is not a factor.
  > - Select at most five nonzero factors by absolute contribution; `strength` is relative to the largest shown. `direction` is relative to the class-1 margin and independent of the decision threshold, so a Legit result can list factors pointing toward the positive class.
  > - Startup verifies additivity on the release's test arrays (within 1e-3) and catalogue coverage of every served feature; each request rechecks additivity. Factors follow AD-4 repeatability.
  > - Factors describe this release's model behavior. They are not evidence that an email is malicious, are not validated as human-meaningful and do not establish model quality.

- E0 evidence appended: "For FR-11, also record startup additivity, factor repeatability on the fixtures and the release's global SHAP summary and top error drivers (`analyze_shap.py --run runs/<name>`), which inform Q9."

Rationale: direction must be stated as threshold-independent (the 0.0358 threshold makes positive factors on Legit results common); global SHAP is the evidence that revealed the shortcut.

### Proposal 6 — SPEC `deployment-and-acceptance.md` and `brownfield-and-evidence.md`

- Traceability row: "| FR-11 Explain a result | CAP-2/5 | Exact additive factors, grouped text factor, repeatability, no factors in errors/logs/status, label-only for releases without an exact method |"
- SM-1 NEW: "…matching filename, one label and, where supported, an exact factor explanation (FR-1/3/4/10/11)." SM-C2 NEW: "…exposed credentials, sensitive-content retention/logging, non-additive factors or factor changes across repeated input; this is not a production-wide guarantee."
- Browser checks NEW: "Browser checks exercise no-file, file-selected, analyzing, both successful labels with and without an explanation, and error; verify factors clear with the result on replacement/removal/retry/error, and verify …"
- New acceptance bullet: "Explanation checks cover startup and per-request additivity, catalogue coverage of every served feature, identical factors under repeated/reordered/restarted input, strict rejection of malformed explanations, and absence of factors from errors, status responses and logs."
- Line 92 appended: "Exact additivity establishes fidelity to the model, not that its factors are meaningful phishing evidence."
- Ownership row: "| Q9 dataset-shortcut factors in explanations | ML and UX | Before FR-11 acceptance |"
- Brownfield line 37 NEW: "| Legitimate/Spam/Phishing, probability, indicators and inspector | Display one label plus AD-14 factors; defer probability, inspector and other extended fields, and keep errors outside the class enum. |"
- Brownfield line 90 NEW: "…this does not establish LIME or measured explanation quality in IAP. AD-14's exact factor explanation is the only XAI in the MVP; LIME is not used."

Rationale: every new FR needs traceability and acceptance checks; fidelity and meaningfulness are kept distinct.

### Proposal 7 — SPEC `local-demo.md`

- Update block, new bullet: "Since 2026-10-24 a success from the pinned run also carries its AD-14 factor explanation (the selected XGBoost supports exact contributions). Until Q9 is decided, the local catalogue shows `is_html` with the provisional note "known dataset bias" rather than hiding it; Q9 may replace this. Local factors explain this run only and add no quality claim."
- Line 18 NEW: "…The success envelope is `analysis_status`, `label` and the optional AD-14 `explanation`, accepting these three declared label values only. … Do not add a third model class, score or export instructions; AD-14 factors are the only explanation."

Rationale: implementation needs an interim treatment while Q9 is open; disclosure without retraining is the only honest interim option.

### Proposal 8 — UX `EXPERIENCE.md` and `DESIGN.md`

- EXPERIENCE Foundation NEW: "MVP output contains the label, the filename and, when the release supports it, up to five model factors (AD-14); probability and email inspector are extensions."
- Voice and Tone sentence: "Describe factors as what the model relied on; never call them evidence, warnings or red flags." Microcopy rows: Explanation heading "What the model relied on"; Explanation notice "These factors describe how the model reached this result. They are not proof that the email is safe or malicious."; Factor direction "Toward {positive label}" / "Toward Legit"; Factor strength "Strong", "Moderate" or "Weak", relative to the largest factor shown (proposed bands ≥0.67, ≥0.34, otherwise); Provisional bias note "Known dataset bias" (Q9).
- status-result-area NEW: "…Error contains no label, factors, score or old result."
- New component row: "| explanation-list | **[ASSUMPTION A5]** Inside status-result-area after the label, only in success. Heading, notice, then an ordered list of 1–5 factors in response order; each item states display text, direction and strength in words plus a decorative relative bar (`aria-hidden`). Not interactive: no tooltip, expansion or raw value. Only the label is announced; factors are read in normal reading order. Absent when the response has no explanation. |"
- Success state NEW: "Exactly one label, identical neutral structure, then explanation-list when present; idle change/remove available."
- Journey climax NEW: "Success shows the same filename and exactly **Legit** or **Phishing**, followed by the factors the model relied on, with no score or inspector."
- DESIGN component tokens: `explanation-list` with `foreground: '{colors.foreground}'`, `fontSize: '{typography.meta.fontSize}'`, `barFill: '{colors.secondary-text}'`, `barTrack: '{colors.border}'`.
- DESIGN component row: "| explanation-list | `meta` list below the result in the same surface. Both directions use the same neutral bar fill on a border-colored track; direction is written in text, never shown by red/green. Bar width is proportional to strength with a small minimum visible width. |"
- Do's and Don'ts NEW: "| Write the exact successful label and analyzed filename, then the model factors in text with neutral bars. | Add Spam, Unknown, a score, probabilities, red/green factor colors or an inspector to this MVP. |"

Rationale: red/green would turn factors into warnings, contradicting "not proof"; announcing only the label keeps screen-reader output short.

### Proposal 9 — Secondary artifacts

- PRD `addendum.md` line 56 NEW: "…they do not justify adding an inspector or scores; the AD-14 factor explanation was approved separately on 2026-10-24."
- `AGENTS.md` overview NEW: "…serving one pinned 19-10 baseline run with its label and exact per-result factor explanation (AD-14)." New "Where things are" bullet: "Per-result explanations are computed in web/backend/adapter.py from the served classifier's exact contributions; factor display text lives in web/contracts/explanation-factors.json, which must cover every preprocess.FEATURE_NAMES entry, so update it whenever FEATURE_NAMES changes."
- Run `node web/scripts/sync-docs.mjs` after the document edits.

Rationale: future agents need the catalogue pointer, or a `FEATURE_NAMES` change silently blocks readiness.

## 5. Implementation handoff

**Scope: Major** — MVP scope addition across PRD, SPEC and architecture (new AD-14). In this single-maintainer project the user holds the PM/architect approval; document edits are applied by this workflow after approval, and implementation is routed to the developer workflow (`bmad-build`).

Implementation work item (not part of the document edits):

1. Contract: `Explanation` definition in `web/contracts/analysis.schema.json`; new `web/contracts/explanation-factors.json` covering the 53 `FEATURE_NAMES` plus `text_content`, with the provisional `is_html` note; `npm.cmd run contracts:generate`; `policy.validate_policy` validates a sample with an explanation.
2. Backend `web/backend/adapter.py`: contributions from the scored vector; startup additivity on the run's test arrays and catalogue coverage; per-request additivity; explanation omitted for classifiers without an exact method.
3. Frontend: runtime validation in `lib/contracts.ts`; controller clears factors with the result; `explanation-list` in `components/AnalysisPage.tsx`.
4. Tests: backend additivity, repeat/reorder/restart factor equality, no factors in errors/status/logs, malformed-explanation rejection, non-tree release; frontend unit, browser and real-model checks.
5. Docs: `web/backend/README.md` (Vietnamese) and AGENTS.md test counts after actual runs.

**Success criteria:** all listed backend and frontend checks pass and are reported with actual counts; the pinned run returns 1–5 additive, repeatable factors for every sample email; errors, status responses and logs contain no factors; `web/docs/` matches the canonical documents. FR-11 acceptance additionally requires a Q9 decision.
