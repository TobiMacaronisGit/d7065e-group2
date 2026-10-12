# Prediction for E1 (R9, fixed-schedule baseline, NFR-04)

Written 12 Oct 2026, **before** R9. Committed before the run starts, so the git timestamp proves the order.

## Setup

Same conditions as R6–R8 (`e3-summary.md`): simulated **2026-10-21, 07:30–18:00**, occupancysim seed
unchanged, factor 60, final physics (3.6 ACH per vent level, 18 °C supply air after 75 % heat recovery,
130 W/m² radiators). Before the run: clock set to 07:30, `control` and `physics` restarted, planner stopped.

| Run | Variant | How |
|---|---|---|
| R9 | Fixed schedule: vent level 2 and 21 °C from 07:30 to 17:00, vent 0 and 17 °C otherwise, no sensors, no planner | `CONTROL_MODE=fixed-schedule`, planner stopped |

Compared against R6 (reactive only), R7 (persistence) and R8 (timetable = final system): energy is
radiator + AHU heating over all five rooms, from the physics counters at the end of the run.

## Prediction

- **Energy: R9 > R8 (282.6 kWh), so NFR-04 passes.** The baseline runs the AHU at level 2 in all five
  rooms for 9.5 h, while the autonomous system ventilates mainly when CO₂ rises; it also heats A109
  after its only lecture (10:00–17:00) and A117 before its first one. Main uncertainty: during lectures
  the autonomous system goes to level 3, which the baseline never does.
- **CO₂: more lecture-room exceedance sim-min than R6 (122).** Level 2 is the cap, and 97–115 students
  need level 3 (R6 already exceeded with level 3 available).
- **Comfort: unclear.** Heating from 07:30 should help A117 (first lecture 10:15); A109 starts at 08:15,
  45 sim-min after the schedule, so it likely starts cold as in R6–R8.
- One run, one simulated day: differences of a few percent are within run-to-run noise.
