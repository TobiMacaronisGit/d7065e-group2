"""Compare the E3 runs (R1 no forecast / R2 persistence / R3 timetable) from the pipeline.

    python3 scripts/compare_runs.py [docs/results/e3-runs.txt] [--pipeline http://localhost:8092]

Reads the run log written by the run commands (lines "R1 <name> start|end YYYY-mm-dd HH:MM:SS" in
LOCAL time, followed after "end" by the physics /rooms JSON). For each run it selects pipeline rows by
wall-clock receive time (recv_ts) AND by simulated time 2026-10-21 07:30–18:00, so data from before the
clock jump is excluded. All metrics come from the pipeline (sensor readings, i.e. what the system saw),
resampled to one value per simulated minute; energy comes from the physics engine at the end of the run.

Metrics per room:
  occ_min      occupied sim-minutes (occupancy > 0)
  exceed_min   occupied sim-minutes with mean CO2 > 1000 ppm          (FR-01, FR-04)
  peak_co2     highest per-minute mean CO2 of the day (ppm)
  comfort_%    occupied sim-minutes with 20 <= T <= 24 degC            (FR-02)
  vent_changes how often control changed the commanded vent level      (NFR-03)
  planner_dec  decisions in which the planner raised ventilation
  heater_kwh   modelled room-heater energy (physics, since its restart)
  ahu_kwh      modelled AHU energy for heating supply air (0 for runs before 10 Oct 17:00, no AHU then)
  energy_kwh   heater_kwh + ahu_kwh                                     (NFR-04)
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DAY = "2026-10-21"
SIM_FROM, SIM_TO = f"{DAY} 07:30:00+00", f"{DAY} 18:00:00+00"
ROOMS = ["A109", "A117", "A110", "A323", "A113C"]
FOCUS = ["A109", "A117"]          # the lecture rooms of the test day
LINE = re.compile(r"^(R\d+)\s+(\S+)\s+(start|end)\s+(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s*$")


def to_utc(local: str) -> str:
    """'2026-10-10 14:25:01' in the machine's local time zone -> '2026-10-10 12:25:01+00'."""
    t = datetime.strptime(local, "%Y-%m-%d %H:%M:%S").astimezone().astimezone(timezone.utc)
    return t.strftime("%Y-%m-%d %H:%M:%S+00")


def parse_log(path: str) -> dict[str, dict]:
    runs: dict[str, dict] = {}
    lines = open(path, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        m = LINE.match(line.strip())
        if not m:
            continue
        rid, name, kind, ts = m.groups()
        r = runs.setdefault(rid, {"name": name})
        r[kind] = ts
        if kind == "end":
            for nxt in lines[i + 1:]:
                if nxt.strip().startswith("["):
                    r["physics"] = {d["room"]: d for d in json.loads(nxt)}
                    break
                if LINE.match(nxt.strip()):
                    break
    return {k: v for k, v in sorted(runs.items()) if "start" in v and "end" in v}


def query(base: str, sql: str) -> list[dict]:
    url = f"{base}/query?" + urllib.parse.urlencode({"sql": sql})
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read())


def window(run: dict) -> str:
    return (f"CAST(recv_ts AS TIMESTAMPTZ) BETWEEN TIMESTAMPTZ '{to_utc(run['start'])}' "
            f"AND TIMESTAMPTZ '{to_utc(run['end'])}' "
            f"AND CAST(sim_ts AS TIMESTAMPTZ) >= TIMESTAMPTZ '{SIM_FROM}' "
            f"AND CAST(sim_ts AS TIMESTAMPTZ) < TIMESTAMPTZ '{SIM_TO}'")


DAY_START_MIN = int(datetime.fromisoformat(f"{DAY}T07:30:00+00:00").timestamp() // 60)
DAY_END_MIN = int(datetime.fromisoformat(f"{DAY}T18:00:00+00:00").timestamp() // 60)


def hold(samples: dict[int, float]) -> dict[int, float]:
    """One value per sim-minute 07:30–18:00, last reading held until the next one."""
    out, last = {}, None
    if samples:
        last = samples[min(samples)]
    for m in range(DAY_START_MIN, DAY_END_MIN):
        if m in samples:
            last = samples[m]
        if last is not None:
            out[m] = last
    return out


def room_metrics(base: str, run: dict, room: str) -> dict:
    rows = query(base, f"""
        SELECT type, CAST(floor(epoch(CAST(sim_ts AS TIMESTAMPTZ)) / 60) AS BIGINT) AS m, avg(value) AS v, max(value) AS vmax
        FROM sensor WHERE room = '{room}' AND {window(run)}
        GROUP BY 1, 2""")
    raw_co2 = {r["m"]: r["v"] for r in rows if r["type"] == "co2"}
    # Sensors sample every 2 wall-s = 2 sim-min at factor 60, and the three streams are not aligned to the
    # same minutes. Hold the last reading (sample-and-hold) so every sim-minute of the day has a value.
    co2 = hold(raw_co2)
    temp = hold({r["m"]: r["v"] for r in rows if r["type"] == "temperature"})
    occ = hold({r["m"]: r["vmax"] for r in rows if r["type"] == "occupancy"})
    occupied = [m for m, n in occ.items() if n and n > 0]
    exceed = sum(1 for m in occupied if co2.get(m, 0) > 1000)
    comfort_n = sum(1 for m in occupied if m in temp and 20.0 <= temp[m] <= 24.0)
    comfort_d = sum(1 for m in occupied if m in temp)
    dec = query(base, f"""
        SELECT sum(CASE WHEN prev IS NOT NULL AND vent <> prev THEN 1 ELSE 0 END) AS changes,
               sum(CASE WHEN reason LIKE '%planner%' THEN 1 ELSE 0 END) AS planner
        FROM (SELECT vent, reason, lag(vent) OVER (ORDER BY recv_ts) AS prev
              FROM decision WHERE room = '{room}' AND {window(run)})""")
    d = dec[0] if dec else {}
    phys = run.get("physics", {}).get(room, {})
    return {
        "occ_min": len(occupied),
        "exceed_min": exceed,
        "peak_co2": round(max(co2.values())) if co2 else None,
        "comfort_%": round(100.0 * comfort_n / comfort_d, 1) if comfort_d else None,
        "vent_changes": int(d.get("changes") or 0),
        "planner_dec": int(d.get("planner") or 0),
        "heater_kwh": phys.get("energy_kwh"),
        "ahu_kwh": phys.get("ahu_kwh", 0.0) if phys else None,
        "energy_kwh": round((phys.get("energy_kwh") or 0) + (phys.get("ahu_kwh") or 0), 3) if phys else None,
        "minutes_co2": len(raw_co2),
    }


def fmt(v) -> str:
    return "–" if v is None else str(v)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    log = args[0] if args else "docs/results/e3-runs.txt"
    base = "http://localhost:8092"
    if "--pipeline" in sys.argv:
        base = sys.argv[sys.argv.index("--pipeline") + 1]
    runs = parse_log(log)
    if not runs:
        raise SystemExit(f"no complete runs in {log}")

    results = {rid: {room: room_metrics(base, run, room) for room in ROOMS} for rid, run in runs.items()}

    print(f"# E3 results — simulated day {DAY}, 07:30–18:00\n")
    print("| Run | Variant | Wall time (local) |\n|---|---|---|")
    for rid, run in runs.items():
        print(f"| {rid} | {run['name']} | {run['start']} → {run['end'][11:]} |")

    keys = ["occ_min", "exceed_min", "peak_co2", "comfort_%", "vent_changes", "planner_dec",
            "heater_kwh", "ahu_kwh", "energy_kwh"]
    for room in ROOMS:
        print(f"\n## {room}\n")
        print("| Metric | " + " | ".join(results) + " |")
        print("|---|" + "---|" * len(results))
        for k in keys:
            print(f"| {k} | " + " | ".join(fmt(results[r][room][k]) for r in results) + " |")

    print("\n## Summary (lecture rooms " + " + ".join(FOCUS) + "; energy: all rooms)\n")
    print("| Metric | " + " | ".join(results) + " |")
    print("|---|" + "---|" * len(results))
    for k in ["occ_min", "exceed_min", "vent_changes", "planner_dec"]:
        print(f"| {k} | " + " | ".join(str(sum(results[r][room][k] or 0 for room in FOCUS)) for r in results) + " |")
    print("| peak_co2 | " + " | ".join(fmt(max((results[r][room]['peak_co2'] or 0) for room in FOCUS)) for r in results) + " |")
    comf = []
    for r in results:
        num = sum((results[r][room]["comfort_%"] or 0) * results[r][room]["occ_min"] for room in FOCUS)
        den = sum(results[r][room]["occ_min"] for room in FOCUS)
        comf.append(fmt(round(num / den, 1) if den else None))
    print("| comfort_% | " + " | ".join(comf) + " |")
    print("| energy_kwh (all rooms) | " + " | ".join(
        fmt(round(sum(results[r][room]["energy_kwh"] or 0 for room in ROOMS), 1)) for r in results) + " |")
    print("\nData check — sim-minutes with a CO2 reading per room (sensors sample every 2 sim-min, expect ≈ 315): " + ", ".join(
        f"{r}: " + "/".join(str(results[r][room]["minutes_co2"]) for room in ROOMS) for r in results))


if __name__ == "__main__":
    main()
