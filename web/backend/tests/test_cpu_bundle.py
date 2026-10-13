import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from web.backend import adapter, cloud_release
from web.backend.policy import ROOT
from scripts import verify_release as parity


def installed_versions(packages):
    def version(name):
        if name not in packages:
            raise adapter.PackageNotFoundError(name)
        return packages[name]
    return version


class DistributionIdentity(unittest.TestCase):
    def test_local_full_and_cpu_providers_are_identified(self):
        for name in ("xgboost", "xgboost-cpu"):
            with self.subTest(provider=name), patch.object(adapter, "version", side_effect=installed_versions({name: "3.2.0"})):
                self.assertEqual(adapter.xgboost_provider(), name)

    def test_missing_and_namespace_conflicting_providers_are_rejected(self):
        for packages in ({}, {"xgboost": "3.2.0", "xgboost-cpu": "3.2.0"}):
            with self.subTest(packages=packages), patch.object(adapter, "version", side_effect=installed_versions(packages)):
                with self.assertRaises(ValueError):
                    adapter.xgboost_provider()

    def test_cloud_rejects_full_only_missing_and_conflicting_installations(self):
        for packages in ({}, {"xgboost": "3.2.0"}, {"xgboost": "3.2.0", "xgboost-cpu": "3.2.0"}):
            with self.subTest(packages=packages), patch.object(adapter, "version", side_effect=installed_versions(packages)):
                with self.assertRaises(ValueError):
                    cloud_release.package_versions()
                with self.assertRaises(ValueError):
                    cloud_release.verify_locked_environment(Path("not-a-lock-directory"), ("xgboost-cpu",))

    def test_cloud_records_cpu_distribution_and_enforces_its_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "uv.lock").write_text('[[package]]\nname="xgboost-cpu"\nversion="3.2.0"\n', encoding="utf-8")
            with patch.object(adapter, "version", side_effect=installed_versions({"xgboost-cpu": "3.2.0"})), \
                 patch.object(cloud_release, "version", return_value="3.2.0"), \
                 patch.object(cloud_release, "requires", return_value=[]):
                versions = cloud_release.package_versions()
                self.assertEqual(versions["xgboost-cpu"], "3.2.0")
                self.assertNotIn("xgboost", versions)
                self.assertEqual(cloud_release.verify_locked_environment(root, ("xgboost-cpu",)), {"xgboost-cpu": "3.2.0"})
                with patch.object(cloud_release, "version", return_value="3.3.0"), self.assertRaises(ValueError):
                    cloud_release.verify_locked_environment(root, ("xgboost-cpu",))


class CrossEnvironmentParity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.source = Path(self.temporary.name)
        manifest = b'{"reference":"synthetic"}'
        (self.source / "manifest.json").write_bytes(manifest)
        self.digest = hashlib.sha256(manifest).hexdigest()
        self.record = {"observation": {"source_manifest_sha256": self.digest,
                       "samples": {p.name: {"vector_sha256": "a" * 64,
                                  "result": {"analysis_status": "completed", "label": "legit"}}
                                  for p in (ROOT / "web/backend/samples").glob("*.eml")}},
                       "runtime": {"python_version": "3.12.14", "xgboost_distribution": "xgboost",
                                   "packages": {"xgboost": "3.2.0"}}}

    def tearDown(self):
        self.temporary.cleanup()

    def subprocess_result(self, command, **kwargs):
        self.command, self.options = command, kwargs
        output = Path(command[command.index("--observe-source") + 1])
        output.write_text(json.dumps(self.record), encoding="utf-8")

    def test_reference_uses_explicit_interpreter_bounded_process_and_observation(self):
        with patch.object(parity.subprocess, "run", side_effect=self.subprocess_result):
            result = parity.reference_result(Path("reference-python"), self.source, 17)
        self.assertEqual(result, self.record)
        self.assertEqual(self.command[0], "reference-python")
        self.assertEqual(self.command[1], str(Path(parity.__file__).resolve()))
        self.assertEqual(self.options["timeout"], 17)
        self.assertTrue(self.options["check"])
        self.assertNotIn("shell", self.options)
        self.assertEqual(self.options["stdout"], subprocess.DEVNULL)

    def test_reference_failure_timeout_malformed_and_oversized_output_fail(self):
        for error in (subprocess.TimeoutExpired("reference-python", 1), subprocess.CalledProcessError(1, "reference-python")):
            with patch.object(parity.subprocess, "run", side_effect=error), self.assertRaises(type(error)):
                parity.reference_result(Path("reference-python"), self.source, 1)
        for blob in (b"invalid JSON", b"x" * (parity.MAX_REFERENCE_BYTES + 1)):
            def write(command, **kwargs):
                Path(command[command.index("--observe-source") + 1]).write_bytes(blob)
            with patch.object(parity.subprocess, "run", side_effect=write), self.assertRaises(ValueError):
                parity.reference_result(Path("reference-python"), self.source, 1)

    def test_source_sample_vector_and_envelope_validation(self):
        for change in (lambda r: r["observation"].update(source_manifest_sha256="b" * 64),
                       lambda r: r["observation"]["samples"].pop(next(iter(r["observation"]["samples"]))),
                       lambda r: next(iter(r["observation"]["samples"].values())).update(vector_sha256="bad"),
                       lambda r: next(iter(r["observation"]["samples"].values()))["result"].update(label="phishing")):
            record = copy.deepcopy(self.record)
            change(record)
            with self.assertRaises(ValueError):
                parity.validate_record(record, self.digest)

    def test_cli_cross_environment_equality_and_mismatch(self):
        cpu = copy.deepcopy(self.record)
        cpu["runtime"] = {"python_version": "3.12.14", "xgboost_distribution": "xgboost-cpu", "packages": {"xgboost-cpu": "3.2.0"}}
        arguments = ["verify_release.py", "--source-run", str(self.source), "--archive", str(self.source / "archive.tar"),
                     "--reference-python", str(self.source / "full-python")]
        output = io.StringIO()
        with patch.object(sys, "argv", arguments), patch.object(parity, "reference_result", return_value=self.record) as reference, \
             patch.object(parity, "isolated", return_value=cpu) as isolated, contextlib.redirect_stdout(output):
            parity.main()
        self.assertEqual(json.loads(output.getvalue())["parity"], "passed")
        self.assertEqual(json.loads(output.getvalue())["runtimes"]["reference"]["xgboost_distribution"], "xgboost")
        self.assertEqual(json.loads(output.getvalue())["runtimes"]["cloud"]["xgboost_distribution"], "xgboost-cpu")
        reference.assert_called_once()
        isolated.assert_called_once_with(None, (self.source / "archive.tar").resolve(), 180)
        for kind in ("vector", "label"):
            changed = copy.deepcopy(cpu)
            sample = next(iter(changed["observation"]["samples"].values()))
            if kind == "vector":
                sample["vector_sha256"] = "b" * 64
            else:
                sample["result"]["label"] = "spam_or_phishing"
            with self.subTest(kind=kind), patch.object(sys, "argv", arguments), \
                 patch.object(parity, "reference_result", return_value=self.record), \
                 patch.object(parity, "isolated", return_value=changed), self.assertRaisesRegex(ValueError, "differ"):
                parity.main()

    def test_cli_preserves_reference_venv_interpreter_without_dereferencing(self):
        interpreter = self.source / "full-venv" / "bin" / "python"
        arguments = ["verify_release.py", "--source-run", str(self.source), "--archive", str(self.source / "archive.tar"),
                     "--reference-python", str(interpreter)]
        resolve = Path.resolve
        def guarded_resolve(path, *args, **kwargs):
            if path == interpreter:
                raise AssertionError("Reference venv interpreter was dereferenced")
            return resolve(path, *args, **kwargs)
        with patch.object(sys, "argv", arguments), patch.object(Path, "resolve", guarded_resolve), \
             patch.object(parity, "reference_result", return_value=self.record) as reference, \
             patch.object(parity, "isolated", return_value=self.record), contextlib.redirect_stdout(io.StringIO()):
            parity.main()
        reference.assert_called_once_with(interpreter.absolute(), self.source.resolve(), 180)

    def test_explicit_cpu_reference_is_rejected_before_cloud_loading(self):
        cpu = copy.deepcopy(self.record)
        cpu["runtime"] = {"python_version": "3.12.14", "xgboost_distribution": "xgboost-cpu", "packages": {"xgboost-cpu": "3.2.0"}}
        arguments = ["verify_release.py", "--source-run", str(self.source), "--archive", str(self.source / "archive.tar"),
                     "--reference-python", str(self.source / "cpu-python")]
        with patch.object(sys, "argv", arguments), patch.object(parity, "reference_result", return_value=cpu), \
             patch.object(parity, "isolated") as isolated, self.assertRaisesRegex(ValueError, "full XGBoost"):
            parity.main()
        isolated.assert_not_called()

    def test_observe_source_without_archive_writes_computed_record(self):
        output = self.source / "reference.json"
        fixture = Mock(release=self.digest, metadata={"packages": {"xgboost": "3.2.0"}})
        fixture.vector.return_value.tobytes.return_value = b"controlled-vector"
        fixture.analyze.return_value = {"analysis_status": "completed", "label": "legit"}
        arguments = ["verify_release.py", "--source-run", str(self.source), "--observe-source", str(output)]
        with patch.object(sys, "argv", arguments), patch.object(parity, "original_adapter", return_value=fixture), \
             patch.object(adapter, "xgboost_provider", return_value="xgboost"), \
             patch.object(parity, "isolated", side_effect=AssertionError("Archive mode was entered")):
            parity.main()
        record = json.loads(output.read_text())
        self.assertEqual(record["observation"]["source_manifest_sha256"], self.digest)
        self.assertEqual(len(record["observation"]["samples"]), 5)
        for sample in record["observation"]["samples"].values():
            self.assertEqual(sample["vector_sha256"], hashlib.sha256(b"controlled-vector").hexdigest())
            self.assertEqual(sample["result"], {"analysis_status": "completed", "label": "legit"})
        self.assertEqual(record["runtime"]["xgboost_distribution"], "xgboost")
        self.assertEqual(fixture.vector.call_count, 5)
        self.assertEqual(fixture.analyze.call_count, 5)

    def test_reference_failures_report_safe_stage_and_cannot_accept_nonzero_success(self):
        output = self.source / "failure.json"
        arguments = ["verify_release.py", "--source-run", str(self.source), "--observe-source", str(output)]
        with patch.object(sys, "argv", arguments), \
             patch.object(parity, "original_adapter", side_effect=ImportError("private credential or email")), self.assertRaises(SystemExit):
            parity.main()
        self.assertEqual(json.loads(output.read_text()), {"failure": "REFERENCE_DEPENDENCY"})
        self.assertNotIn("private", output.read_text())
        def failed(command, **kwargs):
            Path(command[command.index("--observe-source") + 1]).write_text(output.read_text())
            raise subprocess.CalledProcessError(1, command)
        with patch.object(parity.subprocess, "run", side_effect=failed), self.assertRaisesRegex(ValueError, "REFERENCE_DEPENDENCY"):
            parity.reference_result(Path("reference-python"), self.source, 1)
        def false_success(command, **kwargs):
            self.subprocess_result(command, **kwargs)
            raise subprocess.CalledProcessError(1, command)
        with patch.object(parity.subprocess, "run", side_effect=false_success), self.assertRaisesRegex(ValueError, "process failed"):
            parity.reference_result(Path("reference-python"), self.source, 1)
