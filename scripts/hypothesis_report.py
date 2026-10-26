"""Testes diretos de interpretações frequentes, com resultados observados e limites de identificação."""
import json
import pathlib
import hashlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
PRODUCER_SHA=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()

def render(con,table,fmt):
    national=json.loads((ROOT/'data/raw/national.json').read_text())
    candidates={c['n']:int(c['vap']) for cargo in national['carg'] if cargo['cd']=='1' for a in cargo['agr'] for p in a['par'] for c in p['cand']}
    margin=candidates['13']-candidates['22']
    r=con.execute('''SELECT count(*) n,
       count(*) FILTER(WHERE closing_bsb>61200) closing_after17,
       count(*) FILTER(WHERE s.post>0) voting_after17,
       count(*) FILTER(WHERE closing_bsb>61200 AND s.post=0) late_close_without_late_vote,
       count(*) FILTER(WHERE closing_bsb>61500) closing_after1705,
       count(*) FILTER(WHERE s.post1705>0) voting_after1705,
       count(*) FILTER(WHERE closing_bsb>61500 AND s.post1705=0) later_close_without_later_vote,
       coalesce(sum(s.pre),0) pre17,coalesce(sum(s.post),0) post17,
       coalesce(sum(s.post1705),0) post1705
       FROM bu_hours h JOIN sections s USING(id) WHERE s.time_eligible AND s.uf<>'zz' AND closing_bsb IS NOT NULL''').fetchone()
    names=['n','closing_after17','voting_after17','late_close_without_late_vote','closing_after1705','voting_after1705','later_close_without_later_vote','pre17','post17','post1705']
    data=dict(zip(names,r));outside_upper=int(national['v']['tv'])-data['pre17']
    provisional=con.execute("SELECT count(*) FROM good WHERE time_eligible AND coalesce(hash_status,'')<>'Totalizado'").fetchone()[0]
    data['provisional_temporal_sections']=provisional
    data.update(official_margin=margin,outside_known_pre17_upper=outside_upper,winner_survives_extreme_removal=(margin>outside_upper),remaining_margin_lower=margin-outside_upper)
    (ROOT/'output/hypothesis-checks.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    rows=[
      ('“BU encerrado depois de 17h significa voto recebido depois de 17h”',
       f'{fmt(data["late_close_without_late_vote"])} seções têm encerramento posterior e nenhum evento presidencial posterior no corpus conciliado.',
       'A equivalência é refutada por esses casos; horário de encerramento e horário do voto medem eventos distintos.'),
      ('“A margem de 5 minutos isola apenas impressão ou rotina administrativa”',
       f'{fmt(data["later_close_without_later_vote"])} seções também fecham depois de 17h05 sem evento presidencial posterior a esse corte.',
       'O corte é análise de sensibilidade. O protocolo e a impressão devem ser medidos diretamente, sem reclassificar o horário dos votos.'),
      ('“A região com mais votos tardios cresceu por causa da prorrogação”',
       'Há comparação das mesmas seções, variação de comparecimento e decomposição antes/depois de 17h.',
       'A associação não identifica o efeito causal; chegada, comunicação da ordem e preferência de abstentes não são observadas.'),
      ('“O candidato que ganhou nas seções tardias ganhou os votos tardios”',
       'O BU informa o resultado de todas as horas, e o log não contém a escolha de candidato.',
       'A inferência é ecológica. São usados limites matemáticos e exemplos de alocações compatíveis, sem atribuição por horário.'),
      ('“Um desvio de contagem ou relógio prova voto irregular”',
       'Os dossiês distinguem sistemas de apuração, logs de outra seção, retomadas e regressões de relógio.',
       'É necessária explicação por evidência. O sinalizador não é uma conclusão automática sobre validade dos votos.'),
      ('“Há um resultado único observável para a isonomia de horário”',
       'Os cenários variam demanda realizada, ritmo e composição hipotética dos adicionais.',
       'O resultado depende de hipóteses não identificadas pelos logs. A faixa de possibilidades é mostrada separadamente dos fatos.')]
    proof=''
    if data['winner_survives_extreme_removal']:
        caveat=(f'<p><strong>Condição deste teste:</strong> o corpus temporal contém {fmt(provisional)} BUs cujo auxiliar ainda não confirmou Totalizado. O cálculo supõe que os BUs preservados correspondem aos votos da referência nacional, cuja soma confere. Essa condição não é substituída pela igualdade agregada; os limites por candidato abaixo exigem metadado Totalizado e podem ser mais largos.</p>' if provisional else '')
        proof=caveat+(f'<p>Teste conservador nos registros: a diferença oficial é {fmt(margin)} votos. Mesmo tratando todos os {fmt(outside_upper)} votos fora do conjunto conhecido anterior às 17h '
          f'— inclusive tempos desconhecidos e exterior — como votos do 13 a serem retirados, a diferença residual seria de pelo menos {fmt(data["remaining_margin_lower"])}.</p>'
          '<p>Isso é robustez aritmética de um subconjunto, não proposta de invalidar votos e nem reconstrução de uma eleição sem prorrogação. Quem já estava na fila também pode votar depois do horário. '
          'O teste tampouco responde ao que ocorreria com pessoas que não votaram e poderiam comparecer em outro cenário.</p>')
    else:
        proof='<p>A cobertura e os limites atuais ainda não permitem certificar a robustez por esse limite bruto. Os limites por candidato e a cobertura continuam explícitos.</p>'
    return ('<section id="suposicoes"><h2>Suposições confrontadas com os dados</h2>'+table(['Suposição','Evidência disponível','Interpretação'],rows)+
        '<h3>Fechamento e votos efetivamente registrados</h3>'+table(['Corte','Seções com fechamento posterior','Seções com voto posterior','Fechamento posterior sem voto posterior'],[
          ('17h',fmt(data['closing_after17']),fmt(data['voting_after17']),fmt(data['late_close_without_late_vote'])),
          ('17h05',fmt(data['closing_after1705']),fmt(data['voting_after1705']),fmt(data['later_close_without_later_vote']))])+
        '<h3>Robustez de placar e oportunidade de acesso</h3>'+proof+
        '<p>Uma margem eleitoral mede o placar. A distribuição de oportunidades exige considerar horários, capacidade, barreiras e quem não chegou ao registro. As duas perguntas são analisadas separadamente.</p>'
        '<p><a href="hypothesis-checks.json">Números e limites usados neste confronto</a>.</p></section>')
