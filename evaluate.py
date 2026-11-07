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


def _artifact_problem(path):
    """Why a manifest artifact cannot be verified, or None if it can."""
    if not path.exists():
        return 'missing'
    with open(path, 'rb') as handle:
        if handle.read(40).startswith(b'version https://git-lfs.github.com/spec/'):
            return 'Git LFS pointer, content not downloaded (git lfs pull)'
    return None


def attachment_rule_flags(X, manifest, model_dir):
    """Per test email, the ATTACHMENT_RULES that fire, recovered from the scaled X columns.

    Rules whose feature the run lacks are skipped (obfuscated_script before 2026-11-02);
    returns None when none is available (runs before 2026-10-23).
    """
    from preprocess import ATTACHMENT_RULES
    names = manifest.get('settings', {}).get('feature_names', [])
    rules = {rule: feature for rule, feature in ATTACHMENT_RULES.items() if feature in names}
    if not rules:
        return None
    with (model_dir / 'feature_scaler.pkl').open('rb') as handle:
        scaler = pickle.load(handle)
    offset = int(manifest['settings']['doc2vec_dim'])
    values = scaler.inverse_transform(X[:, offset:].astype(np.float64))
    columns = {rule: values[:, names.index(feature)] > 0.5 for rule, feature in rules.items()}
    return pd.DataFrame(columns)


METRIC_PANELS = [('Precision', 'Precision'), ('Recall', 'Recall'), ('F1-score', 'F1-score'),
                 ('ROC-AUC', 'ROC-AUC'), ('Average-Precision', 'Average precision'),
                 ('FP', 'False positives (legitimate mail flagged)')]


def plot_model_metrics(result, path, plt):
    """One bar panel per metric, models in the same order (best test F1 on top) in every panel.

    Bars start at zero; the value is printed at each bar's end because the strong models differ
    only in the third decimal. "+ attachment rules" rows are left out (one bar per classifier).
    """
    models = result[~result['Model'].str.endswith(' + attachment rules')]
    models = models.sort_values(['F1-score', 'Recall'], ascending=False).reset_index(drop=True)
    selected = (models['Selected-on-validation'].fillna(False).astype(bool).to_numpy()
                if 'Selected-on-validation' in models else np.zeros(len(models), dtype=bool))
    colors = np.where(selected, '#2a78d6', '#b4b2ab')
    y = np.arange(len(models))
    fig, axes = plt.subplots(2, 3, figsize=(15, 0.42 * len(models) * 2 + 2.4), sharey=True)
    for ax, (column, title) in zip(axes.flat, METRIC_PANELS):
        values = models[column].astype(float).to_numpy()
        count = column == 'FP'
        top = max(float(np.nanmax(values)), 1.0) if count else 1.0
        ax.barh(y, values, height=0.6, color=colors)
        for i, value in zip(y, values):
            ax.text(value + top * 0.015, i, f'{value:,.0f}' if count else f'{value:.4f}',
                    va='center', fontsize=9, color='#52514e')
        ax.set_xlim(0, top * 1.22)
        ax.set_title(title, loc='left', fontsize=11, color='#0b0b0b')
        ax.set_xticks([])
        ax.tick_params(length=0, labelsize=10, labelcolor='#0b0b0b')
        for spine in ('top', 'right', 'bottom'):
            ax.spines[spine].set_visible(False)
        ax.spines['left'].set_color('#d4d3cd')
    axes[0, 0].set_yticks(y)
    axes[0, 0].set_yticklabels(models['Model'])
    axes[0, 0].invert_yaxis()  # shared: best model on top in every panel
    note = ('Blue: model selected on validation. ' if selected.any() else '') + \
        'Each model at its own validation-selected threshold.'
    fig.suptitle(f'Test metrics of {len(models)} models\n{note}', x=0.01, ha='left',
                 fontsize=13, color='#0b0b0b')
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor='white')
    plt.close(fig)


def evaluate(base_dir=BASE_DIR):
    base = Path(base_dir)
    model_dir = base / 'dumped_models' / 'classification'
    manifest_path = model_dir / 'run_manifest.json'
    if not model_dir.is_dir():
        raise FileNotFoundError(f'{model_dir} does not exist: train first, e.g. '
                                f'python train.py --output {base_dir}')
    manifest = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('status') != 'complete':
            raise RuntimeError('Training is incomplete; refusing to mix artifacts from different runs')
        problems = {relative: problem for relative in manifest['artifacts']
                    if (problem := _artifact_problem(base / relative))}
        if problems:
            raise RuntimeError('Cannot verify this run; artifacts unavailable: '
                               + '; '.join(f'{name} ({why})' for name, why in problems.items()))
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
    rules = attachment_rule_flags(X, manifest, model_dir) if manifest else None
    flagged = rules.any(axis=1).to_numpy() if rules is not None else None
    if rules is not None:
        summary = pd.DataFrame({'Rule': rules.columns, 'Flagged': rules.sum().to_numpy(),
                                'Positives': [int(y[rules[c].to_numpy()].sum()) for c in rules.columns]})
        summary.to_csv(base / 'attachment_rule_hits.csv', index=False)
        print(f'Attachment rules flag {int(flagged.sum())} test emails '
              f'({int(y[flagged].sum())} positive):', flush=True)
        print(summary.to_string(index=False), flush=True)
    for name, config in configurations.items():
        kind = config.get('kind', 'sklearn')
        if kind == 'bert':  # Runs before 2026-10-24 also trained BERT; it is no longer evaluated.
            print(f'Skipping {name}: BERT was removed from the pipeline', flush=True)
            continue
        if kind == 'sklearn':
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
        if flagged is not None:
            # Model OR decisive attachment rule, at the model's own validation threshold. Listed
            # only when a rule changes a decision (otherwise it duplicates the model's row).
            gated = classification_metrics(y, np.where(flagged, 1.0, scores), threshold)
            if (gated['TP'], gated['FP']) != (metrics['TP'], metrics['FP']):
                results.append({**row, 'Model': f'{name} + attachment rules', **gated,
                                'Precision@0.5': None, 'Recall@0.5': None})
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
    plot_model_metrics(result, base / 'model-metrics.png', plt)
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
