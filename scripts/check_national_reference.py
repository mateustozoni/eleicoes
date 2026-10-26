"""Revalida os dois totais nacionais sem sobrescrever as referências da captura."""
import hashlib,json,pathlib,urllib.request
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
def run():
 for first,election,name in [(False,6258,'national'),(True,6257,'first-turn-national')]:
  url=f'https://resultados.tse.jus.br/oficial/ele2026/{election}/dados/br/br-c0001-e{election:06}-u.json'
  with urllib.request.urlopen(url,timeout=60) as r:payload=r.read()
  current=json.loads(payload);captured=json.loads((ROOT/'data/raw'/(name+'.json')).read_text())
  (ROOT/'data/raw'/(name+'-final.json')).write_bytes(payload)
  result=dict(url=url,sha256=hashlib.sha256(payload).hexdigest(),same_content=current==captured,generation_date=current.get('dg'),generation_time=current.get('hg'),checked_utc=datetime.now(timezone.utc).isoformat())
  file='first-turn-national-reference-check.json' if first else 'national-reference-check.json';(ROOT/'output'/file).write_text(json.dumps(result,indent=2))
  if not result['same_content']:raise RuntimeError('A referência nacional mudou: revise as versões antes da auditoria: '+name)
  print(file,'matches captured reference',flush=True)
if __name__=='__main__':run()
