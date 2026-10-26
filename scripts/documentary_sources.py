"""Marcos documentais: natureza e precisão preservadas, sem inferir hora de assinatura."""
import json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
PDF='https://noticias-stf-wp-prd.s3.sa-east-1.amazonaws.com/wp-content/uploads/wpallimport/uploads/2026/10/25183103/liminar-urgente.pdf'
SP='https://www.tre-sp.jus.br/comunicacao/noticias/2026/Outubro/comunicado-oficial-tre-sp-1'
MG='https://www.tre-mg.jus.br/comunicacao/noticias/2026/Outubro/minas-gerais-teve-votacao-tranquila-no-2o-turno-das-eleicoes-2026'
TO='https://agora-to.com.br/tre-to-cumpre-determinacao-de-ampliar-votacao-ate-19h/'
def minimum_judges(regional):
    exact=[r for r in regional if r.get('explicit_minute') and r.get('second') is not None]
    if not exact:return None
    return min(exact,key=lambda r:r['second'])

def sources():
 return dict(date='2026-10-25',timezone='America/Sao_Paulo',signature_time_verified=False,choice='earliest_documented_explicit_judges_notification_not_national_first',average_used=False,
  anchors=[dict(id='recebimento',second=59569,label='16h32min49s · fatos recebidos no STF',kind='recebimento_dos_fatos',scope='br',precision='segundo registrado no texto',source=PDF,note='Não é a hora de assinatura ou publicação.'),
   dict(id='criacao_pdf',second=61307,label='17h01min47s · criação do PDF',kind='metadado_do_arquivo',scope='br',precision='segundo nos metadados',source=PDF,note='Metadado da cópia publicada; não certifica assinatura nem ciência das mesas.'),
   dict(id='juizes_sp',second=62280,label='17h18 · comunicação aos juízes de SP',kind='comunicacao_aos_juizes',scope='sp',precision='minuto informado pelo TRE-SP',source=SP,note='Menor horário explícito localizado; não comprova o primeiro horário nacional nem recebimento simultâneo por cada juiz ou mesa.')],
  regional=[dict(uf='sp',second=62280,label='17h18',precision='minuto explícito',source=SP,source_type='fonte primária oficial',explicit_minute=True),
   dict(uf='mg',second=64800,label='por volta de 18h',precision='aproximado; orientação imediatamente após recebimento por volta de 18h',source=MG,source_type='fonte primária oficial',explicit_minute=False),
   dict(uf='to',second=64800,label='18h',precision='minuto informado em nota atribuída ao TRE-TO',source=TO,source_type='nota reproduzida pela imprensa; página original não localizada',explicit_minute=True)],
  additional=[dict(uf='sp',time='17h16',event='confirmação por telefone com o TSE',source=SP),dict(uf='sp',time='18h16',event='recebimento de e-mail do TSE',source=SP),
   dict(uf='mg',time='18h26 e 18h28',event='assinaturas do ofício regional; não são horários de ciência dos juízes',source='https://www.tre-mg.jus.br/comunicacao/noticias/arquivos/oficio-circular-no-59-2026-pre')],
  missing_hours=dict(uf='sc',source='https://www.tre-sc.jus.br/comunicacao/noticias/2026/Outubro/nota-de-esclarecimento',note='Afirma comunicação aos juízes sem informar horário; não entra na seleção do mínimo.'),
  search_coverage_note='Pesquisa em fontes oficiais e reproduções documentais; não é censo das 27 UFs. Ausência de horário encontrado não significa ausência de comunicação.')
if __name__=='__main__':
 p=ROOT/'docs/stf-20261025/documentary-sources.json';p.write_text(json.dumps(sources(),ensure_ascii=False,indent=2));print(p)
