from pathlib import Path
import subprocess

root = Path.cwd()
out = root / 'output/pdf'
out.mkdir(parents=True, exist_ok=True)
s = (root / 'report/main.tex').read_text(encoding='utf-8')
s = s.replace('20756de', '66e0805').replace('report revised 10 October 2026', 'report revised 11 October 2026')
s = s.replace('\\date{\\today}', '\\date{11 October 2026}')
s = s.replace('Fault and crash scenarios remain separate verification tasks;\nthey are not established by a successful weekday run.', 'Fault and crash scenarios require separate evidence from weekday performance.')
s = s.replace('No current measured delay used; eight-sample detector analytically misses deadline at factor 60.', 'F1 recorded: first DEGRADED decision about 15 sim-min after injection; ten-minute deadline fails. F2 drift test remains outstanding.')
s = s.replace('No complete recovery/loss result used.', 'F3a: decisions resume 6 s after control restart. F3b: stale retained target prevents actuator recovery. Broker/pipeline loss checks remain outstanding.')
s = s.replace('Validation and precedence reviewed; no new fault injection.', 'F6 recorded: all three injected invalid commands rejected. Conflicting-plan precedence reviewed; F8 not newly executed.')
s = s.replace('The unexecuted rows remain a plan.', 'Unexecuted checks within these rows remain a plan.')
s = s.replace('No application test or experiment was run for this document revision.', 'No new application test or experiment was run while revising this document. Previously recorded live fault tests from 11 October are incorporated below.')
s = s.replace('These refinements improve the demonstration, while sensor-quality deadlines, recovery guarantees and model calibration remain open.', 'These refinements improve the demonstration. Newly recorded fault tests confirm late frozen-sensor detection and a failed actuator restart; pipeline scans now use bounded DuckDB buffers and serialized query execution. Recovery guarantees and model calibration remain open.')
s = s.replace('Existing stability snapshots show pipeline RSS growth; bounded retention, event IDs and incremental partitions are appropriate next steps.', 'Existing stability snapshots predate the latest limiter and show pipeline RSS growth. The new shared connection helper serializes history queries, SQL queries and compaction with a query lock; each connection uses one DuckDB thread and a 256 MB buffer-memory limit. Ingestion retains its separate append lock. This constrains concurrent scan memory but does not cap total process RSS, remove full scans or impose retention. Long queries can delay other queries and compaction. No post-change load benchmark is supplied; bounded retention, event IDs and incremental partitions remain appropriate next steps.')
marker = '\\section{Use case and building context}'
s = s.replace(marker, r'''\paragraph{Revision scope and branch provenance.}
This revision checks the fetched GitHub main branch at \texttt{66e0805}, including the pipeline limiter and recorded F1/F3/F6 tests. Additional plots and the 18--24 $^\circ$C descriptive metric come from \texttt{origin/tobias}, commit \texttt{fbb5552}, which was not merged into main at review time. These additions do not change the FR-02 acceptance band or constitute new simulation runs.

''' + marker)
marker = '\\section{Architecture}'
s = s.replace(marker, r'''\paragraph{Temperature target and guidance.}
FR-02's 20--24 $^\circ$C band is a project comfort target, not an established legal requirement. The newer branch additionally reports time within 18--24 $^\circ$C. Swedish public-health guidance HSLF-FS 2024:10 gives operative-temperature guideline values of 18 $^\circ$C minimum (20 $^\circ$C for sensitive groups) and 24 $^\circ$C maximum in autumn, winter and spring. Operative temperature includes surrounding-surface radiation; this project models air temperature only. The additional metric therefore provides context, not a regulatory-compliance finding, and does not replace FR-02.
Source: \href{https://www.folkhalsomyndigheten.se/contentassets/1c28701a4c8f49cabce85e3bb65695dc/hslf-fs-2024-10.pdf}{Folkh\"alsomyndigheten, HSLF-FS 2024:10, Tables 1--3}.

''' + marker)
marker = '\\section{Evaluation and results}'
s = s.replace(marker, r'''\subsection*{Recorded live fault tests, 11 October 2026}
\textbf{F1 -- frozen CO\textsubscript{2}.} The first injection attempt was invalid because the script was not executable. In the valid attempt, A109's sensor was frozen at simulated 08:30:05. The last NORMAL decision was at 08:40:06; the first DEGRADED decision was at 08:45:06, approximately 15 simulated minutes after injection. Ventilation stayed at level 2 using an observed count of 102 people. Fallback operated, but the ten-minute NFR-05 deadline failed.

\textbf{F3a -- controller restart.} Control was stopped at wall UTC 10:18:05 and restarted at 10:18:36. The first recorded decision arrived at 10:18:42: six seconds after restart and 37 seconds after stopping. A109's actuator held level 3 during the outage. This supports prompt decision resumption for this case; it is not a complete proof of correct commands and safe intermediate behaviour across every device.

\textbf{F3b -- actuator restart.} The first attempt accepted a retained command about 112 seconds old and did not exercise expiry. At real-time clock factor 1, the second attempt rejected a 154-second-old command. The A117 actuator stayed at level 0 while seven controller decisions continued to request level 2 without resending the unchanged target. This confirms the restart defect and fails the general NFR-02 recovery claim. No fix is recorded in the reviewed main branch.

\textbf{F6 -- invalid commands.} Three commands were rejected and logged: foreign issuer, target 99 outside the allowed range, and a timestamp 11,888 seconds old. These cases support SAF-01 validation. They do not establish authentication: a fresh valid command spoofing the literal issuer remains a risk.

Evidence: \path{docs/results/faults.txt}. F2, F4, F5 and F7 remain unexecuted in the supplied live evidence. The test plan also reports all 30 containers up for about 19 hours before fault injection; this is an observational stability note, not a controlled recovery test.

''' + marker)
marker = '\\section{Dashboard}'
s = s.replace(marker, r'''\paragraph{Additional temperature metric from the newer branch.}
For the same final R6/R7/R8 lecture-room runs, occupied time with observed air temperature in 18--24 $^\circ$C is 95.6\%, 93.3\% and 99.3\%, respectively. In R8 the per-room shares are A109 100.0\%, A117 99.1\%, A110 87.6\%, and A113C 99.6\%; A323 has no occupied minutes. These are reanalysed existing runs. FR-02 still fails against its original 20--24 $^\circ$C target, and air temperature cannot establish operative-temperature compliance.

\paragraph{Shared-model optimism.}
The planner rollout calls the simulation's own physics step with the same parameters and outdoor-temperature formula. Consequently the evaluation has no model--plant mismatch. Exact occupancy counts and complete registered attendance also favour forecasting and occupancy-based fallback. Results are optimistic simulator evidence, not demonstrated real-building performance or a quantified upper bound.

''' + marker)
s = s.replace('An actuator restart can reject an old retained command,', 'The recorded F3b restart rejected an old retained command,')
marker = '\\section*{Evidence and submission status}'
if marker not in s:
    marker = '\\section*{Evidence and submission status}'
# Add source plots before the final evidence statement, keeping each image readable.
figs = [('s1_A109.png', 'Recorded A109 weekday conditions and control.'), ('s1_A117.png', 'Recorded A117 weekday conditions and control.'), ('e3_planner_A117.png', 'Recorded A117 planner comparison.'), ('f1_frozen_sensor.png', 'Recorded frozen-sensor test and controller fallback.')]
block = '\\clearpage\n\\section*{Additional recorded evidence figures}\nFigures below are checked-in plots from commit \\texttt{fbb5552}; they are not new experiments.\n'
for name, caption in figs:
    data = subprocess.check_output(['git','show',f'origin/tobias:claude/docs/figures/{name}'])
    (out / name).write_bytes(data)
    block += '\\begin{figure}[p]\\centering\n\\includegraphics[width=\\linewidth,height=0.78\\textheight,keepaspectratio]{' + name + '}\n\\caption{' + caption + '}\\end{figure}\n'
block += '\\clearpage\n'
s = s.replace('\\end{document}', block + '\\end{document}')
(out / 'D7065E-revised.tex').write_text(s, encoding='utf-8')
print(out / 'D7065E-revised.tex')
