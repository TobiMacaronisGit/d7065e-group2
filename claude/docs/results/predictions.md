# Predictions for the live E3 runs (R1 / R2 / R3)

Written 10 Oct 2026, **before** any of the runs below. Committed before R1 starts, so the git timestamp
proves the order.

## Setup

- Simulated day: **2026-10-21 (Wednesday), 07:30–18:00**, occupancysim seed unchanged, factor 60.
- Bookings in our rooms: A109 08:15–10:00 (101 students), A117 10:15–12:00 (97), 13:15–15:00 (115),
  15:15–17:00 (102). A110, A323, A113C have no lectures.
- Config: `ach_per_vent_level` **3.6** (was 1.3 until 10 Oct), `docker compose restart physics` before every run.

| Run | Variant | How |
|---|---|---|
| R1 | No forecast (reactive control only) | planner stopped, retained plans cleared, control restarted |
| R2 | Planner, persistence forecast | `PLANNER_FORECAST=persistence` |
| R3 | Planner, timetable forecast | `PLANNER_FORECAST=timetable` (default) |

## Prediction A — from 7 Oct (docs/architecture.md §9 and §10.2)

Written for the **old** ventilation (1.3 ACH/level) and 50–70 persons:

- The planner gives at least 50 % fewer exceedance sim-min than reactive-only, almost entirely from
  sizing ventilation with the physics rollout.
- **A persistence forecast is as good as a perfect one** → expects **R3 ≈ R2**.
- Heater energy rises with the planner.

## Prediction B — added 10 Oct, new ventilation (3.6 ACH/level)

Capacity at which a room still holds 1000 ppm (steady state, n = (1000 − 420)·Q / 5.2):

| Room | old, level 3 | new, level 2 | new, level 3 |
|---|---|---|---|
| A109 | 72 | 129 | 192 |
| A117 | 82 | 147 | 219 |
| A110 | 47 | 85 | 127 |

The test day's lectures (102–116 persons incl. lecturer) are now **below** the level-2 limit, so
exceedances can only happen at the start of a lecture, while ventilation is still catching up.

| Metric (A109 + A117, occupied minutes) | R1 | R2 | R3 | Reasoning |
|---|---|---|---|---|
| CO₂ > 1000 ppm (sim-min) | most | fewer | ≈ 0 | R1 waits for measured CO₂ (30 s sensor lag + ramp); R2 reacts as soon as people are in the room; R3 ventilates ~20 min before they arrive |
| Peak CO₂ (ppm) | ≈ 1050 | ≈ 1000 | ≈ 900 | observed today: ≈ 1030 peak at lecture start, ≈ 880 steady at level 2 |
| % occupied minutes at 20–24 °C | ≈ 0 | ≈ 0 | ≈ 0, slightly higher | proportional heater settles below setpoint (§9); 20–30 min of pre-heat gives < 1 K (15 kW / 34 MJ/K ≈ 1.6 K/h without losses) |
| Heating energy (kWh) | lowest | middle | highest | R3 ventilates and heats earlier; more ventilation = more heat loss |

**Prediction B contradicts Prediction A on R2 vs R3.** The run decides which one holds.
Expected for all three: **FR-02 fails** — the planner cannot compensate for heater capacity.
