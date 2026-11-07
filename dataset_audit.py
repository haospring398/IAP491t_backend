"""Durable ingestion accounting. Payloads are stored only for rejected records."""
import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from collections import Counter
from pathlib import Path


def record_id(location):
    return hashlib.sha256(str(location).encode('utf-8')).hexdigest()


class DatasetAudit:
    def __init__(self, output):
        self.started = time.perf_counter()
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.path = self.output / 'ingestion.sqlite'
        if self.path.exists():
            raise FileExistsError(f'Use a new run directory: {self.path}')
        # In the sandbox the run folder is a Windows bind mount, where SQLite's small random
        # writes took ~2 h instead of ~10 min. IAP491_SCRATCH_DIR (a Linux volume) holds the
        # ledger while it is written; finish() moves it into the run folder in one copy.
        scratch = os.environ.get('IAP491_SCRATCH_DIR')
        if scratch:
            Path(scratch).mkdir(parents=True, exist_ok=True)
            self.work_path = Path(scratch) / f'ingestion-{uuid.uuid4().hex}.sqlite'
        else:
            self.work_path = self.path
        self.db = sqlite3.connect(self.work_path)
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA cache_size=-131072;
            CREATE TABLE files(path TEXT PRIMARY KEY, status TEXT NOT NULL,
                               reason TEXT, loaded INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE records(id TEXT PRIMARY KEY, file TEXT NOT NULL,
                                 location TEXT NOT NULL, status TEXT NOT NULL,
                                 label_kind TEXT, reason TEXT, rejected_payload TEXT);
            CREATE INDEX records_file ON records(file);
        ''')
        self.pending = 0

    def file(self, path, status, reason=''):
        self.db.execute('INSERT INTO files(path,status,reason) VALUES(?,?,?) '
                        'ON CONFLICT(path) DO UPDATE SET status=excluded.status,reason=excluded.reason',
                        (str(path), status, reason))
        self._flush()

    def record(self, path, location, status, kind='', reason='', payload=None):
        self.db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',
                        (record_id(location), str(path), location, status, kind, reason,
                         json.dumps(payload, ensure_ascii=True, default=str) if payload is not None else None))
        self._flush()

    def _flush(self):
        self.pending += 1
        if self.pending >= 2000:
            self.db.commit()
            self.pending = 0

    def finish(self, counts, errors, provenance):
        self.db.execute("UPDATE files SET loaded=(SELECT COUNT(*) FROM records "
                        "WHERE records.file=files.path AND records.status='loaded')")
        self.db.commit()
        files = dict(self.db.execute('SELECT status,COUNT(*) FROM files GROUP BY status'))
        records = dict(self.db.execute('SELECT status,COUNT(*) FROM records GROUP BY status'))
        complete = not errors and not files.get('reading', 0) and not files.get('failed', 0)
        if records.get('loaded', 0) != counts.get('emails_loaded', 0):
            complete = False
        summary = {'status': 'complete' if complete else 'incomplete',
                   'seconds': time.perf_counter() - self.started,
                   'counts': dict(counts), 'errors': dict(errors),
                   'file_outcomes': files, 'record_outcomes': records,
                   'provenance': provenance, 'ledger': self.path.name}
        (self.output / 'load_summary.json').write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
        if self.work_path != self.path:
            self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')  # everything into the main file
        self.db.close()
        self.db = None
        if self.work_path != self.path:
            shutil.move(str(self.work_path), str(self.path))
            for suffix in ('-wal', '-shm'):
                Path(str(self.work_path) + suffix).unlink(missing_ok=True)
        return summary
