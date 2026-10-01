"""occupancy_counter — reads "who is in which room" from BuildSim and publishes a head count
per room as an ordinary sensor stream (bldg/<level>/<room>/sensor/occupancy) and as a BuildSim
sensor value (<room>-occ), so the control loop, the planner and the pipeline treat occupancy
exactly like CO₂ and temperature.

Why a separate process: BuildSim is the only shared state; occupancysim writes it, we read it.
Reading it once here (instead of in every consumer) keeps one integration point with the
whole-building occupancy map and gives the count its own fault domain.
"""
from __future__ import annotations

import logging
import time

import httpx

from common import config, topics
from common.buildsim import BuildSim, head_counts, sensor_record
from common.clock import SimClock
from common.http import make_app, run_in_thread, serve, setup_logging
from common.mqtt import Bus
from common.schemas import SensorReading

log = logging.getLogger("occupancy_counter")


class Counter:
    def __init__(self) -> None:
        self.cfg = config.load()
        self.rooms = config.rooms(self.cfg)
        self.level = self.cfg["level"]
        self.sample_s = float(config.env("SAMPLE_S", "2"))
        self.bs = BuildSim()
        self.clock = SimClock()
        self.bus = Bus("occupancy_counter")
        self.seq = 0
        self.last: dict[str, int] = {}
        self.ok = False

    def register(self) -> None:
        for r in self.rooms:
            self.bs.ensure(sensor_record(r.name, self.level, "occupancy", config.sensor_id(r.name, "occupancy"), "persons", "0"))

    def run(self) -> None:
        self.bus.start()
        self.bus.wait_connected(60)
        self.register()
        while True:
            t0 = time.monotonic()
            try:
                counts = head_counts(self.bs.occupancy(), [r.key for r in self.rooms])
                sim_ts = self.clock.iso()
                self.seq += 1
                for r in self.rooms:
                    n = counts.get(r.key, 0)
                    self.last[r.name] = n
                    reading = SensorReading(config.sensor_id(r.name, "occupancy"), self.level, r.name,
                                            "occupancy", "persons", float(n), sim_ts, self.seq)
                    self.bus.publish(topics.sensor(self.level, r.name, "occupancy"), reading.to_dict())
                    try:
                        self.bs.set_sensor(reading.sensor_id, str(n))
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 404:   # BuildSim restarted → re-register
                            self.register()
                    except httpx.HTTPError:
                        pass  # BuildSim down: MQTT is the primary path
                self.ok = True
                self.bus.health("ok")
            except (httpx.HTTPError, ValueError) as e:
                self.ok = False
                log.warning("occupancy read failed: %s", e)
                self.bus.health("degraded", str(e))
            time.sleep(max(0.0, self.sample_s - (time.monotonic() - t0)))


def main() -> None:
    setup_logging()
    c = Counter()
    run_in_thread(c.run, "counter-loop")
    serve(make_app("occupancy_counter", lambda: {"status": "ok" if c.ok else "degraded", "counts": c.last, "seq": c.seq}))


if __name__ == "__main__":
    main()
