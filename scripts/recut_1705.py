"""Novo corte exato sem reler todo o corpus: bins de 5min e reparo do segundo limítrofe nos originais."""
import collections,concurrent.futures,fcntl,json,pathlib,time
import pyarrow as pa,pyarrow.parquet as pq
from analytics_store import open_store
from analyze import items,process,UFS
ROOT=pathlib.Path(__file__).resolve().parents[1];CUT=61500
def late_method_stats(con,files):
    methods=con.execute('''SELECT 2::INTEGER turn,'2º turno · 17h05+' AS cohort,auth_kind,'identification_seconds' AS metric,
      count(identification_seconds)::BIGINT n,avg(identification_seconds) mean,
      median(identification_seconds) median,quantile_cont(identification_seconds,.9) p90,
      quantile_cont(identification_seconds,.95) p95,max(identification_seconds) maximum
      FROM read_parquet(?,union_by_name=true) WHERE section_eligible AND valid_timing AND presidential_bsb>61500
      AND identification_seconds IS NOT NULL GROUP BY auth_kind ORDER BY auth_kind''',[files])
    method_rows=[dict(zip([x[0] for x in methods.description],r)) for r in methods.fetchall()]
    return method_rows
def worker(item):
 r=process(item,additional_cutoff=CUT)
 return dict(id=r['id'],match=r['match'],eligible=r['time_eligible'],counts=r['additional_cutoff'])
def run():
 with (ROOT/'output/.report.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);con=open_store()
  keys={r[0] for r in con.execute('SELECT id FROM sections').fetchall()}
  boundary={r[0] for r in con.execute("SELECT id FROM sections WHERE time_eligible AND list_contains(list_transform(bins,x->CASE WHEN x.kind='vote' THEN x.second ELSE -1 END),61500)").fetchall()}
  target=ROOT/'data/cutoffs/1705';target.mkdir(parents=True,exist_ok=True);checkpoint=target/'boundary.jsonl';done={}
  if checkpoint.exists():
   for line in checkpoint.read_text().splitlines():
    r=json.loads(line);done[r['id']]=r
  pending=boundary-set(done)
  with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool,checkpoint.open('a') as log:
   for uf in UFS:
    for r in pool.map(worker,items(uf,keys-pending),chunksize=8):
     assert r['match'] and r['eligible'],r['id'];done[r['id']]=r;log.write(json.dumps(r)+'\n')
    log.flush();print('boundary',uf,len(done),'/',len(boundary),flush=True)
  assert boundary<=set(done)
  exact=[]
  for key in boundary:
   for r in done[key]['counts']['auth_cuts']:
    if r['period']=='at17':exact.append(dict(id=key,kind=r['kind'],n=r['n']))
  schema=pa.schema([('id',pa.string()),('kind',pa.string()),('n',pa.int64())]);con.register('exact_1705',pa.Table.from_pylist(exact,schema=schema))
  con.execute("CREATE OR REPLACE TEMP TABLE bins_1705 AS SELECT s.id,b.kind,b.second,b.n FROM sections s,unnest(bins) u(b) WHERE b.kind LIKE 'vote_%'")
  con.execute('''CREATE OR REPLACE TEMP TABLE recut_auth AS WITH base AS (
     SELECT id,substr(kind,6) kind,sum(n) FILTER(WHERE second<61500)::BIGINT pre,
     sum(n) FILTER(WHERE second>=61500)::BIGINT post FROM bins_1705 GROUP BY id,kind),
    cells AS (SELECT b.id,b.kind,coalesce(b.pre,0)::BIGINT pre,coalesce(e.n,0)::BIGINT at17,
      (coalesce(b.post,0)-coalesce(e.n,0))::BIGINT post FROM base b LEFT JOIN exact_1705 e USING(id,kind))
    SELECT id,list(struct_pack(period:=v.period,kind:=kind,n:=v.n) ORDER BY v.period,kind) auth_cuts1705,
    sum(v.n) FILTER(WHERE v.period='pre')::BIGINT pre1705,
    sum(v.n) FILTER(WHERE v.period='at17')::BIGINT at1705,
    sum(v.n) FILTER(WHERE v.period='post')::BIGINT post1705
    FROM cells CROSS JOIN LATERAL (VALUES ('pre',pre),('at17',at17),('post',post)) v(period,n)
    GROUP BY id''')
  con.execute('''CREATE OR REPLACE TABLE cutoff_1705_sections AS SELECT s.id,coalesce(r.pre1705,0)::BIGINT pre1705,
    coalesce(r.at1705,0)::BIGINT at1705,coalesce(r.post1705,0)::BIGINT post1705,
    coalesce(r.auth_cuts1705,[]::STRUCT(period VARCHAR,kind VARCHAR,n BIGINT)[]) auth_cuts1705
    FROM sections s LEFT JOIN recut_auth r USING(id)''')
  bad=con.execute('''SELECT count(*) FROM sections s JOIN cutoff_1705_sections r USING(id)
    WHERE s.time_eligible AND (pre1705+at1705+post1705<>s.total OR pre1705<s.pre OR post1705>s.post)''').fetchone()[0]
  assert bad==0,bad
  for key in boundary:
   actual=con.execute('SELECT pre1705,at1705,post1705 FROM cutoff_1705_sections WHERE id=?',[key]).fetchone();r=done[key]['counts']
   assert actual==(r['pre'],r['at17'],r['post']),(key,actual,r)
  con.execute('COPY cutoff_1705_sections TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(target/'sections.parquet')])
  manifests=sorted((ROOT/'data/timing/v1/2t').glob('*/*/manifest.json'));files=[str(p.parent/'events.parquet') for p in manifests]
  # Coorte pelo horário da confirmação presidencial, a mesma noção de voto pós-corte.
  method_rows=late_method_stats(con,files)
  result=dict(cutoff_seconds=CUT,cutoff_label='17h05',sections=len(keys),boundary_sections_reparsed=len(boundary),partition_errors=bad,
    methods_late=method_rows,method_cohort_basis='presidential_bsb > 61500; section_eligible AND valid_timing; identification_seconds NOT NULL')
  (ROOT/'output/cutoff-1705-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));con.close();print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':run()
