"""Unit tests for the control rules (run: pytest control/)."""
from datetime import datetime, timedelta, timezone

from control.rules import RoomController

CFG = {"co2_safety_ppm": 1200, "co2_high_ppm": 1000, "co2_raise_ppm": 800, "co2_hysteresis_ppm": 100,
       "min_change_interval_sim_s": 300, "stale_after_sim_s": 300, "frozen_after_samples": 4,
       "setpoint_occupied_c": 21.0, "setpoint_empty_c": 17.0, "vent_min_level": 0}
T0 = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)


def reading(value, t, seq=1):
    return {"value": value, "sim_ts": t.isoformat(), "seq": seq}


def ctl():
    return RoomController("level0", "A109", CFG)


def test_no_data_ventilates_safely_and_heats_for_people():
    d = ctl().decide(T0)
    assert d.state == "NO_DATA" and d.vent == 2 and d.setpoint_c == 21.0


def test_reactive_levels_and_safety_override():
    c = ctl()
    c.observe("occupancy", reading(30, T0))
    c.observe("co2", reading(650, T0))
    assert c.decide(T0).vent == 0
    c.observe("co2", reading(850, T0, 2))
    assert c.decide(T0).vent == 1
    c.observe("co2", reading(1050, T0, 3))
    assert c.decide(T0).vent == 2
    c.observe("co2", reading(1300, T0, 4))
    d = c.decide(T0)
    assert d.state == "SAFETY" and d.vent == 3


def test_hysteresis_blocks_early_step_down():
    c = ctl()
    c.observe("occupancy", reading(30, T0))
    c.observe("co2", reading(1050, T0, 1))
    assert c.decide(T0).vent == 2
    c.observe("co2", reading(950, T0 + timedelta(minutes=1), 2))     # below 1000 but inside the 100 ppm margin
    assert c.decide(T0 + timedelta(minutes=1)).vent == 2
    c.observe("co2", reading(850, T0 + timedelta(minutes=2), 3))     # margin ok, but dwell time (5 min) not yet
    assert c.decide(T0 + timedelta(minutes=2)).vent == 2
    c.observe("co2", reading(850, T0 + timedelta(minutes=6), 4))
    assert c.decide(T0 + timedelta(minutes=6)).vent == 1


def test_frozen_sensor_marks_room_degraded_and_uses_occupancy():
    c = ctl()
    c.observe("occupancy", reading(25, T0))
    for i in range(4):
        c.observe("co2", reading(700, T0 + timedelta(seconds=10 * i), i))
    d = c.decide(T0 + timedelta(seconds=40))
    assert d.state == "DEGRADED" and d.vent == 2 and d.inputs["co2_quality"] == "frozen"


def test_stale_co2_is_not_trusted():
    c = ctl()
    c.observe("co2", reading(600, T0))
    c.observe("occupancy", reading(0, T0 + timedelta(minutes=10)))
    d = c.decide(T0 + timedelta(minutes=10))
    assert d.state == "DEGRADED" and d.vent == 0 and d.setpoint_c == 17.0


def test_planner_can_raise_but_not_lower():
    c = ctl()
    c.observe("occupancy", reading(0, T0))
    c.observe("co2", reading(600, T0))
    c.set_plan({"sim_ts": T0.isoformat(), "horizon_min": 30, "suggested_vent": 1, "co2_forecast_max_ppm": 1100, "suggested_setpoint_c": 21.0})
    d = c.decide(T0)
    assert d.vent == 1 and d.setpoint_c == 21.0 and "pre-ventilate" in d.reason
    c.observe("co2", reading(1050, T0 + timedelta(minutes=1), 2))
    c.set_plan({"sim_ts": T0.isoformat(), "horizon_min": 30, "suggested_vent": 0, "co2_forecast_max_ppm": 500, "suggested_setpoint_c": 17.0})
    assert c.decide(T0 + timedelta(minutes=1)).vent == 2
