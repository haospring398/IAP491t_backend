"""Phân tích SHAP cho một run 19-10 (train.py --mode baseline) trên tập test.

Đọc classifier (mặc định selected_model) cùng tập test của ĐÚNG run đó, tính đóng góp
SHAP chính xác cho từng email bằng XGBoost pred_contribs (không cần thư viện shap),
rồi ghi vào <run>/shap/:
  - shap_global.csv     mean |SHAP|, mean SHAP và tỷ trọng của từng feature; 100 chiều
                        Doc2Vec gộp thành một nhóm vì SHAP cộng được.
  - shap_by_source.csv  SHAP trung bình (có dấu) theo nguồn dữ liệu: giá trị dương nghĩa
                        là feature đẩy email của nguồn đó về phía phishing.
  - shap_errors.csv     email bị đoán sai cùng 5 feature đẩy mạnh nhất về phía sai.
  - shap_top.png        biểu đồ top feature theo mean |SHAP|.
SHAP ở đây giải thích margin (log-odds) của XGBoost. Chỉ hỗ trợ XGBoost; model khác
cần thư viện shap và không thuộc phạm vi script này. Không sửa file nào khác của run.

Cách dùng:
  python analyze_shap.py --run runs/2026-10-23_web2
  python analyze_shap.py --run runs/2026-10-23_web2 --model XGBoost --top-n 25
"""
import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate import file_digest

DOC2VEC_GROUP = "doc2vec (gộp mọi chiều)"


def load_run(run, model_name=None):
    run = Path(run)
    model_dir = run / "dumped_models" / "classification"
    manifest = json.loads((model_dir / "run_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete" or manifest.get("schema_version") != 2:
        raise ValueError("Run chưa hoàn tất hoặc không phải schema 2")
    artifacts = {key.replace("\\", "/"): digest for key, digest in manifest["artifacts"].items()}
    name = model_name or manifest["selected_model"]
    config = manifest["models"].get(name)
    if not config or config.get("kind", "sklearn") != "sklearn" or "file" not in config:
        raise ValueError(f"Model {name} không phải classifier sklearn/XGBoost trong run")
    needed = ["data_X_test.npy", "data_y_test.npy", "test_metadata.csv",
              f"dumped_models/classification/{config['file']}"]
    for relative in needed:
        if file_digest(run / relative) != artifacts.get(relative):
            raise ValueError(f"Artifact thay đổi hoặc thiếu so với manifest: {relative}")
    with (model_dir / config["file"]).open("rb") as handle:
        model = pickle.load(handle)
    if not hasattr(model, "get_booster"):
        raise ValueError(f"{name} không phải XGBoost; SHAP chính xác ở đây chỉ hỗ trợ XGBoost")
    X = np.load(run / "data_X_test.npy", allow_pickle=False)
    y = np.load(run / "data_y_test.npy", allow_pickle=False)
    metadata = pd.read_csv(run / "test_metadata.csv")
    settings = manifest["settings"]
    names = list(settings["feature_names"])
    if X.shape != (len(y), settings["doc2vec_dim"] + len(names)) or len(metadata) != len(y) or \
            not np.array_equal(metadata["Class"].to_numpy(), y):
        raise ValueError("Mảng test, metadata và schema feature không khớp nhau")
    return {"run": run, "name": name, "model": model, "threshold": float(config["threshold"]),
            "X": X, "y": y, "metadata": metadata, "doc2vec_dim": settings["doc2vec_dim"],
            "feature_names": names}


def contributions(model, X):
    """Đóng góp SHAP của từng cột cộng bias; tổng mỗi hàng bằng margin của model."""
    import xgboost
    booster = model.get_booster()
    matrix = xgboost.DMatrix(X)
    contrib = booster.predict(matrix, pred_contribs=True)
    margin = booster.predict(matrix, output_margin=True)
    if not np.allclose(contrib.sum(axis=1), margin, atol=1e-3):
        raise ValueError("Tổng đóng góp SHAP không bằng margin của model")
    return contrib[:, :-1], contrib[:, -1]


def analyze(run, model_name=None, top_n=20, output=None):
    data = load_run(run, model_name)
    contrib, _ = contributions(data["model"], data["X"])
    dim = data["doc2vec_dim"]
    # SHAP cộng được: tổng các chiều Doc2Vec là đóng góp của cả biểu diễn văn bản.
    table = pd.DataFrame(contrib[:, dim:], columns=data["feature_names"])
    table.insert(0, DOC2VEC_GROUP, contrib[:, :dim].sum(axis=1))
    y = data["y"]
    scores = np.asarray(data["model"].predict_proba(data["X"]))[:, list(data["model"].classes_).index(1)]
    predicted = (scores >= data["threshold"]).astype(int)
    out = Path(output) if output else data["run"] / "shap"
    out.mkdir(parents=True, exist_ok=True)

    absolute = table.abs().mean()
    summary = pd.DataFrame({
        "mean_abs_shap": absolute,
        "share_percent": 100 * absolute / absolute.sum(),
        "mean_shap": table.mean(),
        "mean_shap_phishing": table[y == 1].mean(),
        "mean_shap_legit": table[y == 0].mean(),
    }).sort_values("mean_abs_shap", ascending=False)
    summary.index.name = "feature"
    summary.to_csv(out / "shap_global.csv")

    metadata = data["metadata"].reset_index(drop=True)
    by_source = table.groupby(metadata["Source"]).mean()
    by_source.insert(0, "Count", metadata.groupby("Source").size())
    by_source.insert(1, "Class", metadata.groupby("Source")["Class"].agg(lambda c: "/".join(map(str, sorted(set(c))))))
    by_source.to_csv(out / "shap_by_source.csv")

    rows = []
    for index in np.flatnonzero(predicted != y):
        # Email legit bị báo phishing: feature dương lớn nhất; phishing bị bỏ sót: âm nhất.
        values = table.iloc[index]
        ordered = values.sort_values(ascending=y[index] == 1)
        rows.append({"RecordId": metadata["RecordId"][index] if "RecordId" in metadata else "",
                     "Source": metadata["Source"][index], "Class": int(y[index]),
                     "Error": "FP" if y[index] == 0 else "FN", "Score": float(scores[index]),
                     **{f"top{rank + 1}": f"{feature} ({value:+.3f})"
                        for rank, (feature, value) in enumerate(ordered.head(5).items())}})
    pd.DataFrame(rows).to_csv(out / "shap_errors.csv", index=False)

    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    top = summary.head(top_n)[::-1]
    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(top))))
    ax.barh(top.index, top["mean_abs_shap"], color="#3b6ea5")
    ax.set(xlabel="mean |SHAP| (log-odds)", title=f"{data['name']} — top {len(top)} feature trên tập test")
    fig.tight_layout(); fig.savefig(out / "shap_top.png"); plt.close(fig)
    return {"output": out, "summary": summary, "by_source": by_source, "errors": len(rows),
            "model": data["name"]}


if __name__ == "__main__":
    import sys
    # Console Windows mặc định cp1252 không in được tiếng Việt.
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Phân tích SHAP (XGBoost) trên tập test của một run.")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--model", help="Mặc định là selected_model của manifest")
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()
    result = analyze(args.run, args.model, args.top_n)
    summary = result["summary"]
    print(f"Model {result['model']}; kết quả ghi tại {result['output']}")
    print(f"Tỷ trọng Doc2Vec: {summary.loc[DOC2VEC_GROUP, 'share_percent']:.1f}%; "
          f"{len(summary) - 1} engineered feature: {100 - summary.loc[DOC2VEC_GROUP, 'share_percent']:.1f}%")
    print(summary.head(args.top_n)[["mean_abs_shap", "share_percent", "mean_shap_phishing",
                                     "mean_shap_legit"]].round(4).to_string())
    print(f"Email đoán sai: {result['errors']} (xem shap_errors.csv)")
