import pathlib,tempfile,unittest
import duckdb,pyarrow as pa,pyarrow.parquet as pq
from recut_1705 import late_method_stats
from timing_report import recognition_summary
class LateMethodTests(unittest.TestCase):
 def test_cohort_uses_confirmation_strictly_after_cut_and_eligible_durations(self):
  rows=[]
  for kind,pres,seconds,section_ok,timing_ok in [
   ('elector_biometric',61501,10,True,True),('elector_biometric',61600,30,True,True),
   ('elector_biometric',61500,900,True,True),('elector_biometric',61499,900,True,True),
   ('elector_biometric',61502,900,False,True),('elector_biometric',61503,900,True,False),
   ('elector_biometric',61504,None,True,True),('no_elector_biometric',61505,40,True,True)]:
   rows.append(dict(auth_kind=kind,presidential_bsb=pres,enabled_bsb=61400,identification_seconds=seconds,section_eligible=section_ok,valid_timing=timing_ok))
  with tempfile.TemporaryDirectory() as folder:
   path=pathlib.Path(folder)/'events.parquet';pq.write_table(pa.Table.from_pylist(rows),path)
   c=duckdb.connect();result={r['auth_kind']:r for r in late_method_stats(c,[str(path)])};c.close()
  self.assertEqual(result['elector_biometric']['n'],2)
  self.assertEqual(result['elector_biometric']['mean'],20)
  self.assertEqual(result['elector_biometric']['median'],20)
  self.assertAlmostEqual(result['elector_biometric']['p90'],28)
  self.assertEqual(result['no_elector_biometric']['n'],1)
  self.assertEqual(result['no_elector_biometric']['mean'],40)
 def test_nonbiometric_summary_weights_records_and_excludes_unknown(self):
  rows=[dict(turn=2,auth_kind=kind,n=n,mean=mean) for kind,n,mean in [
   ('elector_biometric',100,10),('no_elector_biometric',1,20),
   ('pollworker_biometric',3,100),('unknown',1,999)]]
  result={r['recognition']:r for r in recognition_summary(rows)}
  nonbio=result['Sem reconhecimento biométrico do eleitor']
  self.assertEqual(nonbio['n'],4);self.assertEqual(nonbio['mean'],80)
  self.assertEqual(result['Digital do eleitor reconhecida']['mean'],10)
if __name__=='__main__':unittest.main()
