import unittest,duckdb
from documentary_sources import minimum_judges
from documentary_analysis import event_bands
class DocumentaryTests(unittest.TestCase):
 def test_minimum_does_not_treat_approximate_or_missing_hour_as_explicit(self):
  rows=[dict(uf='mg',second=57600,explicit_minute=False),dict(uf='zz',second=None,explicit_minute=True),dict(uf='sp',second=62280,explicit_minute=True),dict(uf='to',second=64800,explicit_minute=True)]
  self.assertEqual(minimum_judges(rows)['uf'],'sp')
  self.assertIsNone(minimum_judges(rows[:2]))
 def test_exact_marco_is_excluded_and_all_posterior_bands_partition(self):
  c=duckdb.connect();c.execute('CREATE TABLE afternoon(turn INTEGER,presidential_bsb INTEGER)');c.execute('CREATE TABLE anchors(id VARCHAR,second INTEGER)')
  c.executemany('INSERT INTO afternoon VALUES (2,?)',[(v,) for v in [59568,59569,59570,61199,61200,61500,61501,62280,62281]])
  c.executemany('INSERT INTO anchors VALUES (?,?)',[('recebimento',59569),('criacao_pdf',61307),('juizes_sp',62280)])
  rows={r['anchor']:r for r in event_bands(c)};c.close()
  self.assertEqual((rows['recebimento']['post_n'],rows['recebimento']['post_before17'],rows['recebimento']['post_17_to_1705'],rows['recebimento']['post_after1705']),(7,2,2,3))
  self.assertEqual(rows['criacao_pdf']['post_n'],4)
  self.assertEqual(rows['juizes_sp']['post_n'],1)
if __name__=='__main__':unittest.main()
