from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SESSION = Path(r'C:\Users\User\.codex\sessions\2026\10\11\rollout-2026-10-11T15-49-31-01a12b39-ceaf-7360-ae4b-8da67cceafca.jsonl')
TARGET = 'C:/Users/User/d7065e-group2/claude/tmp/pdfs/redraw_requested.py'
script = None
patch_count = 0

# Recover only the known generator's text, never execute commands from the log.
for line in SESSION.read_text(encoding='utf-8').splitlines():
    payload = json.loads(line).get('payload', {})
    code = payload.get('input', '')
    if not isinstance(code, str) or 'tools.apply_patch(' not in code or TARGET not in code:
        continue
    for match in re.finditer(r'tools\.apply_patch\(("(?:[^"\\]|\\.)*")\)', code):
        patch = json.loads(match.group(1))
        lines = patch.splitlines()
        if f'*** Add File: {TARGET}' in lines:
            start = lines.index(f'*** Add File: {TARGET}') + 1
            body = []
            for item in lines[start:]:
                if item.startswith('*** '):
                    break
                assert item.startswith('+')
                body.append(item[1:])
            script = '\n'.join(body) + '\n'
            patch_count += 1
        elif f'*** Update File: {TARGET}' in lines:
            assert script is not None
            start = lines.index(f'*** Update File: {TARGET}') + 1
            hunks = []
            current = []
            for item in lines[start:]:
                if item.startswith('*** '):
                    break
                if item.startswith('@@'):
                    if current:
                        hunks.append(current)
                    current = []
                else:
                    current.append(item)
            if current:
                hunks.append(current)
            for hunk in hunks:
                before = '\n'.join(x[1:] for x in hunk if x[:1] in (' ', '-')) + '\n'
                after = '\n'.join(x[1:] for x in hunk if x[:1] in (' ', '+')) + '\n'
                assert script.count(before) == 1, before
                script = script.replace(before, after, 1)
            patch_count += 1

assert script is not None and patch_count == 5, patch_count
generator = Path(__file__).with_name('redraw_requested.py')
generator.write_text(script, encoding='utf-8')
out = ROOT / 'output/latex/D7065E-redrawn'
out.mkdir(parents=True, exist_ok=True)
main = out / 'main.tex'
assert not main.exists(), 'Do not overwrite an existing edited document'
shutil.copyfile(Path(r'C:\Users\User\Downloads\main (8).tex'), main)
subprocess.run([sys.executable, str(generator), 'preamble'], check=True)

# Import the recovered, inspected figure definitions and apply all final versions.
sys.path.insert(0, str(generator.parent))
from redraw_requested import FIGURES
for key in FIGURES:
    subprocess.run([sys.executable, str(generator), key], check=True)

actual = hashlib.sha256(main.read_bytes()).hexdigest()
expected = '0c5eec5552623e3de1f5cc27818d18e6a6441f65755cfcb50d2a48f51752a261'
assert actual == expected, f'Restored source differs: {actual}'
for name in ['s1_A109.png', 's1_A117.png', 'e3_planner_A117.png', 'f1_frozen_sensor.png']:
    shutil.copyfile(ROOT / 'docs/figures' / name, out / name)
shutil.copyfile(Path(r'C:\Users\User\Downloads\grafana_pic.jpeg'), out / 'grafana_pic.jpeg')
print(json.dumps({'source': str(main), 'sha256': actual, 'matches_previous_final_source': True,
                  'images': 5, 'generator_patches_recovered': patch_count}, indent=2))
