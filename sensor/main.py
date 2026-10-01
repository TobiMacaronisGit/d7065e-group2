"""sensor — one container per physical sensor (device layer).

Samples the ground truth from the physics API, degrades it like a real device would
(first-order lag, Gaussian noise, and injectable faults), then reports the observation twice:
  * PUT  BuildSim /api/sensors/{id}/value   → visible in the 3D viewer (the "device touching the air")
  * MQTT bldg/<level>/<room>/sensor/<type>   → the data pipeline and the autonomous services

Fault injection (for the evaluation, D-dimension): publish {"mode": "stuck"|"offline"|"drift"|"none"}
on sys/fault/<SENSOR_ID>  (scripts/inject_fault.sh).

Environment: SENSOR_ID ROOM LEVEL TYPE UNIT SAMPLE_S NOISE_SIGMA LAG_S PHYSICS_URL BUILDSIM_URL MQTT_HOST
"""
from __future__ import annotations

import logging
import math
import random
import time

import httpx

from common import topics
from common.buildsim import BuildSim, sensor_record
from common.config import env
from common.http import make_app, run_in_thread, serve, setup_logging
from common.mqtt import Bus
from common.schemas import SensorReading
from common.timeutil import seconds_between

log = logging.getLogger("sensor")

FIELD = {"co2": "co2_ppm", "temperature": "temp_c"}
FMT = {"co2": "{:.0f}", "temperature": "{:.1f}"}


class Sensor:
    def __init__(self) -> None:
        self.id = env("SENSOR_ID")
        self.room = env("ROOM")
        self.level = env("LEVEL", "level0")
        self.type = env("TYPE")
        self.unit = env("UNIT")
        self.sample_s = float(env("SAMPLE_S", "2"))
        self.sigma = float(env("NOISE_SIGMA", "0"))
        self.lag_s = float(env("LAG_S", "0"))          # simulated seconds
        self.drift_per_sim_h = float(env("DRIFT_PER_SIM_H", "50" if self.type == "co2" else "0.5"))
        self.physics = env("PHYSICS_URL", "http://physics:8000").rstrip("/")
        self.bs = BuildSim()
        self.bus = Bus(self.id)
        self.fault = "none"
        self.filtered: float | None = None
        self.last_sim_ts: str | None = None
        self.drift = 0.0
        self.seq = 0
        self.last_published: str | None = None
        self.buildsim_failures = 0
        self._c = httpx.Client(timeout=3.0)

    # -- fault injection --------------------------------------------------------
    def on_fault(self, _topic: str, payload: dict) -> None:
        mode = payload.get("mode", "none")
        if mode not in ("none", "stuck", "offline", "drift"):
            log.warning("ignoring unknown fault mode %r", mode)
            return
        log.warning("FAULT MODE → %s", mode)
        self.fault = mode
        if mode == "none":
            self.drift = 0.0

    # -- one sample -------------------------------------------------------------
    def sample(self) -> None:
        truth = self._c.get(f"{self.physics}/rooms/{self.room}").json()
        x = float(truth[FIELD[self.type]])
        sim_ts = truth["sim_ts"]
        # first-order lag in simulated time: y += (x - y)(1 - e^{-dt/τ})
        if self.filtered is None or self.lag_s <= 0:
            self.filtered = x
        else:
            dt = seconds_between(self.last_sim_ts, sim_ts)
            self.filtered += (x - self.filtered) * (1 - math.exp(-dt / self.lag_s))
        if self.fault == "drift":
            self.drift += self.drift_per_sim_h * seconds_between(self.last_sim_ts, sim_ts) / 3600
        self.last_sim_ts = sim_ts

        if self.fault == "offline":
            return                                   # a dead device reports nothing at all
        if self.fault == "stuck" and self.last_published is not None:
            value = float(self.last_published)      # frozen on a plausible value
        else:
            value = self.filtered + self.drift + random.gauss(0, self.sigma)
        self.seq += 1
        self.last_published = FMT[self.type].format(value)
        reading = SensorReading(self.id, self.level, self.room, self.type, self.unit, float(self.last_published), sim_ts, self.seq)
        self.bus.publish(topics.sensor(self.level, self.room, self.type), reading.to_dict())
        try:
            self.bs.set_sensor(self.id, self.last_published)
            self.buildsim_failures = 0
        except httpx.HTTPStatusError as e:
            self.buildsim_failures += 1
            if e.response.status_code == 404:        # BuildSim restarted (empty) → re-register ourselves
                self.register()
        except httpx.HTTPError as e:
            self.buildsim_failures += 1
            if self.buildsim_failures in (1, 10, 100):
                log.warning("BuildSim write failed (%s) — MQTT still flowing", e)

    def register(self) -> None:
        self.bs.ensure(sensor_record(self.room, self.level, self.type, self.id, self.unit, self.last_published or "0"))

    def run(self) -> None:
        self.bus.subscribe(topics.fault(self.id), self.on_fault)
        self.bus.start()
        self.bus.wait_connected(60)
        self.register()
        while True:
            t0 = time.monotonic()
            try:
                self.sample()
                self.bus.health("ok" if self.fault == "none" else "degraded", f"fault={self.fault}")
            except (httpx.HTTPError, KeyError, ValueError) as e:
                log.warning("sample failed: %s", e)
                self.bus.health("degraded", f"physics unreachable: {e}")
            time.sleep(max(0.0, self.sample_s - (time.monotonic() - t0)))


def main() -> None:
    setup_logging()
    s = Sensor()
    log.info("sensor %s (%s in %s/%s) every %ss, σ=%s, lag=%ss", s.id, s.type, s.level, s.room, s.sample_s, s.sigma, s.lag_s)
    run_in_thread(s.run, "sensor-loop")
    serve(make_app(s.id, lambda: {"status": "ok" if s.fault == "none" else "degraded", "fault": s.fault,
                                  "seq": s.seq, "last": s.last_published, "buildsim_failures": s.buildsim_failures}))


if __name__ == "__main__":
    main()
