"""Publica só HTML, PDF, figuras e agregados pequenos; nunca copia as bases eleitorais."""
import collections,hashlib,html,json,os,pathlib,re,shutil,urllib.parse
from html.parser import HTMLParser
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1];SOURCE=ROOT/'output';TARGET=ROOT/'public'
BULK={'.sqlite','.duckdb','.db','.csv','.parquet','.jsonl','.log','.jez','.dat','.rdv','.zip'}
MAX_BYTES=8*1024*1024
NOTICE='''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dados não incluídos</title><style>body{max-width:850px;margin:55px auto;padding:0 22px;font:17px/1.7 system-ui;color:#18354a}a{color:#08798a}</style><h1>Dados grandes não fazem parte desta cópia</h1><p>Esta publicação contém o relatório, PDF, figuras e agregados. SQLite, DuckDB, arquivos eleitorais brutos, sessões e exportações grandes de CSV/Parquet ficam apenas no ambiente de processamento.</p><p>A consulta individual por seção exige os lotes locais. Para habilitá-la, execute a coleta e o processamento descritos em <a href="https://github.com/mateustozoni/eleicoes/blob/main/docs/RUNNING.md">como reproduzir a análise</a> e use o servidor em modo completo.</p><p><a href="report.html">Relatório principal</a> · <a href="documentary-comparison.html">Extra documental</a> · <a href="pdf/relatorio-presidencial-2026.pdf">PDF completo</a></p></html>'''
BANNER='''<aside style="background:#e9f2fb;border-left:5px solid #3974a4;padding:16px 20px;margin:0 0 24px;font:14px/1.55 system-ui;color:#18354a"><strong>Cópia compacta publicada.</strong> Os números e sinais de processamento são da captura final; esta página não baixa nem reprocessa urnas. As bases grandes e a consulta por seção exigem o ambiente local. <a href="{notice}">Entenda o que não foi incluído</a>.</aside>'''
def clean_paths(text):
 return re.sub(r'/Users/[^\s"<>]+', '[caminho-local-omitido]',text)
class Rewriter(HTMLParser):
 def __init__(self,builder,path):super().__init__(convert_charrefs=False);self.builder=builder;self.path=path;self.parts=[];self.banner=False
 def tag(self):
  original=self.get_starttag_text()
  def replace(match):
   old=html.unescape(match[3]);new=self.builder.link(self.path,old,match[1])
   return match[0] if new==old else match[1]+'='+match[2]+html.escape(new,quote=True)+match[2]
  changed=re.sub(r'\b(href|src|action)\s*=\s*([\"\'])(.*?)\2',replace,original,flags=re.I)
  self.parts.append(changed)
  if re.match(r'<main(?:\s|>)',original,re.I) and not self.banner:
   notice=os.path.relpath(TARGET/'data-not-included.html',(TARGET/self.path).parent);self.parts.append(BANNER.format(notice=notice));self.banner=True
 def handle_starttag(self,*args):self.tag()
 def handle_startendtag(self,*args):self.tag()
 def handle_endtag(self,tag):self.parts.append('</'+tag+'>')
 def handle_data(self,data):self.parts.append(data)
 def handle_entityref(self,name):self.parts.append('&'+name+';')
 def handle_charref(self,name):self.parts.append('&#'+name+';')
 def handle_decl(self,data):self.parts.append('<!'+data+'>')
 def handle_comment(self,data):self.parts.append('<!--'+data+'-->')
class Builder:
 def __init__(self):self.queue=collections.deque();self.done=set();self.omitted=set()
 def enqueue(self,path):
  if path not in self.done:self.queue.append(path)
 def link(self,origin,url,attribute):
  p=urllib.parse.urlparse(url)
  if p.scheme or p.netloc or not p.path:return url
  relative=pathlib.Path(os.path.normpath(str(origin.parent/p.path.lstrip('/')))) if not p.path.startswith('/') else pathlib.Path(p.path.lstrip('/'))
  source=(SOURCE/relative).resolve()
  bulk=p.path in ['/section','/api/section'] or source.suffix.lower() in BULK
  if source.is_file() and source.stat().st_size>MAX_BYTES and relative.name!='metadata-status.json':bulk=True
  if not source.is_file():bulk=True
  if bulk or SOURCE.resolve() not in source.parents:
   self.omitted.add(str(relative));notice=os.path.relpath(TARGET/'data-not-included.html',(TARGET/origin).parent)
   return notice+'?file='+urllib.parse.quote(str(relative))
  self.enqueue(relative);return url
 def write(self,relative):
  if relative in self.done:return
  self.done.add(relative);source=SOURCE/relative;target=TARGET/relative;target.parent.mkdir(parents=True,exist_ok=True)
  if relative.suffix=='.html':
   parser=Rewriter(self,relative);parser.feed(source.read_text());target.write_text(clean_paths(''.join(parser.parts)))
  elif relative.suffix=='.json':
   d=json.loads(source.read_text())
   if relative.name=='metadata-status.json':
    d={k:v for k,v in d.items() if not isinstance(v,list)};original=json.loads(source.read_text());d.update(confirmed_count=len(original.get('confirmed',[])),changed_count=len(original.get('changed',[])),error_count=len(original.get('errors',[])),publication_note='Listas por seção omitidas do snapshot compacto; disponíveis ao executar a análise local.')
   if relative.name=='collection-status.json':d['recent_requests_per_second']=0
   target.write_text(clean_paths(json.dumps(d,ensure_ascii=False,indent=2)))
  else:shutil.copyfile(source,target)
 def run(self):
  for name in ['report.html','report-1700.html','documentary-comparison.html','live.js','collection-status.json','analysis-status.json','report-meta.json','1700-report-meta.json','reference-status.json','first-turn-download-status.json','timing-profile-status.json','metadata-progress.json','finalization-status.json','pdf-review.json','delivery-verification.json','documentary-verification.json','active-cutoff-verification.json']:
   if (SOURCE/name).exists():self.enqueue(pathlib.Path(name))
  while self.queue:self.write(self.queue.popleft())
  for p in (SOURCE/'figures').glob('*.png'):self.write(p.relative_to(SOURCE))
  (TARGET/'data-not-included.html').write_text(NOTICE)
  (TARGET/'index.html').write_text('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=report.html"><title>Relatório eleitoral</title><a href="report.html">Abrir relatório</a></html>')
  (TARGET/'.nojekyll').touch()
  files=[]
  for p in sorted(TARGET.rglob('*')):
   if not p.is_file() or p.name=='snapshot-manifest.json':continue
   assert p.suffix.lower() not in BULK,p
   assert p.stat().st_size<=MAX_BYTES,p
   files.append(dict(path=p.relative_to(TARGET).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
  manifest=dict(created_utc=datetime.now(timezone.utc).isoformat(),kind='compact_static_snapshot',raw_data_included=False,bulk_exports_included=False,section_lookup_requires_local_data=True,omitted_downloads=sorted(self.omitted),files=files,total_bytes=sum(f['bytes'] for f in files))
  (TARGET/'snapshot-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print(json.dumps(dict(files=len(files),mib=round(manifest['total_bytes']/1024**2,2),omitted=len(self.omitted))))
def main():
 status=json.loads((SOURCE/'finalization-status.json').read_text());pdf=SOURCE/status['pdf']
 assert status['verified'] and status['pdf_ready'],'Revise e verifique o PDF antes de exportar a publicação.'
 assert hashlib.sha256(pdf.read_bytes()).hexdigest()==status['pdf_sha256'],'O PDF mudou depois da última revisão.'
 TARGET.mkdir(exist_ok=True);Builder().run()
if __name__=='__main__':main()
