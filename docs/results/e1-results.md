# E1 results — fixed-schedule baseline (R9) against the final system (R6–R8)

Simulated day 2026-10-21, 07:30–18:00, same seed and factor as R6–R8. Produced with
`python3 scripts/compare_runs.py docs/results/e1-runs.txt` on 12 Oct 2026; R6–R8 are recomputed from the
stored pipeline data and match `e3-results.md` exactly. Prediction written before the run: `e1-predictions.md`.

- **R9** = `CONTROL_MODE=fixed-schedule` (vent 2 + 21 °C from 07:30 to 17:00, vent 0 + 17 °C otherwise,
  no sensors, no plans), planner stopped, `control` and `physics` restarted, clock set to 07:30.
- Energy counters read at sim 18:13:54 (R6–R8: about 18:09). A second reading at sim 20:15 showed the same
  totals (rooms were cooling towards the 17 °C setback, no heating), so the later reading changes nothing;
  that duplicate end line was removed from `e1-runs.txt`.
- **Outcome vs. prediction:** energy R9 > R8 ✅ (445.8 vs 282.6 kWh → final system −37 %, NFR-04 met in the
  model). More lecture exceedances than R6 ❌ (R9 had 0, peak 917 ppm: R6's exceedances come from reactive lag,
  not from level-2 capacity). Comfort: R9 96.4 % (heating from 07:30) against 84.7 % for R8.


| Run | Variant | Wall time (local) |
|---|---|---|
| R6 | no-forecast-ahu | 2026-10-10 17:06:21 → 17:17:01 |
| R7 | persistence-ahu | 2026-10-10 17:17:44 → 17:28:24 |
| R8 | timetable-ahu | 2026-10-10 17:30:51 → 17:41:31 |
| R9 | fixed-schedule | 2026-10-12 17:31:48 → 17:42:28 |

## A109

| Metric | R6 | R7 | R8 | R9 |
|---|---|---|---|---|
| occ_min | 123 | 116 | 119 | 122 |
| exceed_min | 32 | 0 | 0 | 0 |
| peak_co2 | 1127 | 969 | 920 | 912 |
| comfort_% | 62.6 | 61.2 | 87.4 | 86.1 |
| fohm_% | 100.0 | 100.0 | 100.0 | 100.0 |
| vent_changes | 7 | 4 | 4 | 1 |
| planner_dec | 0 | 24 | 30 | 0 |
| heater_kwh | 65.171 | 66.229 | 68.164 | 124.492 |
| ahu_kwh | 5.49 | 7.034 | 6.996 | 36.008 |
| energy_kwh | 70.661 | 73.263 | 75.16 | 160.5 |

## A117

| Metric | R6 | R7 | R8 | R9 |
|---|---|---|---|---|
| occ_min | 350 | 359 | 346 | 354 |
| exceed_min | 90 | 2 | 0 | 0 |
| peak_co2 | 1276 | 1002 | 913 | 917 |
| comfort_% | 72.9 | 71.3 | 83.8 | 100.0 |
| fohm_% | 94.0 | 91.1 | 99.1 | 100.0 |
| vent_changes | 29 | 13 | 6 | 1 |
| planner_dec | 0 | 70 | 84 | 0 |
| heater_kwh | 86.662 | 92.411 | 94.253 | 109.233 |
| ahu_kwh | 23.07 | 30.087 | 30.769 | 39.673 |
| energy_kwh | 109.732 | 122.498 | 125.022 | 148.906 |

## A110

| Metric | R6 | R7 | R8 | R9 |
|---|---|---|---|---|
| occ_min | 232 | 231 | 226 | 220 |
| exceed_min | 49 | 31 | 28 | 6 |
| peak_co2 | 1230 | 1221 | 1192 | 1380 |
| comfort_% | 24.1 | 26.4 | 24.8 | 100.0 |
| fohm_% | 90.9 | 86.6 | 87.6 | 100.0 |
| vent_changes | 17 | 16 | 21 | 1 |
| planner_dec | 0 | 23 | 28 | 0 |
| heater_kwh | 55.222 | 59.33 | 56.889 | 81.706 |
| ahu_kwh | 7.147 | 8.871 | 8.821 | 23.759 |
| energy_kwh | 62.369 | 68.201 | 65.71 | 105.465 |

## A323

| Metric | R6 | R7 | R8 | R9 |
|---|---|---|---|---|
| occ_min | 0 | 0 | 0 | 0 |
| exceed_min | 0 | 0 | 0 | 0 |
| peak_co2 | 461 | 468 | 468 | 463 |
| comfort_% | – | – | – | – |
| fohm_% | – | – | – | – |
| vent_changes | 1 | 0 | 0 | 1 |
| planner_dec | 0 | 0 | 0 | 0 |
| heater_kwh | 6.611 | 6.625 | 6.608 | 12.918 |
| ahu_kwh | 0.032 | 0.0 | 0.0 | 3.329 |
| energy_kwh | 6.643 | 6.625 | 6.608 | 16.247 |

## A113C

| Metric | R6 | R7 | R8 | R9 |
|---|---|---|---|---|
| occ_min | 475 | 479 | 475 | 472 |
| exceed_min | 0 | 0 | 0 | 0 |
| peak_co2 | 856 | 848 | 829 | 586 |
| comfort_% | 78.3 | 80.6 | 79.6 | 100.0 |
| fohm_% | 100.0 | 100.0 | 99.6 | 100.0 |
| vent_changes | 19 | 22 | 20 | 1 |
| planner_dec | 0 | 25 | 19 | 0 |
| heater_kwh | 9.68 | 9.771 | 9.704 | 11.557 |
| ahu_kwh | 0.384 | 0.373 | 0.414 | 3.089 |
| energy_kwh | 10.064 | 10.144 | 10.118 | 14.646 |

## Summary (lecture rooms A109 + A117; energy: all rooms)

| Metric | R6 | R7 | R8 | R9 |
|---|---|---|---|---|
| occ_min | 473 | 475 | 465 | 476 |
| exceed_min | 122 | 2 | 0 | 0 |
| vent_changes | 36 | 17 | 10 | 2 |
| planner_dec | 0 | 94 | 114 | 0 |
| peak_co2 | 1276 | 1002 | 920 | 917 |
| comfort_% | 70.2 | 68.8 | 84.7 | 96.4 |
| fohm_% (18-24 degC) | 95.6 | 93.3 | 99.3 | 100.0 |
| energy_kwh (all rooms) | 259.5 | 280.7 | 282.6 | 445.8 |

Data check — sim-minutes with a CO2 reading per room (sensors sample every 2 sim-min, expect ≈ 315): R6: 314/314/314/314/315, R7: 315/314/315/314/315, R8: 315/315/315/315/315, R9: 312/312/312/312/312
