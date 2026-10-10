"""Use one supervisor, loopback binding, and no access log containing identifiers."""
import argparse
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Loopback real-model demonstration")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    uvicorn.run("web.backend.service:app", host="127.0.0.1", port=args.port, workers=1,
                access_log=False, log_level="warning", timeout_keep_alive=5)
