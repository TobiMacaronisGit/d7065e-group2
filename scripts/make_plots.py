"""Figures for the report (§11), drawn from the pipeline — same data and time windows as compare_runs.py.

    pip install matplotlib
    python3 scripts/make_plots.py            # → docs/figures/*.png

  s1_A109.png, s1_A117.png   final system (R8 = S1): CO₂, vent level, temperature, occupancy over the day
  e3_planner_A117.png        planner off / persistence / timetable (R6 / R7 / R8) overlaid, A117
  f1_frozen_sensor.png       F1: A109 CO₂ sensor frozen at 08:30, room marked DEGRADED at 08:45

x-axis = simulated time of day (the runs replay 2026-10-21; wall time would stack runs on top of each other).
One y-axis per panel (CO₂, vent, temperature and occupancy are different units, so they are stacked, never
put on a second y-axis). Values are sensor readings — what the control system saw — held per sim-minute.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from compare_runs import DAY, parse_log, query, to_utc  # noqa: E402

PIPE = "http://localhost:8092"
OUT = "docs/figures"
INK, INK2, GRID, BAND = "#0b0b0b", "#52514e", "#e4e3df", "#e9e8e4"
SERIES = {"R6": "#2a78d6", "R7": "#eb6834", "R8": "#1baf7a"}          # validated categorical slots 1-3
NAMES = {"R6": "planner off", "R7": "persistence", "R8": "timetable"}
STYLE = {"R6": "-", "R7": "--", "R8": "-"}                             # secondary encoding besides color

plt.rcParams.update({
    "font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.titlesize": 9.5, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.titlelocation": "left", "legend.frameon": False, "figure.dpi": 100, "savefig.dpi": 200,
})


def minute(ts_iso: str) -> int:
    return int(datetime.fromisoformat(ts_iso).timestamp() // 60)


def window(w_from: str, w_to: str, sim_from: str, sim_to: str) -> str:
    return (f"CAST(recv_ts AS TIMESTAMPTZ) BETWEEN TIMESTAMPTZ '{w_from}' AND TIMESTAMPTZ '{w_to}' "
            f"AND CAST(sim_ts AS TIMESTAMPTZ) >= TIMESTAMPTZ '{sim_from}' AND CAST(sim_ts AS TIMESTAMPTZ) < TIMESTAMPTZ '{sim_to}'")


def series(room: str, win: str, m0: int, m1: int) -> dict[str, dict[int, float]]:
    """{co2|temperature|occupancy|vent: {sim-minute: value}} held per minute between m0 and m1."""
    rows = query(PIPE, f"""SELECT type, CAST(floor(epoch(CAST(sim_ts AS TIMESTAMPTZ)) / 60) AS BIGINT) AS m, avg(value) AS v
                           FROM sensor WHERE room = '{room}' AND {win} GROUP BY 1, 2""")
    vent = query(PIPE, f"""SELECT CAST(floor(epoch(CAST(sim_ts AS TIMESTAMPTZ)) / 60) AS BIGINT) AS m, avg(state) AS v
                           FROM actuator WHERE room = '{room}' AND kind = 'vent' AND {win} GROUP BY 1""")
    raw = {t: {r["m"]: r["v"] for r in rows if r["type"] == t} for t in ("co2", "temperature", "occupancy")}
    raw["vent"] = {r["m"]: r["v"] for r in vent}
    out = {}
    for k, pts in raw.items():
        held, last = {}, (pts[min(pts)] if pts else None)
        for m in range(m0, m1):
            last = pts.get(m, last)
            if last is not None:
                held[m] = last
        out[k] = held
    return out


def hours(ms) -> list[float]:
    return [((m * 60) % 86400) / 3600 for m in ms]


def time_axis(ax, h0: float, h1: float, step: float = 1.0) -> None:
    ax.set_xlim(h0, h1)
    ticks = [h0 + i * step for i in range(int((h1 - h0) / step) + 1)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{int(t):02d}:{int(round((t % 1) * 60)):02d}" for t in ticks])


def headroom(ax, frac: float = 0.22) -> None:
    """Free space above the data for labels and legends, so they never sit on a line."""
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + (hi - lo) * frac)


def co2_panel(ax) -> None:
    ax.axhline(1000, color=INK2, lw=1, ls=(0, (4, 3)))
    headroom(ax)
    ax.text(0.995, 1000, "1000 ppm", transform=ax.get_yaxis_transform(), ha="right", va="bottom", color=INK2, fontsize=8)
    ax.set_ylabel("CO₂ (ppm)")


def temp_panel(ax) -> None:
    ax.axhspan(20, 24, color=BAND, lw=0, zorder=0)
    ax.text(0.995, 23.8, "comfort band 20–24 °C", transform=ax.get_yaxis_transform(), ha="right", va="top", color=INK2, fontsize=8)
    ax.set_ylabel("Temperature (°C)")


def s1(run: dict, room: str) -> str:
    m0, m1 = minute(f"{DAY}T07:30:00+00:00"), minute(f"{DAY}T18:00:00+00:00")
    d = series(room, window(to_utc(run["start"]), to_utc(run["end"]), f"{DAY} 07:30:00+00", f"{DAY} 18:00:00+00"), m0, m1)
    fig, axs = plt.subplots(4, 1, figsize=(7.2, 7.0), sharex=True, gridspec_kw={"height_ratios": [3, 1.3, 2.2, 1.6]})
    c = "#2a78d6"
    for ax, key, title in ((axs[0], "co2", "CO₂ observed"), (axs[1], "vent", "Ventilation level (actuator state)"),
                           (axs[2], "temperature", "Temperature observed"), (axs[3], "occupancy", "Occupancy (people)")):
        pts = d[key]
        x, y = hours(sorted(pts)), [pts[m] for m in sorted(pts)]
        if key in ("vent", "occupancy"):
            ax.step(x, y, where="post", color=c, lw=1.6)
        else:
            ax.plot(x, y, color=c, lw=1.6)
        ax.set_title(title)
    co2_panel(axs[0]); temp_panel(axs[2])
    axs[1].set_ylim(-0.2, 3.3); axs[1].set_yticks([0, 1, 2, 3]); axs[1].set_ylabel("Level")
    axs[3].set_ylabel("People")
    time_axis(axs[3], 7.5, 18.0); axs[3].set_xlabel("Simulated time of day (21 Oct)")
    fig.suptitle(f"Final system (R8 = S1), {room}", x=0.01, ha="left", fontsize=10.5, fontweight="bold", color=INK)
    fig.tight_layout()
    path = f"{OUT}/s1_{room}.png"; fig.savefig(path, facecolor="white"); plt.close(fig)
    return path


def e3(runs: dict, room: str = "A117") -> str:
    m0, m1 = minute(f"{DAY}T07:30:00+00:00"), minute(f"{DAY}T18:00:00+00:00")
    fig, axs = plt.subplots(2, 1, figsize=(7.2, 5.6), sharex=True, gridspec_kw={"height_ratios": [3, 2.4]})
    for rid in ("R6", "R7", "R8"):
        if rid not in runs:
            continue
        r = runs[rid]
        d = series(room, window(to_utc(r["start"]), to_utc(r["end"]), f"{DAY} 07:30:00+00", f"{DAY} 18:00:00+00"), m0, m1)
        for ax, key in ((axs[0], "co2"), (axs[1], "temperature")):
            pts = d[key]
            ax.plot(hours(sorted(pts)), [pts[m] for m in sorted(pts)], color=SERIES[rid], ls=STYLE[rid], lw=1.6,
                    label=f"{rid} {NAMES[rid]}")
    axs[0].set_title(f"CO₂ observed, {room} (three lectures)"); co2_panel(axs[0])
    axs[1].set_title(f"Temperature observed, {room}"); temp_panel(axs[1])
    axs[0].legend(loc="upper left", ncol=3, fontsize=8.5)
    time_axis(axs[1], 7.5, 18.0); axs[1].set_xlabel("Simulated time of day (21 Oct)")
    fig.suptitle("E3 — planner off vs persistence vs timetable (final physics)", x=0.01, ha="left",
                 fontsize=10.5, fontweight="bold", color=INK)
    fig.tight_layout()
    path = f"{OUT}/e3_planner_{room}.png"; fig.savefig(path, facecolor="white"); plt.close(fig)
    return path


def f1(faults_txt: str = "docs/results/faults.txt") -> str | None:
    txt = open(faults_txt, encoding="utf-8").read()
    hits = re.findall(r"F1 A109-co2 stuck injected at sim (\S+) \(wall UTC (\S+ \S+)\)", txt)
    if not hits:
        print("F1: no injection line in", faults_txt); return None
    sim_inj, wall_inj = hits[-1]                                # last attempt = the valid one
    t = datetime.fromisoformat(wall_inj.replace("+00", "+00:00"))
    w_from = datetime.fromtimestamp(t.timestamp() - 45, timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")
    w_to = datetime.fromtimestamp(t.timestamp() + 60, timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")
    win = window(w_from, w_to, f"{DAY} 08:00:00+00", f"{DAY} 09:15:00+00")
    m0, m1 = minute(f"{DAY}T08:00:00+00:00"), minute(f"{DAY}T09:15:00+00:00")
    d = series("A109", win, m0, m1)
    dec = query(PIPE, f"""SELECT CAST(sim_ts AS VARCHAR) AS s, state FROM decision WHERE room = 'A109' AND {win} ORDER BY recv_ts""")
    inj_h = hours([minute(sim_inj.replace("Z", "+00:00"))])[0]
    deg = [r for r in dec if r["state"] == "DEGRADED"]
    det_h = hours([minute(deg[0]["s"] + ("" if "+" in deg[0]["s"] else "+00:00"))])[0] if deg else None

    fig, axs = plt.subplots(2, 1, figsize=(7.2, 4.6), sharex=True, gridspec_kw={"height_ratios": [3, 1.4]})
    c = "#2a78d6"
    pts = d["co2"]; axs[0].plot(hours(sorted(pts)), [pts[m] for m in sorted(pts)], color=c, lw=1.6)
    pts = d["vent"]; axs[1].step(hours(sorted(pts)), [pts[m] for m in sorted(pts)], where="post", color=c, lw=1.6)
    for ax in axs:
        if det_h is not None:
            ax.axvspan(det_h, 9.25, color=BAND, lw=0, zorder=0)
        ax.axvline(inj_h, color=INK2, lw=1, ls=(0, (4, 3)))
        if det_h is not None:
            ax.axvline(det_h, color=INK, lw=1.2)
    headroom(axs[0], 0.35)
    box = dict(fc="white", ec="none", pad=1.5)
    axs[0].text(inj_h, 0.98, " sensor frozen", transform=axs[0].get_xaxis_transform(), va="top", color=INK2, fontsize=8, bbox=box)
    if det_h is not None:
        axs[0].text(det_h, 0.98, f" DEGRADED detected\n (+{round((det_h - inj_h) * 60)} sim-min)",
                    transform=axs[0].get_xaxis_transform(), va="top", color=INK, fontsize=8, bbox=box)
    axs[0].set_title("F1 — A109 CO₂ sensor frozen; what control saw"); axs[0].set_ylabel("CO₂ (ppm)")
    axs[1].set_title("Ventilation level (actuator state) — stays at 2 via the occupancy fallback")
    axs[1].set_ylim(-0.2, 3.3); axs[1].set_yticks([0, 1, 2, 3]); axs[1].set_ylabel("Level")
    time_axis(axs[1], 8.0, 9.25, 0.25); axs[1].set_xlabel("Simulated time (21 Oct)")
    fig.tight_layout()
    path = f"{OUT}/f1_frozen_sensor.png"; fig.savefig(path, facecolor="white"); plt.close(fig)
    return path


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    runs = parse_log("docs/results/e3-runs.txt")
    made = []
    if "R8" in runs:
        made += [s1(runs["R8"], "A109"), s1(runs["R8"], "A117")]
    made.append(e3(runs))
    p = f1()
    if p:
        made.append(p)
    print("written:", *made, sep="\n  ")


if __name__ == "__main__":
    main()
