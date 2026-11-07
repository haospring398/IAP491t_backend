"""Compare old repeated traversal, cold cache and warm cache on real local emails."""
import argparse
import json
import mailbox
import time
from unittest.mock import patch
from pathlib import Path

import pandas as pd

from pipeline_cache import PreprocessingCache, preprocessing_signature
from preprocess import (compute_dedup_key, _parse_email, _get_email_body, _strip_html,
                        _normalize, extract_engineered_features, cleanText, remove_stopwords,
                        group_signature)


def benchmark(output, records=400):
    base = Path(__file__).resolve().parent
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError('Choose an empty benchmark output directory')
    meta = pd.read_csv(base / 'test_metadata.csv')
    meta = meta[meta.Location.str.contains(':message:', regex=False)]
    chosen = pd.concat([meta[meta.Class.eq(label)].head(records // 2) for label in (0, 1)], ignore_index=True)
    messages, boxes = [], {}
    try:
        for row in chosen.itertuples():
            path, index = row.Location.rsplit(':message:', 1)
            if row.Class == 0:
                raw = Path(path).read_bytes()
            elif row.Source.startswith('phishing') or row.Source.endswith('.mbox'):
                if path not in boxes:
                    boxes[path] = mailbox.mbox(path, create=False)
                raw = boxes[path].get_bytes(int(index))
            else:
                continue
            messages.append({'Text': raw, 'Location': row.Location})
    finally:
        for box in boxes.values():
            box.close()
    data = pd.DataFrame(messages)
    _, settings = preprocessing_signature()
    expected = []
    _strip_html.cache_clear()
    start = time.perf_counter()
    # The previous pipeline had no HTML conversion cache and reparsed raw MIME
    # independently for identity, grouping, engineered features and text.
    with patch('preprocess._strip_html', _strip_html.__wrapped__):
        for raw in data.Text:
            key = compute_dedup_key(raw)
            plain, markup = _get_email_body(_parse_email(raw))
            body = _normalize('\n'.join(dict.fromkeys(p for p in (plain, _strip_html.__wrapped__(markup)) if p.strip())))
            features = extract_engineered_features(raw)
            text = remove_stopwords(cleanText(raw))
            expected.append((key, group_signature(body, key), features, text))
    legacy_seconds = time.perf_counter() - start
    timings = {}
    for phase in ('cold', 'warm'):
        _strip_html.cache_clear()
        start = time.perf_counter()
        with PreprocessingCache(output / 'cache', workers=1) as cache:
            actual = cache.prepare(data, 'identity', output)
            actual = cache.prepare(actual, 'features', output)
        timings[phase] = time.perf_counter() - start
        observed = list(zip(actual._dedup_key, zip(actual._group_key, actual._simhash), actual._features,
                            actual._clean_text))
        if observed != expected:
            raise RuntimeError('Benchmark found different preprocessing outputs')
    report = {'rows': len(data), 'workers': 1, 'repeated_traversal_seconds': legacy_seconds,
              'cold_seconds': timings['cold'], 'warm_seconds': timings['warm'],
              'cold_speedup': legacy_seconds / timings['cold'],
              'warm_speedup': legacy_seconds / timings['warm'], 'outputs_identical': True,
              'scope': 'Preprocessing real local email subset; excludes model training and full dataset loading'}
    (output / 'benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--records', type=int, default=400)
    args = parser.parse_args()
    benchmark(args.output, args.records)
