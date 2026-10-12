"""Unit tests for the storage layer (run: pytest pipeline/)."""
import json
from datetime import datetime, timedelta, timezone

from pipeline.storage import Storage


def test_append_history_and_compact(tmp_path):
    s = Storage(str(tmp_path))
    for i in range(5):
        s.append("sensor", "bldg/level0/A109/sensor/co2",
                 {"sensor_id": "A109-co2", "level": "level0", "room": "A109", "type": "co2", "unit": "ppm",
                  "value": 600 + i, "sim_ts": f"2026-09-21T10:0{i}:00+00:00", "ts": f"2026-09-21T08:00:0{i}+00:00", "seq": i, "quality": "ok"})
    s.append("nonsense", "x", {})
    assert s.rows["sensor"] == 5 and s.rejected == 1
    h = s.history("A109", "co2", minutes=2)
    assert [r["value"] for r in h] == [602, 603, 604], "last 2 sim-minutes before the latest reading"
    assert s.compact()["sensor"] == 5
    assert (tmp_path / "silver" / "sensor.parquet").exists()
    rows = s.query("SELECT room, count(*) AS n FROM sensor GROUP BY room")
    assert rows == [{"room": "A109", "n": 5}]


def test_query_is_read_only(tmp_path):
    s = Storage(str(tmp_path))
    try:
        s.query("DROP TABLE sensor")
        assert False, "must reject non-SELECT"
    except ValueError:
        pass


def test_history_until_ignores_a_replayed_day(tmp_path):
    """Replay of 21 Oct: an earlier run already reached 18:00; the current run is at 08:00."""
    s = Storage(str(tmp_path))
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    f = tmp_path / "bronze" / "2026-10-21" / "sensor.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "w", encoding="utf-8") as fh:
        for i, hhmm in enumerate(["08:00", "08:01", "17:59", "18:00"]):
            fh.write(json.dumps({"topic": "t", "recv_ts": old, "sensor_id": "A109-occ", "level": "level0",
                                 "room": "A109", "type": "occupancy", "unit": "persons", "value": 0,
                                 "sim_ts": f"2026-10-21T{hhmm}:00+00:00", "ts": old, "seq": i, "quality": "ok"}) + "\n")
    for i, hhmm in enumerate(["07:58", "07:59", "08:00"]):
        s.append("sensor", "t", {"sensor_id": "A109-occ", "level": "level0", "room": "A109", "type": "occupancy",
                                 "unit": "persons", "value": 100 + i, "sim_ts": f"2026-10-21T{hhmm}:00+00:00",
                                 "ts": old, "seq": 10 + i, "quality": "ok"})
    # old behaviour: anchored at the latest stored reading (the earlier run's 18:00) -> wrong rows
    assert [r["value"] for r in s.history("A109", "occupancy", minutes=5)] == [0, 0]
    # fixed: anchored at our own sim time, rows of this run only
    h = s.history("A109", "occupancy", minutes=5, until="2026-10-21T08:00:00+00:00", max_age_s=600)
    assert [r["value"] for r in h] == [100, 101, 102]
