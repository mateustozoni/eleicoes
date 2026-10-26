"""Publica um sinal pequeno para o navegador, sem exportar listas de hashes."""
import json,pathlib,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
while True:
 m=json.loads((ROOT/'output/metadata-status.json').read_text());d={k:v for k,v in m.items() if not isinstance(v,list)}
 d.update(confirmed_count=len(m['confirmed']),changed_count=len(m['changed']),error_count=len(m['errors']))
 p=ROOT/'output/metadata-progress.json';p.with_suffix('.tmp').write_text(json.dumps(d));p.with_suffix('.tmp').replace(p)
 if m['state']=='finished':break
 time.sleep(5)
