"""Unit tests for the planner logic (run: pytest planner/)."""
import numpy as np

from physics.model import RoomParams
from planner.forecast import HORIZONS_MIN, features, fit, persistence, suggest_vent

P = RoomParams(volume_m3=564, area_m2=188, co2_outdoor_ppm=420, co2_gen_m3_per_s_per_person=5.2e-6,
               infiltration_ach=0.2, ach_per_vent_level=1.3, envelope_w_per_k=470,
               thermal_mass_j_per_k=3.4e7, body_heat_w=100, heater_max_w=15000, heater_gain_w_per_k=7500)


def test_features_shape_and_persistence():
    series = [0.0] * 10 + [5.0, 12.0, 20.0]
    assert features(series, 600).shape == (9,)
    assert persistence(series, capacity=94) == [20.0] * len(HORIZONS_MIN)


def test_fit_recovers_a_linear_rule():
    rng = np.random.default_rng(0)
    X = np.array([features(list(rng.integers(0, 60, 13).astype(float)), float(rng.integers(0, 1440))) for _ in range(300)])
    Y = np.stack([2 * X[:, 1] + 3] * len(HORIZONS_MIN), axis=1)          # n̂ = 2·n(t) + 3 for every horizon
    m = fit(X, Y, "test")
    x = features([10.0] * 13, 600)
    assert abs(x @ m.weights[30] - 23) < 1e-6


def test_suggest_vent_raises_ahead_of_a_lecture():
    empty_forecast = [0.0] * 6
    level0, _ = suggest_vent(P, co2_now=500, temp_now=21, occ_forecast=empty_forecast, limit_ppm=1000)
    assert level0 == 0
    lecture = [0.0, 60.0, 60.0, 60.0, 60.0, 60.0]           # 60 people arriving in 10 min
    level1, peak = suggest_vent(P, co2_now=500, temp_now=21, occ_forecast=lecture, limit_ppm=1000)
    assert level1 >= 2 and peak < 1000, "planner must pre-ventilate so the peak stays under the limit"
