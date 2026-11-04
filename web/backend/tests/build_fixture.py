"""Tạo lại run fixture commit sẵn trong tests/fixture_run/.

Chạy từ thư mục gốc của PhishingEmailDetection:

    .venv/Scripts/python.exe web/backend/tests/build_fixture.py

Dựng một run schema 2 nhỏ theo đúng cách train.py upstream (a202d55) tạo run baseline_v6,
nhưng không import module gốc: email tổng hợp -> _process của pipeline_cache đóng băng ->
baseline_feature_vector (134 feature) -> Doc2Vec + StandardScaler fit trên train -> XGBoost
và MLP, ngưỡng chọn trên validation. Manifest dùng cùng các khoá với run v6 (khoá artifact
viết bằng "\\" như run train trên Windows) và chọn MLP như v6; test phục vụ XGBoost qua tên
pin (MODEL_NAME trong policy.py hoặc biến IAP_WEB_MODEL), không sửa selected_model.
Test backend không import file này; chỉ khi đổi bản đóng băng hoặc synthetic_email mới cần
chạy lại.
"""
import hashlib
import io
import json
import os
import pickle
import platform
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

TESTS = Path(__file__).resolve().parent
MODEL_DIR = ("dumped_models", "classification")
SEED = 42
EPOCHS = 5
INFERENCE_EPOCHS = 30
DOC2VEC_DIM = 100
PRECISION_TARGET = 0.9


def split_of(index):
    # 3/5 train, 1/5 validation, 1/5 test; lớp xen kẽ theo index nên mỗi phần đủ hai lớp.
    return ("train", "train", "train", "validation", "test")[index % 5]


def choose_threshold(y, probability):
    """Ngưỡng có F2 cao nhất trên validation (ưu tiên đạt precision mục tiêu), như train.py."""
    from sklearn.metrics import average_precision_score, fbeta_score, precision_score, recall_score
    best = None
    for threshold in sorted(set(float(p) for p in probability)):
        predicted = probability >= threshold
        precision = float(precision_score(y, predicted, zero_division=0))
        recall = float(recall_score(y, predicted, zero_division=0))
        f2 = float(fbeta_score(y, predicted, beta=2, zero_division=0))
        rank = (precision >= PRECISION_TARGET, f2, threshold)
        if best is None or rank > best[0]:
            best = (rank, {"threshold": threshold, "precision": precision, "recall": recall, "f2": f2})
    decision = best[1]
    decision.update({"precision_target": PRECISION_TARGET,
                     "precision_target_met": decision["precision"] >= PRECISION_TARGET,
                     "average_precision": float(average_precision_score(y, probability))})
    return decision


def main():
    # Vector Doc2Vec (kể cả mảng test) phụ thuộc hash seed của Python; dựng với cùng
    # PYTHONHASHSEED=0 như tiến trình con của service để test so được vector lúc phục vụ.
    if os.environ.get("PYTHONHASHSEED") != "0":
        environment = {**os.environ, "PYTHONHASHSEED": "0"}
        raise SystemExit(subprocess.run([sys.executable, str(Path(__file__).resolve())], env=environment).returncode)
    sys.path.insert(0, str(TESTS))
    import test_demo  # Import package backend: frozen_pipeline đứng đầu sys.path.
    import numpy as np
    import pandas as pd
    import pipeline_cache
    import preprocess
    import sklearn
    from gensim.models.doc2vec import Doc2Vec, TaggedDocument
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBClassifier
    frozen = test_demo.backend_module.FROZEN_PIPELINE
    for module in (preprocess, pipeline_cache):
        if Path(module.__file__).resolve().parent != frozen:
            raise SystemExit(f"{module.__name__} không phải bản đóng băng: {module.__file__}")
    signature, settings = pipeline_cache.preprocessing_signature()
    rows = []
    for index, row in enumerate(test_demo.fixture_rows()):
        identity = pipeline_cache._process((row["Text"], "identity", False))
        prepared = pipeline_cache._process((row["Text"], "features", False))
        if "_error" in identity or "_error" in prepared:
            raise SystemExit(f"Tiền xử lý lỗi ở {row['Location']}")
        rows.append({**{k: v for k, v in row.items() if k != "Text"}, "_dedup_key": identity["_dedup_key"],
                     "_group": index, "Split": split_of(index), "_clean_text": prepared["_clean_text"],
                     "Features": np.asarray(preprocess.baseline_feature_vector(prepared), dtype=np.float32)})
    data = pd.DataFrame(rows)
    frames = {name: data[data.Split == name].reset_index(drop=True) for name in ("train", "validation", "test")}
    train = frames["train"]
    tagged = [TaggedDocument(words=preprocess.tokenize_text(text) or ["emptyemailtoken"], tags=[i])
              for i, text in enumerate(train._clean_text)]
    doc2vec = Doc2Vec(vector_size=DOC2VEC_DIM, dm=0, min_count=2, epochs=EPOCHS,
                      alpha=0.025, min_alpha=0.0005, seed=SEED, workers=1)
    doc2vec.build_vocab(tagged)
    doc2vec.train(tagged, total_examples=len(tagged), epochs=EPOCHS, start_alpha=0.025, end_alpha=0.0005)
    scaler = StandardScaler().fit(np.stack(train.Features.to_list()))  # Chỉ fit trên train.
    arrays = {}
    for name, frame in frames.items():
        doc = np.asarray([preprocess.infer_document_vector(doc2vec, text, INFERENCE_EPOCHS)
                          for text in frame._clean_text], dtype=np.float32)
        features = scaler.transform(np.stack(frame.Features.to_list())).astype(np.float32)
        arrays[name] = (np.hstack([doc, features]), frame.Class.to_numpy(dtype=np.int64))
    X_train, y_train = arrays["train"]
    X_validation, y_validation = arrays["validation"]
    candidates = {
        "XGBoost": XGBClassifier(n_estimators=20, max_depth=3, learning_rate=0.3, eval_metric="logloss",
                                 random_state=SEED, n_jobs=1),
        "MLP": MLPClassifier(hidden_layer_sizes=(16,), max_iter=300, random_state=SEED),
    }
    models, configurations = {}, {}
    for name, model in candidates.items():
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(X_train, y_train)
        decision = choose_threshold(y_validation, model.predict_proba(X_validation)[:, 1])
        decision.update({"convergence_warning": any(issubclass(w.category, ConvergenceWarning) for w in caught),
                         "candidate": 0})
        models[name] = model
        configurations[name] = {"file": f"{name}.pkl", **decision}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        staging = Path(temp) / "fixture_run"
        model_dir = staging.joinpath(*MODEL_DIR)
        model_dir.mkdir(parents=True)
        artifacts = {}

        def write(parts, blob):
            staging.joinpath(*parts).write_bytes(blob)
            artifacts["\\".join(parts)] = hashlib.sha256(blob).hexdigest()

        columns = ["RecordId", "Source", "Location", "LabelKind", "LabelBasis", "OriginalLabel", "Class",
                   "_dedup_key", "_group"]
        for name in ("validation", "test"):
            X, y = arrays[name]
            for prefix, value in (("X", X), ("y", y)):
                buffer = io.BytesIO()
                np.save(buffer, value)
                write((f"data_{prefix}_{name}.npy",), buffer.getvalue())
            write((f"{name}_metadata.csv",), frames[name][columns].to_csv(index=False).encode("utf-8"))
        for filename, model in (("model_dbow.pkl", doc2vec), ("feature_scaler.pkl", scaler),
                                *((f"{name}.pkl", model) for name, model in models.items())):
            write((*MODEL_DIR, filename), pickle.dumps(model))
        manifest = {
            "status": "complete", "schema_version": 2, "target_mode": "phishing", "positive_label": "phishing",
            "selected_model": "MLP", "models": configurations,
            "settings": {
                "lemmatization": False, "doc2vec_dim": DOC2VEC_DIM, "epochs": EPOCHS,
                "inference_epochs": INFERENCE_EPOCHS, "feature_names": list(preprocess.BASELINE_FEATURE_NAMES),
                "attachment_rules": dict(preprocess.ATTACHMENT_RULES),
                "preprocessing": {"signature": signature, "lemmatization": settings["lemmatization"],
                                  "stopwords": settings["stopwords"]},
                "split_counts": {name: {str(k): int(v) for k, v in frame.Class.value_counts().items()}
                                 for name, frame in frames.items()}},
            "seed": SEED, "python": platform.python_version(), "sklearn": sklearn.__version__,
            "test_used_for_selection": False, "artifacts": artifacts}
        model_dir.joinpath("run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        target = test_demo.FIXTURE_RUN
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(staging, target)
    print(json.dumps({"fixture": str(target), "selected_model": manifest["selected_model"],
                      "thresholds": {name: config["threshold"] for name, config in configurations.items()},
                      "artifacts": len(artifacts)}))


if __name__ == "__main__":
    main()
