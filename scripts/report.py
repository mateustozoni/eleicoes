"""Agrega no DuckDB e gera HTML/SVG estático. Nenhum dado bruto é enviado ao navegador."""
import collections
import fcntl
import html
import json
import math
import os
import pathlib
import sqlite3
import shutil
import time
from datetime import datetime, timezone, timedelta
import duckdb
import pyarrow as pa
from correlations import render as render_correlations
from vote_bounds import build_bounds
from anomalies import render as render_anomalies
from calibration import render as render_calibration
from analytics_store import open_store
from profile_store import published as published_profiles
from timing_report import render as render_timing
from operation_store import published as published_operations
from operation_report import render as render_operations
from scenario_report import render as render_scenarios
from hypothesis_report import render as render_hypotheses
from social_report import render as render_social

ROOT=pathlib.Path(__file__).resolve().parents[1]
UFS='ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz'.split()
IBGE=dict(zip('11 12 13 14 15 16 17 21 22 23 24 25 26 27 28 29 31 32 33 35 41 42 43 50 51 52 53'.split(),
              'ro ac am rr pa ap to ma pi ce rn pb pe al se ba mg es rj sp pr sc rs ms mt go df'.split()))
LABELS={'elector_biometric':'Digital do eleitor reconhecida','no_elector_biometric':'Identificação biográfica / sem biometria do eleitor',
        'pollworker_biometric':'Digital de mesário identificado','pollworker_unassigned_fingerprint':'Digital de mesário sem associação ao registro inicial',
        'pollworker_captured_fingerprint':'Digital de mesário capturada (vínculo não confirmado)',
        'biographic':'Habilitação biográfica explícita','manual_pending':'Procedimento manual sem desfecho classificável','unknown':'Sem classificação'}

def fmt(n):
    return '—' if n is None else f'{int(n):,}'.replace(',','.')

def clock(sec):
    day,sec=divmod(sec,86400); h,sec=divmod(sec,3600); m=sec//60
    return f'{h:02}:{m:02}'+(f' (+{day}d)' if day else '')

def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def chart(series, start, end,cutoff=61200,aria_label='Votos presidenciais registrados a cada cinco minutos; cobertura parcial quando indicada'):
    w,h=1060,300; left,right,top,bottom=70,30,22,45
    maxv=max([v for _,v in series]+[1])*1.08
    x=lambda t:left+(t-start)/(end-start)*(w-left-right)
    y=lambda v:h-bottom-v/maxv*(h-top-bottom)
    parts=[f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(aria_label,quote=True)}">']
    parts.append(f'<rect x="{x(cutoff):.1f}" y="{top}" width="{max(0,x(end)-x(cutoff)):.1f}" height="{h-top-bottom}" fill="#fef0d2"/>')
    for q in range(5):
        v=maxv*q/4; yy=y(v)
        parts.append(f'<path d="M {left} {yy:.1f} H {w-right}" stroke="#dee5ec"/><text x="{left-8}" y="{yy+4:.1f}" text-anchor="end">{fmt(v)}</text>')
    path=[]
    for t,v in series:
        path.append(f'{"M" if not path else "L"} {x(t):.1f} {y(v):.1f} L {x(t+300):.1f} {y(v):.1f}')
    parts.append('<path d="'+' '.join(path)+'" fill="none" stroke="#087e8b" stroke-width="2.2"/>')
    for t in range(math.ceil(start/3600)*3600,end+1,3600):
        parts.append(f'<text x="{x(t):.1f}" y="{h-16}" text-anchor="middle">{clock(t)}</text>')
    parts.append(f'<path d="M {x(cutoff):.1f} {top} V {h-bottom}" stroke="#a96b06" stroke-dasharray="5 4"/>')
    return ''.join(parts)+'</svg>'

def map_svg(states):
    geo=json.loads((ROOT/'data/raw/brazil-states.geojson').read_text())
    vals={r['uf']:r for r in states}; highest=max([r['post'] or 0 for r in states]+[1])
    def xy(pt): return ((pt[0]+74)*15, (6-pt[1])*15)
    out=['<svg viewBox="0 0 640 620" role="img" aria-label="Mapa do Brasil por quantidade de votos após 17h"><defs><pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse"><path d="M0 7L7 0" stroke="#000" stroke-opacity=".16" stroke-width="1"/></pattern><linearGradient id="scale"><stop stop-color="#edf5fb"/><stop offset="1" stop-color="#083c69"/></linearGradient></defs>']
    for f in geo['features']:
        uf=IBGE[str(f['properties']['codarea'])]; r=vals.get(uf,{})
        value=r.get('post') or 0; observed=r.get('eligible') or 0; expected=r.get('expected') or 0
        ratio=value/highest
        rgb=tuple(round(a+(b-a)*ratio) for a,b in zip((237,245,251),(8,60,105)))
        color='#%02x%02x%02x'%rgb if observed else '#cbd2da'
        coords=f['geometry']['coordinates']; polygons=coords if f['geometry']['type']=='MultiPolygon' else [coords]
        d=' '.join('M '+' L '.join(f'{xy(pt)[0]:.1f} {xy(pt)[1]:.1f}' for pt in ring)+' Z' for polygon in polygons for ring in polygon)
        tip=f'{uf.upper()}: {fmt(value)} votos após 17h; {fmt(observed)}/{fmt(expected)} seções com log conciliado'
        out.append(f'<g tabindex="0" aria-label="{tip}"><title>{tip}</title><path d="{d}" fill="{color}" fill-rule="evenodd" stroke="white" stroke-width="1.1"/>')
        if observed<expected:out.append(f'<path d="{d}" fill="url(#hatch)" pointer-events="none"/>')
        out.append('</g>')
    out.append('<rect x="70" y="590" width="330" height="13" fill="url(#scale)"/><text x="70" y="582">0</text><text x="400" y="582" text-anchor="end">'+fmt(highest)+'</text><text x="70" y="618">Mais claro: menos votos · Mais escuro: mais votos</text></svg>')
    return ''.join(out)

def build(cutoff=61500,snapshot=None,profile_snapshot=None,operation_snapshot=None):
    started=time.monotonic()
    generation=datetime.now(timezone.utc).isoformat()
    shutil.copyfile(ROOT/'scripts/live.js',ROOT/'output/live.js')
    prefix='1700-' if cutoff==61200 else ''
    cutoff_label='17h' if cutoff==61200 else '17h05'
    cutoff_clock='17:00:00' if cutoff==61200 else '17:05:00'
    status=json.loads((ROOT/'output/collection-status.json').read_text())
    con=open_store(snapshot,profile_snapshot,operation_snapshot)
    # Os resumos originais de 17h35 permanecem imutáveis no banco principal.
    # Esta visão agrega o recálculo exato de 17h05, sem reinterpretar os nomes antigos.
    con.execute("""CREATE TEMP VIEW sections AS SELECT
        s.* EXCLUDE(pre1735,at1735,post1735,auth_cuts1735),
        CASE WHEN s.time_eligible THEN r.pre1705 END AS pre1705,
        CASE WHEN s.time_eligible THEN r.at1705 END AS at1705,
        CASE WHEN s.time_eligible THEN r.post1705 END AS post1705,
        CASE WHEN s.time_eligible THEN r.auth_cuts1705 ELSE [] END AS auth_cuts1705
        FROM analytics.main.sections s LEFT JOIN cutoff_1705_sections r USING(id)""")
    con.execute("SET memory_limit='8GB'")
    con.execute('SET threads='+str(os.cpu_count() or 4))
    cols={r[0] for r in con.execute('DESCRIBE sections').fetchall()}
    if 'error' not in cols:con.execute('ALTER TABLE sections ADD COLUMN error VARCHAR')
    con.execute('CREATE TEMP TABLE metadata_status(id VARCHAR,status VARCHAR,fetched_utc VARCHAR,sha256 VARCHAR)')
    metadata_path=ROOT/'output/metadata-status.json'
    if metadata_path.exists():
        metadata=json.loads(metadata_path.read_text())
        if metadata.get('confirmed'):
            con.register('metadata_input',pa.Table.from_pylist([{k:r[k] for k in ['id','status','fetched_utc','sha256']} for r in metadata['confirmed']]))
            con.execute('INSERT INTO metadata_status SELECT id,status,fetched_utc,sha256 FROM metadata_input')
            con.unregister('metadata_input')
    if cutoff==61500:
        con.execute('''CREATE TEMP VIEW good AS SELECT s.* REPLACE(pre1705 AS pre,at1705 AS at17,post1705 AS post,
            auth_cuts1705 AS auth_cuts,(time_eligible AND pre1705 IS NOT NULL) AS time_eligible,
            coalesce(m.status,s.hash_status) AS hash_status),s.hash_status AS captured_hash_status,
            m.fetched_utc AS metadata_refreshed_utc,m.sha256 AS metadata_refresh_sha256,
            61500 AS cutoff_seconds FROM sections s LEFT JOIN metadata_status m ON s.id=m.id WHERE s.error IS NULL''')
    else:
        con.execute('''CREATE TEMP VIEW good AS SELECT s.* REPLACE(coalesce(m.status,s.hash_status) AS hash_status),
            s.hash_status AS captured_hash_status,m.fetched_utc AS metadata_refreshed_utc,m.sha256 AS metadata_refresh_sha256,
            61200 AS cutoff_seconds FROM sections s LEFT JOIN metadata_status m ON s.id=m.id WHERE s.error IS NULL''')
    con.execute('CREATE TEMP VIEW timed AS SELECT * FROM good WHERE time_eligible')
    def records(sql):
        cur=con.execute(sql); names=[x[0] for x in cur.description]
        return [dict(zip(names,row)) for row in cur.fetchall()]
    coverage=[]; expected_locals=collections.Counter(); aggregated=0; unpublished=0
    for uf in UFS:
        c=sqlite3.connect(str(ROOT/'data/raw'/(uf+'.sqlite')))
        config=json.loads(c.execute("SELECT payload FROM files WHERE url LIKE '%-cs.json'").fetchone()[0])
        expected=0
        for a in config['abr']:
            for m in a.get('mu',[]):
                for z in m['zon']:
                    for s in z['sec']:
                        if s.get('nsp'): aggregated+=1;continue
                        if s.get('da'):expected+=1
                        else:unpublished+=1
        coverage.append((uf,expected))
        c.close()
    con.execute('CREATE TEMP TABLE expected(uf VARCHAR, expected BIGINT)')
    con.executemany('INSERT INTO expected VALUES (?,?)',coverage)
    states=records('''SELECT e.uf,e.expected,count(g.id) analyzed,count(g.id) FILTER(WHERE g.time_eligible) eligible,
       coalesce(sum(g.post) FILTER(WHERE g.time_eligible),0) post,
       coalesce(sum(g.pre) FILTER(WHERE g.time_eligible),0) pre,
       coalesce(sum(g.at17) FILTER(WHERE g.time_eligible),0) at17,
       coalesce(sum(g.total) FILTER(WHERE g.time_eligible),0) votes
       FROM expected e LEFT JOIN good g USING(uf) GROUP BY e.uf,e.expected ORDER BY e.uf''')
    bins=records('''SELECT b.second,b.kind,sum(b.n)::BIGINT n FROM timed,unnest(bins) AS u(b) GROUP BY b.second,b.kind ORDER BY b.second,b.kind''')
    con.execute('COPY good TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(ROOT/'output'/(prefix+'sections.parquet'))])
    con.execute('COPY (SELECT * EXCLUDE(bins) FROM good) TO ? (HEADER, DELIMITER \';\')',[str(ROOT/'output'/(prefix+'sections.csv'))])
    sums=records('''SELECT count(*) sections,sum(total) total,sum(v13) v13,sum(v22) v22,sum(blank) blank,sum("null") null_votes,
       sum(bu_bio) bu_bio,sum(bu_biography) bu_biography,sum(bu_no_bio) bu_no_bio,
       count(*) FILTER(WHERE hash_status='Recebido') provisional_sections,count(*) FILTER(WHERE hash_status='Totalizado') totalized_sections,
       count(*) FILTER(WHERE NOT match) mismatches,count(*) FILTER(WHERE clock_backwards>0) clock_issues,
       count(*) FILTER(WHERE NOT match AND bu_kind='dadosSecao') urna_mismatches,
       count(*) FILTER(WHERE bu_kind='dadosSA') sa_sections,
       count(*) FILTER(WHERE uf='zz') exterior FROM good''')[0]
    ts=records('''SELECT count(*) sections,coalesce(sum(pre),0) pre,coalesce(sum(post),0) post,coalesce(sum(at17),0) at17,
       min("first") AS "first",max("last") AS "last" FROM timed''')[0]
    con.execute('''CREATE TEMP VIEW bu_hours AS SELECT *,
       date_diff('second',TIMESTAMP '2026-10-25 00:00:00',try_strptime(opening_local,'%Y%m%dT%H%M%S'))+offset_hours*3600 AS opening_bsb,
       date_diff('second',TIMESTAMP '2026-10-25 00:00:00',try_strptime(closing_local,'%Y%m%dT%H%M%S'))+offset_hours*3600 AS closing_bsb
       FROM good WHERE offset_hours IS NOT NULL''')
    closing=records(f'''SELECT count(*) FILTER(WHERE closing_bsb<={cutoff}) at_or_before_17,
       count(*) FILTER(WHERE closing_bsb>{cutoff}) after_17,
       count(*) FILTER(WHERE closing_bsb<=61200) at_or_before_strict17,
       count(*) FILTER(WHERE closing_bsb>61200 AND closing_bsb<=61500) within_closing_margin,
       count(*) FILTER(WHERE closing_bsb>61500) after_closing_margin,
       count(*) FILTER(WHERE closing_bsb<61200 AND full_turnout) early_full_turnout,
       count(*) FILTER(WHERE closing_bsb<61200 AND NOT full_turnout) early_without_full_turnout,
       count(*) FILTER(WHERE closing_bsb IS NULL) missing_time,
       min(opening_bsb) first_opening,max(closing_bsb) last_closing,
       max(closing_bsb) FILTER(WHERE time_eligible AND closing_bsb BETWEEN 0 AND 86400) last_closing_for_timeline,
       count(*) FILTER(WHERE time_eligible AND post>0) sections_with_late_vote
       FROM bu_hours''')[0]
    margin=records('''SELECT count(*) sections,coalesce(sum(pre),0) before_17,
       coalesce(sum(total-pre-post1705),0) window_17_to_1705,
       coalesce(sum(post1705),0) after_1705 FROM sections
       WHERE error IS NULL AND time_eligible AND pre1705 IS NOT NULL''')[0]
    # Local-level 'no late votes' requires every published principal section at that local to be collected.
    # Until complete collection, even apparently complete local groups remain provisional.
    locals_=records('''SELECT uf,municipality,zone,local,bool_or(time_eligible AND post>0) late,bool_and(time_eligible) reconciled,count(*) sections
       FROM good WHERE uf<>'zz' GROUP BY uf,municipality,zone,local''')
    late=sum(r['late'] for r in locals_)
    no_observed=sum(not r['late'] for r in locals_)
    complete=all(r['analyzed']==r['expected'] for r in states)
    reprocessing_pending=con.execute('SELECT count(*) FROM sections WHERE time_eligible AND pre1705 IS NULL').fetchone()[0] if cutoff==61500 else 0
    complete=complete and not reprocessing_pending
    complete_ufs={r['uf'] for r in states if r['analyzed']==r['expected']}
    no_confirmed=sum(not r['late'] and r['reconciled'] and r['uf'] in complete_ufs for r in locals_)
    local_unknown=sum(not r['late'] and not (r['reconciled'] and r['uf'] in complete_ufs) for r in locals_)
    payload=dict(cutoff_seconds=cutoff,cutoff_label=cutoff_label,collection=status,states=states,bins=bins,sums=sums,timed=ts,local_late_observed=late,
                 local_no_late_observed_provisional=no_observed,local_no_late_confirmed=no_confirmed,local_unknown_among_seen=local_unknown,
                 closing=closing,margin=margin,reprocessing_pending=reprocessing_pending,complete=complete,aggregated_sections=aggregated,unpublished_principal_sections=unpublished)
    (ROOT/'output'/(prefix+'summary.json')).write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    errors=records('SELECT id,error FROM sections WHERE error IS NOT NULL')
    (ROOT/'output'/(prefix+'analysis-errors.json')).write_text(json.dumps(errors,ensure_ascii=False,indent=2))
    counts=collections.defaultdict(collections.Counter)
    for r in bins:counts[r['second']][r['kind']]=r['n']
    start=min(28800,ts['first'] or 28800)//300*300
    end=max(68400,ts['last'] or 68400,closing['last_closing_for_timeline'] or 68400)//300*300+300
    series=[(t,counts[t]['vote']) for t in range(start,end,300)]
    enabled_seconds=[r['second'] for r in bins if r['kind'].startswith('enabled_')]
    enabled_start=min([28800]+enabled_seconds)//300*300
    enabled_end=max(end,max([68400]+enabled_seconds)//300*300+300)
    enabled_series=[(t,sum(v for k,v in counts[t].items() if k.startswith('enabled_'))) for t in range(enabled_start,enabled_end,300)]
    enabled_totals=collections.Counter()
    for row in bins:
        if row['kind'].startswith('enabled_'):enabled_totals[row['kind'][8:]]+=row['n']
    habilitation_html=('<section><h2>Horário da liberação · habilitações de eleitores</h2>'
        '<p>Esta série usa o instante da mensagem <code>Eleitor foi habilitado</code>. A série de votos usa a confirmação presidencial. '
        'São momentos e contagens diferentes: uma habilitação pode ser cancelada, interrompida ou não terminar em confirmação presidencial. '
        'Por isso, esta tabela conta <strong>eventos de habilitação</strong>, e não votos de candidatos.</p>'
        +chart(enabled_series,enabled_start,enabled_end,cutoff,'Habilitações de eleitores por horário da liberação, em intervalos de cinco minutos')
        +table(['Procedimento anterior à habilitação','Habilitações registradas'],[(LABELS.get(k,k),fmt(v)) for k,v in enabled_totals.items()])
        +table(['Intervalo (Brasília)','Todas as habilitações','Digital do eleitor','Digital de mesário identificado','Digital de mesário capturada / não associada','Biográfico / sem biometria','Método não classificado'],[
            (f'{clock(t)} – {clock(t+300)}',fmt(n),fmt(counts[t]['enabled_elector_biometric']),fmt(counts[t]['enabled_pollworker_biometric']),
             fmt(counts[t]['enabled_pollworker_captured_fingerprint']+counts[t]['enabled_pollworker_unassigned_fingerprint']),
             fmt(counts[t]['enabled_no_elector_biometric']+counts[t]['enabled_biographic']),fmt(counts[t]['enabled_unknown']+counts[t]['enabled_manual_pending']))
            for t,n in enabled_series])
        +'<p class="muted">Universo: os mesmos logs domésticos conciliados usados na análise temporal. O método de identificação é o registrado no fluxo anterior à habilitação; a série não revela a escolha de voto.</p></section>')
    auth=collections.Counter()
    for r in bins:
        if r['kind'].startswith('vote_'):auth[r['kind'][5:]]+=r['n']
    now=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y às %H:%M:%S')
    national=json.loads((ROOT/'data/raw/national.json').read_text())
    national_candidates={c['n']:int(c['vap']) for cargo in national['carg'] if cargo['cd']=='1' for a in cargo['agr'] for p in a['par'] for c in p['cand']}
    bounds=build_bounds(con,national_candidates)
    bounds['cutoff_seconds']=cutoff
    (ROOT/'output'/(prefix+'candidate-time-bounds.json')).write_text(json.dumps(bounds,ensure_ascii=False,indent=2))
    bound_rows=[]
    if bounds['valid']:
        for key,label in [('pre','Antes das 17h'),('at17','Exatamente 17:00:00'),('post','Após as 17h')]:
            b=bounds['periods'][key];a=b['candidates']['13'];c=b['candidates']['22']
            winner={'13':'Lula','22':'Flávio Bolsonaro',None:'Não determinado pelos dados'}[b['provable_winner']]
            bound_rows.append((label,f'{fmt(a["minimum"])} a {fmt(a["maximum"])}',f'{fmt(c["minimum"])} a {fmt(c["maximum"])}',winner))
    bounds_html=table(['Período','13 · mínimo a máximo possível','22 · mínimo a máximo possível','Vencedor demonstrável'],bound_rows) if bounds['valid'] else '<p>'+html.escape(bounds['reason'])+'</p>'
    correlation_html=render_correlations(con,table,fmt,prefix)
    anomaly_html=render_anomalies(con,table,fmt)
    calibration_html=render_calibration(con,table,fmt)
    timing_html=render_timing(con,table,fmt)
    operations_html=render_operations(con,table,fmt)
    scenarios_html=render_scenarios(con,table,fmt)
    hypotheses_html=render_hypotheses(con,table,fmt)+render_social(con,table,fmt)
    expected_total=sum(r['expected'] for r in states)
    cutoff_context=(f'<nav><a href="report-1700.html">Referência: 17h</a> · <a href="report.html">Comparação com margem: 17h05</a></nav>'
        f'<div class="notice"><strong>Corte ativo: {cutoff_label} de Brasília.</strong> Mapas, locais, correlações, densidades e limites por candidato usam este corte. '
        'A margem de 5 minutos é uma escolha analítica para comparação; não altera o horário oficial nem prova que houve extensão da votação. '
        'Os eventos de voto e de encerramento são mostrados separadamente.</div>')
    if reprocessing_pending:
        cutoff_context+=f'<p class="muted">{fmt(reprocessing_pending)} BUs já coletados estão sendo reprocessados para o corte de 17h05. A cobertura temporal indica apenas os já reprocessados e conciliados.</p>'
    margin_html=('<section><h2>Referência de 17h e janela operacional de 5 minutos</h2>'+table(
        ['Eventos de voto presidencial','Quantidade'],[
        ('Antes de 17:00:00',fmt(margin['before_17'])),
        ('De 17:00:00 até 17:05:00, inclusive',fmt(margin['window_17_to_1705'])),
        ('Após 17:05:00',fmt(margin['after_1705']))])+
        f'<p>Comparação nos mesmos {fmt(margin["sections"])} logs conciliados com os dois cortes. Um voto às 17h03 aparece na janela intermediária; um BU encerrado às 17h03 fica dentro da margem de encerramento. São eventos diferentes.</p>'+table(
        ['Encerramento declarado no BU (seções já lidas)','Quantidade'],[
        ('Até 17:00:00',fmt(closing['at_or_before_strict17'])),
        ('Após 17:00:00 e até 17:05:00',fmt(closing['within_closing_margin'])),
        ('Após 17:05:00',fmt(closing['after_closing_margin'])),
        ('Antes de 17h, com comparecimento igual ao eleitorado apto',fmt(closing['early_full_turnout'])),
        ('Antes de 17h, sem comparecimento integral declarado',fmt(closing['early_without_full_turnout']))])+
        '<p>Comparecimento integral é verificado por votos presidenciais no BU iguais ao número de aptos informado para a eleição presidencial. É uma característica do boletim, não uma conclusão sobre o motivo ou a regularidade do encerramento.</p></section>')
    final_pdf=ROOT/'output/pdf/relatorio-presidencial-2026.pdf'
    final_audit=ROOT/'output/final-audit.json'
    publication_html=''
    documentary_html=''
    if (ROOT/'output/documentary-analysis.json').exists():
        from documentary_report import overview
        documentary_html=overview()
    if final_audit.exists():
        audit=json.loads(final_audit.read_text())
        if audit.get('passed'):
            publication_html='<section id="auditoria-final"><h2>Auditoria integral</h2><p>Recontagem de todos os BUs publicados: soma nacional conferida, sem diferenças; identificadores dos perfis e protocolos dos dois turnos conferidos. <a href="final-audit.json">Auditoria e limitações</a>.</p>'
            bridge=audit.get('first_turn_recount',{}).get('classification_bridge')
            if bridge:
                publication_html+=f'<h3>Primeiro turno: ponte entre categorias de voto</h3><p>Na releitura integral, cada candidato da lista nacional confere. O tipo nulo dos BUs soma {fmt(bridge["official_vn"])}; outros {fmt(bridge["nominal_code28"])} votos constam como nominais no código 28, ausente da lista nacional consultada. Essa quantidade coincide com o campo nacional vnt; vn + vnt = tvn ({fmt(bridge["official_tvn"])}). O resumo bruto preserva o código 28 em demais votos. A igualdade explica a diferença de classificação, sem inferir uma causa jurídica. <a href="first-turn-vote-type-audit.json">Conferência por tipo/código</a> · <a href="first-turn-code28-sections.parquet">Seções e fontes do código 28</a>.</p>'
            bc=audit.get('biometric_crosscheck')
            if bc:
                publication_html+=f'<h3>Conferência de biometria</h3><p>Nos {fmt(bc["sections"])} logs do corpus temporal, as confirmações classificadas com digital reconhecida do eleitor coincidem com o contador biométrico do BU em todas as seções ({fmt(bc["confirmation_biometric"])} eventos). As habilitações classificadas nesse instante somam {fmt(bc["enablement_biometric"])} e diferem do contador do BU em {fmt(bc["bu_vs_enablement_differences"])} seções. Habilitação e confirmação são mensagens distintas; tentativas, cancelamentos e contexto de classificação devem ser examinados antes de tratar a diferença como erro.</p>'
            if final_pdf.exists():publication_html+='<p><a href="pdf/relatorio-presidencial-2026.pdf"><strong>Baixar relatório analítico completo em PDF</strong></a></p>'
            publication_html+='</section>'
    page=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Presidente 2026 · Votação por horário</title><style>',
    '''*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#162b40;font:16px/1.55 system-ui,sans-serif}main{max-width:1240px;margin:auto;padding:44px 30px}h1{font-size:42px;line-height:1.1;letter-spacing:-1.5px;max-width:800px}h2{font-size:25px;margin-top:0}h3{font-size:18px}section{background:white;border:1px solid #dce4ed;border-radius:14px;padding:28px;margin:22px 0}p{max-width:950px}.eyebrow{color:#087e8b;text-transform:uppercase;font-size:12px;letter-spacing:2px;font-weight:750}.muted{color:#526779}.notice{background:#fff4d9;border-left:5px solid #b17d1f;padding:18px 22px;border-radius:6px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}.card{padding:20px;border:1px solid #dce4ed;border-radius:12px;background:white}.num{display:block;font-size:29px;font-weight:750;color:#075c67}.grid{display:grid;grid-template-columns:1.1fr 1fr;gap:28px}svg{width:100%;height:auto}svg text{font:12px system-ui;fill:#41586d}svg g:focus path{stroke:#fa7800;stroke-width:3}.scroll{overflow:auto;max-height:580px}table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}th,td{padding:10px 12px;text-align:right;white-space:nowrap;border-bottom:1px solid #e4eaf0}th{position:sticky;top:0;background:#edf3f8;color:#344f67}th:first-child,td:first-child{text-align:left}a{color:#056b85}code{font-size:12px}details{margin:18px 0}summary{cursor:pointer;font-weight:650}.pill{background:#e4f3f2;color:#075c67;border-radius:20px;padding:5px 12px;font-size:12px}@media(max-width:850px){main{padding:28px 16px}h1{font-size:32px}.cards{grid-template-columns:1fr 1fr}.grid{grid-template-columns:1fr}section{padding:20px}}@media print{body{background:white}.scroll{max-height:none;overflow:visible}section{break-inside:avoid}th{position:static}}''','</style><main>',
    '<div class="eyebrow">Dados oficiais TSE · Pleito 3221 · Eleição 6258</div><h1>Quando os votos para presidente foram registrados</h1>',
    f'<p class="muted">Segundo turno · 25 de outubro de 2026 · Horário de Brasília<br>Relatório gerado em {now}. Cálculos locais em Python e DuckDB.</p>',
    '__CUTOFF_CONTEXT__',
    '__LIVE_STATUS__',
    f'<div class="notice"><strong>{"Coleta concluída; confira as exclusões de qualidade abaixo." if complete else "COLETA PARCIAL — os números ainda não representam todo o Brasil."}</strong><br>{fmt(sums["sections"])} de {fmt(expected_total)} seções publicadas analisadas; {fmt(ts["sections"])} conciliadas e aptas à série temporal. Hachuras indicam exclusões do corpus temporal. Compare quantidades e taxas junto com os denominadores e a cobertura de cada UF. Há {fmt(sums["provisional_sections"])} BUs ainda com metadado Recebido, preservados como provisórios.</div>',
    '<div class="cards">'+''.join(f'<div class="card">{label}<span class="num">{fmt(v)}</span></div>' for label,v in [('Votos antes das 17h',ts['pre']),('Exatamente às 17:00:00',ts['at17']),('Votos após as 17h',ts['post']),('Locais com registro após 17h¹',late)])+'</div>',
    '<section><h2>Votos a cada cinco minutos</h2><p>Contagem de confirmações para <strong>Presidente</strong>, incluindo nulos atribuídos por suspensão. Inclui brancos e nulos; não revela candidato. A faixa amarela começa às 17h. Cada degrau representa o intervalo fechado à esquerda e aberto à direita, por exemplo [17:00, 17:05).</p>',chart(series,start,end,cutoff),
    f'<p class="muted">Somente seções cujo total de eventos presidenciais confere com o BU e sem regressão de relógio detectada. Primeira ocorrência: {clock(ts["first"] or 28800)}; última: {clock(ts["last"] or 28800)}. Registros às 17:00:00 estão separados no corte exato, mas integram o intervalo [17:00,17:05) no gráfico.</p></section>',
    '__DOCUMENTARY_MILESTONES__',
    publication_html,
    '__MARGIN_COMPARISON__',
    '__CALIBRATION__',
    '__TIMING_ANALYSIS__',
    '__OPERATIONS_ANALYSIS__',
    '__SCENARIO_ANALYSIS__',
    '__HYPOTHESES__',
    '<section><h2>Encerramento da seção e último voto são medidas distintas</h2><p>O horário de encerramento declarado no BU pode ser posterior ao último evento de voto. Uma seção encerrada após 17h não necessariamente recebeu votos após 17h. A tabela usa os BUs domésticos já lidos, convertidos para Brasília.</p>',
    table(['Medida','Seções'],[('Encerramento declarado no BU até 17:00:00',fmt(closing['at_or_before_17'])),('Encerramento declarado no BU após 17:00:00',fmt(closing['after_17'])),('Com confirmação presidencial após 17h em log conciliado',fmt(closing['sections_with_late_vote'])),('BU sem horário de encerramento interpretável',fmt(closing['missing_time']))]),
    '<p class="muted">São contagens do corpus coletado; não medem quantas seções receberam autorização de prorrogação nem identificam a causa do encerramento tardio.</p></section>',
    '<section><h2>Mapa · votos após as 17h por estado</h2><p>Escala linear por <strong>quantidade absoluta</strong>: mais escuro indica mais votos registrados após 17:00:00. O tamanho do eleitorado influencia essa quantidade. Hachuras indicam cobertura incompleta; cinza indica ausência de seções conciliadas. Passe o cursor ou use Tab para consultar cada UF.</p><div class="grid">',map_svg([r for r in states if r['uf']!='zz']),
    table(['UF','Votos após 17h','Logs conciliados / publicados','Cobertura'],[(r['uf'].upper(),fmt(r['post']),f'{fmt(r["eligible"])} / {fmt(r["expected"])}',f'{r["eligible"]/max(1,r["expected"])*100:.2f}%') for r in states if r['uf']!='zz']),'</div><p class="muted">Malha simplificada oficial do IBGE. Exterior não faz parte do mapa.</p></section>',
    correlation_html,
    '<section><h2>Locais com e sem votos após as 17h</h2>',
    table(['Medida','Quantidade','Interpretação'],[('Com evento após 17h observado¹',fmt(late),'Limite inferior enquanto a coleta estiver parcial'),('Sem evento após 17h nos logs conciliados já lidos¹',fmt(no_observed),'Provisório: não equivale a “não houve”'),('Sem votos após 17h, locais com cobertura completa',fmt(no_confirmed),'UF integralmente coletada e todas as seções do local conciliadas'),('Locais vistos ainda indeterminados',fmt(local_unknown),'Sem evento tardio confirmado e sem cobertura suficiente para concluir ausência')]),
    '<p>¹ Local administrativo identificado por UF + município + zona + número do local no BU. Não é contagem de prédios físicos únicos. A ausência de um evento em um log incompleto não prova que não houve voto. Um voto tardio também não prova, isoladamente, que decorreu da prorrogação: pode ser atendimento de fila já existente.</p></section>',
    '<section><h2>Digital e habilitação manual</h2><p>Classificação do procedimento que antecede uma confirmação presidencial. A digital do eleitor e a digital do mesário são categorias distintas. Capturar uma digital não significa reconhecer o eleitor. Não há associação com o candidato escolhido.</p>',
    table(['Procedimento observado','Votos presidenciais subsequentes'],[(LABELS.get(k,k),fmt(v)) for k,v in auth.items()]),
    '<p><strong>“Sem digital do mesário” não é inferido pela ausência de uma linha.</strong> Procedimentos sem evidência suficiente ficam sem classificação. Habilitações canceladas ou que não resultaram em confirmação presidencial não entram nesta tabela.</p>',
    table(['Referência nos BUs já lidos (Brasil e exterior)','Eleitores'],[('Digital do eleitor reconhecida',fmt(sums['bu_bio'])),('Habilitados por biografia',fmt(sums['bu_biography'])),('Sem biometria cadastrada',fmt(sums['bu_no_bio']))]),
    '<p class="muted">Os campos do BU medem comparecimento da seção, enquanto a série acima mede confirmações de presidente em seções conciliadas no Brasil; universos diferentes. Os BUs não fornecem o horário dessas categorias.</p></section>',
    '__HABILITATIONS__',
    '<section><h2>Todos os intervalos de cinco minutos</h2>',
    table(['Intervalo (Brasília)','Votos','Digital eleitor','Digital mesário identificado','Digital mesário capturada / não associada','Biográfico / sem biometria','Não classificado'],
       [(f'{clock(t)} – {clock(t+300)}',fmt(counts[t]['vote']),fmt(counts[t]['vote_elector_biometric']),fmt(counts[t]['vote_pollworker_biometric']),fmt(counts[t]['vote_pollworker_captured_fingerprint']+counts[t]['vote_pollworker_unassigned_fingerprint']),fmt(counts[t]['vote_no_elector_biometric']+counts[t]['vote_biographic']),fmt(counts[t]['vote_unknown']+counts[t]['vote_manual_pending'])) for t,_ in series]),
    '<p>Zeros significam nenhum evento no corpus conciliado desta versão; com coleta parcial, não significam zero em toda a eleição.</p></section>',
    '<section><h2>Candidatos · resultado geral e limite da análise horária</h2><p><strong>Não é possível calcular os votos exatos de cada candidato antes e depois das 17h com BU e log.</strong> O BU contém totais por candidato; o log contém eventos com horário, sem a escolha. Distribuir os votos dos candidatos proporcionalmente ao horário criaria uma estimativa sem base individual.</p>',
    table(['Candidato','Soma local dos BUs já analisados','Referência nacional TSE'],[('13 · Lula',fmt(sums['v13']),fmt(national_candidates['13'])),('22 · Flávio Bolsonaro',fmt(sums['v22']),fmt(national_candidates['22'])),('Brancos',fmt(sums['blank']),fmt(int(national['v']['vb']))),('Nulos',fmt(sums['null_votes']),fmt(int(national['v']['tvn'])))]),
    '<p>A soma é feita diretamente sobre cada BU publicado, preservando sua procedência. A auditoria final apresenta a comparação com a referência nacional e o universo de arquivos disponíveis.</p></section>',
    '<section><h2>O que a matemática permite concluir sobre o vencedor por período</h2><p>Sem associar candidatos a eventos individuais, é possível calcular limites. Se uma seção tem N votos no BU, C de um candidato e H confirmações no período, o candidato pode ter entre <code>máx(0, C − (N − H))</code> e <code>mín(C, H)</code> votos naquele período.</p>',
    bounds_html,
    '<p>Os limites somam somente seções com hash Totalizado, log conciliado e horário interpretável. Os votos de cada candidato fora desse conjunto ficam livres para qualquer período, alargando os intervalos. A referência nacional oficial fornece o total de cada candidato. Só se declara vencedor de um período quando o seu mínimo supera o máximo do adversário. Intervalos sobrepostos não permitem determinar quem venceu.</p><p class="muted">São limites matemáticos, não estimativas nem uma reconstrução do voto. <a href="candidate-time-bounds.json">Contas e limites em JSON</a>.</p></section>',
    '<section><h2>Método, qualidade e referências</h2>',
    f'<p>{fmt(aggregated)} seções agregadas do índice não geram uma segunda urna independente. {fmt(unpublished)} seções principais não tinham arquivo auxiliar publicado no índice consultado. {fmt(sums["urna_mismatches"])} seções de urna apresentam diferença entre BU e eventos presidenciais; {fmt(sums["sa_sections"])} BUs são do Sistema de Apuração, com comparação VOTA separada; {fmt(sums["clock_issues"])} seções têm regressão de relógio detectada. Os <a href="#ocorrencias">dossiês acima</a> detalham os casos. {fmt(sums["exterior"])} seções do exterior foram lidas e ficam fora do corte temporal de Brasília nesta versão.</p>',
    '<p>Usa-se o único hash <code>Totalizado</code> do auxiliar oficial; quando ele não existe, o único <code>Recebido</code> é preservado como provisório. Hashes ambíguos ou rejeitados não entram nas contas. Logs internos de contingência são percorridos recursivamente e linhas idênticas são deduplicadas. O relógio do log é o do equipamento, sujeito a ajustes; a conciliação numérica não autentica seu relógio nem sua assinatura.</p>',
    '<p>Auxiliares provisórios são revalidados sem substituir a captura original. Só se promove o status a Totalizado quando o hash e os nomes de BU/log permanecem idênticos. O histórico fica em <code>data/metadata-refresh.sqlite</code>; os dados exportados distinguem o status capturado do revalidado. <a href="metadata-status.json">Revalidação dos metadados</a>.</p>',
    '<p>Conversão para Brasília: Acre +2h; Amazonas +1h, com as onze exceções oficiais +2h; MT, MS, RO e RR +1h; Fernando de Noronha −1h. Demais localidades do Brasil sem deslocamento. Exterior requer mapeamento de fuso próprio e permanece separado. Corte: pré &lt;17:00:00; exato =17:00:00; pós &gt;17:00:00.</p>',
    '<p>Fontes: <a href="https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados">TSE · especificações e limite de requisições</a>; <a href="https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/log-do-ecossistema">formato do log 2026</a>; <a href="https://www.tse.jus.br/comunicacao/noticias/2026/Outubro/esclarecimento-sobre-prorrogacao-da-votacao">nota sobre prorrogação</a>; <a href="https://www.justicaeleitoral.jus.br/fato-ou-boato/checagens/2026/e-falso-que-eleitores-devam-votar-em-dias-diferentes-dependendo-do-candidato-escolhido-entenda">fusos e onze municípios do Amazonas</a>; <a href="https://servicodados.ibge.gov.br/api/docs/malhas?versao=3">malha IBGE</a>.</p>',
    '<p>São usados os leiautes ASN.1 do ZIP oficial do TSE fornecido pelo usuário e a documentação oficial de logs. A leitura foi comparada ao leiaute usado inicialmente; votos, horários e identificação coincidiram após normalizar nomes de tipos de contingência. <a href="layout-verification.json">Resultado da comparação de leiautes</a>. Os SHA-256 e URLs dos payloads ficam nos bancos SQLite locais. Não foi feita verificação criptográfica das assinaturas TSE nesta versão.</p>',
    '<p><a href="summary.json">Agregados JSON</a> · <a href="sections.csv">Seções CSV</a> · <a href="sections.parquet">Seções Parquet</a> · <a href="collection-status.json">Estado da coleta</a></p></section></main></html>']
    live_html='''<section id="status-panel" aria-label="Acompanhamento da coleta"><h2>Coleta e processamento ao vivo</h2><p>Consultas automáticas a cada 5 segundos. Os gráficos incorporam a última geração concluída no processamento local; a posição da leitura é preservada.</p><div class="cards"><div class="card">Seções baixadas<strong class="num" id="live-downloaded">—</strong></div><div class="card">Pendentes<strong class="num" id="live-pending">—</strong></div><div class="card">Erros de download<strong class="num" id="live-errors">—</strong></div><div class="card">Processadas na revisão atual<strong class="num" id="live-analyzed">—</strong></div></div><progress id="live-progress" value="0" max="100" style="width:100%;height:18px"></progress><p><strong id="live-percent">—</strong> · Arquivos originais salvos: <span id="live-volume">—</span> · Taxa recente: <span id="live-rate">—</span></p><p class="muted">Sinal do coletor: <span id="live-download-time">—</span><br>Sinal do processamento: <span id="live-analysis-time">—</span><br>Última consulta desta página: <span id="live-poll-time">—</span><br><span id="live-message">Conectando ao estado local…</span></p><noscript>Abra com JavaScript habilitado no servidor local para acompanhar automaticamente.</noscript></section>'''
    live_html=live_html.replace('<noscript>','<p>Referência do primeiro turno: <strong id="live-reference">consultando…</strong> · <a href="#primeiro-turno">Ver calibração por estado</a></p><noscript>')
    live_html=live_html.replace('<noscript>','<p>Coleta integral do 1º turno: <strong id="live-first-full">consultando…</strong><br>Tempos — 1º turno: <strong id="live-timing-first">consultando…</strong><br>Tempos — 2º turno: <strong id="live-timing-second">consultando…</strong><br>Revalidação de metadados: <strong id="live-metadata">consultando…</strong><br>Finalização: <strong id="live-finalization">consultando…</strong></p><noscript>')
    content=''.join(page)
    if cutoff==61500:
        content=content.replace('17h','17h05').replace('17:00:00','17:05:00').replace('[17:00, 17:05)','[17:05, 17:10)').replace('[17:00,17:05)','[17:05,17:10)')
    content=content.replace('__DOCUMENTARY_MILESTONES__',documentary_html)
    content=content.replace('__CUTOFF_CONTEXT__',cutoff_context).replace('__MARGIN_COMPARISON__',margin_html).replace('__LIVE_STATUS__',live_html)
    content=content.replace('__CALIBRATION__',calibration_html)
    content=content.replace('__TIMING_ANALYSIS__',timing_html)
    content=content.replace('__OPERATIONS_ANALYSIS__',operations_html)
    content=content.replace('__SCENARIO_ANALYSIS__',scenarios_html)
    content=content.replace('__HYPOTHESES__',hypotheses_html)
    content=content.replace('__HABILITATIONS__',habilitation_html)
    content=content.replace('<section><h2>Método, qualidade e referências</h2>',anomaly_html+'<section><h2>Método, qualidade e referências</h2>')
    content=content.replace('<main>',f'<main data-prefix="{prefix}" data-generation="{generation}">').replace('</html>','<script src="live.js"></script></html>')
    for name in ('summary.json','analysis-errors.json','sections.csv','sections.parquet','section-correlations.csv','section-correlations.parquet','correlations.json','candidate-time-bounds.json'):
        content=content.replace('href="'+name+'"','href="'+prefix+name+'"')
    target=ROOT/'output'/('report-1700.html' if cutoff==61200 else 'report.html');tmp=target.with_suffix('.tmp');tmp.write_text(content);tmp.replace(target)
    meta=dict(generation=generation,html_name=target.name,cutoff_seconds=cutoff,analyzed=sums['sections'],eligible=ts['sections'],build_seconds=round(time.monotonic()-started,2))
    mp=ROOT/'output'/(prefix+'report-meta.json');mp.with_suffix('.tmp').write_text(json.dumps(meta));mp.with_suffix('.tmp').replace(mp)
    con.close()
    print(json.dumps(dict(report=str(target),analyzed=sums['sections'],eligible=ts['sections'],expected=expected_total,complete=complete)))

if __name__=='__main__':
    with (ROOT/'output/.report.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        snapshot=sorted((ROOT/'data/derived').glob('part-*.jsonl'))
        profile_snapshot=published_profiles()
        operation_snapshot=published_operations()
        build(61200,snapshot,profile_snapshot,operation_snapshot)
        build(61500,snapshot,profile_snapshot,operation_snapshot)
