"""Train the occupancy forecast from recorded data and evaluate it against the persistence baseline.

    python -m planner.train --parquet data/silver/sensor.parquet [--out planner/model.json]

Data: the pipeline's silver/sensor.parquet (run `curl -X POST localhost:8092/compact` first).
Split BY SIM-DATE (never randomly): occupancysim replays a date deterministically, so a random split
would leak the test day into training and the forecast would look better than it is (report §11).
Outputs MAE per horizon for model vs. persistence — that table goes straight into the report.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import numpy as np

from planner.forecast import HORIZONS_MIN, LAGS_MIN, STEP_MIN, Model, features, fit


def load_series(parquet: str) -> dict[tuple[str, str], list[tuple[int, float]]]:
    """→ {(date, room): [(minute_of_day, occupancy), ...] resampled to 5-min bins}"""
    con = duckdb.connect()
    rows = con.execute(f"""
        SELECT substr(sim_ts,1,10) AS d, room,
               CAST(floor((hour(CAST(sim_ts AS TIMESTAMPTZ))*60 + minute(CAST(sim_ts AS TIMESTAMPTZ))) / {STEP_MIN}) AS INT) * {STEP_MIN} AS mod,
               max(value) AS n
        FROM read_parquet('{parquet}') WHERE type = 'occupancy'
        GROUP BY d, room, mod ORDER BY d, room, mod""").fetchall()
    out: dict[tuple[str, str], list[tuple[int, float]]] = {}
    for d, room, mod, n in rows:
        out.setdefault((d, room), []).append((int(mod), float(n)))
    return out


def make_xy(series: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    X, Y, B, D = [], [], [], []
    hist = max(LAGS_MIN) // STEP_MIN + 1
    fut = max(HORIZONS_MIN) // STEP_MIN
    for (d, _room), pts in series.items():
        vals = [n for _, n in pts]
        mods = [m for m, _ in pts]
        for i in range(hist, len(vals) - fut):
            X.append(features(vals[: i + 1], mods[i]))
            Y.append([vals[i + h // STEP_MIN] for h in HORIZONS_MIN])
            B.append([vals[i]] * len(HORIZONS_MIN))          # persistence baseline
            D.append(d)
    return np.array(X), np.array(Y), np.array(B), np.array(D)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default="data/silver/sensor.parquet")
    ap.add_argument("--out", default=str(Path(__file__).with_name("model.json")))
    ap.add_argument("--version", default="lr-v1")
    a = ap.parse_args()

    X, Y, B, D = make_xy(load_series(a.parquet))
    dates = sorted(set(D))
    if len(dates) < 2:
        raise SystemExit(f"need ≥2 simulated days for a date split, have {dates}")
    test_day = dates[-1]
    tr, te = D != test_day, D == test_day
    model = fit(X[tr], Y[tr], a.version)
    pred = np.stack([X[te] @ model.weights[h] for h in HORIZONS_MIN], axis=1)
    print(f"train days {dates[:-1]}  test day {test_day}  samples train={tr.sum()} test={te.sum()}")
    print("horizon  MAE(model)  MAE(persistence)")
    for i, h in enumerate(HORIZONS_MIN):
        print(f"{h:>5} min  {np.abs(pred[:, i] - Y[te, i]).mean():9.2f}  {np.abs(B[te, i] - Y[te, i]).mean():9.2f}")
    model.save(Path(a.out))
    print("saved", a.out)


if __name__ == "__main__":
    main()
