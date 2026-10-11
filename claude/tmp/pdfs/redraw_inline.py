from pathlib import Path
import re

p = Path('output/latex/D7065E-updated/main.tex')
s = p.read_text(encoding='utf-8')
# Keep the editor's document and all diagram definitions in this single source.
styles = r'''\tikzset{
  every picture/.style={font=\small},
  msg/.style={-{Latex[length=2.5mm]}, thick},
  ret/.style={-{Latex[length=2.5mm]}, thick, dashed},
  act/.style={draw, thick, fill=blue!8, minimum width=2.1cm, minimum height=0.7cm, font=\small\bfseries, align=center},
  note/.style={draw, fill=yellow!15, font=\footnotesize, align=left, inner sep=3pt},
  phase/.style={font=\footnotesize\bfseries, text=darkgray, fill=white, inner sep=1pt, anchor=west},
  lbl/.style={above, font=\footnotesize},
  service/.style={act,fill=serviceblue},
  infrastructure/.style={act,fill=infrapurple},
  device/.style={act,fill=devicegreen},
  external/.style={act,fill=gray!12},
  frame/.style={draw=gray,dashed,rounded corners=2pt,inner sep=4pt},
  check/.style={diamond,draw,thick,fill=blue!8,aspect=2,align=center,font=\small,inner sep=2pt},
  process/.style={draw,thick,fill=serviceblue,align=center,font=\small,inner sep=5pt}
}
% Inline helpers: real dimensions only; diagrams are never scaled.
\newcommand{\diagramphase}[3]{%
  \draw[gray!55,thin] (0,#1) -- (#2,#1);
  \node[phase] at (0.05,#1) {#3};}
\newcommand{\diagramlegend}{\par\smallskip{\footnotesize
  Blue: project service; purple: messaging/storage/dashboard infrastructure;
  green: device adapter; grey: course/external service.\par}}
'''
start = s.index('\\tikzset{')
end = s.index('\\pagestyle', start)
s = s[:start] + styles + s[end:]
s = s.replace('\\usepackage[hidelinks]{hyperref}', '\\usepackage[hidelinks]{hyperref}\n\\usepackage{float}')
s = s.replace('% Typeset each diagram before resizing, preserving TikZ\'s parsing context.\n\\newsavebox{\\reportdiagram}\n', '')

def figure(body, caption, label):
    return '\\begin{figure}[H]\\centering\n' + body + '\n\\caption{' + caption + '}\\label{' + label + '}\n\\end{figure}'

def replace_figure(label, content):
    global s
    pattern = r'\\begin\{figure\}.*?\\end\{figure\}'
    found = [m for m in re.finditer(pattern, s, re.S) if '\\label{' + label + '}' in m.group()]
    assert len(found) == 1, (label, len(found))
    m = found[0]
    s = s[:m.start()] + content + s[m.end():]

context = r'''\begin{tikzpicture}
\node[external,text width=3cm] (people) at (1.7,0) {Occupants};
\node[external,text width=3cm] (manager) at (12.7,0) {Building manager};
\node[external,text width=3cm] (occ) at (1.7,-3.1)
 {occupancysim\\\normalfont People, bookings, clock};
\node[service,text width=4.1cm,minimum height=2.1cm] (sys) at (7.2,-3.1)
 {Ventilation and\\climate control\\\normalfont Five rooms on level 0\\Physics, devices, control,\\planning and history};
\node[external,text width=3cm,minimum height=2.1cm] (bs) at (12.7,-3.1)
 {BuildSim\\\normalfont Shared occupancy,\\values, reached states;\\browser 3D view};
\draw[msg] (people) -- node[lbl]{presence} (occ);
\draw[ret] (occ) -- node[lbl]{clock + bookings} (sys);
\draw[ret] (bs.west) -- node[lbl]{room inputs} (sys.east);
\draw[msg] (sys.south) -- (7.2,-4.65) -- node[lbl]{values / states / view} (12.7,-4.65) -- (bs.south);
\draw[msg] (occ.south) -- (1.7,-5.4) -- node[lbl]{occupancy + entities} (14.5,-5.4) -- (14.5,-3.1) -- (bs.east);
\draw[msg] (sys.north) -- (7.2,-1.25) -- node[lbl]{history / decisions} (12.7,-1.25) -- (manager.south);
\draw[ret] (bs.east) -- (14.5,-3.1) -- (14.5,0) -- (manager.east);
\node[note,text width=13.7cm] at (7.2,-6.7)
 {\textbf{Scope and boundary.} A109/A117: lectures; A110: fika; A323/A113C: offices.\\
 No manual override. Shared lab host/network; truth separation is a code convention.\\
 The system balances CO$_2$, thermal comfort and radiator + AHU heating energy.\\
 BuildSim supplies the browser's live 3D view; the evaluation clock runs at factor 60.};
\end{tikzpicture}
\diagramlegend'''
replace_figure('fig:context', figure(context, 'System context, matching the information flows in \\texttt{context.d2}. Solid arrows are messages/writes; dashed arrows are read or browser responses. The browser response follows the outer right-hand path.', 'fig:context'))

containers_a = r'''\begin{tikzpicture}
\node[service,text width=3cm] (phy) at (1.7,0) {physics\\\normalfont Python; HTTP 8090\\CO$_2$, heat, energy};
\node[external,text width=3cm] (bs) at (7.3,0) {BuildSim\\\normalfont Go; HTTP 9090\\Occupancy, states};
\node[external,text width=3cm] (occ) at (12.9,0) {occupancysim\\\normalfont Go; HTTP 8081\\People, clock, bookings};
\node[device,text width=3cm] (sen) at (1.7,-3) {sensor-* $\times10$\\\normalfont Python; 2 s wall\\CO$_2$/temperature};
\node[device,text width=3cm] (cnt) at (12.9,-3) {occupancy\_counter\\\normalfont Python; 2 s wall\\One shared container};
\node[infrastructure,text width=3cm] (mq) at (7.3,-6) {broker\\\normalfont Mosquitto; MQTT 1883\\QoS 1; retained targets};
\node[device,text width=3cm] (act) at (1.7,-9) {actuator-* $\times10$\\\normalfont Python; vent / heat\\Validate and move};
\node[service,text width=3cm] (ctl) at (12.9,-9) {control\\\normalfont Python; HTTP 8091\\Evaluate every 5 s wall};
\draw[ret] (bs.west) -- node[lbl]{room inputs} (phy.east);
\draw[msg] (occ.west) -- node[lbl]{occupancy} (bs.east);
\draw[ret] (phy) -- node[lbl]{room truth} (sen);
\draw[ret] (bs.south east) -- node[lbl]{persons} (cnt.north west);
\draw[msg] (sen.east) -- node[lbl]{observations} (7.3,-3) -- (mq.north);
\draw[msg] (cnt.west) -- node[lbl]{head counts} (7.3,-3) -- (mq.north);
\draw[msg] (mq.east) -- node[lbl]{inputs + plans} (12.9,-6) -- (ctl.north);
\draw[msg] (ctl.west) -- node[lbl]{commands / decisions} (9,-9) -- (9,-6.5) -- (mq.south east);
\draw[msg] (mq.west) -- node[lbl]{commands} (1.7,-6) -- (act.north);
\draw[msg] (act.east) -- node[lbl]{states} (5,-9) -- (5,-6.5) -- (mq.south west);
\draw[msg] (act.west) -- (-0.2,-9) -- (-0.2,1.8) -- node[lbl]{reached states} (7.3,1.8) -- (bs.north);
\draw[msg] (sen.west) -- (0,-3) -- (0,1.05) -- node[lbl]{display values} (6.7,1.05) -- (bs.north west);
\draw[ret] (occ.north) -- (12.9,2.6) -- node[lbl]{simulated clock} (1.7,2.6) -- (phy.north);
\end{tikzpicture}
\diagramlegend'''
containers_b = r'''\begin{tikzpicture}
\node[infrastructure,text width=3cm] (mq) at (7.3,0) {broker\\\normalfont Same container as above};
\node[infrastructure,text width=3cm] (pipe) at (1.7,-3) {pipeline\\\normalfont Python/DuckDB; 8092\\JSONL / Parquet};
\node[service,text width=3cm] (plan) at (12.9,-3) {planner\\\normalfont Python/NumPy; 8093\\Every 10 s wall};
\node[service,text width=3cm] (view) at (1.7,-6) {viewer\\\normalfont Python; HTTP 8094\\Room layers + alerts};
\node[infrastructure,text width=3cm] (graf) at (7.3,-6) {grafana\\\normalfont HTTP 3000; Infinity\\Historical JSON views};
\node[external,text width=3cm] (occ) at (12.9,-6) {occupancysim\\\normalfont Same container as above};
\node[external,text width=3cm] (bs) at (7.3,-9) {BuildSim\\\normalfont Same container as above};
\node[service,text width=3cm] (seed) at (12.9,-9) {seed\\\normalfont One-shot setup\\No published port};
\draw[msg] (mq.south west) -- node[lbl]{archive events} (pipe.north east);
\draw[ret] (pipe.east) -- node[lbl]{observed history} (plan.west);
\draw[msg] (plan.north west) -- node[lbl]{retained Plan} (mq.south east);
\draw[msg] (mq.west) -- node[lbl]{live events} (-0.1,0) -- (-0.1,-6) -- (view.west);
\draw[ret] (pipe.south east) -- node[lbl]{query JSON} (graf.north west);
\draw[ret] (occ.north) -- node[lbl]{clock + bookings} (plan.south);
\draw[msg] (view.south east) -- node[lbl]{layers + alerts} (bs.north west);
\draw[msg] (seed.west) -- node[lbl]{register} (bs.east);
\draw[msg] (seed.south) -- (12.9,-10.4) -- node[lbl]{room roles} (10.6,-10.4) -- (10.6,-6) -- (occ.west);
\node[note,text width=13.6cm] at (7.3,-11.8)
 {\textbf{Compose inventory across both panels:} 10 sensors + 10 actuators + 10 shared\\
 containers = 30 continuing containers; seed is an additional one-shot container.\\
 Repeated broker, BuildSim and occupancysim boxes refer to the same instances.\\
 Sensors and actuators each run in individual containers; the counter is one shared process.};
\end{tikzpicture}
\diagramlegend'''
replace_figure('fig:containers', figure(containers_a, 'Container view, panel A: the live feedback loop. Ports are host ports. Each device group represents ten independent Compose services. Panel B completes the same container inventory.', 'fig:containers') + '\n\n' + figure(containers_b, 'Container view, panel B: planning, history, presentation and setup. All runtime edges match \\texttt{container.d2}; seed and its setup writes are explicitly added from Compose and \\texttt{scripts/seed.py}. Repeated boxes are references, not additional containers.', 'fig:containers-support'))

components = r'''\begin{tikzpicture}
\node[infrastructure,text width=3.8cm] (mq) at (7.2,0) {MQTT broker\\\normalfont Observations / plans in\\Commands / decisions out};
\node[service,text width=3.6cm] (sub) at (2.1,-2.7) {Bus callbacks\\\normalfont Decode; route by room/type};
\node[service,text width=3.6cm] (cache) at (7.2,-2.7) {Room state/cache\\\normalfont Readings, plan, prior target};
\node[service,text width=3.6cm] (quality) at (12.3,-2.7) {Quality assessment\\\normalfont Age and repeated CO$_2$};
\node[service,text width=3.6cm] (pub) at (2.1,-5.5) {Publisher + API\\\normalfont Commands on change\\Every decision with reason};
\node[service,text width=3.6cm] (clamp) at (7.2,-5.5) {Output constraints\\\normalfont Downward dwell / margin\\Final minimum clamp};
\node[service,text width=3.6cm] (rules) at (12.3,-5.5) {RoomController\\\normalfont Mode, thresholds,\\plan precedence};
\node[external,text width=7cm] (cfg) at (7.2,-8.1) {Configuration + SimClock\\\normalfont Thresholds, intervals, shared simulated time};
\draw[msg] (mq.west) -| (sub.north);
\draw[msg] (sub) -- (cache);
\draw[msg] (cache) -- (quality);
\draw[msg] (quality) -- (rules);
\draw[msg] (rules) -- (clamp);
\draw[msg] (clamp) -- (pub);
\draw[msg] (pub.west) -- (-0.15,-5.5) -- (-0.15,1.1) -| (mq.north);
\draw[msg] (cfg) -- (clamp);
\draw[msg] (cfg.east) -| (rules.south);
\begin{scope}[on background layer]
\node[frame,fit=(sub)(cache)(quality)(pub)(clamp)(rules)] {};
\end{scope}
\node[phase] at (0.2,-6.6) {control container [Python]};
\end{tikzpicture}'''
replace_figure('fig:components', figure(components, 'Components within control. Arrows carry inputs or computed outputs. Configuration and SimClock are logical inputs; general range and drift detection remain absent.', 'fig:components'))

seq1 = r'''\begin{tikzpicture}
% Participant positions: change these definitions to adjust spacing.
\def\xO{1.2}\def\xP{4.1}\def\xL{7.0}\def\xB{9.9}\def\xC{12.8}\def\ybot{-10.05}
\node[act,fill=gray!12] at (\xO,0) {occupancysim};
\node[act,fill=infrapurple] at (\xP,0) {pipeline};
\node[act,fill=serviceblue] at (\xL,0) {planner};
\node[act,fill=infrapurple] at (\xB,0) {MQTT broker};
\node[act,fill=serviceblue] at (\xC,0) {control};
\foreach \x in {\xO,\xP,\xL,\xB,\xC}
 \draw[dashed,gray] (\x,-0.4) -- (\x,\ybot);
\diagramphase{-0.85}{14.6}{Inputs (every 10 s wall)}
\draw[msg] (\xL,-1.55) -- node[lbl]{1. GET /api/state} (\xO,-1.55);
\draw[ret] (\xO,-2.25) -- node[lbl]{2. Clock + bookings} (\xL,-2.25);
\draw[msg] (\xL,-2.95) -- node[lbl]{3. GET /history} (\xP,-2.95);
\draw[ret] (\xP,-3.65) -- node[lbl]{4. Observations} (\xL,-3.65);
\diagramphase{-4.25}{14.6}{Forecast and rollout}
\node[note] at (\xL,-5.15)
 {5. Forecast $\hat n$: 5--30 sim-min\\Early student/lecturer arrivals\\Roll out CO$_2$ at $u=0,1,2,3$\\$u^*$: lowest level with peak $<900$ ppm};
\diagramphase{-6.1}{14.6}{Advice and decision}
\draw[msg] (\xL,-6.8) -- node[lbl]{6. Retained Plan} (\xB,-6.8);
\draw[msg] (\xB,-7.5) -- node[lbl]{7. Deliver plan} (\xC,-7.5);
\node[note,align=left] at (\xC,-8.5)
 {8. Every 5 s wall: mode / quality\\Reactive demand; raise to plan\\Downward dwell + final clamp};
\draw[msg] (\xC,-9.55) -- node[lbl]{9. Command + decision} (\xB,-9.55);
\end{tikzpicture}'''
replace_figure('fig:dynamic', figure(seq1, 'Booked-lecture sequence, part 1: steps 1--9 of \\texttt{dynamic.d2}. A117 is booked 10:15--12:00. History requests use \\texttt{until} and \\protect\\path{max_age_s}; observations are ordered by simulated time. Plan includes $u^*$, its predicted peak and a preheat target. Control already has live readings; only changed targets produce commands.', 'fig:dynamic'))

seq2 = r'''\begin{tikzpicture}
\def\xB{1.2}\def\xA{3.65}\def\xS{6.1}\def\xP{8.55}\def\xT{11.0}\def\xC{13.45}\def\ybot{-12.05}
\node[act,fill=infrapurple] at (\xB,0) {MQTT\\broker};
\node[act,fill=devicegreen] at (\xA,0) {vent actuator\\A117};
\node[act,fill=gray!12] at (\xS,0) {BuildSim};
\node[act,fill=serviceblue] at (\xP,0) {physics};
\node[act,fill=devicegreen] at (\xT,0) {CO$_2$ sensor\\A117};
\node[act,fill=serviceblue] at (\xC,0) {control};
\foreach \x in {\xB,\xA,\xS,\xP,\xT,\xC}
 \draw[dashed,gray] (\x,-0.4) -- (\x,\ybot);
\diagramphase{-0.9}{14.65}{Actuation}
\draw[msg] (\xB,-1.6) -- node[lbl]{10. Retained command} (\xA,-1.6);
\node[note] at (\xA,-2.55)
 {11. Validate ID / issuer / range / age\\Move at 0.5 ventilation level/s wall};
\draw[msg] (\xA,-3.5) -- node[lbl]{12. PUT reached state} (\xS,-3.5);
\diagramphase{-4.1}{14.65}{Physics}
\draw[msg] (\xP,-4.8) -- node[lbl]{13. GET room inputs} (\xS,-4.8);
\draw[ret] (\xS,-5.5) -- node[lbl]{14. States + persons} (\xP,-5.5);
\node[note] at (\xP,-6.5)
 {15. Integrate CO$_2$ and heat\\18 $^\circ$C supply; 75\% recovery\\Radiator + AHU energy};
\diagramphase{-7.45}{14.65}{Observation and feedback}
\draw[msg] (\xT,-8.15) -- node[lbl]{16. GET /rooms/A117} (\xP,-8.15);
\draw[ret] (\xP,-8.85) -- node[lbl]{17. CO$_2$ truth} (\xT,-8.85);
\node[note] at (\xT,-9.75)
 {Sensor: 30-sim-second lag,\\noise and rounding};
\draw[msg] (\xT,-10.75) -- node[lbl]{18. Observed CO$_2$} (\xB,-10.75);
\draw[msg] (\xB,-11.45) -- node[lbl]{19. Feedback to control} (\xC,-11.45);
\end{tikzpicture}'''
replace_figure('fig:dynamic-feedback', figure(seq2, 'Booked-lecture sequence, part 2: steps 10--19 of \\texttt{dynamic.d2}. Physics reads actual reached states and occupancy; later sensor observations close the loop. Step 20 archives observations, commands, states, plans and decisions concurrently through the pipeline, which is omitted here for clarity. Solid arrows are requests/messages; dashed arrows are responses.', 'fig:dynamic-feedback'))

state = r'''\begin{tikzpicture}
\node[process,text width=8cm] (start) at (7.2,0)
 {\textbf{Evaluate every 5 s wall}\\Assess CO$_2$ quality, occupancy age and plan age};
\node[check,text width=2.5cm] (trusted) at (7.2,-1.8) {CO$_2$ trusted?};
\node[check,text width=2.6cm] (high) at (3.55,-3.9) {CO$_2$ $\geq1200$?};
\node[check,text width=2.6cm] (occ) at (10.85,-3.9) {Occupancy fresh?};
\node[process,fill=red!12,text width=2.85cm,minimum height=1.9cm] (safe) at (1.75,-6.3)
 {\textbf{SAFETY}\\Request level 3\\Plan cannot reduce it};
\node[process,text width=2.85cm,minimum height=1.9cm] (normal) at (5.4,-6.3)
 {\textbf{NORMAL}\\Reactive level 0/1/2\\Higher fresh plan\\may raise it};
\node[process,fill=yellow!15,text width=2.85cm,minimum height=1.9cm] (deg) at (9.05,-6.3)
 {\textbf{DEGRADED}\\Occupied: 2; empty: 0\\Higher fresh plan\\may raise it};
\node[process,fill=red!6,text width=2.85cm,minimum height=1.9cm] (none) at (12.7,-6.3)
 {\textbf{NO\_DATA}\\Request level 2\\No plan increase\\in this branch};
\node[process,text width=12cm] (apply) at (7.2,-9)
 {\textbf{Apply ventilation constraints}\\Downward changes outside SAFETY: dwell $\geq300$ sim-s.\\Trusted CO$_2$ also needs a 100-ppm step-down margin.\\Final clamp: $\max(u_{\min},\min(3,u_{\rm request}))$; current $u_{\min}=0$.};
\node[process,text width=12cm] (heat) at (7.2,-11.5)
 {\textbf{Select heating target}\\Fresh occupied count OR NO\_DATA: 21 $^\circ$C; otherwise 17 $^\circ$C.\\A fresh higher plan may preheat when not occupied.\\Observed temperature does not select the central setpoint.};
\node[process,text width=12cm] (pub) at (7.2,-14)
 {\textbf{Publish and remember}\\Decision + reason + inputs every evaluation.\\Retained commands only when targets change.\\Ventilation or heat target changes update the shared last-change time.};
\draw[msg] (start) -- (trusted);
\draw[msg] (trusted) -- node[lbl]{yes} (high);
\draw[msg] (trusted) -- node[lbl]{no} (occ);
\draw[msg] (high) -- node[lbl]{yes} (safe);
\draw[msg] (high) -- node[lbl]{no} (normal);
\draw[msg] (occ) -- node[lbl]{yes} (deg);
\draw[msg] (occ) -- node[lbl]{no} (none);
\foreach \name in {safe,normal,deg,none}
 \draw[msg] (\name.south) -- (\name.south |- 0,-7.8) -| (apply.north);
\draw[msg] (apply) -- (heat);
\draw[msg] (heat) -- (pub);
\draw[msg] (pub.west) -- (-0.2,-14) -- (-0.2,0) -- node[lbl]{next evaluation} (start.west);
\end{tikzpicture}'''
replace_figure('fig:state', figure(state, 'Controller lifecycle, checked against \\texttt{state.d2}, \\protect\\path{control/rules.py} and the configured thresholds. Any mode may be selected at the next evaluation. Red/yellow are mode-status accents; all processing stages belong to control. Quality limits are detailed in the following paragraph.', 'fig:state'))

deployment = r'''\begin{tikzpicture}
\node[external,text width=6cm] (browser) at (7.3,0)
 {User browser\\\normalfont BuildSim 9090; Grafana 3000; service HTTP APIs};
\node[external,text width=4cm,minimum height=2.2cm] (provided) at (2.5,-3)
 {Provided $\times2$\\\normalfont BuildSim: 9090\\occupancysim: 8081};
\node[device,text width=4cm,minimum height=2.2cm] (devices) at (7.3,-3)
 {Device containers $\times20$\\\normalfont 10 sensors + 10 actuators\\One process per device};
\node[service,text width=4cm,minimum height=2.2cm] (services) at (12.1,-3)
 {Project services $\times6$\\\normalfont physics; occupancy\_counter\\control; planner\\pipeline; viewer};
\node[infrastructure,text width=4cm,minimum height=1.5cm] (broker) at (2.5,-6.3)
 {broker $\times1$\\\normalfont MQTT 1883\\Persistent sessions};
\node[infrastructure,text width=4cm,minimum height=1.5cm] (graf) at (7.3,-6.3)
 {grafana $\times1$\\\normalfont HTTP 3000\\Infinity JSON datasource};
\node[service,text width=4cm,minimum height=1.5cm] (seed) at (12.1,-6.3)
 {seed $\times1$\\\normalfont One-shot; no published port\\Equipment + room roles};
\node[note,text width=13.5cm] (network) at (7.3,-9)
 {\textbf{One Compose network on one lab host.} Service DNS; REST and MQTT.\\
 30 continuing containers + one-shot seed. No authentication/TLS boundary.\\
 Project HTTP host ports: physics 8090, control 8091, pipeline 8092,\\
 planner 8093, viewer 8094; each maps to internal port 8000.};
\node[infrastructure,text width=6cm] (data) at (7.3,-11.5)
 {Host data bind mount\\\normalfont Bronze JSONL; silver Parquet};
\draw[msg] (browser.west) -| (provided.north);
\draw[msg] (browser.east) -- (14.6,0) -- (14.6,-4.7) -- (7.3,-4.7) -- (graf.north);
% Plain membership lines show topology, not extra application messages.
\draw[gray] (provided.south) -- (2.5,-4.4) -- (14.35,-4.4) -- (14.35,-8.2) -- (network.east);
\draw[gray] (devices.south) -- (7.3,-4.4);
\draw[gray] (services.south) -- (12.1,-4.4);
\draw[gray] (broker.south) -- (2.5,-8.2) -- (network.north west);
\draw[gray] (graf.south) -- (network.north);
\draw[gray] (seed.south) -- (12.1,-8.2) -- (network.north east);
\draw[msg] (services.east) -- (14.6,-3) -- (14.6,-11.5) -- node[lbl]{pipeline writes} (data.east);
\begin{scope}[on background layer]
\node[frame,fit=(provided)(devices)(services)(broker)(graf)(seed)(network)(data)] {};
\end{scope}
\end{tikzpicture}'''
replace_figure('fig:deployment', figure(deployment, 'Single-host deployment. Grey lines indicate network membership; arrows show browser requests and pipeline storage writes. The six-service group includes the device-adapter counter and storage pipeline; their individual types appear in the container view. Counts exclude the browser and host storage.', 'fig:deployment'))

# All figures stay where they are discussed; no float-driven jumps.
s = re.sub(r'\\begin\{figure\}\[[^]]*\]', r'\\begin{figure}[H]', s)
# PGFPlots is already drawn at native dimensions; bring its typography into line.
s = s.replace('\\begin{axis}[ybar,width=.86\\linewidth,height=5.4cm,', '\\begin{axis}[ybar,width=.86\\linewidth,height=5.4cm,\n font=\\small,label style={font=\\small},tick label style={font=\\footnotesize},title style={font=\\small},')
# Update only prose tied directly to the changed representations / repository conflicts.
s = s.replace('Figure~\\ref{fig:containers} incorporates', 'Figures~\\ref{fig:containers} and~\\ref{fig:containers-support} incorporate')
s = s.replace('The one-shot seed process is omitted from this runtime view.', 'The one-shot seed is shown separately from continuing runtime flows in the setup panel. It registers equipment and configures room roles; it is not a continuing container.')
s = s.replace('registers equipment, role overrides and presentation configuration.', 'registers equipment and configures room-role overrides.')
s = s.replace('Arrows show information flow; REST reads flow from the responding provider to the consuming service.', 'Arrows show information flow; dashed REST/browser responses flow from the responding provider to the consumer, while solid arrows show messages or writes.')
s = s.replace('Steps 10--20', 'Steps 10--19')
# Explain short labels without losing the D2 contract details.
needle = 'Other services also use the shared SimClock client.'
detail = r'''The short labels retain the following contracts from \texttt{container.d2}: room inputs are occupancy plus reached actuator states; observations are CO$_2$/temperature and head counts; actuator state reports carry state, target, motion and fault. Control publishes changed-target commands and decisions/reasons. Pipeline archives \protect\path{bldg/#} and \protect\path{sys/health/#}; history requests use \texttt{until} and \protect\path{max_age_s}. Viewer replaces full room-layer/alert arrays. Sensors use lag, noise and fault effects; physics uses 18 $^\circ$C supply, 75\% heat recovery and HTTP radiator/AHU counters. Pipeline compacts every 300 s wall; planner selects the lowest level with predicted peak below 900 ppm across 30 sim-min. Grafana 12.3.0 uses Infinity 4.1.1.

'''
s = s.replace(needle, detail + needle)
assert all(x not in s for x in ['\\resizebox', '\\begin{lrbox}', '\\usebox', '\\scriptsize', '\\tiny'])
assert len(re.findall(r'\\begin\{tikzpicture\}',s)) == 9
p.write_text(s, encoding='utf-8')
print('Updated inline diagrams:', p.resolve())
