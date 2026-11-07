"""Doc2Vec + email features, group-disjoint validation, threshold tuning.

Run python train.py, then python evaluate.py. Settings below are the only
configuration needed. Test scores are never used to select a model/threshold.
"""
from pathlib import Path
import json
import pickle
import platform
import warnings

import numpy as np
import pandas as pd
import sklearn
from gensim.models.doc2vec import Doc2Vec, TaggedDocument
from sklearn.base import clone
from sklearn.exceptions import ConvergenceWarning
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score
from sklearn.ensemble import (RandomForestClassifier, AdaBoostClassifier, GradientBoostingClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier

from load_data import (load_data_phishing, load_data_enron, load_data_spamassassin,
                       load_data_epvme, load_data_phishing_pot, load_data_malspam, load_data_trec07p,
                       record_dataset_root_files,
                       reset_source_stats, SOURCE_COUNTS, SOURCE_ERRORS, SOURCE_ROW_ISSUES)
from preprocess import (cleanText, remove_stopwords, tokenize_text,
                        extract_engineered_features, deduplicate_emails,
                        group_email_variants, split_train_validation_test,
                        infer_document_vector,
                        BASELINE_EXTRA_FEATURES, BASELINE_FEATURE_NAMES, baseline_feature_vector,
                        ATTACHMENT_RULES)
from evaluate import positive_scores, select_threshold, validation_rank, file_digest

BASE_DIR = Path(__file__).resolve().parent
SEED = 42
TARGET_MODE = 'phishing'  # 'broad': include known spam/mixed positives; never unknown labels.
# Two-stage filter: stage 1 = 'broad' (malicious vs legitimate); stage 2 =
# 'phishing_vs_spam', trained only on sources that name the kind. spam_or_phishing
# CSVs (TREC/CEAS/Ling/Enron.csv), raw trec07p spam and synthetic EPVME do not, so stage 2 omits them.
TARGET_MODES = ('phishing', 'broad', 'phishing_vs_spam')
STAGE2_CLASSES = {'phishing': 1, 'spam': 0}
POSITIVE_LABELS = {'phishing': 'phishing', 'broad': 'phishing/spam/unspecified-positive',
                   'phishing_vs_spam': 'phishing (negative class: spam)'}
# EPVME spoofing/XSS/signature attacks count as positives in phishing mode.
INCLUDE_SYNTHETIC_MALICIOUS = True
MIN_VALIDATION_PRECISION = 0.90  # Target on validation, not a production guarantee.
BALANCED_MODE = 0  # 1: downsample TRAIN only; validation/test keep their distribution.
TRAIN_ALL_MODELS = True  # Train all 9 classifiers; tune XGBoost, MLP and Random Forest.
RUN_ABLATION = True
# 'no_era_proxies' bỏ các feature nghi phản ánh thời đại/nguồn của email chứ không phải
# phishing: email hợp lệ trong Dataset/ đều trước 2008 (ít HTTPS, hiếm display:none).
# num_urls = http + https + URL không scheme, nên phải bỏ cả hai cột đếm theo scheme.
# Chỉ chọn cột lúc vectorize: export của --features-only vẫn đủ BASELINE_FEATURE_NAMES.
# (Hai bộ cũ no_html_presence/html_content nay là mặc định của v6 nên đã bỏ.)
ERA_PROXY_FEATURES = ('num_https_urls', 'num_http_urls', 'has_hidden_elements')
FEATURE_SETS = ('full', 'no_era_proxies')
DOC2VEC_DIM = 100
DOC2VEC_EPOCHS = 40
INFERENCE_EPOCHS = 30
# Default pipeline: Doc2Vec + engineered features, 9 classifiers, one selected on
# validation. The specialist mode (--mode specialists) has four tabular branches.


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def load_training_emails(output, dataset_dir=None, compress=False, store=None):
    """compress=True replaces each source's raw emails as soon as it is read: with a
    pipeline_cache.EmailStore they move to disk (a ~50-byte handle stays in memory), without one
    they are zlib-compressed in memory. ~4 GB of raw email did not fit the 7 GB sandbox."""
    import load_data
    from pipeline_cache import compress_texts, memory_status
    shrink = (lambda frame: compress_texts(frame, store)) if compress else (lambda frame: frame)
    from dataset_audit import DatasetAudit, record_id
    output = Path(output)
    reset_source_stats()
    dataset = Path(dataset_dir) if dataset_dir is not None else BASE_DIR / 'Dataset'
    audit = DatasetAudit(output)
    load_data.ACTIVE_AUDIT = audit
    try:
        # trec07p trước: khi có bản thô thì TREC_07.csv trong phishing/ bị loại.
        phishing, legitimate = map(shrink, load_data_trec07p(pd.DataFrame(), pd.DataFrame(), dataset / 'trec07p'))
        phishing = shrink(load_data_phishing(phishing, dataset / 'phishing'))
        phishing, legitimate = map(shrink, load_data_spamassassin(phishing, legitimate, dataset / 'spamassassin'))
        legitimate = shrink(load_data_enron(legitimate, 0, enron_dir=dataset / 'enron'))
        phishing = shrink(load_data_epvme(phishing, dataset / 'EPVME_extracted'))
        phishing = shrink(load_data_phishing_pot(phishing, dataset / 'phishing_pot'))
        phishing = shrink(load_data_malspam(phishing, dataset / 'malspam'))
        record_dataset_root_files(dataset)
    finally:
        load_data.ACTIVE_AUDIT = None
        summary = audit.finish(SOURCE_COUNTS, SOURCE_ERRORS, load_data.SOURCE_PROVENANCE)
    pd.DataFrame(SOURCE_ROW_ISSUES, columns=['file', 'record', 'ending_line', 'reason']).to_csv(
        output / 'csv_rows_quarantined.csv', index=False)
    if SOURCE_ERRORS or summary['status'] != 'complete':
        raise RuntimeError(f'Dataset read errors: {dict(SOURCE_ERRORS)}; inspect load_summary.json')
    data = pd.concat([phishing, legitimate], ignore_index=True)
    data['RecordId'] = data.Location.map(record_id)
    if len(data) != SOURCE_COUNTS['emails_loaded'] or data.RecordId.duplicated().any():
        raise RuntimeError('Loaded row accounting mismatch or duplicate source record IDs')
    if memory_status():
        print(f'Loaded {len(data)} emails; {memory_status()}', flush=True)
    return data


def raw_email_store(output):
    """Scratch EmailStore on IAP491_SCRATCH_DIR (the sandbox's Linux volume) or the run folder."""
    import os, uuid
    from pipeline_cache import EmailStore
    folder = Path(os.environ.get('IAP491_SCRATCH_DIR') or output)
    return EmailStore(folder / f'raw-emails-{uuid.uuid4().hex}.sqlite')


def select_label_scope(data, target_mode, output, include_synthetic=INCLUDE_SYNTHETIC_MALICIOUS):
    """Preserve publisher/source labels. Never infer a phishing label from text."""
    if target_mode not in TARGET_MODES:
        raise ValueError(f'TARGET_MODE must be one of {TARGET_MODES}')
    data = data.copy()
    for col, default in (('Source', 'unknown'), ('Location', ''), ('OriginalLabel', 'unknown')):
        if col not in data:
            data[col] = default
    if 'LabelKind' not in data:
        data['LabelKind'] = np.where(data.Class == 0, 'legitimate', 'positive_unspecified')
    data.groupby(['Source', 'LabelKind', 'Class'], dropna=False).size().rename('Count').reset_index().to_csv(
        output / 'source_labels.csv', index=False)
    # Check contradictory 0/1 copies BEFORE excluding unspecified positives.
    if 'RecordId' not in data:
        from dataset_audit import record_id
        data['RecordId'] = [record_id(f'{loc}:input:{i}') for i, loc in enumerate(data.Location)]
    columns = ['Source', 'Location', 'OriginalLabel', 'LabelKind', 'Class', '_dedup_key']
    outside_ids = set()
    if target_mode == 'phishing_vs_spam':
        # Relabel BEFORE dedup: the same content labelled spam and phishing is a conflict,
        # not a duplicate. Rows of other kinds get no stage-2 label and leave the scope.
        outside = data.Class.notna() & ~data.LabelKind.isin(STAGE2_CLASSES)
        data.loc[outside, [c for c in columns if c in data]].to_csv(output / 'label_scope_excluded.csv', index=False)
        outside_ids = set(data.loc[outside, 'RecordId'])
        data['Class'] = data.LabelKind.map(STAGE2_CLASSES)
    data, audit = deduplicate_emails(data, report_path=output / 'label_conflicts.csv', return_audit=True)
    # Malspam (malicious email delivering malware) is a positive in phishing mode.
    positive_kinds = {'phishing', 'malspam'} | ({'malicious_synthetic'} if include_synthetic else set())
    keep = ((data.Class == 0) | data.LabelKind.isin(positive_kinds) if target_mode == 'phishing'
            else np.ones(len(data), dtype=bool))
    if target_mode != 'phishing_vs_spam':
        data.loc[~keep, columns].to_csv(output / 'label_scope_excluded.csv', index=False)
    audit.loc[audit.RecordId.isin(data.loc[~keep, 'RecordId']) | audit.RecordId.isin(outside_ids),
              'Disposition'] = 'outside_label_scope'
    audit.to_csv(output / 'training_dispositions.csv', index=False)
    save_json(output / 'selection_summary.json', {'rows_in': len(audit),
              'dispositions': {str(k): int(v) for k, v in audit.Disposition.value_counts().items()},
              'rows_selected': int(np.sum(keep)), 'target_mode': target_mode,
              'include_synthetic_malicious': bool(include_synthetic)})
    if int(audit.Disposition.eq('selected').sum()) != int(np.sum(keep)):
        raise RuntimeError('Selection ledger does not reconcile')
    print(f'Target={target_mode}: retaining {int(np.sum(keep))}/{len(data)} unique labelled emails', flush=True)
    data = data.loc[keep].reset_index(drop=True)
    data['Class'] = data.Class.astype(int)
    if set(data.Class.unique()) != {0, 1}:
        raise ValueError('Need both legitimate and source-labelled phishing emails. Inspect source_labels.csv; do not guess labels.')
    return data


def infer_doc_vectors(model, texts):
    """Infer train/validation/test the same way; document tags never contain y."""
    vectors = []
    for i, text in enumerate(texts):
        # Hàm dùng chung với web demo; seed theo nội dung nên không phụ thuộc thứ tự.
        vectors.append(infer_document_vector(model, text, INFERENCE_EPOCHS))
        if (i + 1) % 5000 == 0:
            print(f'Inferred {i + 1}/{len(texts)} documents', flush=True)
    return np.asarray(vectors, dtype=np.float32)


def prepare_data(data, output, target_mode=TARGET_MODE, seed=SEED, epochs=DOC2VEC_EPOCHS,
                 balanced_mode=BALANCED_MODE, cache_dir=None, workers=None, feature_set='full'):
    frames, preprocessing = prepare_features(data, output, target_mode, seed, balanced_mode, cache_dir, workers)
    return vectorize(frames, preprocessing, epochs=epochs, seed=seed, feature_set=feature_set)


def prepare_features(data, output, target_mode=TARGET_MODE, seed=SEED, balanced_mode=BALANCED_MODE,
                     cache_dir=None, workers=None):
    """Raw email -> train/validation/test frames of metadata, clean text and baseline vectors.

    This is the only stage that parses (possibly malicious) email; vectorize() and the
    classifiers work on its output alone, so they can run outside the sandbox.
    """
    from pipeline_cache import PreprocessingCache
    with PreprocessingCache(cache_dir or BASE_DIR / '.pipeline_cache', workers=workers) as cache:
        data = cache.prepare(data, 'identity', output)
        data = select_label_scope(data, target_mode, output)
        # Thu gọn từng email ngay khi tính xong: chỉ giữ text sạch và vector baseline float32
        # (BASELINE_FEATURE_NAMES). Giữ đủ các dict feature của ~400k email vượt RAM sandbox.
        def compact(result):
            return {'_clean_text': result['_clean_text'],
                    '_features': np.asarray(baseline_feature_vector(result), dtype=np.float32)}
        data = cache.prepare(data, 'features', output, transform=compact)
        # Email thô không còn cần sau khi trích feature/văn bản; giải phóng trước bước nhóm.
        # Bước nhóm dùng hash + SimHash của stage identity, không parse lại Text.
        data['Text'] = data['_clean_text']
        # Ghi chữ ký tiền xử lý để web demo kiểm tra đúng code/stopwords/lemmatization.
        preprocessing = {'signature': cache.signature,
                         'lemmatization': cache.settings['lemmatization'],
                         'stopwords': cache.settings['stopwords']}
    print('Grouping near duplicates...', flush=True)
    data['_group'] = group_email_variants(data)
    data = data.drop(columns=['_group_key', '_simhash'])
    train, validation, test = split_train_validation_test(data, seed=seed)
    # Persist provenance without email bodies, aligned with each output array.
    columns = ['RecordId', 'Source', 'Location', 'LabelKind', 'LabelBasis', 'OriginalLabel', 'Class', '_dedup_key', '_group']
    columns = [col for col in columns if col in data]
    frames = {'train': train, 'validation': validation, 'test': test}
    manifest = pd.concat([frame[columns].assign(Split=name) for name, frame in frames.items()], ignore_index=True)
    manifest.to_csv(output / 'split_manifest.csv', index=False)
    if balanced_mode == 1:
        count = int(train.Class.value_counts().min())
        frames['train'] = pd.concat([part.sample(n=count, random_state=seed)
                                    for _, part in train.groupby('Class')]).sort_index()
    elif balanced_mode != 0:
        raise ValueError('BALANCED_MODE must be 0 or 1')
    for name, frame in frames.items():
        print(f'{name}: {frame.Class.value_counts().to_dict()}; extracting complete email features', flush=True)
        frame = frame.copy()
        frame[columns].to_csv(output / f'{name}_metadata.csv', index=False)
        frame['Features'] = frame['_features'].map(lambda value: np.asarray(value, dtype=np.float32))
        frame['Text'] = frame['_clean_text']
        frames[name] = frame[[*columns, 'Text', 'Features']]
    return frames, preprocessing


def feature_columns(feature_set='full'):
    """Tên và vị trí (trong BASELINE_FEATURE_NAMES) của các cột feature kỹ thuật được giữ."""
    if feature_set not in FEATURE_SETS:
        raise ValueError(f'Unknown feature set: {feature_set}')
    dropped = ERA_PROXY_FEATURES if feature_set == 'no_era_proxies' else ()
    kept = [name for name in BASELINE_FEATURE_NAMES if name not in dropped]
    return kept, [BASELINE_FEATURE_NAMES.index(name) for name in kept]


def vectorize(frames, preprocessing, epochs=DOC2VEC_EPOCHS, seed=SEED, feature_set='full'):
    """Doc2Vec (fit on train only) + scaled baseline features -> (X, y) per split."""
    kept, positions = feature_columns(feature_set)
    lemmatize = preprocessing['lemmatization']  # False since nltk was removed
    train = frames['train']
    tagged = [TaggedDocument(words=tokenize_text(text) or ['emptyemailtoken'], tags=[int(i)])
              for i, text in enumerate(train.Text)]
    model = Doc2Vec(vector_size=DOC2VEC_DIM, dm=0, min_count=2, epochs=epochs,
                    alpha=0.025, min_alpha=0.0005, seed=seed, workers=1)
    model.build_vocab(tagged)  # TRAIN ONLY, with one distinct tag per training email.
    if not len(model.wv):
        raise ValueError('Training vocabulary is empty; inspect decoded text and min_count')
    print(f'Training Doc2Vec: {len(tagged)} unique document tags, {epochs} epochs', flush=True)
    model.train(tagged, total_examples=len(tagged), epochs=epochs,
                start_alpha=0.025, end_alpha=0.0005)
    assert len(model.dv) == len(tagged)
    scaler = StandardScaler()
    numerical = np.stack(train.Features.to_list())[:, positions]
    scaler.fit(numerical)  # TRAIN ONLY
    arrays = {}
    for name, frame in frames.items():
        doc = infer_doc_vectors(model, frame.Text.to_list())
        features = scaler.transform(np.stack(frame.Features.to_list())[:, positions]).astype(np.float32)
        X = np.hstack([doc, features])
        y = frame.Class.to_numpy(dtype=np.int64)
        if not np.isfinite(X).all():
            raise ValueError(f'Non-finite features in {name}')
        arrays[name] = (X, y)
    return arrays, model, scaler, {'lemmatization': lemmatize, 'doc2vec_dim': DOC2VEC_DIM,
        'epochs': epochs, 'inference_epochs': INFERENCE_EPOCHS, 'feature_names': kept,
        'feature_set': feature_set, 'attachment_rules': dict(ATTACHMENT_RULES),
        'preprocessing': preprocessing,
        'split_counts': {name: {str(k): int(v) for k, v in frame.Class.value_counts().items()}
                         for name, frame in frames.items()}}


FEATURE_EXPORT = 'features_manifest.json'
# Files the host copies from a feature folder into each model run (evaluate.py and audits use them).
FEATURE_PROVENANCE = ('split_manifest.csv', 'train_metadata.csv', 'validation_metadata.csv', 'test_metadata.csv',
                      'load_summary.json', 'selection_summary.json', 'source_labels.csv', 'label_conflicts.csv',
                      'label_scope_excluded.csv', 'training_dispositions.csv', 'csv_rows_quarantined.csv',
                      'preprocessing_identity.json', 'preprocessing_features.json')


def export_features(frames, preprocessing, output, target_mode, seed=SEED):
    """Write prepare_features() output in formats that cannot run code when read: .npy without
    pickle, JSON-lines text, CSV metadata. The sandbox writes them; the host trains from them."""
    import gzip
    output = Path(output)
    files = {}
    for name, frame in frames.items():
        np.save(output / f'features_{name}.npy', np.stack(frame.Features.to_list()).astype(np.float32),
                allow_pickle=False)
        np.save(output / f'labels_{name}.npy', frame.Class.to_numpy(dtype=np.int64), allow_pickle=False)
        with gzip.open(output / f'text_{name}.jsonl.gz', 'wt', encoding='utf-8') as handle:
            for text in frame.Text:
                handle.write(json.dumps(text, ensure_ascii=False) + '\n')
        files.update({f'features_{name}.npy': None, f'labels_{name}.npy': None, f'text_{name}.jsonl.gz': None,
                      f'{name}_metadata.csv': None})
    manifest = {'kind': 'baseline_features', 'schema': 1, 'target_mode': target_mode, 'seed': seed,
                'preprocessing': preprocessing, 'feature_names': list(BASELINE_FEATURE_NAMES),
                'attachment_rules': dict(ATTACHMENT_RULES),
                'split_counts': {name: {str(k): int(v) for k, v in frame.Class.value_counts().items()}
                                 for name, frame in frames.items()},
                'files': {name: file_digest(output / name) for name in files}}
    save_json(output / FEATURE_EXPORT, manifest)
    print(f'Features exported to {output}; train with: python train.py --from-features {output} --output <run>',
          flush=True)
    return manifest


def load_exported_features(folder):
    """Read export_features() output after checking every file's SHA-256. Nothing is unpickled."""
    import gzip
    folder = Path(folder)
    manifest = json.loads((folder / FEATURE_EXPORT).read_text(encoding='utf-8'))
    if manifest.get('kind') != 'baseline_features' or manifest.get('schema') != 1:
        raise ValueError(f'{folder} is not a baseline feature export')
    for name, expected in manifest['files'].items():
        if file_digest(folder / name) != expected:
            raise RuntimeError(f'Feature export changed after it was written: {name}')
    if manifest['feature_names'] != list(BASELINE_FEATURE_NAMES):
        raise ValueError('Exported feature names differ from this code; re-extract the features')
    frames = {}
    for name in ('train', 'validation', 'test'):
        frame = pd.read_csv(folder / f'{name}_metadata.csv')
        features = np.load(folder / f'features_{name}.npy', allow_pickle=False)
        labels = np.load(folder / f'labels_{name}.npy', allow_pickle=False)
        with gzip.open(folder / f'text_{name}.jsonl.gz', 'rt', encoding='utf-8') as handle:
            texts = [json.loads(line) for line in handle]
        if not (len(frame) == len(features) == len(labels) == len(texts)) or not np.array_equal(
                frame.Class.to_numpy(), labels):
            raise ValueError(f'Feature export split {name} is not aligned')
        if features.shape[1] != len(BASELINE_FEATURE_NAMES) or not np.isfinite(features).all():
            raise ValueError(f'Feature export split {name} has invalid vectors')
        frame['Text'] = texts
        frame['Features'] = list(features)
        frames[name] = frame
    return frames, manifest


def build_candidates(y_train, seed=SEED, all_models=TRAIN_ALL_MODELS):
    ratio = float(np.sum(y_train == 0) / max(1, np.sum(y_train == 1)))
    weights = sorted(set([1.0, float(np.sqrt(ratio)), ratio]))
    candidates = {
        'XGBoost': [XGBClassifier(n_estimators=400, learning_rate=0.05, max_depth=depth,
                        min_child_weight=3, reg_lambda=5, reg_alpha=0.1, subsample=0.85,
                        colsample_bytree=0.85, scale_pos_weight=weight, tree_method='hist',
                        eval_metric='logloss', random_state=seed, n_jobs=4)
                    for depth in (3, 5) for weight in weights],
        'Random Forest': [RandomForestClassifier(n_estimators=300, min_samples_leaf=leaf,
                            max_features='sqrt', class_weight='balanced_subsample',
                            random_state=seed, n_jobs=4) for leaf in (2, 5)],
        'MLP': [MLPClassifier(hidden_layer_sizes=widths, alpha=alpha, max_iter=300,
                    early_stopping=False, random_state=seed)
                for widths, alpha in (((128, 64), 0.001), ((128,), 0.01))],
    }
    if all_models:
        candidates.update({
            'Logistic Regression': [LogisticRegression(max_iter=2000, class_weight='balanced', random_state=seed)],
            'SVM': [SVC(probability=True, class_weight='balanced', random_state=seed)],
            'KNN': [KNeighborsClassifier(n_neighbors=min(5, len(y_train)))],
            'Decision Tree': [DecisionTreeClassifier(min_samples_leaf=5, class_weight='balanced', random_state=seed)],
            'AdaBoost': [AdaBoostClassifier(random_state=seed)],
            'Gradient Boosting': [GradientBoostingClassifier(random_state=seed)]})
    return candidates


def tune_classifiers(X_train, y_train, X_validation, y_validation, candidates,
                     precision_target=MIN_VALIDATION_PRECISION):
    winners, records = {}, []
    for name, options in candidates.items():
        best = None
        for index, estimator in enumerate(options):
            print(f'Fitting {name} candidate {index + 1}/{len(options)}', flush=True)
            model = clone(estimator)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always', ConvergenceWarning)
                model.fit(X_train, y_train)
            convergence = [str(w.message) for w in caught if issubclass(w.category, ConvergenceWarning)]
            for warning in caught:
                print(f'  {warning.category.__name__}: {warning.message}', flush=True)
            scores = positive_scores(model, X_validation)
            decision = select_threshold(y_validation, scores, precision_target)
            decision['average_precision'] = float(average_precision_score(y_validation, scores))
            decision['convergence_warning'] = bool(convergence)
            trial = {'Model': name, 'candidate': index, **decision,
                     'convergence_warning': bool(convergence)}
            records.append(trial)
            if best is None or validation_rank(decision) > validation_rank(best[1]):
                best = model, decision, index
        model, decision, index = best
        model.decision_threshold_ = decision['threshold']
        winners[name] = (model, {**decision, 'candidate': index})
    if not winners:
        raise ValueError('At least one classifier candidate is required')
    return winners, records


def feature_ablation(winners, arrays, precision_target):
    """Matched XGBoost settings; diagnostics on validation only, no test tuning."""
    if 'XGBoost' not in winners:
        return []
    best, combined = winners['XGBoost']
    X_train, y_train = arrays['train']; X_val, y_val = arrays['validation']
    rows = [{'Representation': 'combined', **combined}]
    for name, selection in (('doc2vec_only', slice(0, DOC2VEC_DIM)),
                            ('engineered_only', slice(DOC2VEC_DIM, None))):
        print(f'Validation ablation: {name}', flush=True)
        model = clone(best)
        model.fit(X_train[:, selection], y_train)
        scores = positive_scores(model, X_val[:, selection])
        decision = select_threshold(y_val, scores, precision_target)
        decision['average_precision'] = float(average_precision_score(y_val, scores))
        rows.append({'Representation': name, **decision})
    return rows


def training(data=None, output_dir=BASE_DIR, candidates=None, epochs=DOC2VEC_EPOCHS,
             target_mode=TARGET_MODE, precision_target=MIN_VALIDATION_PRECISION,
             run_ablation=RUN_ABLATION, cache_dir=None, workers=None, features_only=False, from_features=None,
             feature_set='full'):
    """features_only: parse email and export features (the sandbox stage), no training.
    from_features: train from such an export, never touching raw email (the host stage)."""
    feature_columns(feature_set)  # Báo sai tên bộ feature trước khi đọc dữ liệu hàng giờ.
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    if from_features is not None:
        frames, exported = load_exported_features(from_features)
        if exported['target_mode'] != target_mode:
            raise ValueError(f"Features were extracted for target mode {exported['target_mode']}, not {target_mode}")
        import shutil
        for name in FEATURE_PROVENANCE:
            if (Path(from_features) / name).exists():
                shutil.copy2(Path(from_features) / name, output / name)
        preprocessing = exported['preprocessing']
    else:
        store = raw_email_store(output)
        try:
            if data is None:
                data = load_training_emails(output, compress=True, store=store)
            # Không giữ tham chiếu tới DataFrame email thô ở đây: prepare_features chỉ giữ lại một phần
            # số dòng, còn bản đầy đủ (~5 GB với toàn bộ Dataset) sẽ nằm trong RAM suốt quá trình.
            source = [data]
            del data
            frames, preprocessing = prepare_features(source.pop(), output, target_mode,
                                                     cache_dir=cache_dir, workers=workers)
        finally:
            store.close()  # raw emails are no longer needed once features are extracted
        if features_only:
            return export_features(frames, preprocessing, output, target_mode)
    model_dir = output / 'dumped_models' / 'classification'; model_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = model_dir / 'run_manifest.json'
    save_json(manifest_path, {'status': 'incomplete'})  # Interrupted runs cannot be evaluated as complete.
    arrays, doc2vec, scaler, settings = vectorize(frames, preprocessing, epochs=epochs, feature_set=feature_set)
    del frames
    if from_features is not None:
        settings['features_from'] = str(from_features)
    X_train, y_train = arrays['train']; X_val, y_val = arrays['validation']
    if candidates is None:
        candidates = build_candidates(y_train)
    winners, trials = tune_classifiers(X_train, y_train, X_val, y_val, candidates, precision_target)
    decisions = {name: decision for name, (_, decision) in winners.items()}
    pd.DataFrame(trials).to_csv(output / 'validation_results.csv', index=False)
    selected_name = max(decisions, key=lambda name: validation_rank(decisions[name]))
    if not decisions[selected_name]['precision_target_met']:
        print('Validation precision target was NOT met. Using the best validation F2 fallback; '
              'inspect validation_results.csv before deployment.', flush=True)
    ablations = feature_ablation(winners, arrays, precision_target) if run_ablation else []
    pd.DataFrame(ablations).to_csv(output / 'ablation_validation.csv', index=False)
    artifacts = []
    for name in ('validation', 'test'):
        X, y = arrays[name]
        for prefix, value in (('X', X), ('y', y)):
            path = output / f'data_{prefix}_{name}.npy'; np.save(path, value); artifacts.append(path)
        artifacts.append(output / f'{name}_metadata.csv')
    for filename, model in (('model_dbow.pkl', doc2vec), ('feature_scaler.pkl', scaler)):
        path = model_dir / filename
        with path.open('wb') as handle:
            pickle.dump(model, handle)
        artifacts.append(path)
    configurations = {}
    for name, (model, decision) in winners.items():
        path = model_dir / f'{name}.pkl'
        with path.open('wb') as handle:
            pickle.dump(model, handle)
        artifacts.append(path)
        configurations[name] = {'file': path.name, **decision}
    parameters = {name: model.get_params(deep=False) for name, (model, _) in winners.items()}
    save_json(output / 'selected_parameters.json', parameters)
    manifest = {'status': 'complete', 'schema_version': 2, 'target_mode': target_mode,
                'positive_label': POSITIVE_LABELS[target_mode],
                'selected_model': selected_name, 'models': configurations, 'settings': settings,
                'seed': SEED, 'python': platform.python_version(), 'sklearn': sklearn.__version__,
                'test_used_for_selection': False,
                'artifacts': {path.relative_to(output).as_posix(): file_digest(path) for path in artifacts}}
    save_json(manifest_path, manifest)
    print(f'Selected on validation: {selected_name}. Test metrics have not been computed. Run python evaluate.py.', flush=True)
    return manifest


if __name__ == '__main__':
    import argparse
    from datetime import datetime
    from zoneinfo import ZoneInfo
    parser = argparse.ArgumentParser(description='Audited email pipeline: Doc2Vec + 9 classifiers, one selected '
                                     'on validation (default), or four specialist branches')
    parser.add_argument('--mode', choices=('specialists', 'baseline'), default='baseline')
    parser.add_argument('--target-mode', choices=TARGET_MODES, default=TARGET_MODE,
                        help="Two-stage filter: 'broad' trains stage 1, 'phishing_vs_spam' stage 2")
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dataset-dir', type=Path)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--workers', type=int, default=None)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--audit-only', action='store_true', help='Stream every dataset record and verify ingestion accounting')
    parser.add_argument('--branch-labels', type=Path)
    parser.add_argument('--resume', type=Path, help='Resume prepared data into a new output directory')
    parser.add_argument('--features-only', action='store_true',
                        help='Baseline: parse email and export features only (run inside the sandbox)')
    parser.add_argument('--from-features', type=Path,
                        help='Baseline: train from a --features-only export, without reading raw email')
    parser.add_argument('--feature-set', choices=FEATURE_SETS, default='full',
                        help="Baseline only: 'no_era_proxies' drops URL scheme counts and has_hidden_elements")
    args = parser.parse_args()
    output = args.output or BASE_DIR / 'runs' / datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%d_%H%M%S_%f')
    if args.audit_only:
        from load_data import audit_dataset
        summary = audit_dataset(args.dataset_dir or BASE_DIR / 'Dataset', output)
        print('Audit:', summary['status'], '; emails loaded:', summary['counts'].get('emails_loaded', 0))
    elif args.mode == 'specialists':
        if args.feature_set != 'full' or args.features_only or args.from_features:
            parser.error('--feature-set/--features-only/--from-features apply to baseline mode')
        from specialists import run_specialists
        run_specialists(output, dataset_dir=args.dataset_dir, cache_dir=args.cache_dir, target_mode=args.target_mode,
                        workers=args.workers, branch_labels=args.branch_labels,
                        prepare_only=args.prepare_only, resume=args.resume)
    else:
        if args.prepare_only or args.resume or args.branch_labels or args.dataset_dir:
            parser.error('Preparation/resume/dataset options apply to specialist mode')
        if args.features_only and args.from_features:
            parser.error('--features-only and --from-features are the two separate stages')
        if args.features_only and args.feature_set != 'full':
            parser.error('--feature-set applies when training; --features-only exports every feature')
        if output.exists() and any(output.iterdir()):
            parser.error('Choose a new output directory')
        training(output_dir=output, target_mode=args.target_mode, cache_dir=args.cache_dir, workers=args.workers,
                 features_only=args.features_only, from_features=args.from_features,
                 feature_set=args.feature_set)
