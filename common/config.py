"""Load config/rooms.json and derive device ids.

Naming convention (must match scripts/seed_buildsim.py and scripts/gen_compose.py):

    equipment id : <type>-<room>          e.g. co2-A109, temp-A109, vent-A109, heat-A109
    sensor id    : <room>-<type>          e.g. A109-co2, A109-temp, A109-occ
    actuator id  : <room>-<kind>          e.g. A109-vent, A109-heat
    compose svc  : sensor-<type>-<room>   e.g. sensor-co2-a109 (lower-case)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(os.getenv("ROOMS_CONFIG", "/app/config/rooms.json"))


@dataclass(frozen=True)
class Room:
    name: str
    role: str
    area_m2: float
    level: str
    height_m: float

    @property
    def key(self) -> str:  # canonical BuildSim room key
        return f"{self.level}/{self.name}"

    @property
    def volume_m3(self) -> float:
        return self.area_m2 * self.height_m


def load(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():  # allow running from the repo root without Docker
        alt = Path(__file__).resolve().parent.parent / "config" / "rooms.json"
        if alt.exists():
            p = alt
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def rooms(cfg: dict[str, Any] | None = None) -> list[Room]:
    cfg = cfg or load()
    return [
        Room(r["name"], r["role"], float(r["area_m2"]), cfg["level"], float(cfg["room_height_m"]))
        for r in cfg["rooms"]
    ]


def sensor_short(sensor_type: str) -> str:
    return {"co2": "co2", "temperature": "temp", "occupancy": "occ"}[sensor_type]


def sensor_id(room: str, sensor_type: str) -> str:
    return f"{room}-{sensor_short(sensor_type)}"


def actuator_id(room: str, kind: str) -> str:
    return f"{room}-{kind}"


def equipment_id(room: str, device: str) -> str:
    return f"{device}-{room}"


def env(key: str, default: str | None = None) -> str:
    v = os.getenv(key, default)
    if v is None:
        raise RuntimeError(f"missing environment variable {key}")
    return v
