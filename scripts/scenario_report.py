"""Cenários explícitos de adição de participação; não identificam o efeito causal da prorrogação."""
import html
import json
import math
import pathlib
import hashlib
import collections
import numpy as np
from profile_store import exists as profiles_exist

ROOT=pathlib.Path(__file__).resolve().parents[1]
PRODUCER_SHA=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()

def rec(con,sql,params=None):
    c=con.execute(sql,params or []);return [dict(zip([x[0] for x in c.description],r)) for r in c.fetchall()]

def candidates(data):return {c['n']:int(c['vap']) for cargo in data['carg'] if cargo['cd']=='1' for a in cargo['agr'] for p in a['par'] for c in p['cand']}

def new_margin(margin,nominal_extra,share13):return margin+nominal_extra*(2*share13-1)

def capacity(stock,window_seconds,seconds_per_session):
    if stock<0 or window_seconds<0 or seconds_per_session<=0:raise ValueError('Invalid hypothetical capacity inputs')
    return min(stock,math.floor(window_seconds/seconds_per_session))

def sensitivity_plot(margin,max_extra):
    if max_extra<=0:return '<p>Estoque ainda indisponível na cobertura atual.</p>'
    x=lambda n:75+800*n/max_extra;y=lambda p:350-280*p
    out=['<svg viewBox="0 0 1020 430" role="img" aria-label="Sensibilidade do resultado a novos votos nominais e à preferência assumida">']
    for ix in range(40):
        n=max_extra*(ix+.5)/40
        for iy in range(40):
            p=(iy+.5)/40;delta=new_margin(margin,n,p);scale=min(1,abs(delta)/max(1,abs(margin)))
            target=(12,110,113) if delta>=0 else (137,72,130);color=tuple(round(a+(b-a)*scale) for a,b in zip((245,246,248),target))
            out.append(f'<rect x="{75+ix*20}" y="{350-(iy+1)*7}" width="20.1" height="7.1" fill="rgb{color}"><title>Votos adicionais {n:,.0f}; 13 entre adicionais {p*100:.1f}%; diferença final 13−22 = {delta:,.0f}</title></rect>')
    path=[]
    for i in range(1,201):
        n=max_extra*i/200;p=(1-margin/n)/2
        if 0<=p<=1:path.append(f'{"M" if not path else "L"}{x(n):.2f},{y(p):.2f}')
    out.append('<path d="'+' '.join(path)+'" fill="none" stroke="#182b3b" stroke-width="2"/>')
    for i in range(5):
        out.append(f'<text x="{x(max_extra*i/4):.1f}" y="375" text-anchor="middle">{max_extra*i/4/1e6:.1f} mi</text><text x="62" y="{y(i/4)+4:.1f}" text-anchor="end">{i*25}%</text>')
    out.append('<text x="470" y="408" text-anchor="middle">Novos votos nominais hipotéticos, mantendo os votos realizados</text><text transform="translate(18,210) rotate(-90)" text-anchor="middle">Parcela dos adicionais atribuída ao 13</text></svg>')
    return ''.join(out)+'<p class="muted">Verde: diferença favorável ao 13; roxo: favorável ao 22. A linha é o empate matemático. As cores são cenários, não resultados observados nem probabilidades.</p>'

def allocation_example(con,table,fmt):
    r=con.execute('''SELECT id,name,total,v13,v22,post FROM sections WHERE time_eligible AND uf<>'zz'
        AND post>0 AND v13>=post AND v22>=post ORDER BY post DESC LIMIT 1''').fetchone()
    if not r:return ''
    key,name,total,c13,c22,late=r
    return ('<h3>Por que o resultado diário não identifica o candidato no horário</h3><p>Exemplo real de seção: '+html.escape(key+' · '+name)+
        f'. O BU tem {fmt(c13)} votos no 13 e {fmt(c22)} no 22; o log registra {fmt(late)} confirmações depois de 17h. '
        'Como ambos têm votos suficientes no total diário, as duas alocações abaixo são matematicamente compatíveis com esses totais e horários. Não são reconstruções de pessoas nem afirmações sobre o que ocorreu.</p>'+
        table(['Alocação possível, não observada','13 depois de 17h','22 depois de 17h'],[('Extremo A',fmt(late),'0'),('Extremo B','0',fmt(late))])+
        '<p>Assim, atribuir a proporção diária da seção aos eleitores tardios acrescentaria uma hipótese. Os limites matemáticos do relatório preservam essa incerteza.</p>')

def render(con,table,fmt):
    if not profiles_exist(con):return '<section id="isonomia"><h2>Isonomia · cenários e hipóteses</h2><p>A comparação depende dos perfis dos dois turnos, ainda em processamento.</p></section>'
    fp=dict(core=list(con.execute('SELECT count(*),sum(size) FROM ingested_files').fetchone()),
        profiles=list(con.execute('SELECT count(*),sum(sections),sum(events) FROM profile_batches').fetchone()),
        operations=list(con.execute('SELECT count(*),sum(sections) FROM operation_batches').fetchone()) if con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='operation_batches'").fetchone()[0] else None,
        periods=con.execute('SELECT count(*) FROM timing_period_batches').fetchone()[0],code=PRODUCER_SHA)
    cache=ROOT/'output/scenario-fragment.html';cm=ROOT/'output/scenario-fragment-meta.json'
    if cache.exists() and cm.exists() and json.loads(cm.read_text())==fp:return cache.read_text()
    national=json.loads((ROOT/'data/raw/national.json').read_text());first=json.loads((ROOT/'data/raw/first-turn-national.json').read_text())
    c=candidates(national);f=candidates(first);margin=c['13']-c['22'];p_global=c['13']/(c['13']+c['22']);p_first=f['13']/(f['13']+f['22'])
    operation_exists=con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='operation_sections'").fetchone()[0]
    if operation_exists:
        op_join='LEFT JOIN operation_sections o ON o.id=s.id AND o.turn=2'
        op_fields='o.protocol_start_bsb,o.start_after_last_vote,o.procedure_matches_bu,o.single_confirmation'
    else:op_join='';op_fields='NULL::BIGINT protocol_start_bsb,false start_after_last_vote,false procedure_matches_bu,false single_confirmation'
    rows=rec(con,'''SELECT s.id,s.uf,s.name,s.aptos_president aptos,s.total,s.v13,s.v22,
        date_diff('second',TIMESTAMP '2026-10-25 00:00:00',try_strptime(s.closing_local,'%Y%m%dT%H%M%S'))+s.offset_hours*3600 closing_bsb,
        t.active_confirmation_gap_seconds_n rate_n,t.active_confirmation_gap_seconds_mean rate_mean,
        t.active_confirmation_gap_seconds_median rate_median,t.section_eligible,
        fl.last_presidential_bsb,a.v13 first13,a.v22 first22,'''+op_fields+'''
        FROM sections s LEFT JOIN timing_sections t ON t.id=s.id AND t.turn=2
        LEFT JOIN timing_flows fl ON fl.id=s.id AND fl.turn=2
        LEFT JOIN timing_sections a ON a.id=s.id AND a.turn=1 '''+op_join+'''
        WHERE s.error IS NULL AND s.uf<>'zz' AND s.aptos_president IS NOT NULL AND s.total<=s.aptos_president''')
    refs={}
    sample=ROOT/'output/reference-calibration.json'
    if sample.exists():
        for r in json.loads(sample.read_text())['states']:
            if r.get('sufficient'):refs[r['uf']]=dict(seconds=r['p95_seconds'],basis='amostra de 200 seções')
    if operation_exists:
        for r in rec(con,'''SELECT uf,count(*) all_rows,count(*) FILTER(WHERE timing_eligible AND deadline_tail_seconds>=0) AS eligible_count,
           quantile_cont(deadline_tail_seconds,.95) FILTER(WHERE timing_eligible AND deadline_tail_seconds>=0) p95
           FROM operation_sections WHERE turn=1 AND uf<>'zz' GROUP BY uf'''):
            frame=ROOT/'data/timing/v1/frames'/(r['uf']+'.json')
            expected=len(json.loads(frame.read_text())) if frame.exists() else None
            if expected and r['all_rows']==expected and r['eligible_count']>=100 and r['eligible_count']>=.8*expected:
                refs[r['uf']]=dict(seconds=r['p95'],basis='base integral da UF, registros válidos')
    stock=sum(r['aptos']-r['total'] for r in rows);covered=len(rows);eligible=[];unknown_stock=0
    for r in rows:
        r['stock']=r['aptos']-r['total']
        valid=bool(r['section_eligible'] and r['rate_n'] is not None and r['rate_n']>=30 and r['rate_median'] is not None and r['rate_median']>0 and r['rate_mean'] is not None and r['rate_mean']>0 and r['closing_bsb'] is not None and r['last_presidential_bsb'] is not None and r['closing_bsb']>=r['last_presidential_bsb'])
        if not valid:unknown_stock+=r['stock'];continue
        r['p2']=r['v13']/(r['v13']+r['v22']) if r['v13']+r['v22'] else p_global
        r['valid_fraction']=(r['v13']+r['v22'])/r['total'] if r['total'] else 0
        r['p1']=r['first13']/(r['first13']+r['first22']) if r['first13'] is not None and r['first22'] is not None and r['first13']+r['first22'] else p_first
        technical=max(61200,r['closing_bsb'])
        observed=max(61200,r['protocol_start_bsb']) if r['single_confirmation'] and r['start_after_last_vote'] and r['procedure_matches_bu'] and r['protocol_start_bsb'] is not None else technical
        calibrated=max(61200,r['last_presidential_bsb'],r['closing_bsb']-refs.get(r['uf'],dict(seconds=0))['seconds'])
        r['windows']={name:max(0,68400-v) for name,v in [('technical',technical),('protocol',observed),('reference',calibrated)]}
        eligible.append(r)
    results=[];by_state=[]
    window_names={'technical':'Desde o encerramento declarado','protocol':'Desde o início final de protocolo observado','reference':'Com cauda de referência estadual do 1º turno'}
    for window in window_names:
        for pace in ['median','mean']:
            total_capacity=0;valid_capacity=0;delta_local2=0;delta_local1=0;state=collections.defaultdict(lambda:dict(capacity=0,stock=0,sections=0))
            for r in eligible:
                cap=capacity(r['stock'],r['windows'][window],r['rate_'+pace]);nominal=cap*r['valid_fraction']
                total_capacity+=cap;valid_capacity+=nominal;delta_local2+=nominal*(2*r['p2']-1);delta_local1+=nominal*(2*r['p1']-1)
                v=state[r['uf']];v['capacity']+=cap;v['stock']+=r['stock'];v['sections']+=1
            for q in [.25,.5,1.0]:
                valid_extra=valid_capacity*q
                item=dict(window=window,window_label=window_names[window],pace=pace,realization=q,additional_capacity=total_capacity*q,
                    nominal_extra=valid_extra,margin_national_share=new_margin(margin,valid_extra,p_global),
                    margin_local_second_share=margin+q*delta_local2,margin_local_first_finalists_share=margin+q*delta_local1,
                    margin_all_extra_13=margin+valid_extra,margin_all_extra_22=margin-valid_extra)
                results.append(item)
            for uf,s in state.items():by_state.append(dict(window=window,pace=pace,uf=uf,**s))
    decomposition=rec(con,'''SELECT count(*) pairs,sum(a.total) total_first,sum(b.total) total_second,
        sum(coalesce(pa.known_total,0)) known_first,sum(coalesce(pb.known_total,0)) known_second,
        sum(coalesce(pa.pre17,0)) pre_first,sum(coalesce(pb.pre17,0)) pre_second,
        sum(coalesce(pa.post17,0)) post_first,sum(coalesce(pb.post17,0)) post_second,
        sum(coalesce(pa.at17,0)) at_first,sum(coalesce(pb.at17,0)) at_second
        FROM timing_sections a JOIN timing_sections b ON a.id=b.id AND a.turn=1 AND b.turn=2
        LEFT JOIN timing_periods pa ON pa.id=a.id AND pa.turn=1 LEFT JOIN timing_periods pb ON pb.id=b.id AND pb.turn=2
        WHERE a.uf<>'zz' AND a.error IS NULL AND b.error IS NULL''')[0]
    if decomposition['pairs']:
        d=decomposition;u1=d['total_first']-d['known_first'];u2=d['total_second']-d['known_second']
        d.update(unknown_first=u1,unknown_second=u2,pre_change_lower=d['pre_second']-d['pre_first']-u1,pre_change_upper=d['pre_second']+u2-d['pre_first'])
    data=dict(kind='conditional_scenarios_not_causal_estimates',baseline_candidates=c,baseline_margin_13_minus_22=margin,
        covered_domestic_sections=covered,covered_abstention_stock=stock,sections_with_service_model=len(eligible),
        stock_without_service_model=unknown_stock,first_turn_tail_references=refs,scenarios=results,capacity_by_state=by_state,
        turnout_decomposition=decomposition)
    (ROOT/'output/isonomy-scenarios.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    def delta(v):return f'{v:+,.0f}'.replace(',','.')
    selected=[r for r in results if r['pace']=='median' and r['realization'] in (.5,1)]
    content=['<section id="isonomia"><h2>Isonomia · o que os cenários podem e não podem dizer</h2>',
       '<div class="notice"><strong>Estes são cenários condicionais, não estimativas do efeito causal da prorrogação.</strong> Mantêm os votos realizados e acrescentam participação hipotética entre aptos que não tiveram voto contado. Chegada, demanda latente, preferência de abstentes e comunicação a cada mesa não são observadas.</div>',
       f'<p>Cobertura atual: {fmt(covered)} seções domésticas com BU; estoque cadastral de {fmt(stock)} aptos sem voto presidencial contado. '
       f'O modelo de ritmo alcança {fmt(len(eligible))} seções. Há {fmt(unknown_stock)} aptos sem voto em seções sem ritmo suficientemente observado; esse grupo não recebe capacidade zero por interpretação e permanece na análise de limites.</p>',
       '<h3>Robustez matemática sob adição de votos</h3>',
       f'<p>Diferença nacional oficial 13 − 22: <strong>{fmt(margin)}</strong>. Para N novos votos nominais, dos quais uma fração p vai ao 13, '
       'a nova diferença é <code>diferença atual + N × (2p − 1)</code>. O empate obedece a <code>p = (1 − diferença atual/N)/2</code>. '
       'A preferência dos abstentes varia livremente neste quadro; não é inferida dos logs.</p>',sensitivity_plot(margin,stock),
       '<h3>Referências de capacidade dentro da janela até 19h</h3><p>A taxa é a média ou mediana dos intervalos entre confirmações observadas sem retomada registrada, com pelo menos 30 observações por seção. '
       'O número de atendimentos é limitado ao estoque cadastral. As três janelas usam: o encerramento declarado; o início final observado do protocolo; ou uma correção hipotética pela cauda estadual de primeiro turno. '
       'Nenhuma dessas medidas identifica diretamente a hora em que o portão deixou de admitir pessoas.</p>',
       '<p><strong>Importante:</strong> capacidade até 19h não é limite superior do comparecimento final sob uma regra que permite atender a fila depois do horário. '
       'É apenas uma referência operacional dentro da janela. A faixa de estoque acima é mais ampla. A hipótese também não inclui mudanças de comportamento de quem já votou.</p>',
       table(['Janela hipotética','Realização','Atendimentos adicionais de referência','Nominais sob taxa observada','Diferença 13−22: composição local do 2º','Diferença: composição entre finalistas no 1º','Extremo: todos nominais no 22'],[
            (r['window_label'],f'{r["realization"]*100:.0f}%',fmt(r['additional_capacity']),fmt(r['nominal_extra']),delta(r['margin_local_second_share']),delta(r['margin_local_first_finalists_share']),delta(r['margin_all_extra_22'])) for r in selected]),
       '<p>“Composição local” é uma hipótese ecológica: a preferência dos adicionais seria igual à proporção observada na seção. O cenário do primeiro turno usa a proporção entre os dois finalistas, sem afirmar transferência individual de eleitores. '
       'Quando essa referência local não existe, usa a proporção nacional entre os finalistas. Uma realização de 50% significa metade da capacidade hipotética, não uma probabilidade estimada de votar.</p>',
       '<h3>A mudança de comparecimento ocorreu em qual parte do relógio?</h3>']
    if decomposition['pairs']:
        d=decomposition
        content.extend([f'<p>Comparação de {fmt(d["pairs"])} seções pareadas. Os valores temporais são somente os registros conciliados; votos sem tempo utilizável ficam explícitos como desconhecidos.</p>',
            table(['Turno','Votos no BU','Antes de 17h conhecidos','Exatamente 17h conhecidos','Após 17h conhecidos','Tempo desconhecido'],[
            ('1º',fmt(d['total_first']),fmt(d['pre_first']),fmt(d['at_first']),fmt(d['post_first']),fmt(d['unknown_first'])),
            ('2º',fmt(d['total_second']),fmt(d['pre_second']),fmt(d['at_second']),fmt(d['post_second']),fmt(d['unknown_second']))]),
            f'<p>A diferença dos votos anteriores às 17h está entre <strong>{delta(d["pre_change_lower"])} e {delta(d["pre_change_upper"])}</strong>, permitindo que todos os tempos desconhecidos sejam distribuídos da forma mais desfavorável. '
            'Isso é decomposição aritmética, não uma atribuição causal da mudança ao horário. Uma política também poderia produzir antecipação ou mudança de comportamento, aspectos não identificados aqui.</p>'])
    content.extend([allocation_example(con,table,fmt),
       '<h3>O que fica sem identificação causal</h3><p>Seções que permaneceram em votação não foram sorteadas: demanda, capacidade, fila, transporte e decisão operacional podem influenciar tanto o encerramento quanto o comparecimento. '
       'Comparar simplesmente “tardias” e “não tardias” pode misturar esses mecanismos. Correlações e cenários não determinam quantos ausentes teriam chegado nem em quem votariam.</p>',
       '<p><a href="isonomy-scenarios.json">Todos os parâmetros, variantes, referências e resultados dos cenários</a>. As conclusões nacionais finais dependem da conclusão da cobertura e das verificações.</p></section>'])
    body=''.join(content);cache.write_text(body);cm.write_text(json.dumps(fp));return body
