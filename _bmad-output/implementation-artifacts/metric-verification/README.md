# Evaluation evidence

`log-provenance.json` records verification against the user-provided successful train/evaluate terminal log. The selected run ID matches the log; all ten CSV rows agree with its six-decimal output. This comparison does not independently reproduce full-precision predictions or plot contents.

`recomputed.csv` contains only three independently recomputed models: Logistic Regression, Random Forest and XGBoost. These matched the existing report. The optional full recomputation was cancelled after the successful evaluation log was supplied. This partial CSV is not a complete evaluation report.

Root evaluation reports, saved models and the current run pointer were preserved.
