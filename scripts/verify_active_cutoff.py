"""Auditoria dos novos cortes nas exportações, incluindo o segundo exato e a coorte de métodos."""
import json,pathlib,duckdb
ROOT=pathlib.Path(__file__).resolve().parents[1]
def run():
 c=duckdb.connect();a=ROOT/'output/1700-sections.parquet';b=ROOT/'output/sections.parquet'
 cur=c.execute('''SELECT count(*) n,count(*) FILTER(WHERE a.time_eligible AND
   (b.pre+b.at17+b.post<>a.total OR b.pre<>a.pre1705 OR b.at17<>a.at1705 OR b.post<>a.post1705
    OR b.pre<a.pre OR b.post>a.post)) partition_or_monotonicity_errors,
   count(*) FILTER(WHERE a.total<>b.total OR a.v13<>b.v13 OR a.v22<>b.v22) recount_changes,
   sum(b.pre) FILTER(WHERE b.time_eligible) pre1705,sum(b.at17) FILTER(WHERE b.time_eligible) at1705,
   sum(b.post) FILTER(WHERE b.time_eligible) post1705 FROM read_parquet(?) a JOIN read_parquet(?) b USING(id)''',[str(a),str(b)])
 d=dict(zip([x[0] for x in cur.description],cur.fetchone()));assert d['n']==499207 and d['partition_or_monotonicity_errors']==0 and d['recount_changes']==0
 for prefix,cut in [('',61500),('1700-',61200)]:
  summary=json.loads((ROOT/'output'/(prefix+'summary.json')).read_text());assert summary['cutoff_seconds']==cut and summary['complete']
 assert 'pre1735' not in [r[0] for r in c.execute('DESCRIBE SELECT * FROM read_parquet(?)',[str(b)]).fetchall()]
 methods=json.loads((ROOT/'output/timing-summary.json').read_text())['methods'];late=[r for r in methods if r.get('cohort')=='2º turno · 17h05+'];assert len(late)==5 and all(r['turn']==2 for r in late)
 source=json.loads((ROOT/'output/cutoff-1705-verification.json').read_text());assert late==source['methods_late']
 d.update(passed=True,cutoff_seconds=61500,late_method_groups=len(late),late_identification_records=sum(r['n'] for r in late))
 (ROOT/'output/active-cutoff-verification.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print(json.dumps(d,ensure_ascii=False))
if __name__=='__main__':run()
