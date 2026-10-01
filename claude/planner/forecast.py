"""Occupancy forecast (30 min ahead) + CO₂ rollout → suggested ventilation. Pure numpy, testable.

Model: one linear regression per horizon step h ∈ {5,10,…,30} min
    n̂(t+h) = w_h · [1, n(t), n(t−5), n(t−10), n(t−15), n(t−30), n(t−60), sin(tod), cos(tod)]
trained by planner/train.py on our own recorded Parquet (planner/model.json). Until a model exists,
`persistence` (n̂ = n(t)) is the baseline — and the baseline every evaluation must beat.

Why not just roll the physics forward? Because the physics needs *future occupancy*; predicting that
is the genuinely uncertain part. Rolling the CO₂ mass balance forward with the *predicted* occupancy
is then a deterministic consequence (docs/decision-log.md, D-07).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from physics.model import RoomParams, RoomState, step

STEP_MIN = 5
LAGS_MIN = (0, 5, 10, 15, 30, 60)
HORIZONS_MIN = (5, 10, 15, 20, 25, 30)
MODEL_PATH = Path(__file__).with_name("model.json")


def features(series: list[float], minute_of_day: float) -> np.ndarray:
    """series = occupancy per 5-min bin, oldest first, last element = now. Needs ≥ 13 bins (60 min)."""
    n = len(series)
    lags = [series[max(0, n - 1 - lag // STEP_MIN)] for lag in LAGS_MIN]
    tod = 2 * math.pi * minute_of_day / 1440
    return np.array([1.0, *lags, math.sin(tod), math.cos(tod)])


@dataclass
class Model:
    version: str
    weights: dict[int, np.ndarray]          # horizon_min -> weight vector

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "Model | None":
        if not path.exists():
            return None
        d = json.loads(path.read_text())
        return cls(d["version"], {int(h): np.array(w) for h, w in d["weights"].items()})

    def save(self, path: Path = MODEL_PATH) -> None:
        path.write_text(json.dumps({"version": self.version, "lags_min": LAGS_MIN, "horizons_min": HORIZONS_MIN,
                                    "weights": {h: w.tolist() for h, w in self.weights.items()}}, indent=1))

    def predict(self, series: list[float], minute_of_day: float, capacity: float) -> list[float]:
        x = features(series, minute_of_day)
        return [float(min(capacity, max(0.0, x @ self.weights[h]))) for h in HORIZONS_MIN]


def persistence(series: list[float], capacity: float) -> list[float]:
    last = series[-1] if series else 0.0
    return [float(min(capacity, max(0.0, last)))] * len(HORIZONS_MIN)


def fit(X: np.ndarray, Y: np.ndarray, version: str) -> Model:
    """Least squares per horizon. X: (N, 9) features, Y: (N, 6) targets."""
    w = {h: np.linalg.lstsq(X, Y[:, i], rcond=None)[0] for i, h in enumerate(HORIZONS_MIN)}
    return Model(version, w)


def co2_rollout(p: RoomParams, co2_now: float, temp_now: float, occ_forecast: list[float],
                vent_level: float, setpoint_c: float, t_out_c: float) -> float:
    """Max CO₂ over the horizon if we keep `vent_level` — same equations as the physics engine."""
    s = RoomState(co2_ppm=co2_now, temp_c=temp_now)
    peak = co2_now
    for n in occ_forecast:
        s = step(p, s, int(round(n)), vent_level, setpoint_c, t_out_c, STEP_MIN * 60)
        peak = max(peak, s.co2_ppm)
    return peak


def suggest_vent(p: RoomParams, co2_now: float, temp_now: float, occ_forecast: list[float],
                 limit_ppm: float, vent_max: int = 3, setpoint_c: float = 21.0, t_out_c: float = 0.0) -> tuple[int, float]:
    """Smallest ventilation level that keeps the forecast CO₂ below `limit_ppm`; returns (level, peak_at_level)."""
    for level in range(vent_max + 1):
        peak = co2_rollout(p, co2_now, temp_now, occ_forecast, level, setpoint_c, t_out_c)
        if peak < limit_ppm:
            return level, peak
    return vent_max, co2_rollout(p, co2_now, temp_now, occ_forecast, vent_max, setpoint_c, t_out_c)
