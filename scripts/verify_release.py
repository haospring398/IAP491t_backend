"""Offline five-sample original/cloud vector and label parity in separate children."""
import argparse
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.backend.policy import ROOT, RUN_ID

MAX_REFERENCE_BYTES = 64 * 1024


def original_adapter(source):
    import artifact_store
    from web.backend.adapter import Adapter
    source = Path(source)
    manifest_bytes = (source / "manifest.json").read_bytes()
    manifest = artifact_store.verify_run(source)
    if manifest != json.loads(manifest_bytes):
        raise ValueError("Changed source")
    adapter = Adapter.__new__(Adapter)
    adapter.release = hashlib.sha256(manifest_bytes).hexdigest()
    adapter._load_verified(source, manifest, "dumped_models/classification/runs/" + RUN_ID)
    return adapter


def result_record(adapter):
    from web.backend.adapter import xgboost_provider
    return {"observation": observe(adapter),
            "runtime": {"python_version": platform.python_version(),
                        "xgboost_distribution": xgboost_provider(),
                        "packages": adapter.metadata["packages"]}}


def validate_record(record, source_digest):
    try:
        observation, runtime = record["observation"], record["runtime"]
        if (set(record) != {"observation", "runtime"} or
                set(observation) != {"source_manifest_sha256", "samples"} or
                observation["source_manifest_sha256"] != source_digest or
                set(observation["samples"]) != {p.name for p in (ROOT / "web/backend/samples").glob("*.eml")} or
                len(observation["samples"]) != 5 or
                runtime["xgboost_distribution"] not in ("xgboost", "xgboost-cpu") or
                not isinstance(runtime["python_version"], str) or
                not isinstance(runtime["packages"], dict) or
                not isinstance(runtime["packages"][runtime["xgboost_distribution"]], str)):
            raise ValueError()
        for sample in observation["samples"].values():
            if (set(sample) != {"vector_sha256", "result"} or
                    re.fullmatch(r"[0-9a-f]{64}", sample["vector_sha256"]) is None or
                    sample["result"] not in ({"analysis_status": "completed", "label": "legit"},
                                            {"analysis_status": "completed", "label": "spam_or_phishing"})):
                raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Invalid parity observation") from None
    return record


def reference_result(interpreter, source, timeout):
    """One direct reference process, bounded disk output, no shell or child fanout."""
    with tempfile.TemporaryDirectory(prefix="iap-reference-") as tmp:
        output = Path(tmp) / "observation.json"
        process_failed = False
        try:
            subprocess.run([str(interpreter), str(Path(__file__).resolve()),
                            "--source-run", str(source), "--observe-source", str(output)],
                           cwd=ROOT, env=os.environ.copy(), check=True, timeout=timeout,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            process_failed = True
            if not output.is_file():
                raise
        with output.open("rb") as handle:
            blob = handle.read(MAX_REFERENCE_BYTES + 1)
        if len(blob) > MAX_REFERENCE_BYTES:
            raise ValueError("Reference observation exceeds bound")
        record = json.loads(blob)
        if isinstance(record, dict) and set(record) == {"failure"}:
            stages = {"REFERENCE_DEPENDENCY", "REFERENCE_FILES", "REFERENCE_OBSERVATION"}
            if isinstance(record["failure"], str) and record["failure"] in stages:
                raise ValueError("Reference failed: " + record["failure"])
            raise ValueError("Invalid reference failure")
        if process_failed:
            raise ValueError("Reference process failed")
        digest = hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest()
        return validate_record(record, digest)


def check_child(connection, source, archive):
    try:
        from web.backend import cloud_release as cloud
        if archive is None:
            result = result_record(original_adapter(source))
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
                result = result_record(adapter)
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
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--reference-python", type=Path,
                        help="Original full-XGBoost interpreter; comparison runs in a separate environment")
    parser.add_argument("--observe-source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    if args.observe_source is None and args.archive is None:
        parser.error("--archive is required for parity verification")
    os.environ["PYTHONHASHSEED"] = "0"
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS"):
        os.environ[name] = "1"
    source = args.source_run.resolve()
    if args.observe_source is not None:
        failed = False
        try:
            record = result_record(original_adapter(source))
        except Exception as error:
            stage = ("REFERENCE_DEPENDENCY" if isinstance(error, ImportError) else
                     "REFERENCE_FILES" if isinstance(error, OSError) else "REFERENCE_OBSERVATION")
            record, failed = {"failure": stage}, True
        blob = json.dumps(record).encode("utf-8")
        if len(blob) > MAX_REFERENCE_BYTES:
            raise ValueError("Reference observation exceeds bound")
        with args.observe_source.open("xb") as output:
            output.write(blob)
        if failed:
            raise SystemExit(1)
        return
    # Venv interpreters are often symlinks; resolving one selects the base Python
    # and loses that environment's installed distributions.
    local = (reference_result(args.reference_python.absolute(), source, args.timeout_seconds)
             if args.reference_python is not None else isolated(source, None, args.timeout_seconds))
    digest = hashlib.sha256((source / "manifest.json").read_bytes()).hexdigest()
    validate_record(local, digest)
    if args.reference_python is not None and local["runtime"]["xgboost_distribution"] != "xgboost":
        raise ValueError("Explicit reference must use full XGBoost")
    exported = isolated(None, args.archive.resolve(), args.timeout_seconds)
    validate_record(exported, digest)
    if local["observation"] != exported["observation"]:
        raise ValueError("Original/cloud vectors or labels differ")
    print(json.dumps({"parity": "passed", "sample_count": 5,
                      "comparison": "full_xgboost_vs_cpu" if args.reference_python is not None else "same_environment",
                      **exported["observation"],
                      "runtimes": {"reference": local["runtime"], "cloud": exported["runtime"]}}, indent=2))


if __name__ == "__main__":
    main()
