import pathlib
import unittest
from timing_profiles import sessions,profile,process_batch
import tempfile
from synthetic_fixtures import synthetic_bu,synthetic_log
import pyarrow.parquet as pq

ROOT=pathlib.Path(__file__).resolve().parents[1]

def rows(events):
    return [[f'25/10/2026 {t}','INFO','02260684','VOTA',message,f'{i:016X}'] for i,(t,message) in enumerate(events)]

class TimingTests(unittest.TestCase):
    def test_distinct_identification_voting_stage_and_inter_person_intervals(self):
        r,d=sessions(rows([('08:00:00','Identificador do eleitor digitado pelo mesário'),
            ('08:00:10','Tipo de habilitação do eleitor [biométrica]'),('08:00:11','Eleitor foi habilitado'),
            ('08:01:00','Voto confirmado para [Governador]'),('08:01:30','Voto confirmado para [Presidente]'),
            ('08:01:31','O voto do eleitor foi computado'),('08:01:40','Identificador do eleitor digitado pelo mesário'),
            ('08:01:48','Eleitor foi habilitado'),('08:02:30','Voto confirmado para [Presidente]'),
            ('08:02:31','O voto do eleitor foi computado')]),2,'sp/71072/0001/0001','SÃO PAULO','logd.dat','test')
        self.assertEqual(len(r),2)
        self.assertEqual((r[0]['identification_seconds'],r[0]['voting_seconds'],r[0]['pres_stage_seconds'],r[0]['session_seconds']),(11,79,30,80))
        self.assertEqual((r[1]['confirmation_gap_seconds'],r[1]['activation_gap_seconds']),(60,17))
        self.assertEqual(r[0]['auth_kind'],'elector_biometric')
        self.assertTrue(all(x['valid_timing'] for x in r))

    def test_restart_does_not_turn_an_uncompleted_confirmation_into_a_completed_session(self):
        r,d=sessions(rows([('08:00:00','Eleitor foi habilitado'),('08:00:30','Voto confirmado para [Presidente]'),
            ('08:05:00','Iniciando aplicação - 2º turno'),('08:06:00','Eleitor foi habilitado'),
            ('08:06:30','Voto confirmado para [Presidente]'),('08:06:31','O voto do eleitor foi computado')]),
            2,'sp/71072/0001/0001','SÃO PAULO','logd.dat','test')
        self.assertFalse(r[0]['completed']);self.assertFalse(r[0]['valid_timing'])
        self.assertTrue(r[1]['completed']);self.assertEqual(d['computed_messages'],1)

    def test_negative_clock_spans_are_not_repaired_by_sorting(self):
        r,d=sessions(rows([('08:10:00','Eleitor foi habilitado'),('08:09:00','Voto confirmado para [Presidente]'),
            ('08:09:01','O voto do eleitor foi computado')]),2,'sp/71072/0001/0001','SÃO PAULO','logd.dat','test')
        self.assertEqual(d['clock_regressions'],1)
        self.assertFalse(any(x['valid_timing'] for x in r))

    def test_synthetic_bu_and_parquet_publication(self):
        item=(2,'ac/01074/0004/0001','CRUZEIRO DO SUL',
            synthetic_bu(),
            [synthetic_log()],'TSE sample')
        m,records,h=profile(item)
        self.assertEqual((m['total'],m['presidential_markers'],m['completed_presidential_sessions']),(202,202,202))
        self.assertTrue(m['section_eligible']);self.assertEqual(len(records),202)
        with tempfile.TemporaryDirectory() as directory:
            result=process_batch([item],directory)
            self.assertEqual(result['sections'],1)
            self.assertEqual(pq.read_table(pathlib.Path(directory)/'events.parquet').num_rows,202)

if __name__=='__main__':unittest.main()
