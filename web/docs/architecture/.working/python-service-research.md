# Python service research — 2026-10-05

Primary sources checked on the date above. This is version and API research, not an installation, dependency-resolution test, runtime benchmark or model-compatibility result.

| Candidate seed | Verified source |
| --- | --- |
| CPython 3.11.17 | [Python release, 2026-10-01](https://www.python.org/downloads/release/python-31117/) |
| Official Python image 3.11.17-slim-bookworm | [Docker Official Image tags](https://hub.docker.com/_/python) |
| FastAPI 0.142.2 | [Release notes, 2026-09-30](https://fastapi.tiangolo.com/release-notes/) |
| Uvicorn 0.54.0 | [Current release notes, 2026-09-24](https://uvicorn.dev/release-notes/) |
| python-multipart 0.0.32 | [Maintainer package metadata](https://pypi.org/project/python-multipart/0.0.32/) |

The checked local interpreter is 3.11.2. Keeping the 3.11 series while moving to 3.11.17 is a proposed compatibility path; E0 must validate the complete Linux environment, artifacts, preprocessing resources and feature/label parity. Neither equal minor versions nor installed package metadata certify compatibility. Production image digests and the full dependency lock belong to the validated release.

## Runtime fit and boundaries

- FastAPI supports multipart uploads and `UploadFile` may spool to temporary storage. The supervisor must cap the received body, enforce admission before expensive work and own closing/cleanup; request handlers must not assume every upload remains in RAM. [Request files](https://fastapi.tiangolo.com/tutorial/request-files/).
- Uvicorn's documented keep-alive timeout concerns connections between requests. It is not a hard deadline for native ML computation. A single application inference slot also differs from setting Uvicorn's connection limit to one. [Server behavior](https://uvicorn.dev/server-behavior/).
- Python's process APIs support terminating a worker; forced termination skips worker cleanup and may damage IPC. The parent must retain ownership of temporary files and admission state, discard that worker's channels, confirm exit and validate a fresh worker before readiness returns. `spawn` is the portable start method for the Windows development/Linux container boundary. These are architectural inferences from the API contract. [Python 3.11 multiprocessing](https://docs.python.org/3.11/library/multiprocessing.html).
- Trusted pickle loading depends on a compatible environment and is separate from hash integrity. E0 must establish the eligible release and startup must reject an unsuitable deployment bundle. [scikit-learn model persistence](https://scikit-learn.org/stable/model_persistence.html).

## Proposed runtime choice

One lightweight ASGI supervisor and one resident, serialized ML process avoid loading a model per request and provide a boundary for terminating timed-out native work. An in-process thread is simpler but does not establish that deadline. A fresh model-loaded process per request provides isolation at the cost of repeated startup. The resident process is a fast-path proposal, pending whole-container memory/startup/parity measurements. No resource feasibility is claimed.
