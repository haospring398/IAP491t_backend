"""Administrator-provisioned, digest-pinned release delivery; no ML imports here."""
import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import time
from dataclasses import dataclass
from importlib.metadata import version, requires
from pathlib import Path
from urllib.parse import urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from web.backend.policy import ROOT, RUN_ID

ARTIFACTS = ("model_dbow.pkl", "feature_scaler.pkl", "XGBoost.pkl")
MEMBERS = ("release.json", "manifest.json") + ARTIFACTS
MAX_ARCHIVE_BYTES = 384 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_DOWNLOAD_SECONDS = 105
CODE_FILES = (
    "preprocess.py", "artifact_store.py", "web/__init__.py", "web/backend/__init__.py", "web/backend/adapter.py",
    "web/backend/service.py", "web/backend/policy.py", "web/backend/cloud_release.py",
    "web/backend/cloud_worker.py", "vercel_app.py", "app.py", "pyproject.toml", "uv.lock",
    ".python-version", "vercel.json", "web/contracts/analysis.schema.json",
    "web/contracts/transport-policy.json", "web/contracts/transport-policy.schema.json",
)
PACKAGES = ("numpy", "scipy", "gensim", "scikit-learn", "xgboost", "nltk",
            "beautifulsoup4", "textblob", "fastapi", "uvicorn", "python-multipart", "jsonschema", "packaging")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
PRIVATE_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62})\.private\.blob\.vercel-storage\.com\Z")


class ReleaseFailure(ValueError):
    """A safe stage, never a URL, credential, path or raw upstream exception."""
    def __init__(self, stage):
        self.stage = stage
        super().__init__(stage)


@dataclass(frozen=True)
class ReleaseConfig:
    url: str
    token: str
    digest: str

    @classmethod
    def from_environment(cls):
        return cls.validate(os.environ.get("MODEL_BLOB_URL", ""),
                            os.environ.get("BLOB_READ_WRITE_TOKEN", ""),
                            os.environ.get("MODEL_RELEASE_SHA256", ""))

    @classmethod
    def validate(cls, url, token, digest):
        try:
            parts = urlsplit(url)
            if (parts.scheme != "https" or not PRIVATE_HOST.fullmatch(parts.netloc) or
                    parts.username or parts.password or parts.port is not None or
                    not parts.path.startswith("/") or parts.path == "/" or parts.query or parts.fragment or
                    any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in url) or
                    "\\" in url or any(p in (".", "..") for p in unquote(parts.path).split("/")) or
                    not DIGEST.fullmatch(digest) or not token or
                    not all(33 <= ord(c) <= 126 for c in token)):
                raise ValueError()
        except Exception:
            raise ReleaseFailure("CLOUD_CONFIGURATION") from None
        return cls(url, token, digest)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_hashes(root=ROOT):
    """Canonical UTF-8/LF source bytes survive Windows Git line-ending conversion."""
    return {name: hashlib.sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in CODE_FILES}


def package_versions():
    return {name: version(name) for name in PACKAGES}


def verify_locked_environment(root=ROOT, roots=PACKAGES):
    """Check installed runtime dependency closure, including platform markers."""
    import tomllib
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    locked = {}
    for package in lock["package"]:
        if "version" in package:
            locked.setdefault(canonicalize_name(package["name"]), set()).add(package["version"])
    installed, pending = {}, list(roots)
    while pending:
        name = canonicalize_name(pending.pop())
        if name in installed:
            continue
        value = version(name)
        if value not in locked.get(name, set()):
            raise ValueError("Installed dependency differs from lock")
        installed[name] = value
        for text in requires(name) or ():
            requirement = Requirement(text)
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            if not requirement.specifier.contains(version(requirement.name), prereleases=True):
                raise ValueError("Incompatible installed dependency")
            pending.append(requirement.name)
    return installed


def write_archive(fileobj, directory):
    """Canonical TAR bytes also let us bind an extracted cache to its digest."""
    with tarfile.open(fileobj=fileobj, mode="w|", format=tarfile.USTAR_FORMAT) as archive:
        for name in MEMBERS:
            path = directory / name
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = path.stat().st_size, 0o600, 0
            with path.open("rb") as handle:
                archive.addfile(info, handle)


def archive_digest(directory):
    class DigestWriter:
        def __init__(self):
            self.digest = hashlib.sha256()
        def write(self, chunk):
            self.digest.update(chunk)
            return len(chunk)
    writer = DigestWriter()
    write_archive(writer, directory)
    return writer.digest.hexdigest()


def cache_root():
    return Path(tempfile.gettempdir()) / "iap-model-release-v1"


def remove_partial(config):
    """Only the digest's own bounded staging directory is eligible for removal."""
    root = cache_root()
    if root.is_symlink() or not DIGEST.fullmatch(config.digest):
        raise ReleaseFailure("CLOUD_INTEGRITY")
    path = root / (config.digest + ".partial")
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        if path.resolve().parent != root.resolve():
            raise ReleaseFailure("CLOUD_INTEGRITY")
        shutil.rmtree(path)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReleaseFailure("CLOUD_DOWNLOAD")


class BoundedStream:
    def __init__(self, stream, deadline):
        self.stream, self.deadline = stream, deadline
        self.digest, self.size = hashlib.sha256(), 0

    def read(self, size=-1):
        if time.monotonic() >= self.deadline:
            raise ReleaseFailure("CLOUD_DOWNLOAD")
        chunk = self.stream.read(min(size if size >= 0 else 1024 * 1024, 1024 * 1024))
        self.size += len(chunk)
        if self.size > MAX_ARCHIVE_BYTES:
            raise ReleaseFailure("CLOUD_INTEGRITY")
        self.digest.update(chunk)
        return chunk


def unpack_stream(stream, destination, expected_digest, deadline):
    """Stream an uncompressed TAR: one extracted copy, no full download on disk."""
    bounded = BoundedStream(stream, deadline)
    seen, expanded = set(), 0
    # No generic extract/extractall: even administrator mistakes cannot traverse.
    with tarfile.open(fileobj=bounded, mode="r|") as archive:
        for member in archive:
            if (member.name not in MEMBERS or member.name in seen or not member.isfile() or
                    member.pax_headers or member.size < 0):
                raise ReleaseFailure("CLOUD_INTEGRITY")
            seen.add(member.name)
            expanded += member.size
            if expanded > MAX_ARCHIVE_BYTES or (member.name.endswith(".json") and member.size > MAX_METADATA_BYTES):
                raise ReleaseFailure("CLOUD_INTEGRITY")
            source = archive.extractfile(member)
            with (destination / member.name).open("xb") as target:
                copied = 0
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    copied += len(chunk)
                    target.write(chunk)
                if copied != member.size:
                    raise ReleaseFailure("CLOUD_INTEGRITY")
            os.chmod(destination / member.name, stat.S_IRUSR | stat.S_IWUSR)
    # TAR stops on its end marker. Hash the remaining padding too; the environment
    # pins the full exported archive, not just extracted members.
    while bounded.read(1024 * 1024):
        pass
    if seen != set(MEMBERS) or bounded.digest.hexdigest() != expected_digest:
        raise ReleaseFailure("CLOUD_INTEGRITY")


def validate_directory(directory, expected_manifest=None, expected_archive=None):
    """Revalidate every immutable cached member before every child reload."""
    try:
        if directory.is_symlink() or set(p.name for p in directory.iterdir()) != set(MEMBERS):
            raise ValueError()
        for name in MEMBERS:
            path = directory / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
                raise ValueError()
            if name.endswith(".json") and path.stat().st_size > MAX_METADATA_BYTES:
                raise ValueError()
        release = json.loads((directory / "release.json").read_bytes())
        original = (directory / "manifest.json").read_bytes()
        manifest = json.loads(original)
        source_digest = hashlib.sha256(original).hexdigest()
        if (release["format"] != 1 or release["run_id"] != RUN_ID or manifest["run_id"] != RUN_ID or
                release["source_manifest_sha256"] != source_digest or
                expected_manifest is not None and expected_manifest != source_digest or
                manifest["doc2vec_size"] != 100 or manifest["feature_width"] != 140 or
                not isinstance(manifest["test_samples"], int) or manifest["test_samples"] <= 0 or
                release["feature_names"] != manifest["feature_names"] or
                release["labels"] != {"0": "legit", "1": "spam_or_phishing"} or
                release["code_sha256"] != code_hashes() or release["packages"] != package_versions() or
                set(release["artifacts"]) != set(ARTIFACTS) or
                release["verification"] != {"full_run_hashes": True, "test_samples": manifest["test_samples"], "feature_width": 140}):
            raise ValueError()
        # Imported only inside the already isolated cloud model child.
        from preprocess import FEATURE_NAMES
        from artifact_store import FILES
        verify_locked_environment()
        if manifest["feature_names"] != list(FEATURE_NAMES) or set(manifest["files"]) != set(FILES):
            raise ValueError()
        expanded = 0
        for name in ARTIFACTS:
            entry, path = release["artifacts"][name], directory / name
            expanded += path.stat().st_size
            if (entry["bytes"] != path.stat().st_size or entry["sha256"] != manifest["files"][name] or
                    not DIGEST.fullmatch(entry["sha256"]) or sha256(path) != entry["sha256"]):
                raise ValueError()
        if expanded > MAX_ARCHIVE_BYTES:
            raise ValueError()
        if expected_archive is not None and archive_digest(directory) != expected_archive:
            raise ValueError()
        return release, manifest
    except ReleaseFailure:
        raise
    except Exception:
        raise ReleaseFailure("CLOUD_INTEGRITY") from None


def provision(config, expected_manifest=None):
    """Download once or fail closed on a changed cache; never silently refresh."""
    destination = cache_root() / config.digest
    stage = cache_root() / (config.digest + ".partial")
    try:
        cache_root().mkdir(mode=0o700, parents=True, exist_ok=True)
        if cache_root().is_symlink():
            raise ReleaseFailure("CLOUD_INTEGRITY")
        if destination.exists() or destination.is_symlink():
            return destination, *validate_directory(destination, expected_manifest, config.digest)
        remove_partial(config)
        stage.mkdir(mode=0o700)
        # Disable ambient HTTP proxy inheritance and redirects: the Bearer token
        # goes only to the validated, administrator-owned private Blob URL.
        opener = build_opener(ProxyHandler({}), NoRedirect())
        request = Request(config.url, headers={"Authorization": "Bearer " + config.token,
                                               "Accept-Encoding": "identity"})
        deadline = time.monotonic() + MAX_DOWNLOAD_SECONDS
        try:
            with opener.open(request, timeout=15) as response:
                if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ReleaseFailure("CLOUD_DOWNLOAD")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isascii() or not length.isdigit() or int(length) > MAX_ARCHIVE_BYTES):
                    raise ReleaseFailure("CLOUD_INTEGRITY")
                unpack_stream(response, stage, config.digest, deadline)
        except ReleaseFailure:
            raise
        except Exception:
            raise ReleaseFailure("CLOUD_DOWNLOAD") from None
        release, manifest = validate_directory(stage, expected_manifest, config.digest)
        os.replace(stage, destination)
        return destination, release, manifest
    except ReleaseFailure:
        raise
    except Exception:
        raise ReleaseFailure("CLOUD_INTEGRITY") from None
    finally:
        remove_partial(config)
