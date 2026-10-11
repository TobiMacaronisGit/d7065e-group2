from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/latex/D7065E-redrawn'
src = Path(r'C:\Users\User\Downloads\main (8).tex').read_text(encoding='utf-8')
tex = (OUT / 'main.tex').read_text(encoding='utf-8')
figures = re.findall(r'\\begin\{figure\}.*?\\end\{figure\}', tex, re.S)
tikz = [f for f in figures if '\\begin{tikzpicture}' in f]

# Verify the user's protected running text verbatim, ignoring figure replacements.
def prose(s):
    s = s.split('\\begin{document}', 1)[1]
    return re.sub(r'\\begin\{figure\}.*?\\end\{figure\}', '<FIGURE>', s, flags=re.S)
assert prose(src) == prose(tex), 'Running text changed'
assert len(tikz) == 9
assert len(figures) == len(re.findall(r'\\begin\{figure\}\[H\]', tex))
assert not re.search(r'\\(?:resizebox|scalebox|tiny|scriptsize)\b|\\begin\{lrbox\}|transform canvas|transform shape|\bscale=', tex)
assert tex.count('\\tikzset{') == 1

labels = re.findall(r'node\[lbl[^]]*\]\{([^{}]*)\}', tex)
for label in labels:
    visible = label.replace('$_2$', '2').replace('$', '')
    assert '\\\\' not in label and len(visible) <= 25, (label, len(visible))
for key, nums in [('fig:dynamic', range(1, 10)), ('fig:dynamic-feedback', range(10, 20))]:
    f = next(f for f in tikz if '\\label{' + key + '}' in f)
    actual = [int(n) for n in re.findall(r'(\d+)\. ', f.split('\\caption{')[0])]
    assert actual == list(nums), (key, actual)
feedback = next(f for f in tikz if '\\label{fig:dynamic-feedback}' in f).split('\\begin{tikzpicture}')[1].split('\\end{tikzpicture}')[0]
feedback = re.sub(r'(?m)^%.*$', '', feedback)
assert 'pipeline' not in feedback and feedback.count('\\node[act,') == 6

compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8').split('\nvolumes:')[0]
devices = (ROOT / 'compose.devices.yml').read_text(encoding='utf-8')
shared = re.findall(r'^  ([a-z0-9_-]+):\s*$', compose, re.M)
device_names = re.findall(r'^  ([a-z0-9_-]+):\s*$', devices, re.M)
assert len(shared) == 11 and len(device_names) == 20
assert set(shared) == {'buildsim','occupancysim','broker','grafana','seed','physics','occupancy_counter','control','planner','pipeline','viewer'}
assert sum(n.startswith('sensor-') for n in device_names) == 10
assert sum(n.startswith('actuator-') for n in device_names) == 10
ports = {'physics': 8090, 'control': 8091, 'pipeline': 8092, 'planner': 8093,
         'viewer': 8094, 'buildsim': 9090, 'occupancysim': 8081, 'broker': 1883, 'grafana': 3000}
for name, port in ports.items():
    block = re.search(r'^  ' + name + r':\s*\n(.*?)(?=^  [a-z0-9_-]+:|\Z)', compose, re.M | re.S).group(1)
    assert f'127.0.0.1:{port}:' in block

config = json.loads((ROOT / 'config/rooms.json').read_text(encoding='utf-8'))
expected_devices = {f'sensor-{kind}-{r["name"].lower()}' for r in config['rooms'] for kind in ('co2','temp')}
expected_devices |= {f'actuator-{kind}-{r["name"].lower()}' for r in config['rooms'] for kind in ('vent','heat')}
assert set(device_names) == expected_devices
for k, v in {'co2_raise_ppm':800,'co2_high_ppm':1000,'co2_safety_ppm':1200,
             'min_change_interval_sim_s':300,'co2_hysteresis_ppm':100}.items():
    assert config['control'][k] == v

preamble = r'''% Replace the previous diagram-style block with this fragment once.
% Load float BEFORE hyperref to preserve correct [H] figure hyperlink anchors.
\usepackage{float}
\usepackage{tikz,pgfplots,xcolor}
\usetikzlibrary{arrows.meta,positioning,fit,backgrounds,shapes.geometric,babel}
\pgfplotsset{compat=1.18}
\definecolor{serviceblue}{HTML}{DBEAFE}
\definecolor{devicegreen}{HTML}{DCFCE7}
\definecolor{infrapurple}{HTML}{EDE9FE}
'''
preamble += tex[tex.index('% Shared diagram styles:'):tex.index('\\pagestyle')]
(OUT / 'preamble.tex').write_text(preamble, encoding='utf-8')
(OUT / 'figures.tex').write_text('% Replacement figure environments in report order; not a standalone document.\n\n' + '\n\n'.join(tikz) + '\n', encoding='utf-8')

log = (OUT / 'main.log').read_text(encoding='utf-8', errors='replace')
assert 'Overfull \\hbox' not in log
assert not re.search(r'^!|LaTeX Error|Package report-diagrams Error', log, re.M)
assert 'already defined' not in log
widths = [float(n)*2.54/72.27 for n in re.findall(r'REPORT-DIAGRAM-WIDTH: ([\d.]+)pt', log)]
assert widths and max(widths) <= 15.5
summary = {'input': str(Path(r'C:\Users\User\Downloads\main (8).tex')),
           'final_source_sha256': hashlib.sha256((OUT / 'main.tex').read_bytes()).hexdigest(),
           'running_text_unchanged': True, 'tikz_pictures':9, 'figures_all_H':True,
           'max_label_characters':max(len(x.replace('$_2$', '2').replace('$', '')) for x in labels),
           'max_width_cm':round(max(widths), 3), 'overfull_hboxes':0,
           'continuing_containers':30, 'one_shot_containers':1, 'ports':ports}
(OUT / 'validation/checks.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

pdf_out = ROOT / 'output/pdf/D7065E-redrawn.pdf'
shutil.copyfile(OUT / 'main.pdf', pdf_out)
zip_path = ROOT / 'output/latex/D7065E-redrawn.zip'
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for p in sorted(OUT.iterdir()):
        if p.suffix in {'.tex','.png','.jpeg','.md','.pdf'}:
            z.write(p, p.name)
    for p in sorted((OUT / 'validation').glob('*')):
        z.write(p, 'validation/' + p.name)
print(json.dumps(summary, indent=2))
print('Packaged:', zip_path)
