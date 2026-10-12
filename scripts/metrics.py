#!/usr/bin/env python3
"""metrics.py: evidence for the test plan, computed from the pipeline (not from logs).

Standard library only, so it runs anywhere:  python scripts/metrics.py <command> [options]

Commands (the IDs match docs/test-plan.md and docs/requirements.md)

  now                         wall time and simulated time, to log when you inject a fault
  report   [--date D]         S1 / E1 / E2 / E3 metrics per room: comfort band (FR-02), CO2 over the
                              limit and excursions (FR-01, FR-04), actuator changes and gaps (NFR-03),
                              decision states, heater energy from physics (NFR-04)
  compare  A.json B.json      two saved reports side by side (E1 energy, E2 hysteresis, E3 planner)
  setback  --room R [--date D] after each occupied-to-empty change, is the room set back in time (FR-03)
  fault    --room R --since T first DEGRADED decision after an injection time (F1, NFR-05)
  loss                        readings received against expected per sensor (F3, F4, NFR-07)
  latency  [--last-minutes N] median and p95 decision interval per room (E4, NFR-01), optional docker stats

Typical use
  python scripts/metrics.py report --label full-system --json results/s1.json
  python scripts/metrics.py report --label no-planner  --json results/e3.json
  python scripts/metrics.py compare results/e3.json results/s1.json

Every table is markdown, so it can be pasted into docs/architecture.md (sections 7 and 8).

Notes on what is measured
  * CO2 and temperature are the OBSERVED sensor values (lag 30 s, noise), not the physics truth.
  * Durations are simulated minutes: each reading lasts until the next one; gaps longer than three
    times the normal spacing (a dead sensor, a restart) are cut to that length and counted.
  * "Occupied" means the latest occupancy reading at that time is above zero.
  * Energy comes from physics (GET /rooms, energy_kwh) at the moment of the call and resets when
    physics restarts, so take it just before stopping a run.
  * /query returns at most 10,000 rows; the script warns when it hits that limit. Use --date to
    limit a report to one simulated day.
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import statistics
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

ROW_LIMIT = 10000
SAFE = re.compile(r"^[A-Za-z0-9_.:+\-]+$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def parse_ts(text: str) -> float:
    """ISO-8601 string to epoch seconds (UTC if no offset is given)."""
    d = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def safe(value: str, what: str) -> str:
    if not SAFE.match(value):
        raise SystemExit(f"invalid {what}: {value!r}")
    return value


def quantile(values: list[float], q: float) -> float:
    xs = sorted(values)
    if not xs:
        return float("nan")
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def table(headers: list[str], rows: list[list]) -> str:
    def cell(x):
        if x is None:
            return "n/a"
        if isinstance(x, float):
            return f"{x:.1f}"
        return str(x)
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def verdict(ok: bool | None) -> str:
    return "n/a" if ok is None else ("pass" if ok else "FAIL")


class Pipeline:
    def __init__(self, url: str, verbose: bool = False) -> None:
        self.url = url.rstrip("/")
        self.verbose = verbose

    def query(self, sql: str, optional: bool = False) -> list[dict]:
        if self.verbose:
            print(f"SQL: {sql}", file=sys.stderr)
        url = f"{self.url}/query?" + urllib.parse.urlencode({"sql": sql})
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                rows = json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            if optional:
                print(f"warning: query failed ({e.code}): {body}", file=sys.stderr)
                return []
            raise SystemExit(f"the pipeline rejected a query ({e.code}): {body}\n  SQL: {sql}")
        except urllib.error.URLError as e:
            raise SystemExit(f"cannot reach the pipeline at {self.url} ({e.reason}). Is the stack up (make up)?")
        if len(rows) >= ROW_LIMIT:
            print(f"warning: {ROW_LIMIT} rows returned, the result may be truncated; use --date", file=sys.stderr)
        return rows


def date_clause(day: str | None) -> str:
    if not day:
        return ""
    if not DATE.match(day):
        raise SystemExit(f"--date must look like 2026-09-21, got {day!r}")
    nxt = date.fromisoformat(day) + timedelta(days=1)
    return f" AND sim_ts >= '{day}' AND sim_ts < '{nxt.isoformat()}'"


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)


# ---------------------------------------------------------------------------------------------
# per-room analysis
# ---------------------------------------------------------------------------------------------
def series(p: Pipeline, room: str, sensor_type: str, where_date: str) -> list[tuple[float, float]]:
    rows = p.query(f"SELECT sim_ts, value FROM sensor WHERE room='{room}' AND type='{sensor_type}'{where_date} ORDER BY sim_ts")
    out: dict[float, float] = {}
    for r in rows:
        if r.get("value") is not None and r.get("sim_ts"):
            out[parse_ts(r["sim_ts"])] = float(r["value"])
    return sorted(out.items())


def spacing_cap(ser: list[tuple[float, float]]) -> float:
    diffs = [b[0] - a[0] for a, b in zip(ser, ser[1:]) if b[0] > a[0]]
    return max(3 * statistics.median(diffs), 60.0) if diffs else 120.0


def room_metrics(p: Pipeline, room: str, where_date: str, limit: float, band: tuple[float, float], long_min: float) -> dict:
    co2 = series(p, room, "co2", where_date)
    temp = series(p, room, "temperature", where_date)
    occ = series(p, room, "occupancy", where_date)
    otimes = [t for t, _ in occ]
    ovals = [v for _, v in occ]

    def occupied(t: float) -> bool:
        i = bisect.bisect_right(otimes, t) - 1
        return i >= 0 and ovals[i] > 0

    # CO2 over the limit, peak, excursions
    cap = spacing_cap(co2)
    over_all = over_occ = 0.0
    gaps = 0
    for (t, v), (t2, _) in zip(co2, co2[1:]):
        dt = t2 - t
        if dt > cap:
            gaps += 1
            dt = cap
        if v > limit:
            over_all += dt
            if occupied(t):
                over_occ += dt
    peak_all = max((v for _, v in co2), default=None)
    occ_vals = [v for t, v in co2 if occupied(t)]
    peak_occ = max(occ_vals, default=None)

    durations: list[float] = []
    open_end = False
    start = None
    for t, v in co2:
        if v > limit and start is None:
            start = t
        elif v <= limit and start is not None:
            durations.append(t - start)
            start = None
    if start is not None:
        durations.append(co2[-1][0] - start)
        open_end = True

    # comfort band while occupied
    capt = spacing_cap(temp)
    occ_min = band_min = 0.0
    for (t, v), (t2, _) in zip(temp, temp[1:]):
        dt = min(t2 - t, capt)
        if occupied(t):
            occ_min += dt
            if band[0] <= v <= band[1]:
                band_min += dt

    return {
        "samples": {"co2": len(co2), "temperature": len(temp), "occupancy": len(occ)},
        "gaps": gaps,
        "occupied_min": occ_min / 60,
        "in_band_min": band_min / 60,
        "comfort_pct": (100 * band_min / occ_min) if occ_min > 0 else None,
        "over_all_min": over_all / 60,
        "over_occ_min": over_occ / 60,
        "peak_all_ppm": peak_all,
        "peak_occ_ppm": peak_occ,
        "excursions": len(durations),
        "longest_excursion_min": (max(durations) / 60) if durations else 0.0,
        "excursions_long": sum(1 for d in durations if d > long_min * 60),
        "open_excursion": open_end,
    }


def actuator_metrics(p: Pipeline, where_date: str, gap_min: float) -> dict:
    rows = p.query("SELECT actuator_id, kind, room, seq, sim_ts FROM actuator WHERE issued_by IS NOT NULL"
                   f"{where_date} ORDER BY sim_ts", optional=True)
    seen: set = set()
    per: dict[str, dict] = {}
    for r in rows:
        key = (r["actuator_id"], r.get("seq"), r["sim_ts"])      # retained redelivery repeats a command
        if key in seen:
            continue
        seen.add(key)
        d = per.setdefault(r["actuator_id"], {"room": r.get("room"), "kind": r.get("kind"), "times": []})
        d["times"].append(parse_ts(r["sim_ts"]))
    out = {}
    for aid, d in sorted(per.items()):
        ts = sorted(d["times"])
        gaps = [b - a for a, b in zip(ts, ts[1:])]
        out[aid] = {
            "room": d["room"], "kind": d["kind"], "changes": len(ts),
            "min_gap_min": (min(gaps) / 60) if gaps else None,
            "gaps_under": sum(1 for g in gaps if g < gap_min * 60),
        }
    return out


def decision_counts(p: Pipeline, where_date: str) -> dict:
    rows = p.query(f"SELECT room, state, count(*) AS n FROM decision WHERE 1=1{where_date} GROUP BY room, state ORDER BY room, state",
                   optional=True)
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r["room"], {})[r["state"]] = int(r["n"])
    return out


def physics_energy(url: str):
    try:
        rooms = get_json(url.rstrip("/") + "/rooms")
        return {r["room"]: float(r["energy_kwh"]) for r in rooms}, rooms[0].get("sim_ts") if rooms else None
    except (urllib.error.URLError, ValueError, KeyError, IndexError, TimeoutError) as e:
        print(f"warning: no energy figures, physics not reachable at {url} ({e})", file=sys.stderr)
        return None, None


# ---------------------------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------------------------
def cmd_now(args) -> None:
    print(f"wall (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    try:
        rooms = get_json(args.physics.rstrip("/") + "/rooms")
        print(f"simulated : {rooms[0]['sim_ts']}   (clock_degraded={rooms[0].get('clock_degraded')})")
    except (urllib.error.URLError, ValueError, KeyError, IndexError, TimeoutError) as e:
        print(f"simulated : unavailable, physics not reachable at {args.physics} ({e})")


def cmd_report(args) -> None:
    p = Pipeline(args.url, args.verbose)
    where = date_clause(args.date)
    rooms = [r["room"] for r in p.query("SELECT DISTINCT room FROM sensor ORDER BY room")]
    if not rooms:
        raise SystemExit("no sensor data in the pipeline yet")
    band = (args.band[0], args.band[1])
    per_room = {r: room_metrics(p, r, where, args.limit, band, args.long_min) for r in rooms}
    acts = actuator_metrics(p, where, args.gap_min)
    states = decision_counts(p, where)
    energy, phys_ts = physics_energy(args.physics)

    occ_min = sum(m["occupied_min"] for m in per_room.values())
    in_band = sum(m["in_band_min"] for m in per_room.values())
    peaks = [m["peak_occ_ppm"] for m in per_room.values() if m["peak_occ_ppm"] is not None]
    totals = {
        "occupied_min": occ_min,
        "in_band_min": in_band,
        "comfort_pct": (100 * in_band / occ_min) if occ_min > 0 else None,
        "over_occ_min": sum(m["over_occ_min"] for m in per_room.values()),
        "over_all_min": sum(m["over_all_min"] for m in per_room.values()),
        "peak_occ_ppm": max(peaks) if peaks else None,
        "excursions": sum(m["excursions"] for m in per_room.values()),
        "excursions_long": sum(m["excursions_long"] for m in per_room.values()),
        "commands": sum(a["changes"] for a in acts.values()),
        "gaps_under": sum(a["gaps_under"] for a in acts.values()),
        "energy_kwh": sum(energy.values()) if energy else None,
    }
    report = {
        "label": args.label, "date": args.date, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "limit_ppm": args.limit, "band": list(band), "gap_min": args.gap_min, "long_min": args.long_min,
        "physics_sim_ts": phys_ts, "rooms": per_room, "actuators": acts, "decision_states": states,
        "energy_kwh": energy, "totals": totals,
    }

    print(f"### Run `{args.label}`" + (f", simulated day {args.date}" if args.date else ", all recorded data"))
    print()
    print(f"Per room (limit {args.limit:g} ppm, comfort band {band[0]:g} to {band[1]:g} °C):\n")
    rows = []
    for r, m in per_room.items():
        rows.append([r, m["occupied_min"], m["comfort_pct"], m["over_occ_min"], m["peak_occ_ppm"], m["excursions"],
                     m["longest_excursion_min"], m["excursions_long"], (energy or {}).get(r) if energy else None])
    rows.append(["all", totals["occupied_min"], totals["comfort_pct"], totals["over_occ_min"], totals["peak_occ_ppm"],
                 totals["excursions"], None, totals["excursions_long"], totals["energy_kwh"]])
    print(table(["Room", "Occupied sim-min", "In band %", "CO₂ over limit, occupied (sim-min)", "Peak CO₂ occupied (ppm)",
                 "Excursions", "Longest (sim-min)", f"Over {args.long_min:g} sim-min", "Heater kWh"], rows))
    print()
    print(f"Actuator target changes (NFR-03, gap threshold {args.gap_min:g} sim-min):\n")
    print(table(["Actuator", "Room", "Kind", "Changes", "Shortest gap (sim-min)", "Gaps under threshold"],
                [[a, v["room"], v["kind"], v["changes"], v["min_gap_min"], v["gaps_under"]] for a, v in acts.items()]
                + [["all", None, None, totals["commands"], None, totals["gaps_under"]]]))
    print()
    print("Decision rows by state:\n")
    names = ["NORMAL", "DEGRADED", "SAFETY", "NO_DATA"]
    print(table(["Room"] + names, [[r] + [states.get(r, {}).get(n, 0) for n in names] for r in rooms]))
    print()
    gaps = {r: m["gaps"] for r, m in per_room.items() if m["gaps"]}
    if gaps:
        print(f"Data gaps cut to the normal spacing (CO₂): {gaps}\n")
    if any(m["open_excursion"] for m in per_room.values()):
        print("Note: a room was still over the limit at the end of the data; its excursion is a lower bound.\n")

    print("Checks against docs/requirements.md:\n")
    checks = [
        ["FR-01", f"no excursion longer than {args.long_min:g} sim-min", f"{totals['excursions_long']} long of {totals['excursions']}",
         verdict(totals["excursions_long"] == 0 if totals["excursions"] is not None else None)],
        ["FR-02", "at least 90 % of occupied sim-min in band", None if totals["comfort_pct"] is None else f"{totals['comfort_pct']:.1f} %",
         verdict(None if totals["comfort_pct"] is None else totals["comfort_pct"] >= 90)],
        ["NFR-03", f"no gap under {args.gap_min:g} sim-min (SAFETY excepted)", f"{totals['gaps_under']} gaps",
         "pass" if totals["gaps_under"] == 0 else "check each against SAFETY decisions"],
    ]
    print(table(["Requirement", "Criterion", "Measured", "Verdict"], checks))
    print()
    print("FR-03 (setback in empty rooms) is checked per room with the `setback` command.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)
        print(f"\nSaved {args.json}")


def cmd_compare(args) -> None:
    a = json.load(open(args.a, encoding="utf-8"))
    b = json.load(open(args.b, encoding="utf-8"))
    ta, tb = a["totals"], b["totals"]
    print(f"### `{a['label']}` (A) against `{b['label']}` (B)\n")

    def delta(x, y):
        if x is None or y is None:
            return None
        return f"{(y - x):+.1f}" + (f" ({100 * (y - x) / x:+.0f} %)" if x else "")
    rows = []
    for key, name in [("occupied_min", "Occupied sim-min"), ("comfort_pct", "In band %"), ("over_occ_min", "CO₂ over limit, occupied (sim-min)"),
                      ("peak_occ_ppm", "Peak CO₂ occupied (ppm)"), ("excursions", "Excursions"), ("excursions_long", "Long excursions"),
                      ("commands", "Actuator target changes"), ("gaps_under", "Gaps under threshold"), ("energy_kwh", "Heater kWh")]:
        rows.append([name, ta.get(key), tb.get(key), delta(ta.get(key), tb.get(key))])
    print(table(["Metric", f"A {a['label']}", f"B {b['label']}", "B minus A"], rows))
    print()
    checks = []
    if ta.get("over_occ_min"):
        red = 100 * (ta["over_occ_min"] - tb["over_occ_min"]) / ta["over_occ_min"]
        checks.append(["FR-04 (E3)", "B has at least 50 % fewer exceedance sim-min than A (A = reactive only)", f"{red:.0f} % fewer", verdict(red >= 50)])
    else:
        checks.append(["FR-04 (E3)", "B has at least 50 % fewer exceedance sim-min than A", "A has no exceedance to reduce", "n/a"])
    if ta.get("energy_kwh") is not None and tb.get("energy_kwh") is not None:
        checks.append(["NFR-04 (E1)", "energy of the full system at most the baseline (A = baseline)", f"{tb['energy_kwh']:.1f} against {ta['energy_kwh']:.1f} kWh",
                       verdict(tb["energy_kwh"] <= ta["energy_kwh"])])
    checks.append(["NFR-03 (E2)", "fewer actuator changes with hysteresis (A = hysteresis off)", f"{tb['commands']} against {ta['commands']}", verdict(tb["commands"] <= ta["commands"])])
    print(table(["Experiment", "Criterion", "Measured", "Verdict"], checks))
    print("\nUse only the checks that match the pair you compared; the others are not meaningful for it.")


def cmd_setback(args) -> None:
    p = Pipeline(args.url, args.verbose)
    room = safe(args.room, "room")
    occ = series(p, room, "occupancy", date_clause(args.date))
    events = [t1 for (t0, v0), (t1, v1) in zip(occ, occ[1:]) if v0 > 0 and v1 <= 0]
    print(f"### Setback after the room empties: {room} (FR-03)\n")
    if not events:
        print("No change from occupied to empty found in the recorded occupancy.")
        return
    rows = []
    for t in events:
        decs = p.query(f"SELECT sim_ts, vent, setpoint_c FROM decision WHERE room='{room}' "
                       f"AND sim_ts >= '{iso(t)}' AND sim_ts <= '{iso(t + args.within * 60)}' ORDER BY sim_ts")
        hit = next((d for d in decs if d.get("vent") is not None and d.get("setpoint_c") is not None
                    and float(d["vent"]) <= args.vent_min and float(d["setpoint_c"]) <= args.setpoint), None)
        delay = (parse_ts(hit["sim_ts"]) - t) / 60 if hit else None
        rows.append([iso(t), hit["sim_ts"] if hit else "never within the window", delay,
                     verdict(delay is not None and delay <= args.within)])
    print(table(["Room emptied at", "Vent at most " + f"{args.vent_min:g}" + " and setpoint at most " + f"{args.setpoint:g}" + " °C at",
                 "Delay (sim-min)", f"Within {args.within:g} sim-min"], rows))


def cmd_fault(args) -> None:
    p = Pipeline(args.url, args.verbose)
    room, state, since = safe(args.room, "room"), safe(args.state, "state"), safe(args.since, "--since")
    rows = p.query(f"SELECT sim_ts, state, reason FROM decision WHERE room='{room}' AND state='{state}' AND sim_ts > '{since}' ORDER BY sim_ts LIMIT 1")
    print(f"### Detection of a fault in {room}, injected at {since}\n")
    if not rows:
        print(table(["First decision in state", "Detected at", "Delay (sim-min)", "Criterion", "Verdict", "Reason"],
                    [[state, "not detected", None, f"within {args.within:g} sim-min", "FAIL", None]]))
        return
    delay = (parse_ts(rows[0]["sim_ts"]) - parse_ts(since)) / 60
    print(table(["First decision in state", "Detected at", "Delay (sim-min)", "Criterion", "Verdict", "Reason"],
               [[state, rows[0]["sim_ts"], delay, f"within {args.within:g} sim-min", verdict(delay <= args.within), rows[0].get("reason")]]))


def cmd_loss(args) -> None:
    p = Pipeline(args.url, args.verbose)
    base = p.query("SELECT sensor_id, count(*) AS n, count(DISTINCT seq) AS received, min(seq) AS first_seq, max(seq) AS last_seq "
                   "FROM sensor GROUP BY sensor_id ORDER BY sensor_id")
    resets = {r["sensor_id"]: int(r["resets"]) for r in p.query(
        "SELECT sensor_id, count(*) AS resets FROM (SELECT sensor_id, seq, lag(seq) OVER (PARTITION BY sensor_id ORDER BY recv_ts) AS prev "
        "FROM sensor) AS s WHERE prev IS NOT NULL AND seq < prev GROUP BY sensor_id", optional=True)}
    rows = []
    for r in base:
        rs = resets.get(r["sensor_id"], 0)
        expected = int(r["last_seq"]) - int(r["first_seq"]) + 1
        if rs:
            rows.append([r["sensor_id"], r["n"], r["received"], None, None, f"restarted {rs}x: seq starts again, compare per segment"])
        else:
            rows.append([r["sensor_id"], r["n"], r["received"], expected, expected - int(r["received"]), "ok" if expected == int(r["received"]) else "missing readings"])
    print("### Readings received against expected (sequence numbers)\n")
    print(table(["Sensor", "Rows", "Distinct seq", "Expected", "Missing", "Note"], rows))
    print("\nA sensor that was killed restarts its `seq` from 1, so judge loss only on sensors that kept running "
          "(for example the pipeline outage F3, or the broker outage F4).")


def cmd_latency(args) -> None:
    p = Pipeline(args.url, args.verbose)
    where = ""
    if args.last_minutes:
        since = (datetime.now(timezone.utc) - timedelta(minutes=args.last_minutes)).isoformat(timespec="milliseconds")
        where = f" WHERE recv_ts >= '{since}'"
    inner = (f"SELECT room, epoch(CAST(recv_ts AS TIMESTAMPTZ)) - lag(epoch(CAST(recv_ts AS TIMESTAMPTZ))) "
             f"OVER (PARTITION BY room ORDER BY recv_ts) AS dt FROM decision{where}")
    per_room = p.query(f"SELECT room, count(*) AS n, median(dt) AS med, quantile_cont(dt, 0.95) AS p95, max(dt) AS mx "
                       f"FROM ({inner}) AS d WHERE dt IS NOT NULL GROUP BY room ORDER BY room")
    overall = p.query(f"SELECT count(*) AS n, median(dt) AS med, quantile_cont(dt, 0.95) AS p95, max(dt) AS mx FROM ({inner}) AS d WHERE dt IS NOT NULL")
    rows = [[r["room"], r["n"], r["med"], r["p95"], r["mx"]] for r in per_room]
    if overall and overall[0]["n"]:
        o = overall[0]
        rows.append(["all", o["n"], o["med"], o["p95"], o["mx"]])
        ok = o["med"] is not None and float(o["med"]) <= 60
    else:
        ok = None
    print("### Decision interval per room (wall seconds)\n")
    print(table(["Room", "Intervals", "Median (s)", "p95 (s)", "Max (s)"], rows))
    print(f"\nNFR-01: median at most 60 s wall under full load: {verdict(ok)}")
    if args.docker:
        print("\n### Container resources (docker stats, one sample)\n")
        try:
            out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}"],
                                 capture_output=True, text=True, timeout=60, check=True).stdout
            stats = [line.split("|") for line in out.splitlines() if line.strip()]
            print(table(["Container", "Memory", "CPU"], stats))
            imgs = subprocess.run(["docker", "images", "--format", "{{.Repository}}|{{.Size}}"],
                                  capture_output=True, text=True, timeout=60, check=True).stdout
            mine = [line.split("|") for line in imgs.splitlines() if line.startswith("d7065e-group2")]
            if mine:
                print("\nImage sizes (D-01):\n")
                print(table(["Image", "Size"], mine))
        except (OSError, subprocess.SubprocessError) as e:
            print(f"docker stats not available: {e}")


# ---------------------------------------------------------------------------------------------
def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default="http://localhost:8092", help="pipeline base URL (host port 8092)")
    common.add_argument("--physics", default="http://localhost:8090", help="physics base URL (host port 8090)")
    common.add_argument("-v", "--verbose", action="store_true", help="print every SQL statement to stderr")

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("now", parents=[common], help="wall time and simulated time").set_defaults(fn=cmd_now)

    r = sub.add_parser("report", parents=[common], help="S1/E1/E2/E3 metrics per room")
    r.add_argument("--label", default="run", help="name of the run, for example full-system or no-planner")
    r.add_argument("--date", help="limit to one simulated day, for example 2026-09-21")
    r.add_argument("--limit", type=float, default=1000.0, help="CO2 limit in ppm (FR-01)")
    r.add_argument("--band", type=float, nargs=2, default=[20.0, 24.0], metavar=("LOW", "HIGH"), help="comfort band in °C (FR-02)")
    r.add_argument("--gap-min", type=float, default=5.0, help="minimum gap between changes in sim-min (NFR-03)")
    r.add_argument("--long-min", type=float, default=10.0, help="longest allowed excursion in sim-min (FR-01)")
    r.add_argument("--json", help="save the report for `compare`")
    r.set_defaults(fn=cmd_report)

    c = sub.add_parser("compare", help="compare two saved reports")
    c.add_argument("a", help="baseline report (json)")
    c.add_argument("b", help="report under test (json)")
    c.set_defaults(fn=cmd_compare)

    sb = sub.add_parser("setback", parents=[common], help="setback after a room empties (FR-03)")
    sb.add_argument("--room", required=True)
    sb.add_argument("--date", help="limit to one simulated day")
    sb.add_argument("--within", type=float, default=15.0, help="criterion in sim-min (FR-03)")
    sb.add_argument("--vent-min", type=float, default=0.0, help="minimum ventilation level (control.vent_min_level)")
    sb.add_argument("--setpoint", type=float, default=17.0, help="setback setpoint in °C (control.setpoint_empty_c)")
    sb.set_defaults(fn=cmd_setback)

    f = sub.add_parser("fault", parents=[common], help="detection delay after a fault injection")
    f.add_argument("--room", required=True)
    f.add_argument("--since", required=True, help="simulated injection time, from `metrics.py now`")
    f.add_argument("--state", default="DEGRADED")
    f.add_argument("--within", type=float, default=10.0, help="criterion in sim-min (NFR-05)")
    f.set_defaults(fn=cmd_fault)

    sub.add_parser("loss", parents=[common], help="readings received against expected per sensor").set_defaults(fn=cmd_loss)

    lt = sub.add_parser("latency", parents=[common], help="decision interval per room (E4)")
    lt.add_argument("--last-minutes", type=float, help="only the last N wall minutes")
    lt.add_argument("--docker", action="store_true", help="also print docker stats and image sizes")
    lt.set_defaults(fn=cmd_latency)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
