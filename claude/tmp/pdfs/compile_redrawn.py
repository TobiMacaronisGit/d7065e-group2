from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from redraw_requested import FIGURES, MAIN, OUT

compiler = Path(r'C:\Program Files\WindowsApps\OpenAI.Codex_26.1007.2314.0_x64__2p2nqsd0c76g0\app\resources\tectonic\tectonic.exe')
env = dict(os.environ)
env['TECTONIC_CACHE_DIR'] = r'C:\Users\User\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Roaming\Codex\web\ChatGPT\latex\tectonic'
validation = OUT / 'validation'
validation.mkdir(exist_ok=True)
for key in sys.argv[1:]:
    if key != 'final':
        subprocess.run([sys.executable, str(Path(__file__).with_name('redraw_requested.py')), key], check=True)
    start = time.monotonic()
    r = subprocess.run([str(compiler), '--only-cached', '--keep-logs', '--keep-intermediates', '--untrusted', 'main.tex'],
                       cwd=OUT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    log = (OUT / 'main.log').read_text(encoding='utf-8', errors='replace')
    name = key.replace('fig:', '')
    (validation / f'{name}.log').write_text(log, encoding='utf-8')
    (validation / f'{name}-console.txt').write_text(r.stdout, encoding='utf-8')
    overfull = re.findall(r'Overfull \\hbox[^\n]*', log)
    summary = dict(figure=key, source_sha256=hashlib.sha256(MAIN.read_bytes()).hexdigest(),
                   exit_code=r.returncode, overfull_hboxes=overfull,
                   widths_cm=[round(float(x)*2.54/72.27, 3) for x in re.findall(r'REPORT-DIAGRAM-WIDTH: ([\d.]+)pt', log)])
    (validation / f'{name}.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(f'{key}: exit={r.returncode}, Overfull hbox={len(overfull)}, max width={max(summary["widths_cm"], default=0)} cm, {time.monotonic()-start:.1f}s', flush=True)
    if r.returncode or overfull:
        print(r.stdout[-5000:])
        raise SystemExit(1)
