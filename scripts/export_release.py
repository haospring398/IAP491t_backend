"""Verify the complete original run, then atomically export only inference files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.backend.cloud_release import ARTIFACTS, MAX_ARCHIVE_BYTES, MAX_METADATA_BYTES, code_hashes, package_versions, sha256, write_archive, verify_locked_environment
from web.backend.policy import ROOT, RUN_ID


def export_release(source, output):
    # Dependency imports occur only when export is explicitly requested.
    import artifact_store
    from web.backend.adapter import Adapter
    source, output = Path(source).resolve(), Path(output).resolve()
    if source.name != RUN_ID:
        raise ValueError("Export requires the original demo run")
    if output.exists():
        raise ValueError("Refusing to replace an existing release")
    if output == source or source in output.parents:
        raise ValueError("Export must be outside the original run")
    verify_locked_environment()
    if (source / "manifest.json").stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("Source manifest exceeds metadata bound")
    manifest_bytes = (source / "manifest.json").read_bytes()
    if len(manifest_bytes) > MAX_METADATA_BYTES:
        raise ValueError("Source manifest exceeds metadata bound")
    manifest = artifact_store.verify_run(source)
    if manifest != json.loads(manifest_bytes):
        raise ValueError("Source changed during verification")
    adapter = Adapter.__new__(Adapter)
    adapter.release = hashlib.sha256(manifest_bytes).hexdigest()
    adapter._load_verified(source, manifest, run_identity="dumped_models/classification/runs/" + RUN_ID)
    if manifest["doc2vec_size"] != 100 or manifest["feature_width"] != 140:
        raise ValueError("Unexpected original feature dimensions")
    release = {
        "format": 1, "run_id": RUN_ID, "source_manifest_sha256": adapter.release,
        "feature_names": manifest["feature_names"], "labels": {"0": "legit", "1": "spam_or_phishing"},
        "artifacts": {name: {"sha256": manifest["files"][name], "bytes": (source / name).stat().st_size} for name in ARTIFACTS},
        "code_sha256": code_hashes(), "packages": package_versions(),
        "inference": {key: adapter.metadata[key] for key in ("alpha", "min_alpha", "epochs", "stopwords", "wordnet", "numerical_threads")},
        "verification": {"full_run_hashes": True, "test_samples": manifest["test_samples"], "feature_width": manifest["feature_width"]},
    }
    release_bytes = json.dumps(release, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(release_bytes) > MAX_METADATA_BYTES:
        raise ValueError("Release metadata exceeds metadata bound")
    # Avoid a second copy of the 307 MB model. A staging directory contains only
    # metadata and hard links when possible; fallback paths are copied boundedly.
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.TemporaryDirectory(prefix="iap-export-", dir=output.parent) as temporary_dir:
            staging = Path(temporary_dir)
            (staging / "manifest.json").write_bytes(manifest_bytes)
            (staging / "release.json").write_bytes(release_bytes)
            for name in ARTIFACTS:
                try:
                    os.link(source / name, staging / name)
                except OSError:
                    import shutil
                    shutil.copyfile(source / name, staging / name)
            handle = tempfile.NamedTemporaryFile(prefix=".iap-release-", suffix=".tar", dir=output.parent, delete=False)
            temporary = Path(handle.name)
            with handle:
                write_archive(handle, staging)
                handle.flush()
                os.fsync(handle.fileno())
            if temporary.stat().st_size > MAX_ARCHIVE_BYTES:
                raise ValueError("Export exceeds archive bound")
            # Validate the exported bytes against source hashes before publication;
            # hard links/copying cannot silently change an artifact after verification.
            import tarfile
            with tarfile.open(temporary, "r:") as archive:
                for name in ARTIFACTS:
                    digest = hashlib.sha256()
                    with archive.extractfile(name) as member:
                        for chunk in iter(lambda: member.read(1024 * 1024), b""):
                            digest.update(chunk)
                    if digest.hexdigest() != manifest["files"][name]:
                        raise ValueError("Source artifact changed during export")
            if (source / "manifest.json").read_bytes() != manifest_bytes:
                raise ValueError("Source manifest changed during export")
            digest = sha256(temporary)
            # A hard-link publication is atomic and cannot clobber a raced output.
            os.link(temporary, output)
            return {"archive": str(output), "sha256": digest, "bytes": output.stat().st_size,
                    "source_manifest_sha256": adapter.release, "run_id": RUN_ID}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_release(args.source_run, args.output), indent=2))


if __name__ == "__main__":
    main()
