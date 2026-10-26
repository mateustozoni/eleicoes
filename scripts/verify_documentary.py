"""Conferências independentes do extra contra bins centrais e invariantes das sessões."""
import json,pathlib,duckdb
from documentary_sources import minimum_judges
ROOT=pathlib.Path(__file__).resolve().parents[1]
def run():
 d=json.loads((ROOT/'output/documentary-analysis.json').read_text());src=d['sources'];assert not src['average_used'] and not src['signature_time_verified']
 assert minimum_judges(src['regional'])['uf']=='sp'
 assert all(r['pre_n']+r['at_n']+r['post_n']==r['ballots'] for r in d['national'])
 assert all(r['post_n']==r['bio_post']+r['nonbio_post']+r['unknown_post'] for r in d['national'])
 assert all(r['post_n']==r['post_before17']+r['post_17_to_1705']+r['post_after1705'] for r in d['bands'])
 c=duckdb.connect();checks=[]
 for a in src['anchors']:
  floor=a['second']//300*300;ceil=floor+300
  low,high=c.execute('''SELECT sum(x.n) FILTER(WHERE x.second>=?),sum(x.n) FILTER(WHERE x.second>=?)
    FROM read_parquet(?) s,unnest(bins) u(x) WHERE s.time_eligible AND x.kind='vote' ''',[ceil,floor,str(ROOT/'output/1700-sections.parquet')]).fetchone()
  n=next(r['post_n'] for r in d['national'] if r['turn']==2 and r['anchor']==a['id']);assert low<=n<=high,(a,low,n,high)
  checks.append(dict(anchor=a['id'],coarse_lower=low,exact_post=n,coarse_upper=high))
 assert len(d['same_universe_status'])==6
 assert all(r['bu_after']+r['bu_closed']+r['missing_close']==r['sections'] for r in d['same_universe_status'])
 meta=json.loads((ROOT/'docs/stf-20261025/pdf-metadata.json').read_text());assert meta['creation_time_brasilia']=='17:01:47'
 result=dict(passed=True,signature_time_verified=False,average_used=False,minimum_judges_uf='sp',minimum_judges_seconds=62280,
   partition_errors=d['verification']['partition_errors'],independent_core_bin_brackets=checks,regional_hours_available=len(src['regional']),coverage_is_not_national_census=True)
 (ROOT/'output/documentary-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':run()
