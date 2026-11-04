import asyncio
import base64
import copy
import contextlib
import hashlib
import importlib
import importlib.util
import io
import multiprocessing
import os
import pickle
import json
import runpy
import shutil
import sys
import tempfile
import time
import unittest
import uuid
import weakref
from pathlib import Path
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

from fastapi.testclient import TestClient
from starlette.requests import Request

TESTS = Path(__file__).resolve().parent
BACKEND_DIR = TESTS.parent
WEB_ROOT = BACKEND_DIR.parent


def backend_package():
    """Tên import của backend: "backend" khi chạy từ web/, "web.backend" khi chạy từ thư mục gốc."""
    for name in ("backend", "web.backend"):
        try:
            spec = importlib.util.find_spec(name)
        except ImportError:
            continue
        if spec and spec.origin and Path(spec.origin).resolve().parent == BACKEND_DIR:
            return name
    # Không import được theo tên nào (ví dụ chạy script trong tests/): thêm web/ vào sys.path.
    sys.path.insert(0, str(WEB_ROOT))
    return "backend"


PACKAGE = backend_package()
backend_module = importlib.import_module(PACKAGE)
adapter_module = importlib.import_module(f"{PACKAGE}.adapter")
policy_module = importlib.import_module(f"{PACKAGE}.policy")
service_module = importlib.import_module(f"{PACKAGE}.service")
from_adapter = ("MANIFEST", "MODEL_DIR", "Adapter", "ControlledUnpickler", "StartupFailure", "worker",
                "multipart_email", "validate_email")
MANIFEST, MODEL_DIR, Adapter, ControlledUnpickler, StartupFailure, worker, multipart_email, validate_email = (
    getattr(adapter_module, name) for name in from_adapter)
POLICY, SCHEMA, POLICY_SCHEMA, RUN_PATH_ENV, MODEL_NAME_ENV, Rejection, validate_policy, load_configuration = (
    getattr(policy_module, name) for name in
    ("POLICY", "SCHEMA", "POLICY_SCHEMA", "RUN_PATH_ENV", "MODEL_NAME_ENV", "Rejection", "validate_policy",
     "load_configuration"))
Supervisor, create_app = service_module.Supervisor, service_module.create_app

TOKEN = "test-only-local-demo-token"
SAMPLES = sorted((BACKEND_DIR / "samples").glob("*.eml"))
# Run schema 2 nhỏ dựng như baseline_v6 (134 feature, XGBoost + MLP, chọn MLP) trên email tổng
# hợp, commit sẵn trong tests/fixture_run/ (tạo lại bằng build_fixture.py). Test chỉ dùng bản sao.
# Test cần XGBoost (fixture chọn MLP) tự đặt IAP_WEB_MODEL=XGBoost, không dựa vào policy.MODEL_NAME;
# chỉ PinnedRelease kiểm giá trị pin thật của policy.
SERVE_XGBOOST = {MODEL_NAME_ENV: "XGBoost"}
FIXTURE_RUN = TESTS / "fixture_run"
FIXTURE_COUNT = 120
FIXTURE = {}


def synthetic_email(index, positive):
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = f"Notice {index}"
    msg["From"] = "Account <support@gmail.com>" if positive else "Colleague <colleague@example.org>"
    msg["To"] = "recipient@example.org"
    msg["Reply-To"] = "other@example.invalid" if positive else "colleague@example.org"
    msg.set_content(f"Message identifier {index}: please read https://example.invalid/{index}")
    msg.add_alternative(f'<html><body>Message identifier {index} <a href="https://example.invalid/{index}">Open</a>'
                        + ("<script>const marker=1;</script>" if index % 3 == 0 else "") + "</body></html>",
                        subtype="html")
    return msg.as_bytes()


def fixture_rows(count=FIXTURE_COUNT):
    """Các dòng dữ liệu đã dựng run fixture; RecordId là SHA-256 của Location."""
    rows = []
    for index in range(count):
        positive = bool(index % 2)
        location = f"synthetic:message:{index}"
        rows.append({"Text": synthetic_email(index, positive), "Class": int(positive), "Source": "synthetic",
                     "Location": location, "LabelKind": "phishing" if positive else "legitimate",
                     "OriginalLabel": str(int(positive)), "LabelBasis": "synthetic test fixture",
                     "RecordId": hashlib.sha256(location.encode("utf-8")).hexdigest()})
    return rows


def setUpModule():
    FIXTURE["temp"] = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    FIXTURE["run"] = Path(FIXTURE["temp"].name) / "run"
    shutil.copytree(FIXTURE_RUN, FIXTURE["run"])
    FIXTURE["raws"] = {row["RecordId"]: row["Text"] for row in fixture_rows()}
    FIXTURE["previous_env"] = os.environ.get(RUN_PATH_ENV)
    FIXTURE["previous_model"] = os.environ.pop(MODEL_NAME_ENV, None)
    os.environ[RUN_PATH_ENV] = str(FIXTURE["run"])


def tearDownModule():
    if FIXTURE.get("previous_env") is None:
        os.environ.pop(RUN_PATH_ENV, None)
    else:
        os.environ[RUN_PATH_ENV] = FIXTURE["previous_env"]
    if FIXTURE.get("previous_model") is not None:
        os.environ[MODEL_NAME_ENV] = FIXTURE["previous_model"]
    FIXTURE["temp"].cleanup()


def variant_run(test, edit=None, files=None):
    """Bản sao run fixture với manifest/artifact bị sửa cho từng ca lỗi."""
    temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    test.addCleanup(temp.cleanup)
    run = Path(temp.name) / "run"
    shutil.copytree(FIXTURE["run"], run)
    if edit:
        manifest = json.loads((run / MANIFEST).read_text(encoding="utf-8"))
        edit(manifest)
        (run / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    for relative, content in (files or {}).items():
        (run / relative).write_bytes(content)
    return run


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
            raw = (BACKEND_DIR / "samples" / name).read_bytes()
            vector = a.vector(raw)
            results.append((name, hashlib.sha256(vector.tobytes()).hexdigest(), a.analyze(raw)))
        connection.send((True, results))
    except Exception as exc:
        connection.send((False, type(exc).__name__))
    finally:
        connection.close()


def served_vectors_child(connection, raws):
    try:
        a = Adapter()
        connection.send((True, [(a.vector(raw)[0], a.analyze(raw)["label"]) for raw in raws]))
    except Exception as exc:
        connection.send((False, type(exc).__name__))
    finally:
        connection.close()


def in_hash_seed_child(target, *args):
    """Chạy target trong tiến trình spawn với PYTHONHASHSEED=0 và một luồng, như worker của service."""
    environment = {"PYTHONHASHSEED": "0", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe()
    with patch.dict(os.environ, environment):
        process = ctx.Process(target=target, args=(child, *args))
        process.start()
    child.close()
    try:
        if not parent.poll(120):
            raise AssertionError("Hash-seed child timeout")
        ok, output = parent.recv()
        if not ok:
            raise AssertionError(output)
        return output
    finally:
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
        parent.close()
        process.close()


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
                with patch(f"{PACKAGE}.adapter.Adapter", new=lambda *_: Model()), \
                     patch(f"{PACKAGE}.adapter.multipart_email", new=lambda *_: b"parsed email"):
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
            self.reject("RESOURCE_LIMIT", validate_email, (BACKEND_DIR / "samples/multipart.eml").read_bytes())
        with patch.dict(POLICY["limits"], {"mimeDepth": 0}):
            self.assertTrue(validate_email(raw))  # Root depth0.
            self.reject("RESOURCE_LIMIT", validate_email, (BACKEND_DIR / "samples/multipart.eml").read_bytes())
        attachment = (BACKEND_DIR / "samples/attachment.eml").read_bytes()
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
        class EstimatorFunctionCall:
            def __reduce__(self):
                from sklearn.utils.validation import check_scalar
                return (check_scalar, (5, "x", int))
        with self.assertRaises(ValueError):
            ControlledUnpickler(io.BytesIO(pickle.dumps(EstimatorFunctionCall()))).load()
        with patch(f"{PACKAGE}.adapter.file_sha256", side_effect=ValueError("tampered hash")):
            with self.assertRaises(ValueError):
                Adapter()
        self.assertIsNone(Supervisor("invalid token").token)


class Configuration(unittest.TestCase):
    def test_missing_feature_dependency_is_unready_at_dependency_load(self):
        # Thiếu magika/oletools/tldextract thì preprocess v6 âm thầm ra feature khác (olevba bị bỏ
        # qua), nên worker phải từ chối ngay lúc khởi động, không làm sập supervisor.
        for name in ("magika", "oletools.olevba", "tldextract"):
            with self.subTest(module=name), patch.dict(sys.modules, {name: None}):
                with self.assertRaises(StartupFailure) as caught:
                    Adapter()
                self.assertEqual(caught.exception.stage, "DEPENDENCY_LOAD")
                connection = Mock()
                worker(connection, None)
                connection.send.assert_called_once_with(("unavailable", "DEPENDENCY_LOAD"))

    def test_python_without_strict_address_parsing_is_unready_at_dependency_load(self):
        # Python thiếu getaddresses strict (vd. 3.11.2) cho feature header khác lúc train v6.
        with patch(f"{PACKAGE}.adapter.strict_address_parsing", return_value=False):
            with self.assertRaises(StartupFailure) as caught:
                Adapter()
            self.assertEqual(caught.exception.stage, "DEPENDENCY_LOAD")
            connection = Mock()
            worker(connection, None)
            connection.send.assert_called_once_with(("unavailable", "DEPENDENCY_LOAD"))
        self.assertTrue(adapter_module.strict_address_parsing())

    def test_missing_and_malformed_configuration_does_not_abort_import(self):
        from pathlib import Path
        read_text = Path.read_text
        documents = {"transport-policy.json": "POLICY", "analysis.schema.json": "SCHEMA",
                     "transport-policy.schema.json": "POLICY_SCHEMA", "explanation-factors.json": "FACTORS"}
        for name in documents:
            for failure in ("missing", "malformed"):
                with self.subTest(file=name, failure=failure):
                    def read(path, *args, **kwargs):
                        if path.name == name:
                            if failure == "missing":
                                raise FileNotFoundError("private administrator path")
                            return "{malformed private configuration"
                        return read_text(path, *args, **kwargs)
                    with patch.object(Path, "read_text", read):
                        imported = runpy.run_path(str(BACKEND_DIR / "policy.py"))
                    self.assertEqual(imported[documents[name]], {})
                    self.assertTrue(imported["UUID"].fullmatch(str(uuid.uuid4())))
                    with self.assertRaises(ValueError):
                        imported["validate_policy"]()

    def test_factor_catalogue_must_be_well_formed(self):
        FACTORS, validate_factors = policy_module.FACTORS, policy_module.validate_factors
        validate_factors(FACTORS)
        broken = [{"version": 2, "factors": FACTORS["factors"]}, {"version": 1, "factors": {}},
                  {"version": 1, "factors": {"Bad-Id": {"label": "x"}}}, {"version": 1, "factors": {"ok": {"label": ""}}},
                  {"version": 1, "factors": {"ok": {"label": "x", "extra": "y"}}}, {**FACTORS, "extra": 1}, [],
                  {"version": True, "factors": FACTORS["factors"]}, {"version": 1, "factors": {"ok": {"label": " x"}}},
                  {"version": 1, "factors": {"ok": {"label": "x "}}}, {"version": 1, "factors": {"ok": {"label": "x" * 81}}}]
        for document in broken:
            with self.subTest(document=str(document)[:60]), self.assertRaises(ValueError):
                validate_factors(document)

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
        cls.environment = patch.dict(os.environ, SERVE_XGBOOST)
        cls.environment.start()
        cls.adapter = Adapter()
        cls.run_dir = FIXTURE["run"]
        cls.manifest = json.loads((cls.run_dir / MANIFEST).read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()

    def test_relative_run_path_resolves_from_web_root_in_any_working_directory(self):
        try:
            relative = os.path.relpath(FIXTURE["run"], WEB_ROOT)
        except ValueError:
            self.skipTest("Run fixture nằm khác ổ đĩa với web/")
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as foreign:
            os.chdir(foreign)
            with patch.dict(os.environ, {RUN_PATH_ENV: relative}):
                loaded = Adapter()
            os.chdir(previous)
        self.assertEqual(loaded.metadata["manifest_sha256"], self.adapter.metadata["manifest_sha256"])

    def test_backend_never_imports_root_modules(self):
        repository = WEB_ROOT.parent
        if not (repository / "train.py").is_file():
            self.skipTest("Bản chép web/ riêng: không có module gốc để import nhầm")
        self.assertTrue(self.adapter.metadata["manifest_sha256"])
        environments = {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()}
        leaked = []
        for name, module in list(sys.modules.items()):
            location = getattr(module, "__file__", None)
            if not location:
                continue
            path = Path(location).resolve()
            if (repository in path.parents and WEB_ROOT not in path.parents and
                    not any(environment == path or environment in path.parents for environment in environments)):
                leaked.append(name)
        self.assertEqual(leaked, [])

    def test_serving_vectors_and_labels_match_training_test_arrays(self):
        import numpy as np
        import pandas as pd
        adapter = self.adapter
        X = np.load(self.run_dir / "data_X_test.npy")
        metadata = pd.read_csv(self.run_dir / "test_metadata.csv")
        config = self.manifest["models"]["XGBoost"]
        self.assertEqual(adapter.metadata["selected_model"], self.manifest["selected_model"])
        self.assertEqual(adapter.metadata["served_model"], "XGBoost")
        self.assertEqual(adapter.threshold, config["threshold"])
        expected = adapter.classifier.predict_proba(X)[:, 1] >= config["threshold"]
        # Vector Doc2Vec phụ thuộc hash seed; fixture train với PYTHONHASHSEED=0 như tiến trình
        # con của service, nên so trong tiến trình con spawn có cùng hash seed.
        served = in_hash_seed_child(served_vectors_child, [FIXTURE["raws"][record] for record in metadata.RecordId])
        labels = []
        for row, (vector, label) in enumerate(served):
            np.testing.assert_allclose(vector, X[row], rtol=0, atol=1e-6)
            labels.append(label)
        self.assertEqual(labels, ["phishing" if value else "legit" for value in expected])
        self.assertEqual(set(labels), {"legit", "phishing"})

    def test_web_uses_frozen_pipeline_not_root_copy(self):
        import pipeline_cache
        import preprocess
        FROZEN_PIPELINE = backend_module.FROZEN_PIPELINE
        # Web phải nạp đúng hai module đóng băng cùng run, kể cả khi root đã đổi code.
        for module in (preprocess, pipeline_cache):
            self.assertEqual(Path(module.__file__).resolve().parent, FROZEN_PIPELINE)
        hashed = self.adapter.metadata["code_sha256"]
        self.assertIn("backend/frozen_pipeline/preprocess.py", hashed)
        self.assertNotIn("preprocess.py", hashed)

    def test_independent_scaled_values_composition_and_classifier_input(self):
        import numpy as np
        import preprocess
        adapter = self.adapter
        raw = (BACKEND_DIR / "samples/html.eml").read_bytes()
        # Đường trích độc lập của bản đóng băng (extract_baseline_features), không qua _process.
        raw_features = np.asarray(preprocess.extract_baseline_features(raw), dtype=np.float32)
        scaled = (raw_features - adapter.scaler.mean_) / adapter.scaler.scale_
        observed_embeddings = []
        infer = adapter.doc.infer_vector
        def capture_embedding(*args, **kwargs):
            embedded = infer(*args, **kwargs)
            observed_embeddings.append(embedded.copy())
            return embedded
        with patch.object(adapter.doc, "infer_vector", side_effect=capture_embedding), patch.object(adapter.classifier, "predict_proba", wraps=adapter.classifier.predict_proba) as predict:
            result = adapter.analyze(raw)
        self.assertIn(result["label"], ("legit", "phishing"))
        actual = predict.call_args.args[0]
        self.assertEqual(actual.shape, (1, adapter.doc.vector_size + len(preprocess.BASELINE_FEATURE_NAMES)))
        np.testing.assert_array_equal(actual[0, :adapter.doc.vector_size], observed_embeddings[0])
        np.testing.assert_allclose(actual[0, adapter.doc.vector_size:], scaled, rtol=1e-5, atol=1e-5)

    def test_validation_threshold_and_target_label_mapping(self):
        raw = SAMPLES[0].read_bytes()
        adapter = self.adapter
        for score, label in ((0.0, "legit"), (adapter.threshold, "phishing"), (1.0, "phishing")):
            with patch.object(adapter, "score", return_value=score):
                result = adapter.analyze(raw)
                result.pop("explanation", None)
                self.assertEqual(result, {"analysis_status": "completed", "label": label})
        def broad(manifest):
            manifest["target_mode"] = "broad"
        with patch.dict(os.environ, {RUN_PATH_ENV: str(variant_run(self, broad))}):
            mixed = Adapter()
        with patch.object(mixed, "score", return_value=1.0):
            self.assertEqual(mixed.analyze(raw)["label"], "spam_or_phishing")
        with patch.object(adapter.classifier, "predict_proba", return_value=[[0.5, float("nan")]]):
            with self.assertRaises(ValueError):
                adapter.analyze(raw)

    def test_every_fixture_classifier_loads_through_controlled_unpickler(self):
        # Fixture giữ hai loại model của release v6: MLP (được chọn) và XGBoost (được pin, có explanation).
        self.assertEqual(set(self.manifest["models"]), {"MLP", "XGBoost"})
        self.assertEqual(self.manifest["selected_model"], "MLP")
        for name, config in self.manifest["models"].items():
            with self.subTest(model=name):
                blob = (self.run_dir / MODEL_DIR / config["file"]).read_bytes()
                self.assertTrue(hasattr(ControlledUnpickler(io.BytesIO(blob)).load(), "predict_proba"))

    def test_run_verification_matrix_rejects_readiness(self):
        def edit(**values):
            def apply(manifest):
                for key, value in values.items():
                    manifest[key] = value
            return apply
        def settings(key, value):
            def apply(manifest):
                manifest["settings"][key] = value
            return apply
        def signature(manifest):
            manifest["settings"]["preprocessing"]["signature"] = "0" * 64
        def bert(manifest):
            manifest["models"]["BERT"] = {"kind": "bert", "directory": "bert", "threshold": 0.5}
            manifest["selected_model"] = "BERT"
        def pinned(edit_config):
            def apply(manifest):
                edit_config(manifest["models"]["XGBoost"])
            return apply
        def nested_file(config):
            config["file"] = "../XGBoost.pkl"
        def threshold_above_one(config):
            config["threshold"] = 1.5
        def boolean_threshold(config):
            config["threshold"] = True
        def lemmatized(manifest):
            manifest["settings"]["preprocessing"]["lemmatization"] = True
        import preprocess
        cases = [
            ("incomplete", variant_run(self, edit(status="incomplete")), "RUN_VERIFICATION"),
            ("schema 1", variant_run(self, edit(schema_version=1)), "RUN_VERIFICATION"),
            ("tampered artifact", variant_run(self, files={f"{MODEL_DIR}/feature_scaler.pkl": b"tampered"}), "RUN_VERIFICATION"),
            ("missing run", Path(tempfile.gettempdir()) / f"missing-{uuid.uuid4()}", "RUN_VERIFICATION"),
            ("feature schema", variant_run(self, settings("feature_names", self.manifest["settings"]["feature_names"][:-1])), "MODEL_COMPATIBILITY"),
            # Chỉ 52 feature FEATURE_NAMES của bản đóng băng v6, không phải BASELINE_FEATURE_NAMES.
            ("old feature list", variant_run(self, settings("feature_names", list(preprocess.FEATURE_NAMES))), "MODEL_COMPATIBILITY"),
            ("preprocessing", variant_run(self, signature), "MODEL_COMPATIBILITY"),
            ("unknown target", variant_run(self, edit(target_mode="spam")), "MODEL_COMPATIBILITY"),
            # Tên pin (policy.MODEL_NAME hoặc IAP_WEB_MODEL) phải có trong manifest["models"] và qua
            # cùng các kiểm tra như model được chọn.
            ("bert pinned", variant_run(self, bert), "MODEL_COMPATIBILITY", "BERT"),
            ("bert selected", variant_run(self, bert), "MODEL_COMPATIBILITY", "selected"),
            ("unknown pinned name", variant_run(self), "MODEL_COMPATIBILITY", "LightGBM"),
            ("pinned nested file", variant_run(self, pinned(nested_file)), "MODEL_COMPATIBILITY"),
            ("pinned threshold", variant_run(self, pinned(threshold_above_one)), "MODEL_COMPATIBILITY"),
            ("pinned boolean threshold", variant_run(self, pinned(boolean_threshold)), "MODEL_COMPATIBILITY"),
            ("lemmatized", variant_run(self, lemmatized), "INFERENCE_SETTINGS"),
        ]
        for name, run, stage, *model in cases:
            environment = {RUN_PATH_ENV: str(run), MODEL_NAME_ENV: model[0] if model else "XGBoost"}
            with self.subTest(case=name), patch.dict(os.environ, environment):
                with self.assertRaises(StartupFailure) as caught:
                    Adapter()
                self.assertEqual(caught.exception.stage, stage)
        # Chưa cấu hình: không có biến môi trường và RUN_PATH là None.
        with patch.dict(os.environ, {RUN_PATH_ENV: ""}), patch(f"{PACKAGE}.policy.RUN_PATH", None), \
                self.assertRaises(StartupFailure) as caught:
            Adapter()
        self.assertEqual(caught.exception.stage, "RUN_VERIFICATION")
        with self.assertRaises(StartupFailure) as caught:
            Adapter(pinned=str(variant_run(self)))
        self.assertEqual(caught.exception.stage, "RUN_VERIFICATION")
        # Tên pin không có trong run: worker không sẵn sàng ở MODEL_COMPATIBILITY.
        with patch.dict(os.environ, {MODEL_NAME_ENV: "LightGBM"}):
            self.assert_worker_unready("MODEL_COMPATIBILITY")

    def test_pinned_model_uses_own_threshold_and_selection_override(self):
        models = self.manifest["models"]
        self.assertNotEqual(models["XGBoost"]["threshold"], models["MLP"]["threshold"])
        metadata = self.adapter.metadata
        self.assertEqual((metadata["selected_model"], metadata["served_model"]), ("MLP", "XGBoost"))
        self.assertEqual(metadata["threshold"], models["XGBoost"]["threshold"])
        self.assertEqual(type(self.adapter.classifier).__name__, "XGBClassifier")
        # Biến môi trường ghi đè hằng số pin, bằng SELECTED_MODEL hoặc bằng tên model được chọn.
        for value in ("selected", "MLP"):
            with self.subTest(override=value), patch.dict(os.environ, {MODEL_NAME_ENV: value}):
                adapter = Adapter()
                self.assertEqual((adapter.metadata["selected_model"], adapter.metadata["served_model"]), ("MLP", "MLP"))
                self.assertEqual(adapter.threshold, models["MLP"]["threshold"])
                self.assertEqual(type(adapter.classifier).__name__, "MLPClassifier")
                self.assertIsNone(adapter.metadata["explanation"])
        # Không có tên pin (MODEL_NAME None, không có biến môi trường): dùng selected_model của manifest.
        with patch.dict(os.environ, {MODEL_NAME_ENV: ""}), patch(f"{PACKAGE}.policy.MODEL_NAME", None):
            self.assertEqual(Adapter().metadata["served_model"], "MLP")
        # Khởi động lại phải phục vụ đúng model đã nhớ: đổi pin là RELEASE_CHANGED, như đổi manifest.
        connection = Mock()
        worker(connection, self.adapter.metadata["run"], self.adapter.release, "MLP")
        connection.send.assert_called_once_with(("unavailable", "RELEASE_CHANGED"))

    def assert_worker_unready(self, stage):
        connection = Mock()
        worker(connection, self.adapter.metadata["run"], self.adapter.release)
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
        width = adapter.metadata["feature_width"]
        modifications = [
            (patch.object(adapter.doc, "vector_size", adapter.doc.vector_size - 1), loaded),
            (patch.object(adapter.scaler, "n_features_in_", adapter.scaler.n_features_in_ - 1), loaded),
            # XGBoost là property của class (MLP giữ hai thuộc tính này trên instance); property
            # tạm trên class (create=True) che được cả hai trường hợp.
            (patch.object(type(adapter.classifier), "n_features_in_", new_callable=PropertyMock, return_value=width - 1, create=True), loaded),
            (patch.object(type(adapter.classifier), "classes_", new_callable=PropertyMock, return_value=np.asarray([1, 2]), create=True), loaded),
            (contextlib.nullcontext(), [object(), adapter.scaler, adapter.classifier]),
            (contextlib.nullcontext(), [adapter.doc, adapter.scaler, object()]),
        ]
        if hasattr(adapter.classifier, "get_booster"):
            modifications.append((patch.object(adapter.classifier, "get_booster", return_value=Mock(num_features=Mock(return_value=width - 1))), loaded))
        for index, (modification, objects) in enumerate(modifications):
            with self.subTest(case=index), modification, patch.object(ControlledUnpickler, "load", side_effect=objects):
                self.assert_worker_unready("MODEL_COMPATIBILITY")

    def test_changed_load_bytes_and_self_consistent_manifest_reject_readiness(self):
        read_bytes = Path.read_bytes
        def changed_bytes(path):
            return b"changed bytes" if path.name == "feature_scaler.pkl" else read_bytes(path)
        with patch.object(Path, "read_bytes", changed_bytes):
            self.assert_worker_unready("ARTIFACT_BYTES")
        manifest = copy.deepcopy(self.manifest)
        manifest["review_note"] = "self-consistent changed release"
        blob = json.dumps(manifest).encode()
        def changed_manifest(path):
            return blob if path.name == "run_manifest.json" else read_bytes(path)
        with patch.object(Path, "read_bytes", changed_manifest):
            self.assert_worker_unready("RELEASE_CHANGED")
        self.assertNotEqual(hashlib.sha256(blob).hexdigest(), self.adapter.release)

    def test_startup_attribution_never_retains_raw_exception(self):
        with patch(f"{PACKAGE}.adapter.file_sha256", side_effect=ValueError("private email and Bearer secret")):
            self.assert_worker_unready("RUN_VERIFICATION")
        connection = Mock()
        with patch(f"{PACKAGE}.adapter.Adapter", side_effect=RuntimeError("private email and Bearer secret")):
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
        validator = Draft7Validator(SCHEMA)
        for sample in SAMPLES:
            with self.subTest(sample=sample.name):
                h = headers()
                response = self.client.post("/v1/analyze", headers=h, files={"file": (sample.name, sample.read_bytes(), "message/rfc822")})
                self.assertEqual(response.status_code, 200)
                validator.validate(response.json())
                expected = {"analysis_status", "label"} | ({"explanation"} if self.supervisor.metadata["explanation"] else set())
                self.assertEqual(set(response.json()), expected)
                self.assertIn(response.json()["label"], ("legit", "phishing"))
                self.assertEqual(response.headers["X-Request-ID"], h["X-Request-ID"])
        import preprocess
        settings = json.loads((FIXTURE["run"] / MANIFEST).read_text(encoding="utf-8"))["settings"]
        self.assertEqual(self.supervisor.metadata["feature_width"], settings["doc2vec_dim"] + len(preprocess.BASELINE_FEATURE_NAMES))
        self.assertEqual(self.supervisor.metadata["hash_seed"], "0")
        self.assertEqual(self.supervisor.metadata["epochs"], settings["inference_epochs"])
        self.assertEqual(self.supervisor.metadata["target_mode"], "phishing")
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

    async def test_recovery_rejects_changed_served_model_and_preserves_startup_pin(self):
        supervisor = Supervisor(TOKEN)
        supervisor.pinned = "dumped_models/classification/runs/pinned"
        supervisor.manifest_digest = "a" * 64
        supervisor.served_model = "XGBoost"
        old_metadata = {"run": supervisor.pinned, "manifest_sha256": supervisor.manifest_digest, "served_model": "XGBoost"}
        supervisor.metadata = old_metadata
        # Cùng manifest nhưng MODEL_NAME/IAP_WEB_MODEL đã đổi: không được phục vụ model khác.
        changed = {**old_metadata, "served_model": "MLP"}
        with patch.object(supervisor, "_message", AsyncMock(return_value=("ready", changed))):
            await supervisor._startup()
        self.assertFalse(supervisor.ready)
        self.assertEqual(supervisor.served_model, "XGBoost")
        self.assertIs(supervisor.metadata, old_metadata)
        self.assertEqual(supervisor.last_failure, "RELEASE_CHANGED")
        # Worker khởi động lại nhận model đã nhớ cùng run và digest.
        with patch.object(service_module.multiprocessing, "get_context") as context, \
                patch.object(service_module.asyncio, "create_task", side_effect=lambda coroutine: coroutine.close()):
            context.return_value.Pipe.return_value = (Mock(), Mock())
            supervisor.launch()
        args = context.return_value.Process.call_args.kwargs["args"]
        self.assertEqual(args[1:], (supervisor.pinned, "a" * 64, "XGBoost"))

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

    # Worker là tiến trình spawn nên không patch được RUN_PATH; dùng run không tồn tại
    # để kiểm tra service vẫn sống khi không nạp được run (ca chưa cấu hình được test
    # trong-tiến-trình ở AdapterVerification).
    async def test_unavailable_run_keeps_live_and_reports_run_verification(self):
        with patch.dict(os.environ, {RUN_PATH_ENV: str(Path(tempfile.gettempdir()) / f"missing-{uuid.uuid4()}")}):
            supervisor = Supervisor(TOKEN)
            supervisor.launch()
            await supervisor.startup
        self.assertFalse(supervisor.ready)
        self.assertEqual(supervisor.last_failure, "RUN_VERIFICATION")
        await supervisor.close()

    def test_unavailable_run_http_is_live_but_not_ready(self):
        missing = str(Path(tempfile.gettempdir()) / f"missing-{uuid.uuid4()}")
        with patch.dict(os.environ, {RUN_PATH_ENV: missing}), TestClient(create_app(TOKEN)) as client:
            self.assertEqual(client.get("/health/live").json(), {"status": "alive"})
            self.assertEqual(client.get("/health/ready").status_code, 503)

    async def test_unreapable_child_exits_without_replacement(self):
        supervisor = Supervisor(TOKEN)
        process = Mock()
        process.is_alive.return_value = True
        supervisor.process = process
        with patch(f"{PACKAGE}.service.os._exit") as exit_process:
            await supervisor.recycle()
        exit_process.assert_called_once_with(1)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertTrue(supervisor.closed)
        self.assertIs(supervisor.process, process)


class PinnedRelease(unittest.TestCase):
    """Run v6 đã đóng gói (web/model/, không có trong git): 234 cột, chữ ký v6, phục vụ XGBoost có explanation."""

    def test_bundled_v6_release_metadata(self):
        if policy_module.RUN_PATH is None:
            self.skipTest("RUN_PATH chưa cấu hình")
        if not (WEB_ROOT / policy_module.RUN_PATH / MANIFEST).is_file():
            self.skipTest("Chưa đóng gói run vào web/model/ (web/scripts/bundle-run.py)")
        with patch.dict(os.environ, {RUN_PATH_ENV: "", MODEL_NAME_ENV: ""}):
            adapter = Adapter()
        metadata = adapter.metadata
        self.assertEqual(metadata["run"], str(Path(policy_module.RUN_PATH)))
        self.assertEqual((metadata["feature_width"], metadata["doc2vec_size"], metadata["engineered_size"]), (234, 100, 134))
        self.assertEqual(metadata["preprocessing_signature"],
                         "4c010fc3df571a8a57f4939301c23b9429bace77e4ef379cd76e774886e71f6e")
        # Validation chọn MLP, nhưng web phục vụ XGBoost được pin ở ngưỡng validation của chính nó.
        self.assertEqual((metadata["selected_model"], metadata["served_model"]), ("MLP", "XGBoost"))
        self.assertEqual(metadata["threshold"], 0.2113690823316574)
        self.assertEqual(metadata["explanation"], "xgboost_pred_contribs")
        factors = policy_module.FACTORS["factors"]
        for sample in SAMPLES:
            with self.subTest(sample=sample.name):
                result = adapter.analyze(sample.read_bytes())
                self.assertEqual(set(result), {"analysis_status", "label", "explanation"})
                shown = result["explanation"]["factors"]
                self.assertTrue(1 <= len(shown) <= 5 and all(item["factor"] in factors for item in shown))
        # Classifier phục vụ ở ngưỡng manifest trên mảng test đóng gói: đúng FP/FN của XGBoost trong
        # runs/2026-11-02_baseline_v6/evaluation_results.csv.
        import numpy as np
        run = WEB_ROOT / policy_module.RUN_PATH
        X = np.load(run / "data_X_test.npy", allow_pickle=False)
        y = np.load(run / "data_y_test.npy", allow_pickle=False)
        positive = adapter.classifier.predict_proba(X)[:, 1] >= adapter.threshold
        self.assertEqual((int(((y == 0) & positive).sum()), int(((y == 1) & ~positive).sum())), (1292, 76))


class Repeatability(unittest.TestCase):
    def test_vectors_and_labels_repeat_reorder_and_restart(self):
        os.environ["PYTHONHASHSEED"] = "0"
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[name] = "1"
        names = [p.name for p in SAMPLES]
        results = []
        # Phục vụ XGBoost để so sánh cả explanation qua lặp lại, đảo thứ tự và khởi động lại;
        # tiến trình con spawn kế thừa biến môi trường.
        environment = patch.dict(os.environ, SERVE_XGBOOST)
        environment.start()
        self.addCleanup(environment.stop)
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
        for name, vector_hash, result in results[0] + results[1]:
            self.assertIn("explanation", result)
            current = (vector_hash, result)
            self.assertEqual(seen.setdefault(name, current), current)
        self.assertEqual(len(seen), 5)


class Explanation(unittest.TestCase):
    """AD-14: factor chính xác, có tính cộng, fail closed và chỉ cho XGBoost với target phishing."""

    @classmethod
    def setUpClass(cls):
        # Fixture chọn MLP; cả nhóm phục vụ XGBoost qua IAP_WEB_MODEL, như run v6 đang phục vụ.
        cls.environment = patch.dict(os.environ, SERVE_XGBOOST)
        cls.environment.start()
        cls.run_dir = FIXTURE["run"]
        with patch.dict(os.environ, {RUN_PATH_ENV: str(cls.run_dir)}):
            cls.adapter = Adapter()

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()

    def test_factors_match_independent_contributions_and_schema(self):
        import numpy as np
        import xgboost
        import preprocess
        from jsonschema import Draft7Validator
        FACTORS = policy_module.FACTORS
        adapter, validator = self.adapter, Draft7Validator(SCHEMA)
        self.assertEqual(adapter.metadata["explanation"], "xgboost_pred_contribs")
        names = ["text_content", *preprocess.BASELINE_FEATURE_NAMES]
        # Explanation phủ factor văn bản và đủ 134 feature của v6, mỗi factor có trong catalogue.
        self.assertEqual(adapter.factor_names, names)
        self.assertEqual(len(names), 135)
        self.assertTrue(all(name in FACTORS["factors"] for name in names))
        raws = [sample.read_bytes() for sample in SAMPLES] + list(FIXTURE["raws"].values())[:10]
        for index, raw in enumerate(raws):
            with self.subTest(email=index):
                result = adapter.analyze(raw)
                validator.validate(result)
                factors = result["explanation"]["factors"]
                data = xgboost.DMatrix(adapter.vector(raw))
                contrib = adapter.classifier.get_booster().predict(data, pred_contribs=True)[0]
                margin = adapter.classifier.get_booster().predict(data, output_margin=True)[0]
                self.assertAlmostEqual(float(contrib.sum()), float(margin), delta=1e-3)
                dim = adapter.doc.vector_size
                values = [float(contrib[:dim].sum()), *map(float, contrib[dim:-1])]
                order = sorted((i for i, v in enumerate(values) if v != 0), key=lambda i: (-abs(values[i]), i))[:5]
                largest = abs(values[order[0]])
                expected = [{"factor": names[i], "direction": "positive" if values[i] > 0 else "negative",
                             "strength": round(abs(values[i]) / largest, 2)} for i in order]
                self.assertEqual(factors, [factor for factor in expected if factor["strength"] > 0])
                self.assertTrue(1 <= len(factors) <= 5 and factors[0]["strength"] == 1.0)
                self.assertTrue(all(f["factor"] in FACTORS["factors"] for f in factors))
                self.assertEqual(len({f["factor"] for f in factors}), len(factors))
                self.assertEqual(result["label"], "phishing" if adapter.score(adapter.vector(raw)) >= adapter.threshold else "legit")
                self.assertTrue(np.isfinite([f["strength"] for f in factors]).all())

    def test_ranking_ties_rounding_and_empty_contributions_follow_ad14(self):
        import numpy as np
        adapter, raw = self.adapter, SAMPLES[0].read_bytes()
        dim = adapter.doc.vector_size
        row = np.zeros((1, adapter.width))
        # Văn bản 0.6 + 0.4 = 1.0; hai feature hoà 0.5 xếp theo thứ tự feature; factor thứ 5 làm tròn
        # về 0 bị bỏ; factor thứ 6 bị cắt bởi giới hạn 5.
        row[0, 0], row[0, 1] = 0.6, 0.4
        row[0, dim:dim + 5] = [-2.0, 0.5, -0.5, 0.004, 0.003]
        with patch.object(adapter, "contributions", return_value=row):
            factors = adapter.analyze(raw)["explanation"]["factors"]
        self.assertEqual(factors, [
            {"factor": "char_length", "direction": "negative", "strength": 1.0},
            {"factor": "text_content", "direction": "positive", "strength": 0.5},
            {"factor": "word_count", "direction": "positive", "strength": 0.25},
            {"factor": "uppercase_word_ratio", "direction": "negative", "strength": 0.25}])
        with patch.object(adapter, "contributions", return_value=np.zeros((1, adapter.width))):
            self.assertEqual(set(adapter.analyze(raw)), {"analysis_status", "label"})

    def test_unsupported_releases_return_label_only(self):
        def unedited_mlp_fixture(manifest):
            pass  # Fixture đã chọn MLP, giống release v6; phục vụ selection qua biến môi trường.
        def broad_xgboost(manifest):
            manifest["target_mode"] = "broad"
        raw = SAMPLES[0].read_bytes()
        for edit, model in ((unedited_mlp_fixture, "selected"), (broad_xgboost, "XGBoost")):
            environment = {RUN_PATH_ENV: str(variant_run(self, edit)), MODEL_NAME_ENV: model}
            with self.subTest(case=edit.__name__), patch.dict(os.environ, environment):
                adapter = Adapter()
                self.assertIsNone(adapter.metadata["explanation"])
                self.assertEqual(set(adapter.analyze(raw)), {"analysis_status", "label"})

    def test_mismatch_and_catalogue_gap_fail_closed(self):
        FACTORS = policy_module.FACTORS
        raw = SAMPLES[0].read_bytes()
        booster = self.adapter.classifier.get_booster()
        predict = booster.predict
        def shifted(data, **kwargs):
            output = predict(data, **kwargs)
            return output + 0.01 if kwargs.get("pred_contribs") else output
        with patch.object(booster, "predict", side_effect=shifted), self.assertRaises(Rejection) as caught:
            self.adapter.analyze(raw)
        self.assertEqual(caught.exception.code, "INTERNAL_ERROR")
        with patch.dict(os.environ, {RUN_PATH_ENV: str(self.run_dir)}):
            with patch.object(Adapter, "contributions", side_effect=ValueError("not additive")), self.assertRaises(StartupFailure) as startup:
                Adapter()
            self.assertEqual(startup.exception.stage, "EXPLANATION")
            with patch.dict(FACTORS["factors"]):
                del FACTORS["factors"]["html_js_obfuscated"]
                with self.assertRaises(StartupFailure) as gap:
                    Adapter()
            self.assertEqual(gap.exception.stage, "EXPLANATION")

    def test_worker_reports_internal_error_without_result(self):
        connection = Mock()
        connection.recv.side_effect = [(encoded(SAMPLES[0].read_bytes()), "multipart/form-data; boundary=test"), EOFError()]
        with patch.dict(os.environ, {RUN_PATH_ENV: str(self.run_dir)}), \
                patch.object(Adapter, "explain", side_effect=Rejection("INTERNAL_ERROR")):
            worker(connection, None)
        sent = [call.args[0] for call in connection.send.call_args_list]
        self.assertEqual(sent[0][0], "ready")
        self.assertEqual(sent[1:], [("processing", None), ("error", "INTERNAL_ERROR")])
        self.assertIn("INTERNAL_ERROR", POLICY["errors"])

    def test_schema_rejects_malformed_explanations(self):
        from jsonschema import Draft7Validator
        validator = Draft7Validator(SCHEMA)
        factor = {"factor": "num_attachments", "direction": "positive", "strength": 1.0}
        valid = {"analysis_status": "completed", "label": "phishing", "explanation": {"factors": [factor]}}
        self.assertTrue(validator.is_valid(valid))
        for explanation in ({"factors": []}, {"factors": [factor] * 6}, {"factors": [{**factor, "strength": 0}]},
                            {"factors": [{**factor, "strength": 1.5}]}, {"factors": [{**factor, "direction": "up"}]},
                            {"factors": [{**factor, "value": 3}]}, {"factors": [factor], "score": 0.9},
                            {"factors": [{**factor, "factor": "Is-HTML"}]}):
            with self.subTest(explanation=str(explanation)[:60]):
                self.assertFalse(validator.is_valid({**valid, "explanation": explanation}))
