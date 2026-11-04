# #### download_nazario.py
#
# Tải toàn bộ dataset phishing của Jose Nazario tại
# https://monkey.org/~jose/phishing/ về Dataset/phishing/, sẵn sàng cho
# load_data.py đọc (load_data.py đọc raw email không phân biệt file có
# đuôi ".mbox" hay không, và tự tách nếu 1 file là mbox gộp nhiều email).
#
# Cách dùng:
#   pip install requests beautifulsoup4
#   python download_nazario.py
#   python download_nazario.py --out-dir ./Dataset/phishing --only-recent 5
#
# Mặc định script sẽ:
#   1. Lấy danh sách file THẬT TỪ trang index (không hardcode cứng), để tự
#      cập nhật nếu tác giả thêm file mới (phishing-2026...).
#   2. Bỏ qua LICENSE.txt / README.txt / thư mục cha (không phải data).
#   3. Bỏ qua file đã tải đủ dung lượng (so khớp Content-Length) -> chạy
#      lại script không tải trùng.
#   4. Tải với streaming + retry, in tiến độ.

import argparse
import os
import re
import sys
import time

import requests

INDEX_URL = "https://monkey.org/~jose/phishing/"
SKIP_NAMES = {"LICENSE.txt", "README.txt"}


def list_remote_files(index_url=INDEX_URL, timeout=30):
    """
    Parse trang index (Apache directory listing) để lấy danh sách file thật
    đang có trên server, thay vì hardcode cứng danh sách năm.
    """
    resp = requests.get(index_url, timeout=timeout)
    resp.raise_for_status()
    html = resp.text

    hrefs = re.findall(r'href="([^"]*)"', html)
    files = []
    for href in hrefs:
        # Bỏ link sort-column ("?C=N;O=D"), link cha ("/~jose/", "../"), và
        # icon/asset (không xảy ra ở đây vì regex chỉ bắt href, nhưng vẫn
        # phòng thủ thêm).
        if not href or href.startswith('?') or href.startswith('..'):
            continue
        if href.startswith('/') and not href.startswith('/~jose/phishing'):
            continue
        name = href.rstrip('/').split('/')[-1]
        if not name or name in SKIP_NAMES:
            continue
        files.append(name)

    # loại trùng, giữ thứ tự
    seen = set()
    ordered = []
    for f in files:
        if f not in seen:
            seen.add(f)
            ordered.append(f)
    return ordered


# Danh sách dự phòng (đúng tại thời điểm viết script này), dùng khi không
# fetch được trang index (offline, đổi cấu trúc HTML...):
FALLBACK_FILES = [
    "20051114.mbox",
    "phishing-2015", "phishing-2016", "phishing-2017", "phishing-2018",
    "phishing-2019", "phishing-2020", "phishing-2021", "phishing-2022",
    "phishing-2023", "phishing-2024", "phishing-2025",
    "phishing0.mbox", "phishing1.mbox", "phishing2.mbox", "phishing3.mbox",
    "private-phishing4.mbox",
]


def human_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def download_file(url, dest_path, timeout=30, chunk_size=1 << 20, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            with requests.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))

                if os.path.exists(dest_path) and total and os.path.getsize(dest_path) == total:
                    print(f"  [skip] {os.path.basename(dest_path)} đã tải đủ ({human_size(total)})")
                    return True

                downloaded = 0
                tmp_path = dest_path + ".part"
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded / total * 100
                            print(f"\r  [{os.path.basename(dest_path)}] "
                                  f"{human_size(downloaded)}/{human_size(total)} ({pct:.0f}%)",
                                  end="", flush=True)
                        else:
                            print(f"\r  [{os.path.basename(dest_path)}] {human_size(downloaded)}",
                                  end="", flush=True)
                print()
                os.replace(tmp_path, dest_path)
                return True
        except requests.RequestException as e:
            print(f"\n  Lỗi tải {url} (lần {attempt}/{max_retries}): {e}")
            time.sleep(2 * attempt)

    print(f"  [FAIL] Không tải được {url} sau {max_retries} lần thử.")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Tải toàn bộ dataset phishing Nazario (monkey.org/~jose/phishing/)")
    parser.add_argument("--out-dir", default="./Dataset/phishing",
                         help="Thư mục lưu file (mặc định: ./Dataset/phishing)")
    parser.add_argument("--only-recent", type=int, default=None,
                         help="Chỉ tải N file mới nhất theo thứ tự liệt kê trên trang "
                              "(bỏ qua nếu muốn tải hết, dataset đầy đủ khá nặng, ~150MB)")
    parser.add_argument("--index-url", default=INDEX_URL)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    try:
        files = list_remote_files(args.index_url)
        if not files:
            raise ValueError("Danh sách rỗng")
        print(f"Lấy được {len(files)} file từ {args.index_url}")
    except Exception as e:
        print(f"Không lấy được danh sách từ trang index ({e}), dùng danh sách dự phòng.")
        files = FALLBACK_FILES

    if args.only_recent:
        files = files[-args.only_recent:]

    print(f"Sẽ tải {len(files)} file vào '{args.out_dir}':")
    for f in files:
        print("  -", f)
    print()

    ok, fail = 0, 0
    for fname in files:
        url = args.index_url.rstrip('/') + '/' + fname
        dest = os.path.join(args.out_dir, fname)
        print(f"Tải {fname} ...")
        if download_file(url, dest):
            ok += 1
        else:
            fail += 1

    print(f"\nHoàn tất: {ok} file OK, {fail} file lỗi.")
    print(f"Dữ liệu đã nằm trong '{args.out_dir}' -- load_data.py có thể đọc thẳng "
          f"(không cần đổi tên/đuôi file gì thêm).")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
