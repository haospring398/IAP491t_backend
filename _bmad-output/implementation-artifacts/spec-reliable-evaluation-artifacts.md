---
title: 'Reliable evaluation artifacts'
type: 'bugfix'
created: '2026-09-25'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The saved test arrays have different sample counts, and the current CSV and ROC plot calculate ROC-AUC from different inputs. Running evaluation against mixed or stale artifacts can fail late or produce misleading results.

**Approach:** Validate the test arrays and each classifier's expected feature count before generating outputs. Use positive-class probabilities for ROC-AUC in both the CSV and plot, while preserving the existing evaluation entry point and output files.

</frozen-after-approval>

## Implementation Notes

- `evaluate.py` now validates held-out arrays, the saved scaler schema, and classifier feature counts/classes before writing reports. It calculates both CSV and plotted ROC-AUC from positive-class probabilities.
- `tests/test_evaluate.py` uses isolated temporary artifacts to verify a valid run and three invalid artifact cases.
- The checked-in arrays remain inconsistent (X=8238, y=75187); evaluation now reports this clearly. Regenerating them requires a full training run and is outside this bug fix.
- Review added a combined-width check against the saved Doc2Vec size and a non-separable ROC-AUC fixture. Five integration tests pass.

## Review Triage Log

- **high, patched:** A 142-column test array and matching classifier could pass despite the current 140-column pipeline. Evaluation now checks saved Doc2Vec width plus `FEATURE_NAMES` before predictions.
- **medium, deferred:** Equal dimensions do not prove all artifacts came from the same training run. A run manifest emitted by `train.py` would be needed for provenance and would change the training artifact format.
- **medium, patched:** The original separable test data gave AUC=1 for labels and probabilities, masking a regression. The fixture now gives different values and asserts probability AUC.
- **medium, deferred:** CSV and plots are written in sequence, so a plotting failure can leave mixed versions. This behavior predates the change; atomic report publishing needs a separate change.
- **low, patched:** The test's engineered feature count now derives from `FEATURE_NAMES`, avoiding a false failure when the schema changes.
