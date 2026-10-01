# Interfaces and communication

Report section 5. Precise enough that another team could rebuild the system from this file alone.
Source of truth in code: `common/schemas.py` (payloads), `common/topics.py` (topics), `common/buildsim.py`
(BuildSim calls). If they disagree with this document, the document is wrong — fix it.

## Communication patterns, and why each link uses the one it does

| Pattern | Used for | Why here |
|---|---|---|
| **MQTT pub/sub** (QoS 1, retained where noted) | sensor readings, actuator commands and states, plans, decisions, health, fault injection | one producer, several independent consumers; the broker buffers while a consumer restarts (NFR-02, NFR-07) |
| **REST request/response** | everything to/from BuildSim; `planner` → `pipeline` history; all `/healthz` | one-to-one calls whose result the caller must confirm (a 404 from BuildSim means "re-register", not "retry later") |
| **WebSocket** | BuildSim → browser (3D viewer) | provided by BuildSim; we publish state, the viewer pushes it to the browser |

Delivery is **at-least-once**: every consumer must tolerate duplicates. Readings carry `seq`, commands
carry `seq` and are idempotent (applying the same target twice changes nothing).

## Time

Every payload carries two timestamps:

| Field | Clock | Used for |
|---|---|---|
| `ts` | wall clock, UTC ISO-8601 | latency, recovery time, anything measured in real seconds |
| `sim_ts` | simulated building clock (60× wall), UTC ISO-8601 | physics steps, freshness/dwell windows, evaluation over a "simulated day" |

## MQTT topic tree

| Topic | Payload | Retained | Publisher | Subscribers |
|---|---|---|---|---|
| `bldg/<level>/<room>/sensor/<type>` | `SensorReading` | no | `sensor-*`, `occupancy_counter` | `control`, `pipeline`, `viewer` |
| `bldg/<level>/<room>/actuator/<kind>/cmd` | `ActuatorCommand` | **yes** | `control` | `actuator-*`, `pipeline` |
| `bldg/<level>/<room>/actuator/<kind>/state` | `ActuatorState` | **yes** | `actuator-*` | `pipeline`, `control` (future), dashboard |
| `bldg/<level>/<room>/plan` | `Plan` | **yes** | `planner` | `control`, `pipeline` |
| `bldg/<level>/<room>/decision` | `Decision` | no | `control` | `pipeline`, `viewer` |
| `sys/health/<service>` | `Health` | **yes** (incl. broker last-will `status: down`) | every service | `viewer`, `pipeline` |
| `sys/fault/<device-id>` | `{"mode": "stuck\|offline\|drift\|slow\|none"}` | no | `scripts/inject_fault.sh` | that device |

`<type>` ∈ `co2 | temperature | occupancy`; `<kind>` ∈ `vent | heat`; `<level>` = `level0`.

## Message schemas

```jsonc
// SensorReading — bldg/level0/A109/sensor/co2
{ "sensor_id": "A109-co2", "level": "level0", "room": "A109",
  "type": "co2", "unit": "ppm", "value": 843.0,        // ppm | °C | persons
  "sim_ts": "2026-09-21T10:14:00+00:00", "ts": "2026-09-19T08:31:02.145+00:00",
  "seq": 1841, "quality": "ok" }

// ActuatorCommand — bldg/level0/A109/actuator/vent/cmd   (retained)
{ "actuator_id": "A109-vent", "level": "level0", "room": "A109", "kind": "vent",
  "target": 2,                                          // vent: level 0..3 | heat: setpoint °C 10..26
  "reason": "CO2 1043 → reactive level 2", "issued_by": "control",
  "sim_ts": "...", "ts": "...", "seq": 97 }

// ActuatorState — bldg/level0/A109/actuator/vent/state  (retained)
{ "actuator_id": "A109-vent", "level": "level0", "room": "A109", "kind": "vent",
  "state": 1.5, "target": 2, "moving": true, "fault": "none", "sim_ts": "...", "ts": "..." }

// Plan — bldg/level0/A109/plan                          (retained)
{ "level": "level0", "room": "A109", "horizon_min": 30,
  "occupancy_forecast": [0, 12, 41, 58, 60, 60],        // one value per 5 sim-min step
  "co2_forecast_max_ppm": 1180.4, "suggested_vent": 2, "suggested_setpoint_c": 21.0,
  "model_version": "lr-v1", "sim_ts": "...", "ts": "..." }

// Decision — bldg/level0/A109/decision
{ "level": "level0", "room": "A109", "state": "NORMAL",  // NORMAL | DEGRADED | SAFETY | NO_DATA
  "vent": 2, "setpoint_c": 21.0,
  "reason": "CO2 1043 → reactive level 2; planner expects 1180 ppm in 30 min → pre-ventilate 2",
  "inputs": { "co2": 1043.0, "co2_quality": "ok", "temp": 21.4, "occupancy": 55, "plan_vent": 2 },
  "sim_ts": "...", "ts": "..." }

// Health — sys/health/control                           (retained)
{ "service": "control", "status": "ok", "detail": "clock_degraded=false", "ts": "..." }
```

## Errors and failure semantics

| Situation | Who detects it | Behaviour |
|---|---|---|
| Command from an issuer ≠ `control`, out of range, or older than 120 s wall | `actuator` | rejected, counter incremented, logged, **not applied** (SAF-01) |
| Duplicate command (QoS 1 redelivery) | — | applied again; idempotent by construction |
| `PUT /api/sensors/{id}/value` → 404 | `sensor`, `occupancy_counter` | BuildSim restarted with empty state → device re-registers itself, then retries (NFR-06) |
| BuildSim unreachable | every device, `physics`, `viewer` | keep publishing to MQTT, log once, report `degraded`; no data is lost because MQTT is the primary path |
| Broker unreachable | all | paho reconnects with backoff; persistent session + QoS 1 redelivers what was missed (NFR-07) |
| occupancysim clock unreachable | `common/clock.py` | extrapolate at the last known factor, report `clock_degraded` |
| CO₂ stale > 300 sim-s or frozen ≥ 8 identical samples | `control` | room → `DEGRADED`, decide from occupancy (NFR-05) |
| No trustworthy CO₂ **and** no occupancy | `control` | room → `NO_DATA`, ventilate at a safe default, heat as if occupied |
| `pipeline` down | `planner` | no new plans published; `control` continues reactive (graceful degradation) |

## BuildSim REST (what each container touches)

| Container | Call | Purpose |
|---|---|---|
| `sensor-*` | `PUT /api/sensors/{id}/value`, `POST /api/equipment/bulk` | report observation; self-register after a 404 |
| `occupancy_counter` | `GET /api/occupancy`, `PUT /api/sensors/{id}/value` | read whole-building occupancy; publish head count |
| `actuator-*` | `PUT /api/actuators/{id}/state`, `POST /api/equipment/bulk` | report reached state; self-register |
| `physics` | `GET /api/occupancy`, `GET /api/actuators/{id}` | occupancy + **actuator read-back that closes the loop** |
| `viewer` | `PUT /api/room-layers`, `PUT /api/alerts` | the only writer of these two collections |
| `seed` | `POST /api/equipment/bulk`, `GET /api/building/floors/level0` | initial registration; room classification for occupancysim |

Rules that bite: values and states are **strings**; rooms are keyed `level0/A109`; collection PUTs
**replace** the collection (hence one writer each); `bulk` only creates and never overwrites.

## occupancysim REST

| Call | Used by | Purpose |
|---|---|---|
| `GET /api/state` | `common/clock.py` (physics, control, planner, occupancy_counter) | simulated time, factor, running |
| `GET/PUT /api/config` | `seed` | set `room_roles` so lectures are booked into A109/A117 |

## Our HTTP APIs

| Service | Endpoint | Returns |
|---|---|---|
| all | `GET /healthz` | `{service, status, …}` — also the Compose healthcheck |
| `physics` | `GET /rooms`, `GET /rooms/{room}` | ground truth: `co2_ppm`, `temp_c`, `occupants`, `vent_level`, `setpoint_c`, `energy_kwh`, `t_out_c` |
| `pipeline` | `GET /history?room&type&minutes[&level]` | recent readings, oldest first |
| `pipeline` | `GET /query?sql=SELECT …` | read-only DuckDB over views `sensor, actuator, plan, decision, health` (SELECT/WITH only) |
| `pipeline` | `GET /stats`, `POST /compact` | row counts; rebuild silver Parquet |
| `control` | `GET /decisions` | last decision per room |
| `planner` | `GET /plans` | last plan per room |

**`physics` is not called by `control`, `planner` or the dashboard** — only by sensor processes. The truth
layer is unobservable to the control system by deployment, not by politeness.
