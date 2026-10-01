# D7065E — Project Overview: what is required, what we decided

Group 2 — Tobias Hanke, Evangelos Vasilaras · Repo: https://github.com/TobiMacaronisGit/d7065e-group2
Status: proposal approved (submitted 10 Sep). Next gate: **design approval (week 3 / KW38)**. Final submission **12 Oct**, demos 14/16/19 Oct.

Sources: Canvas *Introduction* + *Grading*, L1/L2 lecture transcripts and slides, course-notes 1–4, `lab-quickstart.md`, `report_guide` + `final_report_example`, our proposal (`Project-ProposalFINAL.pdf`).

---

## 1. What the course requires

### 1.1 Pass/Fail (all mandatory — missing one = U)

| # | Requirement | Where we satisfy it |
|---|---|---|
| P1 | Sensors, actuators and the autonomous component are **separate, independently restartable processes** (Docker), no monolith | one container per device, `control`, `planner` |
| P2 | **End-to-end loop**: sensor → transport → autonomous decision → actuator → visible effect in BuildSim → next reading reflects it | `physics` reads actuator state back from BuildSim |
| P3 | ≥1 component makes **autonomous decisions** from sensor data and drives actuators | `control` (rules) + `planner` (forecast) |
| P4 | **Data pipeline** collects, stores, and makes data available (monitoring / training / evaluation) | `broker` (MQTT) + `pipeline` (JSONL → Parquet/DuckDB + query API) |
| P5 | **Architecture document**: C4 context, C4 container, requirements table, interface documentation | `docs/architecture.md`, `docs/requirements.md`, `docs/interfaces.md`, `docs/diagrams/*.d2` |
| P6 | **Test plan** executed: unit tests, ≥1 end-to-end integration test, documented results | `*/test_*.py`, `tests/e2e/`, `docs/test-plan.md` |
| P7 | **Dashboard** visualising sensor readings, actuator states, decisions | BuildSim overlays (`viewer`) + Grafana |
| P8 | **Written report** (architecture, implementation, evaluation, design decisions) + contribution statement | LaTeX report from `final_report_template` |
| P9 | **Oral exam**: each of us draws and justifies the whole architecture from memory | both must understand every container |

### 1.2 What actually decides the grade (rubric A–D, levels 3/4/5)

The professor said it three times: *"a simple system that is well-designed, well-justified and critically evaluated scores higher than a complex one that cannot be explained."* Fancier AI ≠ higher grade.

| Dim | Level 3 | Level 4 | Level 5 |
|---|---|---|---|
| **A Architecture** | C4 L1+L2, requirements table, interface contracts, every major decision justified against ≥1 alternative | decisions linked to FR/NFR; sequence + state diagrams; interfaces precise enough for another team | assumptions/limits/trade-offs critically evaluated; how it would scale (more rooms, floors, buildings) |
| **B CPS loop** | loop closes end-to-end, a reading can be traced through the system | behaviour under crash / unavailable service / delayed or invalid data demonstrated **and** analysed; recovery explained | emergent behaviour: cascading failures, feedback effects, conflicting decisions, bottlenecks |
| **C Autonomy + data** | autonomous component fed through a pipeline, approach justified | pipeline supports storage/analysis/evaluation; decision quality measured with metrics; compared to alternatives | data-quality issues (missing, delayed, contradictory, corrupted) identified and handled; interaction of data quality and decisions evaluated |
| **D Evaluation** | what was tested, how, results | quantitative metrics (latency, recovery time, decision quality); fault injection tied back to design | stress tests / breaking points; trade-offs; honest critique with evidence |

**Justification pattern to use everywhere** (report guide §2.6): *"X was chosen because … (requirement); the alternative was Y; the trade-off accepted is Z."*

### 1.3 Report structure (from `report_guide`, mirrors the grade-5 example)

1 Summary (+ *changes since the proposal*) · 2 Use case & BuildSim context · 3 Requirements table (ID, type, priority, acceptance criterion, verified-by) · 4 Architecture: C4 context, C4 container (**must map 1:1 to `docker-compose.yml` and repo folders**), component responsibilities ("one job per process, why separate"), design-decision table · 5 Interfaces (message schemas, topics, endpoints) · 6 Physical simulation · 7 Autonomous service + data pipeline · 8 Behaviour (dynamic/sequence + state machine) · 9 Deployment · 10 Test plan · 11 Evaluation & experiments (plots, baseline comparison, breaking point) · 12 Dashboard · 13 Risks & reflection.

Diagrams: D2 (course tool, `tutorials/diagrams-as-code.md`), Mermaid acceptable. The architecture document is a **living document** — start now, keep it consistent with the code.

### 1.4 Hard technical facts about the platform (from L2 + docs)

- **BuildSim is a blackboard**: passive, no physics, no decisions, no history, no persistence (restart = empty), no auth. Every tool asks "what do I read from BuildSim, what do I write back?"
- Sensor `value` and actuator `state` are **strings**. `PUT /api/sensors/{id}/value` returns 404 until the equipment exists → seed first (`POST /api/equipment/bulk`, idempotent, only creates).
- Rooms are addressed **`<level>/<room>`** (`level0/A109`); bare names are ambiguous across floors.
- `PUT /api/occupancy`, `/api/entities`, `/api/room-layers`, `/api/alerts`, `/api/effects` each **replace the whole collection → exactly one writer per collection**. occupancysim owns occupancy + entities; we own room-layers and alerts (→ `viewer` service is the single writer).
- **occupancysim** (course tool, port 8081) generates people from a seeded day plan, publishes to BuildSim, runs at **60× wall clock** by default (`OCCUPANCY_FACTOR`), exposes its clock at `GET /api/state` (`sim.clock.time`, `factor`, `running`). Room roles come from area: office ≤ 40 m², lecture ≥ 60 m², fika ≥ 100 m² (3/floor); `room_roles` overrides per name.
- The autonomous service must **not** write to BuildSim itself; it commands an independent **actuator process** that validates, rate-limits, applies and reports (quickstart §3, tutorial).
- L2 three-layer picture: **truth layer** (physics, never observable by control) → **device layer** (sensor gateways add noise/lag/faults; actuators travel toward commands at a limited rate) → **infrastructure** (BuildSim, broker, storage, dashboard). Our proposal follows exactly this split.
- Go is "recommended" for tiny images, but the professor said explicitly in L1: *"you can use whatever language you like … Python has a lot of benefits for ML/statistics."* We still have to write the justification (Section 2.2).

---

## 2. What we decided (proposal + follow-up decisions)

### 2.1 Use case (approved)

CO₂-driven ventilation with thermal trade-off in **5 rooms on level 0**. The same actuator (fresh-air rate) lowers CO₂ and raises heating demand — a real optimisation conflict, strong in Luleå winters. A reactive rule loop always keeps rooms safe; a predictive planner (30-min forecast) ventilates *before* the threshold is crossed.

**Demo scenario** (from the proposal): one weekday fast-forwarded. Morning arrival → CO₂ rises → planner ventilates ahead → temperature drops → heating responds. 10:15 lecture fills beyond forecast → reactive loop catches it. CO₂ sensor freezes on a plausible value → room marked *degraded*, control continues on estimate. Container killed mid-demo → system degrades instead of dying.

### 2.2 Decisions taken (each with the alternative we rejected)

| Decision | Chosen | Rejected alternative | Why / trade-off |
|---|---|---|---|
| Language | **Python** for all our services | Go (course recommendation) | Team knows Python, not Go; forecast/statistics stack (numpy, duckdb) is native; ~6 weeks. Trade-off: images ~150 MB instead of ~6 MB, slower start — we measure this and report it honestly (D5). |
| Transport | **MQTT (Mosquitto)**, QoS 1, retained commands/plans | direct REST between services; Kafka | ≥4 consumers need the same readings (control, planner, pipeline, viewer); broker buffers during restarts; retained messages let a restarted actuator recover its last command. Kafka is far too heavy for a laptop. Trade-off: one more process, and delivery is at-least-once → consumers must be idempotent. |
| Storage | **`pipeline` container: JSONL (bronze) → Parquet via DuckDB (silver) + HTTP query API** | InfluxDB, TimescaleDB, Prometheus | No DB server, transparent files, replayable, exactly the pattern in course-notes 3; DuckDB reads Parquet for training. Prometheus is pull-based and not a raw store. Trade-off: no native Grafana datasource → Grafana reads via the pipeline's query API (Infinity plugin). |
| Dashboard | **BuildSim overlays** (room-layers, alerts) via one `viewer` service **+ Grafana** | own web dashboard | The viewer is provided infrastructure — we only map state into it (and say so). Grafana gives time-series with zero UI code. |
| Device granularity | **one container per device** (`sensor` image × 10, `actuator` image × 10), Compose file generated by script | one gateway per room; one process per signal type | Most realistic fault domains (one frozen CO₂ sensor, the rest keeps going); supports the fault-injection story. Trade-off: ~25 containers → generated Compose, memory footprint to measure. |
| Occupancy source | read `GET /api/occupancy` from BuildSim (published by occupancysim) via an `occupancy_counter` device | poll occupancysim directly | BuildSim stays the only shared state; occupancy is just another sensor stream. |
| Control architecture | three layers: **fast reactive rules + safety clamps** (`control`) · **planner** with forecast (`planner`) · actuator-side validation | one "smart" controller | Exactly the two-loop model from L1 (fast sense-react loop + slower planner setting its policy). Safety rules are hard clamps that no forecast can override. |
| Forecast | **linear regression on lagged features** (occupancy lags, time-of-day sin/cos) → occupancy 30 min ahead → CO₂ mass-balance rollout → suggested vent level | rolling physics rollout only; ML classifier; LLM | Physics rollout alone is circular; LR is transparent, trainable from our own Parquet in minutes, evaluable against a time-of-day baseline. |
| Simulated clock | **occupancysim's clock is the single time authority** (`/api/state`), physics steps `factor × Δt_wall`; every message carries `ts` (wall) and `sim_ts` | independent clocks | Time-sync was flagged as our biggest risk; one authority removes it. If occupancysim is unreachable, physics falls back to its own clock and flags `degraded`. |
| Rooms | A109, A117 (lecture), A110 (forced fika), A323, A113C (offices) | random | Two large lecture rooms guarantee the 10:15 spike; `config/occupancy.json` overrides all other level-0 lecture rooms so occupancysim books lectures into ours. |

### 2.3 Containers (= C4 Level 2 = `docker-compose.yml` = repo folders)

| Container | Folder | One job | Reads | Writes |
|---|---|---|---|---|
| `buildsim` | course | shared state + 3D viewer | — | — |
| `occupancysim` | course | people → BuildSim occupancy/entities | BuildSim floors | `PUT /api/occupancy`, `/api/entities` |
| `physics` | `physics/` | ground truth CO₂/temperature per room, stepped on the sim clock | BuildSim occupancy + actuator states, occupancysim clock | own REST `GET /rooms/{room}` (truth), `/metrics` |
| `sensor` ×10 | `sensor/` | sample truth, add lag/noise/faults, report | physics truth | `PUT /api/sensors/{id}/value`, MQTT `bldg/…/sensor/{type}` |
| `occupancy_counter` | `occupancy_counter/` | head count per room as a sensor | BuildSim occupancy | MQTT `bldg/…/sensor/occupancy`, BuildSim sensor |
| `actuator` ×10 | `actuator/` | validate command, travel at limited rate, report reached state | MQTT `…/cmd` | `PUT /api/actuators/{id}/state`, MQTT `…/state` |
| `broker` | `broker/` | decouple publishers from consumers | — | — |
| `pipeline` | `pipeline/` | persist everything, serve history | MQTT `bldg/#` | JSONL, Parquet, HTTP `/history`, `/query` |
| `control` | `control/` | reactive rules, safety clamps, degraded handling, decision log | MQTT sensors, plans | MQTT `…/cmd`, `…/decision` |
| `planner` | `planner/` | 30-min forecast → suggested setpoints | pipeline history | MQTT `bldg/…/plan` |
| `viewer` | `viewer/` | single writer of BuildSim overlays | MQTT decisions/sensors/health | `PUT /api/room-layers`, `/api/alerts` |
| `grafana` | `grafana/` | time-series dashboard | pipeline query API | — |

### 2.4 Requirements (draft — to be finalised in `docs/requirements.md`)

FR-01 occupied room CO₂ < 1000 ppm (back below within 10 sim-min) · FR-02 occupied rooms 20–24 °C ≥ 90 % of occupied minutes · FR-03 setback in empty rooms within 15 sim-min · FR-04 planner raises ventilation before the threshold is crossed (≥ 50 % fewer exceedance minutes than reactive-only) · NFR-01 decision ≤ 60 s wall per room · NFR-02 sensor/actuator/control crash: loop recovers within 60 s wall, no unsafe command · NFR-03 no actuator change more than once per 5 sim-min (hysteresis) · NFR-04 heating energy ≤ baseline (fixed schedule) · NFR-05 frozen sensor detected within 10 sim-min and room marked degraded · REG-01 minimum ventilation floor never violated.

### 2.5 Plan (from the proposal, sequenced)

1. **Week 3 (now):** skeleton in repo; one room end-to-end — `co2 sensor → broker → control → vent actuator → BuildSim → physics → next reading`. Architecture doc v0.1 with C4 L1/L2 for design approval.
2. All 5 rooms, temperature + heating, occupancy counter, pipeline writing JSONL/Parquet, viewer overlays.
3. Planner: collect a few simulated days, `train.py`, forecast evaluation vs baseline.
4. Fault injection (stuck/offline/drift sensor, kill containers, broker down), boundary tests (rooms ×N, sample rate), metrics collection.
5. Report, plots, oral-exam rehearsal (both draw the architecture from memory).

### 2.6 Open points / risks to watch

- **Grafana ↔ DuckDB**: Infinity plugin reading JSON from the pipeline query API is the plan; if it is fiddly, a 60-line HTML page in `viewer` is the fallback (decide by end of week 4).
- **Forecast is "too easy"** because occupancysim is deterministic per date+seed: train on different dates/seeds than we evaluate on, and say so in the report.
- **occupancysim room roles**: our `room_roles` override makes only A109/A117 lecture rooms on level 0 → verify visually that lectures land there.
- **Laptop load**: ~25 Python containers. Measure RAM/CPU early (that is itself D-evidence).
- Design-approval deliverable scope is still vague → ask at tutoring whether C4 L1/L2 + requirements table + interface list is enough.
