# Architecture document — CO₂-driven ventilation with thermal trade-off

| Project | CO₂-driven ventilation with thermal trade-off |
| Team | Group 2 — Tobias Hanke, Evangelos Vasilaras |
| Use case | Indoor air quality vs. heating energy, 5 rooms on level 0 of the A-house |
| Repository | https://github.com/TobiMacaronisGit/d7065e-group2 |

Companion documents: [`00-overview.md`](00-overview.md) (course requirements + what we decided),
[`requirements.md`](requirements.md), [`interfaces.md`](interfaces.md), [`decision-log.md`](decision-log.md),
[`test-plan.md`](test-plan.md). Diagrams: [`diagrams/`](diagrams) (D2 source, `make diagrams` renders SVG).
Measurements: `scripts/metrics.py` (§10).

---

## 1. Use case and building context

Rooms are equipped with CO₂ and temperature sensors. The system decides how much fresh air each room
gets and compensates the resulting heat loss. The conflict is genuine: **the same actuator appears in
both equations with opposite effects** — ventilation lowers CO₂ and raises heating demand. In Luleå,
where outdoor temperatures reach −20 °C, that trade-off is expensive in winter and nearly free in summer.
Both quantities build up over minutes rather than instantly, which is what makes forecasting useful
rather than decorative.

**BuildSim is the shared state**, and only that: it owns the building model (rooms, equipment), stores
current sensor values and actuator states, and streams the 3D view over WebSocket. It simulates nothing,
decides nothing, calls no one, and remembers nothing across a restart. Every component asks the same
integration question: *what do I read from BuildSim, and what do I write back?* The answers are in §5.

**The rooms** (`config/rooms.json`, height 3 m). Mixed roles give the controller genuinely different
regimes: two lecture halls that fill abruptly, a fika room, and two small offices.

| Room | Role | Area (m²) | Forecast capacity (persons) |
|---|---|---|---|
| A109 | Lecture | 188 | 94 |
| A117 | Lecture | 214 | 107 |
| A110 | Fika | 124 | 31 |
| A323 | Office | 17 | 4 |
| A113C | Office | 16 | 4 |

occupancysim would scatter lectures over about 50 halls on level 0, so `seed` overrides its room roles so
that only A109 and A117 are lecture rooms (D-11). That is a scenario choice, and we state it as one.

**Actors.** The *building manager* watches the dashboard and could override; *occupants* influence the
system only by being present. Neither is on the control path — the loop runs autonomously.

**Demo scenario.** One simulated weekday at 60×. People arrive; CO₂ rises; the planner raises ventilation
ahead of the threshold; room temperature drops and heating responds. At 10:15 a lecture room fills beyond
the forecast and the reactive loop catches it without the planner. A CO₂ sensor then freezes on a
plausible value: the room is marked *degraded* and control continues from occupancy. Finally a container
is killed mid-demo and the system degrades instead of dying.

---

## 2. Requirements

See [`requirements.md`](requirements.md): five functional, seven non-functional, one regulatory and one
safety requirement, each with a measurable acceptance criterion and the test that verifies it. The tension
that shapes the whole design: FR-01 (CO₂ down) and FR-02 (comfort) pull ventilation up, NFR-04 (energy)
pulls it down, REG-01 sets a hard floor, and NFR-03 forbids solving it by oscillating between them. That
is why a single threshold rule is not enough and why the safety clamp is applied *after* every other rule.

Time is the easiest thing to get wrong, so every criterion states its unit: **sim-min** is the building's
clock, **s wall** is real time, and at the default factor of 60 one wall second is one simulated minute.
The results against every criterion are collected in §10.

---

## 3. Architecture

### 3.1 Context (C4 level 1) — `diagrams/context.d2`

One box for our system, surrounded by the building manager, the occupants, and the two course-provided
systems (BuildSim, occupancysim). Everything physical is reached through BuildSim. The only other things
that cross the boundary are occupancysim's simulated clock and the room roles that `seed` writes to it.

| Crossing | Direction | What | Protocol |
|---|---|---|---|
| BuildSim | both | Sensor values, actuator states, room layers and alerts out; occupancy and actuator read-back in | REST |
| occupancysim | both | Simulated clock in; room roles out (once, by `seed`) | REST |
| Browser | BuildSim to browser | The 3D view | WebSocket, provided by BuildSim |

### 3.2 Containers (C4 level 2) — `diagrams/container.d2`

Each box is one Docker container, one repository folder, one service in `docker-compose.yml`.
Layers follow the L2 model: **truth** (never observable by control) → **device** → **infrastructure**.

| Container | Layer | One job | Why it is a separate process |
|---|---|---|---|
| `physics` | truth | ground truth CO₂/temperature per room, stepped on the simulated clock | it is the environment, not part of the control system; separating it is what lets us *know the truth* and measure how wrong the observations are. Only the sensors are given its URL |
| `sensor-<type>-<room>` ×10 | device | sample truth, add lag/noise/faults, report to BuildSim + broker | one fault domain per physical device: a frozen CO₂ sensor in A109 must not affect the temperature sensor beside it |
| `occupancy_counter` | device | head count per room from BuildSim's occupancy map as a sensor stream | one integration point with the whole-building occupancy collection; own failure domain |
| `actuator-<kind>-<room>` ×10 | device | validate command (issuer, range, age, target), travel at rate limit, report reached state | *proposing a command is not applying it* — validation and rate limiting belong to the device, not the decider |
| `broker` (Mosquitto) | infra | decouple publishers from consumers, buffer, retain last state | four consumers need the same readings; a consumer restart must not disturb the producers |
| `pipeline` | data | persist everything (bronze JSONL, silver Parquet via DuckDB), serve history + read-only SQL | remembering is a different job with a different failure mode from deciding; if it dies, control keeps regulating |
| `control` | autonomous | reactive rules, safety clamps, degraded handling, decision log | the fast loop; must be simple enough to verify and must survive the planner being wrong or absent |
| `planner` | autonomous | 30-min occupancy forecast → CO₂ rollout → suggested setpoints | the slow loop; heavier and less trustworthy, so it is advisory only and its failure cannot stop control |
| `viewer` | presentation | the single writer of BuildSim's room-layer and alert collections | those PUTs replace the whole collection — two writers would erase each other every cycle. It has no UI of its own; the 3D view is BuildSim's |
| `grafana` | presentation | time series from the pipeline | off-the-shelf; no UI code of ours on the critical path |
| `seed` (one-shot) | setup | register devices, point occupancysim's lectures at our rooms | runs once and exits; not part of the running system. Devices also register themselves, so it is a convenience |

### 3.3 The two loops

This is the L1 model made concrete:

- **Fast loop (`control`, every 5 s wall ≈ 5 sim-min):** reads observations, applies thresholds with
  hysteresis, clamps to the safety floor, commands actuators. It always runs and keeps rooms safe no
  matter what else fails. It is deliberately rule-based: verifiable, explainable in an oral exam, and
  fast enough that latency is never the reason a room goes over the limit. Every round it publishes a
  decision with its inputs and reason, and it sends a command only when a target changed.
- **Slow loop (`planner`, every 10 s wall):** forecasts occupancy 30 sim-min ahead, rolls the CO₂ mass
  balance forward for each ventilation level, and publishes the smallest level that keeps the forecast
  peak under 900 ppm. **A plan may raise ventilation or the setpoint; it can never lower them.** A
  stale, missing or wrong plan therefore degrades the system to "reactive only", never to unsafe. `control`
  drops a plan that is older than twice its horizon, which is 60 sim-min, one wall minute.

The rules, from `config/rooms.json` (`control` block), applied in this order:

| Layer | Rule | Configured |
|---|---|---|
| Safety | CO₂ at or above the safety level forces full ventilation | 1200 ppm |
| Reactive | Level 2 at or above the high threshold, level 1 at or above the raise threshold, else 0 | 1000 ppm, 800 ppm |
| Planner | A fresh plan may raise ventilation, and the setpoint of an empty room (pre-heat) | 60 sim-min freshness |
| Hysteresis | Stepping down needs a margin below the threshold *and* a minimum dwell time | 100 ppm, 300 sim-s |
| Setpoint | Comfort when occupied (or no data), setback when empty | 21 °C, 17 °C |
| Floor | Ventilation level never below the minimum, applied last | `vent_min_level` 0 |

Because one wall second is one simulated minute, the reactive loop is slow in building time: a control
round takes up to 5 sim-min and the vent needs 4 to 6 sim-min to reach level 2 or 3. Starting at 800 ppm
rather than 1000 ppm helps, but this is exactly the gap the planner exists to close, and what experiment
E3 measures. There is also a physical limit: at the maximum ventilation level a room holds 1000 ppm only for
about 72 persons (A109), 82 (A117) and 47 (A110), so above that no controller can meet FR-01 (§9).

> **Note (10 Oct):** these limits are for the old ventilation (`ach_per_vent_level` 1.3). With 3.6 the same
> formula gives about 129 / 147 / 85 persons at level 2 and 192 / 219 / 127 at level 3 (A109 / A117 / A110);
> see `docs/results/predictions.md`.

### 3.4 Data quality as a control input

A rule controller that trusts its inputs fails the interesting way: a CO₂ sensor frozen on 700 ppm looks
perfectly healthy and silently defeats FR-01. `control` therefore classifies every CO₂ input as
`ok | stale | frozen | missing` before using it (rolling identical-value check plus a freshness window in
simulated time) and falls back to occupancy — a second, independent signal — when it is not `ok`.
Data quality is treated as a first-class input, not as noise.

As built: a reading is `stale` after 300 sim-s and `frozen` after 8 identical samples. With no trustworthy
CO₂ and no occupancy either, the room goes to `NO_DATA`, ventilates at level 2 and heats as if occupied.

Three blind spots are known, and we report them rather than hide them:

1. **Detection speed.** At 2 s wall per sample (assuming `SAMPLE_S` is in wall seconds, which `sensor/main.py` should
   confirm), 8 identical samples take about 14 sim-min, plus up to 5 sim-min until the next control round,
   against the 10 sim-min of NFR-05. An offline run of the real rules gives 14 to 20 sim-min (§10.5), and F1 will measure it. Lowering the sample count detects earlier but risks false alarms.
2. **Drift.** A slow bias is not a frozen value, so the check cannot see it (F2). Cross-checking CO₂
   against the physics-expected rise given occupancy would.
3. **The planner has no age check of its own.** `/history` windows are counted back from the newest
   reading, so a dead sensor's last value looks current to the planner, while `control` does check age.

### 3.5 Design decisions

Full table with alternatives and trade-offs: [`decision-log.md`](decision-log.md). The index:

| # | Decision | Chosen |
|---|---|---|
| D-01 | Implementation language | Python 3.12 for all our services (against the Go recommendation, so we measure the cost) |
| D-02 | Inter-service transport | MQTT, QoS 1, persistent sessions, retained commands, states and plans |
| D-03 | Historical storage | `pipeline`: bronze JSONL → silver Parquet via DuckDB, HTTP query API |
| D-04 | Dashboard | BuildSim overlays through one `viewer` container, plus Grafana |
| D-05 | Device granularity | One container per physical device, Compose generated from `config/rooms.json` |
| D-06 | Occupancy source | `GET /api/occupancy` from BuildSim, published there by occupancysim |
| D-07 | Forecast method | Linear regression on lagged occupancy and time of day, then a deterministic CO₂ rollout |
| D-08 | Decision architecture | Reactive rules and safety clamp, advisory planner that may only raise |
| D-09 | Command authority | `control` proposes; the actuator process validates and applies |
| D-10 | Time authority | occupancysim's clock; every message carries `ts` and `sim_ts` |
| D-11 | Room selection | A109, A117 lecture; A110 fika; A323, A113C offices; roles overridden |
| D-12 | Physics | One container for all rooms |

Three decisions showed their consequences only once the system was built:

- **D-08.** The planner cannot lower ventilation, so it targets FR-04 (fewer exceedances), not energy.
  The energy saving of NFR-04 comes from the occupancy-driven setback in `control`.
- **D-02 and D-09 together.** Actuators reject commands older than 120 s wall, and `control` sends a command
  only when a target changes. A retained command therefore recovers a restarted actuator only within
  120 s (§9).
- **D-01.** About 25 Python containers on one laptop set the resource ceiling, which is what E4 finds.

---

## 4. Behaviour

- **Dynamic diagram** (`diagrams/dynamic.d2`): the lecture-fills scenario, numbered interactions from the
  occupancy write through forecast, decision, command, actuator travel, BuildSim state, physics read-back,
  to the next reading. This is the diagram that shows the loop actually closing.
- **State machine** (`diagrams/state.d2`): the per-room controller lifecycle
  `NO_DATA → NORMAL ⇄ DEGRADED`, with `SAFETY` reachable from both and every transition labelled with the
  condition that triggers it. Every transition in that diagram is a branch in `control/rules.py`.

**The loop, in eight steps.** (1) occupancysim places people in BuildSim. (2) `physics` reads occupancy and
the actuator states from BuildSim — the read-back that closes the loop. (3) A sensor reads the true value
from `physics`, (4) degrades it, and publishes it, and writes it to BuildSim for the 3D view. (5) `control`
receives the reading and any plan, (6) decides, and publishes a retained command. (7) The actuator
validates it and (8) travels to the target, writes the reached state to BuildSim and publishes it. Step 2
then sees the new state.

**What happens when something breaks** (the full semantics are in [`interfaces.md`](interfaces.md)):

| Situation | Behaviour |
|---|---|
| Invalid command (wrong issuer, wrong actuator, out of range, no `ts`, older than 120 s wall) | Rejected and counted by the actuator, never applied (SAF-01) |
| BuildSim restarts and answers 404 | Each device re-registers itself and retries (NFR-06) |
| BuildSim unreachable | Devices keep publishing to MQTT, log once, report `degraded`; `physics` holds its last inputs |
| Broker unreachable | Clients reconnect with backoff; persistent sessions and QoS 1 redeliver what was missed; failed publishes are queued (NFR-07) |
| occupancysim unreachable | Clocks extrapolate at the last factor and report `clock_degraded` |
| CO₂ stale or frozen | Room becomes `DEGRADED`, decided from occupancy (NFR-05) |
| No CO₂ and no occupancy | Room becomes `NO_DATA`, ventilated at a safe default |
| Pipeline down | `planner` publishes nothing new; `control` drops the last plan after 60 sim-min and runs reactively |
| `control` restarts | Stateless; sends its commands again in its first round |
| An actuator restarts | Starts at its initial value; accepts the retained command only if it is under 120 s old (§9) |
| A service dies | The broker publishes `down` on its `sys/health/<service>` (last will) |

---

## 5. Interfaces

See [`interfaces.md`](interfaces.md) — message schemas with units, the MQTT topic tree, the BuildSim
endpoints each container touches, and the HTTP APIs of `physics`, `pipeline`, `control`, `planner`.
Written to be precise enough that another team could rebuild the system from it; the code
(`common/schemas.py`, `common/topics.py`, `common/buildsim.py`) wins if they ever disagree.

The summary, so this document stands on its own. **MQTT** carries everything with several consumers
(QoS 1, at-least-once, so consumers tolerate duplicates). **REST** carries everything one-to-one whose
result the caller must confirm: all BuildSim traffic, `planner` to `pipeline`, and every `/healthz`.
Every payload carries `ts` (wall) and `sim_ts` (simulated).

| Topic | Payload | Retained | Publisher | Subscribers |
|---|---|---|---|---|
| `bldg/<level>/<room>/sensor/<type>` | `SensorReading` | no | sensors, `occupancy_counter` | `control`, `pipeline`, `viewer` |
| `bldg/<level>/<room>/actuator/<kind>/cmd` | `ActuatorCommand` | yes | `control` | actuators, `pipeline` |
| `bldg/<level>/<room>/actuator/<kind>/state` | `ActuatorState` | yes | actuators | `pipeline` (`control` is planned) |
| `bldg/<level>/<room>/plan` | `Plan` | yes | `planner` | `control`, `pipeline` |
| `bldg/<level>/<room>/decision` | `Decision` | no | `control` | `pipeline`, `viewer` |
| `sys/health/<service>` | `Health` | yes, with last will | every service | `viewer`, `pipeline` |
| `sys/fault/<device-id>` | `{"mode": …}` | no | `scripts/inject_fault.sh` | that device |

`<type>` is co2, temperature or occupancy; `<kind>` is vent or heat. Fault modes: `none` clears; sensors
accept `stuck`, `offline`, `drift`; actuators accept `stuck`, `slow`. The pipeline subscribes to `bldg/#` and
`sys/health/#` only, so injected faults are not recorded and experiment logs must note the injection time.

Who touches BuildSim: sensors and `occupancy_counter` write sensor values; actuators write reached states;
`physics` reads occupancy and actuator states; `occupancy_counter` reads occupancy; `viewer` writes room layers
and alerts; `seed` bulk-registers devices and reads the floor plan. Devices also use the same bulk call to
register themselves. Values and states are strings, rooms are keyed `<level>/<room>`, and collection PUTs
replace the whole collection.

Our own HTTP APIs, all with `GET /healthz`:

| Service (host port) | Endpoints |
|---|---|
| `physics` (8090) | `GET /rooms`, `GET /rooms/{room}`: CO₂, temperature, occupants, vent level, setpoint, heater power, energy, outdoor temperature |
| `control` (8091) | `GET /decisions`: last decision per room |
| `pipeline` (8092) | `GET /history`, `GET /query?sql=`, `GET /stats`, `POST /compact` |
| `planner` (8093) | `GET /plans`: last plan per room |
| `viewer` (8094) | `GET /healthz` only |

---

## 6. Simulating the sensor values

`physics/model.py`. CO₂ is a mass balance driven by occupancy and ventilation; temperature is a heat
balance over envelope loss, body heat, heater power and ventilation loss; outdoor temperature follows an
annual plus daily cosine for Luleå (the sign of the daily term is currently inverted, see §9). Occupancy is **not** invented — it comes from the course's
occupancysim through BuildSim, which gives us realistic arrivals, lectures, fika and lunch for free and
keeps a well-known part of the simulation out of our own code.

```
CO₂:          dC/dt = g·n·1e6/V − (Q/V)·(C − C_out)
Temperature:  C_th·dT/dt = k_env·(T_out − T) + q_body·n + P_heat − ρ·c_p·Q·(T − T_out)
Flow:         Q = (ACH_inf + level·ACH_per_level)·V/3600
Heater:       P_heat = clamp(K_heater·(setpoint − T), 0, P_max)
```

The ventilation level `Q` is the one actuator in both equations. The parameters (`config/rooms.json`) are
420 ppm outdoor CO₂, 5.2e-6 m³/s of CO₂ per person, 0.2 air changes per hour of infiltration plus 1.3 per
ventilation level, 2.5 W/K of envelope loss per m² of floor, 60 kJ/K of thermal mass per m³, 100 W per
person, and a heater of up to 80 W/m² with a gain of 40 W/K per m². `physics` ticks every wall second and
advances every room by the clock factor, in sub-steps of at most 30 simulated seconds. The sensors then
degrade the truth: 2 s sampling, 30 s lag, noise of σ 15 ppm and 0.1 °C, and injectable faults.

The property that matters: **actuator commands feed back into these equations through BuildSim**. The
physics reads actuator state from BuildSim every 2 s wall; if that read-back were missing, the loop would
never close and the whole system would be a dashboard. The planner reuses the same `step` function for its
CO₂ rollout, so its predictions and the simulator cannot drift apart.

**Time.** occupancysim is the single time authority (D-10). `SimClock` polls its `/api/state` every 5 s,
extrapolates in between, and keeps going with `degraded` set if occupancysim disappears. `physics`,
`control`, `planner` and `occupancy_counter` use it. Honest limitations are listed in §9.

---

## 7. Autonomous services and data engineering

**Autonomy**: `control` (rules + hysteresis + safety clamp + degraded handling) and `planner` (linear
regression forecast + physics rollout). Rule-based was chosen over a learned controller because it meets
the latency budget, is verifiable for a safety-relevant function, and can be explained from memory in the
oral exam; a learned *forecast* was added exactly where learning helps — predicting the future occupancy
that the physics cannot know. The planner is evaluated against a persistence baseline on a different
simulated day than it was trained on (`planner/train.py`), because occupancysim replays a date
deterministically and a random split would leak the test day into training.

**The planner, step by step.** Every 10 s wall and per room it (1) fetches 120 min of occupancy and 10 min
of CO₂ and temperature from the pipeline, (2) resamples occupancy to 5-minute bins and builds nine features
(a constant, occupancy now and 5, 10, 15, 30 and 60 min ago, `sin` and `cos` of the time of day), (3) predicts
occupancy for +5 to +30 min with one linear model per horizon, clamped to the room's capacity (persistence
if no model exists), (4) rolls the CO₂ balance forward for each ventilation level and picks the smallest one
that stays under 900 ppm, and (5) publishes a retained plan, with the occupied setpoint if anyone is
expected. The model is loaded once at start, so a newly trained model needs a planner restart.

**Training** (`make train`, which compacts first). Occupancy is binned to 5 minutes per simulated date and
room, samples from all rooms are pooled, and each horizon is fitted by least squares. The split is by
simulated date: the last date is the test day, so at least two recorded days are needed (about 48 wall
minutes). It prints the mean absolute error per horizon for the model and for persistence, then saves
`planner/model.json`, whatever the comparison shows.

**Pipeline**: sensors/actuators/plans/decisions/health → MQTT → `pipeline` → bronze JSONL (exactly what
arrived, `data/bronze/<sim-date>/<kind>.jsonl`) → silver Parquet (typed, de-duplicated, via DuckDB,
rebuilt every 300 s and on demand) → gold (training and evaluation tables).
Each row keeps the producer's `ts` and `sim_ts` plus the pipeline's `recv_ts`, so per-hop latency is
measurable rather than asserted. `/history` and `/query` read the live bronze files, so they are always
fresh; silver is for training. The pipeline uses a persistent session, so after a short outage the broker
delivers what it missed, and Grafana reads the same data through `/query` with the Infinity plugin: four
panels (CO₂, temperature, ventilation level with occupancy, latest decisions with reasons).

---

## 8. Deployment

Everything runs on one laptop, so deployment is about composition, not geography: ~25 containers, each
independently startable, stoppable and restartable, communicating only over the network interfaces in §5.
If this were a real building, the split would be: sensors, actuators, broker, `control` and `pipeline` on
a **local edge server** (the building must keep regulating itself when the internet is down — the
"local survivability" argument from L1); `planner` training and long-term analysis on **external compute**,
because they are slow, off the critical path, and a stale model is harmless. That is exactly why the
planner is advisory-only in §3.3: the architecture already tolerates the component that would be remote
being unavailable.

**As built.** One Compose project (`d7065e-group2`); `compose.devices.yml`, generated from
`config/rooms.json`, holds the 20 device containers. Startup follows health checks, not sleeps:
`broker` and `buildsim` first, then `occupancysim`, then `seed` (which waits for both and exits), then
`physics`, then everything else. Every published port is bound to `127.0.0.1`, and every container restarts
automatically except `seed`.

| Service | Host port | | Service | Host port |
|---|---|---|---|---|
| `broker` | 1883 | | `pipeline` | 8092 |
| `buildsim` | 9090 | | `planner` | 8093 |
| `occupancysim` | 8081 | | `viewer` | 8094 |
| `physics` | 8090 | | `grafana` | 3000 |
| `control` | 8091 | | | |

All containers share one default Compose network. State lives in two places only: the `mosquitto-data`
volume (retained messages and queued sessions) and the `./data` mount of the pipeline.

---

## 9. Risks, assumptions, critical reflection

| Risk / assumption | Impact | Mitigation / how we will report it | Status |
|---|---|---|---|
| BuildSim has no persistence and no auth | single point of failure for the whole system | devices re-register on 404 (NFR-06); reported as a platform limitation, with the recovery time measured | F5 |
| Broker is a single point of failure | all fan-out stops | persistent sessions + retained state; measure what actually happens during `stop broker` | F4 |
| **A restarted actuator may never recover.** The retained command keeps its original `ts`, the actuator rejects commands older than 120 s, and `control` re-sends only on a target change | after an actuator crash the room stays at the initial value (vent 0, heat 17 °C) until the target changes | confirm with F3 on `actuator-vent-a109` during a lecture; fix by having `control` re-send commands periodically (also a heartbeat), or by skipping the age check for a retained redelivery | predicted from code |
| **Frozen-sensor detection is slower than NFR-05.** 8 samples at 2 sim-min plus a control round is about 14 to 19 sim-min | NFR-05 (10 sim-min) fails by configuration | measure in F1; lower `frozen_after_samples` and accept more false alarms, or report the gap | predicted from configuration |
| **The outdoor temperature's daily term is inverted** in `physics/model.py`: the coldest hour is 15:00 and the warmest 03:00, against a docstring that says the opposite | afternoon lectures meet the worst weather; heating energy and comfort are biased in every run | change `-daily_amplitude_c` to `+daily_amplitude_c` (maximum at 15:00; a cosine cannot also put the minimum at 05:00) and add a test; re-run after the fix | found offline |
| **FR-02 is not reachable as configured.** The heater is proportional, so the room settles below the setpoint (3 % of occupied time in band at 21 °C, 98 % at 22 °C), and a lecture room in setback needs about 3.8 h to heat from 17 to 20 °C in September | FR-02 (90 % in band) fails for lecture rooms | raise `setpoint_occupied_c` to 22, use a pre-heat lead longer than the planner's 30 min or a shallower setback, or restrict FR-02 to rooms that are occupied continuously | predicted offline |
| **FR-01 has a physical limit.** At maximum ventilation a room holds 1000 ppm only for about 72 persons (A109), 82 (A117), 47 (A110), 6 (offices). *Old ventilation (1.3 ACH/level); since 10 Oct (3.6): 192 / 219 / 127 / 16–17 at level 3* | above that no controller can meet FR-01, however good the planner | report the scenario's occupancy against these limits | predicted offline |
| The heater cannot carry the winter trade-off: with its 80 W/m² it holds 21 °C only above about +6 °C outdoors at ventilation level 2 (about −1 °C with 70 persons), and above about −9 °C with no ventilation | in January the heater saturates, so energy and comfort comparisons degenerate | choose the evaluation date with this in mind and say which one it is | predicted offline |
| The 5 sim-min criterion of NFR-03 cannot discriminate: the control round is itself 5 sim-min | E2 passes with or without hysteresis | report total changes or oscillation amplitude as well (hysteresis cut vent changes by about 17 % offline) | predicted offline |
| The planner's benefit comes from sizing ventilation with the physics rollout, not from forecast skill: a persistence forecast is as good as a perfect one at 50 and 70 persons | the premise of D-07 (forecasting future occupancy) may not show in E3 | evaluate the forecast (E5) and the planner's benefit (E3) separately, and say so | **measured (E3, 10 Oct): partly true** — persistence gives −87 %, the timetable the remaining 13 points |
| **The pipeline's history window followed the latest stored reading, not the current time.** After a clock jump or a replayed day, `/history` returned another run's data (at sim 08:30 on 21 Oct: 22 Oct 10:07–10:37) | the planner forecast and rolled out from wrong data; invalidated the first E3 runs R2/R3 | **fixed 10 Oct:** `/history` takes `until` and `max_age_s`, the planner sends both; regression test `test_history_until_ignores_a_replayed_day` | found live (E3) |
| **Reactive control oscillates after the ventilation change.** Level 2 holds a full lecture room at ≈ 880 ppm, just below the 900 ppm step-down threshold (1000 − 100 hysteresis), so control drops to level 1 and CO₂ climbs back over 1000 | reactive only: 149 sim-min over 1000 ppm and 38 vent changes per day (R1) | the planner hides it by holding level 2; the direct fix is to re-tune `co2_hysteresis_ppm` / the thresholds to the 3.6 ACH ventilation | found live (E3) |
| A plan's age is checked as `now − plan_ts ≤ 60 sim-min`; after the clock jumps back, a plan from "later" has a negative age and counts as fresh | a stale plan can drive ventilation for up to one planner cycle (10 s wall) | clear retained plans when the clock jumps back (done for the E3 runs); reject negative ages in `control/rules.py` | found in code |
| Drift defeats the frozen check | a slowly biased sensor goes unnoticed | cross-check CO₂ against the physics-expected rise; report as a limitation (F2) | predicted |
| The planner has no staleness check | a dead sensor's last value looks current to the planner | add an age check to the planner, or rely on `control` dropping plans; observe in F1 | predicted from code |
| `vent_min_level` is 0 | REG-01 is met trivially; the minimum flow is infiltration alone (0.2 air changes per hour) | decide what REG-01 means; if a real minimum is intended, set 1 or more | decision pending |
| occupancysim is deterministic per date+seed | the forecast may look better than it is | train and evaluate on different dates/seeds; report both | E5 |
| Training and serving prepare occupancy slightly differently (maximum vs. last value per bin, time-of-day source) | forecast error that the evaluation does not show | align both paths; check the time zone if training on the host | to check |
| `train.py` saves the model even when persistence is better; one model is pooled over rooms of 16 to 214 m² | a worse model can reach the planner | keep the old model when it loses, or report the result (E5) | **handled 10 Oct:** the model lost; moved to `docs/results/model-lr-v1.json`, never deployed |
| Two clocks (wall vs. 60× simulated) | dwell times and windows silently wrong | one time authority (`common/clock.py`), every message carries both timestamps; extrapolation reported as `clock_degraded` | F7 |
| ~25 Python containers on a laptop | resource limits reached before architectural ones | measure RAM/CPU and the decision-latency curve; that *is* the breaking-point experiment | E4 |
| Simplified physics (perfect mixing, no inter-room exchange, no solar gain, no humidity) | energy and comfort figures flatter the system | always report relative to the baseline, never as absolute kWh | by design |
| No authentication or encryption anywhere; the `/query` guard only checks that a statement starts with SELECT or WITH | anyone on the machine can publish, query or administer Grafana | stated non-requirement (BuildSim has none); ports are bound to localhost | accepted |

---

## 10. Verification and evaluation

This is the validation half of the traceability thread. This section holds the results. Every run uses the same simulated date and
occupancysim seed, `OCCUPANCY_FACTOR=60` and 5 rooms, and the metrics are computed from the pipeline, not from
logs.

> **How to read the Result column (10 Oct):** **Live** = measured in the running system, with the raw data in
> `docs/results/`. Entries without "Live" (written 7 Oct) come from **offline** runs of the model and rules, not
> from the running system; they stay estimates until the experiment is run live.

### 10.1 Requirements against evidence

| ID | Criterion in short | Verified by | Offline prediction | Result |
|---|---|---|---|---|
| FR-01 | CO₂ back under 1000 ppm within 10 sim-min | `test_reactive_levels_and_safety_override`, S1 | Holds only below the level-3 capacity of the room (about 72 persons in A109). With 70 persons the reactive loop alone spends about 150 sim-min over 1000 ppm; with the planner about 6 | **Live (R5, 10 Oct): pass in the lecture rooms** — 0 sim-min over 1000 ppm (102–116 persons, below the new level-2 capacity). Reactive only (R1): 149 sim-min. A110 (fika, no bookings): 22 sim-min. [`e3-summary.md`](results/e3-summary.md) |
| FR-02 | At least 90 % of occupied sim-min in 20 to 24 °C | S1 | Fails for lecture rooms: they start in setback and need about 3.8 h to reach 20 °C in September, and a 21 °C setpoint settles about 1.5 K low (3 % in band; 98 % at 22 °C) | **Live (R1–R5): fail** — 0 % of occupied sim-min in band in every run; rooms end the day at 13.8–15.8 °C (offices ≈ 18 °C) |
| FR-03 | Setback within 15 sim-min of a room emptying | `test_stale_co2_is_not_trusted`, S1 | The decision follows within one control round (5 sim-min), but the heat actuator needs 10 sim-min to ramp from 21 to 17 °C, so the reached state is borderline | Estimate: borderline |
| FR-04 | At least 50 % fewer exceedance sim-min than reactive-only | `test_suggest_vent_raises_ahead_of_a_lecture`, E3 | Met at 50 and 70 persons (96 to 100 % fewer), but through ventilation sizing, not forecast skill; at 90 persons (above capacity) only 13 % | **Live: pass** — persistence (R4) −87 % (149 → 20 sim-min), timetable (R5) −100 % (149 → 0), against reactive only (R1) |
| FR-05 | Decisions carry reason and inputs, retrievable | `pipeline/test_storage.py`, dashboard | Met by construction: every `Decision` carries `reason` and `inputs` and is recorded in the `decision` view | Estimate: pass (by construction) |
| NFR-01 | Median decision interval at most 60 s wall under full load | E4 | The round is 5 s wall by configuration; the limit is resource-bound at scale |
| NFR-02 | Correct command within 60 s of a crash, nothing unsafe between | F1 to F4 | Sensor, `control` and `pipeline`: recover. A restarted actuator: stays at its initial value (§9) | Result: pass, except the actuator restart (§9) |
| NFR-03 | No actuator change more than once per 5 sim-min (not SAFETY) | `test_hysteresis_blocks_early_step_down`, E2 | Cannot fail, because the control round is 5 sim-min; hysteresis cuts total vent changes by about 17 % (11 against 13 per day) | Result: pass |
| NFR-04 | Heating energy no more than a fixed-schedule baseline | E1 | Met in the model: −46 % in September and −21 % in January against an assumed baseline (level 2 and 21 °C, 07:30 to 17:00) | Result: pass (−46 % in September, −21 % in January) |
| NFR-05 | Stuck CO₂ sensor detected within 10 sim-min | `test_frozen_sensor_marks_room_degraded_and_uses_occupancy`, F1 | Fails with 8 samples: 14 to 20 sim-min. With 3 samples 4 to 10 sim-min, with 0.3 false alarms per sensor-day if readings are whole ppm and none with one decimal | Result: fail (14 to 20 sim-min) |
| NFR-06 | Devices recover from a BuildSim restart within 60 s wall | F5 | From the code: each device re-registers on a 404 and retries | 
| NFR-07 | No readings lost in a 60 s pipeline outage | F3 | From the code: persistent session with QoS 1 | 
| REG-01 | Vent level never below the minimum, in every state | `control/test_rules.py`, code review | Met: the clamp is the last step of the ventilation decision in all four states. Met trivially, because `vent_min_level` is 0 | Pass (code review and offline check) |
| SAF-01 | Invalid commands never applied | `actuator/test_validate.py`, F6 | All six invalid cases are rejected (other issuer, other actuator, target 99, 10 minutes old, non-numeric target, missing `ts`) | Result: pass (6 of 6 invalid commands rejected) |


### 10.2 Scenario and experiments

| Id  | What is run                                                                   | Prediction written before the run                                                                                                                                                       | Result                                                                          |
| --- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| S1  | One simulated weekday, full system                                            | FR-01 holds while the lecture is below the room's capacity; FR-02 fails for the lecture rooms (cold start, proportional heater); the rest per §10.1                                     | **Live (= R5, 10 Oct):** FR-01 pass in the lecture rooms (0 sim-min > 1000 ppm, peak 912), FR-02 fail (0 % in band), 324.6 kWh |
| E1  | Full system against a fixed-schedule baseline (vent and heat on office hours) | Passes: 20 to 46 % less heater energy, because the baseline ventilates and heats an empty room. Comfort is poor in both                                                                 | Result: −46 % kWh (September), −21 % (January), model only                      |
| E2  | Hysteresis on and off                                                         | Both pass the 5 sim-min criterion by construction; the difference is only in total changes (about 17 % fewer with hysteresis)                                                           | Result: 11 against 13 vent changes; both pass the 5 sim-min criterion           |
| E3  | Planner on and off                                                            | At least 50 % fewer exceedance sim-min for 50 to 70 persons, almost entirely from sizing ventilation with the physics rollout. Heater energy rises (about 44 to 59 kWh in the model)    | **Live (R1 / R4 / R5, 10 Oct):** exceedance 149 / 20 / 0 sim-min (−87 % / −100 %), peak 1108 / 1093 / 912 ppm, vent changes 38 / 13 / 11, energy 280.5 / 318.9 / 324.6 kWh (+14 % / +16 %). Run as three variants: off, persistence, timetable. [`e3-summary.md`](results/e3-summary.md) |
| E4  | 5, 10, 20, 40 rooms and sample interval 2 s down to 0.5 s                     | Breaks on container resources, not on the architecture (a consequence of D-01)                                                                                                          |                                                                                 |
| E5  | Forecast against persistence, split by simulated date                         | May barely beat persistence, because occupancysim's day plans are smooth; say so plainly. The offline run points the same way: a perfect forecast adds about one point over persistence | **Live (10 Oct):** the linear model loses to persistence at every horizon (MAE 2.17 vs 1.29 people at 5 min, 9.21 vs 5.34 at 30 min); not deployed. The planner uses the booking timetable instead. [`train.txt`](results/train.txt), [`forecast-notes.md`](forecast-notes.md) |

### 10.3 Fault injection

| Id | Fault | Expected | Result |
|---|---|---|---|
| F1 | CO₂ sensor freezes (`inject_fault.sh A109-co2 stuck`) | Room `DEGRADED`, control continues from occupancy. Offline detection takes 14 to 20 sim-min against the 10 of NFR-05 (§3.4) | Result: detected after 14 to 20 sim-min (fail) |
| F2 | CO₂ sensor drifts | Not detected: the state stays NORMAL while the room is ventilated for the wrong value. A plausibility bound (a reading below the 420 ppm outdoor level is impossible) would catch large drifts | Result: not detected |
| F3 | Process crash: sensor, `control`, `pipeline`, actuator | Others keep running and the loop resumes; the actuator is predicted to stay at its initial value until the target changes (§9) | 
| F4 | Broker down 60 s | Producers buffer, consumers resume, retained state restores targets | 
| F5 | BuildSim restart | Devices self-register on 404, read-back resumes without re-seeding |
| F6 | Invalid command (`issued_by: attacker`, `target: 99`, old `ts`) | Rejected and counted; offline, all six invalid cases are rejected and the valid one applied | Result: all invalid commands rejected |
| F7 | occupancysim down | Clocks extrapolate, `clock_degraded`, physics keeps stepping |
| F8 | Plan suggesting vent 0 at 1100 ppm | Reactive rules win: offline the commanded level is 2, and a plan of 3 at 700 ppm raises it to 3 | Result: vent level 2, the reactive rule wins |


## Appendix A. Runtime reference

**Configuration** (`.env` and Compose defaults):

| Variable | Used by | Value |
|---|---|---|
| `COURSE_REPO` | Compose build | `../../D7065E` |
| `OCCUPANCY_LEVELS`, `OCCUPANCY_FACTOR`, `OCCUPANCY_START` | `occupancysim` | `level0`, `60`, `07:30` |
| `BUILDSIM_URL` | most services | `http://buildsim:9090` |
| `OCCUPANCY_URL` | `seed`, `physics`, `occupancy_counter`, `control`, `planner` | `http://occupancysim:8081` |
| `PHYSICS_URL` | sensors only | `http://physics:8000` |
| `PIPELINE_URL` | `planner` | `http://pipeline:8000` |
| `MQTT_HOST` | all MQTT clients | `broker` |
| `EVAL_S`, `PLAN_S` | `control`, `planner` | `5`, `10` |
| `COMPACT_S`, `DATA_DIR` | `pipeline` | `300`, `/data` |

**Operator commands:**

| Command | Effect |
|---|---|
| `make gen` | Regenerate `compose.devices.yml` from `config/rooms.json` |
| `make up` / `make down` | Generate, build and start the stack / stop it |
| `make logs` | Follow `control`, `planner` and `physics` |
| `make test` / `make e2e` | Unit tests without Docker / end-to-end test against the running stack |
| `make seed` | Register devices and room roles by hand |
| `make compact` / `make train` | Compact recorded data / compact, then train the occupancy model |
| `make diagrams` | Render `docs/diagrams/*.d2` to SVG |
| `make clean` | Stop the stack, delete volumes and `data/bronze` and `data/silver` |

**Broker** (`broker/mosquitto.conf`): port 1883, anonymous clients, persistence on with autosave every 30 s,
at most 10,000 queued messages per client, logs to stdout.
