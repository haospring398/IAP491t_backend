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
#   - extract_message_security_features (header/MIME spoofing: multiple From,
#     From injection, envelope Mail From, XSS trong header, CMS/MIME wrapping)
#   - extract_url_lexical_features    (feature của từng URL, dùng chung cho
#     corpus URL có nhãn như StealthPhisher2025 và URL trích từ email)
#   - extract_engineered_features(raw_text) -> list[float]  (hàm tổng, dùng
#     trong train.py, PHẢI được gọi trên text GỐC, trước khi cleanText() xoá
#     mất URL/HTML/header)

from bs4 import BeautifulSoup
import os
import re
import hashlib
import json
import unicodedata
import html as html_module
from email import policy
from email.header import decode_header
from functools import lru_cache
from collections import defaultdict

import email
from email.utils import parseaddr, getaddresses
from urllib.parse import urlparse


# --------------------------------------------------------------------------
# Các hàm GỐC của repo (không đổi logic, giữ tương thích unit-test.py)
# --------------------------------------------------------------------------

def cleanText(text):
    """Use decoded MIME body and subject, preserving Unicode and word boundaries."""
    text = _deobfuscated_message_text(_parse_email(text))[0]
    text = URL_REGEX.sub(" urltoken ", text)
    text = expand_negations(text)
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def expand_negations(text):
    text = text.replace('\u2019', "'")
    text = re.sub(r"\bwon't\b", 'will not', text, flags=re.I)
    text = re.sub(r"\bcan't\b", 'can not', text, flags=re.I)
    return re.sub(r"\b(\w+)n't\b", r'\1 not', text, flags=re.I)


def spelling_correction(text):
    # Unused by the pipeline. TextBlob pulls in nltk, which was removed for an unfixed CVE
    # (2026-10-26); install textblob separately to call this.
    from textblob import TextBlob
    return TextBlob(text).correct()


def remove_stopwords(text):
    return ' '.join(w for w in tokenize_text(text) if w not in _english_stopwords())


def tokenize_text(text):
    return [w.lower() for w in re.findall(r"\b\w+\b", str(text)) if len(w) >= 2]


# Tham số suy luận Doc2Vec dùng chung cho train.py và web demo: hai bên phải
# gọi cùng một hàm để vector lúc phục vụ trùng với vector lúc huấn luyện.
DOC2VEC_INFER_ALPHA = 0.025
DOC2VEC_INFER_MIN_ALPHA = 0.0005


def infer_document_vector(model, text, epochs):
    """Suy luận vector cho văn bản đã làm sạch; seed theo nội dung để lặp lại được."""
    words = tokenize_text(text) or ["emptyemailtoken"]
    seed = int.from_bytes(hashlib.sha256(" ".join(words).encode()).digest()[:4], "big")
    model.random.seed(seed)
    return model.infer_vector(words, alpha=DOC2VEC_INFER_ALPHA,
                              min_alpha=DOC2VEC_INFER_MIN_ALPHA, epochs=epochs)


# --------------------------------------------------------------------------
# Danh sách từ khoá / domain tham chiếu cho các nhóm kỹ thuật bổ sung
# --------------------------------------------------------------------------

URL_REGEX = re.compile(r'(https?://[^\s"\'<>\)\]]+|www\.[^\s"\'<>\)\]]+)', re.IGNORECASE)

# EPVME generator placeholders (https://github.com/sunknighteric/EPVME-Dataset).
# They name the attack class, so text models would learn the label from the
# subject instead of the payload. Real email with these exact subjects is rare.
SYNTHETIC_TEMPLATE_SUBJECTS = {"mime attack sample", "cms attack sample", "test xss", "xss test mail"}
# Payloads that break the header block push "Subject: MIME Attack Sample" into the body.
_TEMPLATE_PHRASES = re.compile(r"\b(?:mime attack sample|cms attack sample|xss test mail|test xss)\b", re.I)


def _content_subject(msg):
    subject = str(msg.get("Subject", ""))
    return "" if _normalize(subject) in SYNTHETIC_TEMPLATE_SUBJECTS else subject


# Corpus anonymisation placeholder: Phishing Pot replaces every honeypot address with
# "phishing@pot" (92% of its emails, in greetings, subjects and URLs). Left in, text
# models learn the literal word "phishing" as the label. Headers and link features keep
# it: a recipient address inside a URL is a genuine kit signal. No word boundaries: the
# maintainer's sed often glued it to neighbours ("phishing@potSie", "&#phishing@pot6;").
# The second alternative is the neutral recipient that _normalize_redactions() writes
# for malware-traffic-analysis.net placeholders.
_REDACTION_PLACEHOLDERS = re.compile(r"phishing\s*(?:@|%40|&#0*64;|&commat;|\[at\]|\(at\))\s*pot|"
                                     r"(?:(?:recipient|sender)(?:@|%40))?(?:mail\.)?(?:recipient|sender)-domain\.example",
                                     re.I)

# malware-traffic-analysis.net redacts malspam by hand: "[recipient's email address]",
# "[recipient's email domain]", "[removed]"... (95% of its emails). Recipient addresses
# become one neutral address under the reserved .example TLD, so To and personalised
# URLs (?n=[recipient's email address]) still look like an address to header and link
# features; names and other redactions are dropped ("Customer" would fake a generic
# greeting). The text pipeline then masks the neutral address like phishing@pot.
# "recip" also covers the author's typos ("[recipeint's email domain]"); spoofed senders
# ("[spoofed sender email address]") get their own neutral address so From-based header
# features still see one. Anything "...removed..." or naming a person is dropped.
_RECIPIENT_PLACEHOLDER = re.compile(rb"\[[^\]\r\n]{0,40}recip[^\]\r\n]{0,60}\]", re.I)
_SENDER_PLACEHOLDER = re.compile(rb"\[[^\]\r\n]{0,30}sender[^\]\r\n]{0,40}\]", re.I)
_AUTHOR_REDACTION = re.compile(rb"\[(?:[^\]\r\n]{0,40}\bremoved\b[^\]\r\n]{0,20}|redacted|reacted|attachment omitted|"
                               rb"malicious attachment redacted|base64 string|random name|unknown|fname lname|"
                               rb"string of alphabetic characters)\]", re.I)


def _neutral_party(party):
    def replace(match):
        placeholder = match.group(0).lower()
        if b"name" in placeholder:
            return b""
        if b"domain" in placeholder:
            return party + b"-domain.example"
        if b"server" in placeholder:
            return b"mail." + party + b"-domain.example"
        return party + b"@" + party + b"-domain.example"
    return replace


def _normalize_redactions(raw):
    if b"[" not in raw:
        return raw
    raw = _RECIPIENT_PLACEHOLDER.sub(_neutral_party(b"recipient"), raw)
    return _AUTHOR_REDACTION.sub(b"", _SENDER_PLACEHOLDER.sub(_neutral_party(b"sender"), raw))


# Same author redactions after MIME decoding: inside base64/quoted-printable bodies and
# encoded-word subjects the raw-byte pass in _normalize_redactions() cannot see them.
_DECODED_REDACTION = re.compile(r"\[[^\]\n]{0,60}(?:recip|sender|removed|redacted|spoofed)[^\]\n]{0,60}\]", re.I)


def _without_corpus_artifacts(text):
    text = _DECODED_REDACTION.sub(" ", _TEMPLATE_PHRASES.sub(" ", text))
    return _REDACTION_PLACEHOLDERS.sub(" ", text)


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
    if hasattr(msg, '_pipeline_body'):
        return msg._pipeline_body
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
    msg._pipeline_body = ("\n".join(plain), "\n".join(markup))
    return msg._pipeline_body


@lru_cache(maxsize=64)
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


def _find_urls(plain_text, html_text):
    combined = f"{plain_text}\n{_strip_html(html_text)}\n{html_text}"
    return sorted(set(unwrap_gateway_url(u.rstrip('.,);')) for u in URL_REGEX.findall(combined)))


# Link rewriting added by the RECIPIENT's mail gateway, not by the sender: Outlook Safe
# Links, Proofpoint URL Defense, Barracuda LinkProtect, Trend Micro Click-Time. It says
# nothing about the email (only which company received it) and hides the real target, so
# the original URL is restored before any URL feature. Sender-side redirects
# (google.com/url, l.facebook.com) are kept: they are the open-redirect abuse
# link_open_redirect_count measures. Opaque rewrites (Mimecast) cannot be decoded.
_GATEWAY_REWRITES = (
    (re.compile(r"(?:^|\.)safelinks\.protection\.(?:outlook\.com|office365\.us)$"), "", "url"),
    (re.compile(r"^linkprotect\.cudasvc\.com$"), "", "a"),
    (re.compile(r"(?:^|\.)trendmicro\.com$"), "/clicktime/", "url"),
    (re.compile(r"^urldefense\.proofpoint\.com$"), "/v1/", "u"),
)
_PROOFPOINT_V2 = re.compile(r"^https?://urldefense\.proofpoint\.com/v2/url\?", re.I)
_PROOFPOINT_V3 = re.compile(r"^https?://urldefense(?:\.proofpoint)?\.com/v3/__(.+?)__;", re.I)


def unwrap_gateway_url(url):
    """Original target of a URL rewritten by a recipient-side security gateway (nested too)."""
    from urllib.parse import parse_qs, unquote
    for _ in range(3):
        v3 = _PROOFPOINT_V3.match(url)
        if v3:
            url = v3.group(1)
            continue
        parsed = _safe_urlparse(url)
        query = parse_qs(html_module.unescape(parsed.query))
        if _PROOFPOINT_V2.match(url) and query.get("u"):
            url = unquote(query["u"][0].translate(str.maketrans("-_", "%/")))
            continue
        host = (parsed.hostname or "").lower()
        target = next((query[key][0] for pattern, path, key in _GATEWAY_REWRITES
                       if pattern.search(host) and path in parsed.path and query.get(key)), None)
        if not target or not re.match(r"(?:https?:)?//|www\.", target, re.I):
            break
        url = target
    return url.strip()


def extract_url_features(plain_text, html_text):
    urls = _find_urls(plain_text, html_text)
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
            href, anchor_html = unwrap_gateway_url(html_module.unescape(m.group(1))), m.group(2)
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


# Per-URL lexical features, computed from the URL string only so that labelled
# URL corpora (StealthPhisher2025) and URLs found in email share one definition.
# Page-content columns of URL corpora need a live fetch and are not reproduced.
# The scheme is deliberately excluded: in StealthPhisher2025 every legitimate
# URL is https, so the model would learn the corpus rather than phishing.
URL_LEXICAL_FEATURE_NAMES = [
    "url_length", "url_host_length", "url_path_length", "url_query_length",
    "url_path_depth", "url_query_param_count", "url_subdomain_count", "url_host_is_ip",
    "url_has_port", "url_has_at_symbol", "url_has_double_slash_path", "url_has_punycode",
    "url_host_hyphen_count", "url_host_digit_count", "url_digit_ratio", "url_letter_ratio",
    "url_special_char_count", "url_percent_encoding_count", "url_host_entropy", "url_entropy",
    "url_suspicious_tld", "url_is_shortener", "url_executable_extension", "url_sensitive_word_count",
]
# Every legitimate StealthPhisher2025 URL is a bare homepage (path, query and
# digits are all empty), so path/query features separate the corpus perfectly
# and would flag any email link with a path. Train on that corpus with these
# host-only features; use the full list only with URL data that has real paths.
URL_HOST_FEATURE_NAMES = [
    "url_host_length", "url_subdomain_count", "url_host_is_ip", "url_has_port",
    "url_has_punycode", "url_host_hyphen_count", "url_host_digit_count",
    "url_host_entropy", "url_suspicious_tld", "url_is_shortener",
]
URL_SENSITIVE_WORDS = ("login", "signin", "logon", "verify", "account", "update", "secure",
                       "banking", "confirm", "password", "wallet", "webscr", "unlock", "recover")
_SECOND_LEVEL_LABELS = {"co", "com", "net", "org", "gov", "edu", "ac"}


def normalize_url(url):
    url = str(url).strip().strip("'\"<>").rstrip(".,);")
    return url if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I) else "http://" + url


@lru_cache(maxsize=1)
def _public_suffix_list():
    import tldextract
    # Snapshot bundled with the pinned tldextract version: no network fetch, so the
    # result is reproducible. Private suffixes make user.github.io its own site.
    return tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)


@lru_cache(maxsize=131072)
def _psl_parts(host):
    return _public_suffix_list()(host)


def registrable_domain(host):
    """eTLD+1 by the Public Suffix List; IP hosts are kept whole.

    Hosts without a known suffix (intranet names such as Enron's) keep the last two labels.
    """
    host = str(host).lower().strip(".")
    if re.fullmatch(r"[\d.]+|\[?[0-9a-f:]+\]?", host):
        return host
    found = _psl_parts(host).top_domain_under_public_suffix
    if found:
        return found
    labels = [label for label in host.split(".") if label]
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL_LABELS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def url_group_key(url):
    """Split URL corpora by registrable domain so one site never spans train/test."""
    host = (_safe_urlparse(normalize_url(url)).hostname or "").lower()
    return registrable_domain(host) or str(url).lower()


def _entropy(text):
    import math
    if not text:
        return 0.0
    counts = defaultdict(int)
    for char in text:
        counts[char] += 1
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def extract_url_lexical_features(url):
    url = normalize_url(url)
    parsed = _safe_urlparse(url)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    body = url.split("://", 1)[-1]
    path = parsed.path or ""
    is_ip = bool(re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}", host)) or ":" in host
    labels = [label for label in host.split(".") if label]
    registered = registrable_domain(host)
    lowered = body.lower()
    extension = re.search(r"\.([a-z0-9]{1,5})$", path.lower())
    values = {
        "url_length": len(body), "url_host_length": len(host),
        "url_path_length": len(path), "url_query_length": len(parsed.query),
        "url_path_depth": len([p for p in path.split("/") if p]),
        "url_query_param_count": len([q for q in re.split(r"[&;]", parsed.query) if q]),
        "url_subdomain_count": 0 if is_ip else max(0, len(labels) - len(registered.split("."))),
        "url_host_is_ip": int(is_ip), "url_has_port": int(port is not None),
        "url_has_at_symbol": int("@" in body), "url_has_double_slash_path": int("//" in path),
        "url_has_punycode": int("xn--" in host),
        "url_host_hyphen_count": host.count("-"),
        "url_host_digit_count": sum(c.isdigit() for c in host),
        "url_digit_ratio": sum(c.isdigit() for c in body) / max(len(body), 1),
        "url_letter_ratio": sum(c.isalpha() for c in body) / max(len(body), 1),
        "url_special_char_count": len(re.findall(r"[^A-Za-z0-9./:]", body)),
        "url_percent_encoding_count": len(re.findall(r"%[0-9A-Fa-f]{2}", body)),
        "url_host_entropy": _entropy(host), "url_entropy": _entropy(body),
        "url_suspicious_tld": int(any(host.endswith(tld) for tld in SUSPICIOUS_TLDS)),
        "url_is_shortener": int(host in SHORTENER_DOMAINS),
        "url_executable_extension": int(bool(extension) and "." + extension.group(1) in EXECUTABLE_EXTENSIONS),
        "url_sensitive_word_count": sum(lowered.count(w) for w in URL_SENSITIVE_WORDS),
    }
    return [float(values[name]) for name in URL_LEXICAL_FEATURE_NAMES]


def extract_email_urls(raw_text, include_qr=False):
    """URLs as extract_url_features sees them, for scoring with a URL-level model.

    include_qr adds URLs decoded from QR codes, which link-based features never see.
    """
    msg = _parse_email(raw_text)
    plain, markup = _get_email_body(msg)
    urls = _find_urls(plain, markup)
    if include_qr:
        urls += sorted({c["payload"].strip() for c in inspect_email_qr_codes(msg)["codes"]
                        if c["kind"] == "url"} - set(urls))
    return urls


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


# Header/MIME syntax abused by sender spoofing and signature wrapping (the attack
# families of EPVME). Measured statically on the raw header values before
# decoding; RFC-invalid syntax is evidence, not a verdict. Return-Path/envelope
# features stay 0 when an archive did not keep them (Enron maildir, mbox splits).
MESSAGE_SECURITY_FEATURE_NAMES = [
    "hdr_from_header_count", "hdr_from_address_count", "hdr_from_encoded_address",
    "hdr_invalid_encoded_charset", "hdr_from_control_chars", "hdr_markup_in_headers",
    "hdr_envelope_syntax_anomaly", "hdr_null_return_path", "hdr_return_path_domain_mismatch",
    "hdr_sender_domain_mismatch", "hdr_from_subdomain_depth",
    "mime_signature_count", "mime_unsigned_text_outside_signature", "mime_max_blank_line_run",
    "mime_max_signature_b64_length",
    # Handbook Ch. 7.3 mismatch triangle and lookalike sender domains.
    "hdr_reply_to_freemail_divergence", "hdr_display_name_other_address",
    "hdr_display_name_brand_mismatch", "hdr_sender_brand_lookalike", "hdr_sender_brand_combosquat",
    # Sender domain imitates a recipient's domain (lookalike of the victim's own company).
    "hdr_sender_recipient_lookalike",
]
# A cid: reference count was measured and dropped: it fired in 15-26% of every
# EPVME family but ~0% of legitimate mail, because EPVME bodies come from
# Nazario HTML. It identified the body source, not the attack.
_RAW_HEADER_NAMES = ("From", "To", "Subject", "Sender", "Return-Path")
_ENCODED_WORD = re.compile(r"=\?([^?\s]+)\?[bBqQ]\?[^?\s]*\?=")
_HEADER_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩﻿￿]")
_HEADER_MARKUP = re.compile(r"<\s*/?\s*(script|img|svg|iframe|a|body|style|object|embed)\b|\bon[a-z]+\s*=|javascript\s*:", re.I)
_SIGNATURE_TYPES = {"application/pkcs7-signature", "application/x-pkcs7-signature",
                    "application/pgp-signature", "application/pkcs7-mime", "application/x-pkcs7-mime"}


def _address_domain(address):
    address = str(address).strip().strip("<>")
    return address.rsplit("@", 1)[-1].lower().strip(".>") if "@" in address else ""


def _envelope_sender(msg):
    unixfrom = msg.get_unixfrom() or ""
    parts = unixfrom[5:].split() if unixfrom.startswith("From ") else []
    return parts[0] if parts else ""


def extract_message_security_features(msg):
    import codecs
    if hasattr(msg, "_pipeline_security"):
        return msg._pipeline_security
    raw = getattr(msg, "_pipeline_raw_headers", None) or {
        name: [str(v) for v in (msg.get_all(name) or [])] for name in _RAW_HEADER_NAMES}
    froms = raw.get("From", [])
    decoded_froms = [_decode_header_value(v) for v in froms]
    addresses = [a for _, a in getaddresses(decoded_froms) if "@" in a]
    from_domain = _address_domain(addresses[0]) if addresses else ""

    def invalid_charset(value):
        for charset in _ENCODED_WORD.findall(value):
            try:
                codecs.lookup(charset.split("*")[0])
            except LookupError:
                return True
        return False

    shown = [v for name in ("From", "To", "Subject") for v in raw.get(name, [])]
    envelope = _envelope_sender(msg)
    return_path = (raw.get("Return-Path") or [""])[0].strip()
    bounce = envelope if envelope and envelope not in ("<>", "MAILER-DAEMON") else return_path
    bounce_domain = _address_domain(bounce)
    sender_domain = _address_domain(parseaddr(_decode_header_value((raw.get("Sender") or [""])[0]))[1])
    labels = [label for label in from_domain.split(".") if label]

    signatures, outside, blank_run, signature_length = 0, 0, 0, 0
    def visit(part, signed):
        nonlocal signatures, outside, blank_run, signature_length
        ctype = part.get_content_type()
        if part.is_multipart():
            for child in part.get_payload():
                visit(child, signed or ctype == "multipart/signed")
            return
        if ctype in _SIGNATURE_TYPES:
            signatures += 1
            payload = part.get_payload()
            if isinstance(payload, str):
                signature_length = max(signature_length, len(re.sub(r"\s+", "", payload)))
        elif part.get_content_maintype() == "text":
            outside += not signed
            run = longest = 0
            for line in _safe_decode(part).splitlines():
                run = run + 1 if not line.strip() else 0
                longest = max(longest, run)
            blank_run = max(blank_run, longest)
    visit(msg, False)
    signed_present = any(p.get_content_type() == "multipart/signed" for p in msg.walk())
    display = parseaddr(decoded_froms[0])[0] if decoded_froms else ""
    shown_address = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", display)
    reply_domain = _address_domain(parseaddr(str(msg.get("Reply-To", "")))[1])
    sender_hosts = {d for d in (from_domain, bounce_domain, reply_domain) if d}
    impersonation = [brand_impersonation(d) for d in sender_hosts]
    display_brands = _brand_in_text(display)
    recipient_values = raw.get("To", []) + [str(v) for v in (msg.get_all("Cc") or [])]
    recipient_domains = {registrable_domain(_address_domain(a))
                         for _, a in getaddresses([_decode_header_value(v) for v in recipient_values]) if "@" in a}
    from_registered = registrable_domain(from_domain) if from_domain else ""
    values_identity = {
        "hdr_sender_recipient_lookalike": int(any(domains_look_alike(from_registered, d) for d in recipient_domains)),
        "hdr_reply_to_freemail_divergence": int(reply_domain in FREEMAIL_DOMAINS and bool(from_domain)
                                                and from_domain not in FREEMAIL_DOMAINS),
        "hdr_display_name_other_address": int(bool(shown_address) and bool(addresses) and
                                              shown_address.group(0).lower() != addresses[0].lower()),
        "hdr_display_name_brand_mismatch": int(bool(display_brands) and bool(from_domain) and
                                               not any(_is_official_for(b, from_domain) for b in display_brands)),
        "hdr_sender_brand_lookalike": int(any(v and v[1] == "lookalike" for v in impersonation)),
        "hdr_sender_brand_combosquat": int(any(v and v[1] == "combosquat" for v in impersonation)),
    }
    values = {
        **values_identity,
        "hdr_from_header_count": len(froms),
        "hdr_from_address_count": len(addresses),
        "hdr_from_encoded_address": int(any(
            _ENCODED_WORD.search(v) and "@" not in _ENCODED_WORD.sub("", v) and "@" in d
            for v, d in zip(froms, decoded_froms))),
        "hdr_invalid_encoded_charset": int(any(invalid_charset(v) for v in shown)),
        "hdr_from_control_chars": int(any(_HEADER_CONTROL.search(v) for v in froms + decoded_froms)),
        "hdr_markup_in_headers": int(any(_HEADER_MARKUP.search(v) for v in shown)),
        # RFC 5321 reverse-path: one mailbox, no comments, empty list items or source routes.
        "hdr_envelope_syntax_anomaly": int(bool(envelope) and bool(
            re.search(r"^<@|,|\(|\)|;", envelope) or envelope.count("<") != envelope.count(">")
            or envelope.count("@") > 1)),
        "hdr_null_return_path": int(envelope == "<>" or return_path == "<>"),
        "hdr_return_path_domain_mismatch": int(bool(bounce_domain and from_domain) and
            registrable_domain(bounce_domain) != registrable_domain(from_domain)),
        "hdr_sender_domain_mismatch": int(bool(sender_domain and from_domain) and
            registrable_domain(sender_domain) != registrable_domain(from_domain)),
        "hdr_from_subdomain_depth": max(0, len(labels) - len(registrable_domain(from_domain).split("."))) if labels else 0,
        "mime_signature_count": signatures,
        "mime_unsigned_text_outside_signature": outside if signed_present else 0,
        "mime_max_blank_line_run": blank_run,
        "mime_max_signature_b64_length": signature_length,
    }
    msg._pipeline_security = {name: float(values[name]) for name in MESSAGE_SECURITY_FEATURE_NAMES}
    return msg._pipeline_security


def _header_attack_identity(msg):
    """Header-only attack variants copy an existing body; keep them distinct from it."""
    f = extract_message_security_features(msg)
    if not (f["hdr_from_header_count"] > 1 or f["hdr_from_address_count"] > 1
            or f["hdr_from_encoded_address"] or f["hdr_invalid_encoded_charset"]
            or f["hdr_from_control_chars"] or f["hdr_markup_in_headers"]
            or f["hdr_envelope_syntax_anomaly"] or f["hdr_null_return_path"]):
        return None
    raw = getattr(msg, "_pipeline_raw_headers", None) or {
        name: [str(v) for v in (msg.get_all(name) or [])] for name in _RAW_HEADER_NAMES}
    return {"envelope": _envelope_sender(msg), **{name: raw.get(name, []) for name in _RAW_HEADER_NAMES}}


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


HTML_SECURITY_FEATURE_NAMES = [
    'html_script_count', 'html_script_chars', 'html_external_script_count',
    'html_event_handler_count', 'html_eval_count', 'html_decode_call_count',
    'html_javascript_url_count', 'html_data_uri_count', 'html_iframe_count',
    'html_hidden_iframe_count', 'html_password_input_count',
    'html_long_encoded_string_count', 'html_document_write_count',
]


def extract_html_security_features(markup):
    """Static measurements for supervised HTML classification; never execute JS."""
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script\s*>', markup, re.I | re.S)
    script_text = '\n'.join(scripts)
    iframes = re.findall(r'<iframe\b[^>]*>', markup, re.I | re.S)
    values = [len(scripts), len(script_text),
              len(re.findall(r'<script\b[^>]*\bsrc\s*=', markup, re.I)),
              len(re.findall(r'\bon[a-z]+\s*=', markup, re.I)),
              len(re.findall(r'\b(?:eval|Function)\s*\(', script_text)),
              len(re.findall(r'\b(?:atob|unescape|decodeURIComponent|fromCharCode)\s*\(', script_text)),
              len(re.findall(r'javascript\s*:', markup, re.I)),
              len(re.findall(r'data\s*:[^,]{0,100};base64,', markup, re.I)),
              len(iframes), sum(bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden|\bhidden\b|\b(?:width|height)\s*=\s*[\"\']?0', tag, re.I)) for tag in iframes),
              len(re.findall(r'<input\b[^>]*\btype\s*=\s*[\"\']?password\b', markup, re.I)),
              len(re.findall(r'[A-Za-z0-9+/]{160,}={0,2}', script_text)),
              len(re.findall(r'\bdocument\s*\.\s*write\s*\(', script_text))]
    return dict(zip(HTML_SECURITY_FEATURE_NAMES, values))


# Payloads inside the HTML body: URLs in tag attributes, payloads parked in hidden
# elements, obfuscated JavaScript and HTML injection. Static only: nothing is executed
# or fetched. Mail clients never run scripts, so legitimate mail has no reason to carry
# obfuscated JavaScript; JSON-LD (schema.org actions in order/flight emails) and other
# non-script <script type> blocks are left out of the JavaScript checks.
HTML_PAYLOAD_FEATURE_NAMES = [
    'html_url_dangerous_scheme_count', 'html_url_obfuscated_count', 'html_form_remote_action_count',
    'html_meta_refresh_count', 'html_base_href_count',
    'html_hidden_offsite_url_count', 'html_hidden_encoded_payload_count', 'html_hidden_script_count',
    'html_hidden_high_entropy_count',
    'html_js_escape_count', 'html_js_charcode_array_max', 'html_js_string_concat_count',
    'html_js_obfuscator_signature_count', 'html_js_max_string_entropy', 'html_js_redirect_count',
    'html_js_dom_injection_count', 'html_js_obfuscation_score', 'html_js_obfuscated',
    'html_injection_attr_markup_count', 'html_injection_url_payload_count', 'html_encoded_markup_count',
    'html_dangerous_tag_count', 'html_css_injection_count',
]
HTML_PAYLOAD_MAX_CHARS = 2_000_000
_URL_ATTRIBUTE = re.compile(r'''\s(href|src|action|formaction|data|background|poster|xlink:href|lowsrc|dynsrc|ping|srcset)'''
                            r'''\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))''', re.I)
_LINK_ATTRIBUTES = ('href', 'action', 'formaction')
_C0_AND_SPACE = ''.join(map(chr, range(33)))
_DANGEROUS_SCHEME = re.compile(r'^(?:javascript|vbscript|livescript|mocha|file|blob):|'
                               r'^data:(?!image/(?:png|jpe?g|gif|webp|bmp)[;,])', re.I)
_NUMERIC_HOST = re.compile(r'^(?:\d{8,10}|0x[0-9a-f]+|0\d+(?:\.\d+){0,3})$|(?:^|\.)0x[0-9a-f]+(?:\.|$)', re.I)
_JS_TYPES = {'', 'text/javascript', 'application/javascript', 'module', 'text/ecmascript',
             'application/ecmascript', 'text/jscript', 'text/vbscript', 'application/x-javascript'}
_EVENT_HANDLER = re.compile(r'''\son[a-z]+\s*=\s*(?:"([^"]*)"|'([^']*)')''', re.I)
_ENCODED_PAYLOAD = re.compile(r'[A-Za-z0-9+/]{100,}={0,2}|(?:[0-9a-fA-F]{2}){40,}|(?:%[0-9a-fA-F]{2}){10,}|'
                              r'(?:\\x[0-9a-fA-F]{2}){8,}|(?:\\u[0-9a-fA-F]{4}){6,}')
_SCRIPT_LIKE = re.compile(r'<\s*/?\s*(?:script|iframe|object|embed|svg|form)\b|(?:java|vb)script\s*:|\beval\s*\(|'
                          r'\bdocument\s*\.\s*(?:write|cookie|location)|\bwindow\s*\.\s*location|\batob\s*\(|'
                          r'fromCharCode|\bon(?:load|error|click|mouseover|focus)\s*=', re.I)
_JS_ESCAPE = re.compile(r'\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}|\\u\{[0-9a-fA-F]+\}|\\[0-3][0-7]{2}')
_JS_CHARCODE_ARRAY = re.compile(r'(?:\d{1,5}\s*,\s*){7,}\d{1,5}')
_JS_STRING_CONCAT = re.compile(r'''(["'])[^"'\\\n]{0,12}\1\s*\+\s*(?=["'])''')
# Literals without whitespace (base64/hex/packed data); HTML strings that document.write
# prints are long and varied too, but contain spaces.
_JS_STRING_LITERAL = re.compile(r'''(["'`])((?:(?!\1)[^\\\s]|\\.){64,})\1''')
_JS_OBFUSCATOR_SIGNATURES = (
    re.compile(r'eval\s*\(\s*function\s*\(\s*p\s*,\s*a\s*,\s*c\s*,\s*k\s*,\s*e\s*,\s*[dr]\s*\)'),  # Dean Edwards packer
    re.compile(r'[\[\]()!+]{40,}'),  # JSFuck
    re.compile('ﾟωﾟﾉ|ﾟДﾟ|ﾟΘﾟ'),  # aaencode
    re.compile(r'\$=~\[\];|\$\.\$\$\$\$'),  # jjencode
)
_JS_OBFUSCATOR_IDENTIFIER = re.compile(r'\b_0x[0-9a-f]{4,6}\b')  # obfuscator.io
_JS_DECODE = re.compile(r'\b(?:atob|unescape|decodeURI(?:Component)?|fromCharCode)\s*\(')
_JS_EXEC = re.compile(r'\b(?:eval|Function)\s*\(|\bdocument\s*\.\s*write(?:ln)?\s*\(|\.\s*(?:inner|outer)HTML\s*\+?=(?!=)|'
                      r'\bset(?:Timeout|Interval)\s*\(\s*["\'`]')
_JS_REDIRECT = re.compile(r'\b(?:(?:window|document|top|self|parent)\s*\.\s*)?location(?:\s*\.\s*href)?\s*=(?!=)|'
                          r'\blocation\s*\.\s*(?:replace|assign)\s*\(|\bwindow\s*\.\s*open\s*\(|\.\s*submit\s*\(\s*\)')
_JS_DOM_INJECTION = re.compile(r'\.\s*(?:inner|outer)HTML\s*\+?=(?!=)|\binsertAdjacentHTML\s*\(|'
                               r'\bdocument\s*\.\s*write(?:ln)?\s*\(|\bnew\s+Function\s*\(|'
                               r'\bset(?:Timeout|Interval)\s*\(\s*["\'`]|\bcreateContextualFragment\s*\(')
_INJECTION_PAYLOAD = re.compile(r'<\s*/?\s*(?:script|svg|img|iframe|body|object|embed|form|input|a)\b|'
                                r'\bon[a-z]+\s*=|(?:java|vb)script\s*:|["\']\s*/?>|\balert\s*\(|'
                                r'\bdocument\s*\.\s*(?:cookie|domain|write)|\beval\s*\(', re.I)
# Active markup only: sloppy legacy HTML leaves "8</td" or quote debris in attributes.
_ATTRIBUTE_MARKUP = re.compile(r'<\s*(?:script|iframe|svg|img|object|embed|form|body|meta|link|base|style)\b|'
                               r'(?:java|vb)script\s*:|\bon[a-z]+\s*=', re.I)
_ENCODED_MARKUP = re.compile(r'(?:&lt;|&#0*60;|&#x0*3c;|%3c|\\x3c|\\u003c)\s*/?\s*'
                             r'(?:script|iframe|object|embed|svg|form|meta|base)\b', re.I)
_DANGEROUS_TAGS = re.compile(r'<(?:object|embed|applet|frameset|frame|isindex|foreignobject)\b|'
                             r'<iframe\b[^>]*\bsrcdoc\s*=|<svg\b[^>]*\son[a-z]+\s*=|'
                             r'<link\b[^>]*\brel\s*=\s*["\']?import|'
                             r'<(?:animate|set)\b[^>]*\b(?:attributename\s*=\s*["\']?(?:xlink:)?href|to\s*=\s*["\']?javascript)', re.I)
_CSS_INJECTION = re.compile(r'expression\s*\(|behavior\s*:\s*url|-moz-binding|'
                            r'url\(\s*["\']?\s*(?:javascript|vbscript|data\s*:\s*text/html)', re.I)


def _html_url_values(markup):
    """(attribute, raw value) of every URL-bearing attribute; srcset yields one per candidate."""
    for match in _URL_ATTRIBUTE.finditer(markup):
        name = match.group(1).lower()
        raw = next(v for v in match.groups()[1:] if v is not None)
        if name == 'srcset':
            for candidate in raw.split(','):
                if candidate.strip():
                    yield name, candidate.strip().split()[0]
        else:
            yield name, raw


def _decoded_url(raw):
    """The URL a browser follows: entities decoded, tab/CR/LF removed, C0 and space trimmed."""
    return re.sub(r'[\t\r\n]', '', html_module.unescape(raw)).strip(_C0_AND_SPACE)


def _url_is_obfuscated(raw, url):
    """Scheme spelled with entities/control characters, backslashes, userinfo, encoded or numeric host.

    Entity-encoded mailto:/tel: links are address munging against harvesters (SpamAssassin
    ham: 130 links in newsletters), not obfuscation of a destination, and are not counted.
    """
    scheme = re.match(r'([a-z][a-z0-9+.-]*):', url, re.I)
    if scheme and scheme.group(1).lower() in ('mailto', 'tel'):
        return False
    if scheme and not raw.strip().lower().startswith(scheme.group(1).lower() + ':'):
        return True
    prefix = re.match(r'(?:(?:https?|ftp):)?([\\/]{2,})', url, re.I)
    if not prefix:
        return False
    if '\\' in prefix.group(1):
        return True
    authority = re.split(r'[/?#\\]', url[prefix.end():], maxsplit=1)[0]
    host = authority.rsplit('@', 1)[-1].split(':')[0]
    return '@' in authority or '%' in host or bool(_NUMERIC_HOST.search(host))


def _url_domain(url):
    if not re.match(r'(?:https?:)?//|www\.', url, re.I):
        return ''
    host = (_safe_urlparse(normalize_url(url.lstrip('/') if url.startswith('//') else url)).hostname or '').lower()
    return registrable_domain(host) if host else ''


def _hidden_html_content(markup, soup):
    """Top-level hidden elements and the registrable domains linked from visible content.

    Hidden: hidden attribute, hiding inline style or <style> class/id, text in the background
    color, <input type=hidden>. Zero-size images are not counted: tracking pixels are routine.
    """
    from bs4.element import Comment, Declaration, Doctype, NavigableString, ProcessingInstruction, Tag
    hidden_classes, hidden_ids = _hidden_css_selectors(markup)
    roots, visible, hidden_links = [], set(), []
    stack = [(soup, False, None, None)]
    while stack:
        node, hidden, color, background = stack.pop()
        if isinstance(node, NavigableString):
            if not hidden and not isinstance(node, (Comment, Declaration, Doctype, ProcessingInstruction)):
                visible.update(_url_domain(u) for u in URL_REGEX.findall(str(node)))
            continue
        if not isinstance(node, Tag):
            continue
        name = (node.name or '').lower()
        if name in _NON_RENDERED_TAGS:
            continue
        style = node.get('style', '') or ''
        classes = {str(c).lower() for c in (node.get('class') or [])}
        color = (_css_color(style, 'color') or
                 (_normalize_color(node.get('color')) if name == 'font' else None) or color)
        background = (_css_color(style, 'background-color') or _css_color(style, 'background') or
                      _normalize_color(node.get('bgcolor')) or background)
        hides = (node.has_attr('hidden') or _style_hides(style) or bool(classes & hidden_classes)
                 or str(node.get('id', '')).lower() in hidden_ids
                 or (name == 'input' and str(node.get('type', '')).strip().lower() == 'hidden')
                 or bool(color and background and color == background))
        if hides and not hidden:
            roots.append(node)
        hidden = hidden or hides
        for attribute in _LINK_ATTRIBUTES + (() if hidden else ('src',)):
            value = node.get(attribute)
            if value:
                url = unwrap_gateway_url(str(value).strip())
                (hidden_links.append(url) if hidden else visible.add(_url_domain(url)))
        stack.extend((child, hidden, color, background) for child in node.contents)
    for root in roots:
        hidden_links.extend(URL_REGEX.findall(root.get_text(' ')))
    return roots, visible - {''}, hidden_links


def _hidden_payload_counts(roots):
    encoded = script = entropy = 0
    for root in roots:
        values = []
        for tag in [root, *root.find_all(True)]:
            for attribute, value in tag.attrs.items():
                if attribute.lower() not in ('href', 'src', 'srcset', 'action', 'formaction', 'style', 'class', 'id'):
                    values.append(' '.join(value) if isinstance(value, list) else str(value))
        blob = root.get_text(' ') + ' ' + ' '.join(values)
        encoded += len(_ENCODED_PAYLOAD.findall(blob))
        script += len(_SCRIPT_LIKE.findall(blob)) + len(root.find_all(['script', 'iframe', 'object', 'embed']))
        entropy += sum(_entropy(token) >= 4.5 for token in re.findall(r'\S{40,}', blob)
                       if not re.match(r'(?:https?:|www\.)', token, re.I))
    return encoded, script, entropy


def _javascript_sources(markup, urls):
    """<script> bodies of script types, event-handler attributes and javascript:/vbscript: URLs."""
    from urllib.parse import unquote
    sources = []
    for attributes, body in re.findall(r'<script\b([^>]*)>(.*?)</script\s*>', markup, re.I | re.S):
        kind = re.search(r'''\btype\s*=\s*["']?([^"'\s>]*)''', attributes, re.I)
        if (kind.group(1).lower() if kind else '') in _JS_TYPES:
            sources.append(body)
    for tag in re.findall(r'<[a-z][^>]*>', markup, re.I):
        sources.extend(html_module.unescape(a or b) for a, b in _EVENT_HANDLER.findall(tag))
    sources.extend(unquote(url.split(':', 1)[1]) for url in urls if re.match(r'(?:java|vb)script:', url, re.I))
    return '\n'.join(sources)


def extract_html_check_features(markup):
    """HTML_SECURITY_FEATURE_NAMES + HTML_PAYLOAD_FEATURE_NAMES, run only when the email has HTML parts.

    is_html is this gate, not a model input; an email without HTML gets zeros.
    """
    if not markup:
        return dict.fromkeys(HTML_SECURITY_FEATURE_NAMES + HTML_PAYLOAD_FEATURE_NAMES, 0.0)
    return {**extract_html_security_features(markup), **extract_html_payload_features(markup)}


def extract_html_payload_features(markup):
    """HTML_PAYLOAD_FEATURE_NAMES for an email's HTML parts; zeros without HTML."""
    from urllib.parse import unquote
    values = dict.fromkeys(HTML_PAYLOAD_FEATURE_NAMES, 0.0)
    if not markup or '<' not in markup:
        return values
    markup = markup[:HTML_PAYLOAD_MAX_CHARS]
    pairs = [(name, raw, _decoded_url(raw)) for name, raw in _html_url_values(markup)]
    urls = [url for _, _, url in pairs]
    for name, raw, url in pairs:
        values['html_url_dangerous_scheme_count'] += bool(_DANGEROUS_SCHEME.match(url))
        values['html_url_obfuscated_count'] += _url_is_obfuscated(raw, url)
        # Reflected injection: markup or script in the query/fragment of a link (decoded twice).
        decoded = unquote(unquote(url))
        query = decoded.partition('?')[2] or decoded.partition('#')[2]
        values['html_injection_url_payload_count'] += bool(query and _INJECTION_PAYLOAD.search(query))
    for form in re.findall(r'<(?:form|button|input)\b[^>]*>', markup, re.I):
        action = re.search(r'''\s(?:form)?action\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))''', form, re.I)
        target = _decoded_url(next(v for v in action.groups() if v is not None)) if action else ''
        values['html_form_remote_action_count'] += bool(re.match(r'(?:https?:)?//', target, re.I)
                                                       or _DANGEROUS_SCHEME.match(target))
    values['html_meta_refresh_count'] = len(re.findall(r'''<meta\b[^>]*http-equiv\s*=\s*["']?refresh''', markup, re.I))
    values['html_base_href_count'] = len(re.findall(r'<base\b[^>]*\shref\s*=', markup, re.I))
    try:
        soup = BeautifulSoup(markup, 'html.parser')
        roots, visible, hidden_links = _hidden_html_content(markup, soup)
        (values['html_hidden_encoded_payload_count'], values['html_hidden_script_count'],
         values['html_hidden_high_entropy_count']) = _hidden_payload_counts(roots)
        # A hidden link to a site the visible content never links to; hidden mobile/desktop
        # variants of a newsletter link to the same sites as its visible part.
        values['html_hidden_offsite_url_count'] = sum(
            bool(domain) and domain not in visible for domain in map(_url_domain, hidden_links))
        # Injected markup: an attribute value that holds active tags or script, as left when
        # a quote breaks out of the attribute.
        for tag in soup.find_all(True):
            for attribute, value in tag.attrs.items():
                value = ' '.join(value) if isinstance(value, list) else str(value)
                name = attribute.lower()
                values['html_injection_attr_markup_count'] += bool(
                    name not in _LINK_ATTRIBUTES + ('src', 'style') and not name.startswith('on')
                    and _ATTRIBUTE_MARKUP.search(value))
    except Exception:
        pass  # Unparseable markup keeps the regex measurements.
    js = _javascript_sources(markup, urls)
    if js:
        escapes = len(_JS_ESCAPE.findall(js))
        charcodes = max((m.group().count(',') + 1 for m in _JS_CHARCODE_ARRAY.finditer(js)), default=0)
        concat = sum(1 for _ in _JS_STRING_CONCAT.finditer(js))
        signatures = sum(bool(p.search(js)) for p in _JS_OBFUSCATOR_SIGNATURES) + (
            len(set(_JS_OBFUSCATOR_IDENTIFIER.findall(js))) >= 5)
        entropy = max((_entropy(m.group(2)) for m in _JS_STRING_LITERAL.finditer(js)), default=0.0)
        encoded_blob = entropy >= 5.2 or bool(re.search(r'[A-Za-z0-9+/]{160,}={0,2}', js))
        families = [escapes >= 20, charcodes >= 20, concat >= 8, signatures > 0, encoded_blob,
                    bool(_JS_DECODE.search(js) and _JS_EXEC.search(js))]
        values.update({'html_js_escape_count': escapes, 'html_js_charcode_array_max': charcodes,
                       'html_js_string_concat_count': concat, 'html_js_obfuscator_signature_count': signatures,
                       'html_js_max_string_entropy': entropy,
                       'html_js_redirect_count': len(_JS_REDIRECT.findall(js)),
                       'html_js_dom_injection_count': len(_JS_DOM_INJECTION.findall(js)),
                       'html_js_obfuscation_score': sum(families),
                       'html_js_obfuscated': int(signatures > 0 or sum(families) >= 2)})
    values['html_encoded_markup_count'] = len(_ENCODED_MARKUP.findall(markup))
    values['html_dangerous_tag_count'] = len(_DANGEROUS_TAGS.findall(markup))
    css = ' '.join(re.findall(r'<style\b[^>]*>(.*?)</style\s*>', markup, re.I | re.S) +
                   [a or b for a, b in re.findall(r'''\sstyle\s*=\s*(?:"([^"]*)"|'([^']*)')''', markup, re.I)])
    values['html_css_injection_count'] = len(_CSS_INJECTION.findall(css))
    return {name: float(value) for name, value in values.items()}


# --------------------------------------------------------------------------
# 5. Attachment
# --------------------------------------------------------------------------


# Static inspection only: never execute, extract to disk, or fetch embedded URLs.
# "No indicator" does NOT mean malware-free. Opaque/encrypted content is partial.
ATTACHMENT_MAX_BYTES = 8 * 1024 * 1024
ATTACHMENT_TOTAL_BYTES = 32 * 1024 * 1024
ATTACHMENT_MAX_MEMBERS = 200
ATTACHMENT_MAX_DEPTH = 2
ATTACHMENT_MAX_RATIO = 100
ATTACHMENT_MAX_PARTS = 100
ATTACHMENT_FEATURE_NAMES = [
    "attachment_suspicious_count", "attachment_incomplete_scan_count",
    "attachment_type_mismatch_count", "attachment_disguised_executable_count",
    "attachment_bidi_filename_count", "attachment_embedded_executable_count",
    "attachment_office_active_content_count", "attachment_office_external_target_count",
    "attachment_pdf_active_content_count", "attachment_script_content_count",
    "attachment_encrypted_archive_count", "attachment_archive_limit_count",
    "attachment_scan_error_count", "attachment_disguised_active_count",
]
_ACTIVE_EXTENSIONS = EXECUTABLE_EXTENSIONS | {
    ".dll", ".cpl", ".lnk", ".url", ".wsh", ".sct", ".chm", ".sh"}
_OFFICE_ZIP_EXTENSIONS = {
    ".docx", ".xlsx", ".pptx", ".dotx", ".xltx", ".ppsx"} | MACRO_EXTENSIONS
_BIDI_CHARS = set("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_MAX_SCAN_ITEMS = 512
# Magika labels of content that runs or renders active code when opened: markup that can
# carry script, scripts (VBScript is labelled "vba"), binaries, shortcuts, installers.
_ACTIVE_CONTENT_LABELS = {
    "html", "svg", "mht", "javascript", "vba", "powershell", "batch", "shell", "autoit", "autohotkey",
    "pebin", "elf", "macho", "lnk", "internetshortcut", "jar", "javabytecode", "msi", "chm", "apk", "dex", "swf"}
_SCRIPT_CONTENT_LABELS = {"html", "svg", "javascript", "vba", "powershell", "batch", "shell"}
# Names a user opens as a document, picture or media file. .txt/.csv are left out: code
# pasted into a text file is common and Magika is least certain on short plain text.
_PASSIVE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf", ".odt", ".ods", ".odp",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".ico",
    ".mp3", ".mp4", ".wav", ".avi", ".mov"}
_PASSIVE_MIME = re.compile(r"^(?:image|audio|video)/|^application/(?:pdf|msword|rtf|vnd\.ms-|vnd\.openxmlformats-|"
                           r"vnd\.oasis\.opendocument\.)")


@lru_cache(maxsize=1)
def _magika():
    from magika import Magika
    return Magika()


def attachment_content_type(data):
    """Magika content-type label ("pdf", "html", "javascript", ...).

    Google's deep-learning file-type classifier: it reads a few KB from the start, middle
    and end of the bytes and is strongest where magic bytes fail, i.e. text formats such as
    HTML, scripts and UTF-16 code. It names the type, never whether the file is malicious.
    """
    if not data:
        return "empty"
    result = _magika().identify_bytes(bytes(data))
    return str(result.prediction.output.label) if result.ok else "unknown"


def _attachment_magic(data):
    if len(data) >= 64 and data[:2] == b"MZ":
        offset = int.from_bytes(data[60:64], "little")
        if 0 <= offset <= len(data) - 4 and data[offset:offset + 4] == b"PE\0\0":
            return "pe"
    if data.startswith(b"\x7fELF"):
        return "elf"
    if data[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                    b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"):
        return "macho"
    if data.startswith(b"L\0\0\0\x01\x14\x02\0"):
        return "lnk"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "zip"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ole"
    if data.lstrip().startswith(b"{\\rtf"):
        return "rtf"
    if data.startswith((b"Rar!", b"7z\xbc\xaf\x27\x1c", b"\x1f\x8b")):
        return "opaque_archive"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if b"\0" not in data[:4096]:
        return "text"
    return "unknown"


def inspect_email_attachments(raw_or_message):
    """Return bounded static evidence for MIME attachments, including inline files.

    Every result states coverage. Flags indicate risk, never a confirmed malware
    verdict. PDF/legacy Office content may conceal compressed/obfuscated code.
    """
    import io
    import zipfile
    import zlib
    from pathlib import PurePosixPath
    from email.message import Message
    msg = raw_or_message if isinstance(raw_or_message, Message) else _parse_email(raw_or_message)
    reports = []
    budget = {"bytes": ATTACHMENT_TOTAL_BYTES, "members": ATTACHMENT_MAX_MEMBERS,
              "items": _MAX_SCAN_ITEMS}
    def inspect(data, name, mime, depth=0, parent=None):
        report = {"filename": name or "(unnamed)", "parent": parent,
                  "declared_type": mime, "detected_type": _attachment_magic(data),
                  "content_type": attachment_content_type(data),
                  "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "indicators": [], "limitations": []}
        reports.append(report)
        flags, limits = report["indicators"], report["limitations"]
        def flag(value):
            if value not in flags:
                flags.append(value)
        def limit(value):
            if value not in limits:
                limits.append(value)
        budget["items"] -= 1
        normalized = unicodedata.normalize("NFKC", name or "").rstrip(" .").lower()
        ext = PurePosixPath(normalized.replace("\\", "/")).suffix
        magic, content = report["detected_type"], report["content_type"]
        if any(c in (name or "") for c in _BIDI_CHARS):
            flag("bidi_filename")
        if ext in _ACTIVE_EXTENSIONS:
            flag("executable_extension")
            if len(re.findall(r"\.[a-z0-9]+", normalized)) > 1:
                flag("double_extension")
        if ext in MACRO_EXTENSIONS:
            flag("macro_enabled_extension")
        executable = magic in {"pe", "elf", "macho", "lnk"}
        if executable:
            flag("executable_content")
            if ext not in _ACTIVE_EXTENSIONS:
                flag("disguised_executable")
                flag("type_mismatch")
        expected = {".pdf": {"pdf"}, ".png": {"png"}, ".jpg": {"jpeg"},
                    ".jpeg": {"jpeg"}, ".gif": {"gif"}, ".zip": {"zip"},
                    ".rtf": {"rtf"}, ".doc": {"ole"}, ".xls": {"ole"},
                    ".ppt": {"ole"}}
        expected.update({suffix: {"zip"} for suffix in _OFFICE_ZIP_EXTENSIONS})
        if ext in expected and magic not in expected[ext]:
            flag("type_mismatch")
        mime_expected = {"application/pdf": "pdf", "image/png": "png",
                         "image/jpeg": "jpeg", "image/gif": "gif"}
        if mime in mime_expected and magic != mime_expected[mime]:
            flag("type_mismatch")
        # Named or declared as a document/picture, but the content is active (an HTML
        # credential page saved as invoice.pdf, a script sent as image/jpeg).
        passive = ext in _PASSIVE_EXTENSIONS or (not ext and bool(_PASSIVE_MIME.match(mime or "")))
        if passive and content in _ACTIVE_CONTENT_LABELS:
            flag("disguised_active_content")
            flag("type_mismatch")
        # Find structurally plausible embedded PE headers; an MZ string alone
        # would flag innocent text too often.
        offset = 0
        for _ in range(32):
            offset = data.find(b"MZ", offset + 1)
            if offset < 0:
                break
            if _attachment_magic(data[offset:offset + 65536]) == "pe":
                flag("embedded_executable")
                break
        if magic == "pdf":
            pdf = re.sub(rb"#([0-9a-fA-F]{2})",
                         lambda m: bytes([int(m[1], 16)]), data)
            if re.search(rb"/(?:JavaScript|JS|Launch|OpenAction|AA|EmbeddedFile|RichMedia)\b", pdf):
                flag("pdf_active_content")
            if re.search(rb"/Encrypt\b", pdf):
                flag("encrypted_document")
                limit("encrypted_document_not_decrypted")
            limit("pdf_compressed_streams_and_actions_not_fully_parsed")
        if magic == "ole":
            # Compressed VBA/XLM cannot be ruled out by strings alone.
            limit("legacy_office_requires_dedicated_macro_and_exploit_scanner")
            text = data.decode("latin-1", errors="replace") + data.decode("utf-16le", errors="ignore")
            if re.search(r"\b(?:AutoOpen|Document_Open|Workbook_Open|CreateObject|Shell)\b", text, re.I):
                flag("office_active_code_strings")
        if magic == "rtf":
            if re.search(rb"\\(?:object|objdata|objupdate)\b", data, re.I):
                flag("office_embedded_object")
            limit("rtf_embedded_objects_not_fully_parsed")
        if magic == "text" or content in _SCRIPT_CONTENT_LABELS or ext in {".html", ".htm", ".svg", ".js", ".vbs", ".ps1", ".hta"}:
            if re.search(rb"<\s*script\b|javascript\s*:|wscript[.]shell|powershell\s|"
                         rb"ActiveXObject\s*[(]|eval\s*[(]|<\s*form\b", data, re.I):
                flag("script_or_form_content")
        if magic == "zip":
            if depth >= ATTACHMENT_MAX_DEPTH:
                flag("archive_limit")
                limit("archive_depth_limit")
                return
            eocd = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
            if eocd >= 0 and len(data) >= eocd + 22:
                declared_members = int.from_bytes(data[eocd + 10:eocd + 12], "little")
                if declared_members > budget["members"]:
                    flag("archive_limit")
                    limit("archive_member_limit")
                    return
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    members = archive.infolist()
                    names = {item.filename.replace("\\", "/").lower() for item in members}
                    if ext in _OFFICE_ZIP_EXTENSIONS and "[content_types].xml" not in names:
                        flag("type_mismatch")
                    if any(n.endswith("vbaproject.bin") or "/macrosheets/" in n for n in names):
                        flag("office_macro")
                    if len(members) > budget["members"]:
                        flag("archive_limit")
                        limit("archive_member_limit")
                    for member in members[:budget["members"]]:
                        if member.is_dir():
                            continue
                        if budget["members"] <= 0 or budget["items"] <= 0:
                            flag("archive_limit")
                            limit("archive_member_limit")
                            break
                        budget["members"] -= 1
                        member_name = member.filename.replace("\\", "/")
                        if ".." in PurePosixPath(member_name).parts or member_name.startswith("/") or re.match(r"^[a-z]:", member_name, re.I):
                            flag("archive_path_traversal")
                        if member.flag_bits & 1:
                            flag("encrypted_archive")
                            limit("encrypted_member_not_inspected")
                            continue
                        if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                            limit("unsupported_archive_compression")
                            continue
                        size_limit = min(ATTACHMENT_MAX_BYTES, budget["bytes"])
                        if (member.file_size > size_limit or size_limit <= 0 or
                                member.file_size / max(member.compress_size, 1) > ATTACHMENT_MAX_RATIO):
                            flag("archive_limit")
                            limit("archive_size_or_ratio_limit")
                            continue
                        try:
                            with archive.open(member) as handle:
                                child = handle.read(size_limit + 1)
                            budget["bytes"] -= len(child)
                            if len(child) > size_limit:
                                flag("archive_limit")
                                limit("archive_actual_size_limit")
                                continue
                        except (RuntimeError, NotImplementedError, OSError, ValueError, EOFError, zlib.error, zipfile.BadZipFile):
                            flag("scan_error")
                            limit("archive_member_unreadable")
                            continue
                        lower = member_name.lower()
                        if lower.endswith(".xml") and re.search(rb"DDEAUTO|<(?:[a-zA-Z]+:)?ddeLink\b", child, re.I):
                            flag("office_dde_field")
                        if lower.endswith(".rels"):
                            # XML entity declarations are not expanded or followed.
                            rels = html_module.unescape(child.decode("utf-8", errors="replace"))
                            if re.search(r'TargetMode\s*=\s*["\']External["\']', rels, re.I) and re.search(
                                    r"attachedTemplate|oleObject|/package|externalLink", rels, re.I):
                                flag("office_external_target")
                        first_child = len(reports)
                        inspect(child, member_name, "", depth + 1, report["filename"])
                        if any(item["indicators"] for item in reports[first_child:]):
                            flag("nested_suspicious_content")
                        if any(item["limitations"] for item in reports[first_child:]):
                            limit("nested_content_incomplete")
            except (zipfile.BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError):
                flag("scan_error")
                limit("archive_unreadable")
        elif magic in {"opaque_archive", "unknown"} or ext in {".iso", ".img", ".rar", ".7z", ".ace"}:
            limit("unsupported_or_opaque_format")

    def bounded_parts():
        stack = [(msg, 0)]
        visited = 0
        while stack:
            part, depth = stack.pop()
            visited += 1
            if visited > 1000 or depth > 20:
                yield None
                return
            yield part
            if part.is_multipart():
                children = part.get_payload()
                if not isinstance(children, list) or len(children) > 1000:
                    yield None
                    return
                stack.extend((child, depth + 1) for child in reversed(children))

    count = 0
    for part in bounded_parts():
        if part is None:
            reports.append({"filename": "(remaining MIME tree)", "parent": None,
                            "indicators": ["archive_limit"], "limitations": ["mime_tree_limit"],
                            "declared_type": "", "detected_type": "unscanned", "content_type": "unscanned", "size": None,
                            "sha256": None})
            break
        filename = part.get_filename()
        if filename:
            pieces = []
            for value, charset in decode_header(str(filename)):
                if isinstance(value, bytes):
                    try:
                        value = value.decode(charset or "utf-8", errors="replace")
                    except LookupError:
                        value = value.decode("utf-8", errors="replace")
                pieces.append(value)
            filename = "".join(pieces)
        attached = (part.get_content_disposition() == "attachment" or filename or
                    (not part.is_multipart() and part.get_content_maintype() not in {"text", "multipart"}))
        if not attached:
            continue
        count += 1
        if count > ATTACHMENT_MAX_PARTS or budget["items"] <= 0:
            reports.append({"filename": "(remaining MIME parts)", "parent": None,
                            "indicators": ["archive_limit"], "limitations": ["mime_part_limit"],
                            "declared_type": "", "detected_type": "unscanned", "content_type": "unscanned", "size": None,
                            "sha256": None})
            break
        payload = part.get_payload()
        if not isinstance(payload, (str, bytes)):
            reports.append({"filename": filename or "(attached message)", "parent": None,
                            "indicators": [], "limitations": ["container_payload_not_directly_scanned"],
                            "declared_type": part.get_content_type(), "detected_type": "unscanned", "content_type": "unscanned",
                            "size": None, "sha256": None})
            continue
        limit = min(ATTACHMENT_MAX_BYTES, budget["bytes"])
        # Apply a bound before decoding MIME base64 or quoted-printable payloads.
        if limit <= 0 or len(payload) > limit * 4:
            reports.append({"filename": filename or "(unnamed)", "parent": None,
                            "indicators": ["archive_limit"], "limitations": ["mime_payload_size_limit"],
                            "declared_type": part.get_content_type(), "detected_type": "unscanned", "content_type": "unscanned",
                            "size": None, "sha256": None})
            continue
        decoded = part.get_payload(decode=True)
        if decoded is None:
            decoded = payload.encode("utf-8", errors="replace") if isinstance(payload, str) else payload
        if len(decoded) > limit:
            reports.append({"filename": filename or "(unnamed)", "parent": None,
                            "indicators": ["archive_limit"], "limitations": ["decoded_payload_size_limit"],
                            "declared_type": part.get_content_type(), "detected_type": "unscanned", "content_type": "unscanned",
                            "size": len(decoded), "sha256": None})
            continue
        budget["bytes"] -= len(decoded)
        inspect(decoded, filename or "", part.get_content_type())
    for report in reports:
        report["status"] = "suspicious" if report["indicators"] else (
            "incomplete" if report["limitations"] else "no_indicator")
        report["complete"] = not report["limitations"]
        report["malware_confirmed"] = False
        report["analysis"] = "bounded_static_indicators_only"
    return reports


def extract_attachment_features(msg):
    reports = inspect_email_attachments(msg)
    top = [r for r in reports if r["parent"] is None]
    def count(*flags):
        return sum(bool(set(flags) & set(r["indicators"])) for r in reports)
    return {
        "num_attachments": len(top),
        "has_executable_attachment": int(bool(count("executable_extension", "executable_content"))),
        "has_macro_attachment": int(bool(count("macro_enabled_extension", "office_macro"))),
        "has_archive_attachment": int(any(r["detected_type"] in {"zip", "opaque_archive"} for r in reports)),
        "has_double_extension_attachment": int(bool(count("double_extension"))),
        "attachment_suspicious_count": sum(r["status"] == "suspicious" for r in reports),
        "attachment_incomplete_scan_count": sum(not r["complete"] for r in reports),
        "attachment_type_mismatch_count": count("type_mismatch"),
        "attachment_disguised_executable_count": count("disguised_executable"),
        "attachment_bidi_filename_count": count("bidi_filename"),
        "attachment_embedded_executable_count": count("embedded_executable"),
        "attachment_office_active_content_count": count("office_macro", "office_active_code_strings", "office_embedded_object", "office_dde_field"),
        "attachment_office_external_target_count": count("office_external_target"),
        "attachment_pdf_active_content_count": count("pdf_active_content"),
        "attachment_script_content_count": count("script_or_form_content"),
        "attachment_encrypted_archive_count": count("encrypted_archive"),
        "attachment_archive_limit_count": count("archive_limit", "archive_path_traversal"),
        "attachment_scan_error_count": count("scan_error"),
        "attachment_disguised_active_count": count("disguised_active_content"),
    }


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
# 7. Text obfuscation: invisible characters, mixed fonts/scripts, hidden HTML
# --------------------------------------------------------------------------

# Measured on the corpora (2026-10): 6-8% of Nazario 2022-2025 phishing contains
# invisible characters and up to 8.8% has Cyrillic/Greek letters inside Latin
# words (passwогd, Bаnk, UРЅ); legitimate corpora are ~0%. That legitimate mail
# is also older and mostly plain text, so the counts are evidence, not model
# features. The text models receive the normalized, visible text instead.
TEXT_OBFUSCATION_FEATURE_NAMES = [
    "invisible_char_count", "bidi_control_count", "styled_char_count", "mixed_style_word_count",
    "mixed_script_word_count", "confusable_char_count", "spaced_letter_word_count",
    "hidden_text_ratio", "font_family_count", "font_switch_count",
    "intra_word_tag_break_count", "intra_word_font_switch_count",
    "webfont_rule_count", "embedded_webfont_count",
]
_INVISIBLE_CHARS = re.compile("[­͏؜ᅟᅠ឴឵᠋-᠎​-‏"
                              "‪-‮⁠-⁤⁦-⁯ㅤ︀-️﻿ﾠ]")
_BIDI_CONTROLS = set("؜‎‏‪‫‬‭‮⁦⁧⁨⁩")
# "Fonts" that NFKC leaves alone; math bold/italic, fullwidth and circled letters are NFKC-mapped.
_SMALL_CAPS_CHARS = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡʏᴢ"
_SMALL_CAPS = str.maketrans(_SMALL_CAPS_CHARS, "abcdefghijklmnopqrstuvwyz")
# Cyrillic/Greek/Armenian letters that render like Latin ones (subset of Unicode confusables).
_HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "һ": "h", "ԛ": "q", "ԝ": "w", "ӏ": "l", "г": "r", "п": "n", "к": "k",
    "м": "m", "т": "t", "ѵ": "v",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
    "Т": "T", "Х": "X", "У": "Y", "І": "I", "Ј": "J", "Ѕ": "S", "Ԍ": "G", "Ԛ": "Q", "Ԝ": "W", "Ӏ": "I",
    "α": "a", "ο": "o", "ν": "v", "κ": "k", "ι": "i", "υ": "u", "γ": "y", "ε": "e", "χ": "x",
    "ω": "w", "η": "n", "ρ": "p", "τ": "t", "β": "b", "μ": "u", "ϲ": "c", "ϳ": "j",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N",
    "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "օ": "o", "ս": "u", "հ": "h", "ո": "n",
})
_CONFUSABLE_SCRIPTS = {"CYRILLIC", "GREEK", "ARMENIAN"}
# "P a y P a l", "S.E.C.U.R.I.T.Y": one repeated separator between 5+ single letters.
_SPACED_LETTERS = re.compile(r"\b[A-Za-z](?P<sep>[ .\-_*·])[A-Za-z](?:(?P=sep)[A-Za-z]){3,}\b")


def _script(ch):
    return unicodedata.name(ch, "").split(" ", 1)[0] if ch.isalpha() else None


def normalize_obfuscated_text(text):
    """Undo obfuscation that keeps the rendered look; returns (text, counts).

    Only words that mix Latin with Cyrillic/Greek/Armenian are mapped to Latin,
    so genuine Cyrillic/Greek text and Vietnamese diacritics stay unchanged.
    """
    counts = defaultdict(int)
    invisible = _INVISIBLE_CHARS.findall(text)
    counts["invisible_char_count"] = len(invisible)
    counts["bidi_control_count"] = sum(c in _BIDI_CONTROLS for c in invisible)
    text = _INVISIBLE_CHARS.sub("", text)

    def word(match):
        value = match.group(0)
        styled = sum(c in _SMALL_CAPS_CHARS or unicodedata.normalize("NFKC", c) != c for c in value)
        if styled:
            counts["styled_char_count"] += styled
            counts["mixed_style_word_count"] += styled < len(value)
            value = unicodedata.normalize("NFKC", value).translate(_SMALL_CAPS)
        scripts = {_script(c) for c in value} - {None}
        if "LATIN" in scripts and scripts & _CONFUSABLE_SCRIPTS:
            counts["mixed_script_word_count"] += 1
            mapped = value.translate(_HOMOGLYPHS)
            counts["confusable_char_count"] += sum(a != b for a, b in zip(value, mapped))
            value = "".join(c for c in unicodedata.normalize("NFKD", mapped) if not unicodedata.combining(c))
        return value

    text = re.sub(r"[^\W_]+", word, text)

    def join(match):
        counts["spaced_letter_word_count"] += 1
        return re.sub(r"[ .\-_*·]", "", match.group(0))

    text = _SPACED_LETTERS.sub(join, text)
    return unicodedata.normalize("NFKC", text), dict(counts)


_BLOCK_TAGS = {"address", "article", "aside", "blockquote", "br", "center", "dd", "div", "dl", "dt",
               "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
               "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table", "tbody",
               "td", "tfoot", "th", "thead", "tr", "ul"}
_NON_RENDERED_TAGS = {"script", "style", "head", "title", "template", "noembed", "iframe", "object", "embed"}
_NAMED_COLORS = {"white": "#ffffff", "black": "#000000", "red": "#ff0000", "blue": "#0000ff",
                 "green": "#008000", "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0"}
_LINE_BREAK = object()


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _style_hides(style):
    """Inline/CSS declarations that make text invisible in a mail client."""
    if not style:
        return False
    s = str(style).lower()
    if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden|mso-hide\s*:\s*all", s):
        return True
    match = re.search(r"opacity\s*:\s*([\d.]+)", s)
    if match and (_number(match.group(1)) is not None) and _number(match.group(1)) <= 0.05:
        return True
    match = re.search(r"font-size\s*:\s*([\d.]+)\s*(px|pt|em|rem|%)?", s)
    if match and _number(match.group(1)) is not None:
        size, unit = _number(match.group(1)), match.group(2) or "px"
        if size == 0 or (unit in ("px", "pt") and size <= 1) or (unit in ("em", "rem") and size <= 0.1) \
                or (unit == "%" and size <= 10):
            return True
    return bool(re.search(r"overflow\s*:\s*hidden", s) and re.search(
        r"(?<![-\w])(?:max-)?(?:height|width)\s*:\s*0(?:px|pt|em|%)?\s*(?:;|!|$)", s))


def _normalize_color(value):
    if not value:
        return None
    v = str(value).strip().lower().replace(" ", "").split("!")[0]
    if v in _NAMED_COLORS:
        return _NAMED_COLORS[v]
    match = re.fullmatch(r"#?([0-9a-f]{3})", v)
    if match:
        return "#" + "".join(c * 2 for c in match.group(1))
    match = re.fullmatch(r"#?([0-9a-f]{6})", v)
    if match:
        return "#" + match.group(1)
    match = re.fullmatch(r"rgba?\((\d+),(\d+),(\d+)(?:,[\d.]+)?\)", v)
    if match:
        return "#%02x%02x%02x" % tuple(min(255, int(x)) for x in match.groups())
    return None


def _css_value(style, prop):
    match = re.search(r"(?<![-\w])" + prop + r"\s*:\s*([^;]+)", str(style or ""), re.I)
    return match.group(1).strip() if match else None


def _css_color(style, prop):
    value = _css_value(style, prop)
    if value is None:
        return None
    if prop == "background":
        return next((c for c in map(_normalize_color, value.split()) if c), None)
    return _normalize_color(value)


def _hidden_css_selectors(markup):
    """Classes/ids hidden by <style> rules, e.g. the .preheader{display:none} convention."""
    classes, ids = set(), set()
    css = " ".join(re.findall(r"<style\b[^>]*>(.*?)</style\s*>", markup, re.I | re.S))
    for selectors, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        if _style_hides(body):
            for selector in selectors.split(","):
                selector = selector.strip()
                match = re.fullmatch(r"[a-z0-9]*\.([\w-]+)", selector, re.I)
                if match:
                    classes.add(match.group(1).lower())
                match = re.fullmatch(r"[a-z0-9]*#([\w-]+)", selector, re.I)
                if match:
                    ids.add(match.group(1).lower())
    return classes, ids


def extract_visible_html_text(markup):
    """Text a mail client would show, and how it was styled.

    Hidden elements are dropped (inline style, hiding <style> classes, text in
    the background color). Inline tags are joined without inserting spaces, so
    "Pa<span>ss</span>word" stays one word. Web fonts are reported, not decoded:
    a custom font can remap glyphs so the stored characters differ from what is
    displayed, and that cannot be undone without rendering the font.
    """
    from bs4.element import Comment, Declaration, Doctype, NavigableString, ProcessingInstruction, Tag
    stats = {"hidden_text_chars": 0, "visible_text_chars": 0, "font_family_count": 0,
             "font_switch_count": 0, "intra_word_tag_break_count": 0,
             "intra_word_font_switch_count": 0, "webfont_rule_count": 0, "embedded_webfont_count": 0}
    if not markup:
        return "", stats
    if "<" not in markup:
        text = re.sub(r"\s+", " ", html_module.unescape(markup)).strip()
        stats["visible_text_chars"] = len(text)
        return text, stats
    stats["webfont_rule_count"] = len(re.findall(r"@font-face", markup, re.I))
    stats["embedded_webfont_count"] = len(re.findall(r"url\(\s*['\"]?data:(?:application|font)/", markup, re.I))
    hidden_classes, hidden_ids = _hidden_css_selectors(markup)
    try:
        soup = BeautifulSoup(markup, "html.parser")
    except Exception:
        text = _strip_html(markup)
        stats["visible_text_chars"] = len(text)
        return text, stats
    pieces, fonts = [], set()
    last = {"font": None, "tail": "", "started": False}
    stack = [(soup, False, None, None, (None, None))]
    while stack:
        item = stack.pop()
        if item is _LINE_BREAK:
            pieces.append("\n")
            last["tail"] = "\n"
            continue
        node, hidden, color, background, font = item
        if isinstance(node, (Comment, Declaration, Doctype, ProcessingInstruction)):
            continue
        if isinstance(node, NavigableString):
            text = str(node)
            if hidden:
                stats["hidden_text_chars"] += len(text.strip())
                continue
            if text.strip():
                if last["tail"][-1:].isalnum() and text[:1].isalnum():
                    stats["intra_word_tag_break_count"] += 1
                    stats["intra_word_font_switch_count"] += font != last["font"]
                if last["started"] and font != last["font"]:
                    stats["font_switch_count"] += 1
                last.update(font=font, tail=text, started=True)
                fonts.add(font[0])
                stats["visible_text_chars"] += len(text.strip())
            else:
                last["tail"] = " "
            pieces.append(text)
            continue
        if not isinstance(node, Tag):
            continue
        name = (node.name or "").lower()
        if name in _NON_RENDERED_TAGS:
            continue
        style = node.get("style", "") or ""
        classes = {str(c).lower() for c in (node.get("class") or [])}
        color = (_css_color(style, "color") or
                 (_normalize_color(node.get("color")) if name == "font" else None) or color)
        background = (_css_color(style, "background-color") or _css_color(style, "background") or
                      _normalize_color(node.get("bgcolor")) or background)
        hidden = (hidden or node.has_attr("hidden") or _style_hides(style) or bool(classes & hidden_classes)
                  or str(node.get("id", "")).lower() in hidden_ids
                  or bool(color and background and color == background))
        family = _css_value(style, "font-family") or (node.get("face") if name == "font" else None)
        size = _css_value(style, "font-size") or (node.get("size") if name == "font" else None)
        family = family.split(",")[0].strip(" '\"").lower() if family else font[0]
        font = (family, str(size).strip().lower() if size else font[1])
        if name in _BLOCK_TAGS:
            pieces.append("\n")
            last["tail"] = "\n"
            stack.append(_LINE_BREAK)
        stack.extend((child, hidden, color, background, font) for child in reversed(node.contents))
    stats["font_family_count"] = len(fonts - {None})
    text = "".join(pieces)
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return re.sub(r"\n{2,}", "\n", text).strip(), stats


def _deobfuscated_message_text(msg):
    """Subject + visible body after deobfuscation, with evidence counts; cached on msg."""
    if hasattr(msg, "_pipeline_text"):
        return msg._pipeline_text
    plain, markup = _get_email_body(msg)
    visible, html_stats = extract_visible_html_text(markup)
    subject = _content_subject(msg).strip()
    bodies = list(dict.fromkeys(s.strip() for s in (plain, visible) if s.strip()))
    text, counts = normalize_obfuscated_text(
        _without_corpus_artifacts("\n\n".join(([subject] if subject else []) + bodies)))
    shown = html_stats["hidden_text_chars"] + html_stats["visible_text_chars"]
    values = {**counts, **html_stats,
              "hidden_text_ratio": html_stats["hidden_text_chars"] / shown if shown else 0.0}
    msg._pipeline_text = (text, {name: float(values.get(name, 0)) for name in TEXT_OBFUSCATION_FEATURE_NAMES})
    return msg._pipeline_text


def extract_text_obfuscation_features(raw_text):
    return _deobfuscated_message_text(_parse_email(raw_text))[1]


# --------------------------------------------------------------------------
# 8. QR codes (quishing)
# --------------------------------------------------------------------------

# NOT USED BY THE PIPELINE (2026-10-21): the corpora contain only 2 emails with a
# decodable QR code, too few to evaluate. Kept as an optional, standalone tool;
# needs `pip install zxing-cpp` and imports it lazily.
# QR codes are decoded from MIME images, data: URIs in HTML, images inside
# Office/ZIP attachments, PDF pages (only when PyMuPDF is installed), and QR
# codes drawn with HTML table cells or Unicode block characters, which evade
# image scanners. Nothing is fetched: remote images are counted as unscanned.
QR_FEATURE_NAMES = [
    "qr_code_count", "qr_url_count", "qr_non_url_payload_count", "qr_only_link",
    "qr_url_sender_domain_mismatch", "qr_url_not_in_email_links", "qr_url_risky_host_count",
    "qr_url_sensitive_word_count", "qr_in_attachment_count", "qr_rendered_from_markup_count",
    "qr_unscanned_image_count",
]
QR_MAX_IMAGES = 24
QR_MAX_PIXELS = 25_000_000
QR_MAX_PDF_PAGES = 3
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
_QR_KINDS = ((r"^(?:https?|ftp)://|^www\.", "url"), (r"^mailto:", "email"), (r"^(?:tel|sms|smsto|mms):", "phone"),
             (r"^WIFI:", "wifi"), (r"^BEGIN:VCARD", "contact"), (r"^MECARD:", "contact"),
             (r"^(?:bitcoin|ethereum|litecoin|monero):", "crypto"), (r"^otpauth://", "otp"))
_HALF_BLOCKS = {"█": (1, 1), "▀": (1, 0), "▄": (0, 1), "■": (1, 1), "▓": (1, 1), " ": (0, 0), " ": (0, 0)}


def _read_qr(image):
    """zxing-cpp on a grayscale PIL image; tiny images are also tried upscaled."""
    from PIL import Image
    import zxingcpp
    def read(img):
        return [r.text for r in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode)
                if r.valid and r.text]
    texts = read(image)
    if not texts and min(image.size) < 300:
        texts = read(image.resize((image.width * 4, image.height * 4), Image.NEAREST))
    return texts


def _decode_qr_image(data):
    import io
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > QR_MAX_PIXELS:
                return [], "image_pixel_limit"
            texts = []
            for index in range(min(getattr(image, "n_frames", 1), 3)):
                image.seek(index)
                # Composite transparency on white: a dark-on-transparent QR is otherwise all dark.
                rgba = image.convert("RGBA")
                gray = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba).convert("L")
                texts.extend(t for t in _read_qr(gray) if t not in texts)
            return texts, None
    except Image.DecompressionBombError:
        return [], "image_pixel_limit"
    except Exception:
        return [], "image_unreadable"


def _grid_to_image(grid):
    """0/1 module grid (1 = dark) -> scaled grayscale image with a quiet zone."""
    import numpy as np
    from PIL import Image
    modules = np.pad(np.asarray(grid, dtype=np.uint8), 4)
    pixels = np.kron(255 - modules * 255, np.ones((6, 6), dtype=np.uint8)).astype(np.uint8)
    return Image.fromarray(pixels, mode="L")


def _html_table_qr_images(markup):
    """QR codes drawn as table cells with dark/light background colors."""
    if len(re.findall(r"<tr\b", markup, re.I)) < 21:
        return []
    try:
        soup = BeautifulSoup(markup, "html.parser")
    except Exception:
        return []
    images = []
    for table in soup.find_all("table")[:20]:
        rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
        if not 21 <= len(rows) <= 200:
            continue
        grid, colors = [], set()
        for tr in rows:
            row = []
            for cell in (c for c in tr.find_all(["td", "th"]) if c.find_parent("tr") is tr):
                color = (_css_color(cell.get("style"), "background-color") or _css_color(cell.get("style"), "background")
                         or _normalize_color(cell.get("bgcolor")) or "#ffffff")
                colors.add(color)
                r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
                span = int(_number(cell.get("colspan")) or 1)
                row.extend([int(0.299 * r + 0.587 * g + 0.114 * b < 128)] * max(1, min(span, 200)))
            grid.append(row)
        width = max(len(r) for r in grid)
        if len(colors) < 2 or width < 21 or width > 200 or min(len(r) for r in grid) < width - 1:
            continue
        images.append(_grid_to_image([r + [0] * (width - len(r)) for r in grid]))
    return images


def _block_character_qr_images(text):
    """QR codes drawn with full/half block characters (one char = two vertical modules)."""
    if not any(c in text for c in "█▀▄"):
        return []
    images, run = [], []
    for line in text.splitlines() + [""]:
        blocks = sum(c in "█▀▄■▓" for c in line)
        if blocks >= 10 and all(c in _HALF_BLOCKS for c in line.rstrip()):
            run.append(line.rstrip())
            continue
        if len(run) >= 10:
            width = max(len(r) for r in run)
            grid = []
            for r in run:
                cells = [_HALF_BLOCKS.get(c, (0, 0)) for c in r.ljust(width)]
                grid.append([top for top, _ in cells])
                grid.append([bottom for _, bottom in cells])
            images.append(_grid_to_image(grid))
        run = []
    return images


def _message_images(msg):
    """Yield (image bytes, origin) without fetching remote content; count what was not scanned."""
    import base64
    import io
    import zipfile
    unscanned = 0
    found = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        name = str(part.get_filename() or "").lower()
        ctype = part.get_content_type()
        try:
            data = part.get_payload(decode=True) or b""
        except Exception:
            continue
        if len(data) > ATTACHMENT_MAX_BYTES:
            unscanned += ctype.startswith("image/") or name.endswith(tuple(_IMAGE_EXTENSIONS))
            continue
        if ctype == "image/svg+xml" or name.endswith(".svg"):
            unscanned += 1
        elif ctype.startswith("image/") or os.path.splitext(name)[1] in _IMAGE_EXTENSIONS:
            found.append((data, "mime_image"))
        elif data.startswith(b"PK\x03\x04"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for member in archive.infolist()[:ATTACHMENT_MAX_MEMBERS]:
                        if os.path.splitext(member.filename.lower())[1] in _IMAGE_EXTENSIONS:
                            if member.file_size > ATTACHMENT_MAX_BYTES or member.flag_bits & 1:
                                unscanned += 1
                            else:
                                found.append((archive.read(member), "attachment_container"))
            except Exception:
                unscanned += 1
        elif data.startswith(b"%PDF-"):
            try:
                import fitz  # PyMuPDF, optional: renders pages so QR codes in PDFs can be read.
            except ImportError:
                unscanned += 1
                continue
            try:
                with fitz.open(stream=data, filetype="pdf") as document:
                    for page in list(document)[:QR_MAX_PDF_PAGES]:
                        found.append((page.get_pixmap(dpi=150).tobytes("png"), "attachment_container"))
            except Exception:
                unscanned += 1
    _, markup = _get_email_body(msg)
    for match in re.finditer(r"data:image/(?:png|jpe?g|gif|bmp|webp);base64,([A-Za-z0-9+/=\s]{40,})", markup, re.I):
        payload = re.sub(r"\s+", "", match.group(1))
        if len(payload) > ATTACHMENT_MAX_BYTES * 4 // 3:
            unscanned += 1
            continue
        try:
            found.append((base64.b64decode(payload + "=" * (-len(payload) % 4)), "html_data_uri"))
        except ValueError:
            unscanned += 1
    unscanned += len(re.findall(r"<img\b[^>]*\bsrc\s*=\s*[\"']?\s*(?:https?:)?//", markup, re.I))
    unscanned += max(0, len(found) - QR_MAX_IMAGES)
    return found[:QR_MAX_IMAGES], unscanned


def _qr_kind(payload):
    text = payload.strip()
    for pattern, kind in _QR_KINDS:
        if re.match(pattern, text, re.I):
            return kind
    return "url" if re.fullmatch(r"[\w-]+(?:\.[\w-]+)+\.[a-z]{2,}(?:[/?#]\S*)?|[\w-]+\.[a-z]{2,}(?:[/?#]\S*)?",
                                 text, re.I) else "text"


def inspect_email_qr_codes(raw_or_message):
    """Decoded QR payloads with origin, plus QR_FEATURE_NAMES values; cached on the message."""
    msg = _parse_email(raw_or_message)
    if hasattr(msg, "_pipeline_qr"):
        return msg._pipeline_qr
    codes, limitations = [], []
    images, unscanned = _message_images(msg)
    for data, origin in images:
        texts, problem = _decode_qr_image(data)
        if problem:
            unscanned += 1
            limitations.append(problem)
        codes.extend({"payload": t, "origin": origin} for t in texts)
    plain, markup = _get_email_body(msg)
    drawn = _html_table_qr_images(markup) + _block_character_qr_images(plain + "\n" + _strip_html(markup))
    for image in drawn:
        codes.extend({"payload": t, "origin": "drawn_in_markup"} for t in _read_qr(image))
    if unscanned:
        limitations.append(f"{unscanned} image(s) not scanned (remote, SVG, PDF without renderer, or limits)")
    sender = parseaddr(str(msg.get("From", "")))[1]
    sender_domain = registrable_domain(_address_domain(sender)) if "@" in sender else ""
    links = _find_urls(plain, markup)
    link_domains = {url_group_key(u) for u in links}
    values = defaultdict(float)
    for code in codes:
        code["kind"] = _qr_kind(code["payload"])
        values["qr_code_count"] += 1
        values["qr_in_attachment_count"] += code["origin"] == "attachment_container"
        values["qr_rendered_from_markup_count"] += code["origin"] == "drawn_in_markup"
        if code["kind"] != "url":
            values["qr_non_url_payload_count"] += 1
            continue
        lexical = dict(zip(URL_LEXICAL_FEATURE_NAMES, extract_url_lexical_features(code["payload"])))
        domain = url_group_key(code["payload"])
        code["domain"] = domain
        values["qr_url_count"] += 1
        values["qr_url_sender_domain_mismatch"] += bool(sender_domain) and domain != sender_domain
        values["qr_url_not_in_email_links"] += domain not in link_domains
        values["qr_url_risky_host_count"] += any(lexical[n] for n in (
            "url_host_is_ip", "url_is_shortener", "url_suspicious_tld", "url_has_at_symbol",
            "url_has_punycode", "url_has_port", "url_executable_extension"))
        values["qr_url_sensitive_word_count"] += lexical["url_sensitive_word_count"]
    values["qr_only_link"] = float(values["qr_url_count"] > 0 and not links)
    values["qr_unscanned_image_count"] = float(unscanned)
    msg._pipeline_qr = {"codes": codes, "limitations": limitations,
                        "features": {n: float(values[n]) for n in QR_FEATURE_NAMES}}
    return msg._pipeline_qr


def extract_qr_features(raw_text):
    return inspect_email_qr_codes(raw_text)["features"]


# --------------------------------------------------------------------------
# 9. Brand impersonation, link context, attachment payloads, BEC content
#    (Phishing Email Investigation Guide, Ch. 7.3, 9.2-9.4, 10.1, 11.1, 18.4.3, 20.1)
# --------------------------------------------------------------------------

# brand -> (name tokens, official registrable domains). A domain is also treated as
# official when its registrable label equals a token (regional sites: amazon.de, dhl.de).
BRAND_DOMAINS = {
    "paypal": ({"paypal"}, {"paypal.com", "paypal.me", "paypalobjects.com", "paypal-community.com"}),
    "microsoft": ({"microsoft", "office365", "onedrive", "sharepoint", "outlook"},
                  {"microsoft.com", "office.com", "office365.com", "live.com", "outlook.com", "hotmail.com",
                   "msn.com", "microsoftonline.com", "sharepoint.com", "onmicrosoft.com", "windows.net",
                   "azure.com", "bing.com", "skype.com", "onedrive.com", "office.net"}),
    "apple": ({"apple", "icloud"}, {"apple.com", "icloud.com", "itunes.com", "me.com", "mzstatic.com"}),
    "amazon": ({"amazon"}, {"amazon.com", "amazonses.com", "amazonaws.com", "media-amazon.com", "ssl-images-amazon.com"}),
    "google": ({"google", "gmail"}, {"google.com", "gmail.com", "googlemail.com", "googleusercontent.com",
                                     "googleapis.com", "gstatic.com", "youtube.com", "goo.gl",
                                     "googleadservices.com", "googletagmanager.com", "googlesyndication.com",
                                     "googlegroups.com", "googleblog.com", "google-analytics.com"}),
    "netflix": ({"netflix"}, {"netflix.com", "nflxext.com", "nflximg.net"}),
    "facebook": ({"facebook", "instagram", "whatsapp"},
                 {"facebook.com", "facebookmail.com", "fb.com", "fbcdn.net", "instagram.com", "whatsapp.com", "meta.com"}),
    "linkedin": ({"linkedin"}, {"linkedin.com", "licdn.com"}),
    "dhl": ({"dhl"}, {"dhl.com"}), "fedex": ({"fedex"}, {"fedex.com"}), "ups": ({"ups"}, {"ups.com"}),
    "usps": ({"usps"}, {"usps.com", "usps.gov"}), "irs": ({"irs"}, {"irs.gov"}),
    "chase": ({"chase"}, {"chase.com", "jpmorganchase.com", "jpmorgan.com"}),
    "wellsfargo": ({"wellsfargo"}, {"wellsfargo.com", "wf.com"}),
    "bankofamerica": ({"bankofamerica"}, {"bankofamerica.com", "bofa.com", "ml.com"}),
    "citibank": ({"citibank"}, {"citibank.com", "citi.com"}),
    "americanexpress": ({"americanexpress", "amex"}, {"americanexpress.com", "aexp.com"}),
    "docusign": ({"docusign"}, {"docusign.com", "docusign.net"}),
    "dropbox": ({"dropbox"}, {"dropbox.com", "dropboxmail.com", "dropboxusercontent.com"}),
    "adobe": ({"adobe"}, {"adobe.com", "adobesign.com", "acrobat.com"}),
    "ebay": ({"ebay"}, {"ebay.com", "ebayimg.com", "ebaystatic.com"}),
    "yahoo": ({"yahoo"}, {"yahoo.com", "yahoo.net", "yimg.com"}),
    "aol": ({"aol"}, {"aol.com"}), "att": ({"att"}, {"att.com", "att.net"}),
    "verizon": ({"verizon"}, {"verizon.com", "verizon.net", "verizonwireless.com"}),
    "coinbase": ({"coinbase"}, {"coinbase.com"}), "binance": ({"binance"}, {"binance.com"}),
    "steam": ({"steamcommunity", "steampowered"}, {"steamcommunity.com", "steampowered.com"}),
}
_BRAND_TOKENS = {token: brand for brand, (tokens, _) in BRAND_DOMAINS.items() for token in tokens}
# Free hosting / site builders / tunnels: reputable infrastructure abused to host kits (Ch. 20.1).
FREE_HOSTING_SUFFIXES = (
    "weebly.com", "weeblysite.com", "wixsite.com", "web.app", "firebaseapp.com", "appspot.com",
    "glitch.me", "workers.dev", "pages.dev", "netlify.app", "vercel.app", "github.io", "gitlab.io",
    "herokuapp.com", "000webhostapp.com", "blogspot.com", "sites.google.com", "ipfs.io", "dweb.link",
    "cf-ipfs.com", "r2.dev", "azurewebsites.net", "square.site", "godaddysites.com", "mystrikingly.com",
    "jimdosite.com", "webflow.io", "framer.app", "ngrok.io", "ngrok-free.app", "trycloudflare.com",
    "duckdns.org", "replit.app", "repl.co", "notion.site", "typedream.app", "carrd.co")
_SKELETON_PAIRS = (("rn", "m"), ("vv", "w"), ("cl", "d"))
_SKELETON_CHARS = str.maketrans({"0": "o", "1": "l", "i": "l", "|": "l", "3": "e", "5": "s", "$": "s", "@": "a"})


def _skeleton(label):
    """Visual skeleton for lookalike comparison: homoglyphs, I/l/1, 0/o, rn/m, vv/w."""
    label = unicodedata.normalize("NFKC", label.lower()).translate(_HOMOGLYPHS)
    label = "".join(c for c in unicodedata.normalize("NFKD", label) if not unicodedata.combining(c)).lower()
    for pair, replacement in _SKELETON_PAIRS:
        label = label.replace(pair, replacement)
    return label.translate(_SKELETON_CHARS)


def _edit_distance(a, b):
    """Optimal string alignment distance (one transposition counts as one edit)."""
    previous2, previous = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            if previous2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                current[j] = min(current[j], previous2[j - 2] + 1)
        previous2, previous = previous, current
    return previous[-1]


@lru_cache(maxsize=131072)
def brand_impersonation(host):
    """(brand, 'lookalike'|'combosquat') when a host imitates a brand it does not belong to.

    lookalike: a label visually equals or is one edit from a brand (paypa1, rnicrosoft,
    suppIies-style homoglyphs). combosquat: the brand name is embedded in someone else's
    domain (paypal-secure.com, paypal.com.evil.tk). Official domains return None.
    """
    host = str(host).lower().strip(".")
    if not host or re.fullmatch(r"[\d.]+|\[?[0-9a-f:]+\]?", host):
        return None
    labels = []
    for label in host.split("."):
        if label.startswith("xn--"):
            try:
                label = label.encode("ascii").decode("idna")
            except (UnicodeError, ValueError):
                pass
        labels.append(label)
    host = ".".join(labels)
    registered = registrable_domain(host)
    registered_label = registered.split(".")[0]
    parts = [p for label in labels for p in label.split("-") if p]
    for part in parts:
        skeleton = _skeleton(part)
        for token, brand in _BRAND_TOKENS.items():
            if part == token or abs(len(part) - len(token)) > 1:
                continue
            # Edit distance only for long names: "apply"/"apple", "tunes"/"itunes" are real words.
            if skeleton == _skeleton(token) or (len(token) >= 6 and _edit_distance(part, token) == 1):
                return brand, "lookalike"
    for token, brand in _BRAND_TOKENS.items():
        official = BRAND_DOMAINS[brand][1]
        if registered in official or registered_label == token:
            continue
        # Short names must be a whole part ("purchase" must not match "chase").
        if any(p == token or (len(token) >= 6 and (p.startswith(token) or p.endswith(token)))
               or (len(token) >= 8 and token in p) for p in parts):
            return brand, "combosquat"
    return None


def _domain_label(domain):
    """Label before the public suffix: globex-supplies for mail.globex-supplies.co.uk."""
    return _psl_parts(domain).domain or str(domain).split(".")[0]


@lru_cache(maxsize=131072)
def domains_look_alike(a, b):
    """True when registrable domain a imitates b without being it (any domain, no list).

    Same label under another suffix (amazon.de / amazon.com, hotmail.co.uk / hotmail.com)
    is not counted: regional sites are too common. Labels under 5 characters are skipped;
    5-character labels need a visual match, since one edit joins real names (apple/apply).
    """
    if not a or not b or a == b:
        return False
    x, y = _domain_label(a), _domain_label(b)
    if x == y or min(len(x), len(y)) < 5:
        return False
    if _skeleton(x) == _skeleton(y) or y in x.split("-") or x in y.split("-"):
        return True
    shortest, longest = sorted((len(x), len(y)))
    # Changed ending of a long name: globex-supply / globex-supplies.
    if shortest >= 8 and len(os.path.commonprefix([x, y])) >= longest - 3:
        return True
    if shortest < 6:
        return False
    limit = 1 if longest < 8 else 2
    return longest - shortest <= limit and _edit_distance(x, y) <= limit


def _brand_in_text(text):
    words = set(re.findall(r"[a-z0-9]+", str(text).lower()))
    joined = re.sub(r"[^a-z0-9]", "", str(text).lower())
    return {brand for token, brand in _BRAND_TOKENS.items()
            if token in words or (len(token) >= 8 and token in joined)}


def _is_official_for(brand, host):
    registered = registrable_domain(str(host).lower())
    tokens, official = BRAND_DOMAINS[brand]
    return registered in official or registered.split(".")[0] in tokens


LINK_FEATURE_NAMES = [
    "link_recipient_address_count", "link_open_redirect_count", "link_brand_lookalike_count",
    "link_brand_combosquat_count", "link_anchor_brand_mismatch_count", "link_free_hosting_count",
    # Sender consistency: works for any domain, not only BRAND_DOMAINS. Measured and NOT
    # used (2026-10-25): domain popularity from Tranco 262N9, because enron.com and most
    # 2001-2008 legitimate domains are unranked in a 2026 list (Enron: all links unranked
    # in 58% of linked mail, phishing 21-30%); and "host on a PSL private suffix", which
    # marks era (Nazario 2015+ 14%, Phishing Pot 22%) but Nazario 2004-07 only 1.2%.
    "link_offsite_domain_ratio", "link_sender_lookalike_count",
    # Shape of the most unusual link host (random/generated domains).
    "link_max_host_length", "link_max_subdomain_depth", "link_max_host_hyphen_count",
    "link_max_host_digit_count", "link_max_host_entropy", "link_punycode_count",
]
_HOST_SHAPE = {"link_max_host_length": "url_host_length", "link_max_subdomain_depth": "url_subdomain_count",
               "link_max_host_hyphen_count": "url_host_hyphen_count",
               "link_max_host_digit_count": "url_host_digit_count", "link_max_host_entropy": "url_host_entropy"}
_OPEN_REDIRECT = re.compile(r"[?&#][\w.\-\[\]]*=(?:https?(?::|%3a)(?://|%2f%2f)|%2f%2f|//|www\.)", re.I)


def _recipient_markers(msg):
    """Recipient addresses as they appear when a kit personalises a URL (Ch. 3.3, 10.1)."""
    import base64
    from urllib.parse import quote
    raw = getattr(msg, "_pipeline_raw_headers", None) or {}
    values = [str(v) for v in (raw.get("To") or msg.get_all("To") or [])] + [str(v) for v in (msg.get_all("Cc") or [])]
    markers = set()
    for _, address in getaddresses([_decode_header_value(v) for v in values]):
        address = address.strip().lower()
        if "@" not in address or len(address) < 6:
            continue
        encoded = address.encode()
        markers.update({address, quote(address, safe="").lower(),
                        base64.b64encode(encoded).decode().rstrip("=").lower(),
                        base64.urlsafe_b64encode(encoded).decode().rstrip("=").lower()})
    return markers


def extract_link_features(msg):
    """Per-email link context the lexical URL counts miss."""
    msg = _parse_email(msg)
    plain, markup = _get_email_body(msg)
    urls = _find_urls(plain, markup)
    markers = _recipient_markers(msg)
    sender = parseaddr(str(msg.get("From", "")))[1]
    sender_domain = registrable_domain(_address_domain(sender)) if "@" in sender else ""
    values = defaultdict(float)
    link_domains = set()
    for url in urls:
        lowered = url.lower()
        values["link_recipient_address_count"] += any(m in lowered for m in markers)
        values["link_open_redirect_count"] += bool(_OPEN_REDIRECT.search(url))
        host = (_safe_urlparse(normalize_url(url)).hostname or "").lower()
        verdict = brand_impersonation(host)
        if verdict:
            values["link_brand_" + verdict[1] + "_count"] += 1
        values["link_free_hosting_count"] += any(host == s or host.endswith("." + s) for s in FREE_HOSTING_SUFFIXES)
        if host:
            link_domains.add(registrable_domain(host))
            shape = dict(zip(URL_LEXICAL_FEATURE_NAMES, extract_url_lexical_features(url)))
            for name, source in _HOST_SHAPE.items():
                values[name] = max(values[name], shape[source])
            values["link_punycode_count"] += shape["url_has_punycode"]
    if sender_domain and link_domains:
        values["link_offsite_domain_ratio"] = sum(d != sender_domain for d in link_domains) / len(link_domains)
        values["link_sender_lookalike_count"] = sum(domains_look_alike(d, sender_domain) for d in link_domains)
    for match in re.finditer(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a\s*>', markup, re.I | re.S):
        href = unwrap_gateway_url(html_module.unescape(match.group(1)).strip())
        if not re.match(r"(?:https?:)?//|www\.", href, re.I):
            continue
        host = (_safe_urlparse(normalize_url(href.lstrip("/"))).hostname or "").lower()
        anchor = _strip_html(match.group(2))
        brands = _brand_in_text(anchor)
        values["link_anchor_brand_mismatch_count"] += bool(brands) and not any(_is_official_for(b, host) for b in brands)
    return {name: float(values[name]) for name in LINK_FEATURE_NAMES}


ATTACHMENT_PAYLOAD_FEATURE_NAMES = [
    "attachment_vba_autoexec_count", "attachment_vba_suspicious_count", "attachment_vba_stomping_count",
    "attachment_xlm_macro_count", "attachment_html_smuggling_count", "attachment_password_archive_in_body",
    "attachment_disk_image_count", "attachment_lnk_command_count", "attachment_onenote_embedded_count",
    "attachment_pdf_uri_count", "attachment_config_profile_count",
]
# Apple configuration profiles install mail/CalDAV/CardDAV accounts, root certificates,
# VPN or MDM enrolment once opened on iOS/macOS. Signed profiles are PKCS#7 with the
# plist in clear, so the content is checked, not only the extension. Phishing Pot:
# about 100 such attachments; the other corpora have none.
_PROFILE_MARKER = re.compile(rb"<key>\s*PayloadType\s*</key>\s*<string>\s*Configuration\s*</string>")
_ONENOTE_MAGIC = bytes.fromhex("e4525c7b8cd8a74daeb15378d02996d3")
_ONENOTE_FILE_DATA = bytes.fromhex("e716e3bd65261145a4c48d4d0b7a9eac")
_LNK_MAGIC = b"L\0\0\0\x01\x14\x02\0"
_LNK_COMMAND = re.compile(r"powershell|pwsh|cmd(?:\.exe)?\s*/[ck]|mshta|wscript|cscript|rundll32|regsvr32|"
                          r"bitsadmin|certutil|curl(?:\.exe)?\s|https?://", re.I)
_SMUGGLING_SAVE = re.compile(rb"createObjectURL|msSaveOrOpenBlob|msSaveBlob|\.download\s*=|\bdownload\s*=", re.I)
_BODY_PASSWORD = re.compile(r"\b(?:password|passcode|pwd|pass)\b\s*(?:is|:|=|-)?\s*\S{3,}|m[aậ]t\s*kh[aẩ]u", re.I)
_OFFICE_EXTENSIONS = {".doc", ".dot", ".xls", ".xlt", ".xla", ".ppt", ".pps", ".pot", ".docx", ".docm", ".dotm",
                      ".xlsx", ".xlsm", ".xlsb", ".xltm", ".xlam", ".pptx", ".pptm", ".ppsm", ".potm", ".rtf", ".mht"}


def _attachment_blobs(msg):
    """(name, bytes, encrypted) for MIME attachments and first-level archive members, bounded."""
    import io
    import zipfile
    for part in msg.walk():
        if part.is_multipart():
            continue
        name = str(part.get_filename() or "")
        if not (part.get_content_disposition() == "attachment" or name):
            continue
        try:
            data = part.get_payload(decode=True) or b""
        except Exception:
            continue
        if len(data) > ATTACHMENT_MAX_BYTES:
            continue
        yield name, data, False
        if not data.startswith(b"PK\x03\x04") or os.path.splitext(name.lower())[1] in _OFFICE_ZIP_EXTENSIONS:
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist()[:ATTACHMENT_MAX_MEMBERS]:
                    if member.is_dir():
                        continue
                    if member.flag_bits & 1:
                        yield member.filename, b"", True
                    elif (member.file_size <= ATTACHMENT_MAX_BYTES and
                          member.file_size / max(member.compress_size, 1) <= ATTACHMENT_MAX_RATIO):
                        yield member.filename, archive.read(member), False
        except Exception:
            continue


def _vba_indicators(name, data):
    """olevba static analysis; macros are parsed, never executed."""
    import logging
    try:
        from oletools.olevba import VBA_Parser
    except ImportError:
        return None
    logging.getLogger("olevba").setLevel(logging.CRITICAL)
    try:
        parser = VBA_Parser(name or "attachment", data=data)
    except Exception:
        return None
    try:
        result = {"autoexec": 0, "suspicious": 0, "stomping": 0, "xlm": 0}
        try:
            result["xlm"] = int(bool(parser.detect_xlm_macros()))
        except Exception:
            pass
        if parser.detect_vba_macros():
            kinds = [kind for kind, _, _ in parser.analyze_macros()]
            result["autoexec"] = int("AutoExec" in kinds)
            result["suspicious"] = kinds.count("Suspicious")
            try:
                result["stomping"] = int(bool(parser.detect_vba_stomping()))
            except Exception:
                pass
        return result
    finally:
        parser.close()


def extract_attachment_payload_features(msg):
    msg = _parse_email(msg)
    values = defaultdict(float)
    encrypted_archive = False
    for name, data, encrypted in _attachment_blobs(msg):
        if encrypted:
            encrypted_archive = True
            continue
        low = name.lower()
        ext = os.path.splitext(low)[1]
        magic = _attachment_magic(data)
        if magic == "ole" or ext in _OFFICE_EXTENSIONS or (magic == "zip" and b"vbaProject.bin" in data):
            vba = _vba_indicators(name, data)
            if vba:
                values["attachment_vba_autoexec_count"] += vba["autoexec"]
                values["attachment_vba_suspicious_count"] += vba["suspicious"]
                values["attachment_vba_stomping_count"] += vba["stomping"]
                values["attachment_xlm_macro_count"] += vba["xlm"]
        if ext in {".htm", ".html", ".shtml", ".xhtml", ".svg", ".hta"} or attachment_content_type(data) in {"html", "svg"} or (
                magic == "text" and re.search(rb"<\s*(?:html|svg)\b", data[:4096], re.I)):
            blob = re.search(rb"\bnew\s+Blob\s*\(|\bBlob\s*\(", data)
            decoded = re.search(rb"\batob\s*\(", data) and re.search(rb"[A-Za-z0-9+/]{2000,}={0,2}", data)
            values["attachment_html_smuggling_count"] += bool((blob or decoded) and _SMUGGLING_SAVE.search(data))
        if ext in {".iso", ".img", ".vhd", ".vhdx"} or data[0x8001:0x8006] == b"CD001" or data.startswith(b"vhdxfile"):
            values["attachment_disk_image_count"] += 1
        if data.startswith(_LNK_MAGIC):
            strings = data.decode("utf-16le", errors="ignore") + data.decode("latin-1")
            values["attachment_lnk_command_count"] += bool(_LNK_COMMAND.search(strings))
        if data.startswith(_ONENOTE_MAGIC):
            values["attachment_onenote_embedded_count"] += data.count(_ONENOTE_FILE_DATA)
        if magic == "pdf":
            pdf = re.sub(rb"#([0-9a-fA-F]{2})", lambda m: bytes([int(m[1], 16)]), data)
            values["attachment_pdf_uri_count"] += len(re.findall(rb"/URI\s*\(", pdf))
        if ext == ".mobileconfig" or _PROFILE_MARKER.search(data):
            values["attachment_config_profile_count"] += 1
    if encrypted_archive:
        plain, _ = _get_email_body(msg)
        visible = _deobfuscated_message_text(msg)[0]
        values["attachment_password_archive_in_body"] = float(bool(_BODY_PASSWORD.search(plain + "\n" + visible)))
    return {name: float(values[name]) for name in ATTACHMENT_PAYLOAD_FEATURE_NAMES}


# Files sent as a cloud link instead of a MIME part: Gmail turns attachments over 25 MB
# into Drive links, Outlook into OneDrive/SharePoint links, iCloud Mail into Mail Drop,
# Proton Mail into Proton Drive links; transfer services work from any client. The MIME
# attachment checks never see these files. Evidence only, not a model input: the
# legitimate corpora predate these services, so the model would learn "modern = phishing".
CLOUD_FILE_LINKS = (
    ("google_drive", r"^(?:drive|docs)\.google\.com$", r"^/(?:file|document|spreadsheets|presentation|drawings|forms)/|"
                                                       r"^/(?:open|uc)$|^/drive/folders/"),
    ("google_drive", r"^drive\.usercontent\.google\.com$", r""),
    ("onedrive_sharepoint", r"^1drv\.ms$|^onedrive\.live\.com$|(?:^|\.)sharepoint\.com$", r""),
    ("dropbox", r"^(?:www\.)?dropbox\.com$", r"^/(?:s|scl|sh|t|l)/"),
    ("dropbox", r"(?:^|\.)dropboxusercontent\.com$", r""),
    ("icloud", r"^(?:www\.)?icloud\.com$", r"^/(?:attachment|iclouddrive)/"),
    ("proton_drive", r"^drive\.proton\.me$", r"^/urls/"),
    ("wetransfer", r"^we\.tl$", r""),
    ("wetransfer", r"^(?:www\.)?wetransfer\.com$", r"^/downloads/"),
    ("box", r"^(?:app\.)?box\.com$|\.app\.box\.com$", r"^/s/"),
    ("mega", r"^mega\.(?:nz|io)$", r"^/(?:file|folder)/"),
    ("zoho_workdrive", r"^workdrive\.zoho(?:external)?\.[a-z.]+$", r""),
    ("adobe", r"^(?:acrobat|documentcloud)\.adobe\.com$", r"^/(?:id|link)/"),
)
_CLOUD_FILE_LINKS = [(p, re.compile(h), re.compile(path)) for p, h, path in CLOUD_FILE_LINKS]
# Genuine share notifications pass SPF/DKIM/DMARC (they come from the provider), so
# attackers put the lure in the sharer's message or in the shared file itself.
CLOUD_SHARE_SENDERS = {
    "drive-shares-dm-noreply@google.com", "drive-shares-noreply@google.com", "comments-noreply@docs.google.com",
    "no-reply@sharepointonline.com", "no-reply@dropbox.com", "no-reply@dropboxmail.com",
    "noreply@wetransfer.com", "noreply@box.com",
}


def cloud_file_provider(url):
    """Provider name when the URL points at a shared cloud file or folder, else ""."""
    parsed = _safe_urlparse(normalize_url(url))
    host = (parsed.hostname or "").lower()
    return next((provider for provider, host_re, path_re in _CLOUD_FILE_LINKS
                 if host_re.search(host) and path_re.search(parsed.path or "/")), "")


def inspect_cloud_file_links(raw_or_message):
    """Cloud-hosted 'attachments' of one email: [{"provider", "url"}], gateway rewrites removed."""
    msg = _parse_email(raw_or_message)
    plain, markup = _get_email_body(msg)
    return [{"provider": provider, "url": url} for url in _find_urls(plain, markup)
            for provider in [cloud_file_provider(url)] if provider]


# BEC / callback indicators (Ch. 9.4). The corpora contain almost no BEC, so these are
# evidence for a rule layer, not model inputs; so are the cloud-file links above.
CONTENT_INDICATOR_NAMES = [
    "bec_secrecy_count", "bec_channel_switch_count", "bec_payment_change_count",
    "bec_gift_card_count", "callback_phone_count", "mail_merge_token_count",
    "cloud_file_link_count", "cloud_share_notification",
]
_CONTENT_PATTERNS = {
    "bec_secrecy_count": r"\b(?:keep (?:this|it) (?:confidential|between us|quiet|private)|"
                         r"(?:do not|don't) (?:tell|share|discuss|mention) (?:this|it|anyone|anybody|others)|"
                         r"confidential until)\b",
    "bec_channel_switch_count": r"\b(?:text me|whatsapp me|call me (?:on|at)|my (?:new|personal|private) "
                                r"(?:number|cell|phone|email)|reach me (?:on|at) my)\b",
    "bec_payment_change_count": r"\b(?:new (?:bank|account|banking|remittance) (?:details|information|info)|"
                                r"updated? (?:bank|remittance|payment|banking) (?:details|information)|"
                                r"change (?:of|in|to) (?:our )?(?:bank|account) details|wire (?:the )?(?:transfer|payment))\b",
    "bec_gift_card_count": r"\b(?:gift ?cards?|itunes cards?|google play cards?|steam cards?)\b",
    "mail_merge_token_count": r"%%[A-Z_]+%%|\{\{\s*\w+\s*\}\}|\[(?:FIRST_?NAME|EMAIL|NAME)\]|\$\{\w+\}",
}
_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")


def extract_content_indicators(msg):
    msg = _parse_email(msg)
    text = _deobfuscated_message_text(msg)[0]
    values = {name: float(len(re.findall(pattern, text, re.I))) for name, pattern in _CONTENT_PATTERNS.items()}
    values["callback_phone_count"] = float(len(_PHONE.findall(text))) if re.search(
        r"\b(?:call|phone|dial|contact (?:us|support))\b[^.\n]{0,80}\b(?:cancel|renew|subscription|refund|charged?|order)\b|"
        r"\b(?:cancel|renew|subscription|refund|charged?|order)\b[^.\n]{0,80}\b(?:call|phone|dial)\b", text, re.I) else 0.0
    values["cloud_file_link_count"] = float(len(inspect_cloud_file_links(msg)))
    sender = parseaddr(str(msg.get("From", "")))[1].lower()
    values["cloud_share_notification"] = float(sender in CLOUD_SHARE_SENDERS)
    return {name: values[name] for name in CONTENT_INDICATOR_NAMES}


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
    # "is_html" is only the gate for the HTML checks (an email without HTML parts gets
    # zeros from them), not a model input: legitimate training mail is almost all plain
    # text, so baseline_v5 XGBoost put 38% of its gain on "is it HTML". html_to_text_ratio
    # is out too: it is 0 without HTML and > 0 for all but 251 of 10,264 HTML test emails
    # (9.3% of the gain), and is_image_only already covers "picture, almost no text".
    "has_form_tag", "has_script_tag", "has_hidden_elements",
    "is_image_only",
    "num_attachments", "has_executable_attachment", "has_macro_attachment",
    "has_archive_attachment", "has_double_extension_attachment",
    "urgency_keyword_count", "sensitive_info_keyword_count",
    "brand_keyword_count", "generic_greeting", "reward_scam_keyword_count",
]

FEATURE_NAMES += ATTACHMENT_FEATURE_NAMES

# Track extraction failures; errors are raised rather than converted to zero vectors.
_extraction_stats = {"total": 0, "failed": 0}


def get_extraction_stats():
    return dict(_extraction_stats)


def reset_extraction_stats():
    _extraction_stats["total"] = 0
    _extraction_stats["failed"] = 0


def extract_engineered_features(raw_text):
    """Extract the ordered FEATURE_NAMES from the complete MIME-decoded message."""
    _extraction_stats["total"] += 1
    try:
        msg = _parse_email(raw_text)
        plain, markup = _get_email_body(msg)
        content, lowered = extract_content_stats_features(plain, markup, _content_subject(msg))
        merged = {}
        for d in (content, extract_url_features(plain, markup), extract_header_features(msg),
                  extract_html_features(markup), extract_attachment_features(msg),
                  extract_social_engineering_features(lowered)):
            merged.update(d)
        return [float(merged[name]) for name in FEATURE_NAMES]
    except Exception:
        _extraction_stats["failed"] += 1
        raise  # Do not silently train on a fabricated all-zero vector.


# Baseline (Doc2Vec + 10 classifiers) input: FEATURE_NAMES, then the header/link/
# attachment/HTML groups added for detection techniques. Text-obfuscation counts and
# BEC indicators stay out: in these corpora they mark the source, not phishing.
BASELINE_EXTRA_FEATURES = (
    ("_message_security", MESSAGE_SECURITY_FEATURE_NAMES), ("_link_features", LINK_FEATURE_NAMES),
    ("_attachment_payload", ATTACHMENT_PAYLOAD_FEATURE_NAMES),
    ("_html_features", HTML_SECURITY_FEATURE_NAMES + HTML_PAYLOAD_FEATURE_NAMES))
BASELINE_FEATURE_NAMES = FEATURE_NAMES + [name for _, names in BASELINE_EXTRA_FEATURES for name in names]
assert len(set(BASELINE_FEATURE_NAMES)) == len(BASELINE_FEATURE_NAMES)


# Decisive attachment gates (verdict cascade of the Phishing Email Investigation Guide).
# A model trained on email labels cannot learn these: almost no training email carries
# them, so their learned weight is ~0. Each rule is a static indicator that legitimate
# mail practically never contains; it flags the email on its own and leaves the model's
# score unchanged. rule -> BASELINE_FEATURE_NAMES entry; fires when the value is > 0.
# Measured 2026-10-25 on every email with an attachment (legitimate: only SpamAssassin
# ham, 119 emails, carries attachments; Enron maildir and the CSVs have none): each rule
# below fired on 0 of them. Not rules: has_executable_attachment (5/119 legitimate),
# script/form and PDF active content (common in legitimate HTML/PDF files, and the model
# has 200+ phishing examples to learn them from).
ATTACHMENT_RULES = {
    "disguised_executable": "attachment_disguised_executable_count",
    "embedded_executable": "attachment_embedded_executable_count",
    "double_extension": "has_double_extension_attachment",
    "bidi_filename": "attachment_bidi_filename_count",
    "vba_autoexec": "attachment_vba_autoexec_count",
    "vba_stomping": "attachment_vba_stomping_count",
    "xlm_macro": "attachment_xlm_macro_count",
    "lnk_command": "attachment_lnk_command_count",
    "html_smuggling": "attachment_html_smuggling_count",
    "disk_image": "attachment_disk_image_count",
    "onenote_embedded": "attachment_onenote_embedded_count",
    "password_archive_in_body": "attachment_password_archive_in_body",
    # Device profiles are installed through MDM, not mailed by strangers (Phishing Pot: 37).
    "config_profile": "attachment_config_profile_count",
    # Magika: a document/picture name or MIME type over HTML, script or binary content.
    "disguised_active_content": "attachment_disguised_active_count",
    # Not an attachment, but the same kind of gate: mail clients never run scripts, so a
    # legitimate sender has no reason to obfuscate one (packer/JSFuck/aaencode/obfuscator.io,
    # or two of: escapes, char-code arrays, string splitting, encoded blobs, decode-then-run).
    # Measured 2026-11-02 on all 1,008 legitimate HTML emails (SpamAssassin ham, Zenodo CSVs): 0.
    "obfuscated_script": "html_js_obfuscated",
}


def attachment_rule_hits(values):
    """Names of the ATTACHMENT_RULES that fire for one email's {feature name: value}."""
    return [rule for rule, name in ATTACHMENT_RULES.items() if values[name] > 0]


def baseline_feature_vector(row):
    """Ordered BASELINE_FEATURE_NAMES from a features-stage row of pipeline_cache."""
    return [*map(float, row["_features"]),
            *(float(row[column][name]) for column, names in BASELINE_EXTRA_FEATURES for name in names)]


def assess_attachment_rules(raw_text):
    """ATTACHMENT_RULES that fire for one raw email (for a web demo, next to the model score)."""
    return attachment_rule_hits(dict(zip(BASELINE_FEATURE_NAMES, extract_baseline_features(raw_text))))


def extract_baseline_features(raw_text):
    """BASELINE_FEATURE_NAMES for one raw email; a web demo must use this, not FEATURE_NAMES."""
    msg = _parse_email(raw_text)
    _, markup = _get_email_body(msg)
    return baseline_feature_vector({
        "_features": extract_engineered_features(msg),
        "_message_security": extract_message_security_features(msg),
        "_link_features": extract_link_features(msg),
        "_attachment_payload": extract_attachment_payload_features(msg),
        "_html_features": extract_html_check_features(markup)})


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
    msg._pipeline_attachment_hashes = sorted({digest for _, digest in attachments})
    content = {"subject": _normalize(str(msg.get("Subject", ""))), "plain": _normalize(plain),
               "html": markup.strip(), "attachments": sorted(attachments)}
    if not plain and not markup and not attachments:
        content["raw"] = raw_text.hex() if isinstance(raw_text, bytes) else str(raw_text)
    # Only added for anomalous headers, so ordinary emails keep their previous key.
    header_attack = _header_attack_identity(msg)
    if header_attack is not None:
        content["header_attack"] = header_attack
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _decode_header_value(value):
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
    return "".join(decoded)


def _parse_email(raw):
    if isinstance(raw, email.message.Message):
        return raw
    if isinstance(raw, bytes):
        msg = email.message_from_bytes(_normalize_redactions(raw), policy=policy.compat32)
    elif isinstance(raw, str):
        if "[" in raw:
            raw = _normalize_redactions(raw.encode("utf-8", "surrogateescape")).decode("utf-8", "surrogateescape")
        msg = email.message_from_string(raw, policy=policy.compat32)
    else:
        raise TypeError("Email must be str or bytes")
    # Keep every raw occurrence for header-security features before decoding.
    msg._pipeline_raw_headers = {name: [str(v) for v in (msg.get_all(name) or [])]
                                 for name in _RAW_HEADER_NAMES}
    # Decode display headers without invoking the strict AddressHeader parser.
    # MIME headers remain untouched so payload/charset decoding stays accurate.
    for name in ("Subject", "From", "To", "Cc", "Reply-To", "Date"):
        value = msg.get(name)
        if value is None:
            continue
        msg.replace_header(name, _decode_header_value(value))
    return msg


def _normalize(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().lower()


@lru_cache(maxsize=1)
def _english_stopwords():
    # Negations carry meaning ("do not click"), so they stay in the text.
    return NLTK_ENGLISH_STOPWORDS - {"no", "not", "nor", "never"}


# The nltk 3.10.3 "english" stopwords corpus, copied verbatim so the cleaned text is
# unchanged after nltk was removed (unfixed CVE-2026-81726, 2026-10-26).
NLTK_ENGLISH_STOPWORDS = frozenset((
    "a", "about", "above", "after", "again", "against", "ain", "all", "am", "an", "and", "any", "are", "aren",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
    "can", "couldn", "couldn't", "d", "did", "didn", "didn't", "do", "does", "doesn", "doesn't", "doing", "don",
    "don't", "down", "during", "each", "few", "for", "from", "further", "had", "hadn", "hadn't", "has", "hasn",
    "hasn't", "have", "haven", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is",
    "isn", "isn't", "it", "it'd", "it'll", "it's", "its", "itself", "just", "ll", "m", "ma", "me", "mightn",
    "mightn't", "more", "most", "mustn", "mustn't", "my", "myself", "needn", "needn't", "no", "nor", "not",
    "now", "o", "of", "off", "on", "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over",
    "own", "re", "s", "same", "shan", "shan't", "she", "she'd", "she'll", "she's", "should", "should've",
    "shouldn", "shouldn't", "so", "some", "such", "t", "than", "that", "that'll", "the", "their", "theirs",
    "them", "themselves", "then", "there", "these", "they", "they'd", "they'll", "they're", "they've", "this",
    "those", "through", "to", "too", "under", "until", "up", "ve", "very", "was", "wasn", "wasn't", "we",
    "we'd", "we'll", "we're", "we've", "were", "weren", "weren't", "what", "when", "where", "which", "while",
    "who", "whom", "why", "will", "with", "won", "won't", "wouldn", "wouldn't", "y", "you", "you'd", "you'll",
    "you're", "you've", "your", "yours", "yourself", "yourselves"))


def deduplicate_emails(data, report_path="label_conflicts.csv", return_audit=False):
    data = data.reset_index(drop=True).copy()
    audit_columns = [c for c in ('RecordId', 'Source', 'Location', 'LabelKind', 'LabelBasis', 'Class') if c in data]
    audit = data[audit_columns].copy()
    audit['Disposition'] = 'selected'
    missing = data.Text.isna() | data.Class.isna()
    audit.loc[missing, 'Disposition'] = 'unknown_label_or_missing_content'
    data = data.loc[~missing].copy()
    if not data.Class.isin([0, 1]).all():
        raise ValueError("Dataset contains labels other than 0/1")
    if '_dedup_key' not in data:
        data["_dedup_key"] = data.Text.apply(compute_dedup_key)
    # nunique ignores missing labels: unknown copies are not negative examples.
    conflicts = data.groupby("_dedup_key").Class.nunique()
    mask = data._dedup_key.isin(set(conflicts[conflicts > 1].index))
    columns = [c for c in ('RecordId', "Class", "_dedup_key", "Source", "Location", "LabelKind", "OriginalLabel", 'LabelBasis')
               if c in data]
    data.loc[mask, columns].to_csv(report_path, index_label="loaded_row")
    audit.loc[data.index[mask], 'Disposition'] = 'conflicting_labels'
    if mask.any():
        print(f"Excluded {int(mask.sum())} conflicting-label rows; see {report_path}")
    data = data.loc[~mask]
    before = len(data)
    # Retain the explicitly phishing-labelled copy when the same positive email
    # also occurs in a CSV with an unspecified numeric positive label.
    if "LabelKind" in data:
        # A synthetic copy of a Nazario email yields to the original; it outranks
        # spam copies so the label-scope step does not discard it with them.
        data = data.assign(_label_rank=data.LabelKind.map(
            {"legitimate": 0, "phishing": 0, "malspam": 0, "malicious_synthetic": 1, "spam": 2,
             "positive_unspecified": 3}).fillna(4))
        data = data.sort_values("_label_rank", kind="stable").drop(columns="_label_rank")
    else:
        data = data.sort_values("Class", kind="stable", na_position="last")
    duplicates = data.duplicated('_dedup_key')
    audit.loc[data.index[duplicates], 'Disposition'] = 'duplicate_content'
    data = data.loc[~duplicates].reset_index(drop=True)
    print(f"Removed {before - len(data)} exact duplicates; {len(data)} emails remain")
    return (data, audit) if return_audit else data


def _simhash(text):
    import numpy as np
    text = re.sub(r"\d+", "0", URL_REGEX.sub(" URL ", text))
    words = re.findall(r"\w+", text)
    if len(words) < 20:
        return None
    shingles = {" ".join(words[i:i + 3]) for i in range(len(words) - 2)}
    values = np.fromiter((int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), 'big')
                          for s in shingles), dtype=np.uint64, count=len(shingles))
    counts = np.zeros(64, dtype=np.int64)
    # Vectorize bit voting in bounded chunks; preserve original >=0 tie rule.
    for start in range(0, len(values), 4096):
        packed = values[start:start + 4096].astype('<u8', copy=False).view(np.uint8)
        counts += np.unpackbits(packed, bitorder='little').reshape(-1, 64).sum(axis=0).astype(np.int64)
    return sum(1 << bit for bit, count in enumerate(counts) if 2 * count >= len(values))


def group_signature(body, exact):
    """(body hash, SimHash or None) that group_email_variants compares; exact is the dedup key."""
    return hashlib.sha256((body or exact).encode()).hexdigest(), _simhash(body)


def group_email_variants(data, group_attachments=False):
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
    attachment_owners = {}
    # The identity stage stores only (body hash, SimHash), not the body text: ~800k bodies
    # did not fit the sandbox memory limit.
    prepared = zip(data['_group_key'], data['_simhash']) if '_group_key' in data else None
    for i, (raw, exact) in enumerate(zip(data.Text, data._dedup_key)):
        if group_attachments:
            digests = data['_attachment_hashes'].iloc[i] if '_attachment_hashes' in data else []
            for digest in digests:
                if digest in attachment_owners:
                    union(i, attachment_owners[digest])
                else:
                    attachment_owners[digest] = i
        if prepared is not None:
            body_key, fingerprint = next(prepared)
            # pandas may hold missing fingerprints as None or NaN and present ones as numpy ints.
            fingerprint = None if fingerprint is None or fingerprint != fingerprint else int(fingerprint)
        else:
            msg = _parse_email(raw)
            plain, markup = _get_email_body(msg)
            body = _normalize("\n".join(dict.fromkeys(p for p in (plain, _strip_html(markup)) if p.strip())))
            body_key, fingerprint = group_signature(body, exact)
        if body_key in bodies:
            union(i, bodies[body_key])
            continue
        bodies[body_key] = i
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
    import numpy as np
    labels = data.Class.to_numpy()
    overall_mean = labels.mean()
    for train_idx, test_idx in splitter.split(data, labels, data._group):
        if len(np.unique(labels[train_idx])) != 2 or len(np.unique(labels[test_idx])) != 2:
            continue
        score = abs(len(test_idx) / len(data) - test_size) + abs(labels[test_idx].mean() - overall_mean)
        if best is None or score < best[0]:
            best = score, train_idx, test_idx
    if best is None:
        raise ValueError("Cannot put both classes in independent train/test groups; more distinct emails are needed")
    _, train_idx, test_idx = best
    train, test = data.iloc[train_idx], data.iloc[test_idx]
    assert set(train._group).isdisjoint(test._group)
    return train.copy(), test.copy()


def split_train_validation_test(data, validation_size=0.2, test_size=0.2, seed=42):
    """Approximate 60/20/20 split. Groups are indivisible and may vary in size."""
    if not (0 < validation_size < 1 and 0 < test_size < 1 and validation_size + test_size < 1):
        raise ValueError("Invalid validation/test fractions")
    development, test = split_email_data(data, test_size=test_size, seed=seed)
    train, validation = split_email_data(
        development, test_size=validation_size / (1 - test_size), seed=seed + 1)
    for left, right in ((train, validation), (train, test), (validation, test)):
        assert set(left._group).isdisjoint(right._group)
        assert set(left._dedup_key).isdisjoint(right._dedup_key)
    return train, validation, test


def inspect_email_file(path):
    """Convenience entry point for checking a local .eml without executing files."""
    from pathlib import Path
    return inspect_email_attachments(Path(path).read_bytes())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Static attachment indicators; not a malware-free certificate")
    parser.add_argument("email_file", help="Path to a raw .eml email")
    args = parser.parse_args()
    from pathlib import Path
    raw = Path(args.email_file).read_bytes()
    result = {"attachments": inspect_email_attachments(raw), "attachment_rules": assess_attachment_rules(raw)}
    print(json.dumps(result, ensure_ascii=True, indent=2))
