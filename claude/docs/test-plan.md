# Test plan

Report section 10 — the validation half of the traceability thread that starts in
[`requirements.md`](requirements.md). Every requirement has a verification approach and a concrete piece
of evidence (a log, a measurement, a plot, a screenshot).

Grading note: "we tested it and it worked" is a grade-3 statement. Level 4 needs *quantitative*
evaluation and fault injection tied back to design decisions; level 5 needs breaking points and an honest
critique. The experiments in §3 are designed for that, not for showing the happy path.

## 1. Unit tests — `pytest` (no Docker needed)

| File | Covers | Requirement |
|---|---|---|
| `physics/test_model.py` | CO₂ rises with people and falls with ventilation; ventilation costs heating energy at −15 °C; heating is gradual and bounded; outdoor temperature is seasonal | the model behind FR-01/FR-02/NFR-04 |
| `control/test_rules.py` | reactive levels, SAFETY override, hysteresis (margin **and** dwell), frozen-sensor → DEGRADED, stale CO₂ not trusted, planner may raise but never lower | FR-01, FR-03, FR-04, NFR-03, NFR-05, REG-01 |
| `actuator/test_validate.py` | issuer / range / staleness / type rejection; rate-limited travel | SAF-01 |
| `pipeline/test_storage.py` | bronze append, history window, compaction to Parquet, read-only query guard | FR-05, NFR-07 |
| `planner/test_forecast.py` | feature vector shape, persistence baseline, least-squares recovers a known linear rule, pre-ventilation before a forecast lecture | FR-04 |

## 2. Integration / end-to-end — `pytest -m e2e` against `docker compose up`

| ID | Test | Asserts |
|---|---|---|
| E2E-1 | `tests/e2e/test_loop.py` — publish a ventilation command, follow it through | actuator applies it → BuildSim shows the reached state → `physics` reads that state back → the next CO₂ readings reflect it. **This is the pass/fail "the loop closes" evidence.** |
| E2E-2 | scenario run S1 (below), asserted from the pipeline afterwards | FR-01/02/03 thresholds hold over a full simulated day |
| E2E-3 | **Stability run**: full stack (30 containers) left running, `docker inspect … RestartCount` + `docker stats --no-stream` at start and end | no container restarts or enters a restart loop. **Executed 10 Oct 2026:** ≈ 93 min (core containers since ≈ 11:51, snapshots 12:33 and 13:25), **0 restarts in all 30 containers**, total RAM ≈ 1.3 GiB; pipeline RSS grew 87 → 116 MiB (every `/query` re-reads all bronze JSONL). Raw output: [`results/stability.txt`](results/stability.txt) |

## 3. Scenario runs and experiments (the evidence for §11 of the report)

All runs: same simulated date and occupancysim seed, `OCCUPANCY_FACTOR=60`, 5 rooms. Metrics are computed
from the pipeline (`/query`), not from logs, so they are reproducible.

| ID | Experiment | Metric | Compares against |
|---|---|---|---|
| S1 | One simulated weekday, full system | % occupied sim-min in comfort band; CO₂ exceedance sim-min; heating kWh; actuator changes per room | — (baseline of the others) |
| E1 | **Energy**: full system vs. fixed-schedule baseline (vent + heat on office hours regardless of occupancy) | modelled kWh, comfort %, exceedance min | NFR-04 |
| E2 | **Hysteresis on/off** | actuator changes per 5 sim-min per room | NFR-03 |
| E3 | **Planner on/off** (reactive-only) | CO₂ exceedance sim-min, peak ppm, energy | FR-04 |
| E4 | **Scaling / breaking point**: 5 → 10 → 20 → 40 rooms (regenerate Compose), and sample interval 2 s → 0.5 s | median + p95 decision interval, MQTT backlog, container RSS/CPU, host load | NFR-01 — find where it *stops* working and say why |
| E5 | **Forecast quality**: model vs. persistence baseline, trained and tested on different simulated dates | MAE per horizon (5…30 min), from `planner/train.py` | FR-04 — an honest "no better than trivial" result is a result |

**Executed 10 Oct 2026 (live):** S1 (= run R5), E3 as three variants — off (R1), persistence (R4),
timetable (R5) — and E5. Results: [`results/e3-summary.md`](results/e3-summary.md),
[`results/e3-results.md`](results/e3-results.md), [`results/train.txt`](results/train.txt).
Runs R2/R3 are invalid (history-window bug, fixed and documented in the summary). E1, E2, E4 not executed.

## 4. Fault injection (rubric B and D)

| ID | Fault | How | Expected behaviour | Measured |
|---|---|---|---|---|
| F1 | CO₂ sensor freezes | `scripts/inject_fault.sh A109-co2 stuck` | detected ≤ 10 sim-min, room → DEGRADED, control continues from occupancy, alert in the 3D viewer | detection delay, whether FR-01 still holds (NFR-05) |
| F2 | CO₂ sensor drifts | `… A109-co2 drift` | *harder*: slow bias is not caught by the frozen check — we expect this to fail and will report it as the honest limitation | ppm of drift before behaviour degrades |
| F3 | Process crash | `docker compose kill sensor-co2-a109 / control / pipeline / actuator-vent-a109` | others keep running; on restart the loop resumes | recovery time (NFR-02), readings lost (NFR-07) |
| F4 | Broker down | `docker compose stop broker` (60 s) then start | producers buffer/reconnect, consumers resume, retained state restores actuator targets | messages lost, time to first correct command |
| F5 | BuildSim restart | `docker compose restart buildsim` | devices self-register on 404; occupancy/actuator read-back resumes without re-seeding | recovery time (NFR-06) |
| F6 | Malicious/invalid command | publish a command with `issued_by: "attacker"`, `target: 99`, or a 10-min-old `ts` | rejected by the actuator, counter increments, nothing applied | rejection count (SAF-01) |
| F7 | Clock authority down | `docker compose stop occupancysim` | clocks extrapolate, services report `clock_degraded`, physics keeps stepping | drift after 5 min, whether control still holds thresholds |
| F8 | Conflicting decisions | publish a plan suggesting vent 0 while CO₂ is 1100 ppm | reactive rules win; the plan can only raise | command actually sent |

## 5. What we expect to find (write the prediction down before running)

Recording predictions in advance is what turns a result into evidence. Current predictions:

- E4 breaks on **container resources, not on the architecture** — Python images and 25 processes will hit
  laptop RAM before `control` misses its 60 s budget. That is a consequence of D-01 and must be reported
  as such, not as "the design scales".
- F2 (drift) **defeats the current data-quality check**. The frozen-value detector cannot see a slow bias;
  cross-checking CO₂ against the physics-expected rise given occupancy would, and is the obvious next step.
- E5 may show the forecast barely beating persistence, because occupancysim's day plans are smooth. If so,
  say it plainly and keep the architecture (the planner's *interface* is the interesting part), rather than
  tuning until the number flatters us.
