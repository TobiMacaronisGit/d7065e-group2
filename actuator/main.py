"""actuator — one container per physical actuator (device layer).

The autonomous service never writes to BuildSim. It publishes a command; this process
  1. validates it (authority, range, freshness, type)      ← "proposing ≠ applying" (lab quickstart §3)
  2. travels towards the target at a limited rate           ← a damper takes time; the setpoint ramps
  3. writes the REACHED state to BuildSim (PUT /api/actuators/{id}/state)  ← the physics reads it back
  4. reports state on MQTT (retained) so control/planner/pipeline see what the device actually did

Commands are retained on the broker, so a restarted actuator recovers its last target immediately.
Fault injection: sys/fault/<ACTUATOR_ID>  {"mode": "stuck"|"slow"|"none"}.

The decision logic lives in actuator/device.py (no I/O) — this file is only the wiring.

Environment: ACTUATOR_ID ROOM LEVEL KIND BUILDSIM_TYPE MIN MAX RATE_PER_S INITIAL BUILDSIM_URL MQTT_HOST
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from actuator.device import Device
from common import topics
from common.buildsim import BuildSim, actuator_record
from common.config import env
from common.http import make_app, run_in_thread, serve, setup_logging
from common.mqtt import Bus
from common.schemas import ActuatorState

log = logging.getLogger("actuator")

TICK_S = 1.0
FMT = {"vent": "{:.1f}", "heat": "{:.1f}"}


class ActuatorService:
    def __init__(self) -> None:
        self.id = env("ACTUATOR_ID")
        self.room = env("ROOM")
        self.level = env("LEVEL", "level0")
        self.kind = env("KIND")
        self.bs_type = env("BUILDSIM_TYPE", "fan_speed")
        self.dev = Device(self.id, self.kind, float(env("MIN")), float(env("MAX")),
                          float(env("RATE_PER_S")), float(env("INITIAL", env("MIN"))))
        self.bs = BuildSim()
        self.bus = Bus(self.id)
        self.sim_ts = ""
        self._lock = threading.Lock()

    @property
    def text(self) -> str:
        return FMT.get(self.kind, "{:.1f}").format(self.dev.state)

    # -- inputs ------------------------------------------------------------------------
    def on_command(self, _topic: str, cmd: dict) -> None:
        with self._lock:
            err = self.dev.apply(cmd)
            if err is None:
                self.sim_ts = cmd.get("sim_ts", "")
        if err:
            log.warning("REJECTED command: %s | %s", err, cmd)
        else:
            log.info("target → %s (%s)", self.dev.target, cmd.get("reason", ""))

    def on_fault(self, _topic: str, payload: dict) -> None:
        mode = payload.get("mode", "none")
        if mode in ("none", "stuck", "slow"):
            log.warning("FAULT MODE → %s", mode)
            self.dev.fault = mode
        else:
            log.warning("ignoring unknown fault mode %r", mode)

    # -- outputs ------------------------------------------------------------------------
    def register(self) -> None:
        self.bs.ensure(actuator_record(self.room, self.level, self.kind, self.id, self.bs_type, self.text))

    def report(self) -> None:
        try:
            self.bs.set_actuator(self.id, self.text)
            ok = True
        except httpx.HTTPStatusError as e:
            ok = False
            if e.response.status_code == 404:        # BuildSim restarted with empty state → re-register
                self.register()
        except httpx.HTTPError as e:
            ok = False
            log.warning("BuildSim write failed: %s", e)
        st = ActuatorState(self.id, self.level, self.room, self.kind, self.dev.state, self.dev.target,
                           self.dev.moving, self.dev.fault, self.sim_ts)
        self.bus.publish(topics.actuator_state(self.level, self.room, self.kind), st.to_dict(), retain=True)
        self.bus.health("ok" if ok and self.dev.fault == "none" else "degraded",
                        f"fault={self.dev.fault} buildsim_ok={ok}")

    def run(self) -> None:
        self.bus.subscribe(topics.actuator_cmd(self.level, self.room, self.kind), self.on_command)
        self.bus.subscribe(topics.fault(self.id), self.on_fault)
        self.bus.start()
        self.bus.wait_connected(60)
        self.register()
        self.report()                    # announce initial state (and restore it after a restart)
        last = last_report = time.monotonic()
        while True:
            time.sleep(TICK_S)
            now = time.monotonic()
            with self._lock:
                changed = self.dev.move(now - last)
            last = now
            if changed or now - last_report > 10:
                self.report()
                last_report = now


def main() -> None:
    setup_logging()
    a = ActuatorService()
    log.info("actuator %s (%s in %s/%s) range [%s,%s] rate %s/s",
             a.id, a.kind, a.level, a.room, a.dev.lo, a.dev.hi, a.dev.rate_per_s)
    run_in_thread(a.run, "actuator-loop")
    serve(make_app(a.id, lambda: {"status": "ok" if a.dev.fault == "none" else "degraded",
                                  "state": a.dev.state, "target": a.dev.target,
                                  "fault": a.dev.fault, "rejected": a.dev.rejected}))


if __name__ == "__main__":
    main()
