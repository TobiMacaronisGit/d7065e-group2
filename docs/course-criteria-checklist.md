# D7065E — Course criteria checklist (final report, demo, oral exam)

One place for every requirement the course states, and where our report meets it.
Status = check of the final report source `report/main.tex` on 12 Oct 2026.

**Sources** (read 11 Oct 2026): Canvas pages *Grading*, *Introduction*, *Architecture document and final report*,
*Final Report Submission* (assignment), *Oral examination*, *AI usage*, announcements; course PDFs
`report_guide.pdf`, `final_report_template.pdf`, `final_report_example.pdf`; our `Project-ProposalFINAL.pdf`.
Lecturer: Johan Kristiansson. A Canvas page always wins over this file.

Legend: ✅ met · ⚠️ partly met · ❌ not done · — not required for the target grade

---

## 0. Submission (Canvas assignment "Final Report Submission")

| Item | Requirement | Status |
|---|---|---|
| Deadline | Mon 12 Oct 2026, 23:59 | — |
| Format | One PDF per team | ✅ |
| File name | `TeamName_FinalReport.pdf` | ✅ `Group2_FinalReport.pdf` |
| Repository link | Link to the project repository in the report | ✅ Summary table |
| Basis | Report Guide, Report Template, Example | ✅ Section structure follows the template |
| Repo matches report | "The document matches what was actually built" (template checklist) | ✅ Source in `report/`, PDF in `docs/final_report.pdf` |

## 1. Stage 1 — Pass/Fail (any item missing ⇒ U)

| # | Requirement (Grading page) | Where in the report | Status |
|---|---|---|---|
| P1 | Sensors, actuators and decision-making run as separate, independently restartable processes; no monolith | §4.2, Table 2, §9 (30 containers) | ✅ |
| P2 | End-to-end loop: sensor → transport → decision → actuator → visible effect in BuildSim → next reading | §8.1, E2E-1 (`docs/results/e2e.txt`, passed) | ✅ |
| P3 | At least one component makes genuine, justified autonomous decisions from sensor data | §7.1 control + planner | ✅ |
| P4 | Data pipeline collects, stores and makes data available | §7.2 (JSONL/Parquet/DuckDB, `/history`, Grafana) | ✅ |
| P5 | Architecture document with C4 context, C4 container, requirements table, interfaces | §3, §4.1, §4.2, §5 | ✅ |
| P6 | Test plan provided and executed: unit tests, ≥ 1 end-to-end test, documented results | §10: U1 (33 unit tests passed, `docs/results/unit-tests.txt`), E2E-1, F1/F3/F6 | ✅ |
| P7 | Dashboard visualising system state | §12, Grafana screenshot; BuildSim room layers and alerts | ✅ |
| P8 | Written report: architecture, implementation, evaluation, key decisions | Whole report | ✅ |
| P9 | Oral exam: each student draws, explains and justifies the architecture from memory | — | Prepare (see §5) |
| P10 | Pair projects: contribution statement | Contribution statement | ✅ |

## 2. Stage 2 — Rubric dimensions (holistic: "at or near that level across most dimensions")

### A — Architecture & design
| Level | Criterion | Status |
|---|---|---|
| 3 | C4 context + container, requirements table, interface contracts | ✅ |
| 3 | Role and responsibility of each component | ✅ Table 2 (one job + why a separate process) |
| 3 | Major decisions justified against ≥ 1 alternative | ✅ §4.4, incl. Python vs. Go |
| 4 | Decisions linked to FR/NFR | ✅ "Serves" column in §4.4 |
| 4 | Behavioural models (sequence, state) | ✅ §8.1, §8.2 |
| 4 | Interfaces precise enough for another team to implement | ✅ §5 |
| 5 | Critical evaluation of the architecture; how it would evolve and scale | ⚠️ Critique strong; scaling path short (§9 edge/cloud) |

### B — Systems integration & CPS loop
| Level | Criterion | Status |
|---|---|---|
| 3 | Loop closes end-to-end; a reading can be traced through the system | ✅ |
| 4 | Behaviour under failure demonstrated and analysed; recovery evaluated | ✅ F1, F3a, F3b (defect found), F6 |
| 5 | Emergent behaviour, cascading failures, feedback effects | ⚠️ Partly (threshold cycle, retained-command defect, shared broker) |

### C — Autonomous services & data engineering
| Level | Criterion | Status |
|---|---|---|
| 3 | Autonomous decisions through a defined pipeline; approach justified | ✅ |
| 4 | Decision component evaluated with metrics and compared to alternatives | ✅ E3 (reactive vs. persistence vs. timetable), E5 (linear model vs. persistence) |
| 5 | Data-quality issues handled and their impact evaluated | ⚠️ Stale/frozen handled and F1 measured; drift and range not handled |

### D — Critical evaluation
| Level | Criterion | Status |
|---|---|---|
| 3 | What was tested, how, results; component and end-to-end tests | ✅ |
| 4 | Quantitative evaluation against requirements; fault injection tied to design decisions | ✅ R6–R8, MAE table, F1/F3/F6 |
| 5 | Stress test / breaking point; energy and trade-off analysis | ⚠️ E1 executed (R9: −37 % energy against a fixed schedule, with the CO₂/comfort trade-off analysed); E4 (scaling) not executed |

**Reading for the target grade:** all pass/fail items are met. The report supports grade 3 safely and grade 4
plausibly; grade 5 would mainly need E4.

## 3. Report Guide / Template — section checklist

| § | Must contain (guide + template) | Status |
|---|---|---|
| 1 Summary | Overview + guiding principle; table (title, team, use case, repo, version); changes since proposal | ✅ |
| 2 Use case | BuildSim role, how each process uses it, actors, scenario, why it matters | ✅ |
| 3 Requirements | ID, type, priority, measurable criterion, verifying test | ✅ |
| 4.1 Context | System as one box, external actors, protocol on every arrow | ✅ |
| 4.2 Container | Every deployable unit, protocol on every arrow, matches `docker-compose.yml` | ✅ |
| 4.3 Component | Optional; one complex container | ✅ control |
| 4.4 Decisions | Choice, alternative, requirement served, trade-off | ✅ |
| 5 Interfaces | Pattern per link, schemas, topics/endpoints with QoS, rate, status codes, examples | ✅ |
| 6 Physical model | Equations, actuator feedback, occupancy model, limitations | ✅ |
| 7.1 Autonomous service | Approach, inputs, outputs, evaluation, failure/safety fallback | ✅ |
| 7.2 Pipeline | Ingestion, storage, processing, data quality, retention | ✅ |
| 8 Behaviour | ≥ 1 sequence diagram + ≥ 1 state machine incl. network drop and recovery | ✅ |
| 9 Deployment | Deployment diagram; placement, fault isolation, resources; edge vs. external compute | ✅ |
| 10 Test plan | Every requirement → verification + evidence; unit, E2E, fault injection | ✅ |
| 11 Evaluation | Measured metrics, response-over-time plot, baseline comparison, honest critique | ✅ (fixed-schedule baseline R9 included) |
| 12 Dashboard | What it shows, screenshot | ✅ |
| 13 Risks & reflection | Weaknesses, assumptions, trade-offs, next steps | ✅ |
| — | Contribution statement (pair projects) | ✅ |

## 4. Course constraints (Introduction page)

| Constraint | Status |
|---|---|
| Every component its own process; each sensor/actuator its own containerised process | ✅ |
| Every design choice justified | ✅ |
| Data flows through a proper architecture (broker, storage, pipeline), not just direct REST calls | ✅ |
| Tested under failure conditions, not only the happy path | ✅ F1/F3/F6 (F2/F4/F5/F7 open) |
| Go recommended; other languages "if strongly motivated" | ✅ Python justified in §4.4 |
| AI coding assistants allowed, but every member must understand all code | See §5 |

## 5. Oral examination (individual, ~30 min)

Format: **10 min presentation with live demo** + **20 min whiteboard, no slides or notes**.
The oral exam is a gate: it cannot raise the grade, but a student who cannot explain and defend the system gets **U**.
Grade 3: draw and explain the architecture from memory, role of each component, justify key decisions.
Grade 4: additionally discuss trade-offs in depth and handle follow-up questions.

Must be able to (Oral examination page):
- [ ] Draw the architecture from memory; responsibilities of every component
- [ ] How sensors, services, storage, decision components and actuators interact
- [ ] Why each communication pattern, technology and deployment choice (incl. Python vs. Go, MQTT vs. REST, JSONL/Parquet vs. a time-series DB)
- [ ] Sense → reason → act: how decisions are made and executed, and the limits of autonomy
- [ ] Behaviour under uncertainty, missing information and wrong decisions (DEGRADED / NO_DATA / SAFETY)
- [ ] Data flow from sensing to action; storage, processing and use for decisions
- [ ] Testing strategy, failure effects, limitations, improvements (F1 late detection, F3b retained-command defect)

Example questions from Canvas:
1. What makes a system autonomous rather than automated?
2. How does your system implement a sense–reason–act loop?
3. What happens if a sensor provides incorrect information?
4. What happens if a decision-making component becomes unavailable?
5. Why was a particular communication pattern chosen?
6. How does your system balance local and cloud-based computation?
7. What are the main failure modes of your system?
8. How would your architecture change at a larger scale?

AI usage page (self-assessment): each of us should be able to explain how AI-generated code was validated and
where AI advice was wrong (examples: R2/R3 history bug, zero-comfort thermal model, linear model losing to
persistence, F3b defect), and to modify or debug the code without AI.
