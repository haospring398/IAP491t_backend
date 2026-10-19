"""Verified same-run inference, imported only inside the serial model child."""
import hashlib
import io
import json
import logging
import os
import pickle
import random
from email import policy as email_policy
from email.parser import BytesParser
from importlib.metadata import version

from web.backend.policy import POLICY, ROOT, RUN_ID, Rejection

STARTUP_STAGES = frozenset({"DEPENDENCY_LOAD", "RUN_VERIFICATION", "RELEASE_CHANGED", "ARTIFACT_BYTES",
                           "ARTIFACT_LOAD", "MODEL_COMPATIBILITY", "INFERENCE_SETTINGS", "PROVENANCE"})


class StartupFailure(ValueError):
    def __init__(self, stage):
        self.stage = stage if stage in STARTUP_STAGES else "DEPENDENCY_LOAD"
        super().__init__(self.stage)

# Exact globals observed in the three selected, hash-verified local artifacts.
# This is controlled loading of trusted local artifacts, not a pickle sandbox.
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
    ("builtins", "bytearray"), ("sklearn.preprocessing._data", "StandardScaler"),
    ("xgboost.sklearn", "XGBClassifier"), ("xgboost.core", "Booster"),
}


class ControlledUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) not in GLOBALS:
            raise ValueError("Unexpected artifact class")
        return super().find_class(module, name)


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
    def __init__(self, pinned=None, expected_manifest=None):
        self.startup_stage = "DEPENDENCY_LOAD"
        try:
            self._load(pinned, expected_manifest)
        except Exception:
            raise StartupFailure(self.startup_stage) from None

    def _load(self, pinned, expected_manifest):
        os.chdir(ROOT)
        import artifact_store
        import preprocess
        import numpy as np
        from gensim.models.doc2vec import Doc2Vec
        from sklearn.preprocessing import StandardScaler
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
        from xgboost import XGBClassifier
        self.startup_stage = "RUN_VERIFICATION"
        run = artifact_store.selected_run() if pinned is None else ROOT / pinned
        if run.resolve() != (ROOT / artifact_store.RUNS / RUN_ID).resolve():
            raise ValueError("Unexpected demo run")
        manifest_bytes = (run / "manifest.json").read_bytes()
        self.release = hashlib.sha256(manifest_bytes).hexdigest()
        self.startup_stage = "RELEASE_CHANGED"
        if expected_manifest is not None and self.release != expected_manifest:
            raise ValueError("Pinned release changed")
        self.startup_stage = "RUN_VERIFICATION"
        manifest = artifact_store.verify_run(run)
        if manifest != json.loads(manifest_bytes):
            self.startup_stage = "RELEASE_CHANGED"
            raise ValueError("Manifest changed during verification")
        loaded = []
        for name in ("model_dbow.pkl", "feature_scaler.pkl", "XGBoost.pkl"):
            self.startup_stage = "ARTIFACT_BYTES"
            # Verify the exact bytes being unpickled too, closing verification/load races.
            blob = (run / name).read_bytes()
            if hashlib.sha256(blob).hexdigest() != manifest["files"][name]:
                raise ValueError("Artifact changed during loading")
            self.startup_stage = "ARTIFACT_LOAD"
            loaded.append(ControlledUnpickler(io.BytesIO(blob)).load())
        self.doc, self.scaler, self.classifier = loaded
        self.startup_stage = "MODEL_COMPATIBILITY"
        if type(self.doc) is not Doc2Vec or type(self.scaler) is not StandardScaler or type(self.classifier) is not XGBClassifier:
            raise ValueError("Unexpected loaded model type")
        if (self.doc.vector_size != manifest["doc2vec_size"] or
                self.scaler.n_features_in_ != len(preprocess.FEATURE_NAMES) or
                self.classifier.n_features_in_ != manifest["feature_width"] or
                not np.array_equal(self.classifier.classes_, [0, 1]) or
                self.classifier.get_booster().num_features() != manifest["feature_width"]):
            raise ValueError("Incompatible loaded model")
        # Freeze observed local resource behavior even if NLTK is installed later.
        frozen = frozenset(ENGLISH_STOP_WORDS) - {"no", "not", "nor", "never"}
        preprocess._english_stopwords = lambda: frozen
        self.doc.workers = 1
        self.classifier.set_params(n_jobs=1)
        self.startup_stage = "INFERENCE_SETTINGS"
        self.alpha, self.min_alpha, self.epochs = self.doc.alpha, self.doc.min_alpha, self.doc.epochs
        if not np.isfinite([self.alpha, self.min_alpha]).all() or self.epochs < 1:
            raise ValueError("Invalid inherited inference settings")
        self.startup_stage = "RELEASE_CHANGED"
        if hashlib.sha256((run / "manifest.json").read_bytes()).hexdigest() != self.release:
            raise ValueError("Manifest changed during loading")
        self.startup_stage = "PROVENANCE"
        self.metadata = {
            "run": str(run.relative_to(ROOT) if run.is_absolute() else run),
            "manifest_sha256": self.release, "feature_width": manifest["feature_width"],
            "doc2vec_size": self.doc.vector_size, "engineered_size": self.scaler.n_features_in_,
            "alpha": self.alpha, "min_alpha": self.min_alpha, "epochs": self.epochs,
            "stopwords": "sklearn English minus no/not/nor/never", "wordnet": "disabled",
            "hash_seed": os.environ.get("PYTHONHASHSEED"), "numerical_threads": 1,
            "code_sha256": {name: artifact_store.sha256(ROOT / name) for name in
                            ("preprocess.py", "artifact_store.py", "web/backend/adapter.py", "web/backend/service.py", "web/backend/policy.py")},
            "packages": {name: version(name) for name in
                         ("numpy", "scipy", "gensim", "scikit-learn", "xgboost", "nltk", "fastapi", "uvicorn", "python-multipart")},
        }

    def vector(self, raw):
        import numpy as np
        import preprocess
        tokens = validate_email(raw)
        preprocess.reset_extraction_stats()
        engineered = np.asarray(preprocess.extract_engineered_features(raw), dtype=float).reshape(1, -1)
        seed = int.from_bytes(hashlib.sha256(raw + self.release.encode()).digest()[:4], "big")
        python_state, numpy_state, doc_state = random.getstate(), np.random.get_state(), self.doc.random.get_state()
        try:
            random.seed(seed)
            np.random.seed(seed)
            self.doc.random.seed(seed)
            embedded = self.doc.infer_vector(tokens, alpha=self.alpha, min_alpha=self.min_alpha, epochs=self.epochs)
            vector = np.hstack((embedded.reshape(1, -1), self.scaler.transform(engineered)))
            if vector.shape != (1, self.metadata["feature_width"]) or not np.isfinite(vector).all():
                raise ValueError("Invalid inference vector")
            return vector
        finally:
            random.setstate(python_state)
            np.random.set_state(numpy_state)
            self.doc.random.set_state(doc_state)
            preprocess.reset_extraction_stats()

    def analyze(self, raw):
        value = self.classifier.predict(self.vector(raw))[0]
        if value not in (0, 1):
            raise ValueError("Unexpected prediction")
        label = int(value)
        return {"analysis_status": "completed", "label": "legit" if label == 0 else "spam_or_phishing"}


def worker(connection, pinned, expected_manifest=None):
    # Only this child imports the numerical stack. No email/exception logging.
    try:
        adapter = Adapter(pinned, expected_manifest)
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
