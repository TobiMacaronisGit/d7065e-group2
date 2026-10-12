# Changes since the proposal (for report §1)

Collected 10 Oct 2026 from the work log and `docs/results/`. Each line: what changed, and what forced it.

| Area | Change | Why / evidence |
|---|---|---|
| Ventilation strength | `ach_per_vent_level` 1.3 → **3.6** | at 1.3, a full lecture room stayed at ≈ 1300–1400 ppm even at the highest level; 3.6 gives level 2 ≈ 10 l/s per person (Folkhälsomyndigheten: ≥ 7 l/s per person + 0.35 l/s·m², ≈ 10 recommended) |
| Supply air | mechanical ventilation air from an AHU at **18 °C after 75 % heat recovery**; AHU energy counted | with outdoor-temperature supply air comfort was 0 % in every run (R1–R5); real buildings temper supply air |
| Radiator | 80 W/m², gain 40 → **130 W/m², gain 130** (band 1 K) | sized for envelope loss at design outdoor temperature; the old proportional heater settled ≈ 1 K below setpoint |
| Occupancy forecast | trained linear model → **booking timetable** (persistence as fallback) | the trained model lost to persistence at every horizon (`results/train.txt`); occupancysim exposes the day's bookings |
| Planner decision | kept | live E3: −98 % / −100 % exceedance minutes, the only variant that improves comfort (`results/e3-summary.md`) |
| Pipeline `/history` | window anchored at the caller's sim time (`until`, `max_age_s`) | bug found during E3: replayed days returned another run's data (invalidated R2/R3) |
| Grafana | 11.2.0 → **12.3.0**, Infinity plugin pinned to 4.1.1 | the unpinned plugin required a newer Grafana (`react/jsx-runtime` 404) |
| Pipeline image | `pytz` added | DuckDB TIMESTAMPTZ queries failed without it (Grafana panels empty) |
| Experiments not executed | E1, E2, E4, F2, F4, F5, F7 (see `test-plan.md`) | time; listed as limitations / future work |

To check before submission: the fault tests F1, F3, F6 and whether anything else changed (e.g. dropped
features) that is not listed here.
