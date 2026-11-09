"""Ablation theo dataset trên bản xuất feature của train.py --features-only.

Mỗi thí nghiệm bỏ (hoặc chỉ giữ) một nhóm dataset trong train VÀ validation, train lại Doc2Vec
cùng 9 classifier theo đúng code của train.py, rồi chấm trên tập test cố định và đầy đủ (mọi
thí nghiệm chấm cùng một tập dòng test, cùng thứ tự). Kết quả là "đóng góp biên khi bỏ nhóm khỏi
train/validation, trên tập test cố định", không phải "hiệu quả tuyệt đối" của dataset.

    python dataset_ablation.py --features runs/2026-11-08_features_v6 --output runs/2026-11-09_dataset_ablation --list
    python dataset_ablation.py --features ... --output ... --overlap
    python dataset_ablation.py --features ... --output ... [--experiments reference without_malspam]
    python dataset_ablation.py --features ... --output ... --summarize

Không lưu model (khoảng 1 GB mỗi thí nghiệm); chỉ lưu điểm của 9 model trên tập test.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DEFINITION_VERSION = 2  # Tăng khi đổi cách chọn dòng: thí nghiệm cũ không còn được coi là hoàn tất.
SPLITS = ('train', 'validation', 'test')
POSITIVE_GROUPS = ('nazario', 'phishing_pot', 'epvme', 'malspam')
LEGITIMATE_GROUPS = ('enron', 'spamassassin', 'trec', 'ceas', 'ling')
GROUPS = POSITIVE_GROUPS + LEGITIMATE_GROUPS
# Source (cột Source của metadata) -> nhóm dataset. Nazario khớp theo mẫu tên bên dưới.
SOURCE_GROUPS = {
    'phishing_pot': 'phishing_pot', 'EPVME': 'epvme', 'malspam': 'malspam',
    '20051114.mbox': 'nazario', 'private-phishing4.mbox': 'nazario',
    'enron': 'enron', 'Enron.csv': 'enron',
    'spamassassin': 'spamassassin', 'SpamAssasin.csv': 'spamassassin',
    'trec07p': 'trec', 'TREC_05.csv': 'trec', 'TREC_06.csv': 'trec', 'TREC_07.csv': 'trec',
    'CEAS_08.csv': 'ceas', 'Ling.csv': 'ling'}
NAZARIO_SOURCE = re.compile(r'phishing-\d{4}|phishing\d+\.mbox')
# Các cặp cần xem trước trong báo cáo chồng lấn: EPVME được dựng từ nội dung các corpus này.
PRIORITY_PAIRS = (('epvme', 'nazario'), ('epvme', 'enron'), ('epvme', 'spamassassin'), ('epvme', 'trec'))
RANDOM_TOLERANCE = 0.01  # random_like_*: tổng số dòng bỏ khớp nhóm tham chiếu trong ±1%,
GROUP_TOLERANCE = 0.02   # từng nhóm dương trong ±2% phần của nhóm đó,
MAX_CLUSTER_SHARE = 0.05  # và không bốc cụm lớn hơn 5% mục tiêu (vd. cụm template XSS 6.011 dòng).
REFERENCE = 'reference'
SEED_RUNS = ('reference', 'reference_seed43', 'reference_seed44')
COMPARED = ('Recall', 'Precision', 'F2-score', 'FPR', 'ROC-AUC', 'Average-Precision')


def _experiments():
    """Danh sách thí nghiệm theo thứ tự ưu tiên chạy."""
    items = [(REFERENCE, {'kind': 'reference', 'seed': 42}),
             ('reference_seed43', {'kind': 'reference', 'seed': 43}),
             ('reference_seed44', {'kind': 'reference', 'seed': 44})]
    items += [(f'without_{g}', {'kind': 'without', 'groups': [g], 'seed': 42}) for g in GROUPS]
    # Enron và TREC chồng lấn rất nhiều (ham TREC 2005 là thư Enron): bỏ riêng từng nhóm thì nhóm kia bù vào.
    items += [('without_enron_trec', {'kind': 'without', 'groups': ['enron', 'trec'], 'seed': 42})]
    items += [(f'only_{g}', {'kind': 'only', 'group': g, 'seed': 42}) for g in POSITIVE_GROUPS]
    items += [('random_like_nazario', {'kind': 'random_like', 'group': 'nazario', 'seed': 42, 'sample_seed': 42,
                                       'stratified': True, 'max_cluster_share': MAX_CLUSTER_SHARE})]
    return dict(items)


EXPERIMENTS = _experiments()


def dataset_group(source):
    """Nhóm dataset của một Source; Source lạ thì dừng thay vì gom nhầm."""
    if source in SOURCE_GROUPS:
        return SOURCE_GROUPS[source]
    if isinstance(source, str) and NAZARIO_SOURCE.fullmatch(source):
        return 'nazario'
    raise ValueError(f'Source {source!r} is not in the dataset group table of dataset_ablation.py')


def group_class(group):
    return 1 if group in POSITIVE_GROUPS else 0


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def load_metadata(features_dir):
    """Metadata của 3 tập (đã kiểm hash theo features_manifest.json), kèm cột Group."""
    features_dir = Path(features_dir)
    manifest = json.loads((features_dir / 'features_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('kind') != 'baseline_features' or manifest.get('schema') != 1:
        raise ValueError(f'{features_dir} is not a baseline feature export')
    if manifest.get('target_mode') != 'phishing':
        raise ValueError('Dataset ablation expects a phishing-mode export (spam outside the label scope)')
    frames = {}
    for split in SPLITS:
        name = f'{split}_metadata.csv'
        if file_sha256(features_dir / name) != manifest['files'][name]:
            raise RuntimeError(f'Feature export changed after it was written: {name}')
        frames[split] = annotate(pd.read_csv(features_dir / name))
    return frames, manifest


def annotate(frame):
    """Thêm cột Group; dòng mang nhãn trái với nhóm (vd. spam lọt vào) là lỗi."""
    frame = frame.copy()
    frame['Group'] = [dataset_group(s) for s in frame.Source]
    wrong = frame.Class.to_numpy() != frame.Group.map(group_class).to_numpy()
    if wrong.any():
        bad = frame.loc[wrong, ['Source', 'Class']].drop_duplicates().to_dict('records')
        raise ValueError(f'Rows whose class contradicts their dataset group: {bad}')
    return frame


def _stratum_targets(frame, target):
    """Chỉ tiêu từng nhóm dương theo tỷ lệ của nhóm trên toàn bộ mẫu dương của tập (kể cả cụm
    bị loại khỏi lần bốc); chia phần dư theo phần lẻ lớn nhất để tổng đúng bằng target."""
    counts = frame.Group[frame.Class == 1].value_counts()
    counts = counts.reindex([g for g in POSITIVE_GROUPS if g in counts.index])
    exact = counts / counts.sum() * target
    targets = np.floor(exact).astype(int)
    for group in (exact - targets).sort_values(ascending=False).index[:target - int(targets.sum())]:
        targets[group] += 1
    return {g: int(v) for g, v in targets.items()}


def stratified_cluster_mask(frame, target, rng):
    """Bỏ trọn các cụm _group thuần dương và thuộc một nhóm, bốc ngẫu nhiên theo từng nhóm dương.
    Cụm lẫn nhãn (bỏ phần dương sẽ tách đôi cụm), cụm vắt nhiều nhóm và cụm lớn hơn 5% target
    không được bốc. Trả về (mask, chi tiết để ghi vào experiment.json)."""
    details = {'target': int(target), 'groups': {}, 'excluded_large_clusters': [], 'multi_group_clusters': 0}
    if target == 0:
        return np.zeros(len(frame), dtype=bool), details
    clusters = frame.groupby('_group').agg(size=('Class', 'size'), low=('Class', 'min'),
                                           groups=('Group', 'nunique'), group=('Group', 'first'))
    pure = clusters[clusters.low == 1]
    limit = MAX_CLUSTER_SHARE * target
    large = pure[pure['size'] > limit].sort_values('size', ascending=False)
    details['excluded_large_clusters'] = [
        {'group': '+'.join(sorted(set(frame.Group[frame._group == key]))), 'size': int(size)}
        for key, size in large['size'].items()]
    details['multi_group_clusters'] = int(((pure['size'] <= limit) & (pure.groups > 1)).sum())
    eligible = pure[(pure['size'] <= limit) & (pure.groups == 1)]
    chosen, total = [], 0
    for group, goal in _stratum_targets(frame, target).items():
        pool = eligible[eligible.group == group]
        low, high = goal * (1 - GROUP_TOLERANCE), goal * (1 + GROUP_TOLERANCE)
        picked, removed = [], 0
        for index in rng.permutation(len(pool)):
            if removed >= goal:  # nhắm đúng chỉ tiêu; ±2% chỉ là giới hạn chấp nhận
                break
            size = int(pool['size'].iloc[index])
            if removed + size > high:
                continue
            picked.append(pool.index[index])
            removed += size
        if removed < low:
            raise ValueError(f'Cannot remove {goal} {group} rows within ±2% using eligible whole clusters')
        details['groups'][group] = {'target': goal, 'removed_rows': removed, 'removed_clusters': len(picked)}
        chosen += picked
        total += removed
    if abs(total - target) > target * RANDOM_TOLERANCE:
        raise ValueError(f'Stratified removal of {total} rows is not within ±1% of {target}')
    details.update({'removed_rows': total, 'removed_clusters': len(chosen)})
    return frame._group.isin(set(chosen)).to_numpy(), details


def removal_masks(metadata, definition, details=None):
    """{split: mảng bool các dòng bị bỏ}. Tập test không bao giờ bị bỏ dòng nào. Với random_like,
    chi tiết lần bốc của từng tập được ghi vào dict details nếu có."""
    kind = definition['kind']
    masks = {}
    for index, split in enumerate(SPLITS):
        frame = metadata[split]
        if split == 'test' or kind == 'reference':
            masks[split] = np.zeros(len(frame), dtype=bool)
        elif kind == 'without':
            masks[split] = frame.Group.isin(definition['groups']).to_numpy()
        elif kind == 'only':
            masks[split] = ((frame.Class == 1) & (frame.Group != definition['group'])).to_numpy()
        elif kind == 'random_like':
            group = definition['group']
            rng = np.random.default_rng(definition['sample_seed'] + index)
            masks[split], drawn = stratified_cluster_mask(frame, int((frame.Group == group).sum()), rng)
            # Số cụm mà without_<group> bỏ: cùng số dòng nhưng có thể ít cụm (ít đa dạng) hơn nhiều.
            drawn[f'without_{group}_clusters'] = int(frame._group[frame.Group == group].nunique())
            if details is not None:
                details[split] = drawn
        else:
            raise ValueError(f'Unknown experiment kind: {kind}')
    return masks


def held_out_groups(definition):
    if definition['kind'] == 'without':
        return list(definition['groups'])
    if definition['kind'] == 'only':
        return [g for g in POSITIVE_GROUPS if g != definition['group']]
    return []


def split_counts(metadata, masks):
    counts = {}
    for split in SPLITS:
        frame, removed = metadata[split], masks[split]
        counts[split] = {
            'kept': {str(k): int(v) for k, v in frame.Class[~removed].value_counts().sort_index().items()},
            'removed': {str(k): int(v) for k, v in frame.Class[removed].value_counts().sort_index().items()},
            'removed_by_group': {g: int(v) for g, v in frame.Group[removed].value_counts().sort_index().items()}}
    return counts


def _pair_scores(y, scores, chosen, complement):
    """AUC/AP của một nhóm một lớp, chấm với toàn bộ lớp còn lại của tập test."""
    from sklearn.metrics import average_precision_score, roc_auc_score
    idx = np.concatenate([chosen, complement])
    if len(chosen) == 0 or len(complement) == 0:
        return None, None
    return float(roc_auc_score(y[idx], scores[idx])), float(average_precision_score(y[idx], scores[idx]))


def subset_rows(y, scores, threshold, idx, label, positives, negatives):
    from evaluate import classification_metrics
    metrics = classification_metrics(y[idx], scores[idx], threshold)
    complement = negatives if label == 1 else positives
    auc, ap = _pair_scores(y, scores, idx, complement)
    rate = metrics['Recall'] if label == 1 else metrics['FPR']
    return {'Count': len(idx), 'TP': metrics['TP'], 'FP': metrics['FP'], 'FN': metrics['FN'], 'TN': metrics['TN'],
            'Rate': rate, 'Rate-name': 'Recall' if label == 1 else 'FPR', 'Pair-ROC-AUC': auc, 'Pair-AP': ap}


def test_metrics(test, scores_by_model, decisions, definition):
    """Chỉ số trên test: tổng thể (đủ và bỏ EPVME), theo nhóm và theo Source."""
    from evaluate import classification_metrics
    test = test.reset_index(drop=True)
    y = test.Class.to_numpy()
    positives, negatives = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
    held = set(held_out_groups(definition))
    no_epvme = np.flatnonzero(test.Group.to_numpy() != 'epvme')
    groups = {g: np.asarray(idx, dtype=int) for g, idx in test.groupby('Group', sort=True).groups.items()}
    sources = {s: np.asarray(idx, dtype=int) for s, idx in test.groupby('Source', sort=True).groups.items()}
    overall, by_group, by_source = [], [], []
    for model, scores in scores_by_model.items():
        decision = decisions[model]
        threshold = decision['threshold']
        common = {'Model': model, 'Threshold': threshold,
                  'threshold_constraint_met': bool(decision['precision_target_met'])}
        overall.append({**common, 'Scope': 'all', 'Count': len(y), **classification_metrics(y, scores, threshold)})
        overall.append({**common, 'Scope': 'without_epvme', 'Count': len(no_epvme),
                        **classification_metrics(y[no_epvme], scores[no_epvme], threshold)})
        for group, idx in groups.items():
            label = group_class(group)
            by_group.append({**common, 'Group': group, 'Class': label, 'held_out': group in held,
                             **subset_rows(y, scores, threshold, idx, label, positives, negatives)})
        for source, idx in sources.items():
            group = dataset_group(source)
            label = group_class(group)
            by_source.append({**common, 'Source': source, 'Group': group, 'Class': label, 'held_out': group in held,
                              **subset_rows(y, scores, threshold, idx, label, positives, negatives)})
    return pd.DataFrame(overall), pd.DataFrame(by_group), pd.DataFrame(by_source)


def definition_record(name, manifest_digest, epochs):
    """Những gì quyết định kết quả; thí nghiệm đã xong chỉ được dùng lại khi mọi khoá này khớp."""
    return {'name': name, 'definition': EXPERIMENTS[name], 'definition_version': DEFINITION_VERSION,
            'export_digest': manifest_digest, 'doc2vec_epochs': int(epochs),
            'python_hash_seed': os.environ.get('PYTHONHASHSEED'),
            'source_groups': {**SOURCE_GROUPS, 'nazario_pattern': NAZARIO_SOURCE.pattern},
            'positive_groups': list(POSITIVE_GROUPS), 'legitimate_groups': list(LEGITIMATE_GROUPS)}


def environment_record():
    """Phiên bản thư viện và hash code lúc chạy (để phát hiện nâng cấp/sửa code giữa đợt dài)."""
    import platform
    import gensim
    import sklearn
    import xgboost
    code = {name: file_sha256(BASE_DIR / name) for name in CODE_FILES}
    return {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__,
            'sklearn': sklearn.__version__, 'xgboost': xgboost.__version__, 'gensim': gensim.__version__,
            'code_sha256': code, **git_state()}


CODE_FILES = ('dataset_ablation.py', 'train.py', 'evaluate.py', 'preprocess.py', 'pipeline_cache.py', 'load_data.py')


def git_state():
    """Commit đang checkout và việc code của pipeline có khác commit đó không (để trả lời
    "kết quả này từ code nào"). Không có git thì ghi None."""
    def git(*args):
        result = subprocess.run(['git', *args], cwd=BASE_DIR, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    try:
        commit = git('rev-parse', 'HEAD')
        changed = git('status', '--porcelain', '--', *CODE_FILES)
    except OSError:
        commit = changed = None
    return {'git_commit': commit,
            'git_code_dirty': None if changed is None else bool(changed),
            'git_code_changes': changed.splitlines() if changed else []}


def experiment_state(folder, record, ignore_lock=False):
    """'complete' (cùng định nghĩa), 'locked', 'pending', hoặc lỗi nếu kết quả cũ khác định nghĩa."""
    if not ignore_lock and (folder / 'lock').exists():
        return 'locked'
    path = folder / 'experiment.json'
    if not path.exists():
        return 'pending'
    stored = json.loads(path.read_text(encoding='utf-8'))
    if stored.get('status') != 'complete':
        return 'pending'  # bị ngắt hoặc lỗi giữa chừng: chạy lại từ đầu
    if {k: stored.get(k) for k in record} != record:
        raise RuntimeError(f'{folder} holds a completed experiment with a different export or definition; '
                           'use a new --output folder')
    return 'complete'


def save_json(path, value):
    tmp = path.with_suffix(path.suffix + '.part')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


def run_experiment(name, frames, metadata, manifest, manifest_digest, output, epochs=None, candidates=None):
    """Chạy một thí nghiệm. candidates(y_train, seed) -> dict ứng viên (mặc định build_candidates)."""
    from train import DOC2VEC_EPOCHS, MIN_VALIDATION_PRECISION, build_candidates, tune_classifiers, vectorize
    from evaluate import positive_scores, validation_rank
    definition = EXPERIMENTS[name]
    folder = Path(output) / name
    folder.mkdir(parents=True, exist_ok=True)
    epochs = DOC2VEC_EPOCHS if epochs is None else int(epochs)
    record = definition_record(name, manifest_digest, epochs)
    state = experiment_state(folder, record)
    if state != 'pending':
        print(f'{name}: {state}, skipped', flush=True)
        return state
    try:
        fd = os.open(folder / 'lock', os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(f'{name}: locked by another process, skipped', flush=True)
        return 'locked'
    os.close(fd)
    started = time.time()
    try:
        # Tiến trình khác có thể vừa chạy xong và nhả lock giữa lần kiểm tra trên và lúc lấy lock.
        if experiment_state(folder, record, ignore_lock=True) == 'complete':
            print(f'{name}: complete, skipped', flush=True)
            return 'complete'
        (folder / 'lock').write_text(f'pid={os.getpid()} started={time.ctime(started)}\n', encoding='utf-8')
        save_json(folder / 'experiment.json', {**record, 'status': 'running', 'started': time.ctime(started)})
        drawn = {}
        masks = removal_masks(metadata, definition, drawn)
        subset = {split: frames[split].loc[~masks[split]].reset_index(drop=True) for split in SPLITS}
        test = metadata['test'].reset_index(drop=True)
        if not subset['test'].RecordId.reset_index(drop=True).equals(test.RecordId):
            raise RuntimeError('Test rows of the export are not aligned with the test metadata')
        counts = split_counts(metadata, masks)
        print(f'{name}: train {counts["train"]["kept"]}, validation {counts["validation"]["kept"]}', flush=True)
        seed = definition['seed']
        arrays, _, _, settings = vectorize(subset, manifest['preprocessing'], epochs=epochs, seed=seed)
        vectorized = time.time()
        X_train, y_train = arrays['train']
        X_val, y_val = arrays['validation']
        options = (candidates or (lambda y, s: build_candidates(y, seed=s)))(y_train, seed)
        winners, trials = tune_classifiers(X_train, y_train, X_val, y_val, options, MIN_VALIDATION_PRECISION)
        decisions = {model: decision for model, (_, decision) in winners.items()}
        selected = max(decisions, key=lambda model: validation_rank(decisions[model]))
        X_test, y_test = arrays['test']
        scores = {model: positive_scores(estimator, X_test) for model, (estimator, _) in winners.items()}
        if not np.array_equal(test.Class.to_numpy(), y_test):
            raise RuntimeError('Test rows are not aligned with the test metadata')
        overall, by_group, by_source = test_metrics(test, scores, decisions, definition)
        pd.DataFrame(trials).to_csv(folder / 'validation_results.csv', index=False)
        overall.to_csv(folder / 'test_overall.csv', index=False)
        by_group.to_csv(folder / 'test_by_group.csv', index=False)
        by_source.to_csv(folder / 'test_by_source.csv', index=False)
        np.savez(folder / 'test_scores.npz', **{model: s.astype(np.float32) for model, s in scores.items()})
        finished = time.time()
        save_json(folder / 'experiment.json', {
            **record, 'status': 'complete', 'selected_model': selected,
            'models': {model: {**decision, 'threshold_constraint_met': bool(decision['precision_target_met'])}
                       for model, decision in decisions.items()},
            'held_out_groups': held_out_groups(definition), 'split_counts': counts,
            **({'random_control': drawn} if drawn else {}),
            'test_record_ids_sha256': hashlib.sha256('\n'.join(subset['test'].RecordId).encode()).hexdigest(),
            'test_scores_sha256': file_sha256(folder / 'test_scores.npz'),
            'environment': environment_record(),
            'seconds': {'vectorize': round(vectorized - started, 1), 'total': round(finished - started, 1)},
            'started': time.ctime(started), 'finished': time.ctime(finished)})
        print(f'{name}: complete in {(finished - started) / 3600:.2f} h, selected {selected}', flush=True)
        return 'complete'
    except Exception as exc:
        import traceback
        save_json(folder / 'experiment.json', {**record, 'status': 'failed', 'error': repr(exc),
                                               'traceback': traceback.format_exc(), 'started': time.ctime(started)})
        raise
    finally:
        (folder / 'lock').unlink(missing_ok=True)


def overlap_report(metadata):
    """Cụm gần trùng (_group) vắt qua nhiều nhóm dataset, theo cặp nhóm và theo tập."""
    rows = []
    for split in SPLITS:
        frame = metadata[split]
        for _, cluster in frame.groupby('_group'):
            groups = sorted(set(cluster.Group))
            if len(groups) < 2:
                continue
            sizes = cluster.Group.value_counts()
            for i, a in enumerate(groups):
                for b in groups[i + 1:]:
                    first, second = (a, b) if (a, b) in PRIORITY_PAIRS or (b, a) not in PRIORITY_PAIRS else (b, a)
                    # Lẫn nhãn xét riêng hai nhóm của cặp (cụm có thể vắt qua 3 nhóm trở lên).
                    mixed = group_class(first) != group_class(second)
                    rows.append({'split': split, 'group_a': first, 'group_b': second, 'mixed': mixed,
                                 'rows_a': int(sizes[first]), 'rows_b': int(sizes[second])})
    columns = ['split', 'group_a', 'group_b', 'clusters', 'same_label_clusters', 'mixed_label_clusters',
               'rows_a', 'rows_b', 'mixed_rows_a', 'mixed_rows_b']
    if not rows:
        return pd.DataFrame(columns=columns)
    pairs = pd.DataFrame(rows)
    pairs['mixed_rows_a'] = pairs.rows_a.where(pairs.mixed, 0)
    pairs['mixed_rows_b'] = pairs.rows_b.where(pairs.mixed, 0)
    report = pairs.groupby(['split', 'group_a', 'group_b']).agg(
        clusters=('mixed', 'size'), mixed_label_clusters=('mixed', 'sum'), rows_a=('rows_a', 'sum'),
        rows_b=('rows_b', 'sum'), mixed_rows_a=('mixed_rows_a', 'sum'), mixed_rows_b=('mixed_rows_b', 'sum')).reset_index()
    total = report.groupby(['group_a', 'group_b'], as_index=False).sum(numeric_only=True).assign(split='total')
    report = pd.concat([report, total], ignore_index=True)
    report['same_label_clusters'] = report.clusters - report.mixed_label_clusters
    report['priority'] = [PRIORITY_PAIRS.index((a, b)) if (a, b) in PRIORITY_PAIRS else len(PRIORITY_PAIRS)
                          for a, b in zip(report.group_a, report.group_b)]
    report['split_order'] = report.split.map({s: i for i, s in enumerate(SPLITS + ('total',))})
    report = report.sort_values(['priority', 'group_a', 'group_b', 'split_order']).drop(columns=['priority', 'split_order'])
    return report[columns].astype({c: int for c in columns[3:]}).reset_index(drop=True)


def _completed(output):
    found = {}
    for name in EXPERIMENTS:
        path = Path(output) / name / 'experiment.json'
        if path.exists():
            stored = json.loads(path.read_text(encoding='utf-8'))
            if stored.get('status') == 'complete':
                found[name] = stored
    return found


def _with_deltas(frame, keys, reference, metrics):
    if reference is None or reference.empty:
        return frame
    base = reference[keys + metrics].rename(columns={m: f'reference_{m}' for m in metrics})
    merged = frame.merge(base, on=keys, how='left')
    for metric in metrics:
        merged[f'delta_{metric}'] = merged[metric] - merged[f'reference_{metric}']
    return merged.drop(columns=[f'reference_{m}' for m in metrics])


def summarize(output, test_metadata=None):
    """Tổng hợp các thí nghiệm đã xong thành CSV và heatmap trong thư mục output. Có metadata tập
    test (load_metadata(...)['test']) thì thêm các phân rã tính từ điểm đã lưu."""
    output = Path(output)
    completed = _completed(output)
    if not completed:
        raise RuntimeError(f'No completed experiment in {output}')
    keys = {(s['export_digest'], s['definition_version'], s['doc2vec_epochs'], s['python_hash_seed'])
            for s in completed.values()}
    if len(keys) > 1:
        raise RuntimeError(f'{output} mixes experiments from different exports or settings: {sorted(keys)}')
    overall, by_group = [], []
    for name, stored in completed.items():
        selected = stored['selected_model']
        for kind, store in (('test_overall.csv', overall), ('test_by_group.csv', by_group)):
            frame = pd.read_csv(output / name / kind)
            frame.insert(0, 'Experiment', name)
            frame['Selected-on-validation'] = frame.Model == selected
            store.append(frame)
    overall, by_group = pd.concat(overall, ignore_index=True), pd.concat(by_group, ignore_index=True)
    group_metrics = ['Rate', 'Pair-ROC-AUC', 'Pair-AP']
    reference_overall = overall[overall.Experiment == REFERENCE] if REFERENCE in completed else None
    reference_group = by_group[by_group.Experiment == REFERENCE] if REFERENCE in completed else None
    overall = _with_deltas(overall, ['Model', 'Scope'], reference_overall, list(COMPARED))
    by_group = _with_deltas(by_group, ['Model', 'Group'], reference_group, group_metrics)
    if reference_group is not None:
        # Góc nhìn "model chọn trên validation": so với model mà reference chọn, không phải cùng họ.
        chosen = reference_group[reference_group['Selected-on-validation']][['Group', 'Rate']]
        by_group = by_group.merge(chosen.rename(columns={'Rate': '_selected_rate'}), on='Group', how='left')
        by_group['delta_vs_reference_selected_Rate'] = by_group.Rate - by_group.pop('_selected_rate')
    overall.to_csv(output / 'summary_overall.csv', index=False)
    by_group.to_csv(output / 'summary_by_group.csv', index=False)
    written = ['summary_overall.csv', 'summary_by_group.csv']
    if REFERENCE in completed:
        family = completed[REFERENCE]['selected_model']
        # Cùng họ classifier với reference; mỗi thí nghiệm tune lại grid trên validation của nó.
        fixed = pd.concat([overall[overall.Model == family].assign(Level='overall'),
                           by_group[by_group.Model == family].assign(Level='group')], ignore_index=True)
        fixed.insert(1, 'Fixed-family', family)
        fixed.to_csv(output / 'summary_fixed_classifier.csv', index=False)
        written.append('summary_fixed_classifier.csv')
        cross = by_group[(by_group.Model == family) & (by_group.Class == 1)
                         & by_group.Experiment.isin([REFERENCE] + [f'only_{g}' for g in POSITIVE_GROUPS])]
        if not cross.empty:
            matrix = cross.pivot(index='Experiment', columns='Group', values='Rate')
            matrix = matrix.reindex(columns=[g for g in POSITIVE_GROUPS if g in matrix.columns])
            matrix.insert(0, 'Model', family)
            matrix.to_csv(output / 'summary_cross_source.csv')
            written.append('summary_cross_source.csv')
        _heatmaps(output, by_group, family, written)
    seeds = [name for name in SEED_RUNS if name in completed]
    if len(seeds) > 1:
        parts = [overall[overall.Experiment.isin(seeds)].melt(
                     id_vars=['Experiment', 'Model', 'Scope'], value_vars=list(COMPARED),
                     var_name='Metric').rename(columns={'Scope': 'Subset'}),
                 by_group[by_group.Experiment.isin(seeds)].melt(
                     id_vars=['Experiment', 'Model', 'Group'], value_vars=group_metrics,
                     var_name='Metric').rename(columns={'Group': 'Subset'})]
        spread = pd.concat(parts, ignore_index=True).groupby(['Model', 'Subset', 'Metric']).value.agg(
            ['count', 'mean', 'min', 'max', 'std']).reset_index()
        spread['range'] = spread['max'] - spread['min']
        spread.to_csv(output / 'seed_spread.csv', index=False)
        written.append('seed_spread.csv')
    if test_metadata is not None:
        nazario, epvme = score_breakdowns(output, completed, test_metadata)
        nazario.to_csv(output / 'summary_nazario_by_cluster.csv', index=False)
        epvme.to_csv(output / 'summary_epvme_by_attack.csv', index=False)
        written += ['summary_nazario_by_cluster.csv', 'summary_epvme_by_attack.csv']
    print('Summary written: ' + ', '.join(written), flush=True)
    return written


def attack_family(label_basis):
    """Họ tấn công EPVME do load_data suy đoán (heuristic, không phải nhãn gốc của dataset)."""
    found = re.search(r'attack_family=([^ ;]+)', str(label_basis))
    return found.group(1) if found else 'unknown'


def score_breakdowns(output, completed, test):
    """Từ điểm test đã lưu (không train thêm): recall Nazario theo cụm có/không có EPVME, và recall
    EPVME theo họ tấn công heuristic, kèm support."""
    test = test.reset_index(drop=True)
    digest = hashlib.sha256('\n'.join(test.RecordId).encode()).hexdigest()
    epvme_clusters = set(test._group[test.Group == 'epvme'])
    nazario = (test.Group == 'nazario').to_numpy()
    shared = test._group.isin(epvme_clusters).to_numpy()
    subsets = {'nazario_in_epvme_cluster': nazario & shared, 'nazario_only_cluster': nazario & ~shared}
    families = test.LabelBasis.map(attack_family).where(test.Group == 'epvme')
    nazario_rows, epvme_rows = [], []
    for name, stored in completed.items():
        if stored['test_record_ids_sha256'] != digest:
            raise RuntimeError(f'{name} was scored on different test rows than the given metadata')
        with np.load(Path(output) / name / 'test_scores.npz', allow_pickle=False) as scores:
            for model, config in stored['models'].items():
                predicted = scores[model] >= config['threshold']
                common = {'Experiment': name, 'Model': model, 'Selected-on-validation': model == stored['selected_model'],
                          'threshold_constraint_met': config['threshold_constraint_met']}
                for subset, mask in subsets.items():
                    support, hits = int(mask.sum()), int(predicted[mask].sum())
                    nazario_rows.append({**common, 'Subset': subset, 'Support': support, 'TP': hits,
                                         'Recall': hits / support if support else None})
                for family in sorted(families.dropna().unique()):
                    mask = (families == family).to_numpy()
                    support, hits = int(mask.sum()), int(predicted[mask].sum())
                    epvme_rows.append({**common, 'Attack-family (heuristic)': family, 'Support': support,
                                       'TP': hits, 'Recall': hits / support})
    return pd.DataFrame(nazario_rows), pd.DataFrame(epvme_rows)


def _heatmaps(output, by_group, family, written):
    """Heatmap độ chênh so với reference: recall nhóm dương, FPR nhóm hợp lệ."""
    if 'delta_Rate' not in by_group:
        return
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    # fixed: cùng họ classifier mà reference chọn; selected: model mỗi thí nghiệm chọn trên validation,
    # so với model reference chọn.
    views = {'fixed': (by_group[by_group.Model == family], 'delta_Rate'),
             'selected': (by_group[by_group['Selected-on-validation']], 'delta_vs_reference_selected_Rate')}
    order = [name for name in EXPERIMENTS if name != REFERENCE]
    for view, (frame, column) in views.items():
        for label, groups, metric in ((1, POSITIVE_GROUPS, 'recall'), (0, LEGITIMATE_GROUPS, 'fpr')):
            part = frame[(frame.Class == label) & frame.Experiment.isin(order)]
            if part.empty:
                continue
            matrix = part.pivot(index='Experiment', columns='Group', values=column)
            matrix = matrix.reindex(index=[n for n in order if n in matrix.index],
                                    columns=[g for g in groups if g in matrix.columns])
            values = matrix.to_numpy(dtype=float)
            limit = (np.nanmax(np.abs(values)) if np.isfinite(values).any() else 0.0) or 1.0
            fig, ax = plt.subplots(figsize=(1.6 + 1.1 * matrix.shape[1], 1.2 + 0.45 * matrix.shape[0]))
            cmap = 'RdBu' if label == 1 else 'RdBu_r'  # đỏ = xấu đi (recall giảm hoặc FPR tăng)
            image = ax.imshow(values, cmap=cmap, vmin=-limit, vmax=limit, aspect='auto')
            ax.set_xticks(range(matrix.shape[1]), matrix.columns, rotation=30, ha='right')
            ax.set_yticks(range(matrix.shape[0]), matrix.index)
            for (i, j), value in np.ndenumerate(values):
                if np.isfinite(value):
                    ax.text(j, i, f'{value:+.3f}', ha='center', va='center', fontsize=8)
            title = family if view == 'fixed' else 'validation-selected model'
            ax.set_title(f'Δ {metric.upper()} vs reference ({title})')
            fig.colorbar(image, ax=ax, shrink=0.8)
            fig.tight_layout()
            name = f'heatmap_{view}_{metric}.png'
            fig.savefig(output / name, dpi=150)
            plt.close(fig)
            written.append(name)
    cross_path = output / 'summary_cross_source.csv'
    if cross_path.exists():
        cross = pd.read_csv(cross_path, index_col=0).drop(columns='Model')
        fig, ax = plt.subplots(figsize=(1.6 + 1.2 * cross.shape[1], 1.2 + 0.5 * cross.shape[0]))
        image = ax.imshow(cross.to_numpy(dtype=float), cmap='viridis', vmin=0, vmax=1, aspect='auto')
        ax.set_xticks(range(cross.shape[1]), cross.columns, rotation=30, ha='right')
        ax.set_yticks(range(cross.shape[0]), cross.index)
        for (i, j), value in np.ndenumerate(cross.to_numpy(dtype=float)):
            if np.isfinite(value):
                ax.text(j, i, f'{value:.3f}', ha='center', va='center', fontsize=8, color='white' if value < 0.6 else 'black')
        ax.set_title(f'Test recall per positive group ({family})')
        fig.colorbar(image, ax=ax, shrink=0.8)
        fig.tight_layout()
        fig.savefig(output / 'heatmap_cross_source.png', dpi=150)
        plt.close(fig)
        written.append('heatmap_cross_source.png')


def list_experiments(metadata, output):
    rows = []
    for name, definition in EXPERIMENTS.items():
        counts = split_counts(metadata, removal_masks(metadata, definition))
        folder = Path(output) / name
        status = 'locked' if (folder / 'lock').exists() else (
            json.loads((folder / 'experiment.json').read_text(encoding='utf-8')).get('status', '?')
            if (folder / 'experiment.json').exists() else 'pending')
        rows.append({'experiment': name, 'status': status,
                     'train_legit': counts['train']['kept'].get('0', 0), 'train_pos': counts['train']['kept'].get('1', 0),
                     'val_legit': counts['validation']['kept'].get('0', 0),
                     'val_pos': counts['validation']['kept'].get('1', 0),
                     'removed_train': sum(counts['train']['removed'].values()),
                     'removed_val': sum(counts['validation']['removed'].values())})
    return pd.DataFrame(rows)


MARKER = 'ablation.json'


def claim_output(output, features, digest):
    """Chỉ ghi vào thư mục mới hoặc thư mục ablation của cùng bản xuất (không bao giờ vào run khác)."""
    output = Path(output)
    if output.resolve() == Path(features).resolve():
        raise RuntimeError('--output must differ from --features')
    marker = output / MARKER
    if marker.exists():
        stored = json.loads(marker.read_text(encoding='utf-8'))
        if stored.get('export_digest') != digest:
            raise RuntimeError(f'{output} belongs to another feature export; use a new --output folder')
        return
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f'{output} is not empty and is not a dataset ablation folder; use a new --output folder')
    output.mkdir(parents=True, exist_ok=True)
    save_json(marker, {'export_digest': digest, 'features': str(features), 'definition_version': DEFINITION_VERSION,
                       'created': time.ctime()})


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be >= 1')
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description='Ablation theo dataset trên bản xuất feature (xem README).')
    parser.add_argument('--features', type=Path, required=True, help='Thư mục của train.py --features-only')
    parser.add_argument('--output', type=Path, required=True, help='Thư mục mới trong runs/')
    parser.add_argument('--experiments', nargs='+', metavar='NAME', help='Chỉ chạy các thí nghiệm này')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--list', action='store_true', help='Liệt kê thí nghiệm và số dòng, không train')
    mode.add_argument('--overlap', action='store_true', help='Ghi overlap_by_group.csv, không train')
    mode.add_argument('--summarize', action='store_true', help='Chỉ tổng hợp các thí nghiệm đã xong')
    mode.add_argument('--unlock', nargs='+', metavar='NAME', help='Xoá lock của thí nghiệm bị ngắt')
    parser.add_argument('--doc2vec-epochs', type=positive_int, help=argparse.SUPPRESS)  # chỉ cho test
    args = parser.parse_args(argv)
    unknown = [n for n in (args.experiments or []) + (args.unlock or []) if n not in EXPERIMENTS]
    if unknown:
        parser.error(f'unknown experiment(s) {unknown}; valid: {", ".join(EXPERIMENTS)}')
    if args.experiments and (args.list or args.overlap or args.summarize or args.unlock):
        parser.error('--experiments only applies to training runs')
    # Doc2Vec phụ thuộc hash seed của Python: mọi thí nghiệm chạy với PYTHONHASHSEED=0.
    if os.environ.get('PYTHONHASHSEED') != '0':
        environment = {**os.environ, 'PYTHONHASHSEED': '0'}
        return subprocess.run([sys.executable, str(Path(__file__).resolve()), *(argv if argv is not None else sys.argv[1:])],
                              env=environment).returncode
    output = args.output
    if args.unlock:
        for name in args.unlock:
            (output / name / 'lock').unlink(missing_ok=True)
            print(f'{name}: lock removed', flush=True)
        return 0
    digest = file_sha256(Path(args.features) / 'features_manifest.json')
    if args.summarize:
        if not (output / MARKER).exists():
            raise RuntimeError(f'{output} is not a dataset ablation folder')
        claim_output(output, args.features, digest)
        summarize(output, load_metadata(args.features)[0]['test'])
        return 0
    metadata, manifest = load_metadata(args.features)
    if args.list:
        with pd.option_context('display.width', 200, 'display.max_columns', 20):
            print(list_experiments(metadata, output).to_string(index=False))
        return 0
    claim_output(output, args.features, digest)
    if args.overlap:
        overlap_report(metadata).to_csv(output / 'overlap_by_group.csv', index=False)
        print(f'Overlap report written: {output / "overlap_by_group.csv"}', flush=True)
        return 0
    from train import load_exported_features
    frames, _ = load_exported_features(args.features)
    for split in SPLITS:
        if not frames[split].RecordId.equals(metadata[split].RecordId):
            raise RuntimeError(f'Export split {split} is not aligned with its metadata')
    failed = []
    for name in args.experiments or list(EXPERIMENTS):
        try:
            run_experiment(name, frames, metadata, manifest, digest, output, epochs=args.doc2vec_epochs)
        except Exception as exc:  # một thí nghiệm lỗi không được dừng cả hàng đợi dài
            failed.append(name)
            print(f'{name}: FAILED ({exc!r}); see {output / name / "experiment.json"}', flush=True)
    if _completed(output):
        summarize(output, metadata['test'])
    if failed:
        print(f'Failed experiments: {", ".join(failed)}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
