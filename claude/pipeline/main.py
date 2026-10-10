"""pipeline — ingest everything on the broker, keep history, serve it back.

Why it exists as its own process: sensing, deciding and remembering are different jobs with different
failure modes. If this container dies, control keeps regulating (it reads the broker, not the disk);
when it comes back, the broker's persistent session delivers what it missed (QoS 1, clean_session=False).

HTTP API (also used by Grafana via the Infinity plugin and by planner/train.py):
    GET /history?room=A109&type=co2&minutes=120     recent readings of one sensor
        [&until=<sim ISO>&max_age_s=<wall s>]       window ends at `until`, rows of this run only
    GET /query?sql=SELECT ...                        read-only DuckDB over the bronze views
    GET /stats                                       row counts, last compaction
    POST /compact                                    rebuild silver parquet now
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import HTTPException, Query

from common import config
from common.http import make_app, run_in_thread, serve, setup_logging
from common.mqtt import Bus
from pipeline.storage import Storage

log = logging.getLogger("pipeline")

COMPACT_S = float(config.env("COMPACT_S", "300"))


class Pipeline:
    def __init__(self) -> None:
        self.store = Storage()
        self.bus = Bus("pipeline")
        self.last_compact: dict = {}
        self.last_compact_ts = 0.0
        self._lock = threading.Lock()

    def on_message(self, topic: str, payload: dict) -> None:
        parts = topic.split("/")
        if parts[0] == "bldg" and len(parts) >= 4:
            kind = {"sensor": "sensor", "actuator": "actuator", "plan": "plan", "decision": "decision"}.get(parts[3])
            if kind == "actuator" and parts[-1] == "cmd":
                kind = "actuator"          # commands and states both land in actuator.jsonl (field `target` vs `state`)
            if kind:
                self.store.append(kind, topic, payload)
        elif parts[0] == "sys" and parts[1] == "health":
            self.store.append("health", topic, payload)

    def run(self) -> None:
        self.bus.subscribe("bldg/#", self.on_message)
        self.bus.subscribe("sys/health/#", self.on_message)
        self.bus.start()
        self.bus.wait_connected(60)
        while True:
            time.sleep(COMPACT_S)
            self.compact()

    def compact(self) -> dict:
        with self._lock:
            self.last_compact = self.store.compact()
            self.last_compact_ts = time.time()
            self.bus.health("ok", f"rows={self.store.rows}")
            log.info("compacted: %s", self.last_compact)
            return self.last_compact


def main() -> None:
    setup_logging()
    p = Pipeline()
    run_in_thread(p.run, "pipeline-loop")
    app = make_app("pipeline", lambda: {"status": "ok", "rows": p.store.rows})

    @app.get("/history")
    def history(room: str, type: str = Query(alias="type"), minutes: int = 120, level: str = "level0",
                until: str | None = None, max_age_s: float | None = None):
        return p.store.history(room, type, minutes, level, until, max_age_s)

    @app.get("/query")
    def query(sql: str):
        try:
            return p.store.query(sql)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, str(e))

    @app.get("/stats")
    def stats():
        return {"rows": p.store.rows, "rejected": p.store.rejected, "last_compact": p.last_compact, "last_compact_ts": p.last_compact_ts}

    @app.post("/compact")
    def compact():
        return p.compact()

    serve(app)


if __name__ == "__main__":
    main()
