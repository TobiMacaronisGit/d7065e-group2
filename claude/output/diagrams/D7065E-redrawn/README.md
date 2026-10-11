# D2 counterparts of the redrawn report

Eight editable, standalone D2 files, checked against repository revision `66e0805` on 11 October 2026. Each includes its own common style classes and has an SVG and PNG preview. The existing `docs/diagrams/*.d2` files have not been edited.

| File | Content |
| --- | --- |
| `context.d2` | System context; all seven original information flows. |
| `container.d2` | Complete container view: all 20 original runtime connections plus two one-shot seed setup writes. |
| `container-part1.d2` | Closed loop and simulation support; 13 runtime connections. |
| `container-part2.d2` | Planning, history, presentation and seed; seven runtime connections plus two setup writes. |
| `dynamic.d2` | Complete sequence with original steps 1–20. |
| `dynamic-part1.d2` | Steps 1–9, five lifelines and three phases. |
| `dynamic-part2.d2` | Steps 10–19, six lifelines and three phases; no pipeline lifeline. |
| `state.d2` | Per-evaluation selection of SAFETY / NORMAL / DEGRADED / NO_DATA; all 14 original branches/stages. |

Repeated service boxes in separate panels refer to the same containers. Use the split views for a more compact presentation and the complete views to trace every connection together.

## Render

Validated and rendered with D2 0.9.0, theme 0, default Dagre layout:

```sh
d2 validate context.d2
d2 --theme 0 --pad 30 context.d2 context.svg
```

Replace `context` with any other filename. The files need no imports, downloaded icons or other assets. `validation.json` records the syntax/render checks, edge and step checks, exact Compose service inventory and published ports.

## Style and layout

Blue denotes project services, purple infrastructure, green device adapters and grey course/external actors. The state diagram additionally uses red/amber mode accents. Messages and writes use solid arrows; read/return responses use dashed arrows. Arrow labels are one line, at most 25 characters; action detail is in yellow notes or source comments. Steps 5, 8, 11 and 15 are notes centred on their lifelines.

D2 uses its own automatic layout and fonts. Its native sequence renderer draws labelled grey phase frames and puts message labels on the arrow line. These are explicit presentation differences from the report's thin horizontal separators and labels above arrows. D2 arrowheads are its standard filled triangles. The report's exact LaTeX fonts, Latex arrow tips, centimetre spacing and print-size layout remain in the TikZ source; these D2 files reproduce the diagram content and colour scheme rather than those physical coordinates. No scaling wrapper is embedded in the sources.

## Consistency changes and retained questions

- The container views state all **30 continuing containers**: ten sensors, ten actuators and ten shared services, plus the one-shot seed. The inventory and host ports match `docker-compose.yml` and `compose.devices.yml`. The seed's two setup writes were absent from the original runtime D2 view and are identified separately here.
- The planner's **level-3 fallback when no candidate stays below 900 ppm** is explicit. This is supported by `planner/forecast.py`; the original D2 description omitted it.
- The state view preserves the implementation's **800 / 1000 / 1200 ppm** thresholds, **300 sim-s** downward dwell and strict **100 ppm** step-down margin. A higher heating plan may still apply in NO_DATA even though ventilation ignores plans in that mode.
- The old provenance headers cited `20756de` and render filenames ending in `-updated`. These new copies identify the checked revision and their actual filenames.
- **Retained open question:** should a future sequence renumber/reorder steps 1–4 to follow the code's history-first, cached-bookings order? This package preserves the requested original numbering and illustrative order, with that qualification in source comments. SimClock polling is separate from the 10-second planning loop.
- `control/rules.py` selects a mode afresh on every evaluation. Its introductory transition docstring describes fewer transitions than its executable logic; the state view follows the executable logic.

## Step 20 caption for the split sequence

> Concurrent throughout steps 1–19, the MQTT broker delivers observations, commands, reached states, plans and decisions to pipeline for archiving (step 20). Archiving is not a final batch after feedback.

This explains why `dynamic-part2.d2` has no pipeline lifeline. The complete `dynamic.d2` also retains the numbered step-20 arrow and an explicit concurrency note.
