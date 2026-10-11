"""Message schemas — every message that crosses a container boundary.

Every payload is JSON with explicit units. Two timestamps everywhere:
  ts      wall-clock ISO-8601 (what really happened when, for latency measurements)
  sim_ts  simulated-clock ISO-8601 (the building's time, 60x faster; for physics and evaluation)

Keep these dataclasses in sync with docs/interfaces.md — that file is the contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from common.timeutil import now_iso

__all__ = ["now_iso", "SensorReading", "ActuatorCommand", "ActuatorState", "Plan", "Decision", "Health"]


@dataclass
class SensorReading:
    sensor_id: str
    level: str
    room: str
    type: str          # co2 | temperature | occupancy
    unit: str          # ppm | °C | persons
    value: float
    sim_ts: str
    seq: int
    quality: str = "ok"   # ok | suspect (set by the device itself, e.g. offline recovery)
    ts: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActuatorCommand:
    actuator_id: str
    level: str
    room: str
    kind: str          # vent | heat
    target: float      # vent level 0..3 | heating setpoint °C
    reason: str
    issued_by: str     # control
    sim_ts: str
    seq: int
    ts: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActuatorState:
    actuator_id: str
    level: str
    room: str
    kind: str
    state: float       # reached value
    target: float      # what it is travelling towards
    moving: bool
    fault: str         # none | stuck | slow
    sim_ts: str
    ts: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    level: str
    room: str
    horizon_min: int
    occupancy_forecast: list[float]   # one value per 5 sim-min step
    co2_forecast_max_ppm: float
    suggested_vent: int
    suggested_setpoint_c: float
    model_version: str
    sim_ts: str
    ts: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Decision:
    level: str
    room: str
    state: str          # NORMAL | DEGRADED | SAFETY | NO_DATA
    vent: int
    setpoint_c: float
    reason: str
    inputs: dict[str, Any]   # the values the decision was based on (auditable)
    sim_ts: str
    ts: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Health:
    service: str
    status: str         # ok | degraded | down
    detail: str = ""
    ts: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
