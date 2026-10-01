# Architecture document — CO₂-driven ventilation with thermal trade-off

**Living document.** Started at the design-approval gate (week 3), refined as the system is built,
submitted with the final report. If this document and `docker-compose.yml` disagree, one of them is a bug.

| Field | Value |
|---|---|
| Project | CO₂-driven ventilation with thermal trade-off |
| Team | Group 2 — Tobias Hanke, Evangelos Vasilaras |
| Use case | Indoor air quality vs. heating energy, 5 rooms on level 0 of the A-house |
| Repository | https://github.com/TobiMacaronisGit/d7065e-group2 |
| Version | v0.1 (skeleton) |

Companion documents: [`00-overview.md`](00-overview.md) (course requirements + what we decided),
[`requirements.md`](requirements.md), [`interfaces.md`](interfaces.md), [`decision-log.md`](decision-log.md),
[`test-plan.md`](test-plan.md). Diagrams: [`diagrams/`](diagrams) (D2 source, `make diagrams` renders SVG).

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

**Actors.** The *building manager* watches the dashboard and could override; *occupants* influence the
system only by being present. Neither is on the control path — the loop runs autonomously.

**Demo scenario.** One simulated weekday at 60×. People arrive; CO₂ rises; the planner raises ventilation
ahead of the threshold; room temperature drops and heating responds. At 10:15 a lecture room fills beyond
the forecast and the reactive loop catches it without the planner. A CO₂ sensor then freezes on a
plausible value: the room is marked *degraded* and control continues from occupancy. Finally a container
is killed mid-demo and the system degrades instead of dying.

---

## 2. Requirements

See [`requirements.md`](requirements.md). The tension that shapes the whole design: FR-01 (CO₂ down) and
FR-02 (comfort) pull ventilation up, NFR-04 (energy) pulls it down, REG-01 sets a hard floor, and NFR-03
forbids solving it by oscillating between them. That is why a single threshold rule is not enough and why
the safety clamp is applied *after* every other rule.

---

## 3. Architecture

### 3.1 Context (C4 level 1) — `diagrams/context.d2`

One box for our system, surrounded by the building manager, the occupants, and the two course-provided
systems (BuildSim, occupancysim). Everything physical is reached through BuildSim; nothing else crosses
the boundary.

### 3.2 Containers (C4 level 2) — `diagrams/container.d2`

Each box is one Docker container, one repository folder, one service in `docker-compose.yml`.
Layers follow the L2 model: **truth** (never observable by control) → **device** → **infrastructure**.

| Container | Layer | One job | Why it is a separate process |
|---|---|---|---|
| `physics` | truth | ground truth CO₂/temperature per room, stepped on the simulated clock | it is the environment, not part of the control system; separating it is what lets us *know the truth* and measure how wrong the observations are |
| `sensor-<type>-<room>` ×10 | device | sample truth, add lag/noise/faults, report to BuildSim + broker | one fault domain per physical device: a frozen CO₂ sensor in A109 must not affect the temperature sensor beside it |
| `occupancy_counter` | device | head count per room from BuildSim's occupancy map as a sensor stream | one integration point with the whole-building occupancy collection; own failure domain |
| `actuator-<kind>-<room>` ×10 | device | validate command, travel at rate limit, report reached state | *proposing a command is not applying it* — validation, rate limiting and retries belong to the device, not the decider |
| `broker` (Mosquitto) | infra | decouple publishers from consumers, buffer, retain last state | four consumers need the same readings; a consumer restart must not disturb the producers |
| `pipeline` | data | persist everything, serve history + SQL | remembering is a different job with a different failure mode from deciding; if it dies, control keeps regulating |
| `control` | autonomous | reactive rules, safety clamps, degraded handling, decision log | the fast loop; must be simple enough to verify and must survive the planner being wrong or absent |
| `planner` | autonomous | 30-min occupancy forecast → CO₂ rollout → suggested setpoints | the slow loop; heavier and less trustworthy, so it is advisory only and its failure cannot stop control |
| `viewer` | presentation | the single writer of BuildSim's room-layer and alert collections | those PUTs replace the whole collection — two writers would erase each other every cycle |
| `grafana` | presentation | time series from the pipeline | off-the-shelf; no UI code of ours on the critical path |
| `seed` (one-shot) | setup | register devices, point occupancysim's lectures at our rooms | runs once and exits; not part of the running system |

### 3.3 The two loops

This is the L1 model made concrete:

- **Fast loop (`control`, every 5 s wall ≈ 5 sim-min):** reads observations, applies thresholds with
  hysteresis, clamps to the safety floor, commands actuators. It always runs and keeps rooms safe no
  matter what else fails. It is deliberately rule-based: verifiable, explainable in an oral exam, and
  fast enough that latency is never the reason a room goes over the limit.
- **Slow loop (`planner`, every 10 s wall):** forecasts occupancy 30 sim-min ahead, rolls the CO₂ mass
  balance forward for each ventilation level, and publishes the smallest level that keeps the forecast
  peak under the limit. **A plan may raise ventilation or the setpoint; it can never lower them.** A
  stale, missing or wrong plan therefore degrades the system to "reactive only", never to unsafe.

### 3.4 Data quality as a control input

A rule controller that trusts its inputs fails the interesting way: a CO₂ sensor frozen on 700 ppm looks
perfectly healthy and silently defeats FR-01. `control` therefore classifies every CO₂ input as
`ok | stale | frozen | missing` before using it (rolling identical-value check plus a freshness window in
simulated time) and falls back to occupancy — a second, independent signal — when it is not `ok`.
Data quality is treated as a first-class input, not as noise.

### 3.5 Design decisions

Full table with alternatives and trade-offs: [`decision-log.md`](decision-log.md).

---

## 4. Behaviour

- **Dynamic diagram** (`diagrams/dynamic.d2`): the lecture-fills scenario, numbered interactions from the
  occupancy write through forecast, decision, command, actuator travel, BuildSim state, physics read-back,
  to the next reading. This is the diagram that shows the loop actually closing.
- **State machine** (`diagrams/state.d2`): the per-room controller lifecycle
  `NO_DATA → NORMAL ⇄ DEGRADED`, with `SAFETY` reachable from both and every transition labelled with the
  condition that triggers it. Every transition in that diagram is a branch in `control/rules.py`.

---

## 5. Interfaces

See [`interfaces.md`](interfaces.md) — message schemas with units, the MQTT topic tree, the BuildSim
endpoints each container touches, and the HTTP APIs of `physics`, `pipeline`, `control`, `planner`.
Written to be precise enough that another team could rebuild the system from it.

---

## 6. Simulating the sensor values

`physics/model.py`. CO₂ is a mass balance driven by occupancy and ventilation; temperature is a heat
balance over envelope loss, body heat, heater power and ventilation loss; outdoor temperature follows an
annual plus daily cosine for Luleå. Occupancy is **not** invented — it comes from the course's
occupancysim through BuildSim, which gives us realistic arrivals, lectures, fika and lunch for free and
keeps a well-known part of the simulation out of our own code.

The property that matters: **actuator commands feed back into these equations through BuildSim**. The
physics reads actuator state from BuildSim each cycle; if that read-back were missing, the loop would
never close and the whole system would be a dashboard. Honest limitations are listed in §9.

---

## 7. Autonomous services and data engineering

**Autonomy**: `control` (rules + hysteresis + safety clamp + degraded handling) and `planner` (linear
regression forecast + physics rollout). Rule-based was chosen over a learned controller because it meets
the latency budget, is verifiable for a safety-relevant function, and can be explained from memory in the
oral exam; a learned *forecast* was added exactly where learning helps — predicting the future occupancy
that the physics cannot know. The planner is evaluated against a persistence baseline on a different
simulated day than it was trained on (`planner/train.py`), because occupancysim replays a date
deterministically and a random split would leak the test day into training.

**Pipeline**: sensors/actuators/plans/decisions/health → MQTT → `pipeline` → bronze JSONL (exactly what
arrived) → silver Parquet (typed, de-duplicated, via DuckDB) → gold (training and evaluation tables).
Each row keeps the producer's `ts` and `sim_ts` plus the pipeline's `recv_ts`, so per-hop latency is
measurable rather than asserted.

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

---

## 9. Risks, assumptions, critical reflection (to be filled with evidence)

| Risk / assumption | Impact | Mitigation / how we will report it |
|---|---|---|
| BuildSim has no persistence and no auth | single point of failure for the whole system | devices re-register on 404 (NFR-06); reported as a platform limitation, with the recovery time measured |
| Broker is a single point of failure | all fan-out stops | persistent sessions + retained state; measure what actually happens during `stop broker` |
| occupancysim is deterministic per date+seed | the forecast may look better than it is | train and evaluate on different dates/seeds; report both |
| Two clocks (wall vs. 60× simulated) | dwell times and windows silently wrong | one time authority (`common/clock.py`), every message carries both timestamps |
| ~25 Python containers on a laptop | resource limits reached before architectural ones | measure RAM/CPU and the decision-latency curve; that *is* the breaking-point experiment |
| Simplified physics (perfect mixing, no inter-room exchange) | energy and comfort figures flatter the system | always report relative to the baseline, never as absolute kWh |
