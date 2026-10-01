"""Unit tests for command validation and rate-limited travel (run: pytest actuator/)."""
from datetime import datetime, timedelta, timezone

from actuator.device import Device

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)


def vent() -> Device:
    return Device("A109-vent", "vent", lo=0, hi=3, rate_per_s=0.5, state=0.0)


def cmd(**kw) -> dict:
    base = {"actuator_id": "A109-vent", "issued_by": "control", "target": 2,
            "ts": NOW.isoformat(), "seq": 1, "reason": "test"}
    base.update(kw)
    return base


def test_accepts_a_valid_command():
    d = vent()
    assert d.apply(cmd(), NOW) is None
    assert d.target == 2 and d.rejected == 0


def test_rejects_unauthorised_issuer():
    d = vent()
    assert "unauthorised" in d.apply(cmd(issued_by="planner"), NOW)
    assert d.target == 0 and d.rejected == 1, "a rejected command must not move the target"


def test_rejects_out_of_range_and_non_numeric_target():
    d = vent()
    assert "outside" in d.apply(cmd(target=99), NOW)
    assert "outside" in d.apply(cmd(target=-1), NOW)
    assert "numeric" in d.apply(cmd(target="high"), NOW)
    assert d.rejected == 3


def test_rejects_stale_command():
    d = vent()
    old = cmd(ts=(NOW - timedelta(minutes=10)).isoformat())
    assert "stale" in d.apply(old, NOW)


def test_rejects_command_for_another_actuator():
    assert "another actuator" in vent().apply(cmd(actuator_id="A110-vent"), NOW)


def test_duplicate_delivery_is_idempotent():
    d = vent()
    d.apply(cmd(seq=1), NOW)
    d.apply(cmd(seq=1), NOW)
    assert d.target == 2 and d.rejected == 0


def test_travel_is_rate_limited():
    d = vent()
    d.apply(cmd(target=3), NOW)
    d.move(1.0)
    assert d.state == 0.5, "0.5 level/s → after 1 s the damper is at 0.5, not at 3"
    for _ in range(10):
        d.move(1.0)
    assert d.state == 3 and not d.moving


def test_stuck_and_slow_faults():
    d = vent()
    d.apply(cmd(target=3), NOW)
    d.fault = "stuck"
    assert d.move(5.0) is False and d.state == 0.0
    d.fault = "slow"
    d.move(1.0)
    assert d.state == 0.125, "slow fault = quarter rate"
