import asyncio
import base64
import copy
import contextlib
import hashlib
import io
import multiprocessing
import os
import pickle
import json
import runpy
import time
import unittest
import uuid
import weakref
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

from fastapi.testclient import TestClient
from starlette.requests import Request
from web.backend.adapter import Adapter, ControlledUnpickler, StartupFailure, worker, multipart_email, validate_email
from web.backend.policy import POLICY, SCHEMA, POLICY_SCHEMA, ROOT, Rejection, validate_policy, load_configuration
from web.backend.service import Supervisor, create_app

TOKEN = "test-only-local-demo-token"
SAMPLES = sorted((ROOT / "web/backend/samples").glob("*.eml"))


def headers(request_id=None, **extra):
    return {"Authorization": f"Bearer {TOKEN}", "X-Request-ID": request_id or str(uuid.uuid4()),
            "X-Analysis-Deadline": str(int(time.time() * 1000 + POLICY["deadlines"]["proxyMs"])), **extra}


def encoded(raw):
    return b'--test\r\nContent-Disposition: form-data; name="file"; filename="message.eml"\r\n\r\n' + raw + b'\r\n--test--\r\n'


def request_scope(h):
    return {"type": "http", "method": "POST", "path": "/v1/analyze",
            "headers": [(k.lower().encode("ascii"), v.encode("latin-1")) for k, v in h.items()]}


def repeatability_child(connection, ordered):
    try:
        a = Adapter()
        results = []
        for name in ordered:
            raw = (ROOT / "web/backend/samples" / name).read_bytes()
            vector = a.vector(raw)
            results.append((name, hashlib.sha256(vector.tobytes()).hexdigest(), a.analyze(raw)))
        connection.send((True, results))
    except Exception as exc:
        connection.send((False, type(exc).__name__))
    finally:
        connection.close()


class WorkerUploadLifetime(unittest.TestCase):
    def test_raw_upload_released_before_next_receive_after_success_and_rejection(self):
        class TrackedUpload(bytearray):
            pass

        for rejected in (False, True):
            with self.subTest(rejected=rejected):
                case = self

                class Connection:
                    def __init__(self):
                        self.upload = None
                        self.messages = []
                        self.closed = False
                        self.checked_next_receive = False

                    def recv(self):
                        if self.upload is None:
                            body = TrackedUpload(b"transient raw upload")
                            self.upload = weakref.ref(body)
                            return body, "multipart/form-data; boundary=test"
                        self.checked_next_receive = True
                        case.assertIsNone(self.upload(), "worker retained raw upload while waiting for its next request")
                        raise EOFError

                    def send(self, message):
                        self.messages.append(message)

                    def close(self):
                        self.closed = True

                class Model:
                    metadata = {}

                    def analyze(self, parsed):
                        case.assertEqual(parsed, b"parsed email")
                        if rejected:
                            raise Rejection("INVALID_EMAIL")
                        return {"analysis_status": "completed", "label": "legit"}

                connection = Connection()
                # Plain replacements avoid mock call histories retaining the body.
                with patch("web.backend.adapter.Adapter", new=lambda *_: Model()), \
                     patch("web.backend.adapter.multipart_email", new=lambda *_: b"parsed email"):
                    worker(connection, None)
                self.assertTrue(connection.checked_next_receive)
                self.assertTrue(connection.closed)
                expected = ("error", "INVALID_EMAIL") if rejected else (
                    "success", {"analysis_status": "completed", "label": "legit"})
                self.assertEqual(connection.messages, [("ready", {}), ("processing", None), expected])


class Boundaries(unittest.TestCase):
    def reject(self, code, fn, *args):
        with self.assertRaises(Rejection) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)

    def test_input_and_multipart_matrix(self):
        raw = SAMPLES[0].read_bytes()
        self.assertEqual(multipart_email(encoded(raw), "multipart/form-data; boundary=test"), raw)
        self.reject("INVALID_REQUEST", multipart_email, encoded(raw).replace(b"message.eml", b"message.txt"), "multipart/form-data; boundary=test")
        self.reject("INVALID_REQUEST", multipart_email, encoded(raw).replace(b'name="file"', b'name="metadata"'), "multipart/form-data; boundary=test")
        duplicate = encoded(raw).replace(b"--test--\r\n", encoded(raw))
        self.reject("INVALID_REQUEST", multipart_email, duplicate, "multipart/form-data; boundary=test")
        self.reject("INVALID_REQUEST", multipart_email, b"broken", "multipart/form-data; boundary=test")
        self.reject("EMPTY_EMAIL", multipart_email, encoded(b""), "multipart/form-data; boundary=test")
        self.reject("EMPTY_EMAIL", validate_email, b"")
        self.reject("INVALID_EMAIL", validate_email, b"no email headers\n\nreadable body")
        self.reject("INVALID_EMAIL", validate_email, b"Subject: valid\nmalformed header\n\nbody")
        self.reject("INVALID_EMAIL", validate_email, b"Subject: broken\nContent-Type: multipart/mixed; boundary=missing\n\nbody")
        self.reject("INSUFFICIENT_CONTENT", validate_email, b"From: a@example.test\n\nthe and a")
        self.reject("EMAIL_TOO_LARGE", validate_email, b"x" * (POLICY["limits"]["fileBytes"] + 1))

    def test_actual_work_limits_and_shared_semantics(self):
        raw = b"Subject: hello\n\nmeeting agenda review"
        with patch.dict(POLICY["limits"], {"tokens": 2}):
            self.reject("RESOURCE_LIMIT", validate_email, raw)
        with patch.dict(POLICY["limits"], {"tokens": 1}):
            self.assertEqual(validate_email(b"Subject: the\n\nthe and meeting"), ["meeting"])
        with patch.dict(POLICY["limits"], {"decodedBytes": 2}):
            self.reject("RESOURCE_LIMIT", validate_email, raw)
        with patch.dict(POLICY["limits"], {"mimeParts": 2}):
            self.reject("RESOURCE_LIMIT", validate_email, (ROOT / "web/backend/samples/multipart.eml").read_bytes())
        with patch.dict(POLICY["limits"], {"mimeDepth": 0}):
            self.assertTrue(validate_email(raw))  # Root depth0.
            self.reject("RESOURCE_LIMIT", validate_email, (ROOT / "web/backend/samples/multipart.eml").read_bytes())
        attachment = (ROOT / "web/backend/samples/attachment.eml").read_bytes()
        # A named text attachment cannot spend the eligible body budget.
        attachment = attachment.replace(b"application/octet-stream", b"text/plain").replace(b"U2FtcGxlIGF0dGFjaG1lbnQu", base64.b64encode(b"x" * 300))
        with patch.dict(POLICY["limits"], {"decodedBytes": 100}):
            self.assertTrue(validate_email(attachment))
        with patch.dict(POLICY["limits"], {"fileBytes": 10}):
            self.reject("EMAIL_TOO_LARGE", multipart_email, encoded(raw), "multipart/form-data; boundary=test")

    def test_configuration_and_pickle_fail_closed(self):
        validate_policy()
        with patch.dict(POLICY["deadlines"], {"backendReserveMs": 1}):
            with self.assertRaises(ValueError):
                validate_policy()
        with self.assertRaises(ValueError):
            ControlledUnpickler(io.BytesIO(pickle.dumps(os.system))).load()
        with patch("artifact_store.selected_run", side_effect=ValueError("tampered hash")):
            with self.assertRaises(ValueError):
                Adapter()
        self.assertIsNone(Supervisor("invalid token").token)


class Configuration(unittest.TestCase):
    def test_missing_and_malformed_configuration_does_not_abort_import(self):
        from pathlib import Path
        read_text = Path.read_text
        for name in ("transport-policy.json", "analysis.schema.json", "transport-policy.schema.json"):
            for failure in ("missing", "malformed"):
                with self.subTest(file=name, failure=failure):
                    def read(path, *args, **kwargs):
                        if path.name == name:
                            if failure == "missing":
                                raise FileNotFoundError("private administrator path")
                            return "{malformed private configuration"
                        return read_text(path, *args, **kwargs)
                    with patch.object(Path, "read_text", read):
                        imported = runpy.run_path(str(ROOT / "web/backend/policy.py"))
                    self.assertEqual(imported[{"transport-policy.json": "POLICY", "analysis.schema.json": "SCHEMA", "transport-policy.schema.json": "POLICY_SCHEMA"}[name]], {})
                    self.assertTrue(imported["UUID"].fullmatch(str(uuid.uuid4())))

    def test_bad_configuration_keeps_live_and_correlated_unavailable(self):
        from pathlib import Path
        read_text = Path.read_text
        base = (copy.deepcopy(POLICY), copy.deepcopy(SCHEMA), copy.deepcopy(POLICY_SCHEMA))
        variants = []
        for index in range(3):
            changed = copy.deepcopy(base)
            changed[index].clear()
            variants.append(changed)
        for name in ("RequestId", "ErrorCode", "AnalysisSuccess", "AnalysisError", "AnalysisStatus"):
            changed = copy.deepcopy(base)
            changed[1]["definitions"].pop(name)
            variants.append(changed)
        for field in ("errors", "deadlines"):
            changed = copy.deepcopy(base)
            changed[0].pop(field)
            variants.append(changed)
        for field in ("MODEL_UNAVAILABLE", "INVALID_REQUEST"):
            changed = copy.deepcopy(base)
            changed[0]["errors"].pop(field)
            variants.append(changed)
        for field in ("workerStartupMs", "backendMs", "proxyMs", "terminateMs", "killReapMs"):
            changed = copy.deepcopy(base)
            changed[0]["deadlines"].pop(field)
            variants.append(changed)
        h = headers()
        for index, documents in enumerate(variants):
            with self.subTest(case=index), patch.dict(POLICY, documents[0], clear=True), patch.dict(SCHEMA, documents[1], clear=True), patch.dict(POLICY_SCHEMA, documents[2], clear=True):
                app = create_app(TOKEN)
                with TestClient(app) as client:
                    self.assertEqual(client.get("/health/live").status_code, 200)
                    self.assertEqual(client.get("/health/ready").status_code, 503)
                    response = client.post("/v1/analyze", headers=h, content=b"private email never parsed")
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json(), {"request_id": h["X-Request-ID"], "error": {"code": "MODEL_UNAVAILABLE", "message": "Analysis is unavailable. Try again later."}})
                    self.assertEqual(response.headers["X-Request-ID"], h["X-Request-ID"])
                    response = client.get(f"/v1/analysis-status?request_id={h['X-Request-ID']}", headers={"Authorization": f"Bearer {TOKEN}"})
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["error"]["code"], "MODEL_UNAVAILABLE")
                    self.assertEqual(app.state.supervisor.last_failure, "CONFIGURATION_INVALID")
                    self.assertIsNone(app.state.supervisor.process)


class AdapterVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = Adapter()
        cls.run_dir = ROOT / cls.adapter.metadata["run"]
        cls.manifest = json.loads((cls.run_dir / "manifest.json").read_text())

    def test_independent_scaled_values_composition_and_classifier_input(self):
        import numpy as np
        import preprocess
        adapter = self.adapter
        raw = (ROOT / "web/backend/samples/html.eml").read_bytes()
        raw_features = np.asarray(preprocess.extract_engineered_features(raw), dtype=float)
        scaled = (raw_features - adapter.scaler.mean_) / adapter.scaler.scale_
        observed_embeddings = []
        infer = adapter.doc.infer_vector
        def capture_embedding(*args, **kwargs):
            embedded = infer(*args, **kwargs)
            observed_embeddings.append(embedded.copy())
            return embedded
        with patch.object(adapter.doc, "infer_vector", side_effect=capture_embedding), patch.object(adapter.classifier, "predict", wraps=adapter.classifier.predict) as predict:
            result = adapter.analyze(raw)
        self.assertIn(result["label"], ("legit", "spam_or_phishing"))
        actual = predict.call_args.args[0]
        self.assertEqual(actual.shape, (1, adapter.doc.vector_size + len(preprocess.FEATURE_NAMES)))
        np.testing.assert_array_equal(actual[0, :adapter.doc.vector_size], observed_embeddings[0])
        np.testing.assert_allclose(actual[0, adapter.doc.vector_size:], scaled, rtol=1e-12, atol=1e-12)
        expected = np.concatenate((observed_embeddings[0], scaled)).reshape(1, -1)
        np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)

    def test_numeric_binary_mapping_uses_computed_vector(self):
        import numpy as np
        adapter = self.adapter
        raw = SAMPLES[0].read_bytes()
        expected = adapter.vector(raw)
        for value, label in ((np.int64(0), "legit"), (np.int64(1), "spam_or_phishing")):
            with patch.object(adapter.classifier, "predict", return_value=np.asarray([value])) as predict:
                self.assertEqual(adapter.analyze(raw), {"analysis_status": "completed", "label": label})
                np.testing.assert_array_equal(predict.call_args.args[0], expected)
        with patch.object(adapter.classifier, "predict", return_value=np.asarray([0.5])):
            with self.assertRaises(ValueError):
                adapter.analyze(raw)

    def assert_worker_unready(self, stage):
        connection = Mock()
        worker(connection, str(self.run_dir.relative_to(ROOT)), self.adapter.release)
        connection.send.assert_called_once_with(("unavailable", stage))
        supervisor = Supervisor(TOKEN)
        with patch.object(supervisor, "_message", AsyncMock(return_value=("unavailable", stage))):
            asyncio.run(supervisor._startup())
        self.assertFalse(supervisor.ready)
        self.assertEqual(supervisor.last_failure, stage)

    def test_incompatible_loaded_classes_and_dimensions_reject_readiness(self):
        import numpy as np
        adapter = self.adapter
        loaded = [adapter.doc, adapter.scaler, adapter.classifier]
        modifications = [
            (patch.object(adapter.doc, "vector_size", 99), loaded),
            (patch.object(adapter.scaler, "n_features_in_", 39), loaded),
            (patch.object(type(adapter.classifier), "n_features_in_", new_callable=PropertyMock, return_value=139), loaded),
            (patch.object(type(adapter.classifier), "classes_", new_callable=PropertyMock, return_value=np.asarray([1, 2])), loaded),
            (patch.object(adapter.classifier, "get_booster", return_value=Mock(num_features=Mock(return_value=139))), loaded),
            (contextlib.nullcontext(), [object(), adapter.scaler, adapter.classifier]),
        ]
        for index, (modification, objects) in enumerate(modifications):
            with self.subTest(case=index), modification, patch("artifact_store.verify_run", return_value=copy.deepcopy(self.manifest)), patch.object(ControlledUnpickler, "load", side_effect=objects):
                self.assert_worker_unready("MODEL_COMPATIBILITY")

    def test_changed_load_bytes_and_self_consistent_manifest_reject_readiness(self):
        from pathlib import Path
        read_bytes = Path.read_bytes
        def changed_bytes(path):
            return b"changed bytes" if path.name == "feature_scaler.pkl" else read_bytes(path)
        with patch("artifact_store.verify_run", return_value=copy.deepcopy(self.manifest)), patch.object(Path, "read_bytes", changed_bytes):
            self.assert_worker_unready("ARTIFACT_BYTES")
        manifest = copy.deepcopy(self.manifest)
        manifest["source_counts"]["review_test"] = "self-consistent changed release"
        blob = json.dumps(manifest).encode()
        def changed_manifest(path):
            return blob if path.name == "manifest.json" else read_bytes(path)
        with patch("artifact_store.verify_run", return_value=manifest), patch.object(Path, "read_bytes", changed_manifest):
            self.assert_worker_unready("RELEASE_CHANGED")
        self.assertNotEqual(hashlib.sha256(blob).hexdigest(), self.adapter.release)

    def test_startup_attribution_never_retains_raw_exception(self):
        with patch("artifact_store.verify_run", side_effect=ValueError("private email and Bearer secret")):
            self.assert_worker_unready("RUN_VERIFICATION")
        connection = Mock()
        with patch("web.backend.adapter.Adapter", side_effect=RuntimeError("private email and Bearer secret")):
            worker(connection, None)
        connection.send.assert_called_once_with(("unavailable", "DEPENDENCY_LOAD"))
        supervisor = Supervisor(TOKEN)
        with self.assertLogs("backend.startup", level="WARNING") as logged:
            supervisor.failure("private email and Bearer secret")
        self.assertEqual(supervisor.last_failure, "WORKER_STARTUP_FAILED")
        self.assertNotIn("private", str(logged.output))
        self.assertNotIn("Bearer", str(logged.output))


class RealModelAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(TOKEN)
        cls.client = TestClient(cls.app).__enter__()
        cls.supervisor = cls.app.state.supervisor
        cls.wait_ready()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    @classmethod
    def wait_ready(cls):
        end = time.monotonic() + POLICY["deadlines"]["workerStartupMs"] / 1000
        while time.monotonic() < end:
            if cls.client.get("/health/ready").status_code == 200:
                return
            time.sleep(0.05)
        raise AssertionError("Actual worker did not become ready")

    def test_real_five_mime_cases_exact_envelope_and_pinned_metadata(self):
        from jsonschema import Draft7Validator
        from web.backend.policy import SCHEMA
        validator = Draft7Validator(SCHEMA)
        for sample in SAMPLES:
            with self.subTest(sample=sample.name):
                h = headers()
                response = self.client.post("/v1/analyze", headers=h, files={"file": (sample.name, sample.read_bytes(), "message/rfc822")})
                self.assertEqual(response.status_code, 200)
                validator.validate(response.json())
                self.assertEqual(set(response.json()), {"analysis_status", "label"})
                self.assertIn(response.json()["label"], ("legit", "spam_or_phishing"))
                self.assertEqual(response.headers["X-Request-ID"], h["X-Request-ID"])
        self.assertEqual(self.supervisor.metadata["feature_width"], 140)
        self.assertEqual(self.supervisor.metadata["hash_seed"], "0")
        self.assertEqual(self.supervisor.metadata["epochs"], 1)
        self.assertEqual(self.client.get("/health/live").json(), {"status": "alive"})

    def test_auth_identity_deadline_and_status(self):
        for override, code in [({"Authorization": "Bearer bad"}, "INVALID_REQUEST"),
                               ({"X-Request-ID": "bad"}, "INVALID_REQUEST"),
                               ({"X-Analysis-Deadline": "bad"}, "INVALID_REQUEST"),
                               ({"X-Analysis-Deadline": "1"}, "ANALYSIS_TIMEOUT"),
                               ({"X-Analysis-Deadline": str(int(time.time() * 1000 + 9999999))}, "INVALID_REQUEST")]:
            response = self.client.post("/v1/analyze", headers=headers(**override), content=b"no body parsing needed")
            self.assertEqual(response.json()["error"]["code"], code)
            if "Authorization" in override:
                self.assertEqual(response.status_code, 401)
            self.assertNotIn("label", response.json())
        request_id = str(uuid.uuid4())
        response = self.client.get(f"/v1/analysis-status?request_id={request_id}", headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(response.json(), {"request_id": request_id, "phase": "unknown"})
        self.assertEqual(response.headers["X-Request-ID"], request_id)
        response = self.client.get(f"/v1/analysis-status?request_id={request_id}&extra=x", headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(response.status_code, 400)

    def test_busy_admission_has_no_body_consumption(self):
        async def scenario():
            supervisor = self.supervisor
            first_id = str(uuid.uuid4())
            admitted, release = asyncio.Event(), asyncio.Event()
            body_sent = False
            async def first_receive():
                nonlocal body_sent
                if not body_sent:
                    admitted.set()
                    await release.wait()
                    body_sent = True
                    return {"type": "http.request", "body": encoded(SAMPLES[0].read_bytes()), "more_body": False}
                await asyncio.Event().wait()
            pid = supervisor.process.pid
            worker_pids = {p.pid for p in multiprocessing.active_children()}
            first = asyncio.create_task(supervisor.analyze(Request(request_scope(headers(first_id, **{"Content-Type": "multipart/form-data; boundary=test"})), first_receive)))
            await admitted.wait()
            consumed = 0
            async def receive():
                nonlocal consumed
                consumed += 1
                raise AssertionError("Rejected request consumed body")
            try:
                response = await supervisor.analyze(Request(request_scope(headers()), receive))
                self.assertEqual(response.status_code, 429)
                self.assertEqual(consumed, 0)
                self.assertEqual(supervisor.active_id, first_id)
                self.assertEqual(supervisor.process.pid, pid)
                self.assertEqual({p.pid for p in multiprocessing.active_children()}, worker_pids)
            finally:
                release.set()
                self.assertEqual((await first).status_code, 200)
            self.assertIsNone(supervisor.active_id)
        self.client.portal.call(scenario)

    def test_latin1_superscript_deadline_is_canonical_invalid_request(self):
        async def scenario():
            receive = AsyncMock(side_effect=AssertionError("Body must stay unread"))
            h = headers(**{"X-Analysis-Deadline": "²"})
            response = await self.supervisor.analyze(Request(request_scope(h), receive))
            self.assertEqual(response.status_code, 400)
            self.assertEqual(json.loads(response.body)["error"]["code"], "INVALID_REQUEST")
            self.assertEqual(response.headers["X-Request-ID"], h["X-Request-ID"])
            receive.assert_not_awaited()
        self.client.portal.call(scenario)

    def test_stalled_upload_deadline_reaps_and_recovers_actual_worker(self):
        old_pid = self.supervisor.process.pid
        async def scenario():
            receiving = asyncio.Event()
            async def receive():
                receiving.set()
                await asyncio.Event().wait()
            h = headers(**{"Content-Type": "multipart/form-data; boundary=test"})
            with patch.dict(POLICY["deadlines"], {"backendMs": 100}):
                task = asyncio.create_task(self.supervisor.analyze(Request(request_scope(h), receive)))
                await receiving.wait()
                self.assertEqual(self.supervisor.phase, "receiving")
                response = await task
            self.assertEqual(response.status_code, 504)
            self.assertEqual(json.loads(response.body)["error"]["code"], "ANALYSIS_TIMEOUT")
            self.assertIsNone(self.supervisor.active_id)
            self.assertEqual(self.supervisor.phase, "unknown")
        self.client.portal.call(scenario)
        self.wait_ready()
        self.assertNotEqual(self.supervisor.process.pid, old_pid)
        self.assertFalse(any(p.pid == old_pid for p in multiprocessing.active_children()))
        response = self.client.post("/v1/analyze", headers=headers(), files={"file": ("recovered.eml", SAMPLES[0].read_bytes())})
        self.assertEqual(response.status_code, 200)

    def test_observed_receiving_processing_startup_and_erasure(self):
        # Hold real admission/receive, then the actual child's result after its
        # processing acknowledgement; neither stage is assigned by the test.
        async def scenario():
            import httpx
            supervisor = self.supervisor
            first_id, other_id = str(uuid.uuid4()), str(uuid.uuid4())
            receiving, release_receive, processing, release_result = (asyncio.Event() for _ in range(4))
            sent = False
            async def receive():
                nonlocal sent
                if not sent:
                    receiving.set()
                    await release_receive.wait()
                    sent = True
                    return {"type": "http.request", "body": encoded(SAMPLES[0].read_bytes()), "more_body": False}
                await asyncio.Event().wait()
            original = supervisor._message
            calls = 0
            async def observed_message():
                nonlocal calls
                calls += 1
                if calls == 2:
                    processing.set()
                    await release_result.wait()
                return await original()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://local.test") as client:
                async def status(request_id, phase):
                    response = await client.get(f"/v1/analysis-status?request_id={request_id}", headers={"Authorization": f"Bearer {TOKEN}"})
                    self.assertEqual(response.json(), {"request_id": request_id, "phase": phase})
                    self.assertEqual(response.headers["X-Request-ID"], request_id)
                with patch.object(supervisor, "_message", observed_message):
                    attempt = asyncio.create_task(supervisor.analyze(Request(request_scope(headers(first_id, **{"Content-Type": "multipart/form-data; boundary=test"})), receive)))
                    try:
                        await receiving.wait()
                        await status(first_id, "receiving")
                        await status(other_id, "unknown")
                        release_receive.set()
                        await processing.wait()
                        await status(first_id, "processing")
                        await status(other_id, "unknown")
                    finally:
                        release_receive.set()
                        release_result.set()
                        self.assertEqual((await attempt).status_code, 200)
                await status(first_id, "unknown")
                # Recovery performs real startup; hold observation until both IDs
                # have checked the service-wide starting phase.
                release_start = asyncio.Event()
                async def held_startup():
                    await release_start.wait()
                    return await original()
                with patch.object(supervisor, "_message", held_startup):
                    await supervisor.recycle()
                    await status(first_id, "starting")
                    await status(other_id, "starting")
                    release_start.set()
                    await supervisor.startup
                self.assertTrue(supervisor.ready)
                await status(first_id, "unknown")
                self.assertIsNone(supervisor.active_id)
        self.client.portal.call(scenario)

    def test_actual_body_overrun_and_error_safety(self):
        response = self.client.post("/v1/analyze", headers=headers(**{"Content-Type": "multipart/form-data; boundary=test", "Content-Length": "1"}), content=b"x" * (POLICY["limits"]["multipartBytes"] + 1))
        self.assertEqual(response.status_code, 413)
        response = self.client.post("/v1/analyze", headers=headers(), files={"file": ("invalid.eml", b"secret invalid email", "message/rfc822")})
        self.assertEqual(response.json()["error"]["code"], "INVALID_EMAIL")
        self.assertNotIn("secret", response.text)

    def test_timeout_reaps_then_recovers_one_actual_worker(self):
        old_pid = self.supervisor.process.pid
        original_message = self.supervisor._message
        first = True
        async def stalled_message():
            nonlocal first
            if first:
                first = False
                await asyncio.sleep(1)
            return await original_message()
        # Inject a stalled IPC observation; the child itself is the actual model.
        with patch.dict(POLICY["deadlines"], {"backendMs": 100}), patch.object(self.supervisor, "_message", stalled_message):
            response = self.client.post("/v1/analyze", headers=headers(), files={"file": ("valid.eml", SAMPLES[0].read_bytes())})
            self.assertEqual(response.status_code, 504)
        self.wait_ready()
        self.assertNotEqual(self.supervisor.process.pid, old_pid)
        self.assertFalse(any(p.pid == old_pid for p in multiprocessing.active_children()))
        self.assertIsNone(self.supervisor.active_id)
        response = self.client.post("/v1/analyze", headers=headers(), files={"file": ("after.eml", SAMPLES[0].read_bytes())})
        self.assertEqual(response.status_code, 200)

    def test_idle_child_death_recovers_before_following_attempt(self):
        old_pid = self.supervisor.process.pid
        self.supervisor.process.kill()
        self.supervisor.process.join(2)
        response = self.client.post("/v1/analyze", headers=headers(), files={"file": ("first.eml", SAMPLES[0].read_bytes())})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("label", response.json())
        self.wait_ready()
        self.assertNotEqual(self.supervisor.process.pid, old_pid)
        response = self.client.post("/v1/analyze", headers=headers(), files={"file": ("recovered.eml", SAMPLES[0].read_bytes())})
        self.assertEqual(response.status_code, 200)

    def test_disconnect_terminates_actual_worker(self):
        old_pid = self.supervisor.process.pid
        async def scenario():
            events = iter([{"type": "http.request", "body": encoded(SAMPLES[0].read_bytes()), "more_body": False}, {"type": "http.disconnect"}])
            async def receive():
                return next(events)
            h = headers(**{"Content-Type": "multipart/form-data; boundary=test"})
            scope = {"type": "http", "method": "POST", "path": "/v1/analyze", "headers": [(k.lower().encode(), v.encode()) for k, v in h.items()]}
            response = await self.supervisor.analyze(Request(scope, receive))
            self.assertEqual(response.status_code, 504)
        self.client.portal.call(scenario)
        self.wait_ready()
        self.assertNotEqual(self.supervisor.process.pid, old_pid)
        self.assertFalse(any(p.pid == old_pid for p in multiprocessing.active_children()))


class Lifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_rejects_changed_manifest_and_preserves_startup_pin(self):
        supervisor = Supervisor(TOKEN)
        supervisor.pinned = "dumped_models/classification/runs/pinned"
        supervisor.manifest_digest = "a" * 64
        old_metadata = {"run": supervisor.pinned, "manifest_sha256": supervisor.manifest_digest}
        supervisor.metadata = old_metadata
        changed = {"run": supervisor.pinned, "manifest_sha256": "b" * 64}
        with patch.object(supervisor, "_message", AsyncMock(return_value=("ready", changed))):
            await supervisor._startup()
        self.assertFalse(supervisor.ready)
        self.assertEqual(supervisor.manifest_digest, "a" * 64)
        self.assertIs(supervisor.metadata, old_metadata)
        self.assertEqual(supervisor.last_failure, "RELEASE_CHANGED")

    async def test_missing_pinned_run_and_invalid_policy_keep_live_unready(self):
        supervisor = Supervisor(TOKEN)
        supervisor.pinned = "missing-run"
        supervisor.launch()
        await supervisor.startup
        self.assertFalse(supervisor.ready)
        self.assertIsNone(supervisor.process)
        await supervisor.close()
        with patch.dict(POLICY["deadlines"], {"backendReserveMs": 1}):
            supervisor = Supervisor(TOKEN)
            supervisor.launch()
            self.assertIsNone(supervisor.process)

    async def test_unreapable_child_exits_without_replacement(self):
        supervisor = Supervisor(TOKEN)
        process = Mock()
        process.is_alive.return_value = True
        supervisor.process = process
        with patch("web.backend.service.os._exit") as exit_process:
            await supervisor.recycle()
        exit_process.assert_called_once_with(1)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertTrue(supervisor.closed)
        self.assertIs(supervisor.process, process)


class Repeatability(unittest.TestCase):
    def test_vectors_and_labels_repeat_reorder_and_restart(self):
        os.environ["PYTHONHASHSEED"] = "0"
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[name] = "1"
        names = [p.name for p in SAMPLES]
        results = []
        for order in (names + names, list(reversed(names))):
            ctx = multiprocessing.get_context("spawn")
            parent, child = ctx.Pipe()
            process = ctx.Process(target=repeatability_child, args=(child, order))
            process.start()
            child.close()
            try:
                self.assertTrue(parent.poll(120), "Repeatability child startup timeout")
                ok, output = parent.recv()
                self.assertTrue(ok, output)
                results.append(output)
            finally:
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                parent.close()
                process.close()
        seen = {}
        for name, vector_hash, label in results[0] + results[1]:
            current = (vector_hash, label)
            self.assertEqual(seen.setdefault(name, current), current)
        self.assertEqual(len(seen), 5)
