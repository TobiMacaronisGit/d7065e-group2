# D7065E — Course criteria checklist (final report, demo, oral exam)

One place for every requirement the course states, with our current status.
Status column = check of `docs/final_report.pdf` (31 pages, built 11 Oct 2026 16:24, "66e0805").

**Sources** (read 11 Oct 2026): Canvas pages *Grading*, *Introduction*, *Architecture document and final report*,
*Final Report Submission* (assignment), *Oral examination*, *AI usage*, announcements; course PDFs
`report_guide.pdf`, `final_report_template.pdf`, `final_report_example.pdf`; our `Project-ProposalFINAL.pdf`.
Lecturer: Johan Kristiansson. A Canvas page always wins over this file.

Legend: ✅ met · ⚠️ partly met / weak spot · ❌ missing · — not required for target grade

---

## 0. Submission logistics (Canvas assignment "Final Report Submission")

| Item | Requirement | Status / action |
|---|---|---|
| Deadline | **Mon 12 Oct 2026, 23:59** (the 5 Oct "today is the deadline" announcement was withdrawn by Johan: "my mistake, just ignore") | — |
| Format | PDF, one submission per team | ✅ |
| File name | `TeamName_FinalReport.pdf` | ❌ rename, e.g. `Group2_FinalReport.pdf` (use the exact Canvas group name) |
| Repository link | link to the project repository inside the report | ✅ in summary table |
| Based on | Report Guide + Report Template + Example | ✅ section structure follows the template |
| Repo matches report | "The document matches what was actually built" (template checklist) | ⚠️ report cites `origin/tobias` plots "not merged into main"; `report/main.tex` in the repo is an **older** version than the PDF → merge `tobias` into `main`, commit the final `.tex` + PDF, cite one commit |

## 1. Stage 1 — Pass/Fail (any missing ⇒ **U** until fixed)

| # | Requirement (Grading page) | Where in report | Status |
|---|---|---|---|
| P1 | Sensors, actuators, decision-making run as separate, independently deployable/restartable processes; no monolith | §4.2, §9 (30 containers) | ✅ |
| P2 | End-to-end loop: sensor → transport → autonomous decision → actuator → visible effect in BuildSim → next sensor reading | §8.1, E2E-1 (`results/e2e.txt`, 1 passed) | ✅ |
| P3 | ≥ 1 component makes genuine, justified autonomous decisions from sensor data | §7.1 control + planner | ✅ |
| P4 | Data pipeline collects, stores, makes data available to other components | §7.2 (JSONL/Parquet/DuckDB, `/history`, Grafana) | ✅ |
| P5 | Architecture document with C4 Context, C4 Container, requirements table, key interfaces & communication paths | §3, §4.1, §4.2, §5 | ✅ |
| P6 | Test plan **provided and executed**, incl. **unit tests**, ≥ 1 E2E integration test, **documented results** | §10 | ❌ **unit-test results are not documented**; the report even says "their presence alone is not a passing result". Fix: run `make test`, save output to `docs/results/unit-tests.txt`, add a "U1 unit tests" row to §10 with the pass count |
| P7 | Dashboard visualising system state | §12, Fig. 10 (Grafana) | ✅ (a BuildSim 3D screenshot with our overlays would be stronger) |
| P8 | Written report documenting architecture, implementation, evaluation, key decisions | whole report | ✅ |
| P9 | Oral exam: each student draws, explains and justifies the architecture **from memory** | — | prepare (see §5) |
| P10 | **Pair projects: contribution statement** (architecture, implementation, testing, evaluation, report preparation per student) — Grading page + "Architecture document and final report" page | — | ❌ **missing** — add a short section; must be truthful |

## 2. Stage 2 — Rubric dimensions (grade = holistic; "at or near that level across most dimensions")

### A — Architecture & design
| Level | Criterion | Status |
|---|---|---|
| 3 | C4 context + container, requirements table, interface contracts | ✅ |
| 3 | Role/responsibility of each component explained | ✅ (shared `occupancy_counter` vs. one container per device not justified ⚠️) |
| 3 | Major decisions justified against ≥ 1 alternative (protocols, service boundaries, storage, deployment) | ✅ §4.4 table — but **Python vs. Go not justified** ❌ (Introduction: "Go is preferred … other languages if strongly motivated") |
| 4 | Decisions **explicitly linked to FR/NFR** (latency, reliability, fault tolerance …) | ⚠️ §4.4 has no requirement column; links are scattered in prose |
| 4 | Behavioural models (sequence/state) | ✅ §8.1 dynamic (2 parts), §8.2 state |
| 4 | Interfaces precise enough for another team to implement | ✅ §5 (topics, schemas, HTTP table, examples) |
| 5 | Architecture critically evaluated; alternatives compared with evidence; how it evolves (more buildings, scale) | ⚠️ critique strong; **evolution / scaling path barely discussed** |

### B — Systems integration & CPS loop
| Level | Criterion | Status |
|---|---|---|
| 3 | Loop closes end-to-end; independent processes; a reading can be traced through the system | ✅ |
| 4 | Service boundaries/communication justified; **behaviour under failure demonstrated and analysed**; recovery evaluated | ✅ F1 frozen sensor, F3a control restart, F3b actuator restart (bug found), F6 invalid commands |
| 5 | Emergent behaviour, cascading failures, feedback effects, contention, conflicting decisions | ⚠️ partly (threshold cycle, retained-command defect, shared-broker risk); no cascade experiment |

### C — Autonomous services & data engineering
| Level | Criterion | Status |
|---|---|---|
| 3 | Autonomous decisions from sensor data; data flows through a defined pipeline; approach justified | ✅ |
| 4 | Pipeline supports storage/analysis/evaluation; decision component evaluated with metrics; compared to alternatives | ✅ E3 (reactive vs. persistence vs. timetable), E5 (linear model vs. persistence MAE) |
| 5 | Data-quality issues (missing, stale, contradictory, corrupted) handled and their impact evaluated | ⚠️ stale/frozen handled + F1 measured; drift/range not handled (honestly stated) |

### D — Critical evaluation
| Level | Criterion | Status |
|---|---|---|
| 3 | What was tested, how, results; component **and** end-to-end tests | ⚠️ component (unit) results missing — see P6 |
| 4 | Quantitative evaluation against requirements; metrics measured; fault injection connected to design decisions | ✅ R6–R8 table, MAE table, F1/F3/F6 timings |
| 5 | Stress test / breaking point, trade-offs (performance, energy, sustainability), honest critique | ❌ no E4 scaling/breaking point, no fixed-schedule energy baseline (E1); critique itself is strong |

**Reading for target grade 3–4:** after fixing P6 and P10, the report supports 3 safely and 4 plausibly
(A4 needs the requirement links + Python justification; D4 is met). Grade 5 would need E4/E1 — out of scope.

## 3. Report Guide / Template — section checklist

| § | Must contain (guide + template) | Status |
|---|---|---|
| 1 Summary | one-paragraph overview + guiding principle; table (title, team, use case, repo, version/date); **changes since proposal + why** | ✅ (state the guiding principle in one sentence) |
| 2 Use case | BuildSim role (shared state, instrumented not modified), how each process uses it, actors, demo scenario, why it matters | ✅ |
| 3 Requirements | ID, **type**, **priority**, measurable criterion, verifying test | ⚠️ type + priority columns dropped (they exist in `docs/requirements.md`) |
| 4.1 Context | system as one box, people + external systems, **purpose and protocol on every arrow** | ⚠️ protocols missing on arrows |
| 4.2 Container | every deployable unit, **protocol on every arrow**, maps 1:1 to `docker-compose.yml` | ⚠️ protocols missing on arrows; otherwise ✅ |
| 4.3 Component | optional; one complex container | ✅ control |
| 4.4 Decisions | choice, alternative(s), **requirement served**, trade-off | ⚠️ requirement column missing; Python/Go row missing |
| 5 Interfaces | pattern per link + why; schemas (fields, types, units); topics/endpoints with QoS, rate, status codes; example message | ✅ |
| 6 Physical model | physical processes + equations, actuator feedback closes the loop, occupancy model, limitations | ✅ |
| 7.1 Autonomous service | approach + latency fit, inputs, outputs, integration, evaluation, failure/safety fallback | ✅ |
| 7.2 Pipeline | ingestion (broker as buffer), storage, processing/features, data quality, retention | ✅ |
| 8 Behaviour | ≥ 1 dynamic/sequence diagram + ≥ 1 state machine (incl. network drop / recovery) | ✅ |
| 9 Deployment | deployment diagram; latency, fault isolation, resources, maintainability; why separate processes; **edge vs. external compute** | ⚠️ edge/cloud placement reduced to one sentence (LO1, typical oral question) |
| 10 Test plan | every requirement → verification + evidence; unit, E2E, fault injection, measurements | ❌ unit tests missing (P6); otherwise ✅ |
| 11 Evaluation | measured metrics, response-over-time plot, energy vs. baseline, breaking point (higher grades), honest critique | ⚠️ good tables; the time-series plots sit in an appendix instead of §11 |
| 12 Dashboard | what it shows, how it overlays BuildSim 3D view, **screenshot** | ✅ Grafana screenshot (BuildSim overlay screenshot missing) |
| 13 Risks & reflection | weaknesses, assumptions, trade-offs, next steps | ✅ strong |
| — | Delete all template guidance notes / bracket slots; all diagrams referenced in text | ✅ |
| — | Pair projects: contribution statement | ❌ (P10) |

## 4. Course constraints (Introduction page)

| Constraint | Status |
|---|---|
| Every component its own process; each sensor/actuator its own Unix process, preferably containerised | ✅ |
| Every design choice justified ("not enough to say we used MQTT") | ⚠️ Python choice unjustified |
| Data must flow through a proper architecture, not just direct REST calls (broker, storage, pipeline) | ✅ MQTT + JSONL/Parquet |
| Tested under failure conditions — happy-path demo is not sufficient | ✅ F1/F3/F6 (F2/F4/F5/F7 open) |
| Go recommended; other languages "if strongly motivated" | ❌ add justification |
| AI coding assistants allowed — but every member must understand all code | see §5 |

## 5. Oral examination (individual, ~30 min)

Format: **10 min presentation with live demo** + **20 min whiteboard, no slides or notes**.
The oral exam is a *gate*: it cannot raise the grade, but anyone who cannot explain/defend the system gets **U**.
Grade 3: draw + explain architecture from memory, role of each component, justify key decisions.
Grade 4: additionally discuss trade-offs in depth and handle follow-up questions.

Must be able to (Oral examination page):
- [ ] Draw the architecture from memory; responsibilities of every component
- [ ] How sensors, services, storage, decision components and actuators interact
- [ ] Why each communication pattern, technology and deployment choice (incl. **Python vs. Go**, MQTT vs. REST, JSONL/Parquet vs. TSDB)
- [ ] Sense → reason → act: how decisions are made, translated to actions, and **the limits of autonomy**
- [ ] Behaviour under uncertainty, missing information, wrong decisions (DEGRADED / NO_DATA / SAFETY)
- [ ] Data flow from sensing to action; storage, processing, transformation for decisions
- [ ] Testing strategy, failure effects, limitations, improvements (F1 late detection, F3b retained-command bug)

Example questions from Canvas (prepare one-minute answers):
1. What makes a system autonomous rather than automated?
2. How does your system implement a sense–reason–act loop?
3. What happens if a sensor provides incorrect information?
4. What happens if a decision-making component becomes unavailable?
5. Why was a particular communication pattern chosen?
6. How does your system balance local and cloud-based computation?
7. What are the main failure modes of your system?
8. How would your architecture change at a larger scale?

AI usage page (self-assessment, high-risk flags): can each of us explain how AI-generated code was validated,
where AI advice was wrong (examples: R2/R3 history bug, zero-comfort thermal model, linear model losing to
persistence, F3b defect), and modify/debug the code without AI?
