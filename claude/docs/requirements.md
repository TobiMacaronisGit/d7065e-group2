# Requirements

Report section 3. Every requirement is **testable**: unique ID, type, priority, a measurable acceptance
criterion, and the test that verifies it. This table is the root of the traceability thread —
requirement → design element → test (`docs/test-plan.md`).

Time unit convention: **sim-min** = simulated minutes (the building's clock, 60× wall clock);
**s wall** = real seconds. Mixing the two silently is the mistake this convention exists to prevent.

| ID | Type | Requirement | Prio | Acceptance criterion | Design element | Verified by |
|---|---|---|---|---|---|---|
| FR-01 | Functional | Keep an occupied room's CO₂ below 1000 ppm by ventilating | Must | After exceeding 1000 ppm, CO₂ is back below it within 10 sim-min | `control` rules, `actuator-vent-*` | `control/test_rules.py::test_reactive_levels_and_safety_override`, E2E scenario S1 |
| FR-02 | Functional | Hold occupied rooms in the comfort band 20–24 °C | Must | ≥ 90 % of occupied sim-minutes in band over one simulated weekday | `control` setpoint logic, `actuator-heat-*` | scenario run S1, metric from `pipeline` |
| FR-03 | Functional | Set back ventilation and heating in empty rooms | Must | Within 15 sim-min of a room emptying: vent = min level, setpoint = 17 °C | `control` rules | `test_stale_co2_is_not_trusted`, S1 |
| FR-04 | Functional | Ventilate *before* the threshold when a fill is forecast | Should | ≥ 50 % fewer CO₂-exceedance sim-minutes than the reactive-only baseline on the same simulated day + seed | `planner` | `planner/test_forecast.py::test_suggest_vent_raises_ahead_of_a_lecture`, experiment E3 |
| FR-05 | Functional | Every actuator command is auditable | Should | Every decision carries a human-readable reason and the inputs it used; retrievable from the pipeline | `Decision` schema, `pipeline` | `pipeline/test_storage.py`, dashboard inspection |
| NFR-01 | Non-functional | Produce a control decision per room at least every 60 s wall | Must | Median decision interval ≤ 60 s wall under full load (5 rooms, 20 device containers) | `control` EVAL_S = 5 s | experiment E4 (latency vs. rooms) |
| NFR-02 | Non-functional | Survive the crash of any single sensor, actuator or service | Must | After `docker compose kill <svc>` + restart, the loop produces a correct command again within 60 s wall; no unsafe command in between | restart policy, retained MQTT state, stateless `control` | fault-injection F1–F4 |
| NFR-03 | Non-functional | No actuator thrashing | Should | No actuator changes its target more than once per 5 sim-min (except SAFETY) | hysteresis + dwell time in `control/rules.py` | `test_hysteresis_blocks_early_step_down`, experiment E2 |
| NFR-04 | Non-functional | Use no more heating energy than a fixed-schedule baseline | Should | Modelled kWh over one simulated weekday ≤ baseline (which ventilates on office hours) | occupancy-driven setback | experiment E1 |
| NFR-05 | Non-functional | Detect a frozen/stale sensor and keep controlling | Must | A stuck CO₂ sensor is detected within 10 sim-min; the room is marked DEGRADED and control continues from occupancy | `RoomController.co2_quality` | `test_frozen_sensor_marks_room_degraded_and_uses_occupancy`, F1 |
| NFR-06 | Non-functional | Survive a BuildSim restart | Should | After `docker compose restart buildsim`, all devices are re-registered and readings resume within 60 s wall, without running the seed again | self-registration on 404 | fault-injection F5 |
| NFR-07 | Non-functional | The data pipeline loses no readings during a short outage | Should | After `docker compose stop pipeline` for 60 s wall, the missed readings appear once the pipeline returns | MQTT QoS 1 + persistent session | fault-injection F3 |
| REG-01 | Regulatory | Maintain a minimum ventilation rate at all times | Must | The commanded vent level is never below `control.vent_min_level`, in every state including NO_DATA | hard clamp after all rules | `control/test_rules.py`, code review of the clamp order |
| SAF-01 | Safety | An unauthorised or out-of-range command is never applied | Must | Commands from an issuer other than `control`, outside range, or older than 120 s wall are rejected and counted | `actuator.validate()` | `actuator/test_validate.py`, F6 |

## Non-requirements (deliberately out of scope)

- No authentication or encryption anywhere (BuildSim has none; this is a laptop lab — stated as a limitation, not solved).
- No multi-floor or multi-building operation (occupancysim's walkable graph has no stairs).
- No physically accurate CFD: perfect mixing per room, no inter-room air exchange, no solar gain, no humidity.
- No consensus, distributed transactions or clustering (explicitly out of scope per the grading page).
