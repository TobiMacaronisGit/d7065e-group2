"""Unit tests for the planner logic (run: pytest planner/)."""
import numpy as np

from physics.model import RoomParams
from planner.forecast import HORIZONS_MIN, features, fit, persistence, suggest_vent, timetable_forecast

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


# 08:15-10:00 lecture in A109 with 40 registered students (times in minutes of day, as occupancysim sends them)
LECTURES = [{"level": "level0", "room": "A109", "start": 495.0, "end": 600.0, "students": 40, "seats": 94},
            {"level": "level1", "room": "A109", "start": 495.0, "end": 600.0, "students": 70, "seats": 94}]


def test_timetable_sees_the_lecture_before_anyone_arrives():
    # now 07:50 -> horizons 07:55 .. 08:20; lecturer from 08:00, students from 08:05
    fc = timetable_forecast(LECTURES, "level0", "A109", 470, capacity=94)
    assert fc == [0.0, 1.0, 41.0, 41.0, 41.0, 41.0]


def test_timetable_ends_with_the_lecture_and_ignores_other_levels():
    fc = timetable_forecast(LECTURES, "level0", "A109", 590, capacity=94)   # 09:50 -> 09:55 .. 10:20
    assert fc == [41.0] + [0.0] * 5


def test_timetable_none_without_booking_and_not_capped():
    assert timetable_forecast(LECTURES, "level0", "A117", 470, capacity=107) is None
    assert timetable_forecast([], "level0", "A109", 470, capacity=94) is None
    # not capped: occupancysim over-books full slots (students > seats), so the forecast follows the booking
    assert max(timetable_forecast(LECTURES, "level0", "A109", 500, capacity=20)) == 41.0
    overbooked = [{"level": "level0", "room": "A109", "start": 495.0, "end": 600.0, "students": 101, "seats": 94}]
    assert max(timetable_forecast(overbooked, "level0", "A109", 500, capacity=20)) == 102.0


def test_timetable_lets_the_planner_ventilate_before_the_lecture():
    big = [{"level": "level0", "room": "A109", "start": 495.0, "end": 600.0, "students": 90, "seats": 94}]
    fc = timetable_forecast(big, "level0", "A109", 470, capacity=94)        # room still empty now (07:50)
    level, _ = suggest_vent(P, co2_now=450, temp_now=21, occ_forecast=fc, limit_ppm=900)
    assert level >= 1                                                     # persistence would say 0 here
    small, _ = suggest_vent(P, co2_now=450, temp_now=21,
                            occ_forecast=timetable_forecast(LECTURES, "level0", "A109", 470, 94), limit_ppm=900)
    assert small == 0                                                     # 41 people stay below the limit within 30 min
