"""Cloud delivery failure boundaries without requiring any model artifacts."""
import asyncio
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from starlette.requests import Request
from web.backend import cloud_release as cloud
from web.backend.cloud_worker import worker as cloud_worker
from web.backend.policy import POLICY, ROOT, RUN_ID
from web.backend.service import Supervisor, create_app

TOKEN = "test-only-cloud-api-token"
URL = "https://teststore.private.blob.vercel-storage.com/release.tar"


def headers():
    return {"Authorization": "Bearer " + TOKEN, "X-Request-ID": str(uuid.uuid4()),
            "X-Analysis-Deadline": str(int(time.time() * 1000 + POLICY["deadlines"]["proxyMs"])),
            "Content-Type": "multipart/form-data; boundary=test"}


def scope(h):
    return {"type": "http", "method": "POST", "path": "/v1/analyze",
            "headers": [(k.lower().encode(), v.encode()) for k, v in h.items()]}


class CloudConfiguration(unittest.TestCase):
    def test_private_url_and_secret_validation(self):
        digest = "a" * 64
        self.assertEqual(cloud.ReleaseConfig.validate(URL, TOKEN, digest).digest, digest)
        bad_urls = ["http://" + URL[8:], URL.replace(".private.", ".public."),
                    URL + "?token=secret", URL + "#fragment", URL.replace("https://", "https://user@"),
                    URL.replace("/release", ":443/release"), URL.replace("/release", "/../release"),
                    URL.replace("/release", "/%2e%2e/release"), URL.replace("teststore.", "teststore.evil."),
                    URL + "\n", "https://localhost/release.tar"]
        for url in bad_urls:
            with self.subTest(url=url), self.assertRaises(cloud.ReleaseFailure) as caught:
                cloud.ReleaseConfig.validate(url, TOKEN, digest)
            self.assertEqual(str(caught.exception), "CLOUD_CONFIGURATION")
        for token, value in [("", digest), ("has space", digest), ("x\n", digest), (TOKEN, "A" * 64), (TOKEN, "bad")]:
            with self.assertRaises(cloud.ReleaseFailure):
                cloud.ReleaseConfig.validate(URL, token, value)

    def test_model_free_entrypoint_import(self):
        script = "import app, sys; assert not any(n in sys.modules for n in ('numpy','preprocess','artifact_store','gensim','xgboost')); assert app.app.state.supervisor.startup_wait"
        subprocess.run([sys.executable, "-c", script], cwd=ROOT, check=True, timeout=20)

    def test_missing_configuration_live_unready_and_no_class(self):
        with patch.dict(os.environ, {"MODEL_BLOB_URL": "", "BLOB_READ_WRITE_TOKEN": "", "MODEL_RELEASE_SHA256": ""}):
            app = create_app(TOKEN, worker_target=cloud_worker, startup_wait=True)
            with TestClient(app) as client:
                async def initialized():
                    await app.state.supervisor.startup
                client.portal.call(initialized)
                self.assertEqual(app.state.supervisor.last_failure, "CLOUD_CONFIGURATION")
                self.assertEqual(client.get("/health/live").status_code, 200)
                h = headers()
                response = client.post("/v1/analyze", headers=h, content=b"--test--\r\n")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["error"]["code"], "MODEL_UNAVAILABLE")
                self.assertEqual(response.headers["X-Request-ID"], h["X-Request-ID"])
                self.assertNotIn("label", response.json())
                self.assertEqual(client.get("/health/ready").status_code, 503)

    def test_redirect_rejected_without_forwarding_secret(self):
        with self.assertRaises(cloud.ReleaseFailure):
            cloud.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test")


class ArchiveBoundaries(unittest.TestCase):
    def archive(self, entries=None):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name, data, kind in entries or [(name, b"{}" if name.endswith(".json") else b"artifact", tarfile.REGTYPE) for name in cloud.MEMBERS]:
                info = tarfile.TarInfo(name)
                info.type, info.size = kind, len(data)
                archive.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
        return out.getvalue()

    def unpack(self, blob, digest=None):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            cloud.unpack_stream(io.BytesIO(blob), destination, digest or hashlib.sha256(blob).hexdigest(), time.monotonic() + 10)
            return {p.name: p.read_bytes() for p in destination.iterdir()}

    def test_bounded_success_and_full_archive_digest(self):
        blob = self.archive()
        self.assertEqual(set(self.unpack(blob)), set(cloud.MEMBERS))
        with self.assertRaises(cloud.ReleaseFailure):
            self.unpack(blob, "a" * 64)
        changed_padding = blob[:-1] + b"x"
        with self.assertRaises(cloud.ReleaseFailure):
            self.unpack(changed_padding, hashlib.sha256(blob).hexdigest())
        with patch.object(cloud, "MAX_ARCHIVE_BYTES", 100):
            with self.assertRaises(cloud.ReleaseFailure):
                self.unpack(blob)

    def test_paths_links_duplicates_and_missing_members(self):
        base = [(name, b"{}", tarfile.REGTYPE) for name in cloud.MEMBERS]
        bad = [base + [("../escape.pkl", b"x", tarfile.REGTYPE)],
               base + [("/absolute.pkl", b"x", tarfile.REGTYPE)],
               base + [("unexpected", b"x", tarfile.REGTYPE)],
               base + [base[0]], base[:-1],
               [("release.json", b"", tarfile.SYMTYPE)] + base[1:],
               [("release.json", b"", tarfile.LNKTYPE)] + base[1:]]
        for entries in bad:
            with self.subTest(entries=entries), self.assertRaises(cloud.ReleaseFailure):
                self.unpack(self.archive(entries))

    def test_metadata_expansion_and_timeout_bounds(self):
        with patch.object(cloud, "MAX_METADATA_BYTES", 1):
            with self.assertRaises(cloud.ReleaseFailure):
                self.unpack(self.archive())
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(cloud.ReleaseFailure):
            cloud.unpack_stream(io.BytesIO(self.archive()), Path(tmp), "a" * 64, time.monotonic() - 1)


class CacheIntegrity(unittest.TestCase):
    def setUp(self):
        import preprocess
        import artifact_store
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "verified"
        self.directory.mkdir()
        self.manifest = {"run_id": RUN_ID, "feature_names": list(preprocess.FEATURE_NAMES),
                         "doc2vec_size": 100, "feature_width": 140, "test_samples": 12,
                         "files": {name: "a" * 64 for name in artifact_store.FILES}}
        for name in cloud.ARTIFACTS:
            data = ("synthetic fixture " + name).encode()
            (self.directory / name).write_bytes(data)
            self.manifest["files"][name] = hashlib.sha256(data).hexdigest()
        manifest_bytes = json.dumps(self.manifest).encode()
        (self.directory / "manifest.json").write_bytes(manifest_bytes)
        self.release = {"format": 1, "run_id": RUN_ID,
                        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                        "feature_names": self.manifest["feature_names"],
                        "labels": {"0": "legit", "1": "spam_or_phishing"},
                        "code_sha256": {"fixture.py": "a" * 64}, "packages": {"fixture": "1"},
                        "verification": {"full_run_hashes": True, "test_samples": 12, "feature_width": 140},
                        "artifacts": {name: {"sha256": self.manifest["files"][name], "bytes": (self.directory / name).stat().st_size} for name in cloud.ARTIFACTS}}
        self.write_release()
        self.digest = cloud.archive_digest(self.directory)
        self.patches = [patch.object(cloud, "code_hashes", return_value=self.release["code_sha256"]),
                        patch.object(cloud, "package_versions", return_value=self.release["packages"]),
                        patch.object(cloud, "verify_locked_environment", return_value={"fixture": "1"})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temporary.cleanup()

    def write_release(self):
        (self.directory / "release.json").write_text(json.dumps(self.release), encoding="utf-8")

    def validate(self):
        return cloud.validate_directory(self.directory, expected_archive=self.digest)

    def test_canonical_cache_digest_binds_provenance_and_bytes(self):
        self.assertEqual(self.validate()[1], self.manifest)
        self.release["untrusted_extra"] = "changed metadata"
        self.write_release()
        with self.assertRaises(cloud.ReleaseFailure):
            self.validate()

    def test_tampered_artifact_schema_source_and_versions(self):
        mutations = [lambda r: r.update(source_manifest_sha256="b" * 64),
                     lambda r: r.update(code_sha256={"fixture.py": "b" * 64}),
                     lambda r: r.update(packages={"fixture": "2"}),
                     lambda r: r.update(feature_names=[]),
                     lambda r: r.update(labels={"0": "legit", "1": "phishing"}),
                     lambda r: r.update(verification={"full_run_hashes": False}),
                     lambda r: r["artifacts"][cloud.ARTIFACTS[0]].update(bytes=1)]
        original = copy.deepcopy(self.release)
        for mutation in mutations:
            self.release = copy.deepcopy(original)
            mutation(self.release)
            self.write_release()
            with self.assertRaises(cloud.ReleaseFailure):
                self.validate()
        self.release = original
        self.write_release()
        (self.directory / cloud.ARTIFACTS[0]).write_bytes(b"tampered")
        with self.assertRaises(cloud.ReleaseFailure):
            self.validate()

    def test_unlocked_transitive_dependency_rejects_cached_release(self):
        with patch.object(cloud, "verify_locked_environment", side_effect=ValueError("transitive package version drift")):
            with self.assertRaises(cloud.ReleaseFailure):
                self.validate()

    def test_runtime_code_pin_independently_rejects_matching_archive(self):
        self.assertEqual(cloud.archive_digest(self.directory), self.digest)
        with patch.object(cloud, "code_hashes", return_value={"fixture.py": "b" * 64}):
            with self.assertRaises(cloud.ReleaseFailure):
                self.validate()
        self.assertEqual(self.validate()[1], self.manifest)

    def test_download_once_cache_revalidation_and_cleanup_on_failure(self):
        out = io.BytesIO()
        cloud.write_archive(out, self.directory)
        blob = out.getvalue()
        config = cloud.ReleaseConfig.validate(URL, TOKEN, hashlib.sha256(blob).hexdigest())
        response = Mock(status=200, headers={"Content-Length": str(len(blob))})
        response.read.side_effect = io.BytesIO(blob).read
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(cloud, "cache_root", return_value=Path(self.temporary.name) / "cache"), patch.object(cloud, "build_opener", return_value=opener):
            directory, _, _ = cloud.provision(config)
            cloud.provision(config)
            self.assertEqual(opener.open.call_count, 1)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer " + TOKEN)
            (directory / "release.json").write_bytes(b"{}")
            with self.assertRaises(cloud.ReleaseFailure):
                cloud.provision(config)
            self.assertEqual(opener.open.call_count, 1)
        with patch.object(cloud, "cache_root", return_value=Path(self.temporary.name) / "failure"), patch.object(cloud, "build_opener", return_value=opener):
            opener.open.side_effect = OSError("private Bearer credential")
            with self.assertRaises(cloud.ReleaseFailure) as caught:
                cloud.provision(config)
            self.assertEqual(str(caught.exception), "CLOUD_DOWNLOAD")
            self.assertFalse((cloud.cache_root() / (config.digest + ".partial")).exists())


class ColdStartup(unittest.IsolatedAsyncioTestCase):
    async def make_supervisor(self):
        supervisor = Supervisor(TOKEN, startup_wait=True)
        supervisor.configuration_valid = True
        supervisor.process = Mock(is_alive=Mock(return_value=True))
        supervisor.starting = True
        return supervisor

    async def test_cold_admission_is_serial_then_uses_original_envelope(self):
        supervisor = await self.make_supervisor()
        entered, release = asyncio.Event(), asyncio.Event()
        async def startup():
            entered.set()
            await release.wait()
            supervisor.ready, supervisor.starting = True, False
        supervisor.startup = asyncio.create_task(startup())
        h = headers()
        sent = False
        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"fixture bounded body", "more_body": False}
            await asyncio.Event().wait()
        supervisor.connection = Mock()
        result = {"analysis_status": "completed", "label": "spam_or_phishing"}
        with patch.object(supervisor, "_message", AsyncMock(side_effect=[("processing", None), ("success", result)])):
            first = asyncio.create_task(supervisor.analyze(Request(scope(h), receive)))
            await entered.wait()
            await asyncio.sleep(0)
            self.assertEqual(supervisor.active_id, h["X-Request-ID"])
            unread = AsyncMock(side_effect=AssertionError("Busy body consumed"))
            other = await supervisor.analyze(Request(scope(headers()), unread))
            self.assertEqual(other.status_code, 429)
            unread.assert_not_awaited()
            release.set()
            response = await first
            self.assertEqual(json.loads(response.body), result)
            self.assertIsNone(supervisor.active_id)

    async def test_cold_deadline_stops_startup_reaps_and_preserves_identity(self):
        supervisor = await self.make_supervisor()
        supervisor.startup = asyncio.create_task(asyncio.Event().wait())
        h = headers()
        h["X-Analysis-Deadline"] = str(int(time.time() * 1000 + POLICY["deadlines"]["backendReserveMs"] + 100))
        sent = False
        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"bounded fixture", "more_body": False}
            await asyncio.Event().wait()
        old_startup = supervisor.startup
        with patch.object(supervisor, "_reap", AsyncMock()) as reap, patch.object(supervisor, "launch"):
            response = await supervisor.analyze(Request(scope(h), receive))
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.headers["X-Request-ID"], h["X-Request-ID"])
        self.assertTrue(old_startup.cancelled())
        reap.assert_awaited_once()
        self.assertIsNone(supervisor.active_id)

    async def test_archive_pin_cannot_change_on_recovery(self):
        supervisor = await self.make_supervisor()
        supervisor.manifest_digest = "a" * 64
        supervisor.metadata = {"archive_sha256": "b" * 64}
        changed = {"run": RUN_ID, "manifest_sha256": "a" * 64, "archive_sha256": "c" * 64}
        with patch.object(supervisor, "_message", AsyncMock(return_value=("ready", changed))), patch.object(supervisor, "_reap", AsyncMock()):
            await supervisor._startup()
        self.assertFalse(supervisor.ready)
        self.assertEqual(supervisor.last_failure, "RELEASE_CHANGED")
        self.assertEqual(supervisor.metadata["archive_sha256"], "b" * 64)

    async def test_cloud_inference_has_independent_backend_time_cap(self):
        supervisor = await self.make_supervisor()
        supervisor.ready, supervisor.starting = True, False
        supervisor.connection = Mock()
        sent = False
        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"bounded fixture", "more_body": False}
            await asyncio.Event().wait()
        calls = 0
        async def delayed_result():
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.sleep(0.08)
                return "processing", None
            return "success", {"analysis_status": "completed", "label": "legit"}
        with patch.dict(POLICY["deadlines"], {"backendMs": 20}), patch.object(supervisor, "_message", delayed_result), patch.object(supervisor, "recycle", AsyncMock()):
            response = await supervisor.analyze(Request(scope(headers()), receive))
        self.assertEqual(response.status_code, 504)
        self.assertEqual(json.loads(response.body)["error"]["code"], "ANALYSIS_TIMEOUT")

    async def test_actual_startup_cancellation_reaps_worker_and_reader(self):
        supervisor = await self.make_supervisor()
        child = supervisor.process
        alive = True
        child.is_alive.side_effect = lambda: alive
        def terminate():
            nonlocal alive
            alive = False
        child.terminate.side_effect = terminate
        connection = supervisor.connection = Mock()
        reader_stopped = asyncio.Event()
        async def startup_reader():
            try:
                await asyncio.Event().wait()
            finally:
                reader_stopped.set()
        h = headers()
        h["X-Analysis-Deadline"] = str(int(time.time() * 1000 + POLICY["deadlines"]["backendReserveMs"] + 100))
        sent = False
        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"bounded fixture", "more_body": False}
            await asyncio.Event().wait()
        with patch.object(supervisor, "_message", startup_reader), patch.object(supervisor, "launch"):
            startup = supervisor.startup = asyncio.create_task(supervisor._startup())
            response = await supervisor.analyze(Request(scope(h), receive))
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.headers["X-Request-ID"], h["X-Request-ID"])
        self.assertTrue(startup.done())
        self.assertTrue(reader_stopped.is_set())
        child.terminate.assert_called_once()
        child.close.assert_called_once()
        connection.close.assert_called_once()
        self.assertIsNone(supervisor.process)
        self.assertIsNone(supervisor.connection)
        self.assertIsNone(supervisor.active_id)

    async def test_download_failure_recovery_claims_admission_before_await(self):
        supervisor = await self.make_supervisor()
        supervisor.process, supervisor.starting = None, False
        supervisor.last_failure = "CLOUD_DOWNLOAD"
        entered, release = asyncio.Event(), asyncio.Event()
        async def recovery():
            entered.set()
            await release.wait()
            supervisor.ready = True
            supervisor.process = Mock(is_alive=Mock(return_value=True))
            supervisor.last_failure = None
        result = {"analysis_status": "completed", "label": "legit"}
        with patch.object(supervisor, "recycle", recovery), patch.object(supervisor, "_job", AsyncMock(return_value=result)):
            first_headers = headers()
            first = asyncio.create_task(supervisor.analyze(Request(scope(first_headers), AsyncMock())))
            try:
                await asyncio.wait_for(entered.wait(), 1)
                self.assertEqual(supervisor.active_id, first_headers["X-Request-ID"])
                unread = AsyncMock(side_effect=AssertionError("Busy body consumed"))
                other = await supervisor.analyze(Request(scope(headers()), unread))
                self.assertEqual(other.status_code, 429)
                unread.assert_not_awaited()
            finally:
                release.set()
                response = await first
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(supervisor.active_id)

    async def test_configuration_and_integrity_failures_do_not_recover(self):
        for stage in ("CLOUD_CONFIGURATION", "CLOUD_INTEGRITY"):
            supervisor = await self.make_supervisor()
            supervisor.process, supervisor.starting = None, False
            supervisor.last_failure = stage
            unread = AsyncMock(side_effect=AssertionError("Unavailable body consumed"))
            with patch.object(supervisor, "recycle", AsyncMock()) as recovery:
                response = await supervisor.analyze(Request(scope(headers()), unread))
            self.assertEqual(response.status_code, 503)
            recovery.assert_not_awaited()
            unread.assert_not_awaited()

    async def test_recovery_recomputes_expired_trusted_deadline_before_job(self):
        supervisor = await self.make_supervisor()
        supervisor.ready, supervisor.starting = True, False
        supervisor.process.is_alive.return_value = False
        async def recovery():
            supervisor.process = Mock(is_alive=Mock(return_value=True))
            supervisor.ready = True
        h = headers()
        h["X-Analysis-Deadline"] = "150000"
        with patch("web.backend.service.time.time", side_effect=[100, 147]), patch.object(supervisor, "recycle", recovery), patch.object(supervisor, "_job", AsyncMock()) as job:
            response = await supervisor.analyze(Request(scope(h), AsyncMock()))
        self.assertEqual(response.status_code, 504)
        job.assert_not_awaited()
        self.assertEqual(response.headers["X-Request-ID"], h["X-Request-ID"])

    async def test_worker_ready_log_contains_only_sanitized_runtime_evidence(self):
        supervisor = await self.make_supervisor()
        metadata = {"run": "dumped_models/classification/runs/" + RUN_ID,
                    "manifest_sha256": "a" * 64, "archive_sha256": "b" * 64,
                    "python_version": "3.12.14", "initialization_seconds": 1.5, "peak_rss_kib": 123,
                    "packages": {"numpy": "2.4.6", "extra-secret": "Bearer private-token"},
                    "private_url": "https://secret.invalid", "email": "private email"}
        with patch.object(supervisor, "_message", AsyncMock(return_value=("ready", metadata))), self.assertLogs("backend.startup", level="WARNING") as logged:
            await supervisor._startup()
        self.assertTrue(supervisor.ready)
        self.assertEqual(len(logged.output), 1)
        record = json.loads(logged.output[0].split("Model worker ready: ", 1)[1])
        self.assertEqual(record["run_id"], RUN_ID)
        self.assertEqual(record["manifest_sha256"], "a" * 64)
        self.assertEqual(record["archive_sha256"], "b" * 64)
        self.assertEqual(record["packages"]["numpy"], "2.4.6")
        self.assertEqual(record["initialization_seconds"], 1.5)
        self.assertEqual(record["peak_rss_kib"], 123)
        self.assertNotIn("private", logged.output[0])
        self.assertNotIn("secret.invalid", logged.output[0])


class ExportAtomicity(unittest.TestCase):
    def test_partial_source_never_publishes_or_changes_source(self):
        from scripts.export_release import export_release
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / RUN_ID
            source.mkdir()
            original = b'{"run_id":"' + RUN_ID.encode() + b'","feature_names":[],"files":{}}'
            (source / "manifest.json").write_bytes(original)
            output = Path(tmp) / "release.tar"
            with self.assertRaises(ValueError):
                export_release(source, output)
            self.assertFalse(output.exists())
            self.assertEqual((source / "manifest.json").read_bytes(), original)

    def test_existing_export_is_never_replaced(self):
        from scripts.export_release import export_release
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / RUN_ID
            source.mkdir()
            output = Path(tmp) / "release.tar"
            output.write_bytes(b"existing release")
            with self.assertRaises(ValueError):
                export_release(source, output)
            self.assertEqual(output.read_bytes(), b"existing release")


class DependencyLock(unittest.TestCase):
    def test_runtime_closure_checks_transitive_versions_and_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "uv.lock").write_text('[[package]]\nname="fixture-root"\nversion="1.0"\n[[package]]\nname="fixture-child"\nversion="2.0"\n', encoding="utf-8")
            installed = {"fixture-root": "1.0", "fixture-child": "2.0"}
            requirements = {"fixture-root": ["fixture-child>=2", 'not-installed; extra == "optional"'], "fixture-child": []}
            with patch.object(cloud, "version", side_effect=installed.__getitem__), patch.object(cloud, "requires", side_effect=requirements.__getitem__):
                self.assertEqual(cloud.verify_locked_environment(root, ("fixture-root",)), installed)
                installed["fixture-child"] = "3.0"
                with self.assertRaises(ValueError):
                    cloud.verify_locked_environment(root, ("fixture-root",))


class CloudWorkerEvidence(unittest.TestCase):
    def test_ready_message_has_python_timing_and_peak_rss_evidence(self):
        from web.backend import cloud_worker as module
        adapter = Mock(metadata={"packages": {"numpy": "2.4.6"}})
        connection = Mock()
        with patch.object(module, "CloudAdapter", return_value=adapter), patch.object(module, "serve") as serve:
            module.worker(connection, None)
        kind, metadata = connection.send.call_args.args[0]
        self.assertEqual(kind, "ready")
        self.assertEqual(metadata["python_version"], module.platform.python_version())
        self.assertGreaterEqual(metadata["initialization_seconds"], 0)
        self.assertTrue(metadata["peak_rss_kib"] is None or metadata["peak_rss_kib"] >= 0)
        serve.assert_called_once_with(connection, adapter)


class ExportRoundTrip(unittest.TestCase):
    """Real full-run verification/export/runtime cache checks; controlled model load."""
    def setUp(self):
        import artifact_store
        import numpy as np
        import preprocess
        from scripts import export_release as exporter
        self.exporter = exporter
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / RUN_ID
        self.source.mkdir()
        for name in artifact_store.FILES:
            (self.source / name).write_bytes(("controlled artifact " + name).encode())
        np.save(self.source / "data_X_test.npy", np.zeros((2, 140)))
        np.save(self.source / "data_y_test.npy", np.asarray([0, 1]))
        self.manifest = {"run_id": RUN_ID, "feature_names": list(preprocess.FEATURE_NAMES),
                         "doc2vec_size": 100, "feature_width": 140, "test_samples": 2,
                         "files": {name: cloud.sha256(self.source / name) for name in artifact_store.FILES}}
        self.write_manifest()
        self.settings = {"alpha": -0.0001, "min_alpha": -0.0001, "epochs": 1,
                         "stopwords": "sklearn English minus no/not/nor/never", "wordnet": "disabled", "numerical_threads": 1}
        def controlled_load(adapter, run, manifest, run_identity=None):
            adapter.metadata = self.settings.copy()
        self.patches = [patch("web.backend.adapter.Adapter._load_verified", controlled_load),
                        patch.object(exporter, "verify_locked_environment", return_value={"fixture": "1"}, create=True),
                        patch.object(exporter, "code_hashes", return_value={"fixture.py": "a" * 64}),
                        patch.object(exporter, "package_versions", return_value={"fixture": "1"}),
                        patch.object(cloud, "code_hashes", return_value={"fixture.py": "a" * 64}),
                        patch.object(cloud, "package_versions", return_value={"fixture": "1"}),
                        patch.object(cloud, "verify_locked_environment", return_value={"fixture": "1"})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temporary.cleanup()

    def write_manifest(self):
        (self.source / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_verified_export_round_trips_through_runtime_validation(self):
        output = self.root / "release.tar"
        result = self.exporter.export_release(self.source, output)
        self.exporter.verify_locked_environment.assert_called_once()
        cache = self.root / "cache"
        cache.mkdir()
        with output.open("rb") as handle:
            cloud.unpack_stream(handle, cache, result["sha256"], time.monotonic() + 10)
        release, manifest = cloud.validate_directory(cache, result["source_manifest_sha256"], result["sha256"])
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(release["inference"], self.settings)
        self.assertEqual(set(p.name for p in cache.iterdir()), set(cloud.MEMBERS))
        for name in cloud.ARTIFACTS:
            self.assertEqual((cache / name).read_bytes(), (self.source / name).read_bytes())

    def test_export_rejects_unlocked_environment_before_publication(self):
        self.exporter.verify_locked_environment.side_effect = ValueError("lock drift")
        output = self.root / "release.tar"
        with self.assertRaises(ValueError):
            self.exporter.export_release(self.source, output)
        self.assertFalse(output.exists())

    def test_export_rejects_oversized_source_and_release_metadata(self):
        output = self.root / "release.tar"
        self.manifest["padding"] = "x" * cloud.MAX_METADATA_BYTES
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.exporter.export_release(self.source, output)
        self.assertFalse(output.exists())
        self.manifest.pop("padding")
        self.write_manifest()
        with patch.object(self.exporter, "code_hashes", return_value={"oversized": "x" * cloud.MAX_METADATA_BYTES}):
            with self.assertRaises(ValueError):
                self.exporter.export_release(self.source, output)
        self.assertFalse(output.exists())
