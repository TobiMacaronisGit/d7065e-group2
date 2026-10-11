from pathlib import Path
import pypdfium2 as pdfium
from pypdf import PdfReader
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[2]
out = root / 'tmp/pdfs/redrawn'
out.mkdir(exist_ok=True)
pdf = root / 'output/latex/D7065E-redrawn/main.pdf'
reader = PdfReader(pdf)
doc = pdfium.PdfDocument(pdf)
phrases = ['System context:', 'Container view, panel A:', 'Container view, panel B:',
           'Components within control', 'sequence, part 1:', 'sequence, part 2:',
           'Controller lifecycle,', 'Single-host deployment,', 'Existing R6']
pages = []
for i, page in enumerate(reader.pages):
    text = ' '.join((page.extract_text() or '').split())
    names = [p for p in phrases if p in text]
    if names:
        image = doc[i].render(scale=1.65).to_pil().convert('RGB')
        image.save(out / f'page-{i+1:02}.png')
        print(i+1, ', '.join(names))
        image.thumbnail((380, 540))
        tile = Image.new('RGB', (400, 570), '#e5e7eb')
        tile.paste(image, ((400-image.width)//2, 5))
        ImageDraw.Draw(tile).text((10, 548), f'Page {i+1}: {names[0]}', fill='black')
        pages.append(tile)
sheet = Image.new('RGB', (1200, 570*((len(pages)+2)//3)), 'white')
for i, image in enumerate(pages):
    sheet.paste(image, ((i%3)*400, (i//3)*570))
sheet.save(out / 'contact.png')
print('Total pages:', len(reader.pages))
