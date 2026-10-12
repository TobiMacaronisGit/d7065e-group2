"""Minimal BuildSim REST client (the only shared state of the system).

Facts to remember (L2 slides, docs/api):
  * sensor values and actuator states are STRINGS
  * PUT /api/sensors/{id}/value → 404 until the equipment exists (seed first)
  * PUT /api/occupancy, /api/room-layers, /api/alerts REPLACE the whole collection
  * rooms are keyed "<level>/<room>"
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

log = logging.getLogger("buildsim")


class BuildSim:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        self.base = (base_url or os.getenv("BUILDSIM_URL", "http://buildsim:9090")).rstrip("/")
        self._c = httpx.Client(base_url=self.base, timeout=timeout)

    # -- health ----------------------------------------------------------------
    def healthy(self) -> bool:
        try:
            return self._c.get("/healthz").status_code == 200
        except httpx.HTTPError:
            return False

    # -- building --------------------------------------------------------------
    def floor(self, level: str) -> dict[str, Any]:
        r = self._c.get(f"/api/building/floors/{level}")
        r.raise_for_status()
        return r.json()

    # -- equipment -------------------------------------------------------------
    def bulk_create(self, equipment: list[dict[str, Any]]) -> dict[str, Any]:
        r = self._c.post("/api/equipment/bulk", json=equipment)
        r.raise_for_status()
        return r.json()

    def equipment(self, eq_id: str) -> dict[str, Any]:
        r = self._c.get(f"/api/equipment/{eq_id}")
        r.raise_for_status()
        return r.json()

    # -- sensors / actuators ---------------------------------------------------
    def set_sensor(self, sensor_id: str, value: float | str, fmt: str = "{:.1f}") -> None:
        text = value if isinstance(value, str) else fmt.format(value)
        r = self._c.put(f"/api/sensors/{sensor_id}/value", json={"data_type": "text", "value": text})
        r.raise_for_status()

    def get_sensor(self, sensor_id: str) -> dict[str, Any]:
        r = self._c.get(f"/api/sensors/{sensor_id}")
        r.raise_for_status()
        return r.json()

    def set_actuator(self, actuator_id: str, state: float | str, fmt: str = "{:.1f}") -> None:
        text = state if isinstance(state, str) else fmt.format(state)
        r = self._c.put(f"/api/actuators/{actuator_id}/state", json={"state": text})
        r.raise_for_status()

    def get_actuator(self, actuator_id: str) -> dict[str, Any]:
        r = self._c.get(f"/api/actuators/{actuator_id}")
        r.raise_for_status()
        return r.json()

    # -- collections (whole-collection PUTs: ONE writer each) ------------------
    def occupancy(self) -> dict[str, Any]:
        r = self._c.get("/api/occupancy")
        r.raise_for_status()
        return r.json()

    def put_room_layers(self, layers: list[dict[str, Any]]) -> None:
        r = self._c.put("/api/room-layers", json=layers)
        r.raise_for_status()

    def put_alerts(self, alerts: list[dict[str, Any]]) -> None:
        r = self._c.put("/api/alerts", json=alerts[:100])
        r.raise_for_status()


    # -- self-registration -------------------------------------------------------------------
    def ensure(self, record: dict[str, Any]) -> bool:
        """Register one equipment record if it does not exist yet (bulk create is idempotent).
        Devices call this at start-up and again after a 404, so a restarted BuildSim (empty
        in-memory state) is re-populated by the devices themselves — no central seed needed."""
        try:
            res = self.bulk_create([record])
            if res.get("created"):
                log.info("registered %s in BuildSim", record["id"])
            return True
        except httpx.HTTPError as e:
            log.warning("register %s failed: %s", record["id"], e)
            return False


def sensor_record(room: str, level: str, sensor_type: str, sensor_id: str, unit: str, initial: str) -> dict[str, Any]:
    eq_type = {"co2": "co2_sensor", "temperature": "temperature_sensor", "occupancy": "occupancy_counter"}[sensor_type]
    short = {"co2": "co2", "temperature": "temp", "occupancy": "occ"}[sensor_type]
    return {"id": f"{short}-{room}", "name": f"{sensor_type} {room}", "type": eq_type, "category": "monitoring",
            "level": level, "room": room, "status": "running",
            "sensors": [{"id": sensor_id, "name": sensor_type, "type": sensor_type, "data_type": "text", "unit": unit, "value": initial}],
            "actuators": []}


def actuator_record(room: str, level: str, kind: str, actuator_id: str, bs_type: str, initial: str) -> dict[str, Any]:
    eq_type = {"vent": "ventilation_fan", "heat": "radiator"}.get(kind, "generic")
    return {"id": f"{kind}-{room}", "name": f"{kind} {room}", "type": eq_type, "category": "hvac",
            "level": level, "room": room, "status": "running", "sensors": [],
            "actuators": [{"id": actuator_id, "name": kind, "type": bs_type, "state": initial}]}


def head_counts(occupancy: dict[str, Any], keys: list[str]) -> dict[str, int]:
    """Reduce the whole-building occupancy map to {room_key: persons} for our rooms."""
    return {k: len((occupancy.get(k) or {}).get("persons", [])) for k in keys}
