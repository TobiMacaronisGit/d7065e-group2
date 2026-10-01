"""physics — the truth layer. One container for all rooms (it *is* the building).

Every wall second it advances the model by `factor` simulated seconds (clock from occupancysim),
using the head count from BuildSim's occupancy map and the actuator states read back from BuildSim.
That read-back is what closes the control loop: a command only changes the next reading if the
physics sees the actuator state in BuildSim.

Exposes the ground truth over its own REST API (GET /rooms, GET /rooms/{room}); sensor processes
poll it and degrade it. Control never reads this API — that boundary is deployment (network), not
just policy, see docs/architecture.md.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from common import config
from common.buildsim import BuildSim, head_counts
from common.clock import SimClock
from common.http import make_app, run_in_thread, serve, setup_logging
from physics.model import RoomState, outdoor_temperature, params_from_config, step

log = logging.getLogger("physics")

TICK_S = 1.0          # wall seconds per model tick
POLL_S = 2.0          # wall seconds between BuildSim reads (occupancy + actuators)


class Physics:
    def __init__(self) -> None:
        self.cfg = config.load()
        self.rooms = config.rooms(self.cfg)
        self.level = self.cfg["level"]
        self.kinds = [a["kind"] for a in self.cfg["actuators"]]
        self.initial = {a["kind"]: float(a["initial"]) for a in self.cfg["actuators"]}
        self.bs = BuildSim()
        self.clock = SimClock()
        self.params = {r.name: params_from_config(self.cfg, r.area_m2, r.height_m) for r in self.rooms}
        self.state = {r.name: RoomState(co2_ppm=self.cfg["physics"]["co2_outdoor_ppm"], temp_c=19.0) for r in self.rooms}
        self.occupants = {r.name: 0 for r in self.rooms}
        self.actuators = {r.name: dict(self.initial) for r in self.rooms}      # kind -> state
        self.buildsim_ok = False
        self.t_out = 0.0
        self.sim_ts = self.clock.iso()
        self._lock = threading.Lock()
        self._last_poll = 0.0

    # -- BuildSim reads -----------------------------------------------------------------
    def poll_buildsim(self) -> None:
        try:
            occ = self.bs.occupancy()
            counts = head_counts(occ, [r.key for r in self.rooms])
            for r in self.rooms:
                self.occupants[r.name] = counts.get(r.key, 0)
            for r in self.rooms:
                for kind in self.kinds:
                    a = self.bs.get_actuator(config.actuator_id(r.name, kind))
                    self.actuators[r.name][kind] = float(a["state"])
            self.buildsim_ok = True
        except (httpx.HTTPError, ValueError, KeyError) as e:
            if self.buildsim_ok:
                log.warning("BuildSim read failed (%s) — holding last occupancy/actuator states", e)
            self.buildsim_ok = False

    # -- model tick ---------------------------------------------------------------------
    def tick(self, wall_dt: float) -> None:
        now = self.clock.now()
        dt = self.clock.sim_dt(wall_dt)
        if dt <= 0:
            return
        self.t_out = outdoor_temperature(now.timetuple().tm_yday, now.hour + now.minute / 60, **self.cfg["physics"]["outdoor"])
        with self._lock:
            for r in self.rooms:
                a = self.actuators[r.name]
                self.state[r.name] = step(self.params[r.name], self.state[r.name], self.occupants[r.name],
                                          a.get("vent", 0.0), a.get("heat", 17.0), self.t_out, dt)
            self.sim_ts = now.isoformat(timespec="seconds")

    def snapshot(self, room: str) -> dict:
        s, a = self.state[room], self.actuators[room]
        return {
            "room": room, "level": self.level, "sim_ts": self.sim_ts, "clock_degraded": self.clock.degraded,
            "co2_ppm": round(s.co2_ppm, 1), "temp_c": round(s.temp_c, 2), "occupants": self.occupants[room],
            "vent_level": a.get("vent"), "setpoint_c": a.get("heat"), "heater_w": round(s.heater_w),
            "energy_kwh": round(s.energy_kwh, 3), "t_out_c": round(self.t_out, 1), "buildsim_ok": self.buildsim_ok,
        }

    def run(self) -> None:
        last = time.monotonic()
        while True:
            time.sleep(TICK_S)
            now = time.monotonic()
            if now - self._last_poll >= POLL_S:
                self._last_poll = now
                self.poll_buildsim()
            self.tick(now - last)
            last = now


def main() -> None:
    setup_logging()
    phys = Physics()
    log.info("physics for %s rooms on %s: %s", len(phys.rooms), phys.level, [r.name for r in phys.rooms])
    run_in_thread(phys.run, "physics-loop")

    app = make_app("physics", lambda: {"status": "ok" if phys.buildsim_ok else "degraded",
                                       "buildsim_ok": phys.buildsim_ok, "clock_degraded": phys.clock.degraded,
                                       "sim_ts": phys.sim_ts})

    @app.get("/rooms")
    def rooms():
        return [phys.snapshot(r.name) for r in phys.rooms]

    @app.get("/rooms/{room}")
    def room(room: str):
        if room not in phys.state:
            from fastapi import HTTPException
            raise HTTPException(404, f"unknown room {room}")
        return phys.snapshot(room)

    serve(app)


if __name__ == "__main__":
    main()
