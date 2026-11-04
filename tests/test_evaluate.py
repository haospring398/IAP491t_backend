"""Kiểm tra đọc corpus, khử trùng lặp trước khi chia và evaluate.py theo bản 19-10."""

import csv
import json
import mailbox
import pathlib
import pickle
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from artifact_store import CLASSIFIERS, publish, write_manifest, selected_run
from dataset_audit import record_id
from evaluate import evaluate, file_digest, select_threshold, validation_rank
from load_data import load_data_phishing, _read_raw_emails, reset_source_stats, SOURCE_COUNTS, SOURCE_ERRORS
from preprocess import FEATURE_NAMES, compute_dedup_key, group_email_variants, split_train_validation_test

EVALUATE = pathlib.Path(__file__).resolve().parents[1] / "evaluate.py"


def raw_email(subject, body, sender="sender@example.org"):
    return f"From: {sender}\nTo: user@example.org\nSubject: {subject}\n\n{body}\n"


class CorpusTests(unittest.TestCase):
    def test_cross_source_duplicates_are_removed_before_group_disjoint_split(self):
        from train import select_label_scope
        rows = []
        def add(text, cls, kind, location):
            rows.append({"Text": text, "Class": cls, "Source": location.split(":")[0], "Location": location,
                         "LabelKind": kind, "OriginalLabel": str(cls), "LabelBasis": "test fixture",
                         "RecordId": record_id(location)})
        # Cùng subject, body chỉ khác khoảng trắng/hoa thường: phải coi là một email.
        add(raw_email("Verify account", "  SAME   Body\ncontent ", "csv@example.com"), 1,
            "positive_unspecified", "curated.csv:record:1")
        add(raw_email("Verify account", "same body CONTENT", "nazario@example.com"), 1,
            "phishing", "phishing0.mbox:message:0")
        self.assertEqual(compute_dedup_key(rows[0]["Text"]), compute_dedup_key(rows[1]["Text"]))
        for i in range(30):
            add(raw_email(f"Invoice {i}", f"unique phishing payload number {i} " * 3), 1,
                "phishing", f"phishing0.mbox:message:{i + 1}")
            add(raw_email(f"Meeting {i}", f"unique legitimate note number {i} " * 3), 0,
                "legitimate", f"enron:message:{i}")
        frame = pd.DataFrame(rows)
        with tempfile.TemporaryDirectory() as tmp, patch("builtins.print"):
            data = select_label_scope(frame, "phishing", pathlib.Path(tmp))
            audit = pd.read_csv(pathlib.Path(tmp) / "training_dispositions.csv")
        # Bản có nhãn phishing rõ ràng được giữ; bản CSV không rõ nhãn bị loại vì trùng lặp.
        self.assertEqual(len(data), 61)
        self.assertTrue(data._dedup_key.is_unique)
        self.assertIn(record_id("phishing0.mbox:message:0"), set(data.RecordId))
        disposition = audit.set_index("RecordId").Disposition
        self.assertEqual(disposition[record_id("curated.csv:record:1")], "duplicate_content")
        data["_group"] = group_email_variants(data)
        train, validation, test = split_train_validation_test(data)
        self.assertEqual(len(train) + len(validation) + len(test), len(data))
        for left, right in ((train, validation), (train, test), (validation, test)):
            self.assertTrue(set(left._dedup_key).isdisjoint(right._dedup_key))
            self.assertTrue(set(left._group).isdisjoint(right._group))

    def test_csv_mbox_and_skipped_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "README.md").write_text("not mail", encoding="utf-8")
            (root / "NOTES.md").write_text("also not mail", encoding="utf-8")
            (root / "vectors.csv").write_text("0,label\nvector,1\n", encoding="utf-8")
            with (root / "mail.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["sender", "receiver", "subject", "body", "label"])
                writer.writerows([["alice@example.com", "bob@example.com", "legit", "hello", "0"],
                                 ["", "", "bad", "click", "1"],
                                 ["", "", "empty", "", "bad"], ["", "", "", "", "1"],
                                 ["", "", "large", "x" * 150000, "0"]])
            (root / "raw-email").write_text("From sender@example.com\nSubject: raw\n\nBody", encoding="utf-8")
            ham_dir = root / "SpamAssasin" / "easy_ham"
            ham_dir.mkdir(parents=True)
            (ham_dir / "ham1").write_text("Subject: ham\n\nHello", encoding="utf-8")
            box = mailbox.mbox(str(root / "phishing-2020"))
            box.add("Subject: one\n\nFirst")
            box.add("Subject: two\n\nSecond")
            box.flush()
            box.close()
            reset_source_stats()
            with patch("builtins.print"):
                data = load_data_phishing(pd.DataFrame(), str(root))
            self.assertEqual(len(data), 8)
            # Nhãn số của CSV chưa có schema đã kiểm duyệt thì giữ là unknown, không đoán 0/1.
            self.assertEqual(data.Class.notna().sum(), 2)
            self.assertEqual(set(data.loc[data.Class.notna(), "LabelKind"]), {"phishing"})
            self.assertEqual(int(data.LabelKind.eq("unknown").sum()), 6)
            # Dòng CSV được dựng thành email MIME (body base64); kiểm tra sau khi giải mã.
            from preprocess import _get_email_body, _parse_email
            message = _parse_email(data.Text.iloc[0])
            self.assertEqual((message["From"], message["To"], message["Subject"]),
                             ("alice@example.com", "bob@example.com", "legit"))
            self.assertEqual(_get_email_body(message)[0].strip(), "hello")
            self.assertEqual(SOURCE_COUNTS["metadata_skipped"], 2)
            self.assertEqual(SOURCE_COUNTS["csv_vector_or_unsupported"], 1)
            self.assertEqual(SOURCE_COUNTS["csv_rows_without_email_content"], 1)
            self.assertEqual(SOURCE_COUNTS["source/phishing-2020"], 2)
            self.assertEqual(dict(SOURCE_ERRORS), {})
            # _read_raw_emails cộng dồn vào SOURCE_COUNTS nên gọi sau khi kiểm tra bộ đếm.
            with patch("builtins.print"):
                self.assertEqual(len(_read_raw_emails(str(root), verbose=False)), 8)

    def test_mbox_read_error_is_reported_and_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "phishing-2021").write_text(
                "From sender@example.com Mon Jan  1 00:00:00 2024\nSubject: x\n\nbody\n", encoding="utf-8")
            reset_source_stats()
            with patch("load_data.mailbox.mbox", side_effect=OSError("read failed")), patch("builtins.print"):
                data = load_data_phishing(pd.DataFrame(), tmp)
            self.assertTrue(data.empty)
            self.assertEqual(SOURCE_ERRORS["OSError"], 1)


class ThresholdTests(unittest.TestCase):
    def test_threshold_maximizes_recall_under_validation_precision_floor(self):
        y = np.array([0, 0, 0, 1, 1, 1, 0, 1])
        scores = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.65, 0.9])
        decision = select_threshold(y, scores, 0.75)
        self.assertTrue(decision["precision_target_met"])
        self.assertGreaterEqual(decision["precision"], 0.75)
        self.assertAlmostEqual(decision["threshold"], 0.4)
        self.assertAlmostEqual(decision["recall"], 1.0)
        strict = select_threshold(y, scores, 0.99)
        self.assertTrue(strict["precision_target_met"])
        self.assertAlmostEqual(strict["threshold"], 0.7)
        self.assertAlmostEqual(strict["recall"], 0.5)
        # Không ngưỡng nào đạt mức precision: dùng F2 tốt nhất và đánh dấu chưa đạt.
        unattainable = select_threshold(np.array([0, 1, 0, 1]), np.array([0.9, 0.1, 0.8, 0.2]), 0.9)
        self.assertFalse(unattainable["precision_target_met"])

    def test_feasible_candidate_outranks_higher_f2_fallback(self):
        feasible = {"precision_target_met": True, "recall": 0.5, "f2": 0.5, "average_precision": 0.5}
        fallback = {"precision_target_met": False, "recall": 1.0, "f2": 0.9, "average_precision": 0.9}
        self.assertGreater(validation_rank(feasible), validation_rank(fallback))

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            select_threshold([1, 1], [0.2, 0.8])
        with self.assertRaises(ValueError):
            select_threshold([0, 1], [0.2, 0.8], 1.5)


class EvaluationTests(unittest.TestCase):
    """Run schema 2 tối thiểu: mảng test, metadata, manifest có ngưỡng và hash."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.models = self.base / "dumped_models" / "classification"
        self.models.mkdir(parents=True)
        rng = np.random.default_rng(0)
        self.y = np.array([0, 1] * 20)
        self.X = rng.normal(size=(40, 4)) + self.y[:, None] * 0.8
        self.model = LogisticRegression().fit(self.X, self.y)
        self.thresholds = {"Logistic Regression": 0.7, "Second": 0.3}
        self.write_run()

    def write_run(self, status="complete", extra_models=None):
        np.save(self.base / "data_X_test.npy", self.X)
        np.save(self.base / "data_y_test.npy", self.y)
        pd.DataFrame({"RecordId": [f"r{i}" for i in range(len(self.y))], "Class": self.y,
                      "Source": ["a", "b"] * (len(self.y) // 2)}).to_csv(self.base / "test_metadata.csv", index=False)
        models = {}
        for name, threshold in self.thresholds.items():
            with (self.models / f"{name}.pkl").open("wb") as handle:
                pickle.dump(self.model, handle)
            models[name] = {"file": f"{name}.pkl", "threshold": threshold}
        models.update(extra_models or {})
        artifacts = ["data_X_test.npy", "data_y_test.npy", "test_metadata.csv",
                     *[f"dumped_models/classification/{c['file']}" for c in models.values() if "file" in c],
                     *[c["test_scores"] for c in models.values() if "test_scores" in c]]
        manifest = {"status": status, "schema_version": 2, "target_mode": "phishing",
                    "selected_model": "Logistic Regression", "models": models,
                    "test_used_for_selection": False,
                    "artifacts": {path: file_digest(self.base / path) for path in artifacts}}
        (self.models / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def run_evaluation(self):
        return subprocess.run([sys.executable, str(EVALUATE), "--run", str(self.base)],
                              capture_output=True, text=True, check=False)

    def test_valid_run_uses_validation_threshold_and_probability_auc(self):
        completed = self.run_evaluation()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        rows = pd.read_csv(self.base / "evaluation_results.csv").set_index("Model")
        scores = self.model.predict_proba(self.X)[:, 1]
        expected_auc = roc_auc_score(self.y, scores)
        self.assertNotEqual(expected_auc, roc_auc_score(self.y, self.model.predict(self.X)))
        for name, threshold in self.thresholds.items():
            row = rows.loc[name]
            # Chỉ số phân loại dùng ngưỡng chọn trên validation, ROC-AUC dùng xác suất.
            predicted = (scores >= threshold).astype(int)
            self.assertAlmostEqual(row["Threshold"], threshold)
            self.assertEqual(row["TP"], int(((predicted == 1) & (self.y == 1)).sum()))
            self.assertEqual(row["FP"], int(((predicted == 1) & (self.y == 0)).sum()))
            self.assertAlmostEqual(row["ROC-AUC"], expected_auc)
        self.assertTrue(rows.loc["Logistic Regression", "Selected-on-validation"])
        self.assertFalse(rows.loc["Second", "Selected-on-validation"])
        for name in ("ROCs.png", "confusion-matrix.png", "evaluation_by_source.csv", "error_analysis.csv"):
            self.assertTrue((self.base / name).is_file(), name)
        by_source = pd.read_csv(self.base / "evaluation_by_source.csv")
        self.assertEqual(set(by_source.Source), {"a", "b"})

    def test_changed_or_incomplete_run_leaves_report_untouched(self):
        report = self.base / "evaluation_results.csv"
        report.write_text("existing report", encoding="utf-8")
        (self.models / "Second.pkl").write_bytes(b"corrupt")
        failed = self.run_evaluation()
        self.assertIn("Artifact changed since training", failed.stderr)
        self.assertEqual(report.read_text(encoding="utf-8"), "existing report")
        self.write_run(status="incomplete")
        failed = self.run_evaluation()
        self.assertIn("Training is incomplete", failed.stderr)
        self.assertEqual(report.read_text(encoding="utf-8"), "existing report")

    def test_test_provenance_must_align_with_arrays(self):
        metadata = pd.read_csv(self.base / "test_metadata.csv")
        metadata["Class"] = 1 - metadata["Class"]
        metadata.to_csv(self.base / "test_metadata.csv", index=False)
        # Cập nhật hash để lỗi duy nhất còn lại là metadata không khớp nhãn test.
        manifest = json.loads((self.models / "run_manifest.json").read_text(encoding="utf-8"))
        manifest["artifacts"]["test_metadata.csv"] = file_digest(self.base / "test_metadata.csv")
        (self.models / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        failed = self.run_evaluation()
        self.assertIn("Test provenance is not aligned", failed.stderr)
        self.assertFalse((self.base / "evaluation_results.csv").exists())

    def test_misaligned_bert_scores_are_rejected(self):
        np.save(self.base / "data_bert_test_scores.npy", np.full(len(self.y) - 1, 0.5))
        self.write_run(extra_models={"BERT": {"kind": "bert", "test_scores": "data_bert_test_scores.npy",
                                              "threshold": 0.5}})
        failed = self.run_evaluation()
        self.assertIn("BERT probabilities are invalid or not aligned", failed.stderr)
        self.assertFalse((self.base / "evaluation_results.csv").exists())

    def test_legacy_run_without_manifest_uses_default_threshold(self):
        (self.models / "run_manifest.json").unlink()
        completed = self.run_evaluation()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        rows = pd.read_csv(self.base / "evaluation_results.csv")
        self.assertEqual(set(rows.Threshold), {0.5})
        self.assertFalse((self.base / "error_analysis.csv").exists())

    def test_interrupted_training_leaves_run_that_evaluation_rejects(self):
        import train
        output = self.base / "interrupted"
        with patch.object(train, "prepare_data", side_effect=RuntimeError("training interrupted")), \
             patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "training interrupted"):
                train.training(data=pd.DataFrame(), output_dir=output, train_bert=False, run_ablation=False)
        manifest = json.loads((output / "dumped_models" / "classification" / "run_manifest.json").read_text())
        self.assertEqual(manifest, {"status": "incomplete"})
        with self.assertRaisesRegex(RuntimeError, "Training is incomplete"):
            evaluate(output)


class ArtifactStoreTests(unittest.TestCase):
    """artifact_store.py vẫn phục vụ run web demo đang pin."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.models = self.root / "dumped_models" / "classification"
        self.run = self.models / "runs" / "run1"
        self.run.mkdir(parents=True)
        X = np.zeros((6, 100 + len(FEATURE_NAMES)))
        X[:, 0] = [-3, -2, -1, 0, 1, 2]
        y = np.array([0, 0, 1, 0, 1, 1])
        model = LogisticRegression().fit(X, y)
        np.save(self.run / "data_X_test.npy", X)
        np.save(self.run / "data_y_test.npy", y)
        for name in CLASSIFIERS:
            with (self.run / f"{name}.pkl").open("wb") as handle:
                pickle.dump(model, handle)
        with (self.run / "feature_scaler.pkl").open("wb") as handle:
            pickle.dump(StandardScaler().fit(np.zeros((6, len(FEATURE_NAMES)))), handle)
        with (self.run / "model_dbow.pkl").open("wb") as handle:
            pickle.dump(SimpleNamespace(vector_size=100), handle)
        write_manifest(self.run, "run1", X, y, SimpleNamespace(vector_size=100), {}, 0)
        (self.models / "current.json").write_text('{"run_id":"run1"}', encoding="utf-8")

    def test_publish_keeps_previous_pointer_on_failure(self):
        import os
        old = pathlib.Path.cwd()
        try:
            os.chdir(self.root)
            with self.assertRaises(Exception):
                publish("incomplete")
            self.assertEqual(selected_run().name, "run1")
        finally:
            os.chdir(old)


if __name__ == "__main__":
    unittest.main()
