"""Evidência empírica sobre o significado temporal do BU e dos procedimentos de encerramento."""
import html
import json
import math
import pathlib
import hashlib
from operation_store import exists

ROOT=pathlib.Path(__file__).resolve().parents[1]
PRODUCER_SHA=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()

def records(con,sql):
    c=con.execute(sql);return [dict(zip([x[0] for x in c.description],r)) for r in c.fetchall()]

def span_plot(rows,field,label):
    selected=[r for r in rows if r.get(field+'_p95') is not None]
    ufs=sorted({r['uf'] for r in rows});maximum=max([60]+[r[field+'_p95'] for r in selected])*1.1
    x=lambda v:75+v/maximum*800;h=70+len(ufs)*27
    out=[f'<svg viewBox="0 0 1060 {h}" role="img" aria-label="{html.escape(label)}">']
    for i in range(6):
        xx=x(maximum*i/5);out.append(f'<path d="M{xx:.1f} 30V{h-25}" stroke="#e0e8ee"/><text x="{xx:.1f}" y="22" text-anchor="middle">{maximum*i/300:.1f} min</text>')
    for i,uf in enumerate(ufs):
        yy=45+i*27;out.append(f'<text x="45" y="{yy+5}" text-anchor="end">{uf.upper()}</text>')
        for turn,color,dy in [(1,'#3a6793',-3),(2,'#b87510',4)]:
            r=next((r for r in selected if r['uf']==uf and r['turn']==turn),None)
            if r:
                median,p95=r[field+'_median'],r[field+'_p95']
                out.append(f'<path d="M{x(median):.1f} {yy+dy}H{x(p95):.1f}" stroke="{color}" stroke-width="3"/><circle cx="{x(median):.1f}" cy="{yy+dy}" r="3" fill="{color}"><title>{uf.upper()}, {turn}º turno: P50 {median:.1f}s; P95 {p95:.1f}s</title></circle>')
    return ''.join(out)+'</svg><p class="muted">Azul: 1º turno; dourado: 2º turno. Ponto = mediana; traço até P95. É uma faixa da distribuição observada, não um intervalo de confiança.</p>'

def render(con,table,fmt):
    if not exists(con):return '<section id="encerramento-protocolo"><h2>Etapas de encerramento</h2><p>O protocolo registrado nos dois turnos está sendo processado.</p></section>'
    fingerprint=dict(data=list(con.execute('SELECT count(*),sum(sections) FROM operation_batches').fetchone()),code=PRODUCER_SHA,render_abi=2)
    cache=ROOT/'output/operation-fragment.html';meta=ROOT/'output/operation-fragment-meta.json'
    if cache.exists() and meta.exists() and json.loads(meta.read_text())==fingerprint:return cache.read_text()
    coverage=records(con,'''SELECT turn,count(*) sections,count(*) FILTER(WHERE timing_eligible AND uf<>'zz') eligible,
       count(*) FILTER(WHERE error IS NOT NULL) errors FROM operation_sections GROUP BY turn ORDER BY turn''')
    agreement=records(con,'''SELECT turn,count(*) n,count(*) FILTER(WHERE abs(declared_minus_confirmed_seconds)<=1) matching,
       median(abs(declared_minus_confirmed_seconds)) median_abs_delta,
       median(print_after_confirmation_seconds) median_print_after,
       quantile_cont(print_after_confirmation_seconds,.95) p95_print_after
       FROM operation_sections WHERE timing_eligible AND single_confirmation AND declared_minus_confirmed_seconds IS NOT NULL AND uf<>'zz'
       GROUP BY turn ORDER BY turn''')
    states=records(con,'''SELECT turn,uf,count(*) n,
       count(protocol_span_seconds) protocol_n,median(protocol_span_seconds) protocol_median,quantile_cont(protocol_span_seconds,.95) protocol_p95,
       count(print_after_confirmation_seconds) print_n,median(print_after_confirmation_seconds) print_median,quantile_cont(print_after_confirmation_seconds,.95) print_p95,
       median(first_print_seconds) physical_print_median,quantile_cont(first_print_seconds,.95) physical_print_p95,
       avg(deadline_tail_seconds) tail_mean,median(deadline_tail_seconds) tail_median,quantile_cont(deadline_tail_seconds,.95) tail_p95
       FROM operation_sections WHERE timing_eligible AND single_confirmation AND uf<>'zz' GROUP BY turn,uf ORDER BY uf,turn''')
    timelines=records(con,'''SELECT turn,(floor(declared_close_bsb/300)*300)::INTEGER AS "second",count(*) n
        FROM operation_sections WHERE timing_eligible AND declared_close_bsb IS NOT NULL AND uf<>'zz'
        GROUP BY turn,"second" ORDER BY turn,"second"''')
    (ROOT/'output/operations-summary.json').write_text(json.dumps(dict(coverage=coverage,agreement=agreement,by_state=states,closing_by_time=timelines),ensure_ascii=False,indent=2))
    con.execute('COPY operation_sections TO ? (FORMAT PARQUET,COMPRESSION ZSTD)',[str(ROOT/'output/operations-sections.parquet')])
    exceptions=records(con,"SELECT id,name,turn,source,last_vote_bsb,protocol_start_bsb,procedure_confirmed_bsb,declared_close_bsb,declared_minus_confirmed_seconds FROM operation_sections WHERE timing_eligible AND single_confirmation AND uf<>'zz' AND abs(declared_minus_confirmed_seconds)>1 ORDER BY turn,id")
    (ROOT/'output/closing-clock-exceptions.json').write_text(json.dumps(exceptions,ensure_ascii=False,indent=2))
    def tm(v):return '—' if v is None else f'{int(v)//3600:02}:{int(v)%3600//60:02}:{int(v)%60:02}'
    exception_html='<h3>Diferenças superiores a um segundo neste confronto</h3>'+table(['Seção','Turno','Último voto (Brasília)','Início final','Confirmação no log','Declarado BU','BU − log'],[(r['id'],r['turn'],tm(r['last_vote_bsb']),tm(r['protocol_start_bsb']),tm(r['procedure_confirmed_bsb']),tm(r['declared_close_bsb']),str(r['declared_minus_confirmed_seconds'])+'s') for r in exceptions])+'<p>São diferenças observadas do relógio/campo registrado; a causa específica não foi comprovada. Nos dois casos atuais de três segundos, ambos os horários ficam depois de 17h e antes de 17h05, sem alteração de classificação. <a href="closing-clock-exceptions.json">Dados e fontes dos casos</a>.</p>'
    latest=records(con,"SELECT id,name,turn,last_vote_bsb,protocol_start_bsb,procedure_confirmed_bsb,declared_close_bsb,deadline_tail_seconds,source FROM operation_sections WHERE timing_eligible AND turn=2 AND uf<>'zz' ORDER BY declared_close_bsb DESC LIMIT 10")
    (ROOT/'output/latest-closing-examples.json').write_text(json.dumps(latest,ensure_ascii=False,indent=2))
    latest_html='<h3>Encerramentos declarados mais tardios</h3>'+table(['Seção','Município','Último voto (Brasília)','Início final','Encerramento BU'],[(r['id'],html.escape(r['name']),tm(r['last_vote_bsb']),tm(r['protocol_start_bsb']),tm(r['declared_close_bsb'])) for r in latest])+'<p>São os maiores horários de encerramento do corpus conciliado, não horários até os quais houve votos. Em Chapada Gaúcha/MG, por exemplo, o último voto é 16:27:42, e a etapa final começa às 23:04:10, com encerramento às 23:04:42. O motivo da espera não foi comprovado. <a href="latest-closing-examples.json">Registros, horários e URLs de origem</a>.</p>'
    nf=lambda v:'—' if v is None else f'{v:.1f}s'
    body=['<section id="encerramento-protocolo"><h2>O que a hora do BU representa nos registros</h2>',
       '<p>O protocolo permite separar o último voto, o início observado da etapa final, a confirmação do encerramento, a geração e a primeira impressão do BU. Uma hora tardia no campo de encerramento não pode ser automaticamente explicada por impressão demorada.</p>',
       '<p>O <a href="https://www.justicaeleitoral.jus.br/mesario/cursos/mesarios-brasil/m6-o-que-fazer-apos-a-votacao/a1-encerramento-da-votacao/index.html">treinamento oficial da Justiça Eleitoral</a> prevê o encerramento ordinário a partir das 17h, depois de atendida a fila. Por isso, fechar o procedimento alguns minutos depois de 17h não comprova, por si só, recepção adicional de eleitores pela prorrogação.</p>',
       table(['Turno','Seções revisadas','Brasil com registros conciliados','Erros de processamento'],[(r['turn'],fmt(r['sections']),fmt(r['eligible']),fmt(r['errors'])) for r in coverage]),
       '<h3>Confronto independente nos casos com uma única confirmação de encerramento</h3>',
       table(['Turno','Seções','BU coincide com confirmação (±1s)','Não coincidem','Mediana |diferença|','Mediana até fim da 1ª impressão','P95 até fim da 1ª impressão'],[(r['turn'],fmt(r['n']),f'{fmt(r["matching"])} ({100*r["matching"]/max(1,r["n"]):.4f}%)',fmt(r['n']-r['matching']),nf(r['median_abs_delta']),nf(r['median_print_after']),nf(r['p95_print_after'])) for r in agreement]),
       '<p>O confronto acima usa somente seções com uma ocorrência de confirmação, evitando selecionar entre vários eventos para aumentar artificialmente a concordância. Em registros múltiplos, os dados preservam a seleção mais próxima do horário declarado, mas esses casos ficam fora deste confronto.</p>',
       exception_html,latest_html,
       '<h3>Da etapa final observada até confirmar o encerramento</h3>',span_plot(states,'protocol','Etapa final de encerramento, mediana e P95 por UF'),
       '<h3>Da confirmação até concluir a primeira impressão</h3>',span_plot(states,'print','Confirmação até primeira impressão de BU, por UF'),
       table(['UF','Turno','P50 etapa final','P95 etapa final','P50 até 1ª impressão','P95 até 1ª impressão','P50 impressão física'],[(r['uf'].upper(),r['turn'],nf(r['protocol_median']),nf(r['protocol_p95']),nf(r['print_median']),nf(r['print_p95']),nf(r['physical_print_median'])) for r in states]),
       '<p>A etapa final começa no último evento de menu/pergunta observado antes da confirmação e depois do último voto. Não é todo o trabalho da mesa. Os tempos são do relógio registrado pela urna e podem ter limitações de precisão. Impressões posteriores, cópias adicionais e recuperação de resultados são fenômenos distintos.</p>',
       '<p><a href="operations-summary.json">Agregados do protocolo</a> · <a href="operations-sections.parquet">Dados por seção</a>. A cobertura integral publicada e as exclusões estão discriminadas acima.</p></section>']
    content=''.join(body);cache.write_text(content);meta.write_text(json.dumps(fingerprint));return content
