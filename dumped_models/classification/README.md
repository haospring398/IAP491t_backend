# dumped_models/classification/

Thư mục này **tự động được tạo ra** khi bạn chạy `python train.py` — không
cần commit sẵn gì vào đây.

Sau khi train xong sẽ có:

- `model_dbow.pkl` — Doc2Vec model đã fit trên tập train
- `feature_scaler.pkl` — StandardScaler cho 42 engineered features (bắt
  buộc dùng lại đúng scaler này khi suy luận email mới)
- `Logistic Regression.pkl`, `Random Forest.pkl`, `XGBoost.pkl`, `SVM.pkl`,
  `KNN.pkl`, `Naive Bayes.pkl`, `Decision Tree.pkl`, `MLP.pkl`,
  `AdaBoost.pkl`, `Gradient Boosting.pkl` — 10 classifier đã fit

`evaluate.py` đọc thẳng từ thư mục này để tính Accuracy/Precision/Recall/
F1/ROC-AUC/Confusion Matrix cho từng model.
