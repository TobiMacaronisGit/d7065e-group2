#!/usr/bin/env python3
"""One-shot setup after `docker compose up` (runs as the `seed` service, or by hand from the host):

  1. BuildSim: register every device from config/rooms.json (bulk, idempotent). The devices also
     register themselves on start, so this is only a convenience so the 3D viewer is complete at once.
  2. occupancysim: PUT /api/config with `room_roles` so that on level 0 ONLY our lecture rooms are
     lecture rooms (all other lecture-sized rooms become offices) → the timetable books lectures into
     A109/A117, and A110 is forced to be a fika room. Without this, the demo's 10:15 lecture would land
     in a random one of ~50 halls.

    python3 scripts/seed.py            (host: BUILDSIM_URL=http://127.0.0.1:9090 OCCUPANCY_URL=http://127.0.0.1:8081)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.buildsim import BuildSim, actuator_record, sensor_record  # noqa: E402
from common import config  # noqa: E402

BUILDSIM = os.getenv("BUILDSIM_URL", "http://127.0.0.1:9090")
OCCUPANCY = os.getenv("OCCUPANCY_URL", "http://127.0.0.1:8081")
M2_PER_UNIT2 = 0.25


def wait(url: str, name: str, tries: int = 60) -> None:
    for _ in range(tries):
        try:
            if httpx.get(url, timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit(f"{name} not reachable at {url}")


def seed_buildsim(cfg: dict) -> None:
    bs = BuildSim(BUILDSIM)
    level = cfg["level"]
    records = []
    for r in cfg["rooms"]:
        for s in cfg["sensors"]:
            sid = config.sensor_id(r["name"], s["type"])
            records.append(sensor_record(r["name"], level, s["type"], sid, s["unit"], "0"))
        records.append(sensor_record(r["name"], level, "occupancy", config.sensor_id(r["name"], "occupancy"), "persons", "0"))
        for a in cfg["actuators"]:
            records.append(actuator_record(r["name"], level, a["kind"], config.actuator_id(r["name"], a["kind"]), a["buildsim_type"], a["initial"]))
    res = bs.bulk_create(records)
    print(f"BuildSim: {res}")


def seed_occupancy(cfg: dict) -> None:
    level = cfg["level"]
    floor = httpx.get(f"{BUILDSIM}/api/building/floors/{level}", timeout=10).json()
    ours = {r["name"]: r["role"] for r in cfg["rooms"]}
    roles = {}
    for room in floor["rooms"]:
        if room.get("type") != "room":
            continue
        m2 = room["area"] * M2_PER_UNIT2
        if room["name"] in ours:
            roles[room["name"]] = ours[room["name"]]
        elif m2 >= 60:                       # every other lecture-sized room stops being a lecture room
            roles[room["name"]] = "office"
    roles.setdefault("A1123", "unused")
    roles.setdefault("A105", "unused")
    params = httpx.get(f"{OCCUPANCY}/api/config", timeout=10).json()
    params["room_roles"] = roles
    r = httpx.put(f"{OCCUPANCY}/api/config", json=params, timeout=30)
    r.raise_for_status()
    print(f"occupancysim: room_roles set for {len(roles)} rooms (ours: {ours})")


def main() -> None:
    cfg = config.load(ROOT / "config" / "rooms.json")
    wait(f"{BUILDSIM}/healthz", "BuildSim")
    seed_buildsim(cfg)
    wait(f"{OCCUPANCY}/healthz", "occupancysim")
    seed_occupancy(cfg)


if __name__ == "__main__":
    main()
