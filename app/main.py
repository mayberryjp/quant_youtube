"""Bottle application entry point."""

from __future__ import annotations

import logging
import sys

from bottle import Bottle, response

from app.config import settings
from app.routes import health

SERVICE_NAME = "youtube-api"
log = logging.getLogger(SERVICE_NAME)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
    force=True,
)

app = Bottle()


@app.hook("after_request")
def _enable_cors() -> None:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"


@app.route("/<:path>", method="OPTIONS")
def _cors_preflight(path: str = "") -> str:
    return ""


app.merge(health.sub)

try:
    from app.routes import episodes

    app.merge(episodes.sub)
except ImportError:
    pass

try:
    from app.routes import runs

    app.merge(runs.sub)
except ImportError:
    pass

if __name__ == "__main__":
    from waitress import serve

    log.info(
        "Starting youtube API on %s:%d ...",
        settings.api_listen_address,
        settings.api_port,
    )
    serve(app, host=settings.api_listen_address, port=settings.api_port, threads=8)
