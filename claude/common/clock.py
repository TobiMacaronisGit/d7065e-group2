"""Simulated clock — occupancysim is the single time authority.

occupancysim (course tool) exposes GET /api/state with
    sim.clock.time     RFC3339 simulated time
    sim.clock.factor   simulated seconds per wall second (default 60)
    sim.clock.running  bool

`SimClock.now()` returns the simulated datetime. Between polls it extrapolates
with the last known factor, so callers can tick every second without hitting
occupancysim every second. If occupancysim is unreachable the clock keeps
extrapolating and reports `degraded=True` — the physics keeps stepping, the
report can show the drift.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

from common.timeutil import parse_iso

log = logging.getLogger("clock")


class SimClock:
    def __init__(self, url: str | None = None, poll_s: float = 5.0, fallback_factor: float = 60.0) -> None:
        self.url = (url or os.getenv("OCCUPANCY_URL", "http://occupancysim:8081")).rstrip("/")
        self.poll_s = poll_s
        self.factor = fallback_factor
        self.running = True
        self.degraded = True
        self._anchor_sim = datetime.now(timezone.utc).replace(hour=7, minute=30, second=0, microsecond=0)
        self._anchor_wall = time.monotonic()
        self._last_poll = 0.0
        self._c = httpx.Client(timeout=3.0)

    def _poll(self) -> None:
        self._last_poll = time.monotonic()
        try:
            st = self._c.get(f"{self.url}/api/state").json()
            clk = st["sim"]["clock"]
            self._anchor_sim = parse_iso(clk["time"])
            self._anchor_wall = time.monotonic()
            self.factor = float(clk.get("factor", self.factor))
            self.running = bool(clk.get("running", True))
            if self.degraded:
                log.info("clock synced to occupancysim: %s x%s", self._anchor_sim.isoformat(), self.factor)
            self.degraded = False
        except Exception as e:  # noqa: BLE001 — any failure means: extrapolate
            if not self.degraded:
                log.warning("occupancysim clock unreachable (%s) — extrapolating at x%s", e, self.factor)
            self.degraded = True

    def now(self) -> datetime:
        if time.monotonic() - self._last_poll > self.poll_s:
            self._poll()
        if not self.running:
            return self._anchor_sim
        return self._anchor_sim + timedelta(seconds=(time.monotonic() - self._anchor_wall) * self.factor)

    def sim_dt(self, wall_dt_s: float) -> float:
        """Simulated seconds that pass in `wall_dt_s` wall seconds."""
        return 0.0 if not self.running else wall_dt_s * self.factor

    def iso(self) -> str:
        return self.now().isoformat(timespec="seconds")
