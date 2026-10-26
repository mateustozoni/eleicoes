"""Confere o snapshot e impede inclusão acidental de bases, segredos e arquivos grandes."""
import hashlib,json,pathlib,re,subprocess,urllib.parse
from html.parser import HTMLParser
ROOT=pathlib.Path(__file__).resolve().parents[1];PUBLIC=ROOT/'public'
FORBIDDEN={'.sqlite','.duckdb','.db','.parquet','.csv','.jsonl','.log','.jez','.dat','.rdv','.zip'}
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='a' and 'href' in attrs:self.links.append(attrs['href'])
  if tag in ['img','script'] and 'src' in attrs:self.links.append(attrs['src'])
def run():
 m=json.loads((PUBLIC/'snapshot-manifest.json').read_text());assert not m['raw_data_included'] and not m['bulk_exports_included']
 for row in m['files']:
  p=PUBLIC/row['path'];assert p.is_file(),p;assert p.stat().st_size==row['bytes'],p
  assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],p
  assert p.suffix.lower() not in FORBIDDEN,p;assert p.stat().st_size<=8*1024**2,p
  if p.suffix in {'.html','.js','.json'}:assert '/Users/' not in p.read_text(),p
 broken=[]
 for p in PUBLIC.rglob('*.html'):
  parser=Links();parser.feed(p.read_text())
  for href in parser.links:
   u=urllib.parse.urlparse(href)
   if u.scheme or u.netloc or not u.path:continue
   target=(PUBLIC/u.path.lstrip('/')).resolve() if u.path.startswith('/') else (p.parent/urllib.parse.unquote(u.path)).resolve()
   if PUBLIC.resolve() not in target.parents or not target.is_file():broken.append((str(p),href))
 assert not broken,broken
 for name in ['report.html','report-1700.html','documentary-comparison.html','pdf/relatorio-presidencial-2026.pdf','data-not-included.html']:assert (PUBLIC/name).is_file()
 status=json.loads((PUBLIC/'finalization-status.json').read_text());pdf=PUBLIC/status['pdf'];assert hashlib.sha256(pdf.read_bytes()).hexdigest()==status['pdf_sha256']
 tracked=[]
 if (ROOT/'.git').exists():
  proc=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True);tracked=proc.stdout.decode().split('\0')
 for name in filter(None,tracked):
  p=ROOT/name
  assert not name.startswith(('data/','output/','output-history/','tmp/','.venv/')),name
  assert p.suffix.lower() not in FORBIDDEN or name=='docs/official-schema.zip',name
  assert p.stat().st_size<=8*1024**2,name
  if p.suffix in {'.py','.md','.json','.yml','.txt','.html','.js'}:
   text=p.read_text();assert not re.search(r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY',text),name
 print(json.dumps(dict(passed=True,public_files=len(m['files']),public_mib=round(m['total_bytes']/1024**2,2),broken_links=len(broken),tracked_files=len(list(filter(None,tracked))),raw_data_included=False)))
if __name__=='__main__':run()
