"""Loopback FastAPI supervisor with one admission and one killable resident child."""
import asyncio
import contextlib
import hmac
import json
import logging
import multiprocessing
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect

from web.backend.adapter import worker, STARTUP_STAGES
from web.backend.policy import POLICY, UUID, UNAVAILABLE_ERROR, RUN_ID, Rejection, validate_policy

FAILURE_STAGES = STARTUP_STAGES | {"CONFIGURATION_INVALID", "AUTH_CONFIGURATION", "WORKER_SPAWN", "WORKER_STARTUP_TIMEOUT", "WORKER_STARTUP_FAILED"}


class AuthenticationRejected(Rejection):
    status = 401


def error_response(code, request_id, status=None, configured=True):
    if not configured:
        code, status, entry = "MODEL_UNAVAILABLE", None, UNAVAILABLE_ERROR
    else:
        entry = POLICY["errors"][code]
    headers = {"X-Request-ID": request_id, "Cache-Control": "no-store"}
    if entry["retryAfterSeconds"]:
        headers["Retry-After"] = str(entry["retryAfterSeconds"])
    return JSONResponse({"request_id": request_id, "error": {"code": code, "message": entry["message"]}},
                        status_code=status or entry["http"], headers=headers)


class Supervisor:
    def __init__(self, token, worker_target=worker, startup_wait=False, cleanup=None):
        self.worker_target, self.startup_wait, self.cleanup = worker_target, startup_wait, cleanup
        self.token = token if token and all(33 <= ord(c) <= 126 for c in token) else None
        self.process = self.connection = self.startup = None
        self.ready = False
        self.starting = False
        self.active_id = None
        self.phase = "unknown"
        self.pinned = None
        self.manifest_digest = None
        self.metadata = None
        self.closed = False
        self.last_failure = None
        self.configuration_valid = False

    def failure(self, stage):
        self.last_failure = stage if stage in FAILURE_STAGES else "WORKER_STARTUP_FAILED"
        logging.getLogger("backend.startup").warning("Local model unavailable: %s", self.last_failure)

    def launch(self):
        if self.closed:
            return
        try:
            validate_policy()
        except Exception:
            self.configuration_valid = False
            self.failure("CONFIGURATION_INVALID")
            return
        self.configuration_valid = True
        if not self.token:
            self.failure("AUTH_CONFIGURATION")
            return
        self.ready = False
        self.starting = True
        # Spawn reads these before importing numerical packages and Python hashing.
        os.environ["PYTHONHASHSEED"] = "0"
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS"):
            os.environ[name] = "1"
        ctx = multiprocessing.get_context("spawn")
        child = None
        try:
            self.connection, child = ctx.Pipe()
            self.process = ctx.Process(target=self.worker_target, args=(child, self.pinned, self.manifest_digest), daemon=True)
            self.process.start()
            child.close()
            self.startup = asyncio.create_task(self._startup())
        except Exception:
            self.failure("WORKER_SPAWN")
            if child:
                child.close()
            if self.connection:
                self.connection.close()
                self.connection = None
            if self.process:
                self.process.close()
                self.process = None
            self.starting = False

    async def _message(self):
        while self.process and self.process.is_alive():
            if self.connection.poll():
                return self.connection.recv()
            await asyncio.sleep(0.01)
        if self.connection and self.connection.poll():
            return self.connection.recv()
        raise Rejection("MODEL_UNAVAILABLE")

    async def _startup(self):
        try:
            kind, metadata = await asyncio.wait_for(self._message(), POLICY["deadlines"]["workerStartupMs"] / 1000)
            if kind != "ready":
                self.failure(metadata)
                raise Rejection("MODEL_UNAVAILABLE")
            if self.manifest_digest is not None and metadata["manifest_sha256"] != self.manifest_digest:
                self.failure("RELEASE_CHANGED")
                raise Rejection("MODEL_UNAVAILABLE")
            if self.metadata is not None and metadata.get("archive_sha256") != self.metadata.get("archive_sha256"):
                self.failure("RELEASE_CHANGED")
                raise Rejection("MODEL_UNAVAILABLE")
            self.metadata = metadata
            self.pinned = metadata["run"]
            self.manifest_digest = metadata["manifest_sha256"]
            self.ready = True
            self.last_failure = None
            if self.startup_wait:
                from web.backend.cloud_release import PACKAGES
                record = {"run_id": RUN_ID, "manifest_sha256": metadata["manifest_sha256"],
                          "archive_sha256": metadata.get("archive_sha256"),
                          "python_version": metadata.get("python_version"),
                          "packages": {name: metadata.get("packages", {}).get(name) for name in PACKAGES},
                          "initialization_seconds": metadata.get("initialization_seconds"),
                          "peak_rss_kib": metadata.get("peak_rss_kib")}
                logging.getLogger("backend.startup").warning("Model worker ready: %s", json.dumps(record, sort_keys=True))
        except asyncio.TimeoutError:
            self.failure("WORKER_STARTUP_TIMEOUT")
            await self._reap()
        except (Exception, asyncio.CancelledError):
            if self.last_failure is None:
                self.failure("WORKER_STARTUP_FAILED")
            await self._reap()
        finally:
            self.starting = False

    async def _reap(self):
        self.ready = False
        process = self.process
        if process:
            if process.is_alive():
                process.terminate()
            await asyncio.to_thread(process.join, POLICY["deadlines"]["terminateMs"] / 1000)
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join, POLICY["deadlines"]["killReapMs"] / 1000)
            if process.is_alive():
                # Fail closed: never replace an unreaped process.
                self.closed = True
                os._exit(1)
                return
            process.close()
            self.process = None
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.cleanup is not None:
            self.cleanup()

    async def _stop_startup(self):
        if self.startup and not self.startup.done():
            self.startup.cancel()
            await asyncio.gather(self.startup, return_exceptions=True)

    async def recycle(self):
        await self._stop_startup()
        await self._reap()
        self.launch()

    async def close(self):
        self.closed = True
        if self.startup and not self.startup.done():
            self.startup.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.startup
        await self._reap()

    def authorize(self, request):
        if not self.configuration_valid or not self.token:
            raise Rejection("MODEL_UNAVAILABLE")
        values = request.headers.getlist("authorization")
        if len(values) != 1 or not hmac.compare_digest(values[0].encode(), f"Bearer {self.token}".encode()):
            raise AuthenticationRejected("INVALID_REQUEST")

    def identity(self, request):
        values = request.headers.getlist("x-request-id")
        if len(values) != 1 or not UUID.fullmatch(values[0]):
            raise Rejection("INVALID_REQUEST")
        return values[0]

    def budget(self, request):
        values = request.headers.getlist("x-analysis-deadline")
        if len(values) != 1 or not values[0].isascii() or not values[0].isdigit() or len(values[0]) > 16:
            raise Rejection("INVALID_REQUEST")
        remaining = int(values[0]) - time.time() * 1000
        limits = POLICY["deadlines"]
        if remaining > limits["proxyMs"] + limits["clockSkewMs"]:
            raise Rejection("INVALID_REQUEST")
        if remaining <= limits["backendReserveMs"]:
            raise Rejection("ANALYSIS_TIMEOUT")
        return (remaining - limits["backendReserveMs"] if self.startup_wait else
                min(limits["backendMs"], remaining - limits["backendReserveMs"])) / 1000

    async def analyze(self, request):
        request_id = str(uuid.uuid4())
        admitted = False
        try:
            request_id = self.identity(request)
            self.authorize(request)
            self.budget(request)
            if self.active_id is not None:
                raise Rejection("SERVICE_BUSY")
            dead_worker = self.ready and self.process and not self.process.is_alive()
            retry_download = (self.startup_wait and not self.ready and not self.starting and
                              self.last_failure == "CLOUD_DOWNLOAD")
            if dead_worker or retry_download:
                # Admission is claimed before recovery yields: one authenticated
                # request can retry a demonstrated download failure, with no queue.
                self.active_id, self.phase = request_id, "starting"
                admitted = True
                self.ready = False
                await self.recycle()
                if not self.startup_wait:
                    raise Rejection("MODEL_UNAVAILABLE")
            if not self.ready and not (self.startup_wait and self.starting and self.startup):
                raise Rejection("MODEL_UNAVAILABLE")
            if not self.process or not self.process.is_alive():
                raise Rejection("MODEL_UNAVAILABLE")
            # No await between readiness check and admission. No request body read yet.
            self.active_id, self.phase = request_id, "receiving"
            admitted = True
            try:
                budget = self.budget(request)
                result = await asyncio.wait_for(self._job(request), budget)
            except (asyncio.TimeoutError, ClientDisconnect):
                await self.recycle()
                raise Rejection("ANALYSIS_TIMEOUT") from None
            except asyncio.CancelledError:
                await asyncio.shield(self.recycle())
                raise
            except Rejection as error:
                if error.code == "MODEL_UNAVAILABLE" and (not self.startup_wait or self.last_failure is None):
                    await self.recycle()
                raise
            except Exception:
                await self.recycle()
                raise Rejection("MODEL_UNAVAILABLE") from None
            return JSONResponse(result, headers={"X-Request-ID": request_id, "Cache-Control": "no-store"})
        except Rejection as error:
            return error_response(error.code, request_id, getattr(error, "status", None), self.configuration_valid)
        finally:
            if admitted:
                self.active_id, self.phase = None, "unknown"

    async def _job(self, request):
        content_type = request.headers.get("content-type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            raise Rejection("INVALID_REQUEST")
        length = request.headers.get("content-length")
        if length and length.isascii() and length.isdigit() and int(length) > POLICY["limits"]["multipartBytes"]:
            raise Rejection("EMAIL_TOO_LARGE")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > POLICY["limits"]["multipartBytes"]:
                raise Rejection("EMAIL_TOO_LARGE")
            body.extend(chunk)
        async def inference():
            if self.startup_wait and not self.ready:
                self.phase = "starting"
                await asyncio.shield(self.startup)
                if not self.ready or not self.process or not self.process.is_alive():
                    raise Rejection("MODEL_UNAVAILABLE")
            if self.startup_wait:
                # Startup and upload spend the trusted proxy budget. Inference
                # still receives at most the unchanged 60-second backend budget.
                return await asyncio.wait_for(model_result(), min(self.budget(request), POLICY["deadlines"]["backendMs"] / 1000))
            return await model_result()

        async def model_result():
            await asyncio.to_thread(self.connection.send, (bytes(body), content_type))
            kind, _ = await self._message()
            if kind != "processing":
                raise Rejection("MODEL_UNAVAILABLE")
            self.phase = "processing"
            kind, payload = await self._message()
            if kind == "error":
                raise Rejection(payload if payload in POLICY["errors"] else "MODEL_UNAVAILABLE")
            if kind != "success":
                raise Rejection("MODEL_UNAVAILABLE")
            return payload

        async def disconnected():
            while True:
                message = await request.receive()
                if message["type"] == "http.disconnect":
                    raise ClientDisconnect()

        task = asyncio.create_task(inference())
        disconnect = asyncio.create_task(disconnected())
        try:
            done, _ = await asyncio.wait((task, disconnect), return_when=asyncio.FIRST_COMPLETED)
            if disconnect in done:
                return await disconnect
            return await task
        finally:
            task.cancel()
            disconnect.cancel()
            await asyncio.gather(task, disconnect, return_exceptions=True)


def create_app(token=None, *, worker_target=worker, startup_wait=False, cleanup=None):
    supervisor = Supervisor(os.environ.get("ML_API_TOKEN") if token is None else token,
                            worker_target, startup_wait, cleanup)

    @asynccontextmanager
    async def lifespan(app):
        supervisor.launch()
        yield
        await supervisor.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.supervisor = supervisor

    @app.get("/health/live")
    async def live():
        return JSONResponse({"status": "alive"}, headers={"Cache-Control": "no-store"})

    @app.get("/health/ready")
    async def ready():
        usable = supervisor.ready and supervisor.process is not None and supervisor.process.is_alive()
        return JSONResponse({"status": "ready" if usable else "unready"}, status_code=200 if usable else 503,
                            headers={"Cache-Control": "no-store"})

    @app.post("/v1/analyze")
    async def analyze(request: Request):
        return await supervisor.analyze(request)

    @app.get("/v1/analysis-status")
    async def status(request: Request):
        request_id = str(uuid.uuid4())
        try:
            values = list(request.query_params.multi_items())
            if len(values) != 1 or values[0][0] != "request_id" or not UUID.fullmatch(values[0][1]):
                raise Rejection("INVALID_REQUEST")
            request_id = values[0][1]
            supervisor.authorize(request)
            phase = supervisor.phase if supervisor.active_id == request_id else "starting" if supervisor.starting else "unknown"
            return JSONResponse({"request_id": request_id, "phase": phase},
                                headers={"X-Request-ID": request_id, "Cache-Control": "no-store"})
        except Rejection as error:
            return error_response(error.code, request_id, getattr(error, "status", None), supervisor.configuration_valid)

    return app


app = create_app()
