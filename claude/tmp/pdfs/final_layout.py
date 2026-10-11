from pathlib import Path
import re
p = Path('output/pdf/D7065E-revised.tex')
s = p.read_text(encoding='utf-8')
s = re.sub(r'(\\section\*\{Evidence and submission status\}\n).*?(?=\\clearpage)', lambda m: m.group(1) + 'Architecture reflects main commit \\texttt{66e0805}; additional plots and temperature analysis are identified as branch \\texttt{fbb5552} material. This revision incorporates recorded evidence and source review; no new application experiments were run.\n\n', s, flags=re.S)
s = s.replace('\\begin{figure}[p]\\centering\n\\includegraphics', '\\begin{figure}[!ht]\\centering\n\\includegraphics', 1)
p.write_text(s, encoding='utf-8')
