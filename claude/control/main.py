"""control — the fast reactive loop (autonomous service #1).

Subscribes to every sensor stream and plan, evaluates each room every EVAL_S wall seconds with
`control.rules.RoomController`, publishes a Decision (always, for the audit trail / dashboard) and
an ActuatorCommand (only when the target changed — retained, so a restarted actuator catches up).

It never touches BuildSim. It survives restarts statelessly: after a restart it rebuilds its view
from the next readings (and the retained actuator states) within one sample interval.
"""
from __future__ import annotations

import logging
import threading
import time

from common import config, topics
from common.clock import SimClock
from common.http import make_app, run_in_thread, serve, setup_logging
from common.mqtt import Bus
from common.schemas import ActuatorCommand
from control.rules import RoomController

log = logging.getLogger("control")

EVAL_S = float(config.env("EVAL_S", "5"))


class Control:
    def __init__(self) -> None:
        self.cfg = config.load()
        self.level = self.cfg["level"]
        self.rooms = config.rooms(self.cfg)
        vent_max = next(a["max"] for a in self.cfg["actuators"] if a["kind"] == "vent")
        self.ctl = {r.name: RoomController(self.level, r.name, self.cfg["control"], vent_max=int(vent_max)) for r in self.rooms}
        self.clock = SimClock()
        self.bus = Bus("control")
        self.seq = 0
        self.commanded: dict[tuple[str, str], float] = {}
        self.last_decisions: dict[str, dict] = {}
        self._lock = threading.Lock()

    # -- inputs ---------------------------------------------------------------------
    def on_reading(self, topic: str, payload: dict) -> None:
        t = topics.parse(topic)
        c = self.ctl.get(t["room"])
        if c and t["level"] == self.level:
            with self._lock:
                c.observe(t["type"], payload)

    def on_plan(self, topic: str, payload: dict) -> None:
        parts = topic.split("/")                      # bldg/<level>/<room>/plan
        room = parts[2] if len(parts) >= 4 else payload.get("room")
        if room in self.ctl:
            with self._lock:
                self.ctl[room].set_plan(payload)

    # -- one evaluation round ------------------------------------------------------------
    def evaluate(self) -> None:
        now = self.clock.now()
        for r in self.rooms:
            with self._lock:
                d = self.ctl[r.name].decide(now)
            self.last_decisions[r.name] = d.to_dict()
            self.bus.publish(topics.decision(self.level, r.name), d.to_dict())
            self._command(r.name, "vent", float(d.vent), d.reason, d.sim_ts)
            self._command(r.name, "heat", float(d.setpoint_c), d.reason, d.sim_ts)

    def _command(self, room: str, kind: str, target: float, reason: str, sim_ts: str) -> None:
        if self.commanded.get((room, kind)) == target:
            return
        self.seq += 1
        cmd = ActuatorCommand(config.actuator_id(room, kind), self.level, room, kind, target, reason, "control", sim_ts, self.seq)
        self.bus.publish(topics.actuator_cmd(self.level, room, kind), cmd.to_dict(), retain=True)
        self.commanded[(room, kind)] = target
        log.info("%s %s → %s | %s", room, kind, target, reason)

    def run(self) -> None:
        self.bus.subscribe(f"bldg/{self.level}/+/sensor/+", self.on_reading)
        self.bus.subscribe(f"bldg/{self.level}/+/plan", self.on_plan)
        self.bus.start()
        self.bus.wait_connected(60)
        time.sleep(EVAL_S)          # let the first readings arrive
        while True:
            t0 = time.monotonic()
            try:
                self.evaluate()
                self.bus.health("ok" if not self.clock.degraded else "degraded", f"clock_degraded={self.clock.degraded}")
            except Exception:  # noqa: BLE001 — the loop must survive one bad round
                log.exception("evaluation round failed")
            time.sleep(max(0.0, EVAL_S - (time.monotonic() - t0)))


def main() -> None:
    setup_logging()
    ctl = Control()
    log.info("control for %s every %ss", [r.name for r in ctl.rooms], EVAL_S)
    run_in_thread(ctl.run, "control-loop")
    app = make_app("control", lambda: {"status": "ok", "rooms": {k: v["state"] for k, v in ctl.last_decisions.items()}})

    @app.get("/decisions")
    def decisions():
        return ctl.last_decisions

    serve(app)


if __name__ == "__main__":
    main()
