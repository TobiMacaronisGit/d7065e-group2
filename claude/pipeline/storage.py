"""Storage layout (medallion pattern from course-notes 3, laptop edition):

    /data/bronze/<sim-date>/<kind>.jsonl   exactly what arrived, one JSON object per line, append-only
    /data/silver/<kind>.parquet            typed, de-duplicated columns, rebuilt by compact() (DuckDB)
    /data/gold/...                         purpose-specific tables (training set, evaluation), see planner/train.py

kind ∈ sensor | actuator | plan | decision | health.   Every row keeps: topic, recv_ts (wall, when the
pipeline got it) and the producer's own ts / sim_ts, so latency = recv_ts − ts is measurable per hop.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb

log = logging.getLogger("storage")

KINDS = ("sensor", "actuator", "plan", "decision", "health")


class Storage:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or os.getenv("DATA_DIR", "/data"))
        for sub in ("bronze", "silver", "gold"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self._files: dict[Path, Any] = {}
        self._lock = threading.Lock()
        self.rows = {k: 0 for k in KINDS}
        self.rejected = 0

    # -- bronze --------------------------------------------------------------------
    def append(self, kind: str, topic: str, payload: dict[str, Any]) -> None:
        if kind not in KINDS:
            self.rejected += 1
            return
        sim_date = (payload.get("sim_ts") or "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.root / "bronze" / sim_date / f"{kind}.jsonl"
        row = {"topic": topic, "recv_ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **payload}
        with self._lock:
            f = self._files.get(path)
            if f is None:
                path.parent.mkdir(parents=True, exist_ok=True)
                f = self._files[path] = open(path, "a", encoding="utf-8")
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            self.rows[kind] += 1

    # -- silver ---------------------------------------------------------------------
    def compact(self) -> dict[str, int]:
        """Rebuild silver/<kind>.parquet from all bronze files. Cheap at lab scale (a few MB)."""
        out: dict[str, int] = {}
        with self._lock:
            for f in self._files.values():
                f.flush()
        con = duckdb.connect()
        for kind in KINDS:
            glob = str(self.root / "bronze" / "*" / f"{kind}.jsonl")
            target = self.root / "silver" / f"{kind}.parquet"
            try:
                n = con.execute(f"SELECT count(*) FROM read_json_auto('{glob}', union_by_name=true)").fetchone()[0]
                if n == 0:
                    continue
                con.execute(f"COPY (SELECT DISTINCT * FROM read_json_auto('{glob}', union_by_name=true) ORDER BY recv_ts) "
                            f"TO '{target}' (FORMAT PARQUET)")
                out[kind] = int(n)
            except duckdb.Error as e:
                if "No files found" not in str(e):
                    log.warning("compact %s failed: %s", kind, e)
        con.close()
        return out

    # -- queries ------------------------------------------------------------------------
    def history(self, room: str, sensor_type: str, minutes: int, level: str = "level0",
                until: str | None = None, max_age_s: float | None = None) -> list[dict[str, Any]]:
        """Readings of one sensor in the `minutes` sim-minutes up to `until`, straight from bronze, by sim_ts.

        Without `until` the window ends at the latest stored reading. That is only right while the
        simulated clock moves forward: after the clock jumps back or a simulated day is replayed, the
        "latest" reading belongs to another run, even another date (found 10 Oct: at sim 08:30 on 21 Oct
        this returned 22 Oct 10:07-10:37). Callers that know the time (the planner) therefore pass
        `until` = their own sim time and `max_age_s`, which keeps only rows received in the last
        max_age_s wall seconds, so rows from an earlier replay of the same sim times are ignored."""
        glob = str(self.root / "bronze" / "*" / "sensor.jsonl")
        filt, params = "room = ? AND type = ? AND level = ?", [room, sensor_type, level]
        if max_age_s:
            filt += " AND CAST(recv_ts AS TIMESTAMPTZ) >= CAST(? AS TIMESTAMPTZ)"
            params.append((datetime.now(timezone.utc) - timedelta(seconds=float(max_age_s))).isoformat())
        if until:
            anchor = "SELECT CAST(? AS TIMESTAMPTZ) AS latest"
            params.append(until)
        else:
            anchor = "SELECT max(CAST(sim_ts AS TIMESTAMPTZ)) AS latest FROM r"
        params.append(minutes)
        con = duckdb.connect()
        try:
            con.execute("SET TimeZone = 'UTC'")      # naive timestamps in bronze are UTC, on every host
            rows = con.execute(
                f"""WITH r AS (SELECT * FROM read_json_auto('{glob}', union_by_name=true) WHERE {filt}),
                         m AS ({anchor})
                    SELECT sim_ts, ts, value, seq, quality FROM r, m
                    WHERE CAST(sim_ts AS TIMESTAMPTZ) >= m.latest - INTERVAL (?) MINUTE
                      AND CAST(sim_ts AS TIMESTAMPTZ) <= m.latest
                    ORDER BY sim_ts""", params).fetchall()
        except duckdb.Error as e:
            if "No files found" in str(e):
                return []
            raise
        finally:
            con.close()
        return [{"sim_ts": r[0], "ts": r[1], "value": r[2], "seq": r[3], "quality": r[4]} for r in rows]

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Read-only SQL over bronze/silver for Grafana (Infinity) and ad-hoc analysis.
        Tables are exposed as views: sensor, actuator, plan, decision, health (bronze, live)."""
        if not sql.strip().lower().startswith(("select", "with")):
            raise ValueError("read-only endpoint: only SELECT/WITH queries are allowed")
        con = duckdb.connect()
        try:
            for kind in KINDS:
                glob = str(self.root / "bronze" / "*" / f"{kind}.jsonl")
                if list((self.root / "bronze").glob(f"*/{kind}.jsonl")):
                    con.execute(f"CREATE VIEW {kind} AS SELECT * FROM read_json_auto('{glob}', union_by_name=true)")
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchmany(10000)]
        finally:
            con.close()
