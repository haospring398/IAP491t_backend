"""Verified same-run inference, imported only inside the serial model child."""
import hashlib
import io
import json
import logging
import os
import pickle
import platform
import random
from email import policy as email_policy
from email.parser import BytesParser
from importlib.metadata import version

from .policy import FACTORS, POLICY, WEB_ROOT, Rejection, pinned_model, pinned_run

STARTUP_STAGES = frozenset({"DEPENDENCY_LOAD", "RUN_VERIFICATION", "RELEASE_CHANGED", "ARTIFACT_BYTES",
                           "ARTIFACT_LOAD", "MODEL_COMPATIBILITY", "INFERENCE_SETTINGS", "EXPLANATION", "PROVENANCE"})
MANIFEST = "dumped_models/classification/run_manifest.json"
MODEL_DIR = "dumped_models/classification"
# Nhãn web theo target của run (AD-2 ngoại lệ local: chỉ có bằng chứng validation).
POSITIVE_LABELS = {"phishing": "phishing", "broad": "spam_or_phishing"}
# Explanation (AD-14): tối đa 5 factor, kiểm tính cộng trên 256 dòng test đầu lúc khởi động.
TEXT_FACTOR = "text_content"
MAX_FACTORS = 5
ADDITIVITY_TOLERANCE = 1e-3
STARTUP_EXPLANATION_ROWS = 256


class StartupFailure(ValueError):
    def __init__(self, stage):
        self.stage = stage if stage in STARTUP_STAGES else "DEPENDENCY_LOAD"
        super().__init__(self.stage)

# Global chính xác của Doc2Vec/numpy, cộng các class (không phải hàm) trong module
# sklearn/xgboost cho classifier được chọn. Chỉ nạp artifact cục bộ đã khớp hash;
# đây không phải sandbox pickle.
GLOBALS = {
    ("gensim.models.doc2vec", "Doc2Vec"),
    ("gensim.models.keyedvectors", "KeyedVectors"),
    ("gensim.utils", "call_on_class_only"),
    ("numpy._core.multiarray", "_reconstruct"), ("numpy._core.multiarray", "scalar"),
    ("numpy", "ndarray"), ("numpy", "dtype"),
    ("numpy.random._pickle", "__randomstate_ctor"),
    ("numpy.random._pickle", "__bit_generator_ctor"),
    ("numpy.random._mt19937", "MT19937"),
    ("collections", "defaultdict"), ("builtins", "int"), ("builtins", "hash"),
    ("builtins", "bytearray"), ("builtins", "float"), ("builtins", "slice"),
}
ESTIMATOR_MODULES = ("sklearn.", "xgboost.")


class ControlledUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        exact = (module, name) in GLOBALS
        if not exact and not module.startswith(ESTIMATOR_MODULES):
            raise ValueError("Unexpected artifact class")
        found = super().find_class(module, name)
        # Module estimator chỉ được trả về class, không cho pickle gọi hàm tuỳ ý.
        if not exact and not isinstance(found, type):
            raise ValueError("Unexpected artifact class")
        return found


def strict_address_parsing():
    """email.utils.getaddresses có tham số strict (CPython 3.11.10+), như Python đã trích feature v6."""
    import email.utils
    import inspect
    return "strict" in inspect.signature(email.utils.getaddresses).parameters


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def multipart_email(body, content_type):
    """Parse one in-memory upload in the killable child; never spool to disk."""
    from python_multipart import MultipartParser
    from python_multipart.multipart import parse_options_header
    logging.getLogger("python_multipart.multipart").disabled = True
    media, options = parse_options_header(content_type)
    boundary = options.get(b"boundary")
    if media.lower() != b"multipart/form-data" or not boundary or len(boundary) > 200:
        raise Rejection("INVALID_REQUEST")
    parts = []
    headers = {}
    field, value, data = bytearray(), bytearray(), bytearray()
    ended = False

    def begin():
        if parts:
            raise Rejection("INVALID_REQUEST")
        headers.clear()
        data.clear()

    def header_end():
        key = bytes(field).lower()
        if key in headers:
            raise Rejection("INVALID_REQUEST")
        headers[key] = bytes(value)
        field.clear()
        value.clear()

    def append_data(chunk, start, end):
        data.extend(chunk[start:end])
        if len(data) > POLICY["limits"]["fileBytes"]:
            raise Rejection("EMAIL_TOO_LARGE")

    def finish():
        kind, disposition = parse_options_header(headers.get(b"content-disposition", b""))
        filename = disposition.get(b"filename", b"")
        if kind != b"form-data" or disposition.get(b"name") != b"file" or not filename.lower().endswith(b".eml"):
            raise Rejection("INVALID_REQUEST")
        if not data:
            raise Rejection("EMPTY_EMAIL")
        parts.append(bytes(data))

    def end():
        nonlocal ended
        ended = True

    callbacks = {
        "on_part_begin": begin,
        "on_header_field": lambda b, s, e: field.extend(b[s:e]),
        "on_header_value": lambda b, s, e: value.extend(b[s:e]),
        "on_header_end": header_end,
        "on_part_data": append_data, "on_part_end": finish, "on_end": end,
    }
    try:
        parser = MultipartParser(boundary, callbacks)
        parser.write(body)
        parser.finalize()
    except Rejection:
        raise
    except Exception:
        raise Rejection("INVALID_REQUEST") from None
    if len(parts) != 1 or not ended:
        raise Rejection("INVALID_REQUEST")
    return parts[0]


def validate_email(raw):
    if not raw:
        raise Rejection("EMPTY_EMAIL")
    if len(raw) > POLICY["limits"]["fileBytes"]:
        raise Rejection("EMAIL_TOO_LARGE")
    try:
        msg = BytesParser(policy=email_policy.compat32).parsebytes(raw)
        # RFC-style header/body separation and at least one identity/content header.
        if not (b"\r\n\r\n" in raw or b"\n\n" in raw) or not any(str(msg.get(k, "")).strip() for k in ("From", "To", "Subject", "Date", "Message-ID")):
            raise Rejection("INVALID_EMAIL")
        import preprocess
        decoded = len(str(preprocess._parse_email(raw).get("Subject", "")).encode("utf-8"))
        nodes = 0
        pending = [(msg, 0, False)]
        while pending:
            part, depth, excluded = pending.pop()
            excluded = excluded or part.get_content_disposition() == "attachment" or bool(part.get_filename())
            nodes += 1
            if nodes > POLICY["limits"]["mimeParts"] or depth > POLICY["limits"]["mimeDepth"]:
                raise Rejection("RESOURCE_LIMIT")
            if part.is_multipart():
                pending.extend((child, depth + 1, excluded) for child in part.get_payload())
            else:
                payload = part.get_payload(decode=True)
                if not excluded and part.get_content_type() in ("text/plain", "text/html"):
                    decoded += len(preprocess._safe_decode(part).encode("utf-8"))
            # Decoding can add transfer-encoding defects.
            if any(type(d).__name__ not in POLICY["limits"]["allowedParserDefects"] for d in part.defects):
                raise Rejection("INVALID_EMAIL")
            if decoded > POLICY["limits"]["decodedBytes"]:
                raise Rejection("RESOURCE_LIMIT")
        cleaned = preprocess.cleanText(raw)
        tokens = preprocess.tokenize_text(preprocess.remove_stopwords(cleaned))
        if len(tokens) > POLICY["limits"]["tokens"]:
            raise Rejection("RESOURCE_LIMIT")
        if not tokens:
            raise Rejection("INSUFFICIENT_CONTENT")
        return tokens
    except Rejection:
        raise
    except Exception:
        raise Rejection("INVALID_EMAIL") from None


class Adapter:
    def __init__(self, pinned=None, expected_manifest=None, expected_model=None):
        self.startup_stage = "DEPENDENCY_LOAD"
        try:
            self._load(pinned, expected_manifest, expected_model)
        except Exception:
            raise StartupFailure(self.startup_stage) from None

    def _load(self, pinned, expected_manifest, expected_model):
        os.chdir(WEB_ROOT)
        import math
        import preprocess
        import pipeline_cache
        import numpy as np
        # Thư viện trích feature của run v6 (nạp lười trong preprocess): thiếu gói nào thì
        # worker báo DEPENDENCY_LOAD ngay, không đợi tới email đầu tiên.
        import magika
        import oletools.olevba
        import tldextract
        # Python thiếu getaddresses strict (vd. 3.11.2) phân tích địa chỉ sai cú pháp khác lúc
        # trích feature v6 (lệch tới 13,2 ở feature header), nên không khởi động.
        if not strict_address_parsing():
            raise ValueError("Python email parser differs from training")
        # Nạp model Magika và Public Suffix List ngay: _process bắt mọi lỗi, nên lỗi nạp lười
        # sẽ thành INVALID_EMAIL thay vì worker không sẵn sàng.
        preprocess._magika()
        preprocess._public_suffix_list()
        from gensim.models.doc2vec import Doc2Vec
        from sklearn.base import ClassifierMixin
        from sklearn.preprocessing import StandardScaler
        self.startup_stage = "RUN_VERIFICATION"
        configured = pinned_run()
        if not configured:
            raise ValueError("No web run configured")
        # Đường dẫn tương đối tính từ web/, chạy từ thư mục nào cũng như nhau.
        expected = (WEB_ROOT / configured).resolve()
        run = expected if pinned is None else (WEB_ROOT / pinned).resolve()
        if run != expected:
            raise ValueError("Unexpected demo run")
        manifest_bytes = (run / MANIFEST).read_bytes()
        self.release = hashlib.sha256(manifest_bytes).hexdigest()
        self.startup_stage = "RELEASE_CHANGED"
        if expected_manifest is not None and self.release != expected_manifest:
            raise ValueError("Pinned release changed")
        self.startup_stage = "RUN_VERIFICATION"
        manifest = json.loads(manifest_bytes)
        if manifest.get("status") != "complete" or manifest.get("schema_version") != 2:
            raise ValueError("Run is not a complete schema-2 run")
        # Run train trên Windows có thể ghi khoá bằng "\\"; chuẩn hoá về "/".
        artifacts = {relative.replace("\\", "/"): digest for relative, digest in manifest["artifacts"].items()}
        for relative, digest in artifacts.items():
            path = (run / relative).resolve()
            if run not in path.parents or file_sha256(path) != digest:
                raise ValueError("Run artifact missing or changed")
        self.startup_stage = "MODEL_COMPATIBILITY"
        settings, target = manifest["settings"], manifest["target_mode"]
        # Run v6 dùng BASELINE_FEATURE_NAMES (134 feature), không phải FEATURE_NAMES.
        if target not in POSITIVE_LABELS or settings["feature_names"] != list(preprocess.BASELINE_FEATURE_NAMES):
            raise ValueError("Unsupported target or feature schema")
        recorded = settings.get("preprocessing") or {}
        signature, current = pipeline_cache.preprocessing_signature()
        if recorded.get("signature") != signature or recorded.get("stopwords") != current["stopwords"]:
            raise ValueError("Preprocessing differs from training")
        # Classifier phục vụ: tên pin trong policy (hoặc biến môi trường), không có thì dùng
        # selected_model của manifest. Ngưỡng là ngưỡng validation của chính model đó.
        selected = manifest["selected_model"]
        served = pinned_model() or selected
        # Khởi động lại giữ đúng classifier đã phục vụ, như run và digest manifest: sửa
        # MODEL_NAME hay IAP_WEB_MODEL giữa chừng không được đổi model dưới cùng digest.
        if expected_model is not None and served != expected_model:
            self.startup_stage = "RELEASE_CHANGED"
            raise ValueError("Served model changed")
        models = manifest["models"]
        if not isinstance(served, str) or not isinstance(models, dict) or not isinstance(models.get(served), dict):
            raise ValueError("Served model is not in the run")
        config = models[served]
        threshold = config.get("threshold")
        if (config.get("kind", "sklearn") != "sklearn" or not isinstance(config.get("file"), str) or
                "/" in config["file"] or "\\" in config["file"] or isinstance(threshold, bool) or
                not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1):
            raise ValueError("Served model is not a supported classifier")
        loaded = []
        for name in ("model_dbow.pkl", "feature_scaler.pkl", config["file"]):
            self.startup_stage = "ARTIFACT_BYTES"
            # Kiểm tra lại đúng các byte sẽ unpickle, tránh race giữa verify và load.
            blob = (run / MODEL_DIR / name).read_bytes()
            if hashlib.sha256(blob).hexdigest() != artifacts.get(f"{MODEL_DIR}/{name}"):
                raise ValueError("Artifact changed during loading")
            self.startup_stage = "ARTIFACT_LOAD"
            loaded.append(ControlledUnpickler(io.BytesIO(blob)).load())
        self.doc, self.scaler, self.classifier = loaded
        self.startup_stage = "MODEL_COMPATIBILITY"
        width = self.width = settings["doc2vec_dim"] + len(preprocess.BASELINE_FEATURE_NAMES)
        if (type(self.doc) is not Doc2Vec or type(self.scaler) is not StandardScaler or
                not isinstance(self.classifier, ClassifierMixin) or not hasattr(self.classifier, "predict_proba")):
            raise ValueError("Unexpected loaded model type")
        if (self.doc.vector_size != settings["doc2vec_dim"] or
                self.scaler.n_features_in_ != len(preprocess.BASELINE_FEATURE_NAMES) or
                self.classifier.n_features_in_ != width or
                not np.array_equal(self.classifier.classes_, [0, 1]) or
                (hasattr(self.classifier, "get_booster") and self.classifier.get_booster().num_features() != width)):
            raise ValueError("Incompatible loaded model")
        # Giữ đúng danh sách stopwords đã ghi lúc train (đã so khớp với bản đóng băng ở trên).
        frozen = frozenset(recorded["stopwords"])
        preprocess._english_stopwords = lambda: frozen
        self.doc.workers = 1
        if "n_jobs" in self.classifier.get_params():
            self.classifier.set_params(n_jobs=1)
        self.startup_stage = "INFERENCE_SETTINGS"
        self.epochs, self.lemmatization = settings["inference_epochs"], recorded["lemmatization"]
        # Bản đóng băng không còn NLTK nên không lemmatize được; run lemmatize bị từ chối.
        if not isinstance(self.epochs, int) or self.epochs < 1 or self.lemmatization is not False:
            raise ValueError("Invalid inference settings")
        self.threshold, self.positive_label = float(threshold), POSITIVE_LABELS[target]
        self.startup_stage = "EXPLANATION"
        # Chỉ XGBoost có đóng góp chính xác. Run broad không giải thích vì trình duyệt không
        # biết tên lớp dương khi kết quả là Legit.
        self.explained = hasattr(self.classifier, "get_booster") and target == "phishing"
        self.factor_names = [TEXT_FACTOR, *preprocess.BASELINE_FEATURE_NAMES]
        if self.explained:
            if not all(name in FACTORS.get("factors", {}) for name in self.factor_names) or "data_X_test.npy" not in artifacts:
                raise ValueError("Explanation catalogue or test arrays incomplete")
            sample = np.load(run / "data_X_test.npy", allow_pickle=False, mmap_mode="r")[:STARTUP_EXPLANATION_ROWS]
            if sample.ndim != 2 or not len(sample) or sample.shape[1] != width:
                raise ValueError("Unexpected test arrays for explanation")
            self.contributions(sample)
        self.startup_stage = "RELEASE_CHANGED"
        if hashlib.sha256((run / MANIFEST).read_bytes()).hexdigest() != self.release:
            raise ValueError("Manifest changed during loading")
        self.startup_stage = "PROVENANCE"
        self.metadata = {
            "run": str(run.relative_to(WEB_ROOT) if WEB_ROOT in run.parents else run),
            "manifest_sha256": self.release, "target_mode": target,
            "selected_model": selected, "served_model": served,
            "threshold": self.threshold, "feature_width": width,
            "doc2vec_size": self.doc.vector_size, "engineered_size": self.scaler.n_features_in_,
            "alpha": preprocess.DOC2VEC_INFER_ALPHA, "min_alpha": preprocess.DOC2VEC_INFER_MIN_ALPHA,
            "epochs": self.epochs, "lemmatization": self.lemmatization,
            "preprocessing_signature": signature,
            "explanation": "xgboost_pred_contribs" if self.explained else None,
            "hash_seed": os.environ.get("PYTHONHASHSEED"), "numerical_threads": 1,
            "code_sha256": {name: file_sha256(WEB_ROOT / name) for name in
                            ("backend/frozen_pipeline/preprocess.py", "backend/frozen_pipeline/pipeline_cache.py",
                             "backend/adapter.py", "backend/service.py", "backend/policy.py")},
            # Thư viện chuẩn email đổi theo bản vá Python (getaddresses strict) nên ghi lại cả bản Python.
            "python": platform.python_version(),
            "packages": {name: version(name) for name in
                         ("numpy", "scipy", "gensim", "scikit-learn", "xgboost", "tldextract", "magika", "oletools",
                          "fastapi", "uvicorn", "python-multipart")},
        }

    def vector(self, raw):
        import numpy as np
        import preprocess
        import pipeline_cache
        validate_email(raw)
        preprocess.reset_extraction_stats()
        python_state, numpy_state, doc_state = random.getstate(), np.random.get_state(), self.doc.random.get_state()
        try:
            # Cùng hàm tiền xử lý với lúc train (pipeline_cache) để feature và văn bản trùng khớp;
            # vector 134 feature ghép đúng như train.py v6 (baseline_feature_vector, float32).
            prepared = pipeline_cache._process((raw, "features", self.lemmatization))
            if "_error" in prepared:
                raise Rejection("INVALID_EMAIL")
            engineered = np.asarray(preprocess.baseline_feature_vector(prepared), dtype=np.float32).reshape(1, -1)
            embedded = preprocess.infer_document_vector(self.doc, prepared["_clean_text"], self.epochs)
            vector = np.hstack((np.asarray(embedded, dtype=np.float32).reshape(1, -1),
                                self.scaler.transform(engineered).astype(np.float32)))
            if vector.shape != (1, self.metadata["feature_width"]) or not np.isfinite(vector).all():
                raise ValueError("Invalid inference vector")
            return vector
        finally:
            random.setstate(python_state)
            np.random.set_state(numpy_state)
            self.doc.random.set_state(doc_state)
            preprocess.reset_extraction_stats()

    def score(self, vector):
        import numpy as np
        index = np.flatnonzero(np.asarray(self.classifier.classes_) == 1)
        if len(index) != 1:
            raise ValueError("Classifier has no positive class")
        probability = float(np.asarray(self.classifier.predict_proba(vector))[0, index[0]])
        if not 0 <= probability <= 1:
            raise ValueError("Invalid positive-class probability")
        return probability

    def contributions(self, matrix):
        """Đóng góp chính xác của XGBoost lên margin; tổng mỗi hàng (kể cả bias) phải bằng margin."""
        import numpy as np
        import xgboost
        booster = self.classifier.get_booster()
        data = xgboost.DMatrix(np.asarray(matrix, dtype=np.float32), nthread=1)
        contrib = booster.predict(data, pred_contribs=True)
        margin = booster.predict(data, output_margin=True)
        if (contrib.shape != (len(matrix), self.width + 1) or not np.isfinite(contrib).all() or
                not np.allclose(contrib.sum(axis=1), margin, rtol=0, atol=ADDITIVITY_TOLERANCE)):
            raise ValueError("Contributions do not reproduce the model margin")
        return contrib[:, :-1]

    def explain(self, vector):
        if not self.explained:
            return None
        try:
            contrib = self.contributions(vector)[0]
        except ValueError:
            raise Rejection("INTERNAL_ERROR") from None
        dim = self.doc.vector_size
        # Gộp các chiều Doc2Vec thành một factor văn bản; bias không phải factor.
        values = [float(contrib[:dim].sum()), *(float(value) for value in contrib[dim:])]
        order = sorted((i for i, value in enumerate(values) if value != 0), key=lambda i: (-abs(values[i]), i))[:MAX_FACTORS]
        if not order:
            return None
        largest = abs(values[order[0]])
        factors = [{"factor": self.factor_names[i], "direction": "positive" if values[i] > 0 else "negative",
                    "strength": round(abs(values[i]) / largest, 2)} for i in order]
        return {"factors": [factor for factor in factors if factor["strength"] > 0]}

    def analyze(self, raw):
        vector = self.vector(raw)
        positive = self.score(vector) >= self.threshold
        result = {"analysis_status": "completed", "label": self.positive_label if positive else "legit"}
        explanation = self.explain(vector)
        if explanation:
            result["explanation"] = explanation
        return result


def worker(connection, pinned, expected_manifest=None, expected_model=None):
    # Only this child imports the numerical stack. No email/exception logging.
    try:
        adapter = Adapter(pinned, expected_manifest, expected_model)
        connection.send(("ready", adapter.metadata))
    except Exception as error:
        stage = error.stage if isinstance(error, StartupFailure) else "DEPENDENCY_LOAD"
        connection.send(("unavailable", stage))
        connection.close()
        return
    try:
        while True:
            body, content_type = connection.recv()
            connection.send(("processing", None))
            try:
                result = adapter.analyze(multipart_email(body, content_type))
                connection.send(("success", result))
            except Rejection as error:
                connection.send(("error", error.code))
            except Exception:
                connection.send(("error", "MODEL_UNAVAILABLE"))
                return
            finally:
                body = content_type = None
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()
