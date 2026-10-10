"""Offline five-sample original/cloud vector and label parity in separate children."""
import argparse
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.backend.policy import ROOT, RUN_ID


def check_child(connection, source, archive):
    try:
        from web.backend.adapter import Adapter
        from web.backend import cloud_release as cloud
        if archive is None:
            import artifact_store
            source = Path(source)
            manifest_bytes = (source / "manifest.json").read_bytes()
            manifest = artifact_store.verify_run(source)
            if manifest != json.loads(manifest_bytes):
                raise ValueError("Changed source")
            adapter = Adapter.__new__(Adapter)
            adapter.release = hashlib.sha256(manifest_bytes).hexdigest()
            adapter._load_verified(source, manifest, "dumped_models/classification/runs/" + RUN_ID)
            result = observe(adapter)
        else:
            from web.backend.cloud_worker import CloudAdapter
            digest = cloud.sha256(archive)
            with tempfile.TemporaryDirectory(prefix="iap-parity-") as tmp:
                cache = Path(tmp)
                directory = cache / digest
                directory.mkdir()
                with Path(archive).open("rb") as handle:
                    cloud.unpack_stream(handle, directory, digest, time.monotonic() + 105)
                cloud.cache_root = lambda: cache
                os.environ["MODEL_BLOB_URL"] = "https://offline.private.blob.vercel-storage.com/release.tar"
                os.environ["BLOB_READ_WRITE_TOKEN"] = "offline-test-never-used"
                os.environ["MODEL_RELEASE_SHA256"] = digest
                adapter = CloudAdapter()
                result = observe(adapter)
        connection.send((True, result))
    except Exception as error:
        connection.send((False, getattr(error, "stage", type(error).__name__)))
    finally:
        connection.close()


def observe(adapter):
    samples = sorted((ROOT / "web/backend/samples").glob("*.eml"))
    if len(samples) != 5:
        raise ValueError("Expected five synthetic samples")
    return {
        "source_manifest_sha256": adapter.release,
        "samples": {sample.name: {"vector_sha256": hashlib.sha256(adapter.vector(sample.read_bytes()).tobytes()).hexdigest(),
                                   "result": adapter.analyze(sample.read_bytes())} for sample in samples},
    }


def isolated(source, archive, timeout):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=check_child, args=(child, source, archive))
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise ValueError("Parity child timeout")
        success, result = parent.recv()
        if not success:
            raise ValueError("Parity child failed: " + result)
        return result
    finally:
        process.join(2)
        if process.is_alive():
            process.kill()
            process.join(2)
        parent.close()
        process.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    os.environ["PYTHONHASHSEED"] = "0"
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS"):
        os.environ[name] = "1"
    local = isolated(args.source_run.resolve(), None, args.timeout_seconds)
    exported = isolated(None, args.archive.resolve(), args.timeout_seconds)
    if local != exported:
        raise ValueError("Original/cloud vectors or labels differ")
    print(json.dumps({"parity": "passed", "sample_count": 5, **exported}, indent=2))


if __name__ == "__main__":
    main()
