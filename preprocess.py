# #### Cleaning + feature engineering
#
# Giữ nguyên các hàm gốc của repo (cleanText, spelling_correction,
# remove_stopwords, tokenize_text) để unit-test.py không bị vỡ.
#
# Bổ sung thêm các hàm trích xuất đặc trưng (feature engineering) cho ĐẦY ĐỦ
# các nhóm kỹ thuật phát hiện phishing, không chỉ dựa vào nội dung văn bản:
#   - extract_url_features            (nhóm URL)
#   - extract_header_features         (nhóm Header)
#   - extract_html_features           (nhóm HTML/structure)
#   - extract_attachment_features     (nhóm Attachment)
#   - extract_social_engineering_features (nhóm Social-engineering)
#   - extract_content_stats_features  (nhóm Content/NLP thống kê)
#   - extract_engineered_features(raw_text) -> list[float]  (hàm tổng, dùng
#     trong train.py, PHẢI được gọi trên text GỐC, trước khi cleanText() xoá
#     mất URL/HTML/header)

from bs4 import BeautifulSoup
import re
import hashlib
import json
import unicodedata
import html as html_module
from email import policy
from email.header import decode_header
from functools import lru_cache
from collections import defaultdict
from textblob import TextBlob
import nltk
from nltk.corpus import wordnet
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

import email
from email.utils import parseaddr, getaddresses
from urllib.parse import urlparse


# --------------------------------------------------------------------------
# Các hàm GỐC của repo (không đổi logic, giữ tương thích unit-test.py)
# --------------------------------------------------------------------------

def cleanText(text):
    """Use decoded MIME body and subject, preserving Unicode and word boundaries."""
    msg = _parse_email(text)
    plain, markup = _get_email_body(msg)
    body = "\n".join(dict.fromkeys(p for p in (plain, _strip_html(markup)) if p.strip()))
    text = str(msg.get("Subject", "")) + "\n" + body
    text = URL_REGEX.sub(" urltoken ", text)
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def spelling_correction(text):
    text = TextBlob(text)
    text = text.correct()
    return text


def remove_stopwords(text):
    return ' '.join(w for w in tokenize_text(text) if w not in _english_stopwords())


def tokenize_text(text):
    return [w.lower() for w in re.findall(r"\b\w+\b", str(text)) if len(w) >= 2]


# --------------------------------------------------------------------------
# Danh sách từ khoá / domain tham chiếu cho các nhóm kỹ thuật bổ sung
# --------------------------------------------------------------------------

URL_REGEX = re.compile(r'(https?://[^\s"\'<>\)\]]+|www\.[^\s"\'<>\)\]]+)', re.IGNORECASE)



SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd", "buff.ly",
    "adf.ly", "bit.do", "cutt.ly", "rb.gy", "shorte.st", "s.id", "tiny.cc",
}

SUSPICIOUS_TLDS = {
    ".zip", ".top", ".xyz", ".click", ".country", ".gq", ".tk", ".ml",
    ".cf", ".ga", ".work", ".support", ".loan", ".men", ".review", ".win",
}

FREEMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "mail.com", "protonmail.com", "yandex.com", "gmx.com",
}

EXECUTABLE_EXTENSIONS = {
    ".exe", ".scr", ".bat", ".cmd", ".com", ".pif", ".js", ".jse", ".vbs",
    ".vbe", ".jar", ".msi", ".ps1", ".wsf", ".hta",
}
MACRO_EXTENSIONS = {".docm", ".xlsm", ".pptm", ".dotm", ".xltm"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".ace", ".iso"}

URGENCY_KEYWORDS = [
    "urgent", "immediately", "act now", "act fast", "expire", "expires",
    "expiring", "suspend", "suspended", "suspension", "verify your account",
    "verify now", "confirm your account", "within 24 hours",
    "limited time", "final notice", "last warning", "account will be closed",
    "unauthorized access", "unusual activity", "security alert",
]
SENSITIVE_INFO_KEYWORDS = [
    "password", "social security", "ssn", "credit card", "card number",
    "cvv", "pin number", "bank account", "routing number", "login credentials",
    "update your billing", "confirm your identity", "date of birth",
]
BRAND_KEYWORDS = [
    "paypal", "amazon", "apple", "microsoft", "google", "netflix", "irs",
    "bank of america", "wells fargo", "chase", "dhl", "fedex", "usps",
    "linkedin", "facebook", "instagram", "docusign", "office365",
]
GENERIC_GREETINGS = [
    "dear customer", "dear user", "dear valued customer", "dear member",
    "dear account holder", "dear sir/madam", "dear sir", "dear madam",
    "dear client", "hello customer",
]
REWARD_KEYWORDS = [
    "congratulations", "you have won", "you've won", "claim your prize",
    "free gift", "winner", "lottery", "selected to receive",
]


# --------------------------------------------------------------------------
# Helpers nội bộ để tách raw email -> plain/html body
# --------------------------------------------------------------------------

def _safe_decode(part):
    payload = part.get_payload(decode=True)
    if payload is None:
        value = part.get_payload()
        return value if isinstance(value, str) else ""
    for charset in (part.get_content_charset(), "utf-8", "windows-1252", "latin-1"):
        if charset:
            try:
                return payload.decode(charset)
            except (LookupError, UnicodeError):
                pass
    return payload.decode("utf-8", errors="replace")


def _get_email_body(msg):
    plain, markup = [], []
    def visit(part):
        if part.get_content_disposition() == "attachment" or part.get_filename():
            return
        if part.is_multipart():
            for child in part.get_payload():
                visit(child)
        elif part.get_content_type() in ("text/plain", "text/html"):
            value = _safe_decode(part)
            is_html = part.get_content_type() == "text/html" or bool(re.search(r"<\s*(html|body|a|div|p|table|form|img)\b", value, re.I))
            (markup if is_html else plain).append(value)
    visit(msg)
    return "\n".join(plain), "\n".join(markup)


def _strip_html(html):
    if not html:
        return ""
    if "<" not in html:
        return re.sub(r"\s+", " ", html_module.unescape(html)).strip()
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    except Exception:
        text = re.sub(r"<[^>]*>", " ", html)
    return re.sub(r"\s+", " ", html_module.unescape(text)).strip()


# --------------------------------------------------------------------------
# 1. Content/NLP thống kê (bổ sung thêm cạnh cleanText/tokenize gốc)
# --------------------------------------------------------------------------

def extract_content_stats_features(plain_text, html_text, subject):
    body_text = "\n".join(dict.fromkeys(p for p in (plain_text, _strip_html(html_text)) if p.strip()))
    full_text = f"{subject}\n{body_text}"
    words = re.findall(r"\b\w+\b", full_text, re.UNICODE)
    n_words = max(len(words), 1)
    uppercase_words = sum(1 for w in words if len(w) > 2 and w.isupper())
    return {
        "char_length": len(body_text),
        "word_count": len(words),
        "uppercase_word_ratio": uppercase_words / n_words,
        "exclamation_count": full_text.count("!"),
        "exclamation_in_subject": subject.count("!"),
        "money_symbol_count": len(re.findall(r"[$\u20ac\u00a3\u00a5]", full_text)),
        "digit_ratio": sum(c.isdigit() for c in full_text) / max(len(full_text), 1),
    }, full_text.lower()


# --------------------------------------------------------------------------
# 2. URL-based
# --------------------------------------------------------------------------

def _safe_urlparse(url):
    """
    urlparse() có thể raise ValueError trên URL rác/malformed trong email
    thật (vd chứa dấu '[' khiến parser tưởng nhầm là IPv6 host và bị Python
    reject). Bọc lại để 1 URL lỗi không làm crash toàn bộ pipeline trích
    xuất feature -- chỉ đơn giản coi URL đó là không xác định được domain.
    """
    try:
        return urlparse(url)
    except ValueError:
        return urlparse("")


def extract_url_features(plain_text, html_text):
    combined = f"{plain_text}\n{_strip_html(html_text)}\n{html_text}"
    urls = sorted(set(u.rstrip('.,);') for u in URL_REGEX.findall(combined)))
    total_urls_found = len(urls)
    # tránh email "URL-bombing" làm chậm parser

    ip_urls = shortened = at_symbol = https_count = http_count = suspicious_tld = 0
    lengths, domains = [], set()
    ip_pattern = re.compile(r"^(\d{1,3}\.){3}\d{1,3}")

    for u in urls:
        lengths.append(len(u))
        if "@" in u:
            at_symbol += 1
        if u.lower().startswith("https://"):
            https_count += 1
        elif u.lower().startswith("http://"):
            http_count += 1
        netloc = _safe_urlparse(u if "://" in u else "http://" + u).netloc.lower()
        host = (_safe_urlparse(u if "://" in u else "http://" + u).hostname or "").lower()
        if host:
            domains.add(host)
            if ip_pattern.match(host):
                ip_urls += 1
            if host in SHORTENER_DOMAINS:
                shortened += 1
            if any(host.endswith(tld) for tld in SUSPICIOUS_TLDS):
                suspicious_tld += 1

    mismatch = 0
    if html_text:
        for i, m in enumerate(re.finditer(
                r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                html_text, flags=re.IGNORECASE | re.DOTALL)):
            href, anchor_html = m.group(1), m.group(2)
            anchor_urls = URL_REGEX.findall(_strip_html(anchor_html))
            if anchor_urls:
                href_domain = _safe_urlparse(href if "://" in href else "http://" + href).netloc.lower()
                anchor_domain = _safe_urlparse(
                    anchor_urls[0] if "://" in anchor_urls[0] else "http://" + anchor_urls[0]
                ).netloc.lower()
                if href_domain and anchor_domain and href_domain != anchor_domain:
                    mismatch += 1

    return {
        "num_urls": total_urls_found,
        "num_unique_domains": len(domains),
        "num_ip_urls": ip_urls,
        "num_shortened_urls": shortened,
        "num_at_symbol_urls": at_symbol,
        "num_https_urls": https_count,
        "num_http_urls": http_count,
        "num_suspicious_tld_urls": suspicious_tld,
        "avg_url_length": (sum(lengths) / len(lengths)) if lengths else 0.0,
        "max_url_length": max(lengths) if lengths else 0,
        "num_anchor_href_mismatch": mismatch,
    }


# --------------------------------------------------------------------------
# 3. Header-based
# --------------------------------------------------------------------------

def extract_header_features(msg):
    from_header = msg.get("From", "") or ""
    reply_to = msg.get("Reply-To", "") or ""
    to_header = msg.get("To", "") or ""
    subject = msg.get("Subject", "") or ""
    date_header = msg.get("Date", "")
    received_headers = msg.get_all("Received", []) or []

    display_name, from_addr = parseaddr(from_header)
    from_domain = from_addr.split("@")[-1].lower() if "@" in from_addr else ""
    reply_addr = parseaddr(reply_to)[1]
    reply_domain = reply_addr.split("@")[-1].lower() if "@" in reply_addr else ""
    reply_to_mismatch = bool(reply_domain and from_domain and reply_domain != from_domain)

    display_lower = display_name.lower()
    brand_in_display = any(b in display_lower for b in BRAND_KEYWORDS)
    sender_is_freemail = from_domain in FREEMAIL_DOMAINS
    brand_freemail_mismatch = bool(brand_in_display and sender_is_freemail)

    recipients = getaddresses([to_header])
    num_recipients = len([a for _, a in recipients if a])

    return {
        "from_domain_is_freemail": int(sender_is_freemail),
        "reply_to_differs_from_sender": int(reply_to_mismatch),
        "display_name_brand_freemail_mismatch": int(brand_freemail_mismatch),
        "num_recipients": num_recipients,
        "num_received_hops": len(received_headers),
        "has_date_header": int(bool(date_header)),
        "subject_is_reply_or_fwd": int(bool(re.match(r"^\s*(re|fw|fwd)\s*:", subject, re.IGNORECASE))),
        "from_display_name_length": len(display_name),
    }


# --------------------------------------------------------------------------
# 4. HTML/structure
# --------------------------------------------------------------------------

def extract_html_features(html_text):
    if not html_text:
        return {
            "is_html": 0, "has_form_tag": 0, "has_script_tag": 0,
            "has_hidden_elements": 0, "is_image_only": 0, "html_to_text_ratio": 0.0,
        }
    stripped = _strip_html(html_text)
    has_form = int(bool(re.search(r"<form[\s>]", html_text, re.IGNORECASE)))
    has_script = int(bool(re.search(r"<script[\s>]", html_text, re.IGNORECASE)))
    has_hidden = int(bool(re.search(
        r'display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0|hidden=["\']?hidden',
        html_text, re.IGNORECASE)))
    num_images = len(re.findall(r"<img[\s>]", html_text, re.IGNORECASE))
    is_image_only = int(num_images > 0 and len(stripped.split()) < 15)
    ratio = (len(stripped) / len(html_text)) if html_text else 0.0
    return {
        "is_html": 1, "has_form_tag": has_form, "has_script_tag": has_script,
        "has_hidden_elements": has_hidden, "is_image_only": is_image_only,
        "html_to_text_ratio": ratio,
    }


# --------------------------------------------------------------------------
# 5. Attachment
# --------------------------------------------------------------------------

def extract_attachment_features(msg):
    count = executable = macro = archive = double_ext = 0
    for part in msg.walk():
        filename = part.get_filename()
        if part.get_content_disposition() == 'attachment' or filename:
            count += 1
            if filename:
                name = filename.lower()
                is_executable = any(name.endswith(ext) for ext in EXECUTABLE_EXTENSIONS)
                executable |= int(is_executable)
                macro |= int(any(name.endswith(ext) for ext in MACRO_EXTENSIONS))
                archive |= int(any(name.endswith(ext) for ext in ARCHIVE_EXTENSIONS))
                double_ext |= int(is_executable and len(re.findall(r'\.[a-z0-9]+', name)) >= 2)
    return {'num_attachments': count, 'has_executable_attachment': executable,
            'has_macro_attachment': macro, 'has_archive_attachment': archive,
            'has_double_extension_attachment': double_ext}


# --------------------------------------------------------------------------
# 6. Social-engineering
# --------------------------------------------------------------------------

def extract_social_engineering_features(lowered_text):
    def _count(keywords):
        pattern = r"(?<!\w)(?:" + "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True)) + r")(?!\w)"
        return len(re.findall(pattern, lowered_text, re.I))
    return {
        "urgency_keyword_count": _count(URGENCY_KEYWORDS),
        "sensitive_info_keyword_count": _count(SENSITIVE_INFO_KEYWORDS),
        "brand_keyword_count": _count(BRAND_KEYWORDS),
        "generic_greeting": int(_count(GENERIC_GREETINGS) > 0),
        "reward_scam_keyword_count": _count(REWARD_KEYWORDS),
    }


# --------------------------------------------------------------------------
# HÀM TỔNG — dùng trong train.py / model_deployment.py
# --------------------------------------------------------------------------

FEATURE_NAMES = [
    "char_length", "word_count", "uppercase_word_ratio", "exclamation_count",
    "exclamation_in_subject", "money_symbol_count", "digit_ratio",
    "num_urls", "num_unique_domains", "num_ip_urls", "num_shortened_urls",
    "num_at_symbol_urls", "num_https_urls", "num_http_urls",
    "num_suspicious_tld_urls", "avg_url_length", "max_url_length",
    "num_anchor_href_mismatch",
    "from_domain_is_freemail", "reply_to_differs_from_sender",
    "display_name_brand_freemail_mismatch", "num_recipients",
    # "num_received_hops" và "has_date_header" ĐÃ LOẠI KHỎI feature set:
    # phân tích feature importance (analyze_feature_importance.py) trên
    # dataset Enron+Nazario+SpamAssassin cho thấy num_received_hops chiếm
    # tới 97-98% importance ở 3/5 model dạng cây -- gần như chắc chắn là
    # shortcut phân biệt "email nội bộ Enron" (hạ tầng mail-relay cố định,
    # 1 công ty, 1 giai đoạn 2000-2002) vs "email được archive lại nhiều
    # năm từ nhiều nguồn khác nhau" (Nazario/SpamAssassin), KHÔNG phải tín
    # hiệu phishing thật. has_date_header cũng nghi vấn tương tự (top 4/5
    # model) vì lý do gần giống: độ đầy đủ của header phụ thuộc cách thu
    # thập/archive dữ liệu, không phải bản chất email.
    "subject_is_reply_or_fwd",
    "from_display_name_length",
    "is_html", "has_form_tag", "has_script_tag", "has_hidden_elements",
    "is_image_only", "html_to_text_ratio",
    "num_attachments", "has_executable_attachment", "has_macro_attachment",
    "has_archive_attachment", "has_double_extension_attachment",
    "urgency_keyword_count", "sensitive_info_keyword_count",
    "brand_keyword_count", "generic_greeting", "reward_scam_keyword_count",
]

# Track extraction failures; errors are raised rather than converted to zero vectors.
_extraction_stats = {"total": 0, "failed": 0}


def get_extraction_stats():
    return dict(_extraction_stats)


def reset_extraction_stats():
    _extraction_stats["total"] = 0
    _extraction_stats["failed"] = 0


def extract_engineered_features(raw_text):
    """Extract all 40 features from the complete MIME-decoded message."""
    _extraction_stats["total"] += 1
    try:
        msg = _parse_email(raw_text)
        plain, markup = _get_email_body(msg)
        content, lowered = extract_content_stats_features(plain, markup, str(msg.get("Subject", "")))
        merged = {}
        for d in (content, extract_url_features(plain, markup), extract_header_features(msg),
                  extract_html_features(markup), extract_attachment_features(msg),
                  extract_social_engineering_features(lowered)):
            merged.update(d)
        return [float(merged[name]) for name in FEATURE_NAMES]
    except Exception:
        _extraction_stats["failed"] += 1
        raise  # Do not silently train on a fabricated all-zero vector.


# --------------------------------------------------------------------------
# Khử trùng lặp / gần trùng (chống data leakage)
# --------------------------------------------------------------------------

def compute_dedup_key(raw_text):
    """Routing differences do not matter; HTML links and attachments do."""
    msg = _parse_email(raw_text)
    plain, markup = _get_email_body(msg)
    attachments = []
    for part in msg.walk():
        if part.get_content_disposition() == "attachment" or part.get_filename():
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = part.as_bytes()
            attachments.append((part.get_filename() or "", hashlib.sha256(payload).hexdigest()))
    content = {"subject": _normalize(str(msg.get("Subject", ""))), "plain": _normalize(plain),
               "html": markup.strip(), "attachments": sorted(attachments)}
    if not plain and not markup and not attachments:
        content["raw"] = raw_text.hex() if isinstance(raw_text, bytes) else str(raw_text)
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _parse_email(raw):
    if isinstance(raw, bytes):
        msg = email.message_from_bytes(raw, policy=policy.compat32)
    elif isinstance(raw, str):
        msg = email.message_from_string(raw, policy=policy.compat32)
    else:
        raise TypeError("Email must be str or bytes")
    # Decode display headers without invoking the strict AddressHeader parser.
    # MIME headers remain untouched so payload/charset decoding stays accurate.
    for name in ("Subject", "From", "To", "Cc", "Reply-To", "Date"):
        value = msg.get(name)
        if value is None:
            continue
        value = str(value)
        try:
            fragments = decode_header(value)
        except (ValueError, email.errors.HeaderParseError):
            fragments = [(value, None)]
        decoded = []
        for fragment, charset in fragments:
            if isinstance(fragment, bytes):
                for encoding in (charset, "utf-8", "windows-1252", "latin-1"):
                    if not encoding:
                        continue
                    try:
                        fragment = fragment.decode(encoding)
                        break
                    except (LookupError, UnicodeError):
                        pass
                if isinstance(fragment, bytes):
                    fragment = fragment.decode("utf-8", errors="replace")
            decoded.append(fragment)
        msg.replace_header(name, "".join(decoded))
    return msg


def _normalize(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().lower()


@lru_cache(maxsize=1)
def _english_stopwords():
    try:
        words = set(stopwords.words("english"))
    except LookupError:
        from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
        words = set(ENGLISH_STOP_WORDS)
    return words - {"no", "not", "nor", "never"}


def deduplicate_emails(data):
    data = data.dropna(subset=["Text", "Class"]).copy()
    if not data.Class.isin([0, 1]).all():
        raise ValueError("Dataset contains labels other than 0/1")
    data["Class"] = data.Class.astype(int)
    data["_dedup_key"] = data.Text.apply(compute_dedup_key)
    conflicts = data.groupby("_dedup_key").Class.nunique()
    mask = data._dedup_key.isin(set(conflicts[conflicts > 1].index))
    if mask.any():
        data.loc[mask, ["Class", "_dedup_key"]].to_csv("label_conflicts.csv", index_label="loaded_row")
        print(f"Excluded {int(mask.sum())} conflicting-label rows; see label_conflicts.csv")
    data = data.loc[~mask]
    before = len(data)
    data = data.drop_duplicates("_dedup_key").reset_index(drop=True)
    print(f"Removed {before - len(data)} exact duplicates; {len(data)} emails remain")
    return data


def _simhash(text):
    text = re.sub(r"\d+", "0", URL_REGEX.sub(" URL ", text))
    words = re.findall(r"\w+", text)
    if len(words) < 20:
        return None
    votes = [0] * 64
    for shingle in {" ".join(words[i:i + 3]) for i in range(len(words) - 2)}:
        value = int.from_bytes(hashlib.blake2b(shingle.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            votes[bit] += 1 if value & (1 << bit) else -1
    return sum(1 << bit for bit, vote in enumerate(votes) if vote >= 0)


def group_email_variants(data):
    """Keep near duplicates, but put a whole SimHash group in one split.

    Hamming distance <=3 is a heuristic, not semantic equivalence. Four
    16-bit bands discover all candidate pairs within that distance.
    """
    parent = list(range(len(data)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a, b):
        a, b = root(a), root(b)
        if a != b:
            parent[max(a, b)] = min(a, b)
    bodies, hashes, bands = {}, {}, defaultdict(set)
    for i, (raw, exact) in enumerate(zip(data.Text, data._dedup_key)):
        msg = _parse_email(raw)
        plain, markup = _get_email_body(msg)
        body = _normalize("\n".join(dict.fromkeys(p for p in (plain, _strip_html(markup)) if p.strip())))
        body_key = hashlib.sha256((body or exact).encode()).hexdigest()
        if body_key in bodies:
            union(i, bodies[body_key])
            continue
        bodies[body_key] = i
        fingerprint = _simhash(body)
        if fingerprint is None:
            continue
        if fingerprint in hashes:
            union(i, hashes[fingerprint])
            continue
        keys = [(band, (fingerprint >> (16 * band)) & 65535) for band in range(4)]
        candidates = set()
        for key in keys:
            candidates.update(bands[key])
        for other in candidates:
            if bin(fingerprint ^ other).count("1") <= 3:
                union(i, hashes[other])
        hashes[fingerprint] = i
        for key in keys:
            bands[key].add(fingerprint)
        if (i + 1) % 5000 == 0:
            print(f"Grouped {i + 1}/{len(data)} emails", flush=True)
    return [root(i) for i in range(len(data))]


def split_email_data(data, test_size=0.3, seed=42):
    """Choose a group-disjoint split using only class counts, not model scores."""
    from sklearn.model_selection import GroupShuffleSplit
    if data.Class.nunique() != 2 or data._group.nunique() < 2:
        raise ValueError("Need two classes and independent email groups for train/test")
    splitter = GroupShuffleSplit(n_splits=32, test_size=test_size, random_state=seed)
    best = None
    for train_idx, test_idx in splitter.split(data, data.Class, data._group):
        train, test = data.iloc[train_idx], data.iloc[test_idx]
        if train.Class.nunique() != 2 or test.Class.nunique() != 2:
            continue
        score = abs(len(test) / len(data) - test_size) + abs(test.Class.mean() - data.Class.mean())
        if best is None or score < best[0]:
            best = score, train, test
    if best is None:
        raise ValueError("Cannot put both classes in independent train/test groups; more distinct emails are needed")
    _, train, test = best
    assert set(train._group).isdisjoint(test._group)
    return train.copy(), test.copy()
