"""Comparações exatas por marcos documentais; toda a computação fica no servidor local."""
import json,pathlib,os,hashlib,math
import duckdb,numpy as np
from scipy.stats import pearsonr,spearmanr
from documentary_sources import sources,minimum_judges
from profile_store import KNOWN_NONBIO
ROOT=pathlib.Path(__file__).resolve().parents[1]
METRICS=['identification_seconds','voting_seconds','pres_stage_seconds','confirmation_gap_seconds']
def records(con,sql,args=None):
 q=con.execute(sql,args or []);return [dict(zip([x[0] for x in q.description],r)) for r in q.fetchall()]
def corr(rows):
 vals=[(r['nonbio_rate'],r['post_fraction']) for r in rows if r.get('nonbio_rate') is not None and r.get('post_fraction') is not None]
 if len(vals)<3:return dict(n=len(vals),pearson=None,spearman=None)
 v=np.array(vals);vary=bool(np.ptp(v[:,0]) and np.ptp(v[:,1]))
 return dict(n=len(vals),pearson=float(pearsonr(v[:,0],v[:,1]).statistic) if vary else None,spearman=float(spearmanr(v[:,0],v[:,1]).statistic) if vary else None)
def event_bands(con):
  bands=records(con,"""SELECT a.id anchor,e.turn,
    count(*) FILTER(WHERE presidential_bsb>a.second) post_n,
    count(*) FILTER(WHERE presidential_bsb>a.second AND presidential_bsb<61200) post_before17,
    count(*) FILTER(WHERE presidential_bsb>a.second AND presidential_bsb>=61200 AND presidential_bsb<=61500) post_17_to_1705,
    count(*) FILTER(WHERE presidential_bsb>a.second AND presidential_bsb>61500) post_after1705
    FROM afternoon e CROSS JOIN anchors a GROUP BY a.id,e.turn ORDER BY a.id,e.turn""")
  assert all(r['post_n']==r['post_before17']+r['post_17_to_1705']+r['post_after1705'] for r in bands)
  return bands

def run():
 out=ROOT/'output';src=sources();earliest=minimum_judges(src['regional']);assert earliest['uf']=='sp' and earliest['second']==62280;src['minimum_judges_documented']=earliest;con=duckdb.connect(str(ROOT/'data/documentary.duckdb'));con.execute("SET memory_limit='8GB'");con.execute('SET threads='+str(os.cpu_count() or 4))
 con.execute("ATTACH '"+str(ROOT/'data/analytics.duckdb').replace("'","''")+"' AS original (READ_ONLY)")
 con.execute("CREATE OR REPLACE TABLE section_metadata AS SELECT * FROM original.main.timing_sections WHERE uf<>'zz' AND section_eligible")
 con.execute('CREATE OR REPLACE TABLE daily_flows AS SELECT * FROM original.main.timing_flows')
 con.execute('DETACH original')
 assert con.execute('SELECT count(*) FROM section_metadata WHERE valid_sessions<>total').fetchone()[0]==0
 paths=sorted((ROOT/'data/timing/v1').glob('*t/*/*/manifest.json'));files=[str(p.parent/'events.parquet') for p in paths]
 fp=hashlib.sha256('\n'.join(str(p)+':'+str(p.stat().st_size) for p in paths).encode()).hexdigest()
 cache=ROOT/'data/documentary-events-manifest.json';previous=json.loads(cache.read_text()) if cache.exists() else {}
 if previous.get('fingerprint')!=fp:
  con.execute('''CREATE OR REPLACE TABLE afternoon AS SELECT turn,id,uf,auth_kind,presidential_bsb,enabled_bsb,
   identification_seconds,voting_seconds,pres_stage_seconds,confirmation_gap_seconds,active_confirmation_gap_seconds
   FROM read_parquet(?,union_by_name=true) WHERE section_eligible AND valid_timing AND uf<>'zz' AND presidential_bsb>=57600''',[files])
  cache.write_text(json.dumps(dict(fingerprint=fp,start_seconds=57600)))
 print('afternoon',con.execute('SELECT turn,count(*) FROM afternoon GROUP BY turn').fetchall(),flush=True)
 con.execute('CREATE OR REPLACE TABLE anchors(id VARCHAR,second INTEGER,label VARCHAR)')
 con.executemany('INSERT INTO anchors VALUES (?,?,?)',[(a['id'],a['second'],a['label']) for a in src['anchors']])
 con.execute('''CREATE OR REPLACE TABLE section_post AS SELECT a.id anchor,e.turn,e.id,
   count(*) FILTER(WHERE presidential_bsb>a.second)::BIGINT post_n,count(*) FILTER(WHERE presidential_bsb=a.second)::BIGINT at_n,
   count(*) FILTER(WHERE presidential_bsb>a.second AND auth_kind='elector_biometric')::BIGINT bio_post,
   count(*) FILTER(WHERE presidential_bsb>a.second AND auth_kind IN ('''+KNOWN_NONBIO+'''))::BIGINT nonbio_post,
   avg(identification_seconds) FILTER(WHERE presidential_bsb>a.second) identification_mean,
   avg(voting_seconds) FILTER(WHERE presidential_bsb>a.second) voting_mean,
   median(confirmation_gap_seconds) FILTER(WHERE presidential_bsb>a.second) gap_median
   FROM afternoon e CROSS JOIN anchors a GROUP BY a.id,e.turn,e.id''')
 con.execute('''CREATE OR REPLACE TABLE section_comparison AS SELECT a.id anchor,a.second cutoff,s.turn,s.id,s.uf,s.name,s.total,s.aptos,
   coalesce(p.post_n,0)::BIGINT post_n,coalesce(p.at_n,0)::BIGINT at_n,
   (s.total-coalesce(p.post_n,0)-coalesce(p.at_n,0))::BIGINT pre_n,
   coalesce(p.bio_post,0)::BIGINT bio_post,coalesce(p.nonbio_post,0)::BIGINT nonbio_post,
   p.identification_mean,p.voting_mean,p.gap_median,
   p.nonbio_post*1.0/nullif(p.bio_post+p.nonbio_post,0) nonbio_share_post,
   f.nonbiometric_sessions*1.0/nullif(f.biometric_sessions+f.nonbiometric_sessions,0) nonbio_rate,
   coalesce(p.post_n,0)*1.0/nullif(s.total,0) post_fraction
   FROM section_metadata s CROSS JOIN anchors a LEFT JOIN section_post p ON p.turn=s.turn AND p.id=s.id AND p.anchor=a.id
   LEFT JOIN daily_flows f ON f.turn=s.turn AND f.id=s.id''')
 bad=con.execute('SELECT count(*) FROM section_comparison WHERE pre_n<0 OR post_n<0 OR pre_n+at_n+post_n<>total').fetchone()[0];assert bad==0
 con.execute('COPY section_comparison TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(out/'documentary-sections.parquet')])
 national=records(con,'''SELECT anchor,cutoff,turn,count(*) sections,sum(total) ballots,sum(pre_n) pre_n,sum(at_n) at_n,sum(post_n) post_n,
  count(*) FILTER(WHERE post_n>0) sections_with_post,sum(bio_post) bio_post,sum(nonbio_post) nonbio_post,
  sum(post_n)-sum(bio_post)-sum(nonbio_post) unknown_post FROM section_comparison GROUP BY anchor,cutoff,turn ORDER BY cutoff,turn''')
 by_state=records(con,'''SELECT anchor,cutoff,turn,uf,count(*) sections,sum(total) ballots,sum(post_n) post_n,sum(at_n) at_n,
  sum(bio_post) bio_post,sum(nonbio_post) nonbio_post,count(*) FILTER(WHERE post_n>0) sections_with_post,
  sum(post_n)*1.0/sum(total) post_fraction,sum(nonbio_post)*1.0/nullif(sum(nonbio_post+bio_post),0) nonbio_share_post,
  sum(f.nonbiometric_sessions)*1.0/nullif(sum(f.nonbiometric_sessions+f.biometric_sessions),0) nonbio_rate
  FROM section_comparison s LEFT JOIN daily_flows f USING(turn,id) GROUP BY anchor,cutoff,turn,uf ORDER BY cutoff,turn,uf''')
 stats=[];windows=[];window_activity=[]
 for a in src['anchors']:
  for metric in METRICS:
   rows=records(con,f'''SELECT turn,auth_kind,count({metric})::BIGINT n,avg({metric}) mean,median({metric}) median,quantile_cont({metric},.9) p90
    FROM afternoon WHERE presidential_bsb>? AND {metric} IS NOT NULL GROUP BY turn,auth_kind ORDER BY turn,auth_kind''',[a['second']])
   for r in rows:r.update(anchor=a['id'],metric=metric)
   stats.extend(rows)
  for width in [900,1800]:
   rows=records(con,"""SELECT turn,CASE WHEN presidential_bsb<? THEN 'pre' ELSE 'post' END period,
      count(*) n,count(DISTINCT id) sections FROM afternoon WHERE presidential_bsb>=? AND presidential_bsb<=?
      AND presidential_bsb<>? GROUP BY turn,period ORDER BY turn,period""",[a['second'],a['second']-width,a['second']+width,a['second']])
   for r in rows:r.update(anchor=a['id'],width_seconds=width,per_minute=r['n']/(width/60))
   window_activity.extend(rows)
   for metric in METRICS:
    rows=records(con,f'''SELECT turn,CASE WHEN presidential_bsb<? THEN 'pre' ELSE 'post' END period,
       count({metric})::BIGINT n,avg({metric}) mean,median({metric}) median,quantile_cont({metric},.9) p90
       FROM afternoon WHERE presidential_bsb>=? AND presidential_bsb<=? AND presidential_bsb<>? AND {metric} IS NOT NULL
       GROUP BY turn,period ORDER BY turn,period''',[a['second'],a['second']-width,a['second']+width,a['second']])
    for r in rows:r.update(anchor=a['id'],width_seconds=width,metric=metric)
    windows.extend(rows)
 print('time statistics complete',flush=True)
 bins=records(con,'''SELECT turn,uf,(floor(presidential_bsb/300)*300)::INTEGER AS "second",count(*) n,
  count(*) FILTER(WHERE auth_kind='elector_biometric') bio_n,
  count(*) FILTER(WHERE auth_kind IN ('''+KNOWN_NONBIO+''')) nonbio_n,
  avg(identification_seconds) identification_mean,avg(voting_seconds) voting_mean,
  avg(pres_stage_seconds) stage_mean,avg(confirmation_gap_seconds) gap_mean
  FROM afternoon GROUP BY turn,uf,"second" ORDER BY turn,uf,"second"''')
 bands=event_bands(con)
 matched=records(con,'''SELECT a.anchor,a.uf,count(*) section_pairs,sum(a.post_n) first_post,sum(b.post_n) second_post,
    sum(a.total) first_ballots,sum(b.total) second_ballots
    FROM section_comparison a JOIN section_comparison b ON a.id=b.id AND a.anchor=b.anchor AND a.turn=1 AND b.turn=2
    JOIN section_metadata ma ON ma.turn=1 AND ma.id=a.id JOIN section_metadata mb ON mb.turn=2 AND mb.id=b.id
    WHERE ma.valid_sessions>=30 AND mb.valid_sessions>=30 GROUP BY a.anchor,a.uf ORDER BY a.anchor,a.uf''')
 con.execute('''CREATE OR REPLACE TABLE window_sections AS SELECT a.id anchor,e.turn,e.id,e.uf,
   count(*) FILTER(WHERE e.presidential_bsb<a.second)::BIGINT pre_n,
   count(*) FILTER(WHERE e.presidential_bsb>a.second)::BIGINT post_n,
   avg(identification_seconds) FILTER(WHERE e.presidential_bsb<a.second) identification_pre,
   avg(identification_seconds) FILTER(WHERE e.presidential_bsb>a.second) identification_post,
   avg(voting_seconds) FILTER(WHERE e.presidential_bsb<a.second) voting_pre,
   avg(voting_seconds) FILTER(WHERE e.presidential_bsb>a.second) voting_post
   FROM afternoon e CROSS JOIN anchors a WHERE e.presidential_bsb>=a.second-900 AND e.presidential_bsb<=a.second+900
   AND e.presidential_bsb<>a.second GROUP BY a.id,e.turn,e.id,e.uf''')
 con.execute('COPY window_sections TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(out/'documentary-window-sections.parquet')])
 # Fechamento administrativo é uma segunda contagem, com universo próprio.
 con.execute('CREATE OR REPLACE TEMP TABLE operations AS SELECT * FROM read_parquet(?)',[str(out/'operations-sections.parquet')])
 closings=records(con,'''SELECT a.id anchor,o.turn,o.uf,count(*) known_bu,
   count(*) FILTER(WHERE o.declared_close_bsb<=a.second) closed_at_or_before,
   count(*) FILTER(WHERE o.declared_close_bsb>a.second) declared_after,
   count(*) FILTER(WHERE o.timing_eligible) reconciled_protocols
   FROM operations o CROSS JOIN anchors a WHERE o.uf<>'zz' AND o.declared_close_bsb IS NOT NULL AND o.error IS NULL
   GROUP BY a.id,o.turn,o.uf ORDER BY a.id,o.turn,o.uf''')
 same_universe_status=records(con,"""SELECT s.anchor,s.turn,count(*) sections,
   count(*) FILTER(WHERE o.declared_close_bsb>s.cutoff) bu_after,
   count(*) FILTER(WHERE o.declared_close_bsb<=s.cutoff) bu_closed,
   count(*) FILTER(WHERE o.declared_close_bsb IS NULL) missing_close,
   count(*) FILTER(WHERE s.post_n>0) activity_after
   FROM section_comparison s LEFT JOIN operations o USING(turn,id) GROUP BY s.anchor,s.turn ORDER BY s.anchor,s.turn""")
 regional=[]
 for item in src['regional']:
  r=records(con,'''SELECT count(*) sections,sum(total) ballots,count(*) FILTER(WHERE declared_close_bsb<=?) closed_at_or_before,
     count(*) FILTER(WHERE declared_close_bsb>?) declared_after FROM operations WHERE turn=2 AND uf=? AND error IS NULL''',[item['second'],item['second'],item['uf']])[0]
  events=records(con,'''SELECT count(*) post_n,count(DISTINCT id) sections_with_post FROM afternoon WHERE turn=2 AND uf=? AND presidential_bsb>?''',[item['uf'],item['second']])[0]
  r.update(item);r.update(events);
  r['protocol_confirmed_at_or_before']=con.execute('SELECT count(*) FROM operations WHERE turn=2 AND uf=? AND procedure_confirmed_bsb<=?',[item['uf'],item['second']]).fetchone()[0];r['closed_percent']=100*r['closed_at_or_before']/r['sections'];regional.append(r)
 minute_sensitivity=records(con,"""SELECT turn,uf,count(*) FILTER(WHERE presidential_bsb>62280) after_minute_start,
   count(*) FILTER(WHERE presidential_bsb>62339) after_minute_end FROM afternoon GROUP BY turn,uf ORDER BY turn,uf""")
 correlations=[]
 for a in src['anchors']:
  for unit in ['uf','section']:
   rows=[r for r in by_state if r['anchor']==a['id'] and r['turn']==2] if unit=='uf' else records(con,"SELECT nonbio_rate,post_fraction FROM section_comparison WHERE anchor=? AND turn=2 AND total>=30",[a['id']])
   correlations.append(dict(anchor=a['id'],unit=unit,**corr(rows)))
 candidates={x['n']:int(x['vap']) for cargo in json.loads((ROOT/'data/raw/national.json').read_text())['carg'] if cargo['cd']=='1' for ag in cargo['agr'] for p in ag['par'] for x in p['cand']}
 con.execute('CREATE OR REPLACE TEMP TABLE core AS SELECT * FROM read_parquet(?)',[str(out/'1700-sections.parquet')])
 bounds=[]
 for a in src['anchors']:
  for code in ['13','22']:
   r=records(con,f'''SELECT count(*) known_sections,sum(c.v{code}) known_candidate,
      sum(greatest(0,c.v{code}-(s.total-s.post_n))) minimum,
      sum(least(c.v{code},s.post_n)) maximum_known
      FROM section_comparison s JOIN core c USING(id) WHERE s.turn=2 AND s.anchor=? AND c.hash_status='Totalizado' ''',[a['id']])[0]
   unknown=candidates[code]-int(r['known_candidate']);r.update(anchor=a['id'],candidate=code,unresolved_candidate=unknown,maximum=int(r['maximum_known'])+unknown);bounds.append(r)
 data=dict(sources=src,coverage=records(con,'SELECT turn,count(*) sections,sum(total) ballots,sum(valid_sessions) valid_sessions FROM section_metadata GROUP BY turn ORDER BY turn'),
   scan_start_seconds=57600,afternoon_records=records(con,'SELECT turn,count(*) n FROM afternoon GROUP BY turn ORDER BY turn'),national=national,by_state=by_state,
   communication_minute_sensitivity=minute_sensitivity,bands=bands,method_metrics=stats,equal_windows=windows,window_activity=window_activity,same_universe_status=same_universe_status,bins=bins,matched_states=matched,closings=closings,regional_communications=regional,correlations=correlations,candidate_post_bounds=bounds,
   verification=dict(partition_errors=bad,all_eligible_sessions_match_bu=True,profile_manifest_fingerprint=fp),
   interpretation='Marcos documentais e metadados não demonstram recebimento local ou efeito causal; a hora da assinatura permanece não verificada.')
 p=out/'documentary-analysis.json';p.with_suffix('.tmp').write_text(json.dumps(data,ensure_ascii=False,indent=2));p.with_suffix('.tmp').replace(p)
 con.close();print(json.dumps(dict(done=True,afternoon=data['afternoon_records'],national=national,regional=regional),ensure_ascii=False),flush=True)
if __name__=='__main__':run()
