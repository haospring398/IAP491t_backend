"""Evaluate saved classifiers with validation-selected thresholds.

ROC-AUC and AP always use probabilities. Test labels never select thresholds.
Run: python evaluate.py
"""
from pathlib import Path
import hashlib
import json
import math
import pickle

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix,
    f1_score, fbeta_score, precision_recall_curve, precision_score, recall_score,
    roc_auc_score, roc_curve)

BASE_DIR = Path(__file__).resolve().parent


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def positive_scores(model, X):
    index = np.flatnonzero(np.asarray(model.classes_) == 1)
    if len(index) != 1:
        raise ValueError('Classifier must have positive class 1')
    scores = np.asarray(model.predict_proba(X)[:, index[0]], dtype=float)
    if not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
        raise ValueError('Invalid classifier probabilities')
    return scores


def select_threshold(y, scores, min_precision=0.90):
    """Maximize validation recall subject to a precision floor.

    If unattainable, use best F2 and explicitly mark the floor as unmet.
    This is a validation target, not a guarantee of production precision.
    """
    if not 0 <= min_precision <= 1:
        raise ValueError('min_precision must be in [0, 1]')
    y, scores = np.asarray(y), np.asarray(scores)
    if set(np.unique(y)) != {0, 1} or len(y) != len(scores):
        raise ValueError('Threshold selection needs aligned validation rows with both classes')
    p, r, thresholds = precision_recall_curve(y, scores)
    p, r = p[:-1], r[:-1]
    f2 = 5 * p * r / np.maximum(4 * p + r, 1e-12)
    eligible = np.flatnonzero((p >= min_precision) & (r > 0))
    feasible = bool(len(eligible))
    if feasible:
        best = max(eligible, key=lambda i: (r[i], f2[i], p[i], thresholds[i]))
    else:
        best = max(range(len(thresholds)), key=lambda i: (f2[i], r[i], p[i]))
    return {'threshold': float(thresholds[best]), 'precision': float(p[best]),
            'recall': float(r[best]), 'f2': float(f2[best]),
            'precision_target': float(min_precision), 'precision_target_met': feasible}


def validation_rank(result):
    # All feasible candidates outrank fallback candidates; never consult test.
    if result['precision_target_met']:
        return (1, result['recall'], result['f2'], result['average_precision'])
    return (0, result['f2'], result['recall'], result['average_precision'])


def classification_metrics(y, scores, threshold):
    y = np.asarray(y)
    predicted = (np.asarray(scores) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    both = len(np.unique(y)) == 2
    return {'Accuracy': float(accuracy_score(y, predicted)),
            'F1-score': float(f1_score(y, predicted, zero_division=0)),
            'F2-score': float(fbeta_score(y, predicted, beta=2, zero_division=0)),
            'Precision': float(precision_score(y, predicted, zero_division=0)),
            'Recall': float(recall_score(y, predicted, zero_division=0)),
            'ROC-AUC': float(roc_auc_score(y, scores)) if both else None,
            'Average-Precision': float(average_precision_score(y, scores)) if both else None,
            'FPR': float(fp / (fp + tn)) if fp + tn else None,
            'FNR': float(fn / (fn + tp)) if fn + tp else None,
            'TN': int(tn), 'FP': int(fp), 'FN': int(fn), 'TP': int(tp)}


def evaluate(base_dir=BASE_DIR):
    base = Path(base_dir)
    model_dir = base / 'dumped_models' / 'classification'
    manifest_path = model_dir / 'run_manifest.json'
    manifest = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('status') != 'complete':
            raise RuntimeError('Training is incomplete; refusing to mix artifacts from different runs')
        for relative, expected in manifest['artifacts'].items():
            if file_digest(base / relative) != expected:
                raise RuntimeError(f'Artifact changed since training: {relative}. Retrain/recover the same run.')
        configurations = manifest['models']
        print('Target:', manifest['target_mode'], '; selected using validation:', manifest['selected_model'])
    else:
        print('Legacy models: using threshold 0.5; label scope and split provenance are unavailable.')
        configurations = {p.stem: {'file': p.name, 'threshold': 0.5}
                          for p in sorted(model_dir.glob('*.pkl'))
                          if p.name not in {'model_dbow.pkl', 'feature_scaler.pkl'}}
    if not configurations:
        raise ValueError('No classifier artifacts were found')
    X = np.load(base / 'data_X_test.npy', allow_pickle=False)
    y = np.load(base / 'data_y_test.npy', allow_pickle=False)
    if set(np.unique(y)) != {0, 1} or len(X) != len(y):
        raise ValueError('Test data must contain both classes and aligned rows')
    metadata = None
    if manifest:
        metadata = pd.read_csv(base / 'test_metadata.csv')
        if len(metadata) != len(y) or not np.array_equal(metadata['Class'].to_numpy(), y):
            raise ValueError('Test provenance is not aligned with test arrays')
    results, curves, matrices, errors, by_source = [], [], [], [], []
    for name, config in configurations.items():
        kind = config.get('kind', 'sklearn')
        if kind == 'bert':
            if not manifest:
                raise ValueError('BERT evaluation requires a complete run manifest')
            scores = np.load(base / config['test_scores'], allow_pickle=False)
            if (scores.shape != y.shape or not np.isfinite(scores).all() or
                    ((scores < 0) | (scores > 1)).any()):
                raise ValueError('BERT probabilities are invalid or not aligned with test emails')
        elif kind == 'sklearn':
            with (model_dir / config['file']).open('rb') as handle:
                model = pickle.load(handle)
            scores = positive_scores(model, X)
        else:
            raise ValueError(f'Unknown classifier artifact kind: {kind}')
        threshold = float(config['threshold'])
        metrics = classification_metrics(y, scores, threshold)
        default = classification_metrics(y, scores, 0.5)
        row = {'Model': name, **metrics, 'Threshold': threshold,
               'Precision@0.5': default['Precision'], 'Recall@0.5': default['Recall']}
        if manifest:
            row['Selected-on-validation'] = name == manifest['selected_model']
        results.append(row)
        fpr, tpr, _ = roc_curve(y, scores)
        curves.append((name, fpr, tpr, metrics['ROC-AUC']))
        predicted = (scores >= threshold).astype(int)
        matrices.append((name, confusion_matrix(y, predicted, labels=[0, 1])))
        if metadata is not None:
            wrong = np.flatnonzero(predicted != y)
            report = metadata.iloc[wrong].copy()
            report.insert(0, 'Model', name)
            report['Predicted'] = predicted[wrong]
            report['Score'] = scores[wrong]
            report['Error'] = np.where(y[wrong] == 0, 'FP', 'FN')
            errors.append(report)
            for source, indices in metadata.groupby('Source', dropna=False).groups.items():
                idx = np.asarray(list(indices), dtype=int)
                by_source.append({'Model': name, 'Source': source, 'Count': len(idx),
                                  **classification_metrics(y[idx], scores[idx], threshold)})
    result = pd.DataFrame(results)
    result.to_csv(base / 'evaluation_results.csv', index=False)
    if errors:
        pd.concat(errors, ignore_index=True).to_csv(base / 'error_analysis.csv', index=False)
        pd.DataFrame(by_source).to_csv(base / 'evaluation_by_source.csv', index=False)
    # Direct plotting preserves ROC coordinates (no seaborn aggregation).
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 7))
    for name, fpr, tpr, auc in curves:
        ax.plot(fpr, tpr, label=f'{name}: AUC={auc:.4f}')
    ax.plot([0, 1], [0, 1], '--', color='grey')
    ax.set(xlabel='False Positive Rate', ylabel='True Positive Rate')
    ax.legend(loc='lower right'); fig.tight_layout()
    fig.savefig(base / 'ROCs.png'); plt.close(fig)
    rows = math.ceil(len(matrices) / 2)
    fig, axes = plt.subplots(rows, 2, figsize=(12, 5 * rows), squeeze=False)
    for ax, (name, matrix) in zip(axes.flat, matrices):
        ax.imshow(matrix, cmap='Greens')
        for (i, j), value in np.ndenumerate(matrix):
            ax.text(j, i, str(value), ha='center', va='center',
                    color='white' if value > matrix.max() / 2 else 'black')
        ax.set(title=name, xlabel='Predicted label', ylabel='Actual label', xticks=[0, 1], yticks=[0, 1])
    for ax in list(axes.flat)[len(matrices):]:
        ax.set_visible(False)
    fig.tight_layout(); fig.savefig(base / 'confusion-matrix.png'); plt.close(fig)
    print(result.to_string(index=False))
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Evaluate baseline or specialist run without test threshold tuning')
    parser.add_argument('--run', type=Path, default=BASE_DIR)
    args = parser.parse_args()
    if (args.run / 'specialist_manifest.json').exists():
        from specialists import evaluate_specialists
        evaluate_specialists(args.run)
    else:
        evaluate(args.run)
