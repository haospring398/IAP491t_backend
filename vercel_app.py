"""Model-free Vercel entrypoint with bounded cold-start request admission."""
from web.backend.cloud_worker import worker, cleanup
from web.backend.service import create_app

app = create_app(worker_target=worker, startup_wait=True, cleanup=cleanup)
