"""Bounded parallel preprocessing with content-addressed, versioned disk cache."""
import hashlib
import json
import multiprocessing
import os
import sqlite3
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from preprocess import (_parse_email, _get_email_body, _strip_html, _normalize,
                        _english_stopwords, compute_dedup_key, cleanText,
                        remove_stopwords, extract_engineered_features,
                        extract_html_features, extract_html_check_features,
                        extract_message_security_features, extract_text_obfuscation_features,
                        extract_link_features, extract_attachment_payload_features,
                        extract_content_indicators, group_signature)


def preprocessing_signature():
    import bs4
    import magika
    import tldextract
    # Verb lemmatization needed nltk/WordNet; nltk was removed for an unfixed CVE
    # (2026-10-26). The key stays so manifests keep the same shape.
    settings = {'schema': 1, 'lemmatization': False,
                'stopwords': sorted(_english_stopwords()), 'bs4': bs4.__version__,
                'tldextract': tldextract.__version__,
                # Magika's model ships inside the package: its version fixes the attachment types.
                'magika': magika.__version__,
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
            group_key, simhash = group_signature(_normalize(body), key)
            return {'_dedup_key': key, '_group_key': group_key, '_simhash': simhash,
                    '_attachment_hashes': msg._pipeline_attachment_hashes}
        if lemmatization:
            raise ValueError('Lemmatized runs predate the removal of nltk (2026-10-26); retrain')
        text = remove_stopwords(cleanText(msg))
        return {'_clean_text': text, '_features': extract_engineered_features(msg),
                '_html_features': {**extract_html_features(markup), **extract_html_check_features(markup)},
                '_message_security': extract_message_security_features(msg),
                # Evidence only (source-dependent in these corpora); not model inputs.
                '_text_obfuscation': extract_text_obfuscation_features(msg),
                '_link_features': extract_link_features(msg),
                '_attachment_payload': extract_attachment_payload_features(msg),
                '_content_indicators': extract_content_indicators(msg),
                '_header_available': any(bool(str(msg.get(h, '')).strip()) for h in ('From', 'To', 'Reply-To'))}
    except Exception as exc:
        return {'_error': f'{type(exc).__name__}: {exc}'}


class CompressedEmail:
    """A raw email held zlib-compressed in memory. ~800k raw emails (~4 GB) did not fit the
    sandbox limit next to the workers; prepare() decompresses one email at a time."""
    __slots__ = ('blob',)

    def __init__(self, raw):
        self.blob = zlib.compress(raw if isinstance(raw, bytes) else raw.encode('utf-8', 'surrogatepass'), 1)

    def raw(self):
        return zlib.decompress(self.blob)


class EmailStore:
    """Raw emails spilled zlib-compressed to an SQLite file; memory keeps a ~50-byte handle per
    email. Even compressed in memory, ~800k emails (2.3 GB) left too little of the sandbox's
    7 GB for feature extraction. Only the main process reads it."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        # A scratch file deleted after use: no journal, no fsync.
        self.db.execute('PRAGMA journal_mode=OFF')
        self.db.execute('PRAGMA synchronous=OFF')
        self.db.execute('CREATE TABLE IF NOT EXISTS raw(id INTEGER PRIMARY KEY, blob BLOB NOT NULL)')

    def add_all(self, texts):
        handles = []
        for raw in texts:
            payload = raw if isinstance(raw, bytes) else raw.encode('utf-8', 'surrogatepass')
            cursor = self.db.execute('INSERT INTO raw(blob) VALUES(?)', (zlib.compress(payload, 1),))
            handles.append(StoredEmail(self, cursor.lastrowid))
        self.db.commit()
        return handles

    def get(self, key):
        return zlib.decompress(self.db.execute('SELECT blob FROM raw WHERE id=?', (key,)).fetchone()[0])

    def close(self):
        self.db.close()
        self.path.unlink(missing_ok=True)


class StoredEmail:
    __slots__ = ('store', 'key')

    def __init__(self, store, key):
        self.store, self.key = store, key

    def raw(self):
        return self.store.get(self.key)


def compress_texts(frame, store=None):
    """Replace a DataFrame's raw Text with handles: StoredEmail in `store` (on disk) or, without
    a store, CompressedEmail (in memory). Rows that already hold a handle are kept."""
    if len(frame):
        texts = frame.Text.to_list()
        fresh = [i for i, t in enumerate(texts) if not isinstance(t, (CompressedEmail, StoredEmail))]
        if store is not None:
            for i, handle in zip(fresh, store.add_all(texts[i] for i in fresh)):
                texts[i] = handle
        else:
            for i in fresh:
                texts[i] = CompressedEmail(texts[i])
        frame['Text'] = texts
    return frame


def _memory():
    """(this process RSS, container limit or None) in bytes; (None, None) outside Linux."""
    try:
        with open('/proc/self/status') as handle:
            status = dict(line.split(':', 1) for line in handle if ':' in line)
        rss = int(status['VmRSS'].split()[0]) * 1024
    except (OSError, KeyError, ValueError):
        return None, None
    try:
        with open('/sys/fs/cgroup/memory.max') as handle:
            limit = handle.read().strip()
        return rss, None if limit == 'max' else int(limit)
    except (OSError, ValueError):
        return rss, None


def memory_status():
    """'RSS x GB of limit y GB' inside a Linux container; empty elsewhere."""
    rss, limit = _memory()
    if rss is None:
        return ''
    return f'RSS {rss / 2**30:.2f} GB of limit ' + ('none' if limit is None else f'{limit / 2**30:.1f} GB')


# Measured in the sandbox: a worker process holds ~0.3 GB (libraries + a batch of emails).
WORKER_BYTES = 350 * 2**20
MEMORY_RESERVE = 1 * 2**30  # growth of the main process while results accumulate


def fit_workers(requested):
    """Fewer workers when the container's memory limit cannot hold the requested number."""
    rss, limit = _memory()
    if rss is None or limit is None:
        return requested
    fitting = max(1, int((limit - rss - MEMORY_RESERVE) // WORKER_BYTES))
    if fitting < requested:
        print(f'Memory: {memory_status()}; using {fitting} worker(s) instead of {requested}', flush=True)
    return min(requested, fitting)


class PreprocessingCache:
    def __init__(self, directory, workers=None, batch_size=128):
        self.signature, self.settings = preprocessing_signature()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / 'emails.sqlite', timeout=60)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS cache '
                        '(version TEXT, digest TEXT, stage TEXT, value BLOB, PRIMARY KEY(version,digest,stage))')
        self.workers = fit_workers(max(1, workers if workers is not None else min(4, os.cpu_count() or 1)))
        self.batch_size = max(1, batch_size)
        try:
            # Never fork a parent that already holds the loaded emails: reference counting and the
            # garbage collector write to the inherited objects, so each forked worker slowly copies
            # gigabytes of them (the sandbox was killed at ~270k emails). forkserver/spawn workers
            # start from a small, fresh interpreter. Windows only has spawn.
            methods = multiprocessing.get_all_start_methods()
            context = multiprocessing.get_context('forkserver' if 'forkserver' in methods else 'spawn')
            self.pool = (ProcessPoolExecutor(max_workers=self.workers, mp_context=context)
                         if self.workers > 1 else None)
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

    def prepare(self, data, stage, output, transform=None):
        """transform(result) -> compact result, applied per email as soon as it is ready, so
        callers that need a few columns never hold every full result at once."""
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
                if isinstance(raw, (CompressedEmail, StoredEmail)):
                    raw = raw.raw()
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
                records.append(transform(result) if transform is not None and '_error' not in result else result)
            if (start // self.batch_size) % 40 == 0:
                print(f'Preprocess {stage}: {min(start + len(batch), len(data))}/{len(data)}; cache hits={hits}'
                      f'{"; " + memory_status() if memory_status() else ""}', flush=True)
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
