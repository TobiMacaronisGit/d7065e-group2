"""Actuator logic without I/O: command validation and rate-limited travel. Unit-testable.

Kept separate from main.py for the same reason as physics/model.py and control/rules.py — the
interesting behaviour (what gets rejected, how fast a damper moves) is testable without a broker,
BuildSim, or a network at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from common.timeutil import parse_iso

MAX_CMD_AGE_S = 120.0          # wall seconds; older commands are stale and must not be applied


@dataclass
class Device:
    actuator_id: str
    kind: str                  # vent | heat
    lo: float
    hi: float
    rate_per_s: float
    state: float
    target: float = 0.0
    fault: str = "none"        # none | stuck | slow
    rejected: int = 0

    def __post_init__(self) -> None:
        self.target = self.state

    # -- validation: the whole point of a separate actuator process ---------------------
    def validate(self, cmd: dict, now: datetime | None = None) -> str | None:
        """Return None if the command may be applied, otherwise the reason it is refused."""
        if cmd.get("issued_by") != "control":
            return f"unauthorised issuer {cmd.get('issued_by')!r}"
        if cmd.get("actuator_id") != self.actuator_id:
            return "command addressed to another actuator"
        try:
            target = float(cmd["target"])
        except (KeyError, TypeError, ValueError):
            return "target missing or not numeric"
        if not (self.lo <= target <= self.hi):
            return f"target {target} outside [{self.lo}, {self.hi}]"
        try:
            age = ((now or datetime.now(timezone.utc)) - parse_iso(cmd["ts"])).total_seconds()
        except (KeyError, TypeError, ValueError):
            return "missing or invalid ts"
        if age > MAX_CMD_AGE_S:
            return f"stale command ({age:.0f}s old)"
        # A duplicate delivery (QoS 1 = at-least-once) of an already applied command simply sets the
        # same target again: applying a command is idempotent, so no de-duplication is needed here.
        return None

    def apply(self, cmd: dict, now: datetime | None = None) -> str | None:
        err = self.validate(cmd, now)
        if err:
            self.rejected += 1
            return err
        self.target = float(cmd["target"])
        return None

    # -- motion ------------------------------------------------------------------------
    def move(self, dt_s: float) -> bool:
        """Travel towards the target at the rate limit. Returns True if the state changed."""
        if self.fault == "stuck":
            return False
        rate = self.rate_per_s / 4 if self.fault == "slow" else self.rate_per_s
        delta = self.target - self.state
        if abs(delta) < 1e-6:
            return False
        self.state = round(self.state + max(-rate * dt_s, min(rate * dt_s, delta)), 3)
        return True

    @property
    def moving(self) -> bool:
        return abs(self.target - self.state) > 1e-6
