"""Reactive control rules + safety clamps + degraded handling for ONE room. Pure logic, no I/O.

Layering (the two loops from L1):
  * SAFETY  — hard clamps nobody can override: CO₂ ≥ co2_safety_ppm → full ventilation; vent ≥ vent_min_level (REG-01)
  * REACTIVE — threshold rules with hysteresis on the way down (NFR-03: no thrashing), immediate on the way up
  * PLANNER  — a fresh plan may RAISE ventilation / setpoint ahead of time; it can never lower below the rules
  * DEGRADED — stale or frozen CO₂ → decide on occupancy instead; no occupancy either → "ventilate safely"

State machine (docs/diagrams/state.d2): NO_DATA → NORMAL ⇄ DEGRADED, NORMAL/DEGRADED → SAFETY → NORMAL.
Every decision carries the inputs it was based on and a human-readable reason (auditable, dashboard).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from common.timeutil import parse_iso
from common.schemas import Decision


@dataclass
class Observation:
    value: float
    sim_ts: datetime
    seq: int


@dataclass
class RoomController:
    level: str
    room: str
    cfg: dict                         # the "control" block of config/rooms.json
    vent_max: int = 3
    state: str = "NO_DATA"
    vent: int = 0
    setpoint: float = 17.0
    last_change: datetime | None = None
    co2: Observation | None = None
    temp: Observation | None = None
    occ: Observation | None = None
    plan: dict | None = None
    co2_history: deque = field(default_factory=lambda: deque(maxlen=64))

    # -- input ---------------------------------------------------------------------------------
    def observe(self, sensor_type: str, reading: dict) -> None:
        obs = Observation(float(reading["value"]), parse_iso(reading["sim_ts"]), int(reading.get("seq", 0)))
        if sensor_type == "co2":
            self.co2 = obs
            self.co2_history.append(obs.value)
        elif sensor_type == "temperature":
            self.temp = obs
        elif sensor_type == "occupancy":
            self.occ = obs

    def set_plan(self, plan: dict) -> None:
        self.plan = plan

    # -- data quality ------------------------------------------------------------------------------
    def _fresh(self, obs: Observation | None, now: datetime) -> bool:
        return obs is not None and (now - obs.sim_ts).total_seconds() <= self.cfg["stale_after_sim_s"]

    def co2_frozen(self) -> bool:
        n = self.cfg["frozen_after_samples"]
        if len(self.co2_history) < n:
            return False
        last = list(self.co2_history)[-n:]
        return max(last) == min(last)          # with σ=15 ppm noise, n identical samples never happens naturally

    def co2_quality(self, now: datetime) -> str:
        if not self._fresh(self.co2, now):
            return "stale" if self.co2 else "missing"
        if self.co2_frozen():
            return "frozen"
        return "ok"

    # -- decision ------------------------------------------------------------------------------
    def decide(self, now: datetime) -> Decision:
        c = self.cfg
        q = self.co2_quality(now)
        occ_known = self._fresh(self.occ, now)
        occupied = occ_known and self.occ.value > 0
        plan_ok = self.plan is not None and (now - parse_iso(self.plan["sim_ts"])).total_seconds() <= 2 * 60 * self.plan.get("horizon_min", 30)
        reasons: list[str] = []

        # 1. what does ventilation want to be?
        if q == "ok":
            co2 = self.co2.value
            if co2 >= c["co2_safety_ppm"]:
                state, want = "SAFETY", self.vent_max
                reasons.append(f"CO2 {co2:.0f} ≥ safety {c['co2_safety_ppm']} → full ventilation")
            else:
                state = "NORMAL"
                want = 2 if co2 >= c["co2_high_ppm"] else 1 if co2 >= c["co2_raise_ppm"] else 0
                reasons.append(f"CO2 {co2:.0f} → reactive level {want}")
                if plan_ok and self.plan["suggested_vent"] > want:
                    want = int(self.plan["suggested_vent"])
                    reasons.append(f"planner expects {self.plan['co2_forecast_max_ppm']:.0f} ppm in {self.plan['horizon_min']} min → pre-ventilate {want}")
        elif occ_known:
            state = "DEGRADED"
            want = 2 if occupied else 0
            reasons.append(f"CO2 {q} → estimate from occupancy {self.occ.value:.0f} → level {want}")
            if plan_ok and self.plan["suggested_vent"] > want:
                want = int(self.plan["suggested_vent"])
        else:
            state, want = "NO_DATA", 2
            reasons.append("no trustworthy CO2 and no occupancy → ventilate safely")

        # 2. hysteresis: stepping DOWN needs margin below the threshold that got us here + a minimum dwell time
        if want < self.vent and state != "SAFETY":
            dwell_ok = self.last_change is None or (now - self.last_change).total_seconds() >= c["min_change_interval_sim_s"]
            margin_ok = q != "ok" or self.co2.value < _threshold_for(self.vent, c) - c["co2_hysteresis_ppm"]
            if not (dwell_ok and margin_ok):
                reasons.append(f"hold {self.vent} (hysteresis)")
                want = self.vent

        # 3. safety clamps
        want = max(int(c["vent_min_level"]), min(self.vent_max, want))

        # 4. heating setpoint: occupied → comfort, empty → setback, planner may pre-heat
        setpoint = c["setpoint_occupied_c"] if occupied or state == "NO_DATA" else c["setpoint_empty_c"]
        if plan_ok and not occupied and self.plan.get("suggested_setpoint_c", 0) > setpoint:
            setpoint = float(self.plan["suggested_setpoint_c"])
            reasons.append("planner: pre-heat")

        if want != self.vent or setpoint != self.setpoint:
            self.last_change = now
        self.vent, self.setpoint, self.state = want, setpoint, state
        return Decision(self.level, self.room, state, want, setpoint, "; ".join(reasons),
                        {"co2": self.co2.value if self.co2 else None, "co2_quality": q,
                         "temp": self.temp.value if self.temp else None,
                         "occupancy": self.occ.value if occ_known else None,
                         "plan_vent": self.plan["suggested_vent"] if plan_ok else None},
                        now.isoformat(timespec="seconds"))


def _threshold_for(level: int, c: dict) -> float:
    return {0: -1e9, 1: c["co2_raise_ppm"], 2: c["co2_high_ppm"]}.get(level, c["co2_safety_ppm"])
