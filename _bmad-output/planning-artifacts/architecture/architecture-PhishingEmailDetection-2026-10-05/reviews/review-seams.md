# Adversarial interoperability review

Amendment 2026-10-19: only the hosting cleanup passages were updated. Earlier review dates and conclusions remain historical and do not certify these edits, model quality or runtime acceptance.

Date: 2026-10-05. Reviewed the draft `ARCHITECTURE-SPINE.md`, including the source-reconciliation changes through AD-13. Lens: construct independently built units that satisfy the stated decisions but still disagree at their shared boundaries. No implementation was run and no spine edits were made.

Verdict: **Needs narrow contract clarifications before independent implementation.** The important ownership and failure boundaries are present. Two high and two medium findings remain; these are fixable by tightening existing ADs rather than adding components.

## High — S1: Release manifest has required information but no single schema authority

References: AD-2, AD-4, AD-11; Structural Seed; Deferred.

Compliant pair: the offline exporter packages a JSON manifest whose `artifacts` object has nested role/name/hash records, a dataset-review evidence reference and a named threshold rule. The worker expects flat role-specific filename/hash fields, an eligibility attestation object and a differently named decision-rule representation. Each verifies hashes, dimensions, numeric classes, provenance and release evaluation using its own expected representation. Both fulfill the information-level requirements of AD-2, and the worker correctly fails closed when it cannot interpret the other producer's otherwise eligible release. They nevertheless cannot interoperate. A seed recipe written as a descriptive expression creates the same issue: independent harness/worker implementations can choose different concatenation, digest encoding or integer reduction while both derive a deterministic seed from release identity plus raw-content digest.

The Python schema authority is currently explicit for HTTP/proxy-control/policy contracts, but not for the deployment manifest shared by exporter, qualification harness and worker. Deferring filenames and internal names is safe; allowing independent representations of this shared entity is not.

Clear fix: tighten AD-2 so one named contract owner supplies a versioned deployment-manifest schema consumed by exporter, E0 harness and worker. It must define the required evidence/eligibility representation and machine-interpretable decision/seed-policy discriminators; unknown versions or unsupported policies fail closed. Keep its detailed fields and exact inference values in the schema/E0 work rather than expanding the spine. Tie the policy references to the manifest's validated identities, rather than allowing consumers to reconstruct a second release policy from local defaults.

Disposition: **Autofix ownership/versioning rule; exact schema contents resolved jointly by ML and the contract owner before E0/E2.**

## High — S2: Ordered durations do not define comparable request deadlines

References: AD-7, AD-8, AD-12; Initial deadlines and Control plane conventions.

Compliant pair: browser A starts its 165-second attempt clock at Analyze. Proxy B first consumes and validates the browser upload, then starts the explicitly named 150-second *upstream* clock when it sends `fetch`. Proxy C starts the same 150-second clock at handler entry and uses the remaining time for `fetch`. Both satisfy an upstream wait of no more than 150 seconds and the numerical ordering `60 < 150 < 165`. For a valid slow upload, C rejects before forwarding while B can start Python work shortly before the browser or proxy expires. The backend's independently correct 60-second admission clock does not repair the origin mismatch. The proxy needs its own bound on ingress consumption in every environment.

Clear fix: define the origin and covered work for each clock. Recommended: browser starts at explicit Analyze and includes upload; proxy's total analysis budget starts at handler entry and includes bounded body collection, validation, cold wake, forwarding and response validation; upstream receives only the remaining proxy wait budget. Backend still enforces its own 60-second clock from admission including body/parse/worker work. Worker startup/recovery clocks start at the replacement spawn/init transition. State that the numeric inequality orders configured budgets, and does not itself promise end-to-end completion or cancellation across hosts. Preserve the existing independent backend termination rule when a browser/proxy disconnects.

Disposition: **Autofix timer origins/coverage; measure the values at E2/E4 as already required.**

## Medium — S3: Status polling has two possible correlation inputs

References: AD-5 and AD-13; IDs/schema convention.

Compliant pair: browser A polls the documented URL with `request_id` in the query and expects the response to echo that value. Proxy B applies the instruction that the same UUID-validation rules apply, including AD-5's missing `X-Request-ID` rejection. A therefore receives `INVALID_REQUEST` for every otherwise valid poll. A separate backend can return the current active ID for a global `starting` phase, while a proxy expects the requested ID; the status shape itself does not say which value is echoed. Neither interpretation is fixed by the current wire examples. This creates avoidable drift despite the new proxy-control schema authority.

Clear fix: make the query's UUID the original analysis-attempt correlation ID, specify whether `X-Request-ID` is omitted or required to equal it, and require a 200 status response's `request_id` to equal the query. Explicitly choose whether `starting` is global child readiness or only a phase for the matching active attempt; nonmatching `receiving`/`processing` must return `unknown`. The browser validates the echoed ID and ignores invalidated/late polls. Keep these choices in the shared status contract.

Disposition: **Autofix status correlation rules before browser/proxy/API stories split.**

## Medium — S4: Shared resource maxima omit their counting semantics

References: AD-3 and AD-6; MIME/work limits; E0 qualification.

Compliant pair: the E0 harness counts decoded subject/body bytes after transfer decoding in the source charset, while the worker counts UTF-8 bytes after charset decoding. A near-limit Shift-JIS email passes the first interpretation and exceeds the second. Similarly, one MIME traversal counts only leaf parts and starts depth at one; another counts container nodes and starts the root at zero. Both use the stated 100-parts/20-depth maxima, reject defects and preserve the release-frozen parser/resource policy, but boundary acceptance differs because the policy requirements do not demand recording these semantic choices. This also prevents reliable qualifying fixtures at the exact limits.

Clear fix: require the shared release policy/schema to define decoded-text byte encoding/count point, MIME node-count and root-depth convention, and the token stream whose length is bounded. A practical initial convention is UTF-8 bytes after charset decoding and before text cleaning, all MIME nodes including the root with root depth zero, and exactly the release's Doc2Vec input token sequence. Qualify boundary fixtures against that one policy. Release-specific tokenization/charset handling stays with the frozen adapter.

Disposition: **Autofix required policy semantics; exact adapter behavior qualified at E0/E2.**

## Boundaries that already converge

- Multipart has one named file, a separate consumed-body cap, canonical proxy forwarding filename and no trusted MIME claim. Independent deviations from those rules would be violations rather than new architectural holes.
- Status/code mappings, strict binary success, runtime validation and manual retry timings are fixed. Canonical backend errors pass through; provider/transport bodies cannot widen the browser response.
- The parent owns admission, request data and IPC. Deadline termination/reaping, discarded channels, cleanup, replacement validation and failure-to-reap unready/restart behavior close the major kill/readiness seam. Worker-generation/IPC implementation details can follow these invariants without a new AD.
- The current mixed-positive run is explicitly ineligible. Hash integrity does not supply target evidence or pickle trust, and fixture/local/cloud evidence is separated.

## Review limit

This review checks the architecture as a consistency contract. It does not certify schema code, parser behavior, model eligibility, deterministic numerical execution, cloud feasibility or the actual state of a deployment.

## Targeted recheck after fixes — 2026-10-05

Brownfield reconciliation was completed first in `../reconcile-brownfield.md` and passes. The following review records the revised spine through AD-13, without implementation or spine edits.

| Original finding | Updated result |
| --- | --- |
| S1 — Canonical manifest authority | Closed. AD-2 names ML's version-1 `contracts/deployment-manifest.schema.json`, shared exporter/runtime validation, required E0 review/evidence references and the offline eligibility approval boundary. Exact field contents remain one owner's E0 implementation rather than independent representations. |
| S2 — Deadline origins/coverage | Origins and ingress coverage are closed. Browser Analyze, proxy handler entry, worker spawn and backend admission are explicit; the trusted proxy deadline is clamped into a local monotonic backend timer. One safety-reserve arithmetic issue remains below. |
| S3 — Status correlation | Closed. Query UUID is the original analysis ID; GET needs no request-ID input header; response ID/header echo the query. Startup is explicitly service-wide, other phases require the matching active attempt, and failed polls cannot commit/fail analysis. |
| S4 — Counting semantics | Closed. One release-owned adapter controls traversal/tokenization; all MIME nodes/root depth zero, pre-normalization UTF-8 decoded text bytes and the final `preprocess.tokenize_text` sequence are explicit. Overflow rejects rather than truncates. |

Multipart parsing also moved into the killable child. The parent keeps bounded asynchronous body collection, deadline, directory and IPC ownership. Termination/reap escalation and the prohibition on replacement alongside an unreaped child make the enforcement boundary clearer.

### Remaining high — S2 follow-up: Clock skew and kill/reap spend the same reserve

The profile subtracts 2 seconds from the trusted proxy deadline, allows inter-host clock skew within that 2-second margin, and permits another 2 seconds for termination/reaping. These cannot all fit inside the same reserve.

Let the proxy's real expiry be `D`, and let the backend clock be 1.9 seconds behind the proxy, which passes the stated skew gate. Backend computation expires at real time `D - 2 + 1.9 = D - 0.1`. Its allowed termination phase can continue after `D`; full cleanup/reaping can finish as late as `D + 1.9`. Thus the forwarded deadline does not guarantee backend computation has stopped by the proxy's reported timeout under the allowed profile.

Clear fix: reserve `qualified maximum adverse clock skew + termination/reap bound` independently. With the stated 2-second skew bound and 2-second kill/reap bound, subtract 4 seconds from the trusted proxy deadline when deriving the local monotonic execution timer, or reduce one of those qualified bounds accordingly. Keep the maximum-60-second admission clamp and fail-closed/restart handling. Alternatively explicitly relax the claim about computations surviving a reported timeout, but that weakens AD-7's stated purpose.

Updated verdict: **One unresolved high blocker: separate the clock-skew and termination reserves. All four original seam categories otherwise converge.** No application/runtime validation was performed.

## Final targeted arithmetic recheck — 2026-10-05

The revised Initial deadlines convention now subtracts a 4-second reserve composed of the qualified 2-second clock-skew allowance plus the separate 2-second termination/reap allowance. AD-7 scopes enforcement to backend/proxy execution; browser timeout invalidates its attempt without asserting immediate server cancellation.

Let `D` be the proxy expiry and `delta` be backend UTC minus proxy UTC, with qualified `abs(delta) <= 2s`. The backend's proxy-derived execution timer expires no later than real `D - 4s - delta`, therefore no later than `D - 2s` under the adverse clock offset. The bounded 2-second TERM/KILL/reap sequence then fits by `D`. The independent 60-second admission clamp can only shorten that budget. An already expired remaining budget still rejects rather than extending work.

**Final verdict: PASS. No unresolved interoperability or arithmetic blocker remains in this review.** The brownfield reconciliation also passes. Qualification must still establish the stated clock-skew and process-enforcement bounds and execute the required cleanup/readiness tests; this document review does not supply that runtime evidence.
