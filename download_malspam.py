# #### download_malspam.py
#
# Tải email malspam thật (thư mang file độc) từ https://www.malware-traffic-analysis.net/
# về Dataset/malspam/, để model học được các feature attachment (macro, LNK, ISO,
# HTML smuggling...) mà các corpus khác gần như không có.
#
# AN TOÀN:
#   - Chỉ lưu file zip CÓ MẬT KHẨU của tác giả, giữ nguyên dạng mã hóa trên đĩa.
#     load_data.load_data_malspam() giải nén .eml trong RAM, không ghi ra đĩa, không
#     chạy attachment. Đừng tự giải nén các file này trên Windows.
#   - Mật khẩu theo trang "about" của site: infected_YYYYMMDD (ngày đăng bài); bài cũ
#     dùng "infected". Vì loader suy mật khẩu từ ngày ở đầu tên file, giữ nguyên tên gốc.
#   - Zip được tải vào RAM và chỉ ghi ra đĩa khi danh mục của nó (tên file trong zip
#     không bị mã hóa) có ít nhất một .eml, đúng tiêu chí loader đọc. Zip chỉ chứa
#     malware rời, attachment, pcap... bị bỏ mà không chạm đĩa và được ghi vào skipped.csv.
#   - Bỏ ngay theo tên: pcap, IOC, tracker .csv/.txt, và zip email phishing (không phải
#     malspam; loader gán mọi zip ở đây nhãn malspam).
#
# Cách dùng:
#   python download_malspam.py                        # mọi năm
#   python download_malspam.py --years 2023 2024 2025 --delay 1.5
#
# Chạy lại không tải trùng: zip đã có trên đĩa hoặc đã nằm trong skipped.csv được bỏ qua
# mà không gửi request. Danh sách file + SHA-256 ghi ở Dataset/malspam/manifest.csv để
# biết chính xác dữ liệu đã dùng.

import argparse
import csv
import hashlib
import io
import os
import re
import sys
import time
import zipfile
from datetime import date

import requests

SITE = "https://www.malware-traffic-analysis.net"
USER_AGENT = "Mozilla/5.0 (academic phishing-detection research; IAP491)"
# Ứng viên theo tên; nội dung zip mới là tiêu chí cuối cùng (phải có .eml).
EMAIL_ZIP = re.compile(r"\.eml|e-?mail|malspam", re.I)
# Chắc chắn không phải email malspam, khỏi tải. Không loại "malware-from"/"artifacts":
# nhiều zip như "email-and-malware-from-..." có chứa email.
NOT_EMAIL = re.compile(r"pcap|ioc|tracker|\.csv\.zip$|\.txt\.zip$|phish", re.I)
MAX_MEMBER = 64 * 1024 * 1024  # Giống giới hạn của load_data._iter_malspam_rows.
MANIFEST_FIELDS = ["year", "post", "title", "file", "bytes", "sha256"]
SKIPPED_FIELDS = ["year", "post", "file", "reason"]


def fetch(session, url, timeout=30, retries=6):
    # DNS mạng nhà chập chờn (NameResolutionError kéo dài vài phút): chờ tăng dần, tối đa ~2 phút.
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 404:
                print(f"  404 {url}")
                return None
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            print(f"  Lỗi {url} (lần {attempt}/{retries}): {exc}")
            time.sleep(min(120, 5 * 2 ** (attempt - 1)))
    return None


def list_posts(session, year):
    """URL các bài trong một năm, theo trang index của năm đó."""
    response = fetch(session, f"{SITE}/{year}/index.html")
    if response is None:
        return []
    links = re.findall(r'href="(\d{2}/\d{2}/index\d*\.html)"', response.text)
    return [f"{SITE}/{year}/{link}" for link in dict.fromkeys(links)]


def is_candidate(name):
    return bool(EMAIL_ZIP.search(name)) and not NOT_EMAIL.search(name)


def email_zips(session, post_url):
    response = fetch(session, post_url)
    if response is None:
        return "", []
    title = re.search(r"<title>(.*?)</title>", response.text, re.I | re.S)
    names = re.findall(r'href="([^"/]+\.zip)"', response.text)
    base = post_url.rsplit("/", 1)[0]
    chosen = [n for n in dict.fromkeys(names) if is_candidate(n)]
    return (title.group(1).strip() if title else ""), [f"{base}/{n}" for n in chosen]


def eml_check(content):
    """None nếu zip có ít nhất một .eml loader đọc được, ngược lại là lý do bỏ.
    Chỉ đọc danh mục zip (không giải mã, không giải nén)."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
    except zipfile.BadZipFile:
        return "not a zip file"
    if any(m.filename.lower().endswith(".eml") and m.file_size <= MAX_MEMBER for m in members):
        return None
    return f"no .eml member ({len(members)} other files)"


def download(session, url, path):
    """Tải zip vào RAM; chỉ ghi ra path khi có .eml. Trả về None nếu đã lưu, hoặc lý do bỏ."""
    response = fetch(session, url, timeout=120)
    if response is None:
        return "download failed"
    reason = eml_check(response.content)
    if reason:
        return reason
    tmp = path + ".part"
    with open(tmp, "wb") as handle:
        handle.write(response.content)
    os.replace(tmp, path)  # File đích chỉ xuất hiện khi đã ghi đủ, nên "đã có" nghĩa là hoàn chỉnh.
    return None


def read_csv(path, key):
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as handle:
        return {row[key]: row for row in csv.DictReader(handle)}


def write_csv(path, fields, rows):
    tmp = path + ".part"
    with open(tmp, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row["file"]))
    os.replace(tmp, path)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    # In tiếng Việt khi output bị chuyển hướng (console Windows mặc định cp1252).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Tải email malspam (zip có mật khẩu) từ malware-traffic-analysis.net")
    parser.add_argument("--out-dir", default="./Dataset/malspam")
    parser.add_argument("--years", type=int, nargs="*", default=list(range(2013, date.today().year + 1)))
    parser.add_argument("--delay", type=float, default=1.0, help="Giây chờ giữa hai request (lịch sự với site)")
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    manifest_path = os.path.join(args.out_dir, "manifest.csv")
    skipped_path = os.path.join(args.out_dir, "skipped.csv")
    # Gộp với các lần chạy trước (ví dụ --years 2018 2019 sau khi bị ngắt giữa chừng).
    manifest = read_csv(manifest_path, "file")
    skipped = read_csv(skipped_path, "file")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    saved = kept = dropped = 0
    for year in args.years:
        posts = list_posts(session, year)
        print(f"{year}: {len(posts)} bài", flush=True)
        time.sleep(args.delay)
        for post in posts:
            title, zips = email_zips(session, post)
            time.sleep(args.delay)
            for url in zips:
                name = url.rsplit("/", 1)[-1]
                key = f"{year}/{name}"
                folder = os.path.join(args.out_dir, str(year))
                path = os.path.join(folder, name)
                if key in skipped:
                    continue
                if os.path.exists(path):
                    kept += 1
                else:
                    os.makedirs(folder, exist_ok=True)
                    reason = download(session, url, path)
                    time.sleep(args.delay)
                    if reason:
                        dropped += 1
                        print(f"  bỏ {name}: {reason}", flush=True)
                        if reason != "download failed":  # Lỗi mạng thì lần sau thử lại.
                            skipped[key] = {"year": year, "post": post, "file": key, "reason": reason}
                        continue
                    saved += 1
                    print(f"  {name}", flush=True)
                manifest[key] = {"year": year, "post": post, "title": title, "file": key,
                                 "bytes": os.path.getsize(path), "sha256": sha256_file(path)}
        # Ghi sau mỗi năm để bị ngắt vẫn giữ được phần đã làm.
        write_csv(manifest_path, MANIFEST_FIELDS, manifest.values())
        write_csv(skipped_path, SKIPPED_FIELDS, skipped.values())
    print(f"Xong: tải mới {saved}, đã có {kept}, bỏ {dropped} zip lần này; "
          f"manifest có {len(manifest)} file, skipped.csv có {len(skipped)} file trong {args.out_dir}")


if __name__ == "__main__":
    main()
