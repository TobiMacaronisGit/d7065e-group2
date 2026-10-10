# E3 / S1 — planner off, persistence, timetable (live runs, 10 Oct 2026)

Raw data: [`e3-runs.txt`](e3-runs.txt) (run windows + physics energy), [`e3-results.md`](e3-results.md)
(per-room tables from `scripts/compare_runs.py`). Predictions written before the runs:
[`predictions.md`](predictions.md) (committed before R1).

## Setup

- Simulated day **2026-10-21 (Wednesday), 07:30–18:00**, occupancysim seed unchanged, factor 60
  (one run ≈ 10.5 min wall). Same day for every run, so the same people arrive at the same times.
- Bookings: A109 08:15–10:00 (101 students); A117 10:15–12:00 (97), 13:15–15:00 (115), 15:15–17:00 (102).
  A110 (fika), A323, A113C (offices) have no bookings.
- Config: `ach_per_vent_level` 3.6 (level 2 ≈ 10 l/s per person in A109), control rules unchanged.
- Before every run: `docker compose restart control physics` (same initial room state, energy counter 0),
  clock set to 07:30.
- Metrics from the pipeline (sensor readings resampled per sim-minute, last value held — sensors sample
  every 2 sim-min), energy from the physics engine at the end of the run. "Occupied" = occupancy > 0.

| Run | Variant | Valid? |
|---|---|---|
| R1 | Planner off — reactive rules only | ✅ |
| R2 | Planner, persistence forecast | ❌ history bug (below) |
| R3 | Planner, timetable forecast | ❌ partly, history bug (below) |
| R4 | Planner, persistence forecast, **bug fixed** | ✅ |
| R5 | Planner, timetable forecast, **bug fixed** — the final system, also counts as **S1** | ✅ |

## Result — lecture rooms A109 + A117 (≈ 470 occupied sim-min)

| Metric | R1 off | R4 persistence | R5 timetable |
|---|---|---|---|
| CO₂ > 1000 ppm while occupied (sim-min) | 149 | 20 (**−87 %**) | **0 (−100 %)** |
| Peak CO₂ (ppm, per-minute mean) | 1108 | 1093 | **912** |
| Vent changes (commanded level) | 38 | 13 | 11 |
| Occupied sim-min at 20–24 °C | 0 % | 0 % | 0 % |
| Heating energy, all rooms (kWh) | 280.5 | 318.9 (+14 %) | 324.6 (**+16 %**) |

Other rooms (R5): A110 (fika, persistence only) 22 sim-min > 1000 ppm (R1: 54), peak 1155;
offices never above 1000 ppm.

## What the numbers say

1. **The planner works (FR-04 passes).** Both variants cut exceedance far beyond the 50 % target.
2. **Most of the benefit needs no forecast skill.** Persistence alone gives −87 %: as soon as people are
   in the room, the CO₂ rollout predicts that level 1 will not hold and keeps level 2. The timetable adds
   the last step — ventilating ~20 min *before* people arrive — which removes the remaining 20 minutes
   and lowers the peak by ~180 ppm.
3. **Reactive control alone oscillates.** At level 2 a full lecture room settles at ≈ 880 ppm; the rule
   steps down to level 1 once CO₂ < 1000 − 100 = 900 ppm, CO₂ climbs back over 1000, and so on
   (38 vent changes, 149 minutes over the limit, but only ~1100 ppm peak). The hysteresis threshold was
   tuned for the old, weaker ventilation and not re-checked when ventilation changed. Part of what the
   planner "achieves" is compensating for this — a cheaper fix would be to re-tune the threshold.
4. **The trade-off is real:** clean air costs ~16 % more heating energy, and comfort is 0 % in every run.
   The proportional heater settles below its setpoint (A109 ends at 15.8 °C with a 17 °C setpoint), and
   more ventilation cools the lecture rooms further (A117 ends at 13.8 °C in R5 vs 15.4 °C in R1).
   FR-02 fails regardless of the planner.

## Predictions against results

| Prediction | Result |
|---|---|
| A (7 Oct): planner ≥ 50 % fewer exceedance sim-min | ✅ −87 % / −100 % |
| A: persistence as good as a perfect forecast | ⚠️ partly: persistence gets most of the benefit, the timetable removes the rest |
| A: heating energy rises with the planner | ✅ +14 % / +16 % |
| B (10 Oct): R1 > persistence > timetable on exceedance and peak | ✅ |
| B: peak ≈ 900 ppm with the timetable | ✅ 912 |
| B: reactive-only exceeds only "a few minutes per lecture" | ❌ 149 min — oscillation (point 3), not foreseen |
| A + B: FR-02 fails in all variants | ✅ 0 % |

## Bug found by the experiment (why R2 and R3 are invalid)

`pipeline/storage.py` `history()` anchored its window at the **latest stored reading** instead of the
current sim time. Replaying 21 Oct meant the planner, asking for "the last 120 min" at 08:30, received
data from an earlier run — at worst from **22 Oct 10:07–10:37** (verified with `curl`). In R2 the
persistence forecast therefore saw an empty room all day and never raised ventilation (0 planner
decisions); in R3 the timetable was right but the rollout started from a wrong CO₂ value.

Fix (10 Oct): `/history` accepts `until` (the caller's sim time) and `max_age_s` (only rows received
within that many wall seconds); the planner always sends both. Test:
`pipeline/test_storage.py::test_history_until_ignores_a_replayed_day`. Verified live: at sim 08:35 the
window returned 08:25–08:33 with 102 persons. R4/R5 were run after the fix; R1 did not use the planner.

R2 also lost the A110 CO₂ and A117 temperature streams for the whole run (0 readings) — cause not
investigated; R4/R5 have complete data.

## Limits of this evaluation

- One simulated day, one run per variant; sensor noise and the clock jump at the start add some variance.
- occupancysim: every registered student attends, so the timetable forecast is an optimistic upper bound.
- Sensor readings, not ground truth: a reading is every 2 sim-min with noise σ = 15 ppm.
- The outdoor-temperature daily term is still inverted (coldest at 15:00, §9) — all runs share it.

## Decision (task p2-5)

**The planner stays, with the timetable forecast and persistence as fallback** (rooms without
bookings, or occupancysim unreachable). It is the only variant that meets FR-01 in the lecture rooms.
The trained linear model (E5, [`train.txt`](train.txt)) lost to persistence and is not deployed.
