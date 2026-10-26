"""Verifica consistência dos artefatos entregues e links locais de dados."""
import json,pathlib,re,urllib.parse
from html.parser import HTMLParser
ROOT=pathlib.Path(__file__).resolve().parents[1];OUT=ROOT/'output'
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if tag=='a' and 'href' in d:self.links.append(d['href'])
  if tag=='img' and 'src' in d:self.links.append(d['src'])
def run():
 problems=[];results=[]
 for prefix,file in [('', 'report.html'),('1700-','report-1700.html')]:
  source=(OUT/file).read_text();meta=json.loads((OUT/(prefix+'report-meta.json')).read_text());summary=json.loads((OUT/(prefix+'summary.json')).read_text())
  assert summary['complete'] and meta['analyzed']==499207 and meta['eligible']==497837
  assert not re.search(r'__[A-Z_]+__',source)
  parser=Links();parser.feed(source)
  for href in parser.links:
   u=urllib.parse.urlparse(href)
   if u.scheme or not u.path or u.path in ['/section','/api/section']:continue
   path=(OUT/urllib.parse.unquote(u.path)).resolve()
   if not path.exists():problems.append(dict(html=file,href=href))
  results.append(dict(html=file,links=len(parser.links),sections=meta['analyzed'],eligible=meta['eligible']))
 if (OUT/'documentary-comparison.html').exists():
  parser=Links();parser.feed((OUT/'documentary-comparison.html').read_text())
  for href in parser.links:
   u=urllib.parse.urlparse(href)
   if u.scheme or not u.path or u.path in ['/section','/api/section']:continue
   if not (OUT/urllib.parse.unquote(u.path)).resolve().exists():problems.append(dict(html='documentary-comparison.html',href=href))
  results.append(dict(html='documentary-comparison.html',links=len(parser.links)))
 assert not problems,problems
 result=dict(passed=True,pages=results,missing_links=problems)
 (OUT/'delivery-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':run()
