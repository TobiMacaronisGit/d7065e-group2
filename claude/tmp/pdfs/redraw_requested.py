from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/latex/D7065E-redrawn'
MAIN = OUT / 'main.tex'

PREAMBLE = r'''% Shared diagram styles: native centimetres; never scale a TikZ picture.
\newdimen\diagramwidth
\newcommand{\checkdiagramwidth}{%
  \pgfextractx{\diagramwidth}{\pgfpointdiff
    {\pgfpointanchor{current bounding box}{west}}
    {\pgfpointanchor{current bounding box}{east}}}%
  \typeout{REPORT-DIAGRAM-WIDTH: \the\diagramwidth}%
  \ifdim\diagramwidth>15.5cm
    \PackageError{report-diagrams}{Diagram exceeds 15.5 cm}
      {Reduce spacing or split the diagram. Do not scale it.}%
  \fi
  \ifdim\diagramwidth>\linewidth
    \PackageError{report-diagrams}{Diagram exceeds linewidth}
      {Reduce spacing or split the diagram. Do not scale it.}%
  \fi}
\tikzset{
  every picture/.style={font=\small,execute at end picture=\checkdiagramwidth},
  msg/.style={-{Latex[length=2.5mm]}, thick},
  ret/.style={-{Latex[length=2.5mm]}, thick, dashed},
  act/.style={draw, thick, fill=blue!8, minimum width=2.1cm, minimum height=0.7cm, font=\small\bfseries, align=center},
  note/.style={draw, fill=yellow!15, font=\footnotesize, align=left, inner sep=3pt},
  phase/.style={font=\footnotesize\bfseries, text=darkgray, fill=white, inner sep=1pt, anchor=west},
  lbl/.style={above, font=\footnotesize, fill=white, inner sep=1pt},
  service/.style={act,fill=serviceblue},
  infrastructure/.style={act,fill=infrapurple},
  device/.style={act,fill=devicegreen},
  external/.style={act,fill=gray!12},
  frame/.style={draw=gray,dashed,rounded corners=2pt,inner sep=4pt},
  check/.style={diamond,draw,thick,fill=blue!8,aspect=2,align=center,font=\small,inner sep=2pt},
  process/.style={draw,thick,fill=serviceblue,align=center,font=\small,inner sep=5pt}
}
\newcommand{\diagramphase}[3]{%
  \draw[gray!55,thin] (0,#1) -- (#2,#1);
  \node[phase] at (0.05,#1) {#3};}
\newcommand{\diagramlegend}{\par\smallskip{\footnotesize
  Blue: project service; purple: messaging/storage/dashboard infrastructure;
  green: device adapter; grey: course/external service.\par}}
'''

FIGURES = {}
FIGURES['fig:context'] = r'''\begin{figure}[H]\centering
\begin{tikzpicture}
\node[external,text width=3cm] (people) at (1.8,0) {Occupants};
\node[external,text width=3cm] (manager) at (12.6,0) {Building manager};
\node[external,text width=3cm,minimum height=1.8cm] (occ) at (1.8,-3.2)
 {occupancysim\\\normalfont People, bookings, clock};
\node[service,text width=4cm,minimum height=2.2cm] (sys) at (7.2,-3.2)
 {Ventilation and\\climate control\\\normalfont Five rooms on level 0\\Physics, devices, control,\\planning and history};
\node[external,text width=3cm,minimum height=2.2cm] (bs) at (12.6,-3.2)
 {BuildSim\\\normalfont Shared occupancy,\\values, reached states;\\browser 3D view};
\draw[msg] (people.south) -- node[lbl,xshift=0.9cm]{presence} (occ.north);
\draw[ret] (occ.north east) -- (3.45,-1.6) -- node[lbl]{clock + bookings} (5.03,-1.6) -- (sys.north west);
\draw[ret] (bs.west) -- node[lbl]{room inputs} (sys.east);
\draw[msg] (sys.south east) -- (8,-4.9) -- node[lbl]{values / states / view} (11.8,-4.9) -- (bs.south west);
\draw[msg] (occ.south) -- (1.8,-5.65) -- node[lbl]{occupancy + entities} (13.4,-5.65) -- (bs.south east);
\draw[msg] (sys.north) -- (7.2,-1.1) -- node[lbl]{history / decisions} (12.6,-1.1) -- (manager.south);
\draw[ret] (bs.east) -- (14.55,-3.2) -- (14.55,0.9) -- node[lbl]{3D view} (12.6,0.9) -- (manager.north);
\node[note,text width=13.6cm] at (7.2,-6.9)
 {\textbf{Scope and boundary.} A109/A117: lectures; A110: fika; A323/A113C: offices.\\
 No manual override. Shared lab host/network; truth separation is a code convention.\\
 Balance CO$_2$, thermal comfort and radiator + AHU heating energy.\\
 Manager views include health; BuildSim supplies 3D conditions and alerts. Clock factor: 60.};
\end{tikzpicture}
\diagramlegend
\caption{System context: all seven information flows from \texttt{context.d2}. Solid arrows show messages/writes; dashed arrows show read or browser responses. Room inputs are occupancy and reached actuator states. Writes include sensor values, reached states, room layers and alerts.}\label{fig:context}
\end{figure}'''

FIGURES['fig:containers'] = r'''\begin{figure}[H]\centering
\begin{tikzpicture}
\node[service,text width=3cm] (phy) at (1.95,0) {physics\\\normalfont Python; 8090\\CO$_2$, heat, energy};
\node[external,text width=3cm] (bs) at (7.35,0) {BuildSim\\\normalfont Go; 9090\\Occupancy, states};
\node[external,text width=3cm] (occ) at (12.75,0) {occupancysim\\\normalfont Go; 8081\\People, clock,\\bookings};
\node[device,text width=3cm] (sen) at (1.95,-3.5) {sensor-* $\times10$\\\normalfont Python; 2 s wall\\CO$_2$/temperature};
\node[device,text width=3cm] (cnt) at (12.75,-3.5) {occupancy\_\\counter\\\normalfont Python; 2 s wall\\Shared container};
\node[infrastructure,text width=3cm] (mq) at (7.35,-6.5) {broker\\\normalfont Mosquitto\\MQTT 1883; QoS 1\\Retained targets};
\node[device,text width=3cm] (act) at (1.95,-9.4) {actuator-* $\times10$\\\normalfont Python; vent / heat\\Validate and move};
\node[service,text width=3cm] (ctl) at (12.75,-9.4) {control\\\normalfont Python; 8091\\Every 5 s wall};
\draw[ret] (bs.west) -- node[lbl]{room inputs} (phy.east);
\draw[msg] (occ.west) -- node[lbl]{occupancy} (bs.east);
\draw[ret] (phy.south) -- node[lbl,xshift=1cm]{room truth} (sen.north);
\draw[ret] (bs.south east) -- node[lbl]{persons} (cnt.north west);
\draw[msg] (sen.east) -- node[lbl]{observations} (6.75,-3.5) -- (mq.north west);
\draw[msg] (cnt.west) -- node[lbl]{head counts} (7.95,-3.5) -- (mq.north east);
\draw[msg] (mq.east) -- node[lbl]{inputs + plans} (12.75,-6.5) -- (ctl.north);
\draw[msg] (ctl.north west) -- (11,-8.1) -- node[lbl]{cmd / decision} (8.1,-8.1) -- (mq.south -| 8.1,0);
\draw[msg] (mq.west) -- node[lbl]{commands} (1.95,-6.5) -- (act.north);
\draw[msg] (act.east) -- (4.15,-9.4) -- (4.15,-8.1) -- node[lbl]{state + fault} (6.7,-8.1) -- (mq.south -| 6.7,0);
\draw[msg] (act.west) -- (-0.25,-9.4) -- (-0.25,2) -- node[lbl]{reached states} (7.35,2) -- (bs.north);
\draw[msg] (sen.west) -- (0.1,-3.5) -- (0.1,1.1) -- node[lbl]{display values} (6.7,1.1) -- (bs.north west);
\draw[ret] (occ.north) -- (12.75,2.9) -- node[lbl]{simulated clock} (1.95,2.9) -- (phy.north);
\end{tikzpicture}
\diagramlegend
\caption{Container view, panel A: the live feedback loop. Numbers are HTTP host ports except broker's MQTT port. Each device group represents ten independent Compose services. Panel B completes the same inventory. Short labels retain the \texttt{container.d2} contracts; state reports carry target, motion and fault.}\label{fig:containers}
\end{figure}'''

FIGURES['fig:containers-support'] = r'''\begin{figure}[H]\centering
\begin{tikzpicture}
\node[infrastructure,text width=3cm] (mq) at (7.3,0) {broker\\\normalfont Same as panel A};
\node[infrastructure,text width=3cm] (pipe) at (1.8,-3) {pipeline\\\normalfont Python / DuckDB\\HTTP 8092\\JSONL / Parquet};
\node[service,text width=3cm] (plan) at (12.8,-3) {planner\\\normalfont Python / NumPy\\HTTP 8093\\Every 10 s wall};
\node[service,text width=3cm] (view) at (1.8,-6) {viewer\\\normalfont Python; HTTP 8094\\Layers + alerts};
\node[infrastructure,text width=3cm] (graf) at (7.3,-6) {grafana\\\normalfont HTTP 3000; Infinity\\Historical JSON};
\node[external,text width=3cm] (occ) at (12.8,-6) {occupancysim\\\normalfont Same as panel A};
\node[external,text width=3cm] (bs) at (7.3,-9) {BuildSim\\\normalfont Same as panel A};
\node[service,text width=3cm] (seed) at (12.8,-9) {seed\\\normalfont One-shot setup\\No published port};
\draw[msg] (mq.south west) -- node[lbl]{archive events} (pipe.north east);
\draw[ret] (pipe.east) -- node[lbl]{observed history} (plan.west);
\draw[msg] (plan.north west) -- node[lbl]{retained Plan} (mq.south east);
\draw[msg] (mq.west) -- node[lbl]{live events} (-0.1,0) -- (-0.1,-6) -- (view.west);
\draw[ret] (pipe.south east) -- node[lbl]{query JSON} (graf.north west);
\draw[ret] (occ.north) -- node[lbl,xshift=-1.2cm]{clock + bookings} (plan.south);
\draw[msg] (view.south east) -- node[lbl]{layers + alerts} (bs.north west);
\draw[msg] (seed.west) -- node[lbl]{register} (bs.east);
\draw[msg] (seed.north) -- node[lbl,xshift=1cm]{room roles} (occ.south);
\node[note,text width=13.6cm] at (7.3,-11)
 {\textbf{Compose inventory across panels A and B:} 10 sensors + 10 actuators + 10 shared\\
 containers = 30 continuing containers, plus one-shot seed. Repeated boxes are references.\\
 Shared: broker, grafana, BuildSim, occupancysim, physics, occupancy\_counter, control,\\
 planner, pipeline and viewer. Devices each run separately; the counter is one shared process.};
\end{tikzpicture}
\diagramlegend
\caption{Container view, panel B: planning, history, presentation and setup. The two panels preserve all 20 runtime edges in \texttt{container.d2}. Seed and its two setup writes are added from Compose and \texttt{scripts/seed.py}; seed is omitted from the D2 runtime view.}\label{fig:containers-support}
\end{figure}'''

FIGURES['fig:components'] = r'''\begin{figure}[H]\centering
\begin{tikzpicture}
\node[infrastructure,text width=3.8cm] (mq) at (7.2,0) {MQTT broker\\\normalfont Observations / plans in\\Commands / decisions out};
\node[service,text width=3.6cm] (sub) at (2.1,-2.7) {Bus callbacks\\\normalfont Decode; route by room/type};
\node[service,text width=3.6cm] (cache) at (7.2,-2.7) {Room state/cache\\\normalfont Readings, plan, prior target};
\node[service,text width=3.6cm] (quality) at (12.3,-2.7) {Quality assessment\\\normalfont Age and repeated CO$_2$};
\node[service,text width=3.6cm] (pub) at (2.1,-5.5) {Publisher + API\\\normalfont Commands on change\\Every decision with reason};
\node[service,text width=3.6cm] (clamp) at (7.2,-5.5) {Output constraints\\\normalfont Downward dwell / margin\\Final minimum clamp};
\node[service,text width=3.6cm] (rules) at (12.3,-5.5) {RoomController\\\normalfont Mode, thresholds,\\plan precedence};
\node[external,text width=7cm] (cfg) at (7.2,-8.2) {Configuration + SimClock\\\normalfont Thresholds, intervals, shared simulated time};
\draw[msg] (mq.west) -| (sub.north);
\draw[msg] (sub) -- (cache);
\draw[msg] (cache) -- (quality);
\draw[msg] (quality) -- (rules);
\draw[msg] (rules) -- (clamp);
\draw[msg] (clamp) -- (pub);
\draw[msg] (pub.west) -- (-0.15,-5.5) -- (-0.15,1.1) -- node[lbl]{commands / decisions} (7.2,1.1) -- (mq.north);
\draw[msg] (cfg.north) -- (clamp.south);
\draw[msg] (cfg.east) -| (rules.south);
\begin{scope}[on background layer]
\node[frame,fit=(sub)(cache)(quality)(pub)(clamp)(rules)] {};
\end{scope}
\node[phase] at (0.2,-6.7) {control container [Python]};
\end{tikzpicture}
\caption{Components within control, checked against \protect\path{control/main.py} and \protect\path{control/rules.py}; there is no component D2 source. Boxes are logical responsibilities: quality and constraints are stages inside RoomController. Configuration and SimClock are logical inputs; general range and drift detection remain absent.}\label{fig:components}
\end{figure}'''

FIGURES['fig:dynamic'] = r'''\begin{figure}[H]\centering
\begin{tikzpicture}
% Lifeline positions are defined once for this picture (centimetres).
\def\xO{1.3}\def\xP{4.2}\def\xL{7.1}\def\xB{10}\def\xC{12.9}\def\ybot{-11.9}
\node[act,fill=gray!12] at (\xO,0) {occupancysim};
\node[act,fill=infrapurple] at (\xP,0) {pipeline};
\node[act,fill=serviceblue] at (\xL,0) {planner};
\node[act,fill=infrapurple] at (\xB,0) {MQTT broker};
\node[act,fill=serviceblue] at (\xC,0) {control};
\begin{scope}[on background layer]
\foreach \x in {\xO,\xP,\xL,\xB,\xC}
 \draw[dashed,gray] (\x,-0.4) -- (\x,\ybot);
\end{scope}
\diagramphase{-0.9}{14.8}{Inputs (every 10 s wall)}
\draw[msg] (\xL,-1.6) -- node[lbl]{1. GET /api/state} (\xO,-1.6);
\draw[ret] (\xO,-2.3) -- node[lbl]{2. Clock + bookings} (\xL,-2.3);
\draw[msg] (\xL,-3) -- node[lbl]{3. GET /history} (\xP,-3);
\draw[ret] (\xP,-3.7) -- node[lbl]{4. Observations} (\xL,-3.7);
\diagramphase{-4.3}{14.8}{Forecast and rollout}
\node[note,text width=5cm] at (\xL,-5.9)
 {5. Forecast $\hat n$: $h=5\ldots30$ min\\Early student/lecturer arrivals\\Roll out CO$_2$: $u=0\ldots3$\\$u^*$: lowest level with\\peak $<900$ ppm\\If none qualifies: use level 3};
\diagramphase{-7.5}{14.8}{Advice and decision}
\draw[msg] (\xL,-8.2) -- node[lbl]{6. Retained Plan} (\xB,-8.2);
\draw[msg] (\xB,-8.9) -- node[lbl]{7. Deliver plan} (\xC,-8.9);
\node[note,text width=3.5cm] at (\xC,-10.05)
 {8. Every 5 s wall\\Quality + mode\\Reactive demand\\Raise to plan\\Dwell + final clamp};
\draw[msg] (\xC,-11.4) -- node[lbl]{9. Command + decision} (\xB,-11.4);
\end{tikzpicture}
\caption{Booked-lecture sequence, part 1: steps 1--9 of \texttt{dynamic.d2}. A117 is booked 10:15--12:00. The order is illustrative: code fetches history before consulting cached bookings. History uses \texttt{until} and \protect\path{max_age_s}, ordered by simulated time. Plan includes $u^*$, predicted peak and preheat. Level 3 is used if no level achieves peak $<900$ ppm, as in \protect\path{planner/forecast.py}. Control has live readings; commands require changed targets.}\label{fig:dynamic}
\end{figure}'''

FIGURES['fig:dynamic-feedback'] = r'''\begin{figure}[H]\centering
\begin{tikzpicture}
% Six participants fit at native size; pipeline/step 20 is in the caption.
\def\xB{1.15}\def\xA{3.6}\def\xS{6.05}\def\xP{8.5}\def\xT{10.95}\def\xC{13.4}\def\ybot{-12.3}
\node[act,fill=infrapurple] at (\xB,0) {MQTT\\broker};
\node[act,fill=devicegreen] at (\xA,0) {vent actuator\\A117};
\node[act,fill=gray!12] at (\xS,0) {BuildSim};
\node[act,fill=serviceblue] at (\xP,0) {physics};
\node[act,fill=devicegreen] at (\xT,0) {CO$_2$ sensor\\A117};
\node[act,fill=serviceblue] at (\xC,0) {control};
\begin{scope}[on background layer]
\foreach \x in {\xB,\xA,\xS,\xP,\xT,\xC}
 \draw[dashed,gray] (\x,-0.4) -- (\x,\ybot);
\end{scope}
\diagramphase{-1}{14.6}{Actuation}
\draw[msg] (\xB,-1.7) -- node[lbl]{10. Deliver command} (\xA,-1.7);
\node[note,text width=4.5cm] at (\xA,-2.65)
 {11. Validate ID / issuer\\Numeric range / wall age\\Move at 0.5 level/s wall};
\draw[msg] (\xA,-3.8) -- node[lbl]{12. PUT reached state} (\xS,-3.8);
\diagramphase{-4.4}{14.6}{Physics}
\draw[msg] (\xP,-5.1) -- node[lbl]{13. GET room inputs} (\xS,-5.1);
\draw[ret] (\xS,-5.8) -- node[lbl]{14. States + persons} (\xP,-5.8);
\node[note,text width=4.3cm] at (\xP,-6.9)
 {15. Integrate CO$_2$ and heat\\18 $^\circ$C supply; 75\% recovery\\Radiator + AHU energy};
\diagramphase{-8}{14.6}{Observation and feedback}
\draw[msg] (\xT,-8.7) -- node[lbl]{16. GET /rooms/A117} (\xP,-8.7);
\draw[ret] (\xP,-9.4) -- node[lbl]{17. CO$_2$ truth} (\xT,-9.4);
\node[note,text width=3.8cm] at (\xT,-10.3)
 {Sensor: 30-sim-second lag,\\noise and rounding};
\draw[msg] (\xT,-11.1) -- node[lbl]{18. Observed CO$_2$} (\xB,-11.1);
\draw[msg] (\xB,-11.8) -- node[lbl]{19. Feedback to control} (\xC,-11.8);
\end{tikzpicture}
\caption{Booked-lecture sequence, part 2: steps 10--19 of \texttt{dynamic.d2}. Commands use QoS 1 and retention. Physics reads reached actuator states and occupancy; later observations close the loop. Step 20 archives observations, commands, states, plans and decisions concurrently through the pipeline, omitted here. Solid arrows are requests/messages; dashed arrows are responses.}\label{fig:dynamic-feedback}
\end{figure}'''

FIGURES['fig:state'] = r'''\begin{figure}[H]\centering
\begin{tikzpicture}
\node[process,text width=8cm] (start) at (7.2,0)
 {\textbf{Evaluate every 5 s wall}\\Assess CO$_2$ quality, occupancy age and plan age};
\node[check,text width=2.5cm] (trusted) at (7.2,-1.8) {CO$_2$ trusted?};
\node[check,text width=2.6cm] (high) at (3.55,-3.9) {CO$_2$ $\geq1200$?};
\node[check,text width=2.6cm] (occ) at (10.85,-3.9) {Occupancy fresh?};
\node[process,fill=red!12,text width=2.85cm,minimum height=2.4cm] (safe) at (1.75,-6.4)
 {\textbf{SAFETY}\\\footnotesize Request level 3\\Plan cannot reduce it};
\node[process,text width=2.85cm,minimum height=2.4cm] (normal) at (5.4,-6.4)
 {\textbf{NORMAL}\\\footnotesize Levels 0 / 1 / 2\\at 800 / 1000 ppm\\Higher fresh plan\\may raise it};
\node[process,fill=yellow!15,text width=2.85cm,minimum height=2.4cm] (deg) at (9.05,-6.4)
 {\textbf{DEGRADED}\\\footnotesize Occupied: 2; empty: 0\\Higher fresh plan\\may raise it};
\node[process,fill=red!6,text width=2.85cm,minimum height=2.4cm] (none) at (12.7,-6.4)
 {\textbf{NO\_DATA}\\\footnotesize Request level 2\\No plan increase\\for ventilation};
\node[process,text width=12cm] (apply) at (7.2,-9.3)
 {\textbf{Apply ventilation constraints}\\Downward changes outside SAFETY: dwell $\geq300$ sim-s.\\Trusted CO$_2$ also needs a 100-ppm step-down margin.\\Final clamp: $\max(u_{\min},\min(3,u_{\rm request}))$; current $u_{\min}=0$.};
\node[process,text width=12cm] (heat) at (7.2,-11.8)
 {\textbf{Select heating target}\\Fresh occupied count OR NO\_DATA: 21 $^\circ$C; otherwise 17 $^\circ$C.\\A fresh higher plan may preheat when not occupied.\\Observed temperature does not select the central setpoint.};
\node[process,text width=12cm] (pub) at (7.2,-14.3)
 {\textbf{Publish and remember}\\Decision + reason + inputs every evaluation.\\Retained commands only when targets change.\\Ventilation or heat target changes update the shared last-change time.};
\draw[msg] (start) -- (trusted);
\draw[msg] (trusted) -- node[lbl]{yes} (high);
\draw[msg] (trusted) -- node[lbl]{no} (occ);
\draw[msg] (high) -- node[lbl]{yes} (safe);
\draw[msg] (high) -- node[lbl]{no} (normal);
\draw[msg] (occ) -- node[lbl]{yes} (deg);
\draw[msg] (occ) -- node[lbl]{no} (none);
\foreach \name in {safe,normal,deg,none}
 \draw[msg] (\name.south) -- (\name.south |- apply.north);
\draw[msg] (apply) -- (heat);
\draw[msg] (heat) -- (pub);
\draw[msg] (pub.west) -- (-0.2,-14.3) -- (-0.2,0) -- node[lbl]{next evaluation} (start.west);
\end{tikzpicture}
\caption{Controller lifecycle, checked against \texttt{state.d2}, \protect\path{control/rules.py} and configuration. NORMAL requests level 0 below 800 ppm, 1 from 800 ppm, and 2 from 1000 ppm; SAFETY begins at 1200 ppm. Any mode may be selected at the next evaluation. Red/yellow indicate mode status. Quality limits follow in the text.}\label{fig:state}
\end{figure}'''

FIGURES['fig:deployment'] = r'''\begin{figure}[H]\centering
\begin{tikzpicture}
\node[external,text width=6cm] (browser) at (7.3,0)
 {User browser\\\normalfont BuildSim 9090; Grafana 3000; service HTTP APIs};
\node[external,text width=4cm,minimum height=2.2cm] (provided) at (2.5,-3)
 {Provided $\times2$\\\normalfont BuildSim: 9090\\occupancysim: 8081};
\node[device,text width=4cm,minimum height=2.2cm] (devices) at (7.3,-3)
 {Device containers $\times20$\\\normalfont 10 sensors + 10 actuators\\One process per device};
\node[act,fill=white,text width=4cm,minimum height=2.2cm] (services) at (12.1,-3)
 {Project services $\times6$\\\normalfont
 \colorbox{serviceblue}{physics; control}\\
 \colorbox{serviceblue}{planner; viewer}\\
 \colorbox{devicegreen}{occupancy\_counter}\\
 \colorbox{infrapurple}{pipeline}};
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
\draw[msg] (browser.east) -- (14.6,0) -- (14.6,-4.7) -- node[lbl]{Grafana HTTP} (7.3,-4.7) -- (graf.north);
% Plain grey lines denote membership rather than application messages.
\draw[gray] (provided.south) -- (2.5,-4.4) -- (14.35,-4.4) -- (14.35,-8.2) -- (network.east);
\draw[gray] (devices.south) -- (7.3,-4.4);
\draw[gray] (services.south) -- (12.1,-4.4);
\draw[gray] (broker.south) -- (2.5,-8.2) -- (network.north west);
\draw[gray] (graf.south) -- (network.north);
\draw[gray] (seed.south) -- (12.1,-8.2) -- (network.north east);
\draw[msg] (services.east) -- (14.85,-3) -- (14.85,-11.5) -- node[lbl]{pipeline writes} (data.east);
\coordinate (hostleft) at (0,-1.6);
\coordinate (hostright) at (15.1,-12.2);
\begin{scope}[on background layer]
\node[frame,fit=(hostleft)(hostright)] {};
\end{scope}
\node[phase] at (0.2,-1.6) {Single Docker host};
\end{tikzpicture}
\caption{Single-host deployment, checked against Compose; there is no deployment D2 source. Grey lines indicate network membership; arrows show browser requests and pipeline storage writes. Type colours remain visible inside the mixed six-service group. Counts exclude the browser and host storage.}\label{fig:deployment}
\end{figure}'''

FIGURES['fig:results'] = r'''\begin{figure}[H]\centering
\begin{tikzpicture}
\begin{axis}[ybar,width=13cm,height=5.8cm,
 font=\small,label style={font=\small},tick label style={font=\footnotesize},title style={font=\small},
 ylabel={Occupied exceedance (sim-min)},symbolic x coords={Reactive,Persistence,Timetable},
 xtick=data,ymin=0,ymax=145,bar width=22pt,nodes near coords,
 every node near coord/.append style={font=\small},
 title={Lecture rooms A109 + A117, final configuration},
 ymajorgrids=true,grid style={black!10}]
\addplot[fill=serviceblue,draw=blue!60] coordinates {(Reactive,122) (Persistence,2) (Timetable,0)};
\end{axis}\end{tikzpicture}
\caption{Existing R6--R8 exceedance results. Energy and comfort must be assessed alongside this air-quality metric.}\label{fig:results}
\end{figure}'''

if __name__ == '__main__':
    key = sys.argv[1]
    s = MAIN.read_text(encoding='utf-8')
    if key == 'preamble':
        s = s[:s.index('% Consistency audit')] + PREAMBLE + s[s.index('\\pagestyle'):]
        s = s.replace(r'\graphicspath{{C:/Users/User/d7065e-group2/claude/output/latex/D7065E-updated/}}',
                      r'\graphicspath{{./}{C:/Users/User/d7065e-group2/claude/output/latex/D7065E-redrawn/}}')
        s = s.replace('\\usepackage[hidelinks]{hyperref}\n\\usepackage{float}',
                      '\\usepackage{float}\n\\usepackage[hidelinks]{hyperref}')
    else:
        matches = list(re.finditer(r'\\begin\{figure\}.*?\\end\{figure\}', s, re.S))
        match = next(m for m in matches if '\\label{' + key + '}' in m.group())
        s = s[:match.start()] + FIGURES[key] + s[match.end():]
    MAIN.write_text(s, encoding='utf-8')
    print('Applied:', key)
