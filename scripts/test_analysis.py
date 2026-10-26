import io
import pathlib
import unittest
import zipfile
from analyze import process, offset
from collect import select_hash
from correlations import phi,coefficient
from vote_bounds import interval
import itertools
from synthetic_fixtures import synthetic_bu,synthetic_log

ROOT=pathlib.Path(__file__).resolve().parents[1]

def packed(text):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('logd.dat',text.encode('latin1'))
    return b.getvalue()

def lines(events):
    return '\n'.join(f'25/10/2026 {t}\tINFO\t02260684\tVOTA\t{m}\t{i:016X}' for i,(t,m) in enumerate(events))

class AnalysisTests(unittest.TestCase):
    def item(self,b,uf='ac'):
        # Synthetic BU and logs: tests never require downloaded election files.
        return ('ac/01074/0004/0001','CRUZEIRO DO SUL',
            synthetic_bu(),[b],'test','Totalizado')

    def test_synthetic_bu_reconciles(self):
        r=process(self.item(synthetic_log()))
        self.assertTrue(r['match']);self.assertEqual(r['total'],202)
        self.assertEqual(r['pre']+r['at17']+r['post'],202)

    def test_timezone_and_exact_cut(self):
        r=process(self.item(packed(lines([('14:59:59','Voto confirmado para [Presidente]'),
            ('15:00:00','Voto confirmado para [Presidente]'),('15:00:01','Voto confirmado para [Presidente]')]))))
        self.assertEqual((r['pre'],r['at17'],r['post']),(1,1,1))
        self.assertEqual(sum(x['n'] for x in r['auth_cuts']),3)
        self.assertEqual(offset('am','AMATURÁ'),2)
        self.assertEqual(offset('am','BOCA DO ACRE'),1)
        self.assertEqual(offset('pe','FERNANDO DE NORONHA'),-1)
        self.assertIsNone(offset('zz','LISBOA'))

    def test_auth_fingerprint_not_counted_as_elector_biometric(self):
        r=process(self.item(packed(lines([('14:00:00','Solicitação de dado pessoal do eleitor para habilitação manual'),
            ('14:00:01','Capturada a digital do mesário'),('14:00:02','Eleitor foi habilitado'),
            ('14:00:10','Voto confirmado para [Presidente]')]))))
        kinds={x['kind']:x['n'] for x in r['bins']}
        self.assertEqual(kinds['vote_pollworker_captured_fingerprint'],1)
        self.assertNotIn('vote_elector_biometric',kinds)

    def test_operational_margin_keeps_vote_timestamp_and_exact_boundary(self):
        r=process(self.item(packed(lines([('15:20:00','Voto confirmado para [Presidente]'),
            ('15:35:00','Voto confirmado para [Presidente]'),('15:35:01','Voto confirmado para [Presidente]')]))))
        # Acre local +2h: 17:20, 17:35, 17:35:01 in Brasília.
        self.assertEqual(r['post'],3)
        self.assertEqual((r['pre1735'],r['at1735'],r['post1735']),(1,1,1))
        self.assertEqual(sum(x['n'] for x in r['auth_cuts1735']),3)

    def test_1705_exact_second_and_brasilia_offset(self):
        r=process(self.item(packed(lines([('15:04:59','Voto confirmado para [Presidente]'),
            ('15:05:00','Voto confirmado para [Presidente]'),('15:05:01','Voto confirmado para [Presidente]')]))),additional_cutoff=61500)
        c=r['additional_cutoff']
        self.assertEqual((c['pre'],c['at17'],c['post']),(1,1,1))
        self.assertEqual(sum(x['n'] for x in c['auth_cuts']),3)
        self.assertEqual((r['pre1735'],r['at1735'],r['post1735']),(3,0,0))

    def test_cancelled_enablement_does_not_produce_vote(self):
        r=process(self.item(packed(lines([('14:00:00','Tipo de habilitação do eleitor [biométrica]'),
            ('14:00:01','Eleitor foi habilitado'),('14:00:02','Eleitor foi suspenso e não confirmou nenhum voto')]))))
        self.assertEqual(r['log_votes'],0)

    def test_nested_duplicate_logs_count_once(self):
        t=lines([('14:00:00','Voto confirmado para [Presidente]')]);b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('logd.dat',t.encode('latin1'));z.writestr('archive.jez',packed(t))
        r=process(self.item(b.getvalue()));self.assertEqual(r['log_votes'],1)

    def test_archived_foreign_section_is_not_added_to_current_bu(self):
        t=lines([('07:00:00','Município: 01074'),('07:00:01','Zona Eleitoral: 0004'),
            ('07:00:02','Seção Eleitoral: 0002'),('08:00:00','Voto confirmado para [Presidente]'),
            ('08:00:01','Seção Eleitoral: 0001'),('08:00:02','Voto confirmado para [Presidente]')])
        r=process(self.item(packed(t)))
        self.assertEqual(r['raw_log_votes'],2)
        self.assertEqual(r['foreign_section_events'],1)
        self.assertEqual(r['log_votes'],1)

    def test_clock_regression_excludes_temporal_series(self):
        r=process(self.item(packed(lines([('14:01:00','Eleitor foi habilitado'),('14:00:00','Voto confirmado para [Presidente]')]))))
        self.assertEqual(r['clock_backwards'],1);self.assertFalse(r['time_eligible'])

    def test_hash_selection_never_adds_rejected_version(self):
        h=select_hash({'hashes':[{'st':'Rejeitado','hash':'old'},{'st':'Totalizado','hash':'final'}]})
        self.assertEqual(h['hash'],'final')
        with self.assertRaises(ValueError): select_hash({'hashes':[{'st':'Recebido'},{'st':'Recebido'}]})

    def test_correlations_and_degenerate_margins(self):
        self.assertAlmostEqual(phi(20,0,0,20),1)
        self.assertAlmostEqual(phi(0,20,20,0),-1)
        self.assertIsNone(phi(0,0,10,20))
        r=coefficient([dict(late_rate=x,nonbio_rate=x) for x in [.1,.2,.3]])
        self.assertAlmostEqual(r['pearson'],1)
        self.assertAlmostEqual(r['spearman'],1)

    def test_candidate_time_bounds_enclose_all_possible_assignments(self):
        for total in range(1,7):
            for candidate in range(total+1):
                for period in range(total+1):
                    assignments=[sum(i<candidate for i in subset) for subset in itertools.combinations(range(total),period)]
                    self.assertEqual(interval(candidate,total,period),(min(assignments),max(assignments)))

if __name__=='__main__':unittest.main()
