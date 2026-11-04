# #### analyze_feature_importance.py
#
# Chẩn đoán xem 5 model dựa trên cây (Random Forest, XGBoost, Gradient
# Boosting, Decision Tree, AdaBoost -- đều có sẵn .feature_importances_)
# đang thực sự "bám" vào đâu để đạt độ chính xác ~99.9%:
#   - Nếu phần lớn importance dồn vào vài chiều Doc2Vec CỤ THỂ hoặc vào các
#     engineered feature mang tính "đặc trưng nguồn dữ liệu" hơn là "đặc
#     trưng phishing" (vd from_domain_is_freemail luôn=0 với Enron nhưng
#     luôn=1 với Nazario/SpamAssassin, is_html/num_urls gần như phân tách
#     2 lớp hoàn hảo) -- đó là dấu hiệu model đang học shortcut phân biệt
#     NGUỒN DỮ LIỆU (Enron vs không-Enron) chứ không phải học "thế nào là
#     phishing" theo nghĩa tổng quát.
#   - Nếu importance trải đều hợp lý trên nhiều feature khác nhau (URL,
#     social-engineering, content...) thì đáng tin hơn.
#
# Cách dùng (SAU khi đã chạy train.py, cần các file .pkl trong
# dumped_models/classification/):
#   python analyze_feature_importance.py
#   python analyze_feature_importance.py --top-n 25 --out-dir ./importance_report

import argparse
import os
import pickle

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt

from preprocess import FEATURE_NAMES

DOC2VEC_DIM = 100

TREE_BASED_MODELS = [
    "Random Forest", "XGBoost", "Gradient Boosting", "Decision Tree", "AdaBoost",
]


def build_full_feature_names():
    """Tên đầy đủ cho 142 chiều: 100 chiều Doc2Vec + 42 engineered feature,
    ĐÚNG THEO THỨ TỰ ghép trong train.py (np.hstack([doc2vec, engineered]))."""
    return [f"doc2vec_dim_{i}" for i in range(DOC2VEC_DIM)] + list(FEATURE_NAMES)


def load_model(model_dir, name):
    path = os.path.join(model_dir, f"{name}.pkl")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def analyze_one_model(name, model, feature_names, top_n):
    if not hasattr(model, "feature_importances_"):
        print(f"  [{name}] Không có feature_importances_ (model này không phải dạng cây), bỏ qua.")
        return None

    importances = np.asarray(model.feature_importances_)
    if len(importances) != len(feature_names):
        print(f"  [{name}] CẢNH BÁO: số chiều importance ({len(importances)}) khác số tên "
              f"feature ({len(feature_names)}) -- model có thể train trên feature set khác, bỏ qua.")
        return None

    doc2vec_mass = importances[:DOC2VEC_DIM].sum()
    engineered_mass = importances[DOC2VEC_DIM:].sum()
    total = importances.sum() or 1.0

    print(f"\n=== {name} ===")
    print(f"  Tổng importance khối Doc2Vec (100 chiều):     {doc2vec_mass/total*100:5.1f}%")
    print(f"  Tổng importance khối Engineered (42 feature): {engineered_mass/total*100:5.1f}%")

    order = np.argsort(importances)[::-1][:top_n]
    print(f"  Top {top_n} feature quan trọng nhất:")
    rows = []
    for rank, idx in enumerate(order, start=1):
        fname = feature_names[idx]
        pct = importances[idx] / total * 100
        kind = "doc2vec" if idx < DOC2VEC_DIM else "engineered"
        flag = "  <-- có thể là shortcut theo NGUỒN dữ liệu, không phải bản chất phishing" \
            if fname in SUSPECT_SHORTCUT_FEATURES else ""
        print(f"    {rank:2d}. {fname:35s} {pct:5.1f}%  ({kind}){flag}")
        rows.append({"model": name, "rank": rank, "feature": fname,
                      "importance_pct": pct, "kind": kind})
    return rows


# Các feature mà nếu đứng TOP nên nghi ngờ là đang phân biệt "Enron vs
# không-Enron" thay vì "phishing vs không-phishing" thật sự -- vì đặc
# điểm nguồn dữ liệu (nội bộ công ty vs email quảng cáo/lừa đảo ngoài) tự
# nhiên khác biệt CỰC LỚN, không liên quan gì tới kỹ thuật phishing.
SUSPECT_SHORTCUT_FEATURES = {
    "is_html", "num_urls", "has_form_tag", "from_domain_is_freemail",
    "num_https_urls", "num_http_urls", "html_to_text_ratio", "num_attachments",
    "num_recipients", "char_length", "word_count",
}


def plot_top_features(all_rows, out_dir, top_n=15):
    df = pd.DataFrame(all_rows)
    for model_name in df["model"].unique():
        sub = df[df["model"] == model_name].sort_values("importance_pct", ascending=True).tail(top_n)
        colors = ["#d62728" if f in SUSPECT_SHORTCUT_FEATURES else "#1f77b4" for f in sub["feature"]]
        plt.figure(figsize=(9, 6))
        plt.barh(sub["feature"], sub["importance_pct"], color=colors)
        plt.xlabel("Importance (%)")
        plt.title(f"Top {top_n} feature quan trọng nhất -- {model_name}\n"
                  f"(đỏ = nghi ngờ shortcut theo nguồn dữ liệu)")
        plt.tight_layout()
        safe_name = model_name.replace(" ", "_")
        plt.savefig(os.path.join(out_dir, f"importance_{safe_name}.png"), dpi=120)
        plt.close()


def main():
    parser = argparse.ArgumentParser(description="Phân tích feature importance của các model đã train.")
    parser.add_argument("--model-dir", default="dumped_models/classification")
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--out-dir", default="./importance_report")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    feature_names = build_full_feature_names()

    all_rows = []
    any_model_found = False
    for name in TREE_BASED_MODELS:
        model = load_model(args.model_dir, name)
        if model is None:
            print(f"  [{name}] Không tìm thấy file model trong '{args.model_dir}', bỏ qua.")
            continue
        any_model_found = True
        rows = analyze_one_model(name, model, feature_names, args.top_n)
        if rows:
            all_rows.extend(rows)

    if not any_model_found:
        raise SystemExit(f"Không tìm thấy model nào trong '{args.model_dir}'. "
                          f"Chạy train.py trước đã nhé.")

    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_csv(os.path.join(args.out_dir, "feature_importance.csv"), index=False)
        plot_top_features(all_rows, args.out_dir, args.top_n)

        # Tổng hợp: feature nào lọt top-N ở NHIỀU model nhất -- càng nhiều
        # model đồng thuận thì càng đáng tin (hoặc càng đáng nghi nếu đó là
        # 1 trong các SUSPECT_SHORTCUT_FEATURES).
        print("\n=== TỔNG HỢP: feature xuất hiện trong top của nhiều model nhất ===")
        agreement = df.groupby("feature")["model"].nunique().sort_values(ascending=False)
        for fname, n_models in agreement.head(15).items():
            flag = "  <-- SHORTCUT NGHI VẤN" if fname in SUSPECT_SHORTCUT_FEATURES else ""
            print(f"  {fname:35s} xuất hiện ở {n_models}/{len(TREE_BASED_MODELS)} model{flag}")

        n_suspect = df["feature"].isin(SUSPECT_SHORTCUT_FEATURES).sum()
        print(f"\n-> {n_suspect}/{len(df)} lượt xuất hiện trong top-{args.top_n} là feature "
              f"thuộc nhóm nghi ngờ shortcut theo nguồn dữ liệu.")
        print(f"   Nếu tỉ lệ này cao VÀ % importance của chúng lớn -- accuracy 99.9% khả năng cao "
              f"đến từ việc phân biệt 'Enron vs không-Enron' chứ không phải phishing thật sự.")

    print(f"\nĐã lưu: {args.out_dir}/feature_importance.csv + biểu đồ importance_<model>.png")


if __name__ == "__main__":
    main()
