"""Bounded parallel preprocessing with content-addressed, versioned disk cache."""
import hashlib
import json
import os
import sqlite3
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from preprocess import (_parse_email, _get_email_body, _strip_html, _normalize,
                        _english_stopwords, compute_dedup_key, cleanText,
                        remove_stopwords, prepare_semantic_text, extract_engineered_features,
                        extract_html_features, extract_html_security_features,
                        extract_message_security_features, extract_text_obfuscation_features,
                        extract_link_features, extract_attachment_payload_features,
                        extract_content_indicators)


def preprocessing_signature():
    from nltk.stem import WordNetLemmatizer
    import bs4
    import nltk
    try:
        WordNetLemmatizer().lemmatize('running', pos='v')
        lemmatization = True
    except LookupError:
        lemmatization = False
    settings = {'schema': 1, 'lemmatization': lemmatization,
                'stopwords': sorted(_english_stopwords()), 'bs4': bs4.__version__,
                'nltk': nltk.__version__,
                'pipeline_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'preprocess_sha256': hashlib.sha256(Path(__file__).with_name('preprocess.py').read_bytes()).hexdigest()}
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest(), settings


def _process(job):
    raw, stage, lemmatization = job
    try:
        msg = _parse_email(raw)
        plain, markup = _get_email_body(msg)
        if stage == 'identity':
            body = '\n'.join(dict.fromkeys(p for p in (plain, _strip_html(markup)) if p.strip()))
            key = compute_dedup_key(msg)
            return {'_dedup_key': key, '_group_body': _normalize(body),
                    '_attachment_hashes': msg._pipeline_attachment_hashes,
                    '_semantic_text': prepare_semantic_text(msg)}
        text = remove_stopwords(cleanText(msg))
        if lemmatization:
            from nltk.stem import WordNetLemmatizer
            lemmatizer = WordNetLemmatizer()
            text = ' '.join(lemmatizer.lemmatize(w, pos='v') for w in text.split())
        return {'_clean_text': text, '_features': extract_engineered_features(msg),
                '_html_features': {**extract_html_features(markup), **extract_html_security_features(markup)},
                '_message_security': extract_message_security_features(msg),
                # Evidence only (source-dependent in these corpora); not model inputs.
                '_text_obfuscation': extract_text_obfuscation_features(msg),
                '_link_features': extract_link_features(msg),
                '_attachment_payload': extract_attachment_payload_features(msg),
                '_content_indicators': extract_content_indicators(msg),
                '_header_available': any(bool(str(msg.get(h, '')).strip()) for h in ('From', 'To', 'Reply-To')),
                '_text_available': bool(str(msg.get('Subject', '')).strip() or plain.strip() or _strip_html(markup).strip())}
    except Exception as exc:
        return {'_error': f'{type(exc).__name__}: {exc}'}


class PreprocessingCache:
    def __init__(self, directory, workers=None, batch_size=128):
        self.signature, self.settings = preprocessing_signature()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / 'emails.sqlite', timeout=60)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS cache '
                        '(version TEXT, digest TEXT, stage TEXT, value BLOB, PRIMARY KEY(version,digest,stage))')
        self.workers = max(1, workers if workers is not None else min(4, os.cpu_count() or 1))
        self.batch_size = max(1, batch_size)
        try:
            self.pool = ProcessPoolExecutor(max_workers=self.workers) if self.workers > 1 else None
        except Exception:
            self.db.close()
            raise

    def close(self):
        if self.pool is not None:
            self.pool.shutdown(wait=True, cancel_futures=True)
        self.db.commit()
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def prepare(self, data, stage, output):
        if stage not in {'identity', 'features'}:
            raise ValueError('Unknown preprocessing stage')
        started = time.perf_counter()
        records, errors = [], []
        hits, calculated = 0, 0
        raw_values = data.Text.to_list()
        for start in range(0, len(raw_values), self.batch_size):
            batch = raw_values[start:start + self.batch_size]
            keys, values, missing = [], {}, {}
            for raw in batch:
                if not isinstance(raw, (bytes, str)):
                    raise ValueError('Raw email must be bytes or str; no input row may be silently dropped')
                payload = raw if isinstance(raw, bytes) else raw.encode('utf-8', errors='surrogatepass')
                key = hashlib.sha256((b'bytes:' if isinstance(raw, bytes) else b'str:') + payload).hexdigest()
                keys.append(key)
                if key in values or key in missing:
                    hits += 1
                    continue
                cached = self.db.execute('SELECT value FROM cache WHERE version=? AND digest=? AND stage=?',
                                         (self.signature, key, stage)).fetchone()
                if cached is not None:
                    values[key] = json.loads(zlib.decompress(cached[0]))
                    hits += 1
                else:
                    missing[key] = raw
            jobs = [(raw, stage, self.settings['lemmatization']) for raw in missing.values()]
            results = self.pool.map(_process, jobs, chunksize=8) if self.pool is not None else map(_process, jobs)
            for key, result in zip(missing, results):
                calculated += 1
                values[key] = result
                if '_error' not in result:
                    blob = zlib.compress(json.dumps(result, ensure_ascii=True).encode(), level=1)
                    self.db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',
                                    (self.signature, key, stage, blob))
            self.db.commit()
            if len(values) != len(set(keys)):
                raise RuntimeError('Worker result count mismatch; preprocessing is incomplete')
            for offset, key in enumerate(keys):
                result = values[key]
                if '_error' in result:
                    row = data.iloc[start + offset]
                    errors.append({'RecordId': row.get('RecordId', ''), 'Location': row.get('Location', ''),
                                   'Stage': stage, 'Error': result['_error']})
                records.append(result)
            if (start // self.batch_size) % 40 == 0:
                print(f'Preprocess {stage}: {min(start + len(batch), len(data))}/{len(data)}; cache hits={hits}', flush=True)
        output = Path(output)
        if errors:
            pd.DataFrame(errors).to_csv(output / f'preprocessing_{stage}_errors.csv', index=False)
            raise RuntimeError(f'{len(errors)} preprocessing errors; every failed row is reported; training stopped')
        if len(records) != len(data):
            raise RuntimeError('Preprocessing lost rows')
        result = data.reset_index(drop=True).copy()
        if records:
            for column in records[0]:
                result[column] = [record[column] for record in records]
        stats = {'stage': stage, 'rows_in': len(data), 'rows_out': len(result),
                 'cache_hits': hits, 'computed': calculated, 'seconds': time.perf_counter() - started,
                 'workers': self.workers, 'signature': self.signature,
                 'settings': self.settings}
        (output / f'preprocessing_{stage}.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
        return result
