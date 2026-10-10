"""Cloud provisioning and the unchanged inference adapter in a serial child."""
import platform
import sys
import time
from web.backend.adapter import Adapter, StartupFailure, serve
from web.backend.cloud_release import ReleaseConfig, ReleaseFailure, provision, remove_partial
from web.backend.policy import RUN_ID

RUN = "dumped_models/classification/runs/" + RUN_ID


class CloudAdapter(Adapter):
    def _load(self, pinned, expected_manifest):
        self.startup_stage = "CLOUD_CONFIGURATION"
        config = ReleaseConfig.from_environment()
        if pinned is not None and pinned != RUN:
            raise ReleaseFailure("CLOUD_INTEGRITY")
        self.startup_stage = "CLOUD_INTEGRITY"
        try:
            directory, release, manifest = provision(config, expected_manifest)
        except ReleaseFailure as error:
            self.startup_stage = error.stage
            raise
        # The original manifest digest remains the RNG identity, independent of
        # archive metadata, TAR headers, compression or delivery URL.
        self.release = release["source_manifest_sha256"]
        self._load_verified(directory, manifest, run_identity=RUN)
        self.startup_stage = "INFERENCE_SETTINGS"
        settings = {key: self.metadata[key] for key in ("alpha", "min_alpha", "epochs", "stopwords", "wordnet", "numerical_threads")}
        if settings != release["inference"] or self.metadata["hash_seed"] != "0":
            raise ValueError("Changed inherited inference settings")
        self.metadata["archive_sha256"] = config.digest
        self.metadata["code_sha256"] = release["code_sha256"]
        self.metadata["packages"] = release["packages"]


def cleanup():
    """Called only after the supervisor has reaped its child."""
    try:
        remove_partial(ReleaseConfig.from_environment())
    except (ReleaseFailure, OSError):
        pass


def worker(connection, pinned, expected_manifest=None):
    started = time.monotonic()
    try:
        adapter = CloudAdapter(pinned, expected_manifest)
        adapter.metadata["python_version"] = platform.python_version()
        adapter.metadata["initialization_seconds"] = round(time.monotonic() - started, 3)
        adapter.metadata["peak_rss_kib"] = None
        try:
            import resource
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            adapter.metadata["peak_rss_kib"] = int(peak / 1024 if sys.platform == "darwin" else peak)
        except (ImportError, OSError, AttributeError):
            pass
        connection.send(("ready", adapter.metadata))
    except Exception as error:
        connection.send(("unavailable", error.stage if isinstance(error, StartupFailure) else "CLOUD_INTEGRITY"))
        connection.close()
        return
    serve(connection, adapter)
