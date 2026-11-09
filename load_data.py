"""Load all local email corpora with traceable source labels.

A source label is evidence, not a guarantee of human-verified ground truth.
Spam corpora do not distinguish phishing from other spam. Unknown numeric
conventions stay unlabelled; content-based predictions never become labels.

Sources: Dataset/phishing (Nazario mbox + curated CSVs), Dataset/spamassassin,
Dataset/enron, Dataset/EPVME_extracted (synthetic malicious, load_data_epvme),
Dataset/phishing_pot (honeypot phishing, load_data_phishing_pot),
Dataset/trec07p (raw TREC 2007, load_data_trec07p; supersedes TREC_07.csv),
Dataset/malspam (encrypted malware-traffic-analysis.net zips, load_data_malspam).
Files directly in Dataset/ are accounted by record_dataset_root_files():
df.csv is excluded by policy; StealthPhisher2025.csv is a URL corpus for
load_url_dataset(), not email.
"""
import csv
import errno
import functools
import hashlib
import mailbox
import os
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email import policy
from pathlib import Path

import pandas as pd

DATASET_DIR = Path(__file__).resolve().parent / "Dataset"
SOURCE_COUNTS = Counter()
SOURCE_ERRORS = Counter()
SOURCE_ROW_ISSUES = []
SOURCE_PROVENANCE = {}
ACTIVE_AUDIT = None
INCLUDE_SPAM = True
READ_WORKERS = min(32, max(4, (os.cpu_count() or 1) * 4))
DATA_COLUMNS = ["Text", "Class", "Source", "Location", "LabelKind", "OriginalLabel",
                "LabelBasis"]
TEXT_LABEL_KINDS = {
    "ham": "legitimate", "legit": "legitimate", "legitimate": "legitimate",
    "safe email": "legitimate", "phishing": "phishing",
    "phishing email": "phishing", "spam": "spam",
}
KIND_CLASSES = {"legitimate": 0, "phishing": 1, "spam": 1, "spam_or_phishing": 1,
                "malicious_synthetic": 1, "malspam": 1}
# EPVME (Exploiting Protocol Vulnerability Malicious Email): Zhang et al., Cybersecurity 8:14
# (2025), DOI 10.1186/s42400-024-00309-6; github.com/sunknighteric/EPVME-Dataset (GPL-3.0).
# Email tổng hợp: các trường không chứa payload (From/To/Subject/body) được lấy ngẫu nhiên, theo
# từng loại tấn công, từ mẫu lành tính hoặc độc hại của Enron, Nazario, SpamAssassin và TREC07;
# không có bảng ánh xạ nguồn cho từng mẫu. Payload: giả mạo header SPF/DMARC, thao túng chữ ký
# S/MIME/OpenPGP (tấn công CMS/MIME/ID) và XSS lấy từ Wooyun Email XSS (Fang et al., 2020).
# Body của tấn công header phần lớn lấy từ mẫu độc hại (phishing hoặc spam); tấn công chữ ký dựng
# trên body email lành tính có chữ ký, trộn với văn bản phishing/spam và payload; mẫu XSS lấy các
# trường không chứa payload từ mẫu lành tính. Mọi email đều gán nhãn malicious, không phải phishing
# thuần. Không có nhãn loại tấn công theo từng file; attack_family bên dưới chỉ là heuristic để
# đánh giá theo họ tấn công. Dòng "From <...>" đầu file là envelope MAIL FROM của kẻ tấn công,
# nên các file này không bao giờ bị tách như mbox.
EPVME_REFERENCE = "https://github.com/sunknighteric/EPVME-Dataset"
EPVME_DIRNAMES = {"epvme_extracted", "epvme"}
# Phishing Pot: real phishing received by honeypot addresses, CC BY-NC 4.0
# (non-commercial, attribution required). Only email/*.eml are samples; the clone
# also holds .git, docs and images. Record the commit: the corpus keeps growing.
PHISHING_POT_REFERENCE = "https://github.com/rf-peixoto/phishing_pot"
PHISHING_POT_DIRNAME = "phishing_pot"
# TREC 2007 Public Corpus bản thô: mọi thư gửi tới một server của University of Waterloo
# (04-07/2007), nhãn ham/spam trong full/index. Cùng corpus với TREC_07.csv nhưng còn
# header và HTML, nên khi có thư mục này thì CSV bị loại (một email không vào hai lần).
# Mỗi data/inmail.N là một email mở đầu bằng dòng envelope "From ": không tách như mbox.
# Spam không phân biệt phishing, giữ cùng quy ước spam_or_phishing như CSV.
TREC07P_REFERENCE = "https://plg.uwaterloo.ca/~gvcormac/treccorpus07/"
TREC07P_DIRNAME = "trec07p"
TREC07P_KINDS = {"ham": "legitimate", "spam": "spam_or_phishing"}
TREC07P_SUPERSEDES = {
    "trec_07.csv": "Same TREC 2007 corpus with headers/HTML stripped; superseded by raw Dataset/trec07p",
}
SINGLE_MESSAGE_DIRNAMES = EPVME_DIRNAMES | {PHISHING_POT_DIRNAME, TREC07P_DIRNAME}
# Malspam: real malicious emails with malware attachments published by
# malware-traffic-analysis.net, kept as the author's password-protected zips
# (download_malspam.py). Read in memory only; attachments are never written or run.
# download_malspam.py ở đây là bản local (upstream chưa công bố bản của họ); thiếu Dataset/malspam
# thì bỏ qua, không lỗi.
MALSPAM_REFERENCE = "https://www.malware-traffic-analysis.net/"
MALSPAM_DIRNAME = "malspam"
# Windows reports a file that antivirus blocked or quarantined as WinError 225/226;
# Python's open() surfaces that as errno EINVAL without winerror. Real malware samples
# (EPVME, Phishing Pot) trigger it; there it is recorded as a loss, not a read error.
ANTIVIRUS_WINERRORS = {225, 226}
# Files in the dataset root that are recorded but deliberately not loaded as email.
EXCLUDED_DATASET_FILES = {
    "df.csv": ("Undocumented numeric labels 0/1/2; pre-cleaned lowercase text without "
               "MIME, headers or URLs; most rows copy Enron/CEAS/Ling/SpamAssassin CSVs "
               "that are already loaded"),
    "trec07p.tgz.zip": "Kaggle download archive of the TREC 2007 corpus; Dataset/trec07p holds the extracted copy",
}
# File bị một corpus thô thay thế trong lần nạp hiện tại (do load_data_trec07p đăng ký).
SUPERSEDED_FILES = {}
# Labelled URL corpora: not email; load with load_url_dataset().
URL_DATASET_FILES = {
    "stealthphisher2025.csv": {"url": "URL", "label": "Label",
                               "labels": {"phishing": 1, "legitimate": 0}},
}
# Exact published file checksums: https://zenodo.org/records/8339691 .
# These curated CSVs originate in spam/ham corpora. The publication calls the
# positive class phishing, but there is no per-message spam/phishing distinction:
# https://trec.nist.gov/data/spam.html
# https://spamassassin.apache.org/old/publiccorpus/readme.html
# Preserve the binary convention; do NOT promote these positives to pure phishing.
CURATED_CSV_MD5 = {
    "ceas_08.csv": "1f0d59191eec892a709995d48cd8decb",
    "enron.csv": "10489e0fdcc8af6fe62135c689367d40",
    "ling.csv": "eac6399dc0c7ae455aebb64423dadc8b",
    "spamassasin.csv": "d921e0b2333bfaa058bd38193e6b3fbd",
    "trec_05.csv": "ef4023fa9e64247212487b77a4c7d98e",
    "trec_06.csv": "b840dc9477f86c098a71a0dfd25c928e",
    "trec_07.csv": "e5a5ae0de1580965191cb32806dc0dae",
}
# Add new numeric schemas only after checking publisher documentation. Require
# the exact file digest so a reused filename cannot silently reverse 0 and 1.
# Example entry: {"md5": "...", "labels": {"0": "phishing", "1": "legitimate"},
#                 "reference": "publisher URL"}
CSV_LABEL_SCHEMAS = {}
NAZARIO_NAMES = {"20051114.mbox", "phishing0.mbox", "phishing1.mbox",
                 "phishing2.mbox", "phishing3.mbox", "private-phishing4.mbox"}
NAZARIO_NAMES.update(f"phishing-{year}" for year in range(2015, 2026))
EMAIL_HEADER = re.compile(
    br"^(?:from|to|subject|date|message-id|received|mime-version|content-type):",
    re.I | re.M)


def reset_source_stats():
    SOURCE_COUNTS.clear()
    SOURCE_ERRORS.clear()
    SOURCE_ROW_ISSUES.clear()
    SOURCE_PROVENANCE.clear()
    SUPERSEDED_FILES.clear()


def _win_long_path(path):
    path = os.fspath(path)
    if os.name != "nt":
        return path
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    path = os.path.normpath(path)
    prefix = chr(92) * 2 + "?" + chr(92)
    if path.startswith(prefix):
        return path
    if path.startswith(chr(92) * 2):
        return prefix + "UNC" + chr(92) + path[2:]
    return prefix + path


def _open_text_robust(path):
    try:
        with open(_win_long_path(path), "rb") as handle:
            return handle.read(), None, None
    except OSError as exc:
        return None, type(exc).__name__, str(exc)


def _looks_like_mbox(path):
    with open(_win_long_path(path), "rb") as handle:
        return handle.read(5) == b"From "


def _try_split_mbox(path):
    if not (_looks_like_mbox(path) or str(path).lower().endswith(".mbox")):
        return []
    return list(_iter_mbox_messages(path))


def _iter_mbox_messages(path):
    """Stream messages: do not retain another complete copy of an mbox."""
    box = mailbox.mbox(_win_long_path(path), create=False)
    try:
        found = False
        for key in box.iterkeys():
            found = True
            yield box.get_bytes(key)
        if not found:
            raise ValueError('Declared mbox contains no messages')
    finally:
        box.close()


def _audit_record(path, number, status, kind='', reason='', payload=None, csv_record=False):
    if ACTIVE_AUDIT is not None:
        location = f'{path}:{"record" if csv_record else "message"}:{number}'
        ACTIVE_AUDIT.record(path, location, status, kind, reason, payload)


def _classify_spamassassin_label(dirpath, spamassassin_root):
    parts = os.path.relpath(dirpath, spamassassin_root).lower().split(os.sep)
    for part in reversed(parts):
        part = re.sub(r"^\d{8}_", "", part)
        if part in {"easy_ham", "easy_ham_2", "hard_ham", "ham"}:
            return 0
        if part in {"spam", "spam_2"}:
            return 1
    return None


def _file_md5(path):
    digest = hashlib.md5()
    with open(_win_long_path(path), "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest


def _record_non_email_file(path):
    """Account for a known non-email file instead of skipping it silently."""
    key = os.fspath(path)
    if key in SOURCE_PROVENANCE:
        return
    name = os.path.basename(key).lower()
    if name in EXCLUDED_DATASET_FILES or name in SUPERSEDED_FILES:
        status, reason = "excluded", EXCLUDED_DATASET_FILES.get(name) or SUPERSEDED_FILES[name]
        SOURCE_COUNTS["files_excluded_by_policy"] += 1
    else:
        status, reason = "url_dataset", "Labelled URL corpus, not email; use load_url_dataset()"
        SOURCE_COUNTS["url_dataset_files"] += 1
    SOURCE_PROVENANCE[key] = {"status": status, "reason": reason,
                              "bytes": os.path.getsize(_win_long_path(key)),
                              "md5": _file_md5(key).hexdigest()}
    if ACTIVE_AUDIT is not None:
        ACTIVE_AUDIT.file(key, status, reason)
    print(f"  Not loaded as email ({status}): {key}")


def record_dataset_root_files(dataset_dir):
    """Files directly under Dataset/ are not scanned by the corpus loaders; account for them."""
    root = Path(dataset_dir)
    if not root.is_dir():
        return
    for path in sorted(p for p in root.iterdir() if p.is_file()):
        name = path.name.lower()
        if name in EXCLUDED_DATASET_FILES or name in URL_DATASET_FILES:
            _record_non_email_file(path)
        else:
            SOURCE_COUNTS["unregistered_root_files"] += 1
            SOURCE_PROVENANCE[os.fspath(path)] = {"status": "unregistered",
                                                  "reason": "Not in a corpus folder; register it before use"}
            if ACTIVE_AUDIT is not None:
                ACTIVE_AUDIT.file(path, "unregistered", "Not in a corpus folder; register it before use")
            print(f"  Unregistered file in dataset root, not loaded: {path}")


def _csv_schema(path):
    name = os.path.basename(path).lower()
    schema = CSV_LABEL_SCHEMAS.get(name)
    if schema is None and name in CURATED_CSV_MD5:
        schema = {"md5": CURATED_CSV_MD5[name],
                  "labels": {"0": "legitimate", "1": "spam_or_phishing"},
                  "reference": "https://zenodo.org/records/8339691"}
    if schema is None:
        return {}, "unverified_numeric_convention"
    if (not schema.get("md5") or not schema.get("reference") or
            not schema.get("labels") or
            any(kind not in KIND_CLASSES for kind in schema["labels"].values())):
        raise ValueError(f"Invalid source label schema: {name}")
    digest = _file_md5(path)
    matched = digest.hexdigest() == schema["md5"]
    SOURCE_PROVENANCE[os.fspath(path)] = {
        "md5": digest.hexdigest(), "expected_md5": schema["md5"],
        "matched": matched, "reference": schema["reference"],
        "labels": schema["labels"],
    }
    if not matched:
        SOURCE_COUNTS["csv_schema_checksum_mismatch"] += 1
        return {}, "checksum_mismatch; numeric labels require review"
    return schema["labels"], "publisher_schema; md5=" + digest.hexdigest() + "; " + schema["reference"]


def _read_csv_emails(path, with_metadata=False):
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            break
        except OverflowError:
            limit //= 10
    with open(_win_long_path(path), encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        names = reader.fieldnames or []
        columns = {name.strip().lower(): name for name in names}
        if len(columns) != len(names):
            raise ValueError("Duplicate CSV column names")
        def column(*aliases):
            return next((columns[a] for a in aliases if a in columns), None)
        label_col = column("label", "class", "email type", "email_type")
        raw_col = column("raw_email", "email text", "email_text")
        body_col = column("body", "text", "content")
        subject_col = column("subject")
        if not (raw_col or body_col or subject_col):
            # Read/count every row, but vectors are not raw email content.
            count = 0
            for number, row in enumerate(reader, 2):
                count += 1
                _audit_record(path, number, 'no_email_content', reason='Vector/features row; no email text',
                              csv_record=True)
            SOURCE_COUNTS["csv_vector_or_unsupported"] += 1
            SOURCE_COUNTS["csv_rows_without_email_content"] += count
            SOURCE_PROVENANCE[os.fspath(path)] = {
                "status": "no_email_content", "rows": count, "columns": names}
            print(f"  CSV has no email content: {path} ({count} rows)")
            return
        mapping, basis = _csv_schema(path)
        for number, row in enumerate(reader, 2):
            SOURCE_COUNTS["csv_records_read"] += 1
            if None in row or any(value is None for value in row.values()):
                SOURCE_COUNTS["csv_rows_quarantined"] += 1
                SOURCE_ROW_ISSUES.append({
                    "file": os.fspath(path), "record": number, "ending_line": reader.line_num,
                    "reason": "CSV field count differs from header; no safe label/content alignment"})
                _audit_record(path, number, 'quarantined', reason='CSV field count differs from header',
                              payload=row, csv_record=True)
                continue
            original = row.get(label_col, "") or ""
            value = original.strip().casefold()
            kind = TEXT_LABEL_KINDS.get(value)
            label_basis = "explicit_text_label"
            if kind is None:
                kind = mapping.get(value, "unknown")
                label_basis = basis if kind != "unknown" else basis + "; missing/unsupported label: " + value
            label = KIND_CLASSES.get(kind)
            if kind in {"spam", "spam_or_phishing"} and not INCLUDE_SPAM:
                SOURCE_COUNTS["spam_excluded"] += 1
                _audit_record(path, number, 'excluded_by_loader', kind, 'INCLUDE_SPAM=False',
                              payload=row, csv_record=True)
                continue
            if raw_col and (row.get(raw_col) or "").strip():
                text = row[raw_col]
            else:
                body = row.get(body_col, "") or ""
                subject = row.get(subject_col, "") or ""
                if not (body.strip() or subject.strip()):
                    SOURCE_COUNTS["empty"] += 1
                    _audit_record(path, number, 'quarantined', kind, 'Missing subject and body',
                                  payload=row, csv_record=True)
                    continue
                subtype = "html" if re.search(
                    r"<\s*(html|body|a|p|div|table|form|img)\b", body, re.I) else "plain"
                msg = MIMEText(body, _subtype=subtype, _charset="utf-8", policy=policy.compat32)
                for header, aliases in (
                        ("Subject", ("subject",)), ("From", ("sender", "from")),
                        ("To", ("receiver", "to")), ("Date", ("date",)),
                        ("Reply-To", ("reply_to", "reply-to"))):
                    header_value = row.get(column(*aliases), "") or ""
                    if header_value:
                        msg[header] = " ".join(header_value.splitlines())
                text = msg.as_bytes()
            if with_metadata:
                yield (text, label, os.path.basename(path), f"{path}:record:{number}",
                       kind, original, label_basis)
            else:
                yield text, label


def _raw_source_label(path, root, default_label, classify, source_kind, discover):
    relative = os.path.relpath(path, root)
    parts = relative.split(os.sep)
    corpus = parts[0].lower() if discover and len(parts) > 1 else None
    source = parts[0] if corpus else os.path.basename(os.fspath(root).rstrip("/\\"))
    if discover:
        default_label = None
        classify = corpus == "spamassassin"
        source_kind = ("phishing" if corpus == "phishing" else
                       "epvme" if corpus in EPVME_DIRNAMES else
                       "phishing_pot" if corpus == PHISHING_POT_DIRNAME else
                       "trec07p" if corpus == TREC07P_DIRNAME else None)
        if corpus == "enron" and any(p.lower() == "maildir" for p in parts[1:-1]):
            return 0, "legitimate", "enron_maildir_assumption; not individually reviewed", source
    if source_kind == "epvme":
        return 1, "malicious_synthetic", "epvme_publisher_all_malicious; " + EPVME_REFERENCE, "EPVME"
    if source_kind == "phishing_pot":
        # Samples live in email/*.eml; README images, .github and CITATION are not email.
        if os.path.basename(path).lower().endswith(".eml") and Path(path).parent.name.lower() == "email":
            return 1, "phishing", _phishing_pot_basis(path), "phishing_pot"
        return None, "unknown", "phishing_pot_non_sample_file", "phishing_pot"
    if source_kind == "trec07p":
        folder = Path(path).parent
        original = (_trec07p_labels(os.fspath(folder.parent)).get(Path(path).name)
                    if folder.name.lower() == "data" else None)
        kind = TREC07P_KINDS.get(original)
        if kind is None:
            return None, "unknown", "trec07p_file_not_in_full_index", TREC07P_DIRNAME
        return (KIND_CLASSES[kind], kind, f"trec07p_full_index label={original}; {TREC07P_REFERENCE}",
                TREC07P_DIRNAME)
    if classify:
        label = _classify_spamassassin_label(os.path.dirname(path), root)
        if label is not None:
            kind = "legitimate" if label == 0 else "spam"
            return label, kind, "spamassassin_folder; https://spamassassin.apache.org/old/publiccorpus/", source
        return None, "unknown", "unrecognised_spamassassin_folder", source
    if source_kind == "phishing":
        # Only declared Nazario archive names, not every file placed in phishing/.
        if os.path.basename(path).lower() in NAZARIO_NAMES:
            return 1, "phishing", "nazario_source; https://monkey.org/~jose/phishing/", os.path.basename(path)
        return None, "unknown", "unregistered_raw_phishing_source", source
    if default_label is not None:
        kind = "legitimate" if default_label == 0 else source_kind or "positive_unspecified"
        return default_label, kind, "caller_declared_corpus_label; not individually reviewed", source
    return None, "unknown", "raw_source_has_no_verified_label_mapping", source


def _prefetch_raw(path, single_message=False):
    """Bounded parallel disk reads; labels/statistics are handled on one thread."""
    name = os.path.basename(path).lower()
    if name.endswith((".csv", ".zip", ".gz", ".bz2", ".xz", ".tar", ".7z")):
        return None
    try:
        with open(_win_long_path(path), 'rb') as handle:
            prefix = handle.read(8192)
            if not single_message and (prefix.startswith(b'From ') or name.endswith('.mbox')):
                return None, None, 'stream_mbox'
            return prefix + handle.read(), None, None
    except OSError as exc:
        blocked = (getattr(exc, "winerror", None) in ANTIVIRUS_WINERRORS
                   or (os.name == "nt" and exc.errno == errno.EINVAL))
        return None, "AntivirusBlocked" if blocked else type(exc).__name__, str(exc)


def _git_commit(repo):
    """Checked-out commit read from .git without running git; None if unavailable."""
    git = Path(repo) / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head
        ref = head[5:]
        if (git / ref).is_file():
            return (git / ref).read_text(encoding="utf-8").strip()
        for line in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split()[0]
    except OSError:
        pass
    return None


def _phishing_pot_basis(path):
    repo = next((p for p in Path(path).parents if p.name.lower() == PHISHING_POT_DIRNAME), None)
    return _phishing_pot_basis_for(os.fspath(repo) if repo else "")


@functools.lru_cache(maxsize=8)
def _phishing_pot_basis_for(repo):
    commit = _git_commit(repo) if repo else None
    return (f"phishing_pot_publisher_states_phishing (honeypot; may include spam); CC BY-NC 4.0; "
            f"commit={commit or 'unknown'}; {PHISHING_POT_REFERENCE}")


def record_phishing_pot_checkout(pot_dir):
    """Provenance of the Phishing Pot clone: commit and tracked samples absent on disk.

    Antivirus quarantine deletes some samples after checkout; they are listed, not guessed.
    """
    pot_dir = Path(pot_dir)
    if not (pot_dir / "email").is_dir():
        return
    present = {p.name for p in (pot_dir / "email").iterdir() if p.is_file()}
    tracked = None
    # Without its own .git, "git -C" would silently answer for the enclosing project repo.
    if (pot_dir / ".git").exists():
        try:
            listed = subprocess.run(["git", "-C", os.fspath(pot_dir), "ls-files", "-z", "email"],
                                    capture_output=True, check=True, timeout=120).stdout
            tracked = {Path(name).name for name in listed.decode("utf-8").split("\0") if name}
        except (OSError, subprocess.SubprocessError, UnicodeError):
            tracked = None
    missing = sorted(tracked - present) if tracked is not None else None
    SOURCE_COUNTS["phishing_pot_missing_from_checkout"] += len(missing or ())
    SOURCE_PROVENANCE[os.fspath(pot_dir)] = {
        "status": "corpus", "reference": PHISHING_POT_REFERENCE, "license": "CC BY-NC 4.0",
        "commit": _git_commit(pot_dir), "samples_present": len(present),
        "samples_tracked": None if tracked is None else len(tracked),
        "missing_from_checkout": missing}
    if missing:
        print(f"  {pot_dir}: {len(missing)} tracked samples missing on disk (antivirus quarantine?)")


@functools.lru_cache(maxsize=8)
def _trec07p_labels(trec_dir):
    """Tên file trong data/ -> nhãn gốc ('ham'/'spam') đọc từ full/index."""
    labels = {}
    with open(_win_long_path(os.path.join(trec_dir, "full", "index")), encoding="ascii") as handle:
        for line in handle:
            if line.strip():
                label, relative = line.split()
                labels[os.path.basename(relative)] = label.lower()
    return labels


def record_trec07p_extract(trec_dir):
    """Ghi provenance của bản giải nén trec07p và đăng ký các CSV mà nó thay thế.

    Trả về False khi thư mục vắng (corpus tuỳ chọn). File có trong index nhưng thiếu trên
    đĩa (antivirus xoá sau khi giải nén) được liệt kê, không đoán.
    """
    trec_dir = Path(trec_dir)
    if not trec_dir.is_dir():
        print(f"  Missing dataset directory: {trec_dir}")
        return False
    index = trec_dir / "full" / "index"
    if not index.is_file():
        SOURCE_ERRORS["trec07p_missing_index"] += 1
        print(f"  Missing label index: {index}")
        return False
    loaded = [key for key, info in SOURCE_PROVENANCE.items()
              if os.path.basename(key).lower() in TREC07P_SUPERSEDES and info.get("status") != "excluded"]
    if loaded:
        # TREC_07.csv đã được nạp: thêm bản thô lúc này sẽ đưa cùng email vào hai lần.
        raise RuntimeError(f"Load trec07p before the CSVs it supersedes: {loaded}")
    labels = _trec07p_labels(os.fspath(trec_dir))
    data = trec_dir / "data"
    present = {p.name for p in data.iterdir() if p.is_file()} if data.is_dir() else set()
    missing = sorted(set(labels) - present, key=lambda n: (len(n), n))
    SOURCE_COUNTS["trec07p_missing_from_extract"] += len(missing)
    SOURCE_PROVENANCE[os.fspath(trec_dir)] = {
        "status": "corpus", "reference": TREC07P_REFERENCE, "index_md5": _file_md5(index).hexdigest(),
        "index_labels": dict(Counter(labels.values())), "samples_present": len(present),
        "missing_from_extract": missing}
    SUPERSEDED_FILES.update(TREC07P_SUPERSEDES)
    if missing:
        print(f"  {trec_dir}: {len(missing)} indexed messages missing on disk (antivirus quarantine?)")
    return True


def _epvme_attack_family(message):
    """Heuristic attack family from EPVME generator conventions; not a label."""
    head = re.split(rb"\r?\n\r?\n", message, maxsplit=1)[0][:16384]
    subject = re.search(rb"^Subject:[ \t]*(.*?)\s*$", head, re.I | re.M)
    subject = subject.group(1).lower() if subject else b""
    if subject == b"cms attack sample":
        return "cms_signature"
    if subject == b"mime attack sample":
        return "mime_wrapping"
    if subject in (b"test xss", b"xss test mail"):
        return "xss"
    if head.startswith(b"From "):
        return "mail_from_inconsistency"
    if len(re.findall(rb"^From:", head, re.I | re.M)) > 1:
        return "multiple_from"
    if re.search(rb"^(From|To|Subject):.*(<\s*(script|img|svg|iframe)\b|\bon[a-z]+\s*=|javascript:)",
                 head, re.I | re.M):
        return "xss"
    if re.search(rb"^From:.*(=\?|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff])", head, re.I | re.M):
        return "from_injection"
    if re.search(rb"^From:.*@(test|security)\.", head, re.I | re.M):
        return "subdomain"
    if re.search(rb"<script\b|\bon[a-z]+\s*=|javascript:", message, re.I):
        return "xss"
    return "unattributed"


def _iter_rows(root_dir, default_label=None, classify=False, optional=False,
               source_kind=None, discover=False, single_message=False, antivirus_ok=False):
    root = _win_long_path(root_dir)
    if not os.path.isdir(root):
        print(f"  Missing dataset directory: {root_dir}")
        if not optional:
            SOURCE_ERRORS["missing_directory"] += 1
        return
    def onerror(exc):
        SOURCE_ERRORS[type(exc).__name__] += 1
        print(f"  Directory read failed: {exc}")
    total = loaded = 0
    def keep_whole(path):
        return single_message or (discover and os.path.relpath(path, root).split(os.sep)[0].lower()
                                  in SINGLE_MESSAGE_DIRNAMES)
    with ThreadPoolExecutor(max_workers=READ_WORKERS) as readers:
        for directory, dirs, files in os.walk(root, onerror=onerror):
            if ".git" in dirs:  # Version-control objects of a cloned corpus, never email.
                SOURCE_COUNTS["vcs_directories_skipped"] += 1
            dirs[:] = sorted(d for d in dirs if d != ".git")  # Other hidden directories can contain emails.
            for dirname in list(dirs):
                linked = os.path.join(directory, dirname)
                if os.path.islink(linked):
                    SOURCE_ERRORS['untraversed_symlink_directory'] += 1
                    if ACTIVE_AUDIT is not None:
                        ACTIVE_AUDIT.file(linked, 'failed', 'Symlink directory requires an explicit dataset root')
                    dirs.remove(dirname)
            files = sorted(files)
            for offset in range(0, len(files), 128):
                batch = files[offset:offset + 128]
                payloads = readers.map(lambda p: _prefetch_raw(p, keep_whole(p)),
                                       (os.path.join(directory, n) for n in batch))
                for name, payload in zip(batch, payloads):
                    low = name.lower()
                    path = os.path.join(directory, name)
                    if low in EXCLUDED_DATASET_FILES or low in URL_DATASET_FILES or low in SUPERSEDED_FILES:
                        _record_non_email_file(path)
                        continue
                    corpus = os.path.relpath(path, root).split(os.sep)[0].lower() if discover else None
                    if corpus == MALSPAM_DIRNAME:
                        reason = "Encrypted malspam archive; read by load_data_malspam()"
                        SOURCE_PROVENANCE[path] = {"status": "excluded", "reason": reason}
                        if ACTIVE_AUDIT is not None:
                            ACTIVE_AUDIT.file(path, "excluded", reason)
                        continue
                    in_pot = source_kind == "phishing_pot" or corpus == PHISHING_POT_DIRNAME
                    in_trec = source_kind == "trec07p" or corpus == TREC07P_DIRNAME
                    reason = None
                    if in_pot and not low.endswith(".eml"):
                        # email/sample-3989.csv is a leaked list of personal data, not a sample.
                        reason = "Phishing Pot sample folder holds only .eml; other files are not read"
                    elif in_trec and Path(path).parent.name.lower() != "data":
                        # full/delay/partial/index là danh sách nhãn, README là mô tả: không phải email.
                        reason = "trec07p: only data/inmail.* are messages; index and README files are not read"
                    if reason:
                        SOURCE_COUNTS["files_excluded_by_policy"] += 1
                        SOURCE_PROVENANCE[path] = {"status": "excluded", "reason": reason}
                        if ACTIVE_AUDIT is not None:
                            ACTIVE_AUDIT.file(path, "excluded", reason)
                        continue
                    if ACTIVE_AUDIT is not None:
                        ACTIVE_AUDIT.file(path, 'reading')
                    metadata_name = (low.startswith('.') or low.startswith(('readme', 'license', 'copying'))
                                     or low == 'cmds' or low.endswith('.md'))
                    if (metadata_name and payload is not None and payload[1] is None
                            and payload[2] != 'stream_mbox' and not EMAIL_HEADER.search(payload[0][:8192])):
                        SOURCE_COUNTS['metadata_skipped'] += 1
                        if ACTIVE_AUDIT is not None:
                            ACTIVE_AUDIT.file(path, 'metadata', 'No email headers in metadata-named file')
                        continue
                    total += 1
                    SOURCE_COUNTS["files_scanned"] += 1
                    if total % 5000 == 0:
                        print(f"  {root_dir}: scanned {total} files; loaded {loaded} emails", flush=True)
                    try:
                        if low.endswith((".zip", ".gz", ".bz2", ".xz", ".tar", ".7z")):
                            raise ValueError("Extract archive before training")
                        if low.endswith(".csv"):
                            found = _read_csv_emails(path, with_metadata=True)
                        else:
                            label, kind, basis, source = _raw_source_label(
                                path, root, default_label, classify, source_kind, discover)
                            if kind == "spam" and not INCLUDE_SPAM:
                                SOURCE_COUNTS["spam_excluded"] += 1
                                # Still enumerate and account for every message in this file.
                            content, error, detail = payload
                            if error and antivirus_ok and error in ("AntivirusBlocked", "FileNotFoundError"):
                                SOURCE_COUNTS["files_blocked_by_antivirus"] += 1
                                if ACTIVE_AUDIT is not None:
                                    ACTIVE_AUDIT.file(path, 'antivirus_blocked', detail)
                                print(f"  Blocked or removed by antivirus, not loaded: {path}")
                                continue
                            if error:
                                raise OSError(detail)
                            if detail == 'stream_mbox':
                                messages = _iter_mbox_messages(path)
                            else:
                                messages = [content]
                            found = _raw_rows(messages, path, label, kind, basis, source)
                        for row in found:
                            loaded += 1
                            SOURCE_COUNTS["emails_loaded"] += 1
                            SOURCE_COUNTS["label_kind/" + row[4]] += 1
                            SOURCE_COUNTS["source/" + row[2]] += 1
                            if ACTIVE_AUDIT is not None:
                                ACTIVE_AUDIT.record(path, row[3], 'loaded', row[4], row[6])
                            yield row
                        if ACTIVE_AUDIT is not None:
                            ACTIVE_AUDIT.file(path, 'complete')
                    except (OSError, UnicodeError, csv.Error, ValueError, mailbox.Error) as exc:
                        SOURCE_ERRORS[type(exc).__name__] += 1
                        if ACTIVE_AUDIT is not None:
                            ACTIVE_AUDIT.file(path, 'failed', str(exc))
                        print(f"  Read failed: {path}: {exc}")
    print(f"  {root_dir}: {total} files -> {loaded} emails (including unknown labels)", flush=True)


def _raw_rows(messages, path, label, kind, basis, source):
    for index, message in enumerate(messages):
        if not message.strip():
            SOURCE_COUNTS['empty'] += 1
            _audit_record(path, index, 'quarantined', kind, 'Empty raw message', payload='')
            continue
        if kind == 'spam' and not INCLUDE_SPAM:
            _audit_record(path, index, 'excluded_by_loader', kind, 'INCLUDE_SPAM=False')
            continue
        message_label, message_kind, message_basis = label, kind, basis
        if kind == 'malicious_synthetic':
            message_basis += f'; attack_family={_epvme_attack_family(message)} (heuristic)'
        if not EMAIL_HEADER.search(message[:8192]):
            SOURCE_COUNTS['raw_rows_needing_review'] += 1
            SOURCE_ROW_ISSUES.append({'file': path, 'record': index, 'ending_line': None,
                                     'reason': 'No recognised raw email headers; retained with unknown label'})
            message_label, message_kind = None, 'unknown'
            message_basis += '; review_required; original source kind=' + kind
        yield (message, message_label, source, f'{path}:message:{index}',
               message_kind, 'source_assigned', message_basis)


def _read_rows(root_dir, default_label=None, **kwargs):
    return list(_iter_rows(root_dir, default_label, **kwargs))


def _append_rows(data, rows):
    frame = pd.DataFrame.from_records(rows, columns=DATA_COLUMNS)
    frames = [part for part in (data, frame) if not part.empty]
    return (pd.concat(frames, ignore_index=True).dropna(subset=["Text"])
            if frames else pd.DataFrame(columns=DATA_COLUMNS))


def load_all_datasets(dataset_dir=None):
    """Scan the complete Dataset tree once; retain unknown labels for review."""
    dataset_dir = Path(dataset_dir or DATASET_DIR)
    # Đăng ký TREC_07.csv bị thay thế trước khi duyệt tới thư mục phishing/.
    record_trec07p_extract(dataset_dir / TREC07P_DIRNAME)
    return _append_rows(pd.DataFrame(), _iter_rows(dataset_dir, discover=True))


def _read_raw_emails(root_dir, verbose=True):
    return [row[0] for row in _read_rows(root_dir, 0)]


def load_data_generic(data, root_dir, label):
    if label not in (0, 1):
        raise ValueError("label must be 0 or 1")
    return _append_rows(data, _iter_rows(root_dir, label))


def load_data_phishing(data, phishing_dir=None):
    return _append_rows(data, _iter_rows(
        phishing_dir or DATASET_DIR / "phishing", source_kind="phishing"))


def load_data_spamassassin(data_phishing, data_legit, spamassassin_dir=None):
    frame = _append_rows(pd.DataFrame(), _iter_rows(
        spamassassin_dir or DATASET_DIR / "spamassassin", classify=True, optional=True))
    # Preserve unknowns in the first result rather than silently dropping them.
    return (_append_rows(data_phishing, frame[frame.Class != 0].itertuples(index=False, name=None)),
            _append_rows(data_legit, frame[frame.Class == 0].itertuples(index=False, name=None)))


def load_data_epvme(data, epvme_dir=None):
    """EPVME synthetic attacks; an absent folder is not an error."""
    return _append_rows(data, _iter_rows(
        epvme_dir or DATASET_DIR / "EPVME_extracted", source_kind="epvme",
        optional=True, single_message=True, antivirus_ok=True))


def load_data_phishing_pot(data, pot_dir=None):
    """Phishing Pot honeypot samples (email/*.eml only); an absent folder is not an error."""
    pot_dir = Path(pot_dir or DATASET_DIR / PHISHING_POT_DIRNAME)
    record_phishing_pot_checkout(pot_dir)
    return _append_rows(data, _iter_rows(
        pot_dir / "email", source_kind="phishing_pot", optional=True,
        single_message=True, antivirus_ok=True))


def load_data_trec07p(data_phishing, data_legit, trec_dir=None):
    """TREC 2007 thô (data/inmail.*, nhãn theo full/index); thư mục vắng thì không lỗi.

    Phải gọi trước load_data_phishing: khi có bản thô, TREC_07.csv bị loại.
    """
    trec_dir = Path(trec_dir or DATASET_DIR / TREC07P_DIRNAME)
    if not record_trec07p_extract(trec_dir):
        return data_phishing, data_legit
    frame = _append_rows(pd.DataFrame(), _iter_rows(
        trec_dir / "data", source_kind="trec07p", single_message=True, antivirus_ok=True))
    # Giống SpamAssassin: nhãn chưa rõ (nếu có) đi cùng phía dương để còn được rà soát.
    return (_append_rows(data_phishing, frame[frame.Class != 0].itertuples(index=False, name=None)),
            _append_rows(data_legit, frame[frame.Class == 0].itertuples(index=False, name=None)))


def _malspam_passwords(name):
    """Site scheme: infected_YYYYMMDD from the post date in the file name; older posts: infected."""
    found = re.match(r"(\d{4})-(\d{2})-(\d{2})", name)
    return ([f"infected_{''.join(found.groups())}".encode()] if found else []) + [b"infected"]


# The whole To value, folded continuation lines included.
_MALSPAM_TO = re.compile(rb"^To:([^\r\n]*(?:\r?\n[ \t][^\r\n]*)*)", re.I | re.M)


def _with_recipient(message):
    """The site removed To from most samples, or left only "[removed]"; real mail has a
    recipient, so num_recipients=0 would identify this source. Restore the neutral
    recipient that preprocess also writes for "[recipient's email address]"."""
    split = re.search(rb"\r?\n\r?\n", message)
    head = message[:split.start()] if split else message
    found = _MALSPAM_TO.search(head)
    # Recipient placeholders become an address in preprocess; other bracketed redactions vanish.
    value = re.sub(rb"\[(?![^\]]*recip)[^\]]*\]", b"", found.group(1)) if found else b""
    if value.strip():
        return message
    SOURCE_COUNTS["malspam_recipient_header_restored"] += 1
    if found:  # blank or only a redaction
        return message[:found.start()] + b"To: recipient@recipient-domain.example" + message[found.end():]
    # After an mbox "From " envelope line, if any, so the parser still sees it first.
    envelope = message.index(b"\n") + 1 if message.startswith(b"From ") and b"\n" in message else 0
    return message[:envelope] + b"To: recipient@recipient-domain.example\r\n" + message[envelope:]


def _iter_malspam_rows(malspam_dir):
    import zipfile
    import zlib
    root = Path(malspam_dir)
    if not root.is_dir():
        print(f"  Missing dataset directory: {root}")
        return
    archives = sorted(p for p in root.rglob("*.zip") if p.is_file())
    loaded = 0
    for path in archives:
        location = os.fspath(path)
        SOURCE_COUNTS["files_scanned"] += 1
        if ACTIVE_AUDIT is not None:
            ACTIVE_AUDIT.file(location, "reading")
        messages, skipped = [], 0
        try:
            with zipfile.ZipFile(_win_long_path(path)) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    if not member.filename.lower().endswith(".eml") or member.file_size > 64 * 1024 * 1024:
                        skipped += 1  # pcaps, .msg, malware binaries: never extracted
                        continue
                    for password in _malspam_passwords(path.name):
                        try:
                            messages.append(_with_recipient(archive.read(member, pwd=password)))
                            break
                        except (RuntimeError, zipfile.BadZipFile, zlib.error):  # wrong password (ZipCrypto
                            continue                                              # may fail only at CRC)
                    else:
                        SOURCE_COUNTS["malspam_members_wrong_password"] += 1
                        SOURCE_ROW_ISSUES.append({"file": location, "record": member.filename, "ending_line": None,
                                                  "reason": "Malspam .eml not decrypted with the site password scheme"})
        except (zipfile.BadZipFile, OSError) as exc:
            SOURCE_ERRORS[type(exc).__name__] += 1
            if ACTIVE_AUDIT is not None:
                ACTIVE_AUDIT.file(location, "failed", str(exc))
            print(f"  Read failed: {path}: {exc}")
            continue
        SOURCE_COUNTS["malspam_non_email_members_skipped"] += skipped
        basis = f"malware-traffic-analysis.net post {path.name[:10]}; published as malicious email; {MALSPAM_REFERENCE}"
        for row in _raw_rows(messages, location, 1, "malspam", basis, "malspam"):
            loaded += 1
            SOURCE_COUNTS["emails_loaded"] += 1
            SOURCE_COUNTS["label_kind/" + row[4]] += 1
            SOURCE_COUNTS["source/" + row[2]] += 1
            if ACTIVE_AUDIT is not None:
                ACTIVE_AUDIT.record(location, row[3], "loaded", row[4], row[6])
            yield row
        if ACTIVE_AUDIT is not None:
            ACTIVE_AUDIT.file(location, "complete")
    print(f"  {root}: {len(archives)} archives -> {loaded} emails", flush=True)


def load_data_malspam(data, malspam_dir=None):
    """Malspam emails (malware attachments); an absent folder is not an error."""
    return _append_rows(data, _iter_malspam_rows(malspam_dir or DATASET_DIR / MALSPAM_DIRNAME))


def load_url_dataset(path=None):
    """Labelled URL corpus -> URL, Class, Source, Location, LabelKind, LabelBasis.

    Rows with unknown labels keep Class=NaN; the same URL with both labels is
    marked as a conflict. Neither is ever repaired by guessing.
    """
    path = Path(path or DATASET_DIR / "StealthPhisher2025.csv")
    spec = URL_DATASET_FILES.get(path.name.lower())
    if spec is None:
        raise ValueError(f"Unregistered URL dataset: {path.name}; add its columns/labels to URL_DATASET_FILES")
    frame = pd.read_csv(_win_long_path(path), usecols=[spec["url"], spec["label"]], dtype=str,
                        keep_default_na=False, encoding="utf-8-sig")
    frame = frame.rename(columns={spec["url"]: "URL", spec["label"]: "OriginalLabel"})
    digest = _file_md5(path).hexdigest()
    frame["Class"] = frame.OriginalLabel.str.strip().str.casefold().map(spec["labels"])
    frame["Source"] = path.name
    frame["Location"] = [f"{path}:record:{number}" for number in range(2, len(frame) + 2)]
    frame["LabelKind"] = frame.Class.map({1: "phishing_url", 0: "legitimate_url"}).fillna("unknown")
    frame["LabelBasis"] = f"publisher_text_label column {spec['label']}; md5={digest}"
    url_key = frame.URL.str.strip()
    conflicting = url_key.map(frame.groupby(url_key).Class.nunique()) > 1
    frame.loc[conflicting, ["Class", "LabelKind"]] = [float("nan"), "conflicting_labels"]
    empty = url_key.eq("")
    frame.loc[empty, ["Class", "LabelKind"]] = [float("nan"), "missing_url"]
    SOURCE_PROVENANCE[os.fspath(path)] = {
        "status": "url_dataset", "md5": digest, "rows": len(frame),
        "label_kinds": {str(k): int(v) for k, v in frame.LabelKind.value_counts().items()},
        "exact_duplicate_urls": int(url_key.duplicated().sum())}
    return frame[["URL", "Class", "Source", "Location", "LabelKind", "OriginalLabel", "LabelBasis"]]


def load_data_enron(data_enron, type_of_data, enron_dir=None, n_phishing=None, seed=42):
    data = _append_rows(data_enron, _iter_rows(enron_dir or DATASET_DIR / "enron", 0))
    if type_of_data == 1 and n_phishing is not None:
        legit, other = data[data.Class == 0], data[data.Class != 0]
        if len(legit) > n_phishing:
            legit = legit.sample(n=n_phishing, random_state=seed)
        data = pd.concat([legit, other], ignore_index=True)
    return data


def audit_dataset(dataset_dir, output):
    """Read every source record without building an in-memory training DataFrame."""
    global ACTIVE_AUDIT
    from dataset_audit import DatasetAudit
    reset_source_stats()
    dataset = Path(dataset_dir)
    audit = DatasetAudit(output)
    ACTIVE_AUDIT = audit
    try:
        # Bản thô trec07p đi trước để TREC_07.csv được loại khi duyệt phishing/.
        trec07p = ((dataset / TREC07P_DIRNAME / 'data', {'source_kind': 'trec07p', 'single_message': True,
                                                         'antivirus_ok': True}),)
        sources = (trec07p if record_trec07p_extract(dataset / TREC07P_DIRNAME) else ()) + (
                   (dataset / 'phishing', {'source_kind': 'phishing'}),
                   (dataset / 'spamassassin', {'classify': True, 'optional': True}),
                   (dataset / 'enron', {'default_label': 0}),
                   (dataset / 'EPVME_extracted', {'source_kind': 'epvme', 'optional': True,
                                                  'single_message': True, 'antivirus_ok': True}),
                   (dataset / PHISHING_POT_DIRNAME / 'email', {'source_kind': 'phishing_pot', 'optional': True,
                                                               'single_message': True, 'antivirus_ok': True}))
        record_phishing_pot_checkout(dataset / PHISHING_POT_DIRNAME)
        for root, settings in sources:
            for _ in _iter_rows(root, **settings):
                pass
        for _ in _iter_malspam_rows(dataset / MALSPAM_DIRNAME):
            pass
        record_dataset_root_files(dataset)
    finally:
        ACTIVE_AUDIT = None
        summary = audit.finish(SOURCE_COUNTS, SOURCE_ERRORS, SOURCE_PROVENANCE)
    pd.DataFrame(SOURCE_ROW_ISSUES, columns=['file', 'record', 'ending_line', 'reason']).to_csv(
        Path(output) / 'csv_rows_quarantined.csv', index=False)
    if summary['status'] != 'complete':
        raise RuntimeError('Ingestion audit is incomplete; inspect load_summary.json and ingestion.sqlite')
    return summary
