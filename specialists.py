"""Five specialists, separate inputs/targets, and explicit missing-label states."""
from pathlib import Path
import json
import pickle
import inspect

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from evaluate import classification_metrics, positive_scores, select_threshold, file_digest
from preprocess import (FEATURE_NAMES, HTML_SECURITY_FEATURE_NAMES, MESSAGE_SECURITY_FEATURE_NAMES,
                        LINK_FEATURE_NAMES, ATTACHMENT_PAYLOAD_FEATURE_NAMES,
                        group_email_variants, split_train_validation_test)

# Branch-only feature dicts stored per email by the features stage.
EXTRA_FEATURE_COLUMNS = ('_message_security', '_link_features', '_attachment_payload')


BRANCHES = {
    'text': {'algorithm': 'BERT', 'target': 'email_phishing', 'features': []},
    'header': {'algorithm': 'Gradient Boosting', 'target': 'email_phishing', 'features': [
        'from_domain_is_freemail', 'reply_to_differs_from_sender',
        'display_name_brand_freemail_mismatch', 'num_recipients',
        'subject_is_reply_or_fwd', 'from_display_name_length', *MESSAGE_SECURITY_FEATURE_NAMES]},
    'html': {'algorithm': 'MLP', 'target': 'html_malicious', 'features': [
        'has_form_tag', 'has_script_tag', 'has_hidden_elements', 'is_image_only',
        'html_to_text_ratio', *HTML_SECURITY_FEATURE_NAMES]},
    'attachment': {'algorithm': 'XGBoost', 'target': 'attachment_malicious',
                   'features': [*[n for n in FEATURE_NAMES if 'attachment' in n], *ATTACHMENT_PAYLOAD_FEATURE_NAMES]},
    'url': {'algorithm': 'SVM', 'target': 'email_phishing', 'features': [
        'num_urls', 'num_unique_domains', 'num_ip_urls', 'num_shortened_urls',
        'num_at_symbol_urls', 'num_https_urls', 'num_http_urls',
        'num_suspicious_tld_urls', 'avg_url_length', 'max_url_length', 'num_anchor_href_mismatch',
        *LINK_FEATURE_NAMES]},
}


def feature_dict(row):
    merged = {**dict(zip(FEATURE_NAMES, row['_features'])), **row['_html_features']}
    for column in EXTRA_FEATURE_COLUMNS:
        merged.update(row[column])
    return merged


def availability(row):
    values = dict(zip(FEATURE_NAMES, row['_features']))
    return {'text': bool(row['_text_available']), 'header': bool(row['_header_available']),
            'html': bool(row['_html_features']['is_html']),
            'attachment': values['num_attachments'] > 0, 'url': values['num_urls'] > 0}


def make_estimator(branch, seed=42):
    if branch == 'header':
        return GradientBoostingClassifier(n_estimators=150, max_depth=2, random_state=seed)
    if branch == 'html':
        return make_pipeline(StandardScaler(), MLPClassifier(
            hidden_layer_sizes=(64, 32), alpha=0.01, max_iter=300, random_state=seed))
    if branch == 'attachment':
        return XGBClassifier(n_estimators=300, max_depth=3, min_child_weight=3,
                             learning_rate=0.05, reg_lambda=5, subsample=0.85,
                             colsample_bytree=0.85, tree_method='hist', eval_metric='logloss',
                             random_state=seed, n_jobs=4)
    if branch == 'url':
        return make_pipeline(StandardScaler(), SVC(probability=True, class_weight='balanced',
                                                   random_state=seed, cache_size=512))
    raise ValueError(f'No tabular estimator for {branch}')


def load_branch_labels(path, data):
    """Per-email labels: any malicious HTML / any malicious attachment.

    Negative labels require all relevant content to have been reviewed.
    Unknown is blank. Email phishing labels never become malware labels.
    """
    if path is None:
        return {}
    labels = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {'RecordId', 'html_malicious', 'attachment_malicious', 'label_basis'}
    if not required.issubset(labels):
        raise ValueError(f'Branch label CSV requires columns: {sorted(required)}')
    if labels.RecordId.eq('').any() or labels.RecordId.duplicated().any():
        raise ValueError('Branch labels require unique, nonempty RecordId')
    if set(labels.RecordId) - set(data.RecordId):
        raise ValueError('Branch label RecordIds do not match selected emails')
    result = {}
    available_by_id = data.set_index('RecordId')
    for row in labels.to_dict('records'):
        entry = {}
        for target in ('html_malicious', 'attachment_malicious'):
            value = row[target].strip()
            if value:
                if value not in {'0', '1'} or not row['label_basis'].strip():
                    raise ValueError(f'Use 0/1/blank and evidence for labels: {row["RecordId"]}')
                branch = 'html' if target == 'html_malicious' else 'attachment'
                if not bool(available_by_id.loc[row['RecordId'], f'_{branch}_available']):
                    raise ValueError(f'Annotated {branch} has no applicable input: {row["RecordId"]}')
                entry[target] = int(value)
        result[row['RecordId']] = entry
    return result


def prepare_specialists(data, output, cache_dir, workers=None, target_mode='phishing', seed=42):
    from pipeline_cache import PreprocessingCache
    from train import select_label_scope
    output = Path(output)
    with PreprocessingCache(cache_dir, workers=workers) as cache:
        prepared = cache.prepare(data, 'identity', output)
        prepared = select_label_scope(prepared, target_mode, output)
        prepared = cache.prepare(prepared, 'features', output)
        preprocessing = {'signature': cache.signature, **cache.settings}
    prepared['_group'] = group_email_variants(prepared, group_attachments=True)
    matrix = np.asarray(prepared['_features'].to_list(), dtype=np.float32)
    prepared['_url_available'] = matrix[:, FEATURE_NAMES.index('num_urls')] > 0
    prepared['_attachment_available'] = matrix[:, FEATURE_NAMES.index('num_attachments')] > 0
    prepared['_html_available'] = matrix[:, FEATURE_NAMES.index('is_html')] > 0
    for name, spec in BRANCHES.items():
        if name != 'text':
            if name == 'html':
                vectors = np.fromiter((item[n] for item in prepared['_html_features'] for n in spec['features']),
                                      dtype=np.float32).reshape(len(prepared), len(spec['features']))
            else:
                # Shared FEATURE_NAMES columns first, then branch-only features, as listed in spec.
                shared = [n for n in spec['features'] if n in FEATURE_NAMES]
                extra = [n for n in spec['features'] if n not in FEATURE_NAMES]
                vectors = np.ascontiguousarray(matrix[:, [FEATURE_NAMES.index(n) for n in shared]])
                if extra:
                    rows = zip(*(prepared[column] for column in EXTRA_FEATURE_COLUMNS))
                    vectors = np.hstack([vectors, np.asarray(
                        [[merged[n] for n in extra] for merged in ({k: v for d in row for k, v in d.items()}
                                                                    for row in rows)], dtype=np.float32)])
            prepared[f'_{name}_vector'] = list(vectors)
    del matrix
    # Raw MIME stays in original dataset; retain only prepared inputs for resuming.
    prepared = prepared.drop(columns=['Text', '_group_body', '_clean_text', '_features', '_html_features',
                                      *EXTRA_FEATURE_COLUMNS, '_text_obfuscation', '_content_indicators'])
    parts = dict(zip(('train', 'validation', 'test'), split_train_validation_test(prepared, seed=seed)))
    provenance = ['RecordId', 'Source', 'Location', 'LabelKind', 'LabelBasis',
                  'OriginalLabel', 'Class', '_dedup_key', '_group']
    provenance = [n for n in provenance if n in prepared]
    all_metadata = []
    for split, frame in parts.items():
        metadata = frame[provenance].copy()
        metadata['Split'] = split
        for name in BRANCHES:
            metadata[f'{name}_available'] = frame[f'_{name}_available']
        metadata.to_csv(output / f'{split}_metadata.csv', index=False)
        all_metadata.append(metadata)
    pd.concat(all_metadata, ignore_index=True).to_csv(output / 'split_manifest.csv', index=False)
    # Local resume artifact contains email text and must remain private.
    pd.to_pickle(parts, output / 'prepared_specialists.pkl')
    template = prepared.loc[prepared._html_available | prepared._attachment_available, ['RecordId', 'Location']].copy()
    for field in ('html_malicious', 'attachment_malicious', 'label_basis'):
        template[field] = ''
    template.to_csv(output / 'specialist_labels_template.csv', index=False)
    return parts, preprocessing


def branch_inputs(frame, name):
    return frame['_semantic_text'].to_list() if name == 'text' else np.stack(frame[f'_{name}_vector'].to_list())


def train_specialists(parts, output, branch_labels=None, precision_target=0.9,
                      train_text=True, bert_model_name='google-bert/bert-base-uncased',
                      bert_epochs=3, preprocessing=None, prepare_only=False, target_mode='phishing'):
    from train import POSITIVE_LABELS
    output = Path(output)
    annotations = load_branch_labels(branch_labels, pd.concat(parts.values(), ignore_index=True))
    # Class 1 of email-level branches is POSITIVE_LABELS[target_mode]; in stage 2 Class 0 is spam.
    manifest = {'schema_version': 1, 'kind': 'five_specialists', 'status': 'incomplete',
                'target_mode': target_mode, 'positive_label': POSITIVE_LABELS[target_mode],
                'preprocessing': preprocessing, 'branches': {}, 'test_used_for_selection': False,
                'selection_note': 'BERT requested; other algorithms from prior top-five F1. '
                                  'Prior scores do not establish specialist performance.'}
    manifest_path = output / 'specialist_manifest.json'
    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    save()
    metrics, trials, by_source = [], [], []
    for name, spec in BRANCHES.items():
        config = {**spec, 'status': 'preparing', 'precision_target': precision_target,
                  'label_source': 'email phishing label' if spec['target'] == 'email_phishing' else 'reviewed branch annotations'}
        if name == 'text':
            config.update(initial_checkpoint=bert_model_name, epochs=bert_epochs,
                          text_policy='decoded subject/body; attachment text not included')
        manifest['branches'][name] = config
        selected = {}
        for split, frame in parts.items():
            available = frame.loc[frame[f'_{name}_available']].copy()
            if spec['target'] == 'email_phishing':
                available['_target'] = available.Class.astype(int)
            else:
                available['_target'] = available.RecordId.map(lambda rid: annotations.get(rid, {}).get(spec['target']))
                available = available.dropna(subset=['_target'])
            selected[split] = available
        config['labelled_rows'] = {split: len(frame) for split, frame in selected.items()}
        config['available_rows'] = {split: int(frame[f'_{name}_available'].sum()) for split, frame in parts.items()}
        if not all(set(selected[split]._target.astype(int).unique()) == {0, 1} for split in ('train', 'validation')):
            config.update(status='awaiting_labels', reason='Need both verified classes in train and validation')
            save()
            continue
        if prepare_only or (name == 'text' and not train_text):
            config.update(status='ready_to_train', reason='Training explicitly deferred')
            save()
            continue
        train_frame, val_frame = selected['train'], selected['validation']
        y_train, y_val = train_frame._target.to_numpy(dtype=int), val_frame._target.to_numpy(dtype=int)
        config['training_class_counts'] = {str(label): int((y_train == label).sum()) for label in (0, 1)}
        if name == 'text':
            from train import train_bert_classifier, BERT_BATCH_SIZE, BERT_MAX_LENGTH, BERT_STRIDE
            from preprocess import BertEmailClassifier
            model = BertEmailClassifier.from_pretrained(bert_model_name, batch_size=BERT_BATCH_SIZE,
                                                        max_length=BERT_MAX_LENGTH, stride=BERT_STRIDE)
            model.model.config.email_positive_label = POSITIVE_LABELS[target_mode]
            model, decision, bert_trials, _ = train_bert_classifier(
                model, branch_inputs(train_frame, name), y_train,
                branch_inputs(val_frame, name), y_val, output / 'text_bert', precision_target, epochs=bert_epochs)
            config['directory'] = 'text_bert'
            trials.extend({'Branch': name, **r} for r in bert_trials)
        else:
            model = make_estimator(name)
            final_estimator = model.steps[-1][1] if hasattr(model, 'steps') else model
            config['hyperparameters'] = final_estimator.get_params(deep=False)
            print(f'Training {name}: {spec["algorithm"]}, rows={len(train_frame)}, features={len(spec["features"])}', flush=True)
            weights = compute_sample_weight('balanced', y_train)
            if hasattr(model, 'steps'):
                step_name, final = model.steps[-1]
                fit_params = {f'{step_name}__sample_weight': weights} if (
                    name != 'url' and 'sample_weight' in inspect.signature(final.fit).parameters) else {}
            else:
                fit_params = {'sample_weight': weights}
            model.fit(branch_inputs(train_frame, name), y_train, **fit_params)
            decision = select_threshold(y_val, positive_scores(model, branch_inputs(val_frame, name)), precision_target)
            config['file'] = f'{name}.pkl'
            with (output / config['file']).open('wb') as handle:
                pickle.dump(model, handle)
            trials.append({'Branch': name, **decision})
        config.update(status='trained', **decision)
        for split in ('validation', 'test'):
            frame = selected[split]
            if len(frame):
                y = frame._target.to_numpy(dtype=int)
                scores = positive_scores(model, branch_inputs(frame, name))
                metrics.append({'Branch': name, 'Algorithm': spec['algorithm'], 'Target': spec['target'],
                                'Split': split, 'Rows': len(frame),
                                **classification_metrics(y, scores, config['threshold'])})
                pd.DataFrame({'RecordId': frame.RecordId.to_list(), 'Label': y, 'Score': scores}).to_csv(
                    output / f'{name}_{split}_scores.csv', index=False)
                # Per-source flag rates expose a branch that learned the corpus instead of the class.
                flagged = scores >= config['threshold']
                for source, index in frame.groupby('Source').indices.items():
                    by_source.append({'Branch': name, 'Split': split, 'Source': source, 'Rows': len(index),
                                      'Positives': int(y[index].sum()), 'Flagged': int(flagged[index].sum()),
                                      'FlaggedRate': float(flagged[index].mean())})
        save()
        if name == 'text':
            del model
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    pd.DataFrame(metrics, columns=['Branch', 'Algorithm', 'Target', 'Split', 'Rows',
        'Accuracy', 'F1-score', 'F2-score', 'Precision', 'Recall', 'ROC-AUC', 'Average-Precision',
        'FPR', 'FNR', 'TN', 'FP', 'FN', 'TP']).to_csv(output / 'specialist_evaluation.csv', index=False)
    pd.DataFrame(trials).to_csv(output / 'specialist_validation.csv', index=False)
    pd.DataFrame(by_source, columns=['Branch', 'Split', 'Source', 'Rows', 'Positives', 'Flagged', 'FlaggedRate']).to_csv(
        output / 'specialist_evaluation_by_source.csv', index=False)
    manifest['status'] = 'complete' if all(c['status'] == 'trained' for c in manifest['branches'].values()) else 'partial'
    artifacts = ['prepared_specialists.pkl', 'split_manifest.csv', 'specialist_evaluation.csv', 'specialist_validation.csv',
                 'specialist_evaluation_by_source.csv',
                 'train_metadata.csv', 'validation_metadata.csv', 'test_metadata.csv']
    for name, config in manifest['branches'].items():
        if config['status'] == 'trained':
            artifacts.extend(f'{name}_{split}_scores.csv' for split in ('validation', 'test')
                             if (output / f'{name}_{split}_scores.csv').exists())
            if 'file' in config:
                artifacts.append(config['file'])
            if 'directory' in config:
                artifacts.extend(str(p.relative_to(output)) for p in (output / config['directory']).rglob('*') if p.is_file())
    manifest['artifacts'] = {p: file_digest(output / p) for p in artifacts if (output / p).exists()}
    manifest['inference_artifacts'] = {p: digest for p, digest in manifest['artifacts'].items()
                                      if p.endswith('.pkl') and p != 'prepared_specialists.pkl'
                                      or p.startswith('text_bert')}
    if branch_labels is not None:
        import shutil
        label_copy = output / 'branch_labels_used.csv'
        if Path(branch_labels).resolve() != label_copy.resolve():
            shutil.copy2(branch_labels, label_copy)
        manifest['artifacts'][label_copy.name] = file_digest(label_copy)
    save()
    return manifest


def evaluate_specialists(output):
    """Recompute metrics from immutable, aligned scores without retuning thresholds."""
    output = Path(output)
    manifest = json.loads((output / 'specialist_manifest.json').read_text())
    if manifest['status'] not in {'complete', 'partial'}:
        raise RuntimeError('Specialist run is incomplete')
    for name, expected in manifest['artifacts'].items():
        if file_digest(output / name) != expected:
            raise RuntimeError(f'Artifact changed: {name}')
    metadata = {split: pd.read_csv(output / f'{split}_metadata.csv').set_index('RecordId')
                for split in ('validation', 'test')}
    annotations = pd.read_csv(output / 'branch_labels_used.csv').set_index('RecordId') if (
        output / 'branch_labels_used.csv').exists() else None
    results = []
    for name, config in manifest['branches'].items():
        if config['status'] != 'trained':
            continue
        for split in ('validation', 'test'):
            count = config['labelled_rows'][split]
            if not count:
                continue
            rows = pd.read_csv(output / f'{name}_{split}_scores.csv', float_precision='round_trip')
            if len(rows) != count or rows.RecordId.duplicated().any():
                raise ValueError(f'Score row accounting mismatch: {name}/{split}')
            meta = metadata[split].loc[rows.RecordId]
            y, scores = rows.Label.to_numpy(dtype=int), rows.Score.to_numpy(dtype=float)
            if not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
                raise ValueError('Invalid specialist probabilities')
            expected = meta.Class.to_numpy(dtype=int) if config['target'] == 'email_phishing' else (
                annotations.loc[rows.RecordId, config['target']].to_numpy(dtype=int))
            if not np.array_equal(y, expected) or not meta[f'{name}_available'].all():
                raise ValueError(f'Score provenance/labels mismatch: {name}/{split}')
            results.append({'Branch': name, 'Algorithm': config['algorithm'], 'Target': config['target'],
                            'Split': split, 'Rows': len(rows),
                            **classification_metrics(y, scores, config['threshold'])})
    result = pd.DataFrame(results)
    print(result.to_string(index=False) if len(result) else 'No trained specialist branches')
    return result


def run_specialists(output, dataset_dir=None, cache_dir=None, workers=None,
                    branch_labels=None, prepare_only=False, train_text=True, bert_epochs=3,
                    bert_model_name='google-bert/bert-base-uncased', resume=None, target_mode='phishing'):
    from train import load_training_emails
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Choose a new output directory; existing runs are preserved')
    output.mkdir(parents=True, exist_ok=True)
    if resume is not None:
        resume = Path(resume)
        previous = json.loads((resume / 'specialist_manifest.json').read_text())
        for name, digest in previous.get('artifacts', {}).items():
            if file_digest(resume / name) != digest:
                raise RuntimeError(f'Resume artifact changed: {name}')
        from pipeline_cache import preprocessing_signature
        current, _ = preprocessing_signature()
        if previous['preprocessing']['signature'] != current:
            raise RuntimeError('Preprocessing changed; prepare a new run before resuming')
        # Runs before the two-stage filter recorded no target mode; they were all 'phishing'.
        if previous.get('target_mode', 'phishing') != target_mode:
            raise RuntimeError(f"Resumed run was prepared for target mode {previous.get('target_mode', 'phishing')}")
        parts = pd.read_pickle(resume / 'prepared_specialists.pkl')
        preprocessing = previous['preprocessing']
        import shutil
        for path in resume.glob('*'):
            if path.is_file() and (path.name.endswith('_metadata.csv') or path.name in {
                    'split_manifest.csv', 'prepared_specialists.pkl', 'specialist_labels_template.csv',
                    'load_summary.json', 'training_dispositions.csv', 'selection_summary.json',
                    'preprocessing_identity.json', 'preprocessing_features.json', 'ingestion.sqlite'}):
                shutil.copy2(path, output / path.name)
    else:
        data = load_training_emails(output, dataset_dir=dataset_dir)
        parts, preprocessing = prepare_specialists(data, output,
            cache_dir or Path(__file__).resolve().parent / '.pipeline_cache', workers=workers,
            target_mode=target_mode)
    manifest = train_specialists(parts, output, branch_labels=branch_labels,
        prepare_only=prepare_only, train_text=train_text, bert_epochs=bert_epochs,
        bert_model_name=bert_model_name, preprocessing=preprocessing, target_mode=target_mode)
    print('Specialists:', {name: c['status'] for name, c in manifest['branches'].items()}, flush=True)
    return manifest
