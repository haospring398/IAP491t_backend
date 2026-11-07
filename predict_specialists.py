"""Assess raw email with available specialists and report missing coverage."""
import argparse
import json
import pickle
from pathlib import Path

import numpy as np

from evaluate import file_digest, positive_scores
from pipeline_cache import _process, preprocessing_signature
from preprocess import inspect_email_attachments
from specialists import availability, feature_dict


class EmailSpecialists:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / 'specialist_manifest.json').read_text())
        if self.manifest['status'] not in {'complete', 'partial'}:
            raise ValueError('Specialist run is incomplete')
        # Runs before the two-stage filter recorded no target mode; they were all 'phishing'.
        self.target_mode = self.manifest.get('target_mode', 'phishing')
        signature, _ = preprocessing_signature()
        if signature != self.manifest['preprocessing']['signature']:
            raise ValueError('Inference preprocessing differs from training')
        for name, expected in self.manifest['inference_artifacts'].items():
            if file_digest(self.directory / name) != expected:
                raise ValueError(f'Artifact changed: {name}')
        self.models = {}
        for name, config in self.manifest['branches'].items():
            if config['status'] == 'trained':
                with (self.directory / config['file']).open('rb') as handle:
                    self.models[name] = pickle.load(handle)

    def assess(self, raw):
        identity = _process((raw, 'identity', False))
        features = _process((raw, 'features', self.manifest['preprocessing']['lemmatization']))
        if '_error' in identity or '_error' in features:
            raise ValueError(identity.get('_error') or features.get('_error'))
        row = {**identity, **features}
        present, values = availability(row), feature_dict(row)
        result = {'target_mode': self.target_mode, 'branches': {},
                  'attachment_evidence': inspect_email_attachments(raw),
                  'text_obfuscation': row['_text_obfuscation'],
                  # BEC/callback indicators: rule-layer evidence, not a trained model input.
                  'content_indicators': row['_content_indicators']}
        for name, config in self.manifest['branches'].items():
            entry = {'target': config['target'], 'algorithm': config['algorithm']}
            if not present[name]:
                entry['status'] = 'no_applicable_input'
            elif config['status'] != 'trained':
                entry.update(status=config['status'], reason=config.get('reason', ''))
            else:
                inputs = np.asarray([[values[n] for n in config['features']]], dtype=np.float32)
                score = float(positive_scores(self.models[name], inputs)[0])
                entry.update(status='assessed', score=score, threshold=config['threshold'],
                             validation_precision_target_met=config['precision_target_met'],
                             positive=score >= config['threshold'])
            result['branches'][name] = entry
        # Email-level branches above threshold for this run's positive class: phishing,
        # any malicious mail ('broad') or phishing rather than spam ('phishing_vs_spam').
        result['phishing_evidence'] = [n for n, e in result['branches'].items()
                                      if e['target'] == 'email_phishing' and e.get('positive')]
        result['malware_alerts'] = [n for n, e in result['branches'].items()
                                  if e['target'] != 'email_phishing' and e.get('positive')]
        result['unassessed_branches'] = [n for n, e in result['branches'].items()
                                        if e['status'] not in {'assessed', 'no_applicable_input'}]
        return result


def two_stage_verdict(stage1, stage2=None):
    """Stage 1 flags malicious mail; stage 2 names it phishing or spam. Any branch above
    threshold counts, as in the single-stage report; nothing is decided without evidence."""
    if not stage1['phishing_evidence']:
        return 'not_flagged' if not stage1['unassessed_branches'] else 'not_flagged_incomplete'
    if stage2 is None or not any(e['status'] == 'assessed' and e['target'] == 'email_phishing'
                                 for e in stage2['branches'].values()):
        return 'malicious_unclassified'
    return 'phishing' if stage2['phishing_evidence'] else 'spam'


class TwoStageFilter:
    def __init__(self, stage1_run, stage2_run):
        self.stage1, self.stage2 = EmailSpecialists(stage1_run), EmailSpecialists(stage2_run)
        if (self.stage1.target_mode, self.stage2.target_mode) != ('broad', 'phishing_vs_spam'):
            raise ValueError("Stage 1 must be trained with --target-mode broad and stage 2 with phishing_vs_spam; "
                             f"got {self.stage1.target_mode} and {self.stage2.target_mode}")

    def assess(self, raw):
        first = self.stage1.assess(raw)
        second = self.stage2.assess(raw) if first['phishing_evidence'] else None  # only flagged mail
        return {'verdict': two_stage_verdict(first, second), 'stage1': first, 'stage2': second}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('email_file')
    parser.add_argument('--run', required=True, help='Single-stage run, or stage 1 (--target-mode broad)')
    parser.add_argument('--spam-stage', help='Stage-2 run (--target-mode phishing_vs_spam): names flagged mail phishing or spam')
    args = parser.parse_args()
    raw = Path(args.email_file).read_bytes()
    assessor = TwoStageFilter(args.run, args.spam_stage) if args.spam_stage else EmailSpecialists(args.run)
    print(json.dumps(assessor.assess(raw), indent=2))
