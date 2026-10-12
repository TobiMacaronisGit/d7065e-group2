"""viewer — the single writer of BuildSim's overlay collections (room-layers, alerts).

BuildSim's 3D viewer is provided infrastructure; this process only maps *our* state into it:
  * room layers  : observed CO₂, observed temperature, occupancy (as the control system sees them)
  * alerts       : rooms that are not NORMAL (SAFETY / DEGRADED / NO_DATA) with the controller's reason,
                   plus services reported "down" by the broker's last-will
Both endpoints REPLACE their whole collection on every PUT, so exactly one process may own them.
That is the only reason this is a separate container.

Time series (Grafana) come from the pipeline, not from here.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from common import config
from common.buildsim import BuildSim
from common.http import make_app, run_in_thread, serve, setup_logging
from common.mqtt import Bus

log = logging.getLogger("viewer")

REFRESH_S = float(config.env("REFRESH_S", "2"))
SEVERITY = {"SAFETY": "critical", "DEGRADED": "warning", "NO_DATA": "warning"}


class Viewer:
    def __init__(self) -> None:
        self.cfg = config.load()
        self.level = self.cfg["level"]
        self.rooms = config.rooms(self.cfg)
        self.bs = BuildSim()
        self.bus = Bus("viewer")
        self.readings: dict[tuple[str, str], float] = {}     # (room, type) -> value
        self.decisions: dict[str, dict] = {}
        self.health: dict[str, dict] = {}
        self.ok = False
        self._lock = threading.Lock()

    def on_reading(self, topic: str, p: dict) -> None:
        with self._lock:
            self.readings[(p["room"], p["type"])] = float(p["value"])

    def on_decision(self, topic: str, p: dict) -> None:
        with self._lock:
            self.decisions[p["room"]] = p

    def on_health(self, topic: str, p: dict) -> None:
        with self._lock:
            self.health[topic.rsplit("/", 1)[-1]] = p

    def layers(self) -> list[dict]:
        def layer(id_, label, unit, t, lo, hi, palette):
            return {"id": id_, "label": label, "unit": unit, "source": "sensor estimate", "minimum": lo, "maximum": hi,
                    "opacity": 0.75, "palette": palette,
                    "values": {r.key: self.readings[(r.name, t)] for r in self.rooms if (r.name, t) in self.readings}}
        return [
            layer("co2", "Observed CO₂", "ppm", "co2", 400, 1400, ["#2563eb", "#22c55e", "#facc15", "#dc2626"]),
            layer("temperature", "Observed temperature", "°C", "temperature", 14, 26, ["#2563eb", "#22c55e", "#facc15", "#dc2626"]),
            layer("occupancy", "Occupancy", "persons", "occupancy", 0, 60, ["#e5e7eb", "#22c55e", "#dc2626"]),
        ]

    def alerts(self) -> list[dict]:
        out = []
        for room, d in self.decisions.items():
            if d["state"] in SEVERITY:
                out.append({"id": f"room-{room}", "severity": SEVERITY[d["state"]], "title": f"{room}: {d['state']}",
                            "message": d["reason"][:200], "level": self.level, "room": room})
        for svc, h in self.health.items():
            if h.get("status") == "down":
                out.append({"id": f"svc-{svc}", "severity": "warning", "title": f"service down: {svc}",
                            "message": "last will received from broker", "level": self.level})
        return out

    def push(self) -> None:
        with self._lock:
            layers, alerts = self.layers(), self.alerts()
        self.bs.put_room_layers(layers)
        self.bs.put_alerts(alerts)

    def run(self) -> None:
        self.bus.subscribe(f"bldg/{self.level}/+/sensor/+", self.on_reading)
        self.bus.subscribe(f"bldg/{self.level}/+/decision", self.on_decision)
        self.bus.subscribe("sys/health/+", self.on_health)
        self.bus.start()
        self.bus.wait_connected(60)
        while True:
            t0 = time.monotonic()
            try:
                self.push()
                self.ok = True
            except httpx.HTTPError as e:
                self.ok = False
                log.warning("BuildSim overlay write failed: %s", e)
            self.bus.health("ok" if self.ok else "degraded")
            time.sleep(max(0.0, REFRESH_S - (time.monotonic() - t0)))


def main() -> None:
    setup_logging()
    v = Viewer()
    run_in_thread(v.run, "viewer-loop")
    serve(make_app("viewer", lambda: {"status": "ok" if v.ok else "degraded", "alerts": len(v.alerts()),
                                     "services": {k: h.get("status") for k, h in v.health.items()}}))


if __name__ == "__main__":
    main()
