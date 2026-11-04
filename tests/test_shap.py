"""Kiểm tra analyze_shap.py trên một run 19-10 nhỏ train từ email tổng hợp."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

import train
from analyze_shap import DOC2VEC_GROUP, analyze, contributions, load_run
from test_pipeline import training_frame


class ShapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(cls.temp.name)
        cls.run_dir = root / "run"
        candidates = {"XGBoost": [XGBClassifier(n_estimators=20, max_depth=3, random_state=42, n_jobs=1)],
                      "Logistic Regression": [LogisticRegression(max_iter=500)]}
        with patch.object(train, "BASE_DIR", root), contextlib.redirect_stdout(io.StringIO()):
            train.training(data=training_frame(80), output_dir=cls.run_dir, candidates=candidates,
                           epochs=2, train_bert=False, run_ablation=False)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_contributions_are_additive_and_reports_are_written(self):
        data = load_run(self.run_dir, "XGBoost")
        contrib, bias = contributions(data["model"], data["X"])
        margin = data["model"].get_booster().predict(__import__("xgboost").DMatrix(data["X"]), output_margin=True)
        np.testing.assert_allclose(contrib.sum(axis=1) + bias, margin, atol=1e-3)
        result = analyze(self.run_dir, "XGBoost", output=self.run_dir / "shap_test")
        out = result["output"]
        for name in ("shap_global.csv", "shap_by_source.csv", "shap_errors.csv", "shap_top.png"):
            self.assertTrue((out / name).is_file(), name)
        summary = pd.read_csv(out / "shap_global.csv", index_col="feature")
        manifest = json.loads((self.run_dir / "dumped_models/classification/run_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(summary), 1 + len(manifest["settings"]["feature_names"]))
        self.assertIn(DOC2VEC_GROUP, summary.index)
        self.assertAlmostEqual(summary.share_percent.sum(), 100.0, places=6)
        self.assertTrue((summary.mean_abs_shap.diff().dropna() <= 1e-12).all())
        by_source = pd.read_csv(out / "shap_by_source.csv", index_col=0)
        self.assertEqual(int(by_source.Count.sum()), len(data["y"]))

    def test_non_xgboost_model_and_tampered_artifact_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "XGBoost"):
            load_run(self.run_dir, "Logistic Regression")
        path = self.run_dir / "test_metadata.csv"
        original = path.read_bytes()
        self.addCleanup(path.write_bytes, original)
        path.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "test_metadata.csv"):
            load_run(self.run_dir, "XGBoost")


if __name__ == "__main__":
    unittest.main()
