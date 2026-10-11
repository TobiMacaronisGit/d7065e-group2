from pathlib import Path
import json
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/diagrams/D7065E-redrawn'
OUT.mkdir(parents=True, exist_ok=True)

STYLE = '''classes: {
  service: {style: {fill: "#DBEAFE"; stroke: "#333333"; stroke-width: 2; font-size: 18}}
  infrastructure: {style: {fill: "#EDE9FE"; stroke: "#333333"; stroke-width: 2; font-size: 18}}
  device: {style: {fill: "#DCFCE7"; stroke: "#333333"; stroke-width: 2; font-size: 18}}
  external: {style: {fill: "#F0F0F0"; stroke: "#333333"; stroke-width: 2; font-size: 18}}
  note: {style: {fill: "#FFFFD9"; stroke: "#777777"; stroke-width: 1; font-size: 16}}
  phase: {style: {fill: "#FFFFFF"; stroke: "#BBBBBB"; stroke-width: 1; font-size: 16; bold: true}}
  msg: {style: {stroke: "#333333"; stroke-width: 2; font-size: 16}}
  ret: {style: {stroke: "#333333"; stroke-width: 2; stroke-dash: 5; font-size: 16}}
  check: {shape: diamond; style: {fill: "#EBEBFF"; stroke: "#333333"; stroke-width: 2; font-size: 18}}
}
'''

def q(s):
    return json.dumps(s, ensure_ascii=False)

def node(key, label, cls='service', extra=''):
    return f'{key}: {q(label)} {{\n  class: {cls}\n' + (f'  {extra}\n' if extra else '') + '}\n'

def edge(a, b, label='', cls='msg'):
    assert len(label) <= 25 and '\n' not in label, label
    return f'{a} -> {b}' + (f': {q(label)}' if label else '') + f' {{class: {cls}}}\n'

def phase(key, label, body):
    return f'{key}: {q(label)} {{\n  class: phase\n' + '\n'.join('  ' + line for line in body.rstrip().splitlines()) + '\n}\n'

def save(name, body, notes=''):
    head = f'''# D7065E Group 2 - counterpart to the redrawn report, 11 October 2026.
# Checked implementation: 66e0805. Original docs/diagrams sources are preserved.
# Render: d2 --theme 0 --pad 30 {name}.d2 {name}.svg
# Colours: blue project; purple infrastructure; green device; grey course/external.
'''
    (OUT / f'{name}.d2').write_text(head + notes + STYLE + '\n' + body, encoding='utf-8')

context = 'direction: down\n\n'
context += node('occupant', 'Occupants', 'external')
context += node('manager', 'Building manager', 'external')
context += node('occupancysim', 'occupancysim\nPeople, bookings, clock', 'external')
context += node('sys', 'Ventilation and climate control\nFive rooms on level 0\nPhysics, devices, control,\nplanning and history')
context += node('buildsim', 'BuildSim\nOccupancy, values, reached states\nBrowser 3D view', 'external')
for a,b,label,cls in [
    ('occupant','occupancysim','presence','msg'),
    ('occupancysim','buildsim','occupancy + entities','msg'),
    ('occupancysim','sys','clock + bookings','ret'),
    ('buildsim','sys','room inputs','ret'),
    ('sys','buildsim','values / states / view','msg'),
    ('sys','manager','history / decisions','msg'),
    ('buildsim','manager','3D view','ret')]:
    context += edge(a,b,label,cls)
context += node('scope', 'Scope and boundary\nA109/A117: lectures; A110: fika; A323/A113C: offices.\nNo manual override. Shared lab host/network.\nTruth separation is a code convention.\nBalance CO₂, thermal comfort and radiator + AHU energy.\nManager also sees health; BuildSim shows conditions and alerts.\nClock factor: 60 sim-seconds per wall-second.', 'note')
context += node('contracts', 'Short-label contracts\nRoom inputs: occupancy and reached actuator states.\nWrites: sensor values, reached states, room layers and alerts.\nDashed arrows: read/browser responses; solid: messages/writes.', 'note')
save('context', context)

container = 'direction: down\n\n'
container += node('buildsim', 'BuildSim\nGo; HTTP 9090\nOccupancy, values, reached states\nBrowser 3D view', 'external')
container += node('occupancysim', 'occupancysim\nGo; HTTP 8081\nPeople, clock, bookings', 'external')
container += '''sys: "Ventilation and climate control" {
  style: {fill: "#FFFFFF"; stroke: "#999999"; stroke-dash: 4}
  truth: "Simulation: sampled through devices" {
    style: {fill: "#FFFFFF"; stroke: "#999999"; stroke-dash: 4}
'''
container += node('physics', 'physics\nPython; HTTP 8090\nCO₂, heat, radiator + AHU energy')
container += '}\ndevice: "Device adapters" {\n  style: {fill: "#FFFFFF"; stroke: "#999999"; stroke-dash: 4}\n'
container += node('sensor', 'sensor-* ×10\nCO₂ + temperature\nOne container per sensor\nSample every 2 s wall', 'device')
container += node('occ', 'occupancy_counter\nOne shared container\nCount persons every 2 s wall', 'device')
container += node('actuator', 'actuator-* ×10\nVentilation + heating\nOne container per actuator\nValidate and rate-limit motion', 'device')
container += '}\n'
container += node('broker', 'broker\nMosquitto; MQTT 1883\nQoS 1; retained targets,\nstates, plans and health', 'infrastructure')
container += node('control', 'control\nPython; HTTP 8091\nEvaluate every 5 s wall\nRules, quality and higher advice')
container += node('planner', 'planner\nPython/NumPy; HTTP 8093\nEvery 10 s wall\nForecast, roll out and advise')
container += node('pipeline', 'pipeline\nPython/DuckDB; HTTP 8092\nBronze JSONL / silver Parquet\nObserved history + query API', 'infrastructure')
container += node('viewer', 'viewer\nPython; HTTP 8094\nRoom layers + alerts')
container += node('grafana', 'grafana\nHTTP 3000\nInfinity; historical JSON', 'infrastructure')
container += node('seed', 'seed\nOne-shot equipment + room roles\nNo published port')
container += '}\n'
runtime = [
    ('buildsim','sys.truth.physics','room inputs','ret'),
    ('sys.truth.physics','sys.device.sensor','room truth','ret'),
    ('sys.device.sensor','sys.broker','observations','msg'),
    ('buildsim','sys.device.occ','persons','ret'),
    ('sys.device.occ','sys.broker','head counts','msg'),
    ('sys.broker','sys.control','inputs + plans','msg'),
    ('sys.control','sys.broker','cmd / decision','msg'),
    ('sys.broker','sys.device.actuator','commands','msg'),
    ('sys.device.actuator','buildsim','reached states','msg'),
    ('sys.device.actuator','sys.broker','state + fault','msg'),
    ('sys.device.sensor','buildsim','display values','msg'),
    ('sys.broker','sys.pipeline','archive events','msg'),
    ('sys.pipeline','sys.planner','observed history','ret'),
    ('occupancysim','sys.planner','clock + bookings','ret'),
    ('sys.planner','sys.broker','retained Plan','msg'),
    ('sys.broker','sys.viewer','live events','msg'),
    ('sys.viewer','buildsim','layers + alerts','msg'),
    ('sys.pipeline','sys.grafana','query JSON','ret'),
    ('occupancysim','buildsim','occupancy + entities','msg'),
    ('occupancysim','sys.truth.physics','simulated clock','ret')]
container += '# All 20 original runtime edges, with short labels.\n'
for a,b,label,cls in runtime:
    container += edge(a,b,label,cls)
container += '# Additional one-shot setup from Compose and scripts/seed.py.\n'
container += edge('sys.seed','buildsim','register')
container += edge('sys.seed','occupancysim','room roles')
container += node('inventory', 'Compose inventory: 30 continuing containers + one-shot seed\n10 sensors + 10 actuators + 10 shared services.\nShared: broker, grafana, BuildSim, occupancysim, physics,\noccupancy_counter, control, planner, pipeline and viewer.\nProject HTTP host ports 8090-8094 map to internal port 8000.\nDevice services and seed publish no host ports.', 'note')
container += node('planning', 'Planning and history\nSix occupancy horizons: 5, 10, 15, 20, 25, 30 sim-min.\nBookings unavailable/absent: persistence in deployed setup.\nChoose lowest level with predicted peak <900 ppm.\nIf none qualifies, return maximum level 3.\nPlan also includes predicted peak and heating target.\nHistory uses until + max_age_s, ordered by simulated time.\nPipeline archives bldg/# and sys/health/#; compacts every 300 s wall.', 'note')
container += node('boundaries', 'Contracts and operational boundaries\nRoom inputs: occupancy and reached states.\nActuator reports: state, target, motion and fault.\nSensors add lag, noise and faults; writes also update BuildSim.\nViewer replaces complete room-layer/alert arrays.\nPhysics: 18 °C supply, 75% recovery, radiator + AHU counters.\nCounters are HTTP truth fields, not automatically archived MQTT.\nGrafana 12.3.0 + Infinity 4.1.1.\nReactive control continues if history/planning fails; plans expire.\nOther services also use SimClock; truth separation is by code convention.\nLoaded-model fallback remains in code, but the rejected model is not deployed.', 'note')
save('container', container)

ACTORS = {
    'occupancysim': ('occupancysim','external'),
    'pipeline': ('pipeline','infrastructure'),
    'planner': ('planner','service'),
    'broker': ('MQTT broker','infrastructure'),
    'control': ('control','service'),
    'actuator': ('vent actuator\nA117','device'),
    'buildsim': ('BuildSim','external'),
    'physics': ('physics','service'),
    'sensor': ('CO₂ sensor\nA117','device')}

inputs = edge('planner','occupancysim','1. GET /api/state')
inputs += edge('occupancysim','planner','2. Clock + bookings','ret')
inputs += edge('planner','pipeline','3. GET /history')
inputs += edge('pipeline','planner','4. Observations','ret')
forecast = node('planner.step5', '5. Forecast n̂: h=5...30 min\nEarly student/lecturer arrivals\nRoll out CO₂ for u=0...3\nu*: lowest level with peak <900 ppm\nIf none qualifies: use level 3', 'note')
advice = edge('planner','broker','6. Retained Plan')
advice += edge('broker','control','7. Deliver plan')
advice += node('control.step8', '8. Every 5 s wall\nQuality + mode\nReactive demand\nRaise to plan\nDwell + final clamp', 'note')
advice += edge('control','broker','9. Command + decision')
actuation = edge('broker','actuator','10. Deliver command')
actuation += node('actuator.step11', '11. Validate ID / issuer\nNumeric range / wall age\nMove at 0.5 level/s wall', 'note')
actuation += edge('actuator','buildsim','12. PUT reached state')
physics = edge('physics','buildsim','13. GET room inputs')
physics += edge('buildsim','physics','14. States + persons','ret')
physics += node('physics.step15', '15. Integrate CO₂ and heat\n18 °C supply; 75% recovery\nRadiator + AHU energy', 'note')
observation = edge('sensor','physics','16. GET /rooms/A117')
observation += edge('physics','sensor','17. CO₂ truth','ret')
observation += node('sensor.effects', 'Sensor: 30-sim-second lag,\nnoise and rounding', 'note')
observation += edge('sensor','broker','18. Observed CO₂')
observation += edge('broker','control','19. Feedback to control')
archive = edge('broker','pipeline','20. Archive events')
archive += node('pipeline.concurrent', 'Concurrent throughout the sequence:\nobservations, commands, reached states,\nplans and decisions are archived.', 'note')

seqnotes = '''# Illustrative source order and original step numbers are preserved.
# Actual planner code fetches history before consulting cached bookings (15 s wall TTL).
# SimClock polls separately; the 10-s phase label denotes the planning loop.
# A117 is booked 10:15-12:00. History uses until + max_age_s and simulated-time ordering.
# Plan includes u*, peak at u*, and preheat target. Control already has live readings.
# Commands require changed targets; decisions are published every evaluation.
# Actuation uses QoS 1 and retention. Heating follows the same actuation/read-back path.
# occupancy_counter independently publishes observed head counts.
# Step 20 archives concurrently, not as a final batch. It is caption text in report part 2.
# Reactive control continues if history or timetable requests fail.
'''

def sequence(names, groups):
    body = 'shape: sequence_diagram\n\n'
    for name in names:
        label, cls = ACTORS[name]
        body += node(name, label, cls)
    body += '\n'
    for key, label, content in groups:
        body += phase(key, label, content)
    return body

part1groups = [('inputs','Inputs (every 10 s wall)',inputs),
               ('forecast','Forecast and rollout',forecast),
               ('advice','Advice and decision',advice)]
part2groups = [('actuation','Actuation',actuation),
               ('physics_phase','Physics',physics),
               ('observation','Observation and feedback',observation)]
save('dynamic-part1', sequence(['occupancysim','pipeline','planner','broker','control'], part1groups), seqnotes)
save('dynamic-part2', sequence(['broker','actuator','buildsim','physics','sensor','control'], part2groups), seqnotes)
save('dynamic', sequence(list(ACTORS), part1groups + part2groups + [('archive','Concurrent archiving (throughout)',archive)]), seqnotes)

state = 'direction: down\n\n'
state += node('evaluate', 'Evaluate every 5 s wall\nAssess CO₂ quality, occupancy age and plan age')
state += node('trusted', 'CO₂ trusted?', 'check')
state += node('high', 'CO₂ ≥1200 ppm?', 'check')
state += node('occ', 'Occupancy fresh?', 'check')
state += node('SAFETY', 'SAFETY\nRequest level 3\nPlan cannot reduce it', extra='style.fill: "#FFE0E0"')
state += node('NORMAL', 'NORMAL\nLevel 0: CO₂ <800 ppm\nLevel 1: 800 ≤CO₂ <1000 ppm\nLevel 2: 1000 ≤CO₂ <1200 ppm\nA higher fresh plan may raise it')
state += node('DEGRADED', 'DEGRADED\nCO₂ missing, stale or frozen\nFresh occupancy: occupied 2; empty 0\nA higher fresh plan may raise it', extra='style.fill: "#FFFFD9"')
state += node('NO_DATA', 'NO_DATA\nNeither trusted CO₂ nor fresh occupancy\nRequest level 2\nNo plan increase for ventilation', extra='style.fill: "#FFF0F0"')
state += node('constrain', 'Apply ventilation constraints\nDownward changes outside SAFETY: dwell ≥300 sim-s.\nTrusted CO₂ also requires a strict 100-ppm step-down margin.\nClamp: max(vent_min_level, min(vent_max, request)).\nConfigured minimum 0; maximum 3.')
state += node('heat', 'Select heating target\nFresh occupied count OR NO_DATA: 21 °C; otherwise 17 °C.\nA fresh higher plan may preheat when not occupied.\nThis also applies in NO_DATA; its ventilation ignores plans.\nObserved temperature does not select the central setpoint.')
state += node('publish', 'Publish and remember\nDecision + reason + inputs every evaluation.\nRetained commands only when targets change.\nVentilation or heat changes update shared last-change time.')
for a,b,label in [('evaluate','trusted',''),('trusted','high','yes'),('trusted','occ','no'),
                  ('high','SAFETY','yes'),('high','NORMAL','no'),('occ','DEGRADED','yes'),('occ','NO_DATA','no'),
                  ('SAFETY','constrain',''),('NORMAL','constrain',''),('DEGRADED','constrain',''),('NO_DATA','constrain',''),
                  ('constrain','heat',''),('heat','publish',''),('publish','evaluate','next evaluation')]:
    state += edge(a,b,label)
state += node('quality', 'Trusted-data limits\nCO₂ exists, simulated age ≤300 s, and last 8 publications are not identical.\nOccupancy uses the same age limit.\nPlan age ≤twice its horizon (normally 60 sim-min).\nNo general range/drift check or future-timestamp rejection.\nAt factor 60, eight 2-s-wall samples span at least 14 sim-min;\nthe 10-sim-minute frozen-detection target is not guaranteed.', 'note')
save('state', state, '# Any prior mode may select any new mode on the next evaluation.\n# Executable control/rules.py takes precedence over its narrower introductory docstring.\n')
print('Created:', ', '.join(p.name for p in sorted(OUT.glob('*.d2'))))
