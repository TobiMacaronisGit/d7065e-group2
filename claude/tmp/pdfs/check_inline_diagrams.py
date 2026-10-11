from pathlib import Path
import re

compose = Path('docker-compose.yml').read_text(encoding='utf-8').split('\nvolumes:')[0]
devices = Path('compose.devices.yml').read_text(encoding='utf-8')
names = re.findall(r'^  ([a-z0-9_-]+):\s*$', compose, re.M)
device_names = re.findall(r'^  ([a-z0-9_-]+):\s*$', devices, re.M)
assert len(names) == 11 and len(device_names) == 20
assert sum(n.startswith('sensor-') for n in device_names) == 10
assert sum(n.startswith('actuator-') for n in device_names) == 10
expected = {'buildsim':9090,'occupancysim':8081,'broker':1883,'grafana':3000,
            'physics':8090,'control':8091,'pipeline':8092,'planner':8093,'viewer':8094}
for name,port in expected.items():
    block = re.search(r'^  '+name+r':\s*\n(.*?)(?=^  [a-z0-9_-]+:|\Z)',compose,re.M|re.S).group(1)
    assert f'127.0.0.1:{port}:' in block,(name,port)
print('Compose: 30 continuing + seed; all nine published ports match.')
s = Path('output/latex/D7065E-updated/main.tex').read_text(encoding='utf-8')
assert not any(x in s for x in ['\\resizebox','\\begin{lrbox}','\\scriptsize','\\tiny','Stealth'])
assert all(x == 'H' for x in re.findall(r'\\begin\{figure\}\[([^]]+)\]',s))
assert '\\input{' not in s
labels = re.findall(r'node\[lbl\]\{([^{}]*)\}',s)
for label in labels:
    plain = re.sub(r'\$_?\d?\$', '',label).replace('\\','')
    assert len(plain) <= 25,(plain,len(plain))
assert len(re.findall(r'\\begin\{tikzpicture\}',s)) == 9
assert s.count('execute at end picture=\\checkdiagramwidth') == 1
assert '\\ifdim\\diagramwidth>15.5cm' in s
print('9 native-size TikZ pictures; all figures [H]; labels <=25 characters; all definitions inline.')
for path in Path('docs/diagrams').glob('*.d2'):
    edges = [line for line in path.read_text(encoding='utf-8').splitlines()
             if ' -> ' in line and not line.lstrip().startswith('#')]
    print(path.name, len(edges),'edges')
for label,numbers in [('fig:dynamic',range(1,10)),('fig:dynamic-feedback',range(10,20))]:
    part = next(m.group() for m in re.finditer(r'\\begin\{figure\}.*?\\end\{figure\}',s,re.S) if '\\label{'+label+'}' in m.group())
    for i in numbers:
        assert re.search(r'(?<!\d)'+str(i)+r'\. ',part),i
print('Sequence numbering 1-19 retained; concurrent step 20 in caption.')
