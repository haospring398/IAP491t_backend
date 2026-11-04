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
from nltk.stem import WordNetLemmatizer
from sklearn.base import clone
from sklearn.exceptions import ConvergenceWarning
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score
from sklearn.ensemble import (RandomForestClassifier, AdaBoostClassifier, GradientBoostingClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.tree import DecisionTreeClassifier
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier

from load_data import (load_data_phishing, load_data_enron, load_data_spamassassin,
                       load_data_epvme, load_data_phishing_pot, load_data_trec07p, record_dataset_root_files,
                       reset_source_stats, SOURCE_COUNTS, SOURCE_ERRORS, SOURCE_ROW_ISSUES)
from preprocess import (FEATURE_NAMES, HTML_SECURITY_FEATURE_NAMES, cleanText, remove_stopwords, tokenize_text,
                        extract_engineered_features, deduplicate_emails,
                        group_email_variants, split_train_validation_test,
                        prepare_semantic_text, BertEmailClassifier, infer_document_vector)
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
TRAIN_ALL_MODELS = True  # Train all 10 classifiers; tune XGBoost, MLP and Random Forest.
RUN_ABLATION = True
# Bộ feature kỹ thuật cho thí nghiệm thiên lệch is_html (chỉ chọn cột từ cache, không đổi
# chữ ký tiền xử lý). html_to_text_ratio bằng 0 đúng khi email không có HTML, nên bỏ cùng
# is_html; nếu không model vẫn suy ra được is_html. 'html_content' thêm các số đo nội dung
# HTML (script, iframe, ô mật khẩu, event handler...) đã có sẵn trong cache.
HTML_PRESENCE_FEATURES = ('is_html', 'html_to_text_ratio')
# 'no_era_proxies' bỏ thêm feature nghi phản ánh thời đại/nguồn của email chứ không phải
# phishing: email hợp lệ trong Dataset/ đều trước 2008 (ít HTTPS, hiếm display:none).
# num_urls = http + https + URL không scheme, nên phải bỏ cả hai cột đếm theo scheme.
ERA_PROXY_FEATURES = ('num_https_urls', 'num_http_urls', 'has_hidden_elements')
FEATURE_SETS = ('full', 'no_html_presence', 'html_content', 'no_era_proxies')
DOC2VEC_DIM = 100
DOC2VEC_EPOCHS = 40
INFERENCE_EPOCHS = 30
TRAIN_BERT = True
BERT_MODEL_NAME = 'google-bert/bert-base-uncased'
BERT_EPOCHS = 3
BERT_BATCH_SIZE = 2
BERT_MAX_LENGTH = 256
BERT_STRIDE = 64
BERT_GRAD_ACCUMULATION = 8
BERT_LEARNING_RATE = 2e-5


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def load_training_emails(output, dataset_dir=None):
    import load_data
    from dataset_audit import DatasetAudit, record_id
    output = Path(output)
    reset_source_stats()
    dataset = Path(dataset_dir) if dataset_dir is not None else BASE_DIR / 'Dataset'
    audit = DatasetAudit(output)
    load_data.ACTIVE_AUDIT = audit
    try:
        # trec07p trước: khi có bản thô thì TREC_07.csv trong phishing/ bị loại.
        phishing, legitimate = load_data_trec07p(pd.DataFrame(), pd.DataFrame(), dataset / 'trec07p')
        phishing = load_data_phishing(phishing, dataset / 'phishing')
        phishing, legitimate = load_data_spamassassin(phishing, legitimate, dataset / 'spamassassin')
        legitimate = load_data_enron(legitimate, 0, enron_dir=dataset / 'enron')
        phishing = load_data_epvme(phishing, dataset / 'EPVME_extracted')
        phishing = load_data_phishing_pot(phishing, dataset / 'phishing_pot')
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
    return data


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
    positive_kinds = {'phishing', 'malicious_synthetic'} if include_synthetic else {'phishing'}
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


def feature_columns(feature_set='full'):
    """Tên feature kỹ thuật theo đúng thứ tự cột: phần lấy từ FEATURE_NAMES, rồi phần thêm."""
    if feature_set not in FEATURE_SETS:
        raise ValueError(f'Unknown feature set: {feature_set}')
    if feature_set == 'full':
        return list(FEATURE_NAMES), []
    dropped = HTML_PRESENCE_FEATURES + (ERA_PROXY_FEATURES if feature_set == 'no_era_proxies' else ())
    kept = [name for name in FEATURE_NAMES if name not in dropped]
    return kept, list(HTML_SECURITY_FEATURE_NAMES) if feature_set == 'html_content' else []


def prepare_data(data, output, target_mode=TARGET_MODE, seed=SEED, epochs=DOC2VEC_EPOCHS,
                 balanced_mode=BALANCED_MODE, semantic_data=None, cache_dir=None, workers=None,
                 feature_set='full'):
    kept, extra = feature_columns(feature_set)
    from pipeline_cache import PreprocessingCache
    with PreprocessingCache(cache_dir or BASE_DIR / '.pipeline_cache', workers=workers) as cache:
        data = cache.prepare(data, 'identity', output)
        data = select_label_scope(data, target_mode, output)
        if semantic_data is None:
            # Văn bản cho BERT không cần khi không train BERT; bỏ sớm để giảm RAM (~1 GB).
            data = data.drop(columns='_semantic_text')
        data = cache.prepare(data, 'features', output)
        # Email thô không còn cần sau khi trích feature/văn bản; giải phóng trước bước nhóm.
        data['Text'] = data['_clean_text']
        if feature_set != 'full':
            positions = [FEATURE_NAMES.index(name) for name in kept]
            data['_features'] = [[values[i] for i in positions] + [float(html[name]) for name in extra]
                                 for values, html in zip(data['_features'], data['_html_features'])]
        # Dict feature chỉ dành cho nhánh specialist hoặc làm bằng chứng; baseline không dùng.
        data = data.drop(columns=[c for c in ('_html_features', '_message_security', '_text_obfuscation',
                                              '_link_features', '_attachment_payload', '_content_indicators')
                                  if c in data])
        # Ghi chữ ký tiền xử lý để web demo kiểm tra đúng code/stopwords/lemmatization.
        preprocessing = {'signature': cache.signature,
                         'lemmatization': cache.settings['lemmatization'],
                         'stopwords': cache.settings['stopwords']}
    print('Grouping near duplicates...', flush=True)
    data['_group'] = group_email_variants(data)
    data = data.drop(columns='_group_body')
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
    lemmatizer = WordNetLemmatizer()
    try:
        lemmatizer.lemmatize('running', pos='v')
        lemmatize = True
    except LookupError:
        lemmatize = False
    for name, frame in frames.items():
        print(f'{name}: {frame.Class.value_counts().to_dict()}; extracting complete email features', flush=True)
        frame = frame.copy()
        frame[columns].to_csv(output / f'{name}_metadata.csv', index=False)
        if semantic_data is not None:
            semantic_data[name] = frame['_semantic_text'].to_list()
        frame['Features'] = frame['_features'].map(lambda value: np.asarray(value, dtype=np.float32))
        frame['Text'] = frame['_clean_text']
        frames[name] = frame
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
    numerical = np.stack(train.Features.to_list())
    scaler.fit(numerical)  # TRAIN ONLY
    arrays = {}
    for name, frame in frames.items():
        doc = infer_doc_vectors(model, frame.Text.to_list())
        features = scaler.transform(np.stack(frame.Features.to_list())).astype(np.float32)
        X = np.hstack([doc, features])
        y = frame.Class.to_numpy(dtype=np.int64)
        if not np.isfinite(X).all():
            raise ValueError(f'Non-finite features in {name}')
        arrays[name] = (X, y)
    return arrays, model, scaler, {'lemmatization': lemmatize, 'doc2vec_dim': DOC2VEC_DIM,
        'epochs': epochs, 'inference_epochs': INFERENCE_EPOCHS, 'feature_names': kept + extra,
        'feature_set': feature_set, 'preprocessing': preprocessing,
        'split_counts': {name: {str(k): int(v) for k, v in frame.Class.value_counts().items()}
                         for name, frame in frames.items()}}


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
            'Naive Bayes': [GaussianNB()],
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



def train_bert_classifier(bert, texts, labels, validation_texts, validation_labels,
                          checkpoint, precision_target, epochs=BERT_EPOCHS):
    """Train on train windows only; choose epoch/threshold on whole validation emails."""
    import math
    import torch
    from contextlib import nullcontext
    from transformers import get_linear_schedule_with_warmup
    if epochs < 1:
        raise ValueError("BERT epochs must be positive")
    if len(texts) != len(labels) or not len(texts) or set(np.unique(labels)) != {0, 1}:
        raise ValueError("BERT training needs aligned email text and labels from both classes")
    if len(validation_texts) != len(validation_labels):
        raise ValueError("BERT validation text and labels are not aligned")
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)

    class WindowDataset(torch.utils.data.Dataset):
        def __init__(self):
            self.tokens, owners, weights = [], [], []
            for owner, text in enumerate(texts):
                windows = bert.encode_windows(text)
                for window in windows:
                    self.tokens.append(np.asarray(window["input_ids"], dtype=np.int32))
                    owners.append(owner)
                    weights.append(1.0 / len(windows))
                if (owner + 1) % 5000 == 0:
                    print(f'BERT tokenized {owner + 1}/{len(texts)} train emails', flush=True)
            self.owners = np.asarray(owners, dtype=np.int64)
            # Equal total contribution per email, even when it has many windows.
            self.weights = np.asarray(weights, dtype=np.float32) * len(owners) / len(texts)
        def __len__(self):
            return len(self.tokens)
        def __getitem__(self, index):
            ids = self.tokens[index].tolist()
            return ({"input_ids": ids, "attention_mask": [1] * len(ids),
                     "token_type_ids": [0] * len(ids)},
                    int(labels[self.owners[index]]), float(self.weights[index]))

    def collate(rows):
        inputs, targets, weights = zip(*rows)
        padded = bert.tokenizer.pad(list(inputs), padding=True, return_tensors="pt")
        return padded, torch.tensor(targets, dtype=torch.long), torch.tensor(weights, dtype=torch.float32)

    dataset = WindowDataset()
    generator = torch.Generator().manual_seed(SEED)
    loader = torch.utils.data.DataLoader(dataset, batch_size=bert.batch_size,
        shuffle=True, collate_fn=collate, num_workers=0, generator=generator)
    counts = np.bincount(np.asarray(labels, dtype=int), minlength=2)
    if not len(texts) or (counts == 0).any():
        raise ValueError("BERT training requires both labelled classes")
    class_weights = torch.tensor(len(labels) / (2.0 * counts), dtype=torch.float32, device=bert.device)
    optimizer = torch.optim.AdamW(bert.model.parameters(), lr=BERT_LEARNING_RATE, weight_decay=0.01)
    updates = math.ceil(len(loader) / BERT_GRAD_ACCUMULATION) * epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, int(updates * 0.1), updates)
    use_amp = bert.device.type == "cuda"
    amp_scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    bert.model.gradient_checkpointing_enable()
    best, best_scores, trials = None, None, []
    print(f'BERT: {len(texts)} emails, {len(dataset)} train windows, device={bert.device}', flush=True)
    for epoch in range(epochs):
        bert.model.train()
        optimizer.zero_grad(set_to_none=True)
        running_loss = 0.0
        for step, (inputs, targets, weights) in enumerate(loader):
            inputs = {key: value.to(bert.device) for key, value in inputs.items()}
            targets, weights = targets.to(bert.device), weights.to(bert.device)
            group_size = min(BERT_GRAD_ACCUMULATION,
                             len(loader) - (step // BERT_GRAD_ACCUMULATION) * BERT_GRAD_ACCUMULATION)
            context = torch.autocast(device_type="cuda", dtype=torch.float16) if use_amp else nullcontext()
            with context:
                logits = bert.model(**inputs).logits
                losses = torch.nn.functional.cross_entropy(
                    logits.float(), targets, weight=class_weights, reduction="none")
                loss = (losses * weights).mean()
            if not torch.isfinite(loss):
                raise RuntimeError("Non-finite BERT loss; training stopped")
            running_loss += float(loss.detach())
            amp_scaler.scale(loss / group_size).backward()
            if (step + 1) % BERT_GRAD_ACCUMULATION == 0 or step + 1 == len(loader):
                amp_scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(bert.model.parameters(), 1.0)
                previous_scale = amp_scaler.get_scale()
                amp_scaler.step(optimizer)
                amp_scaler.update()
                if amp_scaler.get_scale() >= previous_scale:
                    scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            if (step + 1) % 100 == 0:
                print(f'BERT epoch {epoch + 1}/{epochs}, batch {step + 1}/{len(loader)}, '
                      f'loss={running_loss / (step + 1):.4f}', flush=True)
        scores = positive_scores(bert, validation_texts)
        decision = select_threshold(validation_labels, scores, precision_target)
        decision.update(average_precision=float(average_precision_score(validation_labels, scores)),
                        epoch=epoch + 1, candidate=epoch, convergence_warning=False)
        trials.append({"Model": "BERT", **decision})
        print(f'BERT epoch {epoch + 1}: validation precision={decision["precision"]:.4f}, '
              f'recall={decision["recall"]:.4f}', flush=True)
        if best is None or validation_rank(decision) > validation_rank(best):
            best, best_scores = decision, scores.copy()
            bert.decision_threshold_ = decision["threshold"]
            bert.save_pretrained(checkpoint)
    device = str(bert.device)
    bert.model.to("cpu")
    del optimizer, scheduler, amp_scaler, dataset, loader
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    best_model = BertEmailClassifier.from_pretrained(checkpoint, device=device, batch_size=bert.batch_size)
    return best_model, best, trials, best_scores


def training(data=None, output_dir=BASE_DIR, candidates=None, epochs=DOC2VEC_EPOCHS,
             target_mode=TARGET_MODE, precision_target=MIN_VALIDATION_PRECISION,
             run_ablation=RUN_ABLATION, train_bert=TRAIN_BERT,
             bert_model_name=BERT_MODEL_NAME, bert_epochs=BERT_EPOCHS, cache_dir=None, workers=None,
             feature_set='full'):
    # Fail before overwriting a completed run or starting hours of classic training.
    bert = None
    if train_bert:
        try:
            import torch
            import transformers
        except ImportError as exc:
            raise RuntimeError('BERT needs torch, transformers and safetensors. '
                               'Install requirements.txt before training.') from exc
        torch.manual_seed(SEED)
        bert = BertEmailClassifier.from_pretrained(
            bert_model_name, batch_size=BERT_BATCH_SIZE,
            max_length=BERT_MAX_LENGTH, stride=BERT_STRIDE)
        bert.model.config.email_positive_label = (
            POSITIVE_LABELS[target_mode])
        print(f'BERT initialized on {bert.device}; pretrained weights will be fine-tuned.', flush=True)
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    model_dir = output / 'dumped_models' / 'classification'; model_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = model_dir / 'run_manifest.json'
    save_json(manifest_path, {'status': 'incomplete'})  # Interrupted runs cannot be evaluated as complete.
    if data is None:
        data = load_training_emails(output)
    semantic_data = {} if train_bert else None
    # Không giữ tham chiếu tới DataFrame email thô ở đây: prepare_data chỉ giữ lại một phần
    # số dòng, còn bản đầy đủ (~5 GB với toàn bộ Dataset) sẽ nằm trong RAM suốt quá trình.
    source = [data]
    del data
    arrays, doc2vec, scaler, settings = prepare_data(
        source.pop(), output, target_mode, epochs=epochs, semantic_data=semantic_data,
        cache_dir=cache_dir, workers=workers, feature_set=feature_set)
    X_train, y_train = arrays['train']; X_val, y_val = arrays['validation']
    if candidates is None:
        candidates = build_candidates(y_train)
    winners, trials = tune_classifiers(X_train, y_train, X_val, y_val, candidates, precision_target)
    decisions = {name: decision for name, (_, decision) in winners.items()}
    bert_validation_scores = None
    if train_bert:
        bert, decision, bert_trials, bert_validation_scores = train_bert_classifier(
            bert, semantic_data['train'], y_train, semantic_data['validation'], y_val,
            model_dir / 'bert', precision_target, epochs=bert_epochs)
        decisions['BERT'] = decision
        trials.extend(bert_trials)
        settings['bert'] = {
            'checkpoint': bert_model_name, 'epochs': bert_epochs,
            'max_length': BERT_MAX_LENGTH, 'stride': BERT_STRIDE,
            'batch_size': BERT_BATCH_SIZE, 'gradient_accumulation': BERT_GRAD_ACCUMULATION,
            'learning_rate': BERT_LEARNING_RATE, 'aggregation': 'max_window_probability',
            'text_policy': 'decoded subject/body; no stopword removal or lemmatization',
            'window_labels': 'inherited from training email; equal total weight per email',
            'torch': torch.__version__, 'transformers': transformers.__version__,
            'device': str(bert.device),
        }
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
    if train_bert:
        # Test probabilities are generated only after checkpoint/threshold selection.
        # Test labels are never supplied to BERT fitting or checkpoint selection.
        for split, scores in (
                ('validation', bert_validation_scores),
                ('test', positive_scores(bert, semantic_data['test']))):
            path = output / f'data_bert_{split}_scores.npy'
            np.save(path, scores)
            artifacts.append(path)
        artifacts.extend(sorted((model_dir / 'bert').rglob('*')))
        artifacts = [path for path in artifacts if path.is_file()]
        configurations['BERT'] = {
            'kind': 'bert', 'directory': 'bert',
            'test_scores': 'data_bert_test_scores.npy',
            'validation_scores': 'data_bert_validation_scores.npy', **decisions['BERT']}
        parameters['BERT'] = settings['bert']
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
    parser = argparse.ArgumentParser(description='Audited email pipeline and five specialist branches')
    parser.add_argument('--mode', choices=('specialists', 'baseline'), default='specialists')
    parser.add_argument('--target-mode', choices=TARGET_MODES, default=TARGET_MODE,
                        help="Two-stage filter: 'broad' trains stage 1, 'phishing_vs_spam' stage 2")
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dataset-dir', type=Path)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--workers', type=int, default=None)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--audit-only', action='store_true', help='Stream every dataset record and verify ingestion accounting')
    parser.add_argument('--skip-text-training', action='store_true')
    parser.add_argument('--branch-labels', type=Path)
    parser.add_argument('--bert-epochs', type=int, default=BERT_EPOCHS)
    parser.add_argument('--bert-model', default=BERT_MODEL_NAME, help='Initial pretrained BERT checkpoint')
    parser.add_argument('--resume', type=Path, help='Resume prepared data into a new output directory')
    parser.add_argument('--feature-set', choices=FEATURE_SETS, default='full',
                        help="Baseline only: 'no_html_presence' drops is_html/html_to_text_ratio; "
                             "'html_content' also adds HTML content counts; "
                             "'no_era_proxies' also drops URL scheme counts and has_hidden_elements")
    args = parser.parse_args()
    output = args.output or BASE_DIR / 'runs' / datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%d_%H%M%S_%f')
    if args.audit_only:
        from load_data import audit_dataset
        summary = audit_dataset(args.dataset_dir or BASE_DIR / 'Dataset', output)
        print('Audit:', summary['status'], '; emails loaded:', summary['counts'].get('emails_loaded', 0))
    elif args.mode == 'specialists':
        if args.feature_set != 'full':
            parser.error('--feature-set applies to baseline mode')
        from specialists import run_specialists
        run_specialists(output, dataset_dir=args.dataset_dir, cache_dir=args.cache_dir, target_mode=args.target_mode,
                        workers=args.workers, branch_labels=args.branch_labels,
                        prepare_only=args.prepare_only, train_text=not args.skip_text_training,
                        bert_epochs=args.bert_epochs, bert_model_name=args.bert_model, resume=args.resume)
    else:
        if args.prepare_only or args.resume or args.branch_labels or args.dataset_dir:
            parser.error('Preparation/resume/dataset options apply to specialist mode')
        if output.exists() and any(output.iterdir()):
            parser.error('Choose a new output directory')
        training(output_dir=output, train_bert=not args.skip_text_training, target_mode=args.target_mode,
                 bert_epochs=args.bert_epochs, bert_model_name=args.bert_model,
                 cache_dir=args.cache_dir, workers=args.workers, feature_set=args.feature_set)
