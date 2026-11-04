# PRD Quality Review — IAP Email Classification Web Application

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

## Overall verdict

The PRD is suitable to finalize as the product input for UX, architecture and story planning: it defines a coherent single-session academic demonstration, preserves the adopted SPEC and makes its evidence and claim boundaries explicit. It does not authorize real-model or deployment acceptance yet; E0 and the applicable Q1–Q5 decisions remain genuine, assigned gates, rather than defects concealed by the document. No substantive corrective findings were identified for this create-intent review.

## Decision-readiness — strong

The Vision commits to one exported email and the eligible model's `legit` or `phishing` result. MVP scope names the separate Next.js frontend/Python backend boundary and explicitly gives up scores, explanations, inspection, accounts, history and inbox integration. This is an actionable decision about the demonstration, not a neutral list of possible capabilities.

The Dependencies and open questions table identifies the unresolved target, model-quality criteria, parser contract, runtime policy and deployment feasibility as Q1–Q5, with workstream owners and revisit conditions. Its opening paragraph distinguishes planning and marked samples that can proceed from acceptance that E0 or the relevant evidence blocks. The addendum's Delivery dependencies makes the free-host versus local-fallback trade-off explicit: a local demonstration cannot certify the cloud route. Finalization is therefore a planning decision with clear limits, not a claim that a working eligible release exists.

### Findings

None.

## Substance over theater — strong

Vision and target users describes activities supported by the source and expressly avoids inventing interviewed personas. The job statement is labeled a restatement rather than a customer quote; that honesty fits the supplied academic objective. The vision is specific to connecting the browser to the verified research pipeline while preventing spam-inclusive evidence from being represented as phishing-only performance.

The cross-cutting requirements are earned by this product's risks: transient MIME uploads and sensitive logs (NFR-1), no execution or network investigation of email contents (NFR-2), bounded parser/inference work (NFR-3), and coherent same-run artifacts (NFR-4). A1/A2 identify provisional source-proposed limits instead of passing them off as measurements. Supplemental landscape context supports scope and privacy distinctions without a commercial-demand or novelty claim.

### Findings

None.

## Strategic coherence — strong

The thesis is consistent throughout: demonstrate a verified research classifier through a usable browser session without overstating its target or evidence. FR-1–FR-6 support that session; FR-7–FR-9 protect readiness, model eligibility and integration agreement; FR-10 provides reproducible operation and handover. None is an unrelated commercial capability added to a backlog.

Success and counter-metrics tests the thesis through valid Fixture completion, error integrity and reproducible handover (SM-1–SM-3). SM-C1 requires quality/resource costs alongside completion; SM-C2 checks fabricated labels, stale results, request-order changes, credentials and sensitive retention. The explicit warning that upload success or a high phishing-label count is not efficacy evidence avoids substituting activity metrics for the demonstration's purpose.

### Findings

None.

## Done-ness clarity — adequate

All ten FRs state an observable acceptance consequence. Examples include rejecting invalid input before inference (FR-2), preventing errors from becoming a third class and clearing a changed file's result (FR-4), blocking duplicate submissions and stale responses (FR-5), rejecting unready releases (FR-7), and comparing Fixture features/results plus repeated labels (FR-9). NFR-1 supplies allowed log fields, NFR-2 prohibits concrete side effects, and NFR-4 specifies same-release inference without request-time fitting. These requirements can drive meaningful acceptance checks.

Final parser budgets, quality criteria, deadlines, retries, vector tolerance and hosting controls are deliberately unresolved in Q2–Q5. The requirement sections and Dependencies explicitly route the affected acceptance to those gates, so these are legitimate staged decisions, not vague promises or defects requiring invented thresholds. The document is adequate for downstream planning; an engineer cannot sign off the affected implementation until the cited decisions and E0 evidence are recorded. The addendum supplies the initial API schema, readiness response and E0–E5 evidence sequence while retaining the SPEC companions as the full contract.

### Findings

None. The pending acceptance gates are explicit and do not need replacement with new efficacy or latency targets in this review.

## Scope honesty — strong

MVP scope and non-goals explicitly excludes the likely sources of drift: scores, new labels, indicators, explanation tooling, inspectors, accounts, batches, history, databases and automated inbox handling. It also excludes unsupported language/efficacy/research claims. Document purpose and the addendum repeatedly state that PRD creation neither changes the SPEC contract nor completes E0.

A1–A5 cover provisional input/RAM targets, estimate dependency, workstream owners and the proposed stack. The five open questions are proportionate to a brownfield academic demonstration with an unverified release and deployment path. Their density is not presented as permission to build and accept everything immediately: unresolved evidence expressly blocks its corresponding sign-off. Source-described snapshot observations, local metadata and historical mixed-positive metrics remain differentiated in Evidence and claim boundaries.

### Findings

None.

## Downstream usability — strong

Glossary defines Email file, Analysis, Processing error, Eligible release, E0 and Fixture, including the important distinction between an unsuccessful attempt and a classification. FR-1–FR-10, NFR-1–NFR-5 and SM-1–SM-3/SM-C1–SM-C2 give downstream work stable source anchors. Success metrics resolve to the relevant FR/NFR IDs, while Q1–Q5 and A1–A5 identify the decisions and assumptions that UX, architecture and stories must carry forward.

The addendum's Adopted implementation material table identifies each SPEC companion and what must survive extraction, rather than implying the short PRD is the entire technical contract. Named-persona UJs are intentionally omitted and the role/session context is carried inline under Vision and target users; this avoids inventing a protagonist and remains sufficient for this single-session tool. Source reconciliation is recorded as PASS for this gate review.

### Findings

None.

## Shape fit — strong

The document fits a brownfield academic capability demonstration feeding UX, architecture and stories. It uses a short role/session description, concrete FR acceptance, cross-cutting constraints and evidence gates, with detailed technical material in the companion addendum and adopted SPEC. It does not force a market-launch narrative, revenue model, interviewed persona or enterprise workflow onto the supplied objective.

Existing offline research and the new browser/API demonstration are distinguished through the Vision, E0 and Evidence and claim boundaries. Conditional delivery windows, ML work estimated separately and the explicit local/cloud distinction match the actual uncertainty. The rigor concentrates on label validity, artifact coherence, privacy, bounded processing and reproducibility, where this project's consequences require it.

### Findings

None.

## Mechanical notes

- FR-1–FR-10, NFR-1–NFR-5, SM-1–SM-3, SM-C1–SM-C2, Q1–Q5 and A1–A5 are contiguous and unique within their series; references inspected in the PRD/addendum resolve to those IDs or adopted artifacts.
- The Assumptions index roundtrip is complete across the document pair: A1–A4 appear inline in the PRD; A5 appears inline in the addendum and is indexed in the PRD.
- Core glossary terms preserve their meaning across requirements, metrics and the addendum. `legit`/`phishing` remain the only successful output labels; Processing error remains outside that class set.
- No UJ series is claimed. The deliberate role/session format and explanation for omitting invented named-persona journeys fit the agreed academic single-session scope.
- Required material for these stakes is present: vision/roles, functional consequences, cross-cutting constraints, non-goals, success/counter-metrics, dependencies, open decisions, assumptions and technical/source boundaries. Source reconciliation is PASS; this review is not a separate artifact-hash or model verification run.
- Findings count: critical 0; high 0; medium 0; low 0. No substantive PRD/addendum fixes are required by this review. E0 and Q1–Q5 remain downstream work, not completed evidence.
