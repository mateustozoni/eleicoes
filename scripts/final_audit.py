"""Auditoria integral de cobertura e recontagem, com universo explícito."""
import fcntl,hashlib,json,pathlib,sqlite3
from datetime import datetime,timezone
from analytics_store import open_store
ROOT=pathlib.Path(__file__).resolve().parents[1]
UFS='ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz'.split()
def run():
 with (ROOT/'output/.report.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);c=open_store()
  raw=set()
  for uf in UFS:
   with sqlite3.connect(str(ROOT/'data/raw'/(uf+'.sqlite'))) as db:raw.update(x[0] for x in db.execute("SELECT id FROM sections WHERE status='done'"))
  core=set(x[0] for x in c.execute('SELECT id FROM sections WHERE error IS NULL').fetchall())
  sets={}
  for turn in [1,2]:
   for table in ['timing_sections','operation_sections']:
    ids=set(x[0] for x in c.execute(f'SELECT id FROM {table} WHERE turn=?',[turn]).fetchall())
    sets[f'{table}_{turn}']=dict(n=len(ids),missing=sorted(raw-ids),extra=sorted(ids-raw))
  national=json.loads((ROOT/'data/raw/national.json').read_text())
  cand={x['n']:int(x['vap']) for cargo in national['carg'] if cargo['cd']=='1' for a in cargo['agr'] for p in a['par'] for x in p['cand']}
  reference=dict(total=int(national['v']['tv']),v13=cand['13'],v22=cand['22'],blank=int(national['v']['vb']),null=int(national['v']['tvn']))
  cur=c.execute('SELECT sum(total) total,sum(v13) v13,sum(v22) v22,sum(blank) blank,sum("null") AS null_votes FROM sections WHERE error IS NULL')
  recount=dict(zip([x[0] for x in cur.description],cur.fetchone()));recount['null']=recount.pop('null_votes')
  differences={k:recount[k]-v for k,v in reference.items()}
  first=json.loads((ROOT/'data/raw/first-turn-national.json').read_text())
  first_candidates={x['n']:int(x['vap']) for cargo in first['carg'] if cargo['cd']=='1' for ag in cargo['agr'] for party in ag['par'] for x in party['cand']}
  first_sum=c.execute('SELECT sum(total),sum(v13),sum(v22),sum(blank),sum("null"),sum(other_votes) FROM timing_sections WHERE turn=1').fetchone()
  first_expected=(int(first['v']['tv']),first_candidates['13'],first_candidates['22'],int(first['v']['vb']),int(first['v']['vn']),sum(v for k,v in first_candidates.items() if k not in ('13','22'))+int(first['v']['vnt']))
  type_audit=json.loads((ROOT/'output/first-turn-vote-type-audit.json').read_text())
  first_verified=first_sum==first_expected and type_audit['reconciled']
  invariant=c.execute('''SELECT count(*) FILTER(WHERE total<>v13+v22+blank+"null"),
    count(*) FILTER(WHERE time_eligible AND pre+at17+post<>total),
    count(*) FILTER(WHERE time_eligible AND pre1735+at1735+post1735<>total),
    count(*) FILTER(WHERE time_eligible AND (pre1735<pre OR post1735>post)),
    count(*) FILTER(WHERE time_eligible AND uf='zz') FROM sections''').fetchone()
  paired=c.execute('''SELECT count(*),count(*) FILTER(WHERE s.total<>t.total OR s.v13<>t.v13 OR s.v22<>t.v22 OR s.blank<>t.blank OR s."null"<>t."null")
       FROM sections s JOIN timing_sections t ON s.id=t.id AND t.turn=2''').fetchone()
  universes=c.execute("SELECT count(*) FILTER(WHERE s.time_eligible),count(*) FILTER(WHERE t.section_eligible),count(*) FILTER(WHERE s.time_eligible AND t.section_eligible),count(*) FILTER(WHERE s.time_eligible AND NOT t.section_eligible),count(*) FILTER(WHERE NOT s.time_eligible AND t.section_eligible) FROM sections s JOIN timing_sections t ON s.id=t.id AND t.turn=2 WHERE s.uf<>'zz'").fetchone()
  bc=c.execute('''WITH b AS (SELECT s.id,s.bu_bio,
    coalesce(sum(x.n) FILTER(WHERE x.kind='vote_elector_biometric'),0) votes_bio,
    coalesce(sum(x.n) FILTER(WHERE x.kind='enabled_elector_biometric'),0) enabled_bio
    FROM sections s,unnest(bins) u(x) WHERE s.time_eligible GROUP BY s.id,s.bu_bio)
    SELECT count(*) n,count(*) FILTER(WHERE bu_bio<>votes_bio) mismatch_vote,
    count(*) FILTER(WHERE bu_bio<>enabled_bio) mismatch_enable,
    sum(bu_bio) bu_bio,sum(votes_bio) votes_bio,sum(enabled_bio) enabled_bio FROM b''').fetchone()
  metadata=json.loads((ROOT/'output/metadata-status.json').read_text())
  audit=dict(updated_utc=datetime.now(timezone.utc).isoformat(),raw_published_sections=len(raw),core_sections=len(core),missing_core=sorted(raw-core),extra_core=sorted(core-raw),profiles=sets,
    first_turn_recount=dict(observed=first_sum,expected=first_expected,matches=first_verified,fields=['total','13','22','blank','raw_BU_type_nulo','remaining_including_code28'],classification_bridge=type_audit),
    reference=reference,recount=recount,differences=differences,invariants=dict(zip(['candidate_sum_errors','strict17_partition_errors','1735_partition_errors','cutoff_monotonicity_errors','overseas_in_domestic_timing'],invariant)),
    independent_profile_comparison=dict(pairs=paired[0],different=paired[1]),metadata=dict(state=metadata['state'],processed=metadata['processed'],confirmed=len(metadata['confirmed']),changed=metadata['changed'],errors=metadata['errors']),
    biometric_crosscheck=dict(zip(['sections','bu_vs_confirmation_differences','bu_vs_enablement_differences','bu_biometric','confirmation_biometric','enablement_biometric'],bc)),
    eligibility_crosswalk=dict(zip(['core_temporal','session_profiles','both','core_only','profiles_only'],universes)),
    official_reference_sha256=hashlib.sha256((ROOT/'data/raw/national.json').read_bytes()).hexdigest(),signature_verification=False,national_reference_check=json.loads((ROOT/'output/national-reference-check.json').read_text()))
  if (ROOT/'output/cutoff-1705-verification.json').exists():
   audit['active_cutoff_verification']=json.loads((ROOT/'output/cutoff-1705-verification.json').read_text())
  audit['passed']=(first_verified and audit['national_reference_check'].get('same_content') is True and raw==core and all(not v['missing'] and not v['extra'] for v in sets.values()) and not any(differences.values()) and not any(invariant) and paired==(len(raw),0))
  (ROOT/'output/final-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));c.close();print(json.dumps(audit,ensure_ascii=False))
  if not audit['passed']:raise SystemExit('Audit failed')
if __name__=='__main__':run()
