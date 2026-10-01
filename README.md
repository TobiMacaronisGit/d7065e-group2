# d7065e-group2 — CO₂-driven ventilation with thermal trade-off

D7065E *Embedded Intelligence at the Edge* (LTU) · Group 2: Tobias Hanke, Evangelos Vasilaras

A distributed cyber-physical building-control system on [BuildSim](https://github.com/eislab-cps/D7065E):
five rooms on level 0 get fresh air when CO₂ demands it, as little as possible when heating is expensive,
and *before* the threshold is crossed when the planner sees a lecture coming.

**Start with [`docs/00-overview.md`](docs/00-overview.md)** — what the course requires and what we decided.
The architecture document (the report's core) lives in [`docs/architecture.md`](docs/architecture.md).

## Layout = C4 container diagram = docker-compose.yml

| Folder | Container(s) | Layer | One job |
|---|---|---|---|
| `physics/` | `physics` | truth | CO₂ + temperature ground truth per room, stepped on the simulated clock |
| `sensor/` | `sensor-co2-*`, `sensor-temp-*` (×10, generated) | device | sample truth, add lag/noise/faults, report to BuildSim + MQTT |
| `occupancy_counter/` | `occupancy_counter` | device | head count per room from BuildSim as a sensor stream |
| `actuator/` | `actuator-vent-*`, `actuator-heat-*` (×10, generated) | device | validate commands, travel at a limited rate, report reached state |
| `broker/` | `broker` (Mosquitto) | infra | pub/sub decoupling, retained last command/plan/state |
| `pipeline/` | `pipeline` | data | JSONL → Parquet (DuckDB), history + query API |
| `control/` | `control` | autonomous | reactive rules + safety clamps + degraded handling (fast loop) |
| `planner/` | `planner` | autonomous | 30-min occupancy forecast → CO₂ rollout → pre-ventilation (slow loop) |
| `viewer/` | `viewer` | presentation | single writer of BuildSim room-layers + alerts |
| `grafana/` | `grafana` | presentation | time series from the pipeline (Infinity datasource) |
| `common/` | — | — | shared client code (MQTT, BuildSim, schemas, clock) copied into every image |
| `config/` | — | — | `rooms.json`: rooms, devices, physics + control parameters (single source of truth) |
| `scripts/` | `seed` (one-shot) | — | Compose generation, BuildSim/occupancysim seeding, fault injection |
| `tests/` | — | — | end-to-end tests against the running stack |
| `docs/` | — | — | architecture document, requirements, interfaces, test plan, D2 diagrams |

## Run

```bash
cp .env.example .env                 # set COURSE_REPO to your checkout of eislab-cps/D7065E
python3 scripts/gen_compose.py       # config/rooms.json → compose.devices.yml (20 device services)
docker compose up --build            # BuildSim :9090, occupancysim :8081, Grafana :3000
```

Then open <http://127.0.0.1:9090> (3D building; *Layers* → observed CO₂ / temperature / occupancy; alerts show
degraded rooms), <http://127.0.0.1:8081> (people + simulated clock, 60×), <http://127.0.0.1:3000> (Grafana).

Service endpoints on the host (all bind 127.0.0.1): physics `:8090/rooms`, control `:8091/decisions`,
pipeline `:8092/history?room=A109&type=co2&minutes=60` and `:8092/query?sql=…`, planner `:8093/plans`, viewer `:8094/healthz`.

## Test

```bash
pip install -r requirements-dev.txt
pytest                               # unit tests: physics model, control rules, actuator validation, storage, forecast
pytest -m e2e tests/                 # end-to-end against a running stack (closes the loop through BuildSim)
scripts/inject_fault.sh A109-co2 stuck      # fault injection, see docs/test-plan.md
```

## Train the forecast

```bash
curl -X POST localhost:8092/compact                          # bronze JSONL → silver Parquet
python -m planner.train --parquet data/silver/sensor.parquet # needs ≥ 2 simulated days; prints MAE vs baseline
docker compose restart planner                              # picks up planner/model.json
```
