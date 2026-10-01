"""Tiny HTTP helper: every service exposes /healthz (Compose healthcheck + report evidence).

    app = make_app("sensor-co2-A109")
    @app.get("/extra") ...
    serve(app, port=8000)          # blocking; run the service loop in a thread before
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable

import uvicorn
from fastapi import FastAPI


def make_app(service: str, status_fn: Callable[[], dict] | None = None) -> FastAPI:
    app = FastAPI(title=service, docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz():
        extra = status_fn() if status_fn else {}
        return {"service": service, "status": extra.get("status", "ok"), **extra}

    return app


def serve(app: FastAPI, port: int | None = None) -> None:
    port = int(port or os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def run_in_thread(target: Callable[[], None], name: str) -> threading.Thread:
    t = threading.Thread(target=target, name=name, daemon=True)
    t.start()
    return t


def setup_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
