---
title: 'Per-result explanation for the served MLP via Integrated Gradients'
type: 'feature'
created: '2026-11-04'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The web serves the baseline_v6 MLP, so results carry only a label: AD-14 admits only exact tree contributions (XGBoost `pred_contribs`) and forbids other methods. The user wants to keep the MLP and show per-result factors again.

**Approach:** Compute Integrated Gradients (IG) of the MLP's decision margin (logit of class 1) for the served vector, relative to a fixed reference vector. For a one-hidden-layer ReLU MLP, IG has a closed form: each hidden unit switches at most once along the straight path, so the integral is exact. Summed attributions plus the reference margin reproduce the margin; measured error on v6 test rows is about 1e-14, at about 0.06 ms per email. Factors reuse the AD-14 grouping, ordering and strength. Amend AD-14 to admit this method, and tell the user in the UI that the factors are an estimate relative to the reference.

## Boundaries & Constraints

**Always:**
- XGBoost releases keep `pred_contribs` unchanged.
- IG applies only to `MLPClassifier` with exactly one hidden layer, `relu` activation and a logistic output. Any other MLP shape returns the label only.
- The reference is computed at startup from hash-verified run arrays, never from uploads.
- Startup verifies, on the release's test arrays, that (a) the float64 forward pass reproduces `predict_proba` (atol 1e-6) and (b) attributions + reference margin reproduce the margin within `ADDITIVITY_TOLERANCE` (1e-3). Otherwise the worker stays unready (EXPLANATION). A per-request mismatch returns `INTERNAL_ERROR`.
- The only HTTP schema change is the required `explanation.method` field. Factors stay transient, are never logged, and are deterministic across repeat, reorder and restart.

**Never:**
- Sampling-based or surrogate methods (KernelSHAP, LIME).
- Riemann-sum IG.
- New dependencies.
- Changes to frozen pipeline files or the bundled run.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HAPPY_PATH | Valid .eml, v6 MLP pinned | Label + 1–5 factors (text_content + 134 features); UI shows the estimate notice | N/A |
| XGBoost release | Fixture with XGBoost selected | Factors from pred_contribs, as before | N/A |
| Unsupported MLP | MLP with 2 hidden layers or tanh | Label only, metadata explanation None | N/A |
| Broad target | target_mode broad | Label only (unchanged rule) | N/A |
| Completeness broken | Patched weights or reference so sums differ | Startup EXPLANATION unready; per-request INTERNAL_ERROR | No result returned |
| All-zero attribution | Email vector equals reference | Label only | N/A |
| Missing method | Backend explanation without `method`, or unknown value | Proxy/browser reject as UPSTREAM_INVALID_RESPONSE | Existing strict validation |

**Decisions (2026-11-04):**
- Reference = mean of the validation rows labelled legitimate (`data_X_validation.npy` where `data_y_validation.npy == 0`); factors describe how this email differs from a typical legitimate email.
- Contract change: `explanation` gains a required `method` field, `"exact_contributions"` (XGBoost) or `"integrated_gradients"` (MLP). The UI shows the current notice for exact results and an estimate notice for IG results, saying they are an estimate compared with a typical legitimate email and not proof.
- Spec kept whole at about 1,700 tokens; subagents allowed for this run.

</frozen-after-approval>

## Code Map

- `web/backend/adapter.py`:
  - :23-26 constants.
  - :293-302 explanation gate and startup check: today `hasattr(get_booster)`; extend to the supported MLP shape and load the reference from `data_X_validation.npy`/`data_y_validation.npy` (both manifest artifacts).
  - :364-375 `contributions()`: today XGBoost only; dispatch to an IG branch returning per-column attributions.
  - :377-393 `explain()`: reuse unchanged.
  - :307 metadata `explanation`: add a method id such as `mlp_integrated_gradients`.
- Closed form (prototype, scratchpad `ig_proto.py`): with `za = ref@W1+b1`, `zb = x@W1+b1`, `frac_j` = share of α∈[0,1] where unit j is active (1, 0, or the part before/after α = -za/(zb-za)); `IG = (x-ref) * (W1 @ (w2 * frac))`.
- `web/backend/tests/test_demo.py`:
  - the `Explanation` class forces XGBoost; add MLP IG cases (completeness, determinism, unsupported shape via a variant pickle, broken completeness).
  - `test_unsupported_releases_return_label_only` `unedited_mlp_fixture` now gets explained; replace it with an unsupported-shape case.
  - `PinnedRelease` asserts explanation None → expect `mlp_integrated_gradients`.
- `web/contracts/analysis.schema.json:24-27` `Explanation` -- add required `method` enum; then `npm.cmd run contracts:generate` in web/frontend (never hand-edit `lib/contracts.generated.ts`); runtime validators in `web/frontend/lib/contracts.ts` (`isSuccess`/`validateFactors`) and the proxy; backend validates responses against the same schema. Every test fixture explanation (frontend unit `explanation`/`controller`/`proxy`, browser `analysis.spec.ts`, backend `test_schema_rejects_malformed_explanations`) needs `method`.
- `web/frontend/lib/explanation.ts` (notice chosen by `method`; copy per EXPERIENCE.md); `web/frontend/components/AnalysisPage.tsx:52-55` (renders the notice); `web/frontend/tests/browser/analysis.spec.ts:54` (notice text); `web/frontend/tests/integration/real-model.test.ts:78-90` (expect explanation again, labels from the catalogue).
- Docs (canonical, then `node web/scripts/sync-docs.mjs`):
  - `_bmad-output/planning-artifacts/architecture/architecture-PhishingEmailDetection-2026-10-05/ARCHITECTURE-SPINE.md:133-137` (AD-14);
  - `_bmad-output/planning-artifacts/ux-designs/ux-PhishingEmailDetection-2026-10-05/EXPERIENCE.md` (notice copy);
  - `_bmad-output/specs/spec-iap-web-application/local-demo.md` (2026-11-04 update);
  - `AGENTS.md` (explanations line);
  - `web/backend/README.md`.

## Tasks & Acceptance

**Execution:**
- [ ] `web/backend/adapter.py` -- IG branch, reference loading, startup checks, metadata -- serve MLP factors.
- [ ] `web/backend/tests/test_demo.py` -- matrix rows as tests; adjust PinnedRelease and label-only cases.
- [ ] `web/contracts/analysis.schema.json`, generated types, `lib/contracts.ts`, proxy, backend `explain()` -- required `method` in every explanation.
- [ ] `web/frontend/lib/explanation.ts`, `AnalysisPage.tsx` + frontend tests -- notice by method; real-model expects factors and the estimate notice.
- [ ] Docs -- AD-14 amendment, EXPERIENCE copy, local-demo, AGENTS.md, backend README; sync.

**Acceptance Criteria:**
- Given the bundled v6 run, when the worker starts, then metadata `explanation` is `mlp_integrated_gradients`, and every success from the five samples carries factors that validate against the schema and catalogue.
- Given any of the first 256 test rows, when IG is computed, then attributions plus reference margin equal the float64 margin within 1e-3.
- Given the backend and frontend suites run with web/.venv, when executed, then all pass, including test:real-model (msedge) showing the factors and notice.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `cd web; .venv/Scripts/python.exe -m unittest discover -s backend/tests -v` -- expected: all pass.
- In web/frontend: `npm.cmd run contracts:check`, `npm.cmd test`, `npm.cmd run test:browser`, `$env:PLAYWRIGHT_CHANNEL='msedge'; npm.cmd run test:real-model` -- expected: pass.
