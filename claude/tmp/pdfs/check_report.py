from pathlib import Path
from pypdf import PdfReader
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

p = Path('output/pdf/D7065E-revised.pdf')
r = PdfReader(p)
texts = [page.extract_text() for page in r.pages]
text = ' '.join(' '.join(texts).split())
for phrase in ['256 MB', '154', '99.3', 'fbb5552', '15 simulated minutes']:
    assert phrase in text, phrase
print('Pages:', len(r.pages))
print('Characters:', len(text))
doc = pdfium.PdfDocument(p)
thumbs = []
for i in range(len(doc)):
    img = doc[i].render(scale=0.65).to_pil().convert('RGB')
    img.thumbnail((310,440))
    tile = Image.new('RGB',(330,470),'#e5e7eb')
    tile.paste(img,((330-img.width)//2,15))
    ImageDraw.Draw(tile).text((10,450),f'Page {i+1}',fill='black')
    thumbs.append(tile)
cols = 5
sheet = Image.new('RGB',(cols*330,((len(thumbs)+cols-1)//cols)*470),'white')
for i,tile in enumerate(thumbs):
    sheet.paste(tile,((i%cols)*330,(i//cols)*470))
sheet.save('tmp/pdfs/contact-sheet.png')
for i,t in enumerate(texts):
    if 'Recorded live fault tests' in t or 'Additional temperature metric' in t:
        doc[i].render(scale=1.4).to_pil().save(f'tmp/pdfs/detail-{i+1}.png')
print('Rendered all pages and detail pages.')
