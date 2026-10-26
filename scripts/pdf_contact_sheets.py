"""Folhas de contato locais para inspeção de todas as páginas renderizadas."""
import pathlib,json,sys
from PIL import Image,ImageOps,ImageDraw
ROOT=pathlib.Path(__file__).resolve().parents[1];folder=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'tmp/pdfs/final-rendered')
files=sorted(folder.glob('page-*.png'));assert files
out=ROOT/(sys.argv[2] if len(sys.argv)>2 else 'tmp/pdfs/final-contact');out.mkdir(parents=True,exist_ok=True)
for start in range(0,len(files),6):
 canvas=Image.new('RGB',(1800,1760),'#cad6df');draw=ImageDraw.Draw(canvas)
 for i,p in enumerate(files[start:start+6]):
  im=Image.open(p).convert('RGB');im.thumbnail((580,825));x=(i%3)*600+10;y=(i//3)*880+25;canvas.paste(im,(x,y));draw.text((x,y-18),p.stem,fill='black')
 canvas.save(out/f'sheet-{start//6+1:02}.png')
print(json.dumps(dict(pages=len(files),sheets=(len(files)+5)//6)))
