"""Kiểm tra web/scripts/bundle-run.py trên run fixture: chép đúng, lỗi thì không đổi web/model/."""
import contextlib
import hashlib
import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS = Path(__file__).resolve().parent
SCRIPT = TESTS.parents[1] / "scripts" / "bundle-run.py"
FIXTURE_RUN = TESTS / "fixture_run"
MANIFEST = "dumped_models/classification/run_manifest.json"


def load_script():
    spec = importlib.util.spec_from_file_location("bundle_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(folder):
    """Tên và SHA-256 của mọi file (bỏ thư mục tạm), để so trước/sau một lần chạy lỗi."""
    return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.rglob("*")) if path.is_file()}


class BundleRun(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.temp.name)
        self.run = root / "source" / "2026-01-01_fixture"
        shutil.copytree(FIXTURE_RUN, self.run)
        self.model = root / "model"
        self.script = load_script()

    def tearDown(self):
        self.temp.cleanup()

    def bundle(self):
        with patch.object(self.script, "MODEL_ROOT", self.model), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.script.main(["--run", str(self.run)])

    def test_good_run_copies_manifest_bytes_and_artifacts_only(self):
        self.assertEqual(self.bundle(), 0)
        bundled = self.model / self.run.name
        self.assertEqual((bundled / MANIFEST).read_bytes(), (self.run / MANIFEST).read_bytes())
        self.assertEqual(snapshot(bundled), snapshot(self.run))
        # Run v6 không dùng NLTK: chỉ có thư mục run, không thư mục tạm hay nltk_data.
        self.assertEqual([path.name for path in self.model.iterdir()], [self.run.name])

    def test_bad_source_exits_non_zero_and_leaves_previous_bundle(self):
        self.assertEqual(self.bundle(), 0)
        before = snapshot(self.model)
        tampered = self.run / "data_X_test.npy"
        tampered.write_bytes(tampered.read_bytes() + b"x")
        self.assertEqual(self.bundle(), 1)
        tampered.unlink()
        self.assertEqual(self.bundle(), 1)
        self.assertEqual(snapshot(self.model), before)

    def test_failed_restore_names_previous_folder(self):
        self.assertEqual(self.bundle(), 0)
        rename = Path.rename
        def failing(path, target):
            # Đổi tên bản mới vào chỗ và khôi phục bản cũ đều lỗi; chỉ cho đổi tên bản cũ ra ngoài.
            if path.parent.name.startswith(".bundle-") or path.name.startswith(".old-"):
                raise OSError("rename blocked")
            return rename(path, target)
        errors = io.StringIO()
        with patch.object(Path, "rename", failing), patch.object(self.script, "MODEL_ROOT", self.model),                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            self.assertEqual(self.script.main(["--run", str(self.run)]), 1)
        self.assertIn(".old-", errors.getvalue())
        self.assertNotIn("không đổi", errors.getvalue())

    def test_missing_artifact_writes_nothing(self):
        (self.run / "dumped_models" / "classification" / "MLP.pkl").unlink()
        self.assertEqual(self.bundle(), 1)
        self.assertEqual(snapshot(self.model), {})

    def test_previous_nltk_data_folder_is_left_untouched(self):
        old = self.model / "nltk_data" / "corpora" / "stopwords" / "english"
        old.parent.mkdir(parents=True)
        old.write_text("a\nthe\n", encoding="utf-8")
        self.assertEqual(self.bundle(), 0)
        self.assertEqual(old.read_text(encoding="utf-8"), "a\nthe\n")


if __name__ == "__main__":
    unittest.main()
