"""Test dataset_ablation.py trên một bản xuất feature tổng hợp rất nhỏ (Doc2Vec 2 epoch)."""
import gzip
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dataset_ablation as ablation  # noqa: E402
from evaluate import file_digest  # noqa: E402
from preprocess import BASELINE_FEATURE_NAMES  # noqa: E402

# 29 Source của runs/2026-11-08_features_v6 (export phishing mode).
REAL_SOURCES = ['CEAS_08.csv', 'Enron.csv', 'Ling.csv', 'SpamAssasin.csv', 'TREC_05.csv', 'TREC_06.csv', 'enron',
                'spamassassin', 'trec07p', 'EPVME', 'malspam', '20051114.mbox'] + \
               [f'phishing-{year}' for year in range(2015, 2026)] + \
               ['phishing0.mbox', 'phishing1.mbox', 'phishing2.mbox', 'phishing3.mbox', 'private-phishing4.mbox',
                'phishing_pot']
SOURCES = {'phishing-2020': 1, 'phishing_pot': 1, 'EPVME': 1, 'malspam': 1, 'enron': 0, 'Enron.csv': 0,
           'spamassassin': 0, 'trec07p': 0, 'CEAS_08.csv': 0, 'Ling.csv': 0}
POSITIVE_WORDS = 'verify account password urgent click suspended invoice login'.split()
LEGIT_WORDS = 'meeting schedule report project agenda budget lunch review'.split()


def small_candidates(y, seed):
    from sklearn.dummy import DummyClassifier
    from sklearn.linear_model import LogisticRegression
    return {'Logistic Regression': [LogisticRegression(max_iter=500, random_state=seed)],
            # Điểm hằng số: không ngưỡng nào đạt precision 0.90 -> ngưỡng dự phòng (F2).
            'Dummy': [DummyClassifier(strategy='prior')]}


ROWS = 40  # dòng mỗi Source mỗi tập; mục tiêu đối chứng = 40, nên cụm > 2 dòng (5%) không được bốc


def build_export(folder, rows_per_source=ROWS, seed=0):
    """Export giống train.export_features: metadata CSV, .npy, text .jsonl.gz, manifest có hash."""
    rng = np.random.default_rng(seed)
    folder.mkdir(parents=True)
    group_id = 0
    files = {}
    for split in ablation.SPLITS:
        records = []
        for source, label in SOURCES.items():
            for i in range(rows_per_source):
                records.append({'Source': source, 'Class': label, '_group': group_id})
                group_id += 1
        frame = pd.DataFrame(records)
        epvme = frame.index[frame.Source == 'EPVME']
        if split == 'train':
            # Cụm gần trùng vắt nhóm: EPVME+enron (lẫn nhãn), EPVME+Nazario (cùng nhãn), cụm 2 dòng EPVME,
            # và một cụm template 5 dòng EPVME (> 5% mục tiêu: không bao giờ được bốc).
            frame.loc[frame.index[frame.Source == 'enron'][0], '_group'] = frame.loc[epvme[0], '_group']
            frame.loc[frame.index[frame.Source == 'phishing-2020'][0], '_group'] = frame.loc[epvme[1], '_group']
            frame.loc[epvme[3], '_group'] = frame.loc[epvme[2], '_group']
            frame.loc[epvme[4:9], '_group'] = frame.loc[epvme[4], '_group']
        if split == 'test':  # hai dòng Nazario test chung cụm với EPVME
            frame.loc[frame.index[frame.Source == 'phishing-2020'][:2], '_group'] = frame.loc[epvme[0], '_group']
        frame['RecordId'] = [f'{split}-{i}' for i in range(len(frame))]
        frame['Location'] = frame.RecordId
        frame['LabelKind'] = np.where(frame.Class == 1, 'phishing', 'legitimate')
        frame['LabelBasis'] = 'test'
        families = np.where(np.arange(len(epvme)) % 4 == 0, 'xss', 'mime_wrapping')
        frame.loc[epvme, 'LabelBasis'] = [f'epvme; attack_family={f} (heuristic)' for f in families]
        frame['OriginalLabel'] = frame.Class
        frame['_dedup_key'] = frame.RecordId
        frame = frame[['RecordId', 'Source', 'Location', 'LabelKind', 'LabelBasis', 'OriginalLabel', 'Class',
                       '_dedup_key', '_group']]
        frame.to_csv(folder / f'{split}_metadata.csv', index=False)
        labels = frame.Class.to_numpy(dtype=np.int64)
        features = rng.normal(size=(len(frame), len(BASELINE_FEATURE_NAMES))).astype(np.float32)
        features[:, :5] += labels[:, None] * 2.0
        np.save(folder / f'features_{split}.npy', features, allow_pickle=False)
        np.save(folder / f'labels_{split}.npy', labels, allow_pickle=False)
        with gzip.open(folder / f'text_{split}.jsonl.gz', 'wt', encoding='utf-8') as handle:
            for label in labels:
                words = list(rng.choice(POSITIVE_WORDS if label else LEGIT_WORDS, size=12))
                handle.write(json.dumps(' '.join(words)) + '\n')
        for name in (f'{split}_metadata.csv', f'features_{split}.npy', f'labels_{split}.npy', f'text_{split}.jsonl.gz'):
            files[name] = file_digest(folder / name)
    manifest = {'kind': 'baseline_features', 'schema': 1, 'target_mode': 'phishing', 'seed': 42,
                'preprocessing': {'signature': 'test', 'lemmatization': False},
                'feature_names': list(BASELINE_FEATURE_NAMES), 'attachment_rules': {}, 'split_counts': {},
                'files': files}
    (folder / 'features_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return folder


class GroupingTests(unittest.TestCase):
    def test_every_real_source_has_a_group_and_unknown_sources_stop(self):
        groups = {source: ablation.dataset_group(source) for source in REAL_SOURCES}
        self.assertEqual(set(groups.values()), set(ablation.GROUPS))
        self.assertEqual({s for s, g in groups.items() if g == 'nazario'},
                         {s for s in REAL_SOURCES if s.startswith(('phishing-', 'phishing0', 'phishing1', 'phishing2',
                                                                   'phishing3', 'private-', '20051114'))})
        self.assertEqual(ablation.dataset_group('TREC_07.csv'), 'trec')
        with self.assertRaisesRegex(ValueError, 'mystery.csv'):
            ablation.dataset_group('mystery.csv')
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            ablation.annotate(pd.DataFrame({'Source': ['spamassassin'], 'Class': [1]}))

    def test_overlap_counts_cross_group_clusters_by_label_mix(self):
        frame = ablation.annotate(pd.DataFrame({
            'Source': ['EPVME', 'enron', 'EPVME', 'phishing-2020', 'EPVME', 'EPVME', 'Ling.csv', 'enron', 'trec07p'],
            'Class': [1, 0, 1, 1, 1, 1, 0, 0, 0],
            '_group': [1, 1, 2, 2, 3, 3, 4, 5, 5]}))
        empty = frame.iloc[0:0]
        report = ablation.overlap_report({'train': frame, 'validation': empty, 'test': empty})
        train = report[report.split == 'train'].set_index(['group_a', 'group_b'])
        self.assertEqual(train.loc[('epvme', 'enron'), ['clusters', 'mixed_label_clusters', 'same_label_clusters',
                                                         'rows_a', 'rows_b', 'mixed_rows_a', 'mixed_rows_b']].tolist(),
                         [1, 1, 0, 1, 1, 1, 1])
        self.assertEqual(train.loc[('epvme', 'nazario'), ['clusters', 'mixed_label_clusters', 'same_label_clusters']].tolist(),
                         [1, 0, 1])
        self.assertEqual(train.loc[('enron', 'trec'), ['clusters', 'same_label_clusters']].tolist(), [1, 1])
        self.assertEqual(len(train), 3)  # cụm 3 (chỉ EPVME) và cụm 4 (một dòng) không được đếm
        self.assertEqual(list(report.group_a.iloc[:2]), ['epvme', 'epvme'])  # cặp EPVME ưu tiên đứng đầu
        self.assertEqual(report[report.split == 'total'].clusters.sum(), 3)
        # Cụm vắt 3 nhóm: lẫn nhãn xét theo từng cặp, nên epvme × nazario vẫn là cùng nhãn.
        triple = ablation.annotate(pd.DataFrame({'Source': ['EPVME', 'phishing-2020', 'enron'], 'Class': [1, 1, 0],
                                                 '_group': [7, 7, 7]}))
        pairs = ablation.overlap_report({'train': triple, 'validation': empty, 'test': empty})
        pairs = pairs[pairs.split == 'train'].set_index(['group_a', 'group_b']).mixed_label_clusters.to_dict()
        self.assertEqual(pairs, {('epvme', 'nazario'): 0, ('epvme', 'enron'): 1, ('enron', 'nazario'): 1})
        both = ablation.overlap_report({'train': triple, 'validation': empty, 'test': empty})
        both = both[both.split == 'train'].set_index(['group_a', 'group_b']).clusters_with_both_labels.to_dict()
        self.assertEqual(both, {('epvme', 'nazario'): 1, ('epvme', 'enron'): 1, ('enron', 'nazario'): 1})
        self.assertEqual(train.loc[('epvme', 'nazario'), 'clusters_with_both_labels'], 0)


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from train import load_exported_features
        cls.root = Path(tempfile.mkdtemp())
        cls.features = build_export(cls.root / 'features')
        cls.output = cls.root / 'ablation'
        cls.metadata, cls.manifest = ablation.load_metadata(cls.features)
        cls.frames, _ = load_exported_features(cls.features)
        cls.digest = ablation.file_sha256(cls.features / 'features_manifest.json')
        ablation.claim_output(cls.output, cls.features, cls.digest)  # như CLI: thư mục có marker
        for name in ('reference', 'reference_seed43', 'without_epvme', 'without_ling', 'without_enron_trec', 'only_malspam',
                     'random_like_nazario'):
            state = cls.run_named(name)
            assert state == 'complete', (name, state)
        cls.written = ablation.summarize(cls.output, cls.metadata['test'])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def run_named(cls, name):
        return ablation.run_experiment(name, cls.frames, cls.metadata, cls.manifest, cls.digest, cls.output,
                                       epochs=2, candidates=small_candidates)

    def stored(self, name):
        return json.loads((self.output / name / 'experiment.json').read_text(encoding='utf-8'))

    def test_removal_keeps_test_and_drops_only_the_intended_rows(self):
        test_ids = {self.stored(name)['test_record_ids_sha256'] for name in
                    ('reference', 'without_epvme', 'only_malspam', 'random_like_nazario')}
        self.assertEqual(len(test_ids), 1)
        masks = ablation.removal_masks(self.metadata, ablation.EXPERIMENTS['without_epvme'])
        for split in ('train', 'validation'):
            kept = self.metadata[split][~masks[split]]
            self.assertNotIn('epvme', set(kept.Group))
        self.assertFalse(masks['test'].any())
        only = ablation.removal_masks(self.metadata, ablation.EXPERIMENTS['only_malspam'])
        for split in ('train', 'validation'):
            kept = self.metadata[split][~only[split]]
            self.assertEqual(set(kept[kept.Class == 1].Group), {'malspam'})
            self.assertEqual((kept.Class == 0).sum(), (self.metadata[split].Class == 0).sum())
        groups = pd.read_csv(self.output / 'without_epvme' / 'test_by_group.csv')
        self.assertEqual(set(groups[groups.held_out].Group), {'epvme'})
        self.assertEqual(self.stored('without_epvme')['split_counts']['train']['removed_by_group'], {'epvme': ROWS})

    def test_random_removal_is_stratified_by_group_and_skips_large_clusters(self):
        details = {}
        masks = ablation.removal_masks(self.metadata, ablation.EXPERIMENTS['random_like_nazario'], details)
        reference = ablation.removal_masks(self.metadata, ablation.EXPERIMENTS['without_nazario'])
        for split in ('train', 'validation'):
            frame, removed = self.metadata[split], masks[split]
            target = int(reference[split].sum())
            self.assertLessEqual(abs(int(removed.sum()) - target), target * ablation.RANDOM_TOLERANCE)
            self.assertTrue((frame.Class[removed] == 1).all())
            for _, cluster in frame.assign(removed=removed).groupby('_group'):
                self.assertEqual(cluster.removed.nunique(), 1)  # không cụm nào bị tách đôi
            # Phân tầng: mỗi nhóm bỏ theo tỷ lệ của nó trên toàn bộ mẫu dương, trong ±2%.
            positives = frame.Group[frame.Class == 1].value_counts()
            for group, info in details[split]['groups'].items():
                self.assertLessEqual(abs(info['target'] - target * positives[group] / positives.sum()), 1)
                self.assertEqual(info['removed_rows'], int((frame.Group[removed] == group).sum()))
                self.assertLessEqual(abs(info['removed_rows'] - info['target']),
                                     info['target'] * ablation.GROUP_TOLERANCE)
            self.assertEqual(details[split]['without_nazario_clusters'],
                             frame._group[frame.Group == 'nazario'].nunique())
        train = self.metadata['train']
        # Cụm template 5 dòng EPVME (> 5% của 40) bị loại và không bao giờ được bốc; cụm lẫn nhãn cũng vậy.
        self.assertEqual(details['train']['excluded_large_clusters'], [{'group': 'epvme', 'size': 5}])
        # EPVME train: 1 dòng cụm lẫn nhãn, 1 dòng cụm chung với Nazario, 5 dòng cụm template.
        self.assertEqual(details['train']['groups']['epvme']['undrawable_rows'], 7)
        self.assertEqual(details['train']['groups']['nazario']['undrawable_rows'], 1)
        sizes = train.groupby('_group').size()
        self.assertFalse(masks['train'][train._group.isin(sizes[sizes > 2].index)].any())
        mixed = train.groupby('_group').Class.nunique()
        self.assertFalse(masks['train'][train._group.isin(mixed[mixed > 1].index)].any())
        self.assertEqual(self.stored('random_like_nazario')['random_control']['train']['removed_rows'],
                         int(masks['train'].sum()))
        too_big = pd.DataFrame({'_group': [1, 1, 1], 'Class': [1, 1, 1], 'Group': ['epvme'] * 3})
        with self.assertRaisesRegex(ValueError, '±2%'):
            ablation.stratified_cluster_mask(too_big, 3, np.random.default_rng(0))

    def test_metrics_cover_groups_pairwise_auc_and_epvme_free_overall(self):
        from sklearn.metrics import roc_auc_score
        overall = pd.read_csv(self.output / 'reference' / 'test_overall.csv')
        test = self.metadata['test']
        no_epvme = overall[(overall.Scope == 'without_epvme') & (overall.Model == 'Logistic Regression')].iloc[0]
        self.assertEqual(no_epvme.Count, int((test.Group != 'epvme').sum()))
        groups = pd.read_csv(self.output / 'reference' / 'test_by_group.csv')
        row = groups[(groups.Model == 'Logistic Regression') & (groups.Group == 'malspam')].iloc[0]
        scores = np.load(self.output / 'reference' / 'test_scores.npz', allow_pickle=False)['Logistic Regression']
        chosen = np.flatnonzero((test.Group == 'malspam').to_numpy())
        legit = np.flatnonzero(test.Class.to_numpy() == 0)
        idx = np.concatenate([chosen, legit])
        self.assertAlmostEqual(row['Pair-ROC-AUC'], roc_auc_score(test.Class.to_numpy()[idx], scores[idx]))
        self.assertEqual(row.TP + row.FN, len(chosen))
        self.assertEqual(row['Rate-name'], 'Recall')
        enron = groups[(groups.Model == 'Logistic Regression') & (groups.Group == 'enron')].iloc[0]
        self.assertEqual((enron['Rate-name'], enron.TP + enron.FN, enron.FP + enron.TN), ('FPR', 0, 2 * ROWS))
        sources = pd.read_csv(self.output / 'reference' / 'test_by_source.csv')
        self.assertEqual(set(sources.Source), set(SOURCES))

    def test_threshold_constraint_flag_marks_fallback_thresholds(self):
        models = self.stored('reference')['models']
        self.assertFalse(models['Dummy']['threshold_constraint_met'])
        self.assertEqual(models['Dummy']['threshold_constraint_met'], models['Dummy']['precision_target_met'])
        overall = pd.read_csv(self.output / 'summary_overall.csv')
        self.assertFalse(overall[overall.Model == 'Dummy'].threshold_constraint_met.any())

    def test_resume_lock_and_definition_mismatch(self):
        self.assertEqual(self.run_named('reference'), 'complete')  # đã xong: bỏ qua, không train lại
        folder = self.output / 'without_phishing_pot'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'lock').write_text('pid=1')
        self.assertEqual(self.run_named('without_phishing_pot'), 'locked')
        self.assertFalse((folder / 'experiment.json').exists())
        self.assertEqual(ablation.main(['--features', str(self.features), '--output', str(self.output),
                                        '--unlock', 'without_phishing_pot']), 0)
        self.assertFalse((folder / 'lock').exists())
        path = self.output / 'only_malspam' / 'experiment.json'
        original = path.read_text(encoding='utf-8')
        try:
            path.write_text(original.replace(self.digest, '0' * 64), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'different export or definition'):
                self.run_named('only_malspam')
        finally:
            path.write_text(original, encoding='utf-8')
        with self.assertRaises(SystemExit):
            ablation.main(['--features', str(self.features), '--output', str(self.output), '--experiments', 'bogus'])
        with self.assertRaises(SystemExit):  # epoch < 1 bị từ chối, không lặng lẽ thành 40
            ablation.main(['--features', str(self.features), '--output', str(self.output), '--doc2vec-epochs', '0'])
        # Số epoch khác cũng là định nghĩa khác: không dùng lại kết quả 2 epoch cho lần chạy 3 epoch.
        with self.assertRaisesRegex(RuntimeError, 'different export or definition'):
            ablation.run_experiment('reference', self.frames, self.metadata, self.manifest, self.digest, self.output,
                                    epochs=3, candidates=small_candidates)

    def test_interrupted_and_failed_experiments_rerun_and_release_the_lock(self):
        folder = self.output / 'without_nazario'
        folder.mkdir(parents=True, exist_ok=True)
        record = ablation.definition_record('without_nazario', self.digest, 2)
        ablation.save_json(folder / 'experiment.json', {**record, 'status': 'running'})  # bị ngắt, không còn lock
        self.assertEqual(self.run_named('without_nazario'), 'complete')
        self.assertEqual(self.stored('without_nazario')['status'], 'complete')

        def broken(y, seed):
            raise MemoryError('simulated')
        with self.assertRaises(MemoryError):
            ablation.run_experiment('without_trec', self.frames, self.metadata, self.manifest, self.digest,
                                    self.output, epochs=2, candidates=broken)
        failed = self.stored('without_trec')
        self.assertEqual((failed['status'], failed['error']), ('failed', "MemoryError('simulated')"))
        self.assertFalse((self.output / 'without_trec' / 'lock').exists())
        self.assertEqual(self.run_named('without_trec'), 'complete')  # lỗi trước đó không chặn lần chạy lại

    def test_list_reports_counts_and_status(self):
        listing = ablation.list_experiments(self.metadata, self.output).set_index('experiment')
        self.assertEqual(list(listing.index), list(ablation.EXPERIMENTS))
        self.assertEqual(listing.loc['reference', 'status'], 'complete')
        counts = self.stored('without_epvme')['split_counts']['train']
        self.assertEqual(listing.loc['without_epvme', ['train_pos', 'removed_train']].tolist(),
                         [counts['kept']['1'], sum(counts['removed'].values())])

    def test_output_folder_is_claimed_and_mixed_summaries_are_refused(self):
        foreign = self.root / 'foreign_run'
        foreign.mkdir()
        (foreign / 'evaluation_results.csv').write_text('x')
        with self.assertRaisesRegex(RuntimeError, 'not a dataset ablation folder'):
            ablation.claim_output(foreign, self.features, self.digest)
        with self.assertRaisesRegex(RuntimeError, 'must differ'):
            ablation.claim_output(self.features, self.features, self.digest)
        claimed = self.root / 'claimed'
        ablation.claim_output(claimed, self.features, self.digest)
        ablation.claim_output(claimed, self.features, self.digest)  # cùng bản xuất: dùng tiếp được
        with self.assertRaisesRegex(RuntimeError, 'another feature export'):
            ablation.claim_output(claimed, self.features, '0' * 64)
        mixed = self.root / 'mixed'
        for name in ('reference', 'without_epvme'):
            shutil.copytree(self.output / name, mixed / name)
        path = mixed / 'without_epvme' / 'experiment.json'
        path.write_text(path.read_text(encoding='utf-8').replace(self.digest, '0' * 64), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'mixes experiments'):
            ablation.summarize(mixed)

    def test_cli_trains_selected_experiment_under_hash_seed_zero(self):
        import os
        import subprocess
        target = self.root / 'cli_run'
        environment = {k: v for k, v in os.environ.items() if k != 'PYTHONHASHSEED'}
        result = subprocess.run([sys.executable, str(ROOT / 'dataset_ablation.py'), '--features', str(self.features),
                                 '--output', str(target), '--experiments', 'reference', '--doc2vec-epochs', '2'],
                                env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])
        self.assertEqual(sorted(p.name for p in target.iterdir() if p.is_dir()), ['reference'])
        stored = json.loads((target / 'reference' / 'experiment.json').read_text(encoding='utf-8'))
        self.assertEqual((stored['status'], stored['python_hash_seed'], stored['doc2vec_epochs']), ('complete', '0', 2))
        self.assertEqual(len(stored['models']), 9)  # build_candidates mặc định: đủ 9 classifier
        self.assertIn('sklearn', stored['environment'])
        if stored['environment']['git_commit'] is not None:  # không có git thì ghi None
            self.assertRegex(stored['environment']['git_commit'], r'^[0-9a-f]{40}$')  # kết quả gắn với commit
        self.assertIn(stored['environment']['git_code_dirty'], (True, False, None))
        self.assertEqual(stored['code_changed_during_run'], [])
        self.assertTrue((target / 'summary_overall.csv').exists())

    def test_cli_overlap_writes_report_and_empty_summary_fails_clearly(self):
        target = self.root / 'cli'
        self.assertEqual(ablation.main(['--features', str(self.features), '--output', str(target), '--overlap']), 0)
        report = pd.read_csv(target / 'overlap_by_group.csv')
        self.assertEqual(report[(report.split == 'total') & (report.group_a == 'epvme')
                                & (report.group_b == 'enron')].mixed_label_clusters.tolist(), [1])
        self.assertFalse(any(p.is_dir() for p in target.iterdir()))  # không train thí nghiệm nào
        with self.assertRaisesRegex(RuntimeError, 'No completed experiment'):
            ablation.summarize(target)

    def test_combined_removal_and_score_breakdowns(self):
        stored = self.stored('without_enron_trec')
        self.assertEqual(stored['held_out_groups'], ['enron', 'trec'])
        self.assertEqual(stored['split_counts']['train']['removed_by_group'], {'enron': 2 * ROWS, 'trec': ROWS})
        test = self.metadata['test']
        nazario = pd.read_csv(self.output / 'summary_nazario_by_cluster.csv')
        lr = nazario[(nazario.Experiment == 'reference') & (nazario.Model == 'Logistic Regression')].set_index('Subset')
        self.assertEqual(lr.loc['nazario_in_epvme_cluster', 'Support'], 2)
        self.assertEqual(lr.loc['nazario_only_cluster', 'Support'], int((test.Group == 'nazario').sum()) - 2)
        scores = np.load(self.output / 'reference' / 'test_scores.npz', allow_pickle=False)['Logistic Regression']
        threshold = self.stored('reference')['models']['Logistic Regression']['threshold']
        shared = test._group.isin(set(test._group[test.Group == 'epvme'])) & (test.Group == 'nazario')
        self.assertEqual(lr.loc['nazario_in_epvme_cluster', 'TP'], int((scores[shared.to_numpy()] >= threshold).sum()))
        attacks = pd.read_csv(self.output / 'summary_epvme_by_attack.csv')
        ref = attacks[(attacks.Experiment == 'reference') & (attacks.Model == 'Logistic Regression')]
        self.assertEqual(dict(zip(ref['Attack-family (heuristic)'], ref.Support)), {'mime_wrapping': 30, 'xss': 10})
        with self.assertRaisesRegex(RuntimeError, 'different test rows'):
            ablation.score_breakdowns(self.output, {'reference': self.stored('reference')}, test.iloc[::-1])

    def test_summary_deltas_fixed_family_cross_source_and_seed_spread(self):
        for name in ('summary_overall.csv', 'summary_by_group.csv', 'summary_fixed_classifier.csv',
                     'summary_cross_source.csv', 'seed_spread.csv', 'heatmap_fixed_recall.png',
                     'heatmap_cross_source.png'):
            self.assertIn(name, self.written)
            self.assertTrue((self.output / name).exists(), name)
        overall = pd.read_csv(self.output / 'summary_overall.csv')
        reference = overall[overall.Experiment == 'reference']
        self.assertTrue(reference.delta_Recall.isna().all())
        self.assertTrue(overall[overall.Experiment != 'reference'].delta_Recall.notna().all())
        lr = overall[(overall.Model == 'Logistic Regression') & (overall.Scope == 'all')].set_index('Experiment')
        self.assertAlmostEqual(lr.loc['without_epvme', 'delta_Recall'],
                               lr.loc['without_epvme', 'Recall'] - lr.loc['reference', 'Recall'])
        family = self.stored('reference')['selected_model']
        fixed = pd.read_csv(self.output / 'summary_fixed_classifier.csv')
        self.assertEqual(set(fixed.Model), {family})
        cross = pd.read_csv(self.output / 'summary_cross_source.csv', index_col=0)
        self.assertEqual(set(cross.index), {'reference', 'only_malspam'})
        self.assertEqual(list(cross.columns), ['Model'] + list(ablation.POSITIVE_GROUPS))
        # Seed phải thật sự đổi Doc2Vec/classifier: điểm test của hai seed khác nhau.
        self.assertNotEqual(self.stored('reference')['test_scores_sha256'],
                            self.stored('reference_seed43')['test_scores_sha256'])
        groups = pd.read_csv(self.output / 'summary_by_group.csv')
        ling = groups[(groups.Experiment == 'without_ling') & (groups.Group == 'ling')]
        self.assertTrue(ling.held_out.all())
        self.assertEqual(set(ling['Rate-name']), {'FPR'})
        selected = groups[(groups.Experiment == 'without_epvme') & groups['Selected-on-validation']].iloc[0]
        reference_selected = groups[(groups.Experiment == 'reference') & groups['Selected-on-validation']
                                    & (groups.Group == selected.Group)].iloc[0]
        self.assertAlmostEqual(selected.delta_vs_reference_selected_Rate, selected.Rate - reference_selected.Rate)
        own = groups[groups.Experiment == 'reference']
        self.assertTrue(own.delta_Rate.isna().all() and own.delta_vs_reference_selected_Rate.isna().all())
        spread = pd.read_csv(self.output / 'seed_spread.csv')
        self.assertEqual(set(spread['count']), {2})
        self.assertIn('malspam', set(spread.Subset))  # theo nhóm, không chỉ tổng thể
        self.assertIn('all', set(spread.Subset))

    def environment_zero(self):
        return mock.patch.dict('os.environ', {'PYTHONHASHSEED': '0'})

    def test_failed_experiments_are_listed_before_the_summary_and_exit_one(self):
        def fake(name, *args, **kwargs):
            if name == 'without_malspam':
                raise MemoryError('simulated')
            return 'complete'
        output = StringIO()
        with self.environment_zero(), mock.patch.object(ablation, 'run_experiment', side_effect=fake), \
                redirect_stdout(output):
            code = ablation.main(['--features', str(self.features), '--output', str(self.output),
                                  '--experiments', 'reference', 'without_malspam'])
        text = output.getvalue()
        self.assertEqual(code, 1)
        self.assertLess(text.index('Failed experiments: without_malspam'), text.index('Summary written'))

    def test_definition_mismatch_stops_the_whole_queue(self):
        calls = []

        def fake(name, *args, **kwargs):
            calls.append(name)
            raise ablation.DefinitionMismatch('different definition')
        with self.environment_zero(), mock.patch.object(ablation, 'run_experiment', side_effect=fake), \
                redirect_stdout(StringIO()):
            with self.assertRaises(ablation.DefinitionMismatch):
                ablation.main(['--features', str(self.features), '--output', str(self.output),
                               '--experiments', 'without_malspam', 'without_ceas'])
        self.assertEqual(calls, ['without_malspam'])

    def test_summarize_cli(self):
        with self.environment_zero(), redirect_stdout(StringIO()) as output:
            self.assertEqual(ablation.main(['--features', str(self.features), '--output', str(self.output),
                                            '--summarize']), 0)
        self.assertIn('summary_overall.csv', output.getvalue())

    def test_recheck_after_lock_never_overwrites_a_result(self):
        folder = self.output / 'without_ceas'
        # Tiến trình khác xong đúng lúc giữa lần kiểm tra đầu và lúc lấy lock: bỏ qua, nhả lock, không ghi gì.
        with mock.patch.object(ablation, 'experiment_state', side_effect=['pending', 'complete']):
            self.assertEqual(self.run_named('without_ceas'), 'complete')
        self.assertFalse((folder / 'lock').exists())
        self.assertFalse((folder / 'experiment.json').exists())
        # Kết quả của tiến trình kia khác định nghĩa: báo lỗi, giữ nguyên file của nó, không ghi "failed".
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'experiment.json').write_text('{"status": "complete"}', encoding='utf-8')
        with mock.patch.object(ablation, 'experiment_state',
                               side_effect=['pending', ablation.DefinitionMismatch('different')]):
            with self.assertRaises(ablation.DefinitionMismatch):
                self.run_named('without_ceas')
        self.assertEqual((folder / 'experiment.json').read_text(encoding='utf-8'), '{"status": "complete"}')
        self.assertFalse((folder / 'lock').exists())
        shutil.rmtree(folder)

    def test_code_edited_after_the_process_started_is_refused(self):
        folder = self.output / 'without_spamassassin'
        with mock.patch.dict(ablation._LOADED_CODE, {'train.py': '0' * 64}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'changed after this process started'):
                self.run_named('without_spamassassin')
        self.assertEqual(self.stored('without_spamassassin')['status'], 'failed')
        self.assertFalse((folder / 'lock').exists())
        shutil.rmtree(folder)

    def test_output_inside_an_export_or_another_run_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'inside the --features folder'):
            ablation.claim_output(self.features / 'ablation', self.features, self.digest)
        with self.assertRaisesRegex(RuntimeError, 'inside another run or ablation folder'):
            ablation.claim_output(self.output / 'nested', self.features, self.digest)
        run = self.root / 'some_run'
        run.mkdir()
        (run / 'manifest.json').write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'inside another run or ablation folder'):
            ablation.claim_output(run / 'ablation', self.features, self.digest)
        claimed = self.root / 'claimed_marker'
        ablation.claim_output(claimed, self.features, self.digest)
        self.assertNotIn('definition_version', json.loads((claimed / ablation.MARKER).read_text(encoding='utf-8')))


class StratificationTests(unittest.TestCase):
    def test_stratum_targets_use_largest_remainder(self):
        frame = pd.DataFrame({'Group': ['nazario'] * 5 + ['phishing_pot'] * 3 + ['epvme'] * 2 + ['enron'] * 4,
                              'Class': [1] * 10 + [0] * 4})
        # 7 × (5, 3, 2) / 10 = 3.5, 2.1, 1.4 -> sàn 3, 2, 1; phần dư 1 về phần lẻ lớn nhất (Nazario).
        self.assertEqual(ablation._stratum_targets(frame, 7), {'nazario': 4, 'phishing_pot': 2, 'epvme': 1})

    def test_total_tolerance_is_enforced_and_parameters_come_from_the_caller(self):
        # Mỗi nhóm chỉ bốc được cụm 49 dòng (dòng còn lại nằm trong cụm lẫn nhãn): từng nhóm -2% hợp lệ,
        # nhưng tổng 98/100 lệch quá ±1%.
        frame = pd.DataFrame({'_group': [1] * 49 + [2, 2] + [3] * 49 + [4, 4],
                              'Class': [1] * 49 + [1, 0] + [1] * 49 + [1, 0],
                              'Group': ['nazario'] * 49 + ['nazario', 'enron'] + ['epvme'] * 49 + ['epvme', 'enron']})
        with self.assertRaisesRegex(ValueError, 'not within ±1% of 100'):
            ablation.stratified_cluster_mask(frame, 100, np.random.default_rng(0), max_cluster_share=1.0)
        with self.assertRaisesRegex(ValueError, '±2%'):  # mặc định 5%: cụm 49 dòng quá lớn để bốc
            ablation.stratified_cluster_mask(frame, 100, np.random.default_rng(0))
        mask, details = ablation.stratified_cluster_mask(frame, 100, np.random.default_rng(0),
                                                         max_cluster_share=1.0, total_tolerance=0.02)
        self.assertEqual((int(mask.sum()), details['groups']['nazario']['undrawable_rows']), (98, 1))

    def test_stratum_ceiling_keeps_the_total_within_tolerance(self):
        # Cụm 1-3 dòng: nhóm đầu có thể vượt chỉ tiêu 1 dòng; nhóm sau phải bù để tổng không vượt ±1%.
        rng = np.random.default_rng(7)
        rows = []
        for group in ('nazario', 'phishing_pot'):
            size_left, key = 100, len(rows)
            while size_left:
                size = int(min(size_left, rng.integers(1, 4)))
                rows += [{'_group': f'{group}{key}', 'Class': 1, 'Group': group}] * size
                size_left -= size
                key += 1
        frame = pd.DataFrame(rows)
        for seed in range(200):
            mask, details = ablation.stratified_cluster_mask(frame, 100, np.random.default_rng(seed),
                                                             max_cluster_share=1.0)
            self.assertLessEqual(abs(int(mask.sum()) - 100), 1, seed)


if __name__ == '__main__':
    unittest.main()
