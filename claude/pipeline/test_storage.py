"""Unit tests for the storage layer (run: pytest pipeline/)."""
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
