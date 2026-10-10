"""Publish and verify a complete, immutable training run."""

import hashlib
import json
import os
from pathlib import Path
import uuid

import numpy as np

from preprocess import FEATURE_NAMES

ROOT = Path("dumped_models/classification")
RUNS = ROOT / "runs"
POINTER = ROOT / "current.json"
CLASSIFIERS = (
    "Logistic Regression", "Random Forest", "XGBoost", "SVM", "KNN",
    "Naive Bayes", "Decision Tree", "MLP", "AdaBoost", "Gradient Boosting",
)
FILES = ("data_X_test.npy", "data_y_test.npy", "model_dbow.pkl",
         "feature_scaler.pkl") + tuple(f"{name}.pkl" for name in CLASSIFIERS)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(run_dir, run_id, X_test, y_test, doc2vec, source_counts,
                   dedup_removed):
    manifest = {
        "run_id": run_id,
        "source_counts": source_counts,
        "dedup_removed": dedup_removed,
        "feature_names": list(FEATURE_NAMES),
        "doc2vec_size": doc2vec.vector_size,
        "test_samples": len(y_test),
        "feature_width": X_test.shape[1],
        "files": {name: sha256(run_dir / name) for name in FILES},
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def verify_run(run_dir):
    run_dir = Path(run_dir)
    with (run_dir / "manifest.json").open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("run_id") != run_dir.name:
        raise ValueError(f"Manifest run ID mismatch: {run_dir}")
    if manifest.get("feature_names") != list(FEATURE_NAMES):
        raise ValueError("Manifest feature schema differs from FEATURE_NAMES")
    if set(manifest.get("files", {})) != set(FILES):
        raise ValueError("Manifest file list is incomplete or unexpected")
    for name in FILES:
        path = run_dir / name
        if not path.is_file():
            raise ValueError(f"Artifact missing: {path}")
        if sha256(path) != manifest["files"][name]:
            raise ValueError(f"Artifact SHA-256 mismatch: {path}")
    X = np.load(run_dir / "data_X_test.npy", allow_pickle=False)
    y = np.load(run_dir / "data_y_test.npy", allow_pickle=False)
    if X.ndim != 2 or y.ndim != 1 or len(X) == 0 or len(X) != len(y):
        raise ValueError("Test sample counts differ or arrays have invalid dimensions")
    if set(np.unique(y)) != {0, 1}:
        raise ValueError("Test labels must contain classes 0 and 1")
    if len(y) != manifest["test_samples"] or X.shape[1] != manifest["feature_width"]:
        raise ValueError("Manifest test size or feature width mismatch")
    if X.shape[1] != manifest["doc2vec_size"] + len(FEATURE_NAMES):
        raise ValueError("Manifest feature schema width mismatch")
    return manifest


def selected_run():
    if not POINTER.is_file():
        raise FileNotFoundError(f"No completed training run: {POINTER}")
    pointer = json.loads(POINTER.read_text(encoding="utf-8"))
    run_id = pointer.get("run_id", "")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("Invalid current run pointer")
    run_dir = RUNS / run_id
    verify_run(run_dir)
    return run_dir


def publish(run_id):
    run_dir = RUNS / run_id
    verify_run(run_dir)
    ROOT.mkdir(parents=True, exist_ok=True)
    temporary = ROOT / f".current-{uuid.uuid4().hex}.json"
    try:
        temporary.write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
        os.replace(temporary, POINTER)
    finally:
        temporary.unlink(missing_ok=True)
