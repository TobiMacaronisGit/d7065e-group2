from pathlib import Path
import re
import shutil

root = Path.cwd()
source = Path(r'C:\Users\User\Downloads\main (7).tex').read_text(encoding='utf-8')
original = (root / 'report/main.tex').read_text(encoding='utf-8')
# Verify that the already reviewed report revision applies to this user's file.
clean = source.replace('\\usepackage{graphicx}\n', '')
screenshot = re.search(r'\\begin\{figure\}\[htbp\]\s*\\centering\s*\\includegraphics\[width=0\.6\\textwidth\]\{grafana_pic\.jpeg\}.*?\\end\{figure\}', clean, re.S)
assert screenshot, 'Expected user dashboard figure is missing'
clean = clean[:screenshot.start()] + clean[screenshot.end():]
assert re.sub(r'\s+', ' ', clean).strip() == re.sub(r'\s+', ' ', original).strip(), 'User source has additional changes requiring review'

dest = root / 'output/latex/D7065E-updated'
dest.mkdir(parents=True, exist_ok=True)
s = (root / 'output/pdf/D7065E-revised.tex').read_text(encoding='utf-8')
s = s.replace('Additional plots and the 18--24 $^\\circ$C descriptive metric come from \\texttt{origin/tobias}, commit \\texttt{fbb5552}, which was not merged into main at review time.', 'The fetched \\texttt{origin/tobias} branch is at \\texttt{270d623}: it contains main plus the plots and 18--24 $^\\circ$C descriptive metric introduced in \\texttt{fbb5552}. Its latest cleanup removes local repair backups and the project ZIP from version control; it does not alter the runtime or add experiments. These branch additions were not merged into main at review time.')
s = s.replace('No screenshot is supplied with this revision; the architecture diagrams describe implemented flows, and no fabricated dashboard image is used as evidence.', 'Figure~\\ref{fig:grafana-dashboard} preserves the dashboard screenshot supplied with the source document. It shows observed A109 CO\\textsubscript{2}, temperature, ventilation/occupancy and decision reasons. Its capture is illustrative: no run identifier is supplied, so it is not used to establish the R6--R8 metrics or fault-test outcomes.')
dashboard = r'''
\begin{figure}[htbp]
    \centering
    \includegraphics[width=\linewidth]{grafana_pic.jpeg}
    \caption{Grafana dashboard for A109, preserved from the supplied source document. The screenshot illustrates the presentation interface; its run provenance is unspecified.}
    \label{fig:grafana-dashboard}
\end{figure}

'''
s = s.replace('\\section{Risks and critical reflection}', dashboard + '\\section{Risks and critical reflection}')
s = s.replace('Fault and crash scenarios remain separate verification tasks; they are not established by a successful weekday run.', 'Fault and crash evidence is assessed separately from weekday performance; recorded F1/F3/F6 results are included in the test section.')
s = s.replace('Additional recorded evidence figures', 'Additional recorded evidence figures')
s = s.replace('\\section*{Additional recorded evidence figures}\n', '\\section*{Additional recorded evidence figures}\\addcontentsline{toc}{section}{Additional recorded evidence figures}\n')
# Keep the final evidence declaration concise and consistent with the reviewed branches.
s = re.sub(r'(\\section\*\{Evidence and submission status\}\\addcontentsline\{toc\}\{section\}\{Evidence and submission status\}\n).*?(?=\\clearpage)', lambda m: m.group(1) + 'The report reflects main commit \\texttt{66e0805} and the identified additions on \\texttt{origin/tobias} at \\texttt{270d623}. Existing run artifacts and recorded live fault tests support the stated results. The supplied dashboard screenshot is preserved as interface evidence. No new application experiments were run for this revision.\n\n', s, flags=re.S)
(dest / 'main.tex').write_text(s, encoding='utf-8')
shutil.copy2(Path(r'C:\Users\User\Downloads\grafana_pic.jpeg'), dest / 'grafana_pic.jpeg')
for name in ['s1_A109.png', 's1_A117.png', 'e3_planner_A117.png', 'f1_frozen_sensor.png']:
    shutil.copy2(root / 'output/pdf' / name, dest / name)
(dest / 'README.txt').write_text('Upload main.tex and all five image files together to Overleaf. Select main.tex as the main document and use XeLaTeX or pdfLaTeX. The accompanying main.pdf is the compiled preview.\n\nSource: supplied main (7).tex; checked GitHub main 66e0805 and tobias 270d623 on 11 October 2026. The original downloaded file is preserved.\n', encoding='utf-8')
print(dest / 'main.tex')
