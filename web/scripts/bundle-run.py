"""Đóng gói một run đã train vào web/model/ để web/ chạy được khi chép riêng.

Chỉ dùng thư viện chuẩn, chạy bằng Python nào cũng được:

    python web/scripts/bundle-run.py --run runs/2026-11-02_baseline_v6

Chép run_manifest.json và mọi artifact trong manifest (kiểm SHA-256 ngay lúc chép) vào
web/model/<run-id>/. Mọi thứ được ghi vào một thư mục tạm trong web/model/ rồi mới đổi tên
vào chỗ, nên lỗi lúc chép (hash sai, thiếu file) không làm đổi web/model/. Run v6 không dùng
NLTK nên không chép dữ liệu NLTK; thư mục web/model/nltk_data/ cũ (nếu có) được giữ nguyên.
--run tương đối tính từ thư mục hiện hành.
"""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = WEB_ROOT / "model"
# Cùng vị trí manifest mà web/backend/adapter.py đọc.
MANIFEST = "dumped_models/classification/run_manifest.json"


class BundleError(Exception):
    pass


class RestoreError(BundleError):
    """Không đổi tên được run cũ về chỗ cũ: web/model/ đã bị thay đổi."""


def copy_verified(source, target, expected):
    """Chép từng khối và băm đúng các byte đã chép; sai hash thì báo lỗi."""
    digest = hashlib.sha256()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(source, "rb") as reader, open(target, "wb") as writer:
        for block in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(block)
            writer.write(block)
    if digest.hexdigest() != expected:
        raise BundleError(f"Hash không khớp manifest: {source}")


def stage_run(run, staging):
    manifest_path = run / MANIFEST
    if not manifest_path.is_file():
        raise BundleError(f"Không có manifest: {manifest_path}")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("status") != "complete" or manifest.get("schema_version") != 2:
        raise BundleError("Run chưa hoàn tất hoặc không phải schema 2")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise BundleError("Manifest không có danh sách artifact")
    destination = staging / run.name
    for relative, digest in artifacts.items():
        # Run train trên Windows có thể ghi khoá bằng "\\"; adapter cũng chuẩn hoá như vậy.
        relative = relative.replace("\\", "/")
        source = (run / relative).resolve()
        if run not in source.parents:
            raise BundleError(f"Artifact nằm ngoài run: {relative}")
        if not source.is_file():
            raise BundleError(f"Thiếu artifact: {relative}")
        copy_verified(source, destination / relative, digest)
    # Ghi đúng các byte manifest đã đọc; adapter dùng SHA-256 của chúng làm định danh release.
    (destination / MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    (destination / MANIFEST).write_bytes(manifest_bytes)
    if (run / MANIFEST).read_bytes() != manifest_bytes:
        raise BundleError("Manifest thay đổi trong lúc chép")
    return manifest_bytes


def replace(staged, final):
    """Đổi tên bản mới vào chỗ; bản cũ (nếu có) được đổi tên ra trước rồi mới xoá."""
    previous = None
    if final.exists():
        previous = final.with_name(f".old-{final.name}-{uuid.uuid4().hex}")
        final.rename(previous)
    try:
        staged.rename(final)
    except OSError:
        if previous is not None:
            try:
                previous.rename(final)
            except OSError:
                raise RestoreError(f"không khôi phục được run cũ, bản cũ nằm ở {previous}") from None
        raise
    if previous is not None:
        shutil.rmtree(previous, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Chép một run đã kiểm hash vào web/model/")
    parser.add_argument("--run", type=Path, required=True, help="Thư mục run, ví dụ runs/2026-11-02_baseline_v6")
    args = parser.parse_args(argv)
    # Console Windows có thể không mã hoá được tiếng Việt; không để việc in làm hỏng lệnh.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    run = args.run.resolve()
    if not run.is_dir():
        print(f"Không tìm thấy run: {run}", file=sys.stderr)
        return 1
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    if run.name == "nltk_data" or run.name.startswith("."):
        print(f"Tên run không dùng được: {run.name}", file=sys.stderr)
        return 1
    staging = Path(tempfile.mkdtemp(prefix=".bundle-", dir=MODEL_ROOT))
    try:
        manifest_bytes = stage_run(run, staging)
        replace(staging / run.name, MODEL_ROOT / run.name)
    except RestoreError as error:
        print(f"Đóng gói thất bại ({error}); kiểm tra lại web/model/", file=sys.stderr)
        return 1
    except (BundleError, OSError, ValueError) as error:
        print(f"Đóng gói thất bại ({error}); web/model/ không đổi", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"Đã đóng gói {run.name} vào {MODEL_ROOT / run.name}")
    print(f"manifest_sha256 = {hashlib.sha256(manifest_bytes).hexdigest()}")
    print(f"Web phục vụ run này khi RUN_PATH (web/backend/policy.py) là model/{run.name} "
          "hoặc IAP_WEB_RUN_PATH trỏ tới thư mục trên.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
