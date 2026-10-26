"""Atualiza apenas o fragmento já calculado de métodos, sem recalcular as seções."""
import json,pathlib
from timing_report import methods_html,recognition_summary,PRODUCER_SHA
from report import table,fmt
ROOT=pathlib.Path(__file__).resolve().parents[1]
def run():
 p=ROOT/'output/timing-summary.json';d=json.loads(p.read_text());rows=d['methods']
 assert any(r.get('cohort')=='2º turno · 17h05+' for r in rows)
 d['method_recognition_summary']=recognition_summary(rows);p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
 fragment=methods_html(rows,table,fmt)
 for name in ['report.html','report-1700.html','timing-fragment.html']:
  p=ROOT/'output'/name;s=p.read_text();heading=s.index('Identificação por método observado</h3>');start=s.rfind('<h3',0,heading);end=s.index('<h3>Comparação das mesmas seções entre turnos</h3>',start)
  updated=s[:start]+fragment+s[end:];p.with_suffix('.tmp').write_text(updated);p.with_suffix('.tmp').replace(p)
 cache=ROOT/'output/timing-fragment-meta.json';c=json.loads(cache.read_text());c['code']=PRODUCER_SHA;cache.write_text(json.dumps(c))
 for r in d['method_recognition_summary']:print(r)
if __name__=='__main__':run()
