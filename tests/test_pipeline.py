import csv
import hashlib
import importlib.util
import json
import mailbox
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

import numpy as np
import pandas as pd
from email.message import EmailMessage

import load_data
from dataset_audit import record_id
from pipeline_cache import PreprocessingCache
from preprocess import cleanText, remove_stopwords, group_email_variants, compute_dedup_key, _simhash, URL_REGEX
from specialists import prepare_specialists, train_specialists, run_specialists, evaluate_specialists, BRANCHES
from train import load_training_emails, select_label_scope, prepare_data


def email_bytes(index, positive=False):
    msg = EmailMessage()
    msg['Subject'] = f'Notice {index}'
    msg['From'] = ('Account <support@gmail.com>' if positive else 'Colleague <colleague@example.org>')
    msg['To'] = 'recipient@example.org'
    msg['Reply-To'] = 'other@example.invalid' if positive else 'colleague@example.org'
    # Short unique bodies avoid accidentally forming one giant near-duplicate group.
    msg.set_content(f'Message identifier {index}: please read https://example.invalid/{index}')
    msg.add_alternative(f'<html><body>Message identifier {index} '
                        f'<a href="https://example.invalid/{index}">Open</a>'
                        + ('<script>const marker=1;</script>' if index % 3 == 0 else '')
                        + '</body></html>', subtype='html')
    msg.add_attachment(f'Harmless test fixture {index}'.encode(), maintype='application',
                       subtype='octet-stream', filename=f'note-{index}.txt')
    return msg.as_bytes()


def training_frame(count=180):
    rows = []
    for index in range(count):
        location = f'synthetic:message:{index}'
        positive = bool(index % 2)
        rows.append({'Text': email_bytes(index, positive), 'Class': int(positive),
                     'Source': 'synthetic', 'Location': location,
                     'LabelKind': 'phishing' if positive else 'legitimate',
                     'OriginalLabel': str(int(positive)), 'LabelBasis': 'synthetic test fixture',
                     'RecordId': record_id(location)})
    return pd.DataFrame(rows)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_ingestion_accounts_multiline_malformed_unknown_hidden_and_mbox(self):
        dataset = self.root / 'Dataset'
        (dataset / 'phishing').mkdir(parents=True)
        (dataset / 'enron' / '.hidden').mkdir(parents=True)
        (dataset / 'enron' / '.hidden' / 'mail.md').write_bytes(email_bytes(1))
        (dataset / 'enron' / 'unknown').write_bytes(b'not a MIME email')
        (dataset / 'enron' / 'empty').write_bytes(b'')
        (dataset / 'enron' / 'README.md').write_text('Dataset documentation')
        box = mailbox.mbox(str(dataset / 'phishing' / 'phishing0.mbox'), create=True)
        for index in range(4):
            box.add(email_bytes(10 + index, True))
        box.close()
        with (dataset / 'phishing' / 'extra.csv').open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(['subject', 'body', 'label'])
            writer.writerow(['Subject', 'A multiline\nbody', 'phishing'])
            writer.writerow(['Bad', 'alignment', 'phishing', 'extra field'])
            writer.writerow(['', '', 'ham'])
        with (dataset / 'phishing' / 'vectors.csv').open('w', newline='') as handle:
            handle.write('0,label\n1,0\n2,1\n')
        output = self.root / 'load'
        data = load_training_emails(output, dataset)
        self.assertEqual(len(data), 7)
        self.assertEqual(int(data.Class.isna().sum()), 1)
        summary = json.loads((output / 'load_summary.json').read_text())
        self.assertEqual(summary['status'], 'complete')
        self.assertEqual(summary['record_outcomes'], {'loaded': 7, 'no_email_content': 2, 'quarantined': 3})
        self.assertEqual(summary['file_outcomes'], {'complete': 6, 'metadata': 1})
        with closing(sqlite3.connect(output / 'ingestion.sqlite')) as db:
            quarantined = db.execute("SELECT rejected_payload FROM records WHERE status='quarantined'").fetchall()
        self.assertTrue(all(value[0] is not None for value in quarantined))

    def test_unreadable_archive_stops_instead_of_silently_losing_file(self):
        dataset = self.root / 'Dataset'
        (dataset / 'phishing').mkdir(parents=True)
        (dataset / 'enron').mkdir()
        (dataset / 'phishing' / 'not_extracted.zip').write_bytes(b'PK fixture')
        with self.assertRaises(RuntimeError):
            load_training_emails(self.root / 'load', dataset)
        summary = json.loads((self.root / 'load/load_summary.json').read_text())
        self.assertEqual(summary['status'], 'incomplete')
        self.assertEqual(summary['file_outcomes']['failed'], 1)

    def test_negations_are_kept_in_doc2vec_text(self):
        for phrase in ("Don't share", "Do not share", "You can't share", "You won’t share", "It isn't safe"):
            msg = EmailMessage(); msg.set_content(phrase)
            self.assertIn('not', remove_stopwords(cleanText(msg.as_bytes())).split())

    def test_parallel_cache_preserves_order_and_matches_uncached_features(self):
        frame = training_frame(12)
        frame.loc[len(frame)] = frame.iloc[0]
        with PreprocessingCache(self.root / 'cache', workers=1, batch_size=5) as cache:
            sequential = cache.prepare(frame, 'identity', self.root)
            sequential = cache.prepare(sequential, 'features', self.root)
        with PreprocessingCache(self.root / 'other-cache', workers=2, batch_size=5) as cache:
            parallel = cache.prepare(frame, 'identity', self.root)
            parallel = cache.prepare(parallel, 'features', self.root)
        for field in ('RecordId', '_features', '_dedup_key', '_semantic_text', '_clean_text', '_html_features',
                      '_message_security'):
            self.assertEqual(sequential[field].to_list(), parallel[field].to_list())
        with PreprocessingCache(self.root / 'cache', workers=1) as cache:
            warm = cache.prepare(frame, 'features', self.root)
        self.assertEqual(len(warm), len(frame))
        stats = json.loads((self.root / 'preprocessing_features.json').read_text())
        self.assertEqual(stats['computed'], 0)
        self.assertEqual(stats['cache_hits'], len(frame))

    def test_processing_error_is_recorded_and_stops(self):
        frame = training_frame(3)
        with PreprocessingCache(self.root / 'cache', workers=1) as cache:
            with patch('pipeline_cache._process', return_value={'_error': 'fixture failure'}):
                with self.assertRaises(RuntimeError):
                    cache.prepare(frame, 'identity', self.root)
        errors = pd.read_csv(self.root / 'preprocessing_identity_errors.csv')
        self.assertEqual(set(errors.RecordId), set(frame.RecordId))

    def test_shared_attachment_stays_in_one_group_despite_different_bodies(self):
        messages = []
        for body in ('First independent body', 'Completely unrelated second message'):
            msg = EmailMessage(); msg['Subject'] = body; msg.set_content(body)
            msg.add_attachment(b'identical harmless fixture payload', maintype='application',
                               subtype='octet-stream', filename='shared.txt')
            messages.append(msg.as_bytes())
        frame = pd.DataFrame({'Text': messages})
        with PreprocessingCache(self.root / 'cache', workers=1) as cache:
            frame = cache.prepare(frame, 'identity', self.root)
        self.assertNotEqual(frame._dedup_key.iloc[0], frame._dedup_key.iloc[1])
        grouped = group_email_variants(frame, group_attachments=True)
        self.assertEqual(grouped[0], grouped[1])

    def test_vectorized_simhash_matches_reference_bit_voting(self):
        import re
        for length in (0, 19, 20, 50, 400, 5000):
            text = ' '.join(hashlib.sha256(str(index).encode()).hexdigest() for index in range(length))
            normalized = re.sub(r'\d+', '0', URL_REGEX.sub(' URL ', text))
            words = re.findall(r'\w+', normalized)
            if len(words) < 20:
                expected = None
            else:
                votes = [0] * 64
                for shingle in {' '.join(words[i:i + 3]) for i in range(len(words) - 2)}:
                    value = int.from_bytes(hashlib.blake2b(shingle.encode(), digest_size=8).digest(), 'big')
                    for bit in range(64):
                        votes[bit] += 1 if value & (1 << bit) else -1
                expected = sum(1 << bit for bit, vote in enumerate(votes) if vote >= 0)
            self.assertEqual(_simhash(text), expected)

    def test_every_loaded_row_has_selection_disposition_and_empty_conflict_report(self):
        frame = training_frame(6)
        duplicate = frame.iloc[0].copy(); duplicate.RecordId = record_id('duplicate')
        conflict = frame.iloc[1].copy(); conflict.Class = 0; conflict.LabelKind = 'legitimate'; conflict.RecordId = record_id('conflict')
        unknown = frame.iloc[2].copy(); unknown.Class = np.nan; unknown.RecordId = record_id('unknown')
        spam = frame.iloc[3].copy(); spam.Text = email_bytes(999); spam.LabelKind = 'spam'; spam.RecordId = record_id('spam')
        frame = pd.concat([frame, pd.DataFrame([duplicate, conflict, unknown, spam])], ignore_index=True)
        selected = select_label_scope(frame, 'phishing', self.root)
        audit = pd.read_csv(self.root / 'training_dispositions.csv')
        self.assertEqual(len(audit), len(frame))
        self.assertEqual(audit.RecordId.nunique(), len(frame))
        self.assertEqual(len(selected), int(audit.Disposition.eq('selected').sum()))
        self.assertEqual(set(audit.Disposition), {'selected', 'duplicate_content', 'conflicting_labels',
                                                'unknown_label_or_missing_content', 'outside_label_scope'})
        select_label_scope(training_frame(4), 'phishing', self.root)
        self.assertEqual(len(pd.read_csv(self.root / 'label_conflicts.csv')), 0)

    def test_specialists_use_only_own_features_and_do_not_invent_malware_labels(self):
        frame = training_frame()
        parts, settings = prepare_specialists(frame, self.root, self.root / 'cache', workers=1)
        manifest = train_specialists(parts, self.root, preprocessing=settings, train_text=False)
        self.assertEqual(manifest['status'], 'partial')
        self.assertEqual(manifest['branches']['text']['status'], 'ready_to_train')
        self.assertEqual(manifest['branches']['html']['status'], 'awaiting_labels')
        self.assertEqual(manifest['branches']['attachment']['status'], 'awaiting_labels')
        self.assertEqual(manifest['branches']['header']['status'], 'trained')
        self.assertEqual(manifest['branches']['url']['status'], 'trained')
        self.assertEqual(manifest['target_mode'], 'phishing')
        by_source = pd.read_csv(self.root / 'specialist_evaluation_by_source.csv')
        self.assertEqual(set(by_source.Branch), {'header', 'url'})
        recomputed = evaluate_specialists(self.root)
        self.assertEqual(set(recomputed.Branch), {'header', 'url'})
        original = pd.read_csv(self.root / 'specialist_evaluation.csv', float_precision='round_trip')
        for column in ('Precision', 'Recall', 'F1-score', 'TN', 'FP', 'FN', 'TP'):
            self.assertTrue(np.allclose(recomputed[column], original[column]))
        self.assertEqual(len(BRANCHES), 5)
        for name in ('header', 'url'):
            with (self.root / f'{name}.pkl').open('rb') as f:
                import pickle
                model = pickle.load(f)
            self.assertEqual(model.n_features_in_, len(BRANCHES[name]['features']))
        from predict_specialists import EmailSpecialists
        prediction = EmailSpecialists(self.root).assess(email_bytes(1000))
        self.assertIn('html', prediction['unassessed_branches'])
        self.assertEqual(prediction['malware_alerts'], [])
        self.assertEqual(set(prediction['branches']), set(BRANCHES))
        empty_msg = EmailMessage(); empty_msg.set_content('Plain note without URLs')
        unavailable = EmailSpecialists(self.root).assess(empty_msg.as_bytes())
        for name in ('header', 'url', 'html', 'attachment'):
            self.assertEqual(unavailable['branches'][name]['status'], 'no_applicable_input')
        combined = pd.concat(parts.values())
        for left, right in (('train','validation'), ('train','test'), ('validation','test')):
            self.assertTrue(set(parts[left]._group).isdisjoint(parts[right]._group))
        self.assertEqual(set(combined.RecordId), set(frame.RecordId))
        # Explicit synthetic target differs from the email phishing label.
        labels = combined[['RecordId']].copy()
        labels['html_malicious'] = [int(int(r.split(':')[-1]) % 3 == 0) for r in combined.Location]
        labels['attachment_malicious'] = [int(int(r.split(':')[-1]) % 4 == 0) for r in combined.Location]
        labels['label_basis'] = 'Synthetic test labels; not malware ground truth'
        label_path = self.root / 'fixture_labels.csv'; labels.to_csv(label_path, index=False)
        trained = self.root / 'labelled'; trained.mkdir()
        full = train_specialists(parts, trained, branch_labels=label_path, preprocessing=settings, train_text=False)
        for name in ('html', 'attachment'):
            self.assertEqual(full['branches'][name]['status'], 'trained')
            observed = pd.read_csv(trained / f'{name}_test_scores.csv').set_index('RecordId').Label
            expected = labels.set_index('RecordId')[BRANCHES[name]['target']]
            self.assertEqual(observed.to_dict(), expected.loc[observed.index].to_dict())
        resumed = run_specialists(self.root / 'resumed', resume=self.root, prepare_only=True)
        self.assertEqual(resumed['status'], 'partial')

    def test_two_stage_filter_uses_only_named_spam_and_phishing_for_stage_two(self):
        from predict_specialists import EmailSpecialists, TwoStageFilter, two_stage_verdict
        rows = []
        for index in range(120):
            kind = ('phishing', 'spam')[index % 2]
            location = f'stage2:message:{index}'
            rows.append({'Text': email_bytes(index, kind == 'phishing'), 'Class': 1, 'Source': f'{kind}_source',
                         'Location': location, 'LabelKind': kind, 'OriginalLabel': '1',
                         'LabelBasis': 'synthetic test fixture', 'RecordId': record_id(location)})
        extra = [('legitimate', 0, email_bytes(500)), ('spam_or_phishing', 1, email_bytes(501, True)),
                 ('malicious_synthetic', 1, email_bytes(502, True)),
                 ('phishing', 1, email_bytes(503, True)), ('spam', 1, email_bytes(503, True))]  # same content, two kinds
        for number, (kind, label, raw) in enumerate(extra):
            location = f'stage2:extra:{number}'
            rows.append({'Text': raw, 'Class': label, 'Source': 'extra', 'Location': location, 'LabelKind': kind,
                         'OriginalLabel': str(label), 'LabelBasis': 'synthetic test fixture',
                         'RecordId': record_id(location)})
        frame = pd.DataFrame(rows)
        scope = self.root / 'scope'; scope.mkdir()
        selected = select_label_scope(frame, 'phishing_vs_spam', scope)
        self.assertEqual(selected.groupby('LabelKind').Class.unique().map(list).to_dict(),
                         {'phishing': [1], 'spam': [0]})
        self.assertEqual(len(selected), 120)
        audit = pd.read_csv(scope / 'training_dispositions.csv').set_index('RecordId').Disposition
        dispositions = {kind: audit[record_id(f'stage2:extra:{n}')] for n, (kind, _, _) in enumerate(extra[:3])}
        self.assertEqual(set(dispositions.values()), {'outside_label_scope'})
        self.assertEqual(audit[record_id('stage2:extra:3')], 'conflicting_labels')
        self.assertEqual(len(pd.read_csv(scope / 'label_scope_excluded.csv')), 3)

        stage2 = self.root / 'stage2'; stage2.mkdir()
        parts, settings = prepare_specialists(frame, stage2, self.root / 'cache', workers=1, target_mode='phishing_vs_spam')
        manifest = train_specialists(parts, stage2, preprocessing=settings, train_text=False, target_mode='phishing_vs_spam')
        self.assertEqual((manifest['target_mode'], manifest['branches']['header']['status']), ('phishing_vs_spam', 'trained'))
        stage1 = self.root / 'stage1'; stage1.mkdir()
        parts, settings = prepare_specialists(training_frame(120), stage1, self.root / 'cache', workers=1, target_mode='broad')
        train_specialists(parts, stage1, preprocessing=settings, train_text=False, target_mode='broad')
        with self.assertRaises(ValueError):  # stages swapped
            TwoStageFilter(stage2, stage1)
        result = TwoStageFilter(stage1, stage2).assess(email_bytes(1001, True))
        self.assertEqual(result['stage1']['target_mode'], 'broad')
        self.assertEqual(result['stage2'] is None, not result['stage1']['phishing_evidence'])
        self.assertEqual(result['verdict'], two_stage_verdict(result['stage1'], result['stage2']))
        with self.assertRaises(RuntimeError):  # a stage-2 preparation cannot be resumed as stage 1
            run_specialists(self.root / 'resumed', resume=stage2, prepare_only=True, target_mode='broad')

        assessed = {'status': 'assessed', 'target': 'email_phishing'}
        flagged = {'phishing_evidence': ['url'], 'unassessed_branches': [], 'branches': {}}
        self.assertEqual(two_stage_verdict({'phishing_evidence': [], 'unassessed_branches': []}), 'not_flagged')
        self.assertEqual(two_stage_verdict(flagged, {'phishing_evidence': [], 'branches': {'url': assessed}}), 'spam')
        self.assertEqual(two_stage_verdict(flagged, {'phishing_evidence': ['url'], 'branches': {'url': assessed}}), 'phishing')
        self.assertEqual(two_stage_verdict(flagged, {'phishing_evidence': [], 'branches': {
            'url': {'status': 'no_applicable_input', 'target': 'email_phishing'}}}), 'malicious_unclassified')

    def test_baseline_preparation_still_has_all_rows_and_original_dimensions(self):
        frame = training_frame(60)
        arrays, _, _, settings = prepare_data(frame, self.root, epochs=2,
            cache_dir=self.root / 'cache', workers=1)
        self.assertEqual(sum(len(y) for _, y in arrays.values()), len(frame))
        for X, y in arrays.values():
            self.assertEqual(X.shape, (len(y), 153))
            self.assertTrue(np.isfinite(X).all())

    def test_html_ablation_feature_sets_select_cached_columns(self):
        from train import feature_columns, HTML_PRESENCE_FEATURES
        from preprocess import FEATURE_NAMES, HTML_SECURITY_FEATURE_NAMES
        self.assertEqual(feature_columns('full'), (list(FEATURE_NAMES), []))
        kept, extra = feature_columns('html_content')
        self.assertFalse(set(HTML_PRESENCE_FEATURES) & set(kept))
        self.assertEqual(len(kept), len(FEATURE_NAMES) - 2)
        self.assertEqual(extra, list(HTML_SECURITY_FEATURE_NAMES))
        era_kept, era_extra = feature_columns('no_era_proxies')
        self.assertEqual(era_extra, [])
        self.assertEqual(era_kept, [n for n in kept if n not in ('num_https_urls', 'num_http_urls', 'has_hidden_elements')])
        self.assertIn('num_urls', era_kept)
        with self.assertRaises(ValueError):
            feature_columns('unknown')
        frame = training_frame(60)
        full, _, _, _ = prepare_data(frame, self.root, epochs=2, cache_dir=self.root / 'cache', workers=1)
        (self.root / 'ablation').mkdir()
        arrays, _, _, settings = prepare_data(frame, self.root / 'ablation', epochs=2,
            cache_dir=self.root / 'cache', workers=1, feature_set='html_content')
        self.assertEqual(settings['feature_names'], kept + extra)
        self.assertEqual(settings['feature_set'], 'html_content')
        for name, (X, y) in arrays.items():
            self.assertEqual(X.shape, (len(y), 100 + len(kept) + len(extra)))
            self.assertTrue(np.array_equal(y, full[name][1]))
            # Doc2Vec giống hệt run đầy đủ; chỉ phần feature kỹ thuật đổi.
            self.assertTrue(np.allclose(X[:, :100], full[name][0][:, :100]))

    def test_epvme_keeps_envelope_attack_and_separates_it_from_copied_original(self):
        from preprocess import (extract_message_security_features, prepare_semantic_text,
                                _parse_email, _header_attack_identity)
        original = email_bytes(5, True)
        # EPVME stores the attacker's MAIL FROM as a leading "From " line.
        spoofed = b'From <a@example.org,,test@attack.com>\n' + original
        templated = original.replace(b'Subject: Notice 5', b'Subject: MIME Attack Sample')
        multiple = original.replace(b'From: ', b'From: <boss@example.org>\nFrom: ', 1)
        dataset = self.root / 'Dataset'
        (dataset / 'EPVME_extracted' / '1').mkdir(parents=True)
        (dataset / 'enron').mkdir()
        (dataset / 'phishing').mkdir()
        for name, raw in (('a.eml', spoofed), ('b.eml', templated), ('c.eml', multiple)):
            (dataset / 'EPVME_extracted' / '1' / name).write_bytes(raw)
        (dataset / 'enron' / 'mail').write_bytes(email_bytes(6))
        data = load_training_emails(self.root / 'load', dataset)
        epvme = data[data.Source == 'EPVME']
        epvme = epvme.set_index(epvme.Location.map(lambda loc: Path(loc.split(':message:')[0]).name))
        self.assertEqual(len(epvme), 3)
        self.assertEqual(set(epvme.LabelKind), {'malicious_synthetic'})
        self.assertEqual(set(epvme.Class), {1})
        self.assertTrue(epvme.Text.iloc[0].startswith(b'From <'))  # not split as an mbox
        families = {name[:1]: basis.split('attack_family=')[1].split()[0] for name, basis in epvme.LabelBasis.items()}
        self.assertEqual(families, {'a': 'mail_from_inconsistency', 'b': 'mime_wrapping', 'c': 'multiple_from'})
        security = extract_message_security_features(_parse_email(spoofed))
        self.assertEqual(security['hdr_envelope_syntax_anomaly'], 1)
        self.assertEqual(security['hdr_return_path_domain_mismatch'], 1)
        self.assertEqual(extract_message_security_features(_parse_email(multiple))['hdr_from_header_count'], 2)
        self.assertIsNone(_header_attack_identity(_parse_email(original)))
        self.assertNotEqual(compute_dedup_key(spoofed), compute_dedup_key(original))
        self.assertEqual(compute_dedup_key(templated.replace(b'MIME Attack Sample', b'Notice 5')),
                         compute_dedup_key(original))
        self.assertNotIn('Attack Sample', prepare_semantic_text(templated))
        self.assertNotIn('attack', cleanText(templated).split())
        (self.root / 'scope').mkdir()
        selected = select_label_scope(data, 'phishing', self.root / 'scope', include_synthetic=True)
        self.assertEqual(selected.Class.value_counts().to_dict(), {1: 3, 0: 1})
        with self.assertRaises(ValueError):  # Without EPVME no positive label remains.
            select_label_scope(data, 'phishing', self.root / 'scope', include_synthetic=False)
        summary = json.loads((self.root / 'load' / 'load_summary.json').read_text())
        self.assertEqual(summary['status'], 'complete')

    def test_non_email_files_in_dataset_root_are_recorded_not_loaded(self):
        dataset = self.root / 'Dataset'
        (dataset / 'enron').mkdir(parents=True)
        (dataset / 'phishing').mkdir()
        (dataset / 'enron' / 'mail').write_bytes(email_bytes(1))
        (dataset / 'df.csv').write_text('label,text\n0,hello world\n2,buy now\n')
        (dataset / 'StealthPhisher2025.csv').write_text('URL,Label\nhttps://a.example,Legitimate\n')
        (dataset / 'notes.txt').write_text('unregistered')
        data = load_training_emails(self.root / 'load', dataset)
        self.assertEqual(len(data), 1)
        summary = json.loads((self.root / 'load' / 'load_summary.json').read_text())
        self.assertEqual(summary['status'], 'complete')
        self.assertEqual(summary['file_outcomes'], {'complete': 1, 'excluded': 1,
                                                    'url_dataset': 1, 'unregistered': 1})
        self.assertEqual(summary['counts']['files_excluded_by_policy'], 1)

    def test_phishing_pot_loads_samples_only_and_masks_the_redaction_placeholder(self):
        from preprocess import prepare_semantic_text, extract_link_features
        dataset = self.root / 'Dataset'
        pot = dataset / 'phishing_pot'
        for folder in ('email', 'img', '.github', '.git/refs/heads', '.git/objects/ab'):
            (pot / folder).mkdir(parents=True)
        commit = 'c0ffee' * 6 + 'abcd'
        (pot / '.git' / 'HEAD').write_text('ref: refs/heads/main\n')
        (pot / '.git' / 'refs' / 'heads' / 'main').write_text(commit + '\n')
        (pot / '.git' / 'objects' / 'ab' / 'cdef').write_bytes(b'From: not an email\n\nobject')
        (pot / 'README.md').write_text('# Phishing Pot')
        (pot / 'CITATION.cff').write_text('cff-version: 1.2.0')
        (pot / 'img' / 'logo.png').write_bytes(b'\x89PNG\r\n')
        msg = EmailMessage()
        msg['From'] = 'Mail Admin <admin@mailbox-quota.example>'
        msg['To'] = 'phishing@pot'
        msg['Subject'] = 'phishing@pot: mailbox full'
        msg.set_content('Hello phishing@potSie, ref 2020-phishing@pot6527. Your mailbox is full. '
                        'Restore it at https://quota.example/r?u=phishing%40pot')
        raw = msg.as_bytes()
        (pot / 'email' / 'sample-1.eml').write_bytes(raw)
        (pot / 'email' / 'sample-2.eml').write_bytes(b'From attacker@example.net Mon Jan  1 00:00:00 2026\n' + raw)
        (pot / 'email' / 'sample-3.eml').write_bytes(raw)
        (pot / 'email' / 'sample-4.csv').write_text('Email,Name\nperson@example.org,Person\n')  # not a sample
        (dataset / 'enron').mkdir()
        (dataset / 'phishing').mkdir()
        (dataset / 'enron' / 'mail').write_bytes(email_bytes(6))
        real_prefetch = load_data._prefetch_raw

        def quarantined(path, single_message=False):  # Defender blocks real malware samples on open.
            if path.endswith('sample-3.eml'):
                return None, 'AntivirusBlocked', '[WinError 225] contains a virus'
            return real_prefetch(path, single_message)

        with patch('load_data._prefetch_raw', side_effect=quarantined):
            data = load_training_emails(self.root / 'load', dataset)
        pot_rows = data[data.Source == 'phishing_pot']
        self.assertEqual(len(pot_rows), 2)
        self.assertEqual(set(pot_rows.LabelKind), {'phishing'})
        self.assertTrue(all(f'commit={commit}' in basis for basis in pot_rows.LabelBasis))
        self.assertTrue(any(text.startswith(b'From attacker@') for text in pot_rows.Text))  # not split as mbox
        summary = json.loads((self.root / 'load' / 'load_summary.json').read_text())
        self.assertEqual(summary['status'], 'complete')
        self.assertEqual(summary['counts']['files_blocked_by_antivirus'], 1)
        self.assertEqual(summary['counts']['files_excluded_by_policy'], 1)
        self.assertEqual(len(data), 3)  # 2 Phishing Pot samples + 1 Enron; nothing from .git/img/docs
        semantic = prepare_semantic_text(raw)
        self.assertNotIn('phishing', semantic.lower())
        self.assertIn('Your mailbox is full', semantic)
        self.assertFalse({'phishing', 'pot'} & set(cleanText(raw).split()))
        # The personalised link is still evidence: the URL carries the recipient address.
        self.assertEqual(extract_link_features(raw)['link_recipient_address_count'], 1)
        # Python's open() reports a Defender-blocked file as EINVAL without winerror.
        import errno, os
        with patch('load_data.open', side_effect=OSError(errno.EINVAL, 'Invalid argument'), create=True):
            error = load_data._prefetch_raw(str(pot / 'email' / 'sample-1.eml'), True)[1]
        self.assertEqual(error, 'AntivirusBlocked' if os.name == 'nt' else 'OSError')

    def test_trec07p_labels_from_index_and_supersedes_trec07_csv(self):
        dataset = self.root / 'Dataset'
        trec = dataset / 'trec07p'
        for folder in ('data', 'full', 'delay'):
            (trec / folder).mkdir(parents=True)
        (trec / 'README.txt').write_text('TREC 2007 Public Corpus')
        envelope = b'From sender@example.org  Sun Apr  8 13:07:32 2007\n'
        for index in range(1, 5):
            body = email_bytes(index, positive=index % 2 == 1)
            if index == 2:  # Dòng "From " trong body không được làm tách email.
                body += b'\nFrom here on the meeting moves to room 3.\n'
            (trec / 'data' / f'inmail.{index}').write_bytes(envelope + body)
        (trec / 'data' / 'inmail.9').write_bytes(envelope + email_bytes(9))  # không có trong index
        index_lines = 'spam ../data/inmail.1\nham ../data/inmail.2\nspam ../data/inmail.3\n' \
                      'ham ../data/inmail.4\nham ../data/inmail.5\n'
        (trec / 'full' / 'index').write_text(index_lines)
        (trec / 'delay' / 'index').write_text(index_lines)
        (dataset / 'phishing').mkdir()
        (dataset / 'enron').mkdir()
        (dataset / 'enron' / 'mail').write_bytes(email_bytes(20))
        with open(dataset / 'phishing' / 'TREC_07.csv', 'w', newline='') as handle:
            csv.writer(handle).writerows([['label', 'body'], ['0', 'stripped copy of a trec message']])
        (dataset / 'trec07p.tgz.zip').write_bytes(b'PK\x03\x04')
        real_prefetch = load_data._prefetch_raw

        def quarantined(path, single_message=False):
            if path.endswith('inmail.3'):
                return None, 'AntivirusBlocked', '[WinError 225] contains a virus'
            return real_prefetch(path, single_message)

        with patch('load_data._prefetch_raw', side_effect=quarantined):
            data = load_training_emails(self.root / 'load', dataset)
        trec_rows = data[data.Source == 'trec07p'].sort_values('Location')
        self.assertEqual([Path(loc.split(':message:')[0]).name for loc in trec_rows.Location],
                         ['inmail.1', 'inmail.2', 'inmail.4', 'inmail.9'])
        labels = dict(zip((Path(loc.split(':message:')[0]).name for loc in trec_rows.Location),
                          zip(trec_rows.LabelKind, trec_rows.Class)))
        self.assertEqual(labels['inmail.1'], ('spam_or_phishing', 1))
        self.assertEqual(labels['inmail.2'], ('legitimate', 0))
        self.assertEqual(labels['inmail.4'], ('legitimate', 0))
        self.assertEqual(labels['inmail.9'][0], 'unknown')
        self.assertTrue(all(text.startswith(b'From sender@') for text in trec_rows.Text))
        self.assertTrue(any(b'From here on the meeting' in text for text in trec_rows.Text))
        self.assertFalse(data.Source.str.lower().eq('trec_07.csv').any())
        summary = json.loads((self.root / 'load' / 'load_summary.json').read_text())
        self.assertEqual(summary['status'], 'complete')
        self.assertEqual(summary['counts']['files_blocked_by_antivirus'], 1)
        self.assertEqual(summary['counts']['trec07p_missing_from_extract'], 1)  # inmail.5
        # TREC_07.csv và file zip ở gốc bị loại có ghi nhận, không phải "unregistered".
        self.assertEqual(summary['counts']['files_excluded_by_policy'], 2)
        self.assertNotIn('unregistered', summary['file_outcomes'])
        self.assertEqual(len(data), len(trec_rows) + 1)  # + 1 email Enron
        # Gọi sai thứ tự (CSV đã nạp) thì từ chối, không nạp trùng.
        load_data.reset_source_stats()
        load_data.load_data_phishing(pd.DataFrame(), dataset / 'phishing')
        with self.assertRaises(RuntimeError):
            load_data.load_data_trec07p(pd.DataFrame(), pd.DataFrame(), trec)

    def test_url_dataset_labels_conflicts_and_shared_lexical_features(self):
        from preprocess import (extract_url_lexical_features, URL_LEXICAL_FEATURE_NAMES,
                                URL_HOST_FEATURE_NAMES, url_group_key, extract_email_urls)
        self.assertTrue(set(URL_HOST_FEATURE_NAMES) < set(URL_LEXICAL_FEATURE_NAMES))
        path = self.root / 'StealthPhisher2025.csv'
        pd.DataFrame({'URL': ['https://www.example.com', 'http://login-verify.example.tk/a/b?x=1',
                              'https://dup.example.org', 'https://dup.example.org', 'https://odd.example'],
                      'Label': ['Legitimate', 'Phishing', 'Phishing', 'Legitimate', 'Maybe'],
                      'HasSSL': [1, 0, 1, 1, 1]}).to_csv(path, index=False)
        urls = load_data.load_url_dataset(path)
        self.assertEqual(urls.Class.iloc[:2].to_list(), [0, 1])
        self.assertEqual(urls.LabelKind.iloc[2:].to_list(), ['conflicting_labels', 'conflicting_labels', 'unknown'])
        self.assertTrue(urls.Class.iloc[2:].isna().all())
        features = extract_url_lexical_features(urls.URL.iloc[1])
        self.assertEqual(len(features), len(URL_LEXICAL_FEATURE_NAMES))
        values = dict(zip(URL_LEXICAL_FEATURE_NAMES, features))
        self.assertEqual((values['url_suspicious_tld'], values['url_path_depth'], values['url_subdomain_count']), (1, 2, 1))
        # Scheme is not a feature: corpus legitimate URLs are all https.
        self.assertEqual(extract_url_lexical_features('http://x.example/p'), extract_url_lexical_features('https://x.example/p'))
        self.assertEqual(url_group_key('https://a.b.example.co.uk/x'), 'example.co.uk')
        self.assertEqual(extract_email_urls(email_bytes(3)), ['https://example.invalid/3'])

    def test_mixed_fonts_scripts_and_invisible_characters_are_normalized(self):
        from preprocess import normalize_obfuscated_text
        cases = {
            'Reset your pаsswогd at UРЅ': 'Reset your password at UPS',   # Cyrillic homoglyphs
            'Verify 𝐏𝐚𝐲𝐏𝐚𝐥 now': 'Verify PayPal now',                   # math bold "font"
            'Ｐａｙ now': 'Pay now',                                       # fullwidth
            'ᴘᴀʏᴘᴀʟ alert': 'paypal alert',                               # small caps
            'Pa​ss­word': 'Password',                           # invisible splitters
            'Login to P a y P a l': 'Login to PayPal',                    # spaced letters
            'Açtiοn required': 'Action required',                         # Greek omicron + cedilla
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_obfuscated_text(raw)[0], expected)
        for genuine in ('Привет, это обычное письмо', 'Mật khẩu của bạn', 'Καλημέρα σας'):
            self.assertEqual(normalize_obfuscated_text(genuine)[0], genuine)
        _, counts = normalize_obfuscated_text('P𝐚yPal pаsswогd')
        self.assertEqual((counts['mixed_style_word_count'], counts['mixed_script_word_count']), (1, 1))

    def test_visible_html_text_drops_hidden_salting_and_joins_split_words(self):
        from preprocess import extract_visible_html_text, prepare_semantic_text, extract_text_obfuscation_features
        markup = ('<html><head><style>.pre{display:none}</style></head><body>'
                  '<div class="pre">preheader salt</div>'
                  '<div style="font-size:0">benign meeting agenda</div>'
                  '<p>Confirm your Pa<span style="font-family:Arial">ss</span>word '
                  '<font face="Courier">to</font>day</p>'
                  '<span style="color:#fff;background-color:#ffffff">invisible words</span>'
                  '<p>Thanks</p></body></html>')
        text, stats = extract_visible_html_text(markup)
        self.assertEqual(text, 'Confirm your Password today\nThanks')
        self.assertEqual(stats['intra_word_tag_break_count'], 3)
        self.assertGreaterEqual(stats['intra_word_font_switch_count'], 2)
        self.assertEqual(stats['font_family_count'], 2)
        msg = EmailMessage(); msg['Subject'] = 'Notice'
        msg.set_content('fallback'); msg.add_alternative(markup, subtype='html')
        semantic = prepare_semantic_text(msg.as_bytes())
        for hidden in ('salt', 'agenda', 'invisible'):
            self.assertNotIn(hidden, semantic)
        self.assertGreater(extract_text_obfuscation_features(msg.as_bytes())['hidden_text_ratio'], 0.5)

    @unittest.skipUnless(importlib.util.find_spec('zxingcpp'), 'optional QR tool; zxing-cpp not installed')
    def test_qr_codes_are_decoded_from_images_attachments_tables_and_block_characters(self):
        import io, zipfile, base64
        import zxingcpp
        from PIL import Image
        from preprocess import inspect_email_qr_codes, extract_email_urls
        url = 'https://bit.ly/secure-login-verify'
        bitmap = np.asarray(zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, url, width=150, height=150))
        png = io.BytesIO(); Image.fromarray(bitmap).save(png, format='PNG'); png = png.getvalue()
        modules = np.asarray(zxingcpp.write_barcode(zxingcpp.BarcodeFormat.QRCode, url, quiet_zone=0)) < 128

        def message(attach=None, html=None, text='Scan the code to keep your mailbox active.'):
            msg = EmailMessage(); msg['From'] = 'IT Desk <it@example.org>'; msg['Subject'] = 'Mailbox'
            msg.set_content(text)
            if html:
                msg.add_alternative(html, subtype='html')
            if attach:
                msg.add_attachment(attach[0], maintype=attach[1], subtype=attach[2], filename=attach[3])
            return msg.as_bytes()

        office = io.BytesIO()
        with zipfile.ZipFile(office, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>'); archive.writestr('word/media/image1.png', png)
        table = '<table>' + ''.join('<tr>' + ''.join(
            f'<td bgcolor="{"#000000" if dark else "#ffffff"}"></td>' for dark in row) + '</tr>' for row in modules) + '</table>'
        rows = modules if len(modules) % 2 == 0 else np.vstack([modules, np.zeros((1, modules.shape[1]), bool)])
        blocks = '\n'.join(''.join({(1, 1): '█', (1, 0): '▀', (0, 1): '▄', (0, 0): ' '}[(int(t), int(b))]
                                   for t, b in zip(rows[i], rows[i + 1])) for i in range(0, len(rows), 2))
        cases = {
            'mime_image': message(attach=(png, 'image', 'png', 'scan.png')),
            'html_data_uri': message(html=f'<p>Scan</p><img src="data:image/png;base64,{base64.b64encode(png).decode()}">'),
            'attachment_container': message(attach=(office.getvalue(), 'application',
                                                    'vnd.openxmlformats-officedocument.wordprocessingml.document', 'a.docx')),
            'drawn_in_markup': message(html=f'<p>Scan</p>{table}'),
        }
        for origin, raw in cases.items():
            report = inspect_email_qr_codes(raw)
            self.assertEqual([(c['payload'], c['origin'], c['kind']) for c in report['codes']], [(url, origin, 'url')], origin)
            features = report['features']
            self.assertEqual((features['qr_only_link'], features['qr_url_risky_host_count'],
                              features['qr_url_sender_domain_mismatch']), (1, 1, 1))
        drawn = inspect_email_qr_codes(message(text='Scan:\n' + blocks))
        self.assertEqual([c['payload'] for c in drawn['codes']], [url])
        self.assertEqual(extract_email_urls(cases['mime_image'], include_qr=True), [url])
        remote = inspect_email_qr_codes(message(html='<img src="https://cdn.example/qr.png">'))
        self.assertEqual(remote['features']['qr_unscanned_image_count'], 1)

    def test_handbook_link_and_sender_identity_features(self):
        import base64
        from preprocess import (extract_link_features, extract_message_security_features, _parse_email,
                                brand_impersonation, extract_content_indicators)
        victim = 'alice@example.org'
        token = base64.b64encode(victim.encode()).decode().rstrip('=')
        msg = EmailMessage()
        msg['From'] = 'PayPal Service <service@paypa1-billing.com>'
        msg['Reply-To'] = 'paypal.help@gmail.com'
        msg['To'] = victim
        msg['Subject'] = 'Account review'
        msg.set_content('Please review your account. Keep this confidential and do not tell anyone.')
        msg.add_alternative(
            f'<a href="https://evil.example/login?u={token}">Review</a>'
            f'<a href="https://tracker.example/r?url=https%3A%2F%2Fevil.example">Open</a>'
            f'<a href="https://kit.weebly.com/x">PayPal Resolution Center</a>'
            f'<a href="https://paypal.com/help">PayPal help</a>', subtype='html')
        raw = msg.as_bytes()
        links = extract_link_features(raw)
        self.assertEqual(links['link_recipient_address_count'], 1)
        self.assertEqual(links['link_open_redirect_count'], 1)
        self.assertEqual(links['link_free_hosting_count'], 1)
        self.assertEqual(links['link_anchor_brand_mismatch_count'], 1)  # official paypal.com link is not counted
        header = extract_message_security_features(_parse_email(raw))
        self.assertEqual((header['hdr_reply_to_freemail_divergence'], header['hdr_display_name_brand_mismatch'],
                          header['hdr_sender_brand_lookalike']), (1, 1, 1))
        self.assertEqual(extract_content_indicators(raw)['bec_secrecy_count'], 2)
        for host, expected in (('paypa1.com', 'lookalike'), ('secure-paypal.com', 'combosquat'),
                               ('apply.example.com', None), ('purchase-order.com', None), ('amazonses.com', None)):
            verdict = brand_impersonation(host)
            self.assertEqual(verdict[1] if verdict else None, expected, host)
        clean = EmailMessage(); clean['From'] = 'Bob <bob@example.org>'; clean['To'] = victim
        clean.set_content('Agenda at https://example.org/agenda')
        self.assertEqual(sum(extract_link_features(clean.as_bytes()).values()), 0)

    def test_attachment_payload_features_are_static_and_bounded(self):
        import io, zipfile
        from unittest.mock import patch
        from preprocess import extract_attachment_payload_features, ATTACHMENT_PAYLOAD_FEATURE_NAMES
        smuggle = (b'<html><script>var b=new Blob([atob("' + b'QUFB' * 600 + b'")]);'
                   b'var a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="x.zip";</script></html>')
        lnk = b'L\0\0\0\x01\x14\x02\0' + b'\0' * 64 + 'powershell -nop -w hidden'.encode('utf-16le')
        onenote = bytes.fromhex('e4525c7b8cd8a74daeb15378d02996d3') + b'\0' * 32 + bytes.fromhex('e716e3bd65261145a4c48d4d0b7a9eac')
        pdf = b'%PDF-1.7\n1 0 obj <</A <</S /URI /URI (https://evil.example)>> >> endobj\n%%EOF'
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.writestr('invoice.js', b'payload')
        data = bytearray(archive.getvalue())
        data[6] |= 1  # mark the member as encrypted in the local header ...
        data[data.find(b'PK\x01\x02') + 8] |= 1  # ... and in the central directory
        msg = EmailMessage(); msg['From'] = 'a@example.org'; msg['To'] = 'b@example.org'
        msg.set_content('Open the archive, password: Inv2026!')
        # Signed profile: PKCS#7 DER wrapper, plist readable inside; the name hides the extension.
        profile = (b'\x30\x82\x10\x00' + b'<plist><dict><key>PayloadContent</key><array><dict><key>PayloadType</key>'
                   b'<string>com.apple.caldav.account</string></dict></array><key>PayloadType</key>'
                   b'<string>Configuration</string></dict></plist>')
        for payload, name in ((smuggle, 'statement.html'), (lnk, 'scan.lnk'), (onenote, 'notes.one'),
                              (pdf, 'notice.pdf'), (bytes(data), 'invoice.zip'), (b'\0' * 64, 'disk.iso'),
                              (profile, 'calendar.mobile')):
            msg.add_attachment(payload, maintype='application', subtype='octet-stream', filename=name)
        values = extract_attachment_payload_features(msg.as_bytes())
        self.assertEqual(list(values), ATTACHMENT_PAYLOAD_FEATURE_NAMES)
        for name in ('attachment_html_smuggling_count', 'attachment_lnk_command_count',
                     'attachment_onenote_embedded_count', 'attachment_pdf_uri_count',
                     'attachment_password_archive_in_body', 'attachment_disk_image_count',
                     'attachment_config_profile_count'):
            self.assertEqual(values[name], 1, name)
        doc = EmailMessage(); doc['From'] = 'a@example.org'
        doc.set_content('see attached')
        doc.add_attachment(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\0' * 504, maintype='application',
                           subtype='msword', filename='invoice.doc')
        fake = {'autoexec': 1, 'suspicious': 3, 'stomping': 1, 'xlm': 0}
        with patch('preprocess._vba_indicators', return_value=fake):
            macro = extract_attachment_payload_features(doc.as_bytes())
        self.assertEqual((macro['attachment_vba_autoexec_count'], macro['attachment_vba_suspicious_count'],
                          macro['attachment_vba_stomping_count']), (1, 3, 1))

    def test_local_tiny_bert_training_and_inference_without_download(self):
        from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast
        import torch
        torch.set_num_threads(2)
        checkpoint = self.root / 'tiny_initial'; checkpoint.mkdir()
        vocab = ['[PAD]', '[UNK]', '[CLS]', '[SEP]', '[MASK]', 'message', 'notice',
                 'identifier', 'please', 'read', 'open', 'https', 'example', 'invalid']
        (checkpoint / 'vocab.txt').write_text('\n'.join(vocab), encoding='utf-8')
        tokenizer = BertTokenizerFast(vocab_file=str(checkpoint / 'vocab.txt'), do_lower_case=True)
        tokenizer.save_pretrained(checkpoint)
        model = BertForSequenceClassification(BertConfig(vocab_size=len(vocab), hidden_size=16,
            num_hidden_layers=1, num_attention_heads=2, intermediate_size=32,
            max_position_embeddings=512, num_labels=2))
        model.save_pretrained(checkpoint, safe_serialization=True)
        parts, settings = prepare_specialists(training_frame(40), self.root, self.root / 'cache', workers=1)
        manifest = train_specialists(parts, self.root, preprocessing=settings,
            bert_model_name=str(checkpoint), bert_epochs=1)
        self.assertEqual(manifest['branches']['text']['status'], 'trained')
        from predict_specialists import EmailSpecialists
        result = EmailSpecialists(self.root).assess(email_bytes(1001, True))
        self.assertEqual(result['branches']['text']['status'], 'assessed')
        self.assertTrue(0 <= result['branches']['text']['score'] <= 1)


if __name__ == '__main__':
    unittest.main()
