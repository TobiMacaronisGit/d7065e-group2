"""planner — the slow predictive loop (autonomous service #2).

Every PLAN_S wall seconds, per room:
  1. pull the last 2 h of occupancy + the latest CO₂/temperature from the pipeline (history API)
  2. forecast occupancy for the next 30 min (trained linear model, else persistence baseline)
  3. roll the CO₂ mass balance forward for each ventilation level → smallest level that stays < limit
  4. publish a Plan (retained) — control may raise ventilation/setpoint from it, never lower

Deliberately reads from the *pipeline*, not the broker: the planner is the consumer of history,
which is exactly what the data pipeline exists for (rubric C). If the pipeline is down the planner
publishes nothing new; control keeps running on the reactive rules (graceful degradation).
"""
from __future__ import annotations

import logging
import time

import httpx

from common import config, topics
from common.clock import SimClock
from common.http import make_app, run_in_thread, serve, setup_logging
from common.mqtt import Bus
from common.schemas import Plan
from physics.model import outdoor_temperature, params_from_config
from common.timeutil import parse_iso
from planner.forecast import HORIZONS_MIN, STEP_MIN, Model, persistence, suggest_vent

log = logging.getLogger("planner")

PLAN_S = float(config.env("PLAN_S", "10"))
HISTORY_MIN = 120


class Planner:
    def __init__(self) -> None:
        self.cfg = config.load()
        self.level = self.cfg["level"]
        self.rooms = config.rooms(self.cfg)
        self.params = {r.name: params_from_config(self.cfg, r.area_m2, r.height_m) for r in self.rooms}
        self.capacity = {r.name: max(4.0, r.area_m2 / 2 if r.role == "lecture" else r.area_m2 / 4 if r.role == "fika" else 2.0) for r in self.rooms}
        self.vent_max = int(next(a["max"] for a in self.cfg["actuators"] if a["kind"] == "vent"))
        self.limit = self.cfg["control"]["co2_high_ppm"] - self.cfg["control"]["co2_hysteresis_ppm"]
        self.pipeline = config.env("PIPELINE_URL", "http://pipeline:8000").rstrip("/")
        self.model = Model.load()
        self.clock = SimClock()
        self.bus = Bus("planner")
        self.last_plans: dict[str, dict] = {}
        self._c = httpx.Client(timeout=5.0)

    def history(self, room: str, sensor_type: str, minutes: int) -> list[dict]:
        r = self._c.get(f"{self.pipeline}/history", params={"room": room, "type": sensor_type, "minutes": minutes, "level": self.level})
        r.raise_for_status()
        return r.json()

    @staticmethod
    def bins(rows: list[dict], n_bins: int = HISTORY_MIN // STEP_MIN + 1) -> list[float]:
        """Resample readings to 5-min bins (last value per bin); pad with the first value."""
        if not rows:
            return [0.0] * n_bins

        end = parse_iso(rows[-1]["sim_ts"])
        out = []
        for i in range(n_bins - 1, -1, -1):
            cutoff = end.timestamp() - i * STEP_MIN * 60
            vals = [r["value"] for r in rows if parse_iso(r["sim_ts"]).timestamp() <= cutoff]
            out.append(float(vals[-1]) if vals else float(rows[0]["value"]))
        return out

    def plan_room(self, room: str) -> Plan | None:
        occ_rows = self.history(room, "occupancy", HISTORY_MIN)
        co2_rows = self.history(room, "co2", 10)
        temp_rows = self.history(room, "temperature", 10)
        if not occ_rows or not co2_rows:
            return None
        now = self.clock.now()
        series = self.bins(occ_rows)
        mod = now.hour * 60 + now.minute
        cap = self.capacity[room]
        if self.model:
            occ_fc = self.model.predict(series, mod, cap)
            version = self.model.version
        else:
            occ_fc = persistence(series, cap)
            version = "persistence-baseline"
        co2_now = float(co2_rows[-1]["value"])
        temp_now = float(temp_rows[-1]["value"]) if temp_rows else 21.0
        t_out = outdoor_temperature(now.timetuple().tm_yday, now.hour + now.minute / 60, **self.cfg["physics"]["outdoor"])
        level, peak = suggest_vent(self.params[room], co2_now, temp_now, occ_fc, self.limit, self.vent_max,
                                   self.cfg["control"]["setpoint_occupied_c"], t_out)
        pre_heat = any(n >= 1 for n in occ_fc)
        setpoint = self.cfg["control"]["setpoint_occupied_c"] if pre_heat else self.cfg["control"]["setpoint_empty_c"]
        return Plan(self.level, room, max(HORIZONS_MIN), [round(v, 1) for v in occ_fc], round(peak, 1), level, setpoint,
                    version, now.isoformat(timespec="seconds"))

    def run(self) -> None:
        self.bus.start()
        self.bus.wait_connected(60)
        while True:
            t0 = time.monotonic()
            ok = True
            for r in self.rooms:
                try:
                    plan = self.plan_room(r.name)
                    if plan:
                        self.last_plans[r.name] = plan.to_dict()
                        self.bus.publish(topics.plan(self.level, r.name), plan.to_dict(), retain=True)
                except (httpx.HTTPError, ValueError, KeyError) as e:
                    ok = False
                    log.warning("plan for %s failed: %s", r.name, e)
            self.bus.health("ok" if ok else "degraded", f"model={self.model.version if self.model else 'persistence'}")
            time.sleep(max(0.0, PLAN_S - (time.monotonic() - t0)))


def main() -> None:
    setup_logging()
    p = Planner()
    log.info("planner: model=%s, limit=%s ppm, every %ss", p.model.version if p.model else "persistence", p.limit, PLAN_S)
    run_in_thread(p.run, "planner-loop")
    app = make_app("planner", lambda: {"status": "ok", "model": p.model.version if p.model else "persistence-baseline"})

    @app.get("/plans")
    def plans():
        return p.last_plans

    serve(app)


if __name__ == "__main__":
    main()
