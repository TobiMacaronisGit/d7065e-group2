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
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import duckdb

log = logging.getLogger("storage")

KINDS = ("sensor", "actuator", "plan", "decision", "health")
# bronze files touched up to this long before the last compaction are re-read for the live tail of /query;
# generous on purpose (a compaction takes seconds), rows already in silver are filtered out by recv_ts
FRESH_MARGIN_S = 600.0


class Storage:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or os.getenv("DATA_DIR", "/data"))
        for sub in ("bronze", "silver", "gold"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self._files: dict[Path, Any] = {}
        self._lock = threading.Lock()
        self._query_lock = threading.Lock()
        self.rows = {k: 0 for k in KINDS}
        self.rejected = 0

    @contextmanager
    def _connection(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Serialize scans so concurrent requests cannot multiply reader memory.

        Ingestion keeps using its own lock. The memory limit applies to DuckDB's
        buffers, not to total process memory.
        """
        with self._query_lock:
            con = duckdb.connect(config={"threads": 1, "memory_limit": "256MB"})
            try:
                yield con
            finally:
                con.close()

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
        with self._connection() as con:
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
        files = self._sensor_files(until, minutes)
        if not files:
            return []
        src = ", ".join(f"'{f}'" for f in files)
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
        try:
            with self._connection() as con:
                con.execute("SET TimeZone = 'UTC'")      # naive timestamps in bronze are UTC, on every host
                rows = con.execute(
                    f"""WITH r AS (SELECT * FROM read_json_auto([{src}], union_by_name=true) WHERE {filt}),
                             m AS ({anchor})
                        SELECT sim_ts, ts, value, seq, quality FROM r, m
                        WHERE CAST(sim_ts AS TIMESTAMPTZ) >= m.latest - INTERVAL (?) MINUTE
                          AND CAST(sim_ts AS TIMESTAMPTZ) <= m.latest
                        ORDER BY sim_ts""", params).fetchall()
        except duckdb.Error as e:
            if "No files found" in str(e):
                return []
            raise
        return [{"sim_ts": r[0], "ts": r[1], "value": r[2], "seq": r[3], "quality": r[4]} for r in rows]

    def _sensor_files(self, until: str | None, minutes: int) -> list[str]:
        """Bronze sensor files history() has to scan. With `until` only the sim-dates the window can touch
        (one extra day on each side, since bronze/<date>/ comes from the sim_ts string, offsets included)
        instead of every day ever recorded. Found 12 Oct: the planner calls history 15x per 10 s cycle;
        scanning all of bronze each time kept _query_lock busy and delayed every Grafana query by ~2 s."""
        everything = sorted(str(f) for f in (self.root / "bronze").glob("*/sensor.jsonl"))
        if not until:
            return everything                     # anchor = latest stored reading -> needs all days
        try:
            end = datetime.fromisoformat(until.replace("Z", "+00:00"))
        except ValueError:
            return everything
        day, last = (end - timedelta(minutes=minutes, days=1)).date(), (end + timedelta(days=1)).date()
        files = []
        while day <= last:
            f = self.root / "bronze" / day.isoformat() / "sensor.jsonl"
            if f.exists():
                files.append(str(f))
            day += timedelta(days=1)
        return files

    def _views(self, con: duckdb.DuckDBPyConnection, live: bool = True) -> None:
        """Create the views sensor, actuator, plan, decision, health for one /query request.

        Each view is silver Parquet plus, when `live`, the bronze rows that arrived after the last
        compaction. Only bronze files touched since that compaction are read, so the tail is one or two
        files, and it is parsed with the Parquet schema, so both halves have identical column types.
        A kind without Parquet yet (fresh start) is read from bronze directly."""
        for kind in KINDS:
            silver = self.root / "silver" / f"{kind}.parquet"
            bronze = sorted((self.root / "bronze").glob(f"*/{kind}.jsonl"))
            if not silver.exists():
                if bronze:
                    glob = str(self.root / "bronze" / "*" / f"{kind}.jsonl")
                    con.execute(f"CREATE OR REPLACE VIEW {kind} AS "
                                f"SELECT * FROM read_json_auto('{glob}', union_by_name=true)")
                continue
            body = f"SELECT * FROM read_parquet('{silver}')"
            since = silver.stat().st_mtime - FRESH_MARGIN_S
            fresh = [f for f in bronze if f.stat().st_mtime >= since] if live else []
            if fresh:
                schema = con.execute(f"DESCRIBE {body}").fetchall()
                cols = ", ".join("'{}': '{}'".format(r[0].replace("'", "''"), r[1].replace("'", "''")) for r in schema)
                files = ", ".join(f"'{f}'" for f in fresh)
                body += (f" UNION ALL BY NAME SELECT * FROM read_json([{files}], columns={{{cols}}}, "
                         f"format='newline_delimited', ignore_errors=true) "
                         f"WHERE recv_ts > (SELECT max(recv_ts) FROM read_parquet('{silver}'))")
            con.execute(f"CREATE OR REPLACE VIEW {kind} AS {body}")

    def _run(self, con: duckdb.DuckDBPyConnection, sql: str, live: bool) -> list[dict[str, Any]]:
        self._views(con, live)
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchmany(10000)]

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Read-only SQL for Grafana (Infinity) and ad-hoc analysis, live and fast.

        Views = silver Parquet + the bronze rows since the last compaction (see _views), so Grafana shows
        a reading as soon as the pipeline has it. History (12 Oct): views over *all* bronze JSONL took
        4-5 s per request at ~1.7 M rows and, behind _query_lock, queued the Grafana panels into Infinity
        timeouts; silver-only views were fast but up to COMPACT_S (300 s wall, ~5 sim-h) behind.
        If the live tail fails (e.g. a bronze row that does not fit the silver schema), the request is
        answered from silver only and the error is logged; the next compaction absorbs the row."""
        if not sql.strip().lower().startswith(("select", "with")):
            raise ValueError("read-only endpoint: only SELECT/WITH queries are allowed")
        with self._connection() as con:
            try:
                return self._run(con, sql, live=True)
            except duckdb.Error as e:
                log.warning("query: live bronze tail failed, answering from silver only: %s", e)
                return self._run(con, sql, live=False)
